from __future__ import annotations

import csv
import fcntl
import json
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from typing import Any

import psycopg

from app.db import connection_info, fetch_all, fetch_one
from app.notifications.evolution import notify_daily_report
from app.reports.renderer import render_html, render_pdf
from app.settings import settings
from app.storage.filesystem import report_root, validate_report_component


REPORT_LOCKS: dict[str, Lock] = {}
REPORT_LOCKS_GUARD = Lock()


class ReportAlreadyRunning(RuntimeError):
    pass


@contextmanager
def report_generation_lock(report_name: str):
    report_name = validate_report_component(report_name, "report_name")
    with REPORT_LOCKS_GUARD:
        report_lock = REPORT_LOCKS.setdefault(report_name, Lock())

    if not report_lock.acquire(blocking=False):
        raise ReportAlreadyRunning("A report generation job is already running")

    lock_file = Path(settings.reports_dir) / f".report-generation-{report_name}.lock"
    try:
        lock_file.parent.mkdir(parents=True, exist_ok=True)
        with lock_file.open("w", encoding="utf-8") as file:
            try:
                fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ReportAlreadyRunning(
                    "A report generation job is already running"
                ) from exc
            try:
                file.write(f"{datetime.now().isoformat()}\n")
                file.flush()
                yield
            finally:
                fcntl.flock(file.fileno(), fcntl.LOCK_UN)
                lock_file.unlink(missing_ok=True)
    finally:
        report_lock.release()


DATASET_QUERIES = {
    "instance": """
        select
          now() as collected_at,
          current_database() as database_name,
          current_user as database_user,
          inet_server_addr()::text as server_addr,
          inet_server_port() as server_port,
          pg_postmaster_start_time() as postmaster_start_time,
          version() as postgres_version
    """,
    "database_sizes": """
        select
          datname as database_name,
          pg_database_size(datname) as bytes,
          pg_size_pretty(pg_database_size(datname)) as pretty_size
        from pg_database
        where datallowconn
        order by pg_database_size(datname) desc
    """,
    "connections": """
        select
          datname,
          usename,
          application_name,
          client_addr::text as client_addr,
          state,
          count(*)::int as sessions
        from pg_stat_activity
        group by datname, usename, application_name, client_addr, state
        order by sessions desc, datname, usename
    """,
    "long_queries": """
        select
          pid,
          usename,
          datname,
          client_addr::text as client_addr,
          state,
          now() - query_start as duration,
          left(regexp_replace(query, '\\s+', ' ', 'g'), 500) as query
        from pg_stat_activity
        where query_start is not null
          and now() - query_start > interval '5 minutes'
          and state <> 'idle'
        order by query_start
        limit 50
    """,
    "locks": """
        select
          locktype,
          mode,
          granted,
          count(*)::int as locks
        from pg_locks
        group by locktype, mode, granted
        order by granted, locks desc, locktype, mode
    """,
}


DATABASE_LIST_QUERY = """
    select datname as database_name
    from pg_database
    where datallowconn
      and not datistemplate
    order by datname
"""


MULTI_DATABASE_DATASET_QUERIES = {
    "table_sizes": """
        select
          current_database() as database_name,
          schemaname,
          relname as table_name,
          pg_total_relation_size((quote_ident(schemaname) || '.' || quote_ident(relname))::regclass) as total_bytes,
          pg_size_pretty(pg_total_relation_size((quote_ident(schemaname) || '.' || quote_ident(relname))::regclass)) as total_size,
          n_live_tup,
          n_dead_tup,
          last_vacuum,
          last_autovacuum,
          last_analyze,
          last_autoanalyze
        from pg_stat_user_tables
        order by pg_total_relation_size((quote_ident(schemaname) || '.' || quote_ident(relname))::regclass) desc
        limit 50
    """,
    "vacuum_health": """
        select
          current_database() as database_name,
          schemaname,
          relname as table_name,
          n_live_tup,
          n_dead_tup,
          case
            when n_live_tup > 0 then round((n_dead_tup::numeric / n_live_tup) * 100, 2)
            else 0
          end as dead_tuple_percent,
          last_vacuum,
          last_autovacuum,
          last_analyze,
          last_autoanalyze
        from pg_stat_user_tables
        order by n_dead_tup desc
        limit 50
    """,
}


PG_STAT_STATEMENTS_QUERIES = {
    "top_sql_by_total_time": """
        select
          current_database() as database_name,
          s.queryid::text as queryid,
          calls,
          round(total_exec_time::numeric, 2) as total_exec_time_ms,
          round(mean_exec_time::numeric, 2) as mean_exec_time_ms,
          round(max_exec_time::numeric, 2) as max_exec_time_ms,
          rows,
          round((rows::numeric / nullif(calls, 0)), 2) as rows_per_call,
          shared_blks_hit,
          shared_blks_read,
          temp_blks_read,
          temp_blks_written,
          left(regexp_replace(s.query, '\\s+', ' ', 'g'), 1000) as query
        from pg_stat_statements s
        where s.dbid = (
          select oid from pg_database where datname = current_database()
        )
        order by total_exec_time desc
        limit 10
    """,
    "top_sql_by_mean_time": """
        select
          current_database() as database_name,
          s.queryid::text as queryid,
          calls,
          round(total_exec_time::numeric, 2) as total_exec_time_ms,
          round(mean_exec_time::numeric, 2) as mean_exec_time_ms,
          round(max_exec_time::numeric, 2) as max_exec_time_ms,
          rows,
          round((rows::numeric / nullif(calls, 0)), 2) as rows_per_call,
          shared_blks_hit,
          shared_blks_read,
          temp_blks_read,
          temp_blks_written,
          left(regexp_replace(s.query, '\\s+', ' ', 'g'), 1000) as query
        from pg_stat_statements s
        where calls >= 5
          and s.dbid = (
            select oid from pg_database where datname = current_database()
          )
        order by mean_exec_time desc
        limit 10
    """,
    "top_sql_by_io": """
        select
          current_database() as database_name,
          s.queryid::text as queryid,
          calls,
          round(total_exec_time::numeric, 2) as total_exec_time_ms,
          round(mean_exec_time::numeric, 2) as mean_exec_time_ms,
          rows,
          shared_blks_hit,
          shared_blks_read,
          shared_blks_dirtied,
          shared_blks_written,
          temp_blks_read,
          temp_blks_written,
          (shared_blks_read + temp_blks_read) as read_blocks,
          left(regexp_replace(s.query, '\\s+', ' ', 'g'), 1000) as query
        from pg_stat_statements s
        where s.dbid = (
          select oid from pg_database where datname = current_database()
        )
        order by (shared_blks_read + temp_blks_read) desc, total_exec_time desc
        limit 10
    """,
}


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _downsample_rows(rows: list[dict[str, Any]], max_points: int = 288) -> list[dict[str, Any]]:
    if len(rows) <= max_points:
        return rows
    step = len(rows) / max_points
    return [rows[int(index * step)] for index in range(max_points)]


def _collect_os_metrics_history(hours: int = 24) -> list[dict[str, Any]]:
    status_dir = Path(settings.data_dir) / "status"
    if not status_dir.exists():
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    rows: list[dict[str, Any]] = []
    for path in sorted(status_dir.glob("*.jsonl")):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            if not line.strip():
                continue
            try:
                snapshot = json.loads(line)
            except json.JSONDecodeError:
                continue

            collected_at = _parse_datetime(snapshot.get("collected_at"))
            if collected_at is None or collected_at < cutoff:
                continue

            os_metrics = snapshot.get("os_metrics") or {}
            if os_metrics.get("status") != "ok":
                continue
            hosts = os_metrics.get("hosts") or []
            if not hosts:
                continue

            host = hosts[0]
            filesystems = os_metrics.get("filesystems") or []
            filesystem_rows = [
                filesystem
                for filesystem in filesystems
                if _float_or_none(filesystem.get("used_percent")) is not None
            ]
            max_filesystem = max(
                filesystem_rows,
                key=lambda filesystem: _float_or_none(filesystem.get("used_percent")) or 0,
                default={},
            )
            cpu_idle_percent = _float_or_none(host.get("cpu_idle_percent"))
            cpu_used_percent = (
                round(100 - cpu_idle_percent, 2)
                if cpu_idle_percent is not None
                else None
            )

            rows.append(
                {
                    "collected_at": collected_at.isoformat(),
                    "hostname": host.get("hostname") or host.get("host_id") or "",
                    "cpu_used_percent": cpu_used_percent,
                    "cpu_iowait_percent": _float_or_none(host.get("cpu_iowait_percent")),
                    "memory_used_percent": _float_or_none(host.get("memory_used_percent")),
                    "max_filesystem_used_percent": _float_or_none(
                        max_filesystem.get("used_percent")
                    ),
                    "max_filesystem_mount_point": max_filesystem.get("mount_point", ""),
                    "collector_lag_seconds": _float_or_none(
                        host.get("collector_lag_seconds")
                    ),
                }
            )

    rows.sort(key=lambda row: row["collected_at"])
    return _downsample_rows(rows)


def _chart_points(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for row in rows:
        value = _float_or_none(row.get(key))
        if value is None:
            continue
        collected_at = _parse_datetime(row.get("collected_at"))
        label = collected_at.astimezone().strftime("%d/%m %H:%M") if collected_at else ""
        points.append({"label": label, "value": round(value, 2)})
    return points


def _os_metrics_charts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not rows:
        return []

    return [
        {
            "title": "CPU usada - ultimas 24h",
            "unit": "%",
            "max": 100,
            "threshold": None,
            "points": _chart_points(rows, "cpu_used_percent"),
        },
        {
            "title": "CPU iowait - ultimas 24h",
            "unit": "%",
            "max": 100,
            "threshold": settings.os_warning_max_iowait_percent,
            "points": _chart_points(rows, "cpu_iowait_percent"),
        },
        {
            "title": "Memoria usada - ultimas 24h",
            "unit": "%",
            "max": 100,
            "threshold": settings.os_warning_max_memory_used_percent,
            "points": _chart_points(rows, "memory_used_percent"),
        },
        {
            "title": "Filesystem mais cheio - ultimas 24h",
            "unit": "%",
            "max": 100,
            "threshold": settings.os_warning_max_filesystem_used_percent,
            "points": _chart_points(rows, "max_filesystem_used_percent"),
        },
        {
            "title": "Lag do coletor de SO - ultimas 24h",
            "unit": "s",
            "max": None,
            "threshold": settings.os_warning_max_collector_lag_seconds,
            "points": _chart_points(rows, "collector_lag_seconds"),
        },
    ]


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        if not rows:
            file.write("")
            return
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _collect_multi_database_datasets() -> dict[str, list[dict[str, Any]]]:
    databases = [row["database_name"] for row in fetch_all(DATABASE_LIST_QUERY)]
    discovered_databases = len(databases)
    limited = False
    if (
        settings.max_databases_per_report > 0
        and len(databases) > settings.max_databases_per_report
    ):
        databases = databases[: settings.max_databases_per_report]
        limited = True
    datasets = {
        "database_scan_status": [
            {
                "discovered_databases": discovered_databases,
                "scanned_databases": 0,
                "failed_databases": 0,
                "limited": limited,
                "max_databases_per_report": settings.max_databases_per_report,
            }
        ],
        "database_scan_errors": [],
    }
    for name in MULTI_DATABASE_DATASET_QUERIES:
        datasets[name] = []

    scanned_databases = 0
    for database in databases:
        try:
            for name, sql in MULTI_DATABASE_DATASET_QUERIES.items():
                datasets[name].extend(fetch_all(sql, database=database))
            scanned_databases += 1
        except psycopg.Error as exc:
            datasets["database_scan_errors"].append(
                {
                    "database_name": database,
                    "error_type": exc.__class__.__name__,
                    "error": str(exc).splitlines()[0],
                }
            )

    datasets["database_scan_status"][0]["scanned_databases"] = scanned_databases
    datasets["database_scan_status"][0]["failed_databases"] = len(
        datasets["database_scan_errors"]
    )

    datasets["table_sizes"] = sorted(
        datasets["table_sizes"],
        key=lambda row: row.get("total_bytes") or 0,
        reverse=True,
    )[:50]
    datasets["vacuum_health"] = sorted(
        datasets["vacuum_health"],
        key=lambda row: row.get("n_dead_tup") or 0,
        reverse=True,
    )[:50]

    return datasets


def _pg_stat_statements_available(database: str) -> bool:
    row = fetch_one(
        """
        select exists (
          select 1
          from pg_extension
          where extname = 'pg_stat_statements'
        ) as available
        """,
        database=database,
    )
    return bool(row and row.get("available"))


def _collect_pg_stat_statements() -> dict[str, list[dict[str, Any]]]:
    datasets = {
        "pg_stat_statements_status": [],
        "pg_stat_statements_scan_errors": [],
    }
    for name, sql in PG_STAT_STATEMENTS_QUERIES.items():
        datasets[name] = []

    databases = [row["database_name"] for row in fetch_all(DATABASE_LIST_QUERY)]
    if (
        settings.max_databases_per_report > 0
        and len(databases) > settings.max_databases_per_report
    ):
        databases = databases[: settings.max_databases_per_report]

    for database in databases:
        try:
            if not _pg_stat_statements_available(database):
                datasets["pg_stat_statements_status"].append(
                    {
                        "database_name": database,
                        "available": False,
                        "reason": "pg_stat_statements extension is not enabled",
                    }
                )
                continue

            datasets["pg_stat_statements_status"].append(
                {
                    "database_name": database,
                    "available": True,
                    "reason": "pg_stat_statements extension is enabled",
                }
            )
            for name, sql in PG_STAT_STATEMENTS_QUERIES.items():
                datasets[name].extend(fetch_all(sql, database=database))
        except psycopg.Error as exc:
            datasets["pg_stat_statements_scan_errors"].append(
                {
                    "database_name": database,
                    "error_type": exc.__class__.__name__,
                    "error": str(exc).splitlines()[0],
                }
            )

    datasets["top_sql_by_total_time"] = sorted(
        datasets["top_sql_by_total_time"],
        key=lambda row: row.get("total_exec_time_ms") or 0,
        reverse=True,
    )[:10]
    datasets["top_sql_by_mean_time"] = sorted(
        datasets["top_sql_by_mean_time"],
        key=lambda row: row.get("mean_exec_time_ms") or 0,
        reverse=True,
    )[:10]
    datasets["top_sql_by_io"] = sorted(
        datasets["top_sql_by_io"],
        key=lambda row: row.get("read_blocks") or 0,
        reverse=True,
    )[:10]
    return datasets


def generate_daily_report(report_name: str | None = None) -> dict:
    report_name = report_name or settings.report_name
    with report_generation_lock(report_name):
        return _generate_daily_report(report_name)


def _generate_daily_report(report_name: str | None = None) -> dict:
    report_name = report_name or settings.report_name
    now = datetime.now()
    date_key = now.strftime("%Y-%m-%d")
    output_dir = report_root(report_name, date_key)
    output_dir.mkdir(parents=True, exist_ok=True)

    datasets: dict[str, list[dict[str, Any]]] = {}
    csv_files: dict[str, str] = {}
    for name, sql in DATASET_QUERIES.items():
        rows = fetch_all(sql)
        datasets[name] = rows
        csv_path = output_dir / f"{name}.csv"
        _write_csv(csv_path, rows)
        csv_files[name] = str(csv_path)

    for name, rows in _collect_multi_database_datasets().items():
        datasets[name] = rows
        csv_path = output_dir / f"{name}.csv"
        _write_csv(csv_path, rows)
        csv_files[name] = str(csv_path)

    for name, rows in _collect_pg_stat_statements().items():
        datasets[name] = rows
        csv_path = output_dir / f"{name}.csv"
        _write_csv(csv_path, rows)
        csv_files[name] = str(csv_path)

    os_history_rows = _collect_os_metrics_history()
    datasets["os_metrics_history"] = os_history_rows
    csv_path = output_dir / "os_metrics_history.csv"
    _write_csv(csv_path, os_history_rows)
    csv_files["os_metrics_history"] = str(csv_path)

    instance = datasets["instance"][0] if datasets["instance"] else {}
    connections = sum(row.get("sessions", 0) for row in datasets["connections"])
    waiting_locks = sum(
        row.get("locks", 0)
        for row in datasets["locks"]
        if row.get("granted") is False
    )

    pg_stat_statuses = datasets.get("pg_stat_statements_status", [])
    pg_stat_enabled_databases = sum(
        1 for row in pg_stat_statuses if row.get("available")
    )
    summary = {
        "database": instance.get("database_name", ""),
        "server": f"{instance.get('server_addr', '')}:{instance.get('server_port', '')}",
        "database_user": instance.get("database_user", ""),
        "total_connections": connections,
        "long_queries": len(datasets["long_queries"]),
        "waiting_locks": waiting_locks,
        "scanned_databases": datasets["database_scan_status"][0].get(
            "scanned_databases", 0
        ),
        "failed_databases": datasets["database_scan_status"][0].get(
            "failed_databases", 0
        ),
        "largest_database": datasets["database_sizes"][0].get("database_name", "")
        if datasets["database_sizes"]
        else "",
        "largest_database_size": datasets["database_sizes"][0].get("pretty_size", "")
        if datasets["database_sizes"]
        else "",
        "pg_stat_statements": "enabled"
        if pg_stat_enabled_databases > 0
        else "disabled",
        "pg_stat_statements_enabled_databases": pg_stat_enabled_databases,
        "pg_stat_statements_failed_databases": len(
            datasets.get("pg_stat_statements_scan_errors", [])
        ),
        "top_sql_by_total_time": len(datasets.get("top_sql_by_total_time", [])),
        "top_sql_by_mean_time": len(datasets.get("top_sql_by_mean_time", [])),
        "top_sql_by_io": len(datasets.get("top_sql_by_io", [])),
    }

    report = {
        "report_name": report_name,
        "collected_at": now.isoformat(),
        "connection": connection_info(),
        "summary": summary,
        "datasets": datasets,
        "charts": _os_metrics_charts(os_history_rows),
        "csv_files": csv_files,
        "output_dir": str(output_dir),
    }

    html_path = output_dir / "summary.html"
    pdf_path = output_dir / "summary.pdf"
    render_html(report, html_path)
    render_pdf(report, pdf_path)
    report["html"] = str(html_path)
    report["pdf"] = str(pdf_path)
    notify_daily_report(report)
    return report

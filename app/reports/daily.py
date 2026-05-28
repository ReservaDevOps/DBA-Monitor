from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any

from app.db import connection_info, fetch_all, fetch_one
from app.reports.renderer import render_html, render_pdf
from app.settings import settings
from app.storage.filesystem import report_root


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
    "table_sizes": """
        select
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
    "vacuum_health": """
        select
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
          queryid::text as queryid,
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
          left(regexp_replace(query, '\\s+', ' ', 'g'), 1000) as query
        from pg_stat_statements
        order by total_exec_time desc
        limit 10
    """,
    "top_sql_by_mean_time": """
        select
          queryid::text as queryid,
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
          left(regexp_replace(query, '\\s+', ' ', 'g'), 1000) as query
        from pg_stat_statements
        where calls >= 5
        order by mean_exec_time desc
        limit 10
    """,
    "top_sql_by_io": """
        select
          queryid::text as queryid,
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
          left(regexp_replace(query, '\\s+', ' ', 'g'), 1000) as query
        from pg_stat_statements
        order by (shared_blks_read + temp_blks_read) desc, total_exec_time desc
        limit 10
    """,
}


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        if not rows:
            file.write("")
            return
        writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _pg_stat_statements_available() -> bool:
    row = fetch_one(
        """
        select exists (
          select 1
          from pg_extension
          where extname = 'pg_stat_statements'
        ) as available
        """
    )
    return bool(row and row.get("available"))


def _collect_pg_stat_statements() -> dict[str, list[dict[str, Any]]]:
    if not _pg_stat_statements_available():
        return {
            "pg_stat_statements_status": [
                {
                    "available": False,
                    "reason": "pg_stat_statements extension is not enabled in the current database",
                }
            ]
        }

    datasets = {
        "pg_stat_statements_status": [
            {
                "available": True,
                "reason": "pg_stat_statements extension is enabled",
            }
        ]
    }
    for name, sql in PG_STAT_STATEMENTS_QUERIES.items():
        datasets[name] = fetch_all(sql)
    return datasets


def generate_daily_report(report_name: str | None = None) -> dict:
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

    for name, rows in _collect_pg_stat_statements().items():
        datasets[name] = rows
        csv_path = output_dir / f"{name}.csv"
        _write_csv(csv_path, rows)
        csv_files[name] = str(csv_path)

    instance = datasets["instance"][0] if datasets["instance"] else {}
    connections = sum(row.get("sessions", 0) for row in datasets["connections"])
    waiting_locks = sum(
        row.get("locks", 0)
        for row in datasets["locks"]
        if row.get("granted") is False
    )

    summary = {
        "database": instance.get("database_name", ""),
        "server": f"{instance.get('server_addr', '')}:{instance.get('server_port', '')}",
        "database_user": instance.get("database_user", ""),
        "total_connections": connections,
        "long_queries": len(datasets["long_queries"]),
        "waiting_locks": waiting_locks,
        "largest_database": datasets["database_sizes"][0].get("database_name", "")
        if datasets["database_sizes"]
        else "",
        "largest_database_size": datasets["database_sizes"][0].get("pretty_size", "")
        if datasets["database_sizes"]
        else "",
        "pg_stat_statements": "enabled"
        if datasets["pg_stat_statements_status"][0].get("available")
        else "disabled",
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
        "csv_files": csv_files,
        "output_dir": str(output_dir),
    }

    html_path = output_dir / "summary.html"
    pdf_path = output_dir / "summary.pdf"
    render_html(report, html_path)
    render_pdf(report, pdf_path)
    report["html"] = str(html_path)
    report["pdf"] = str(pdf_path)
    return report

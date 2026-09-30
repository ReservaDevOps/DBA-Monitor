from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any

from app.notifications.evolution import send_text_notification
from app.settings import settings
from app.storage.filesystem import load_status_warning_state, save_status_warning_state


logger = logging.getLogger(__name__)


WarningItem = tuple[str, str]


def _total_connections(snapshot: dict[str, Any]) -> int:
    return sum(int(row.get("sessions", 0)) for row in snapshot.get("activity", []))


def _database_size_gb(snapshot: dict[str, Any]) -> float:
    bytes_value = int(snapshot.get("database_size", {}).get("bytes") or 0)
    return bytes_value / 1024 / 1024 / 1024


def _connection_usage(snapshot: dict[str, Any]) -> tuple[int, int | None, float | None]:
    total_connections = _total_connections(snapshot)
    max_connections = snapshot.get("server_settings", {}).get("max_connections")
    if max_connections in {None, 0, "0"}:
        return total_connections, None, None

    max_connections = int(max_connections)
    return total_connections, max_connections, total_connections / max_connections * 100


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _os_warning_items(snapshot: dict[str, Any]) -> list[WarningItem]:
    os_metrics = snapshot.get("os_metrics", {})
    if os_metrics.get("status") != "ok":
        return []

    warnings: list[WarningItem] = []
    hosts = os_metrics.get("hosts", [])
    filesystems = os_metrics.get("filesystems", [])

    for host in hosts:
        hostname = host.get("hostname") or host.get("host_id") or "host"
        host_key = host.get("host_id") or hostname
        memory_used_percent = _float_or_none(host.get("memory_used_percent"))
        if (
            settings.os_warning_max_memory_used_percent is not None
            and memory_used_percent is not None
            and memory_used_percent > settings.os_warning_max_memory_used_percent
        ):
            warnings.append(
                (
                    f"os-memory:{host_key}",
                    "Memoria do SO: "
                    f"{hostname} {memory_used_percent:.1f}% > "
                    f"{settings.os_warning_max_memory_used_percent:.1f}%",
                )
            )

        iowait_percent = _float_or_none(host.get("cpu_iowait_percent"))
        if (
            settings.os_warning_max_iowait_percent is not None
            and iowait_percent is not None
            and iowait_percent > settings.os_warning_max_iowait_percent
        ):
            warnings.append(
                (
                    f"os-iowait:{host_key}",
                    "CPU iowait: "
                    f"{hostname} {iowait_percent:.1f}% > "
                    f"{settings.os_warning_max_iowait_percent:.1f}%",
                )
            )

        lag_seconds = _float_or_none(host.get("collector_lag_seconds"))
        if (
            settings.os_warning_max_collector_lag_seconds is not None
            and lag_seconds is not None
            and lag_seconds > settings.os_warning_max_collector_lag_seconds
        ):
            warnings.append(
                (
                    f"os-collector-lag:{host_key}",
                    "Coletor SO atrasado: "
                    f"{hostname} {lag_seconds:.0f}s > "
                    f"{settings.os_warning_max_collector_lag_seconds:.0f}s",
                )
            )

    for filesystem in filesystems:
        used_percent = _float_or_none(filesystem.get("used_percent"))
        if (
            settings.os_warning_max_filesystem_used_percent is None
            or used_percent is None
            or used_percent <= settings.os_warning_max_filesystem_used_percent
        ):
            continue

        hostname = filesystem.get("hostname") or filesystem.get("host_id") or "host"
        host_key = filesystem.get("host_id") or hostname
        mount_point = filesystem.get("mount_point") or "filesystem"
        warnings.append(
            (
                f"os-filesystem:{host_key}:{mount_point}",
                "Filesystem: "
                f"{hostname}:{mount_point} {used_percent:.1f}% > "
                f"{settings.os_warning_max_filesystem_used_percent:.1f}%",
            )
        )

    return warnings


def _warning_items(snapshot: dict[str, Any]) -> list[WarningItem]:
    warnings: list[WarningItem] = []

    total_connections, max_connections, connection_usage_percent = _connection_usage(
        snapshot
    )
    if (
        settings.status_warning_max_connections is not None
        and total_connections > settings.status_warning_max_connections
    ):
        warnings.append(
            (
                "postgres-connections-total",
                "Conexoes totais: "
                f"{total_connections} > {settings.status_warning_max_connections}",
            )
        )

    if (
        settings.status_warning_max_connections_percent is not None
        and connection_usage_percent is not None
        and connection_usage_percent > settings.status_warning_max_connections_percent
    ):
        warnings.append(
            (
                "postgres-connections-percent",
                "Uso de conexoes: "
                f"{connection_usage_percent:.1f}% "
                f"({total_connections}/{max_connections}) > "
                f"{settings.status_warning_max_connections_percent}%",
            )
        )

    long_queries = len(snapshot.get("long_queries", []))
    if (
        settings.status_warning_max_long_queries is not None
        and long_queries > settings.status_warning_max_long_queries
    ):
        warnings.append(
            (
                "postgres-long-queries",
                "Queries longas: "
                f"{long_queries} > {settings.status_warning_max_long_queries}",
            )
        )

    waiting_locks = int(snapshot.get("locks", {}).get("waiting_locks") or 0)
    if (
        settings.status_warning_max_waiting_locks is not None
        and waiting_locks > settings.status_warning_max_waiting_locks
    ):
        warnings.append(
            (
                "postgres-waiting-locks",
                "Locks em espera: "
                f"{waiting_locks} > {settings.status_warning_max_waiting_locks}",
            )
        )

    database_size_gb = _database_size_gb(snapshot)
    if (
        settings.status_warning_max_database_size_gb is not None
        and database_size_gb > settings.status_warning_max_database_size_gb
    ):
        warnings.append(
            (
                "postgres-database-size",
                "Tamanho do banco atual: "
                f"{database_size_gb:.1f} GB > {settings.status_warning_max_database_size_gb} GB",
            )
        )

    warnings.extend(_os_warning_items(snapshot))

    return warnings


def _warning_lines(snapshot: dict[str, Any]) -> list[str]:
    return [line for _, line in _warning_items(snapshot)]


def _warning_key(snapshot: dict[str, Any]) -> str:
    return "|".join(key for key, _ in _warning_items(snapshot))


def _message(snapshot: dict[str, Any], warnings: list[str]) -> str:
    instance = snapshot.get("instance", {})
    connection = snapshot.get("connection", {})
    server = f"{instance.get('server_addr') or connection.get('host', '')}:{instance.get('server_port') or connection.get('port', '')}"
    lines = [
        f"Warning DBA Monitor - {settings.report_name}",
        f"Coletado em: {snapshot.get('collected_at', '')}",
        f"Banco: {instance.get('database_name', connection.get('database', ''))}",
        f"Servidor: {server}",
        "",
        *warnings,
    ]
    return "\n".join(lines)


def notify_status_warnings(snapshot: dict[str, Any]) -> None:
    if not settings.status_warnings_enabled:
        return

    warning_items = _warning_items(snapshot)
    warnings = [line for _, line in warning_items]
    if not warnings:
        return

    now = datetime.now(timezone.utc)
    state = load_status_warning_state()
    warning_key = "|".join(key for key, _ in warning_items)
    last_sent_at = state.get("last_sent_at")
    last_warning_key = state.get("warning_key")

    if last_sent_at and last_warning_key == warning_key:
        elapsed_seconds = now.timestamp() - datetime.fromisoformat(
            last_sent_at
        ).timestamp()
        if elapsed_seconds < settings.status_warning_cooldown_seconds:
            return

    try:
        send_text_notification(_message(snapshot, warnings))
    except Exception as exc:
        logger.exception("Status warning notification failed: %s", exc)
        return

    save_status_warning_state(
        {
            "last_sent_at": now.isoformat(),
            "warning_key": warning_key,
            "warnings": warnings,
        }
    )

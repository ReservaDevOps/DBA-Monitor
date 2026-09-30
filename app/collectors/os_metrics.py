from __future__ import annotations

from typing import Any

from app.db import fetch_all
from app.settings import settings


def _short_error(exc: Exception) -> str:
    message = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
    if len(message) > 160:
        message = f"{message[:157]}..."
    if message:
        return f"{exc.__class__.__name__}: {message}"
    return exc.__class__.__name__


def collect_os_metrics() -> dict[str, Any]:
    if not settings.os_metrics_enabled:
        return {"status": "disabled"}

    try:
        hosts = fetch_all(
            """
            select
              host_id,
              hostname,
              os_name,
              kernel_release,
              postgres_data_directory,
              collected_at,
              collector_lag_seconds,
              load1,
              load5,
              load15,
              cpu_user_percent,
              cpu_system_percent,
              cpu_idle_percent,
              cpu_iowait_percent,
              cpu_irq_percent,
              cpu_softirq_percent,
              cpu_steal_percent,
              memory_total_bytes,
              memory_available_bytes,
              memory_used_percent,
              swap_total_bytes,
              swap_free_bytes,
              swap_used_percent,
              process_count
            from dba_monitor.os_metric_latest
            order by collected_at desc nulls last, host_id
            """
        )
        filesystems = fetch_all(
            """
            select
              host_id,
              hostname,
              collected_at,
              collector_lag_seconds,
              mount_point,
              device,
              filesystem_type,
              total_bytes,
              used_bytes,
              free_bytes,
              available_bytes,
              used_percent
            from dba_monitor.os_filesystem_latest
            order by host_id, used_percent desc nulls last, mount_point
            """
        )
    except Exception as exc:
        return {"status": "unavailable", "error": _short_error(exc)}

    return {
        "status": "ok",
        "hosts": hosts,
        "filesystems": filesystems,
    }

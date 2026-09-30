from __future__ import annotations

import argparse
import codecs
from datetime import datetime, timezone
import hashlib
import logging
import os
import platform
import socket
import time
from pathlib import Path
from typing import Any


logger = logging.getLogger("dba_os_collector")

PROC_ROOT = Path(os.getenv("OS_COLLECTOR_PROC_ROOT", "/proc"))
PSEUDO_FILESYSTEM_TYPES = {
    "autofs",
    "binfmt_misc",
    "bpf",
    "cgroup",
    "cgroup2",
    "configfs",
    "debugfs",
    "devpts",
    "devtmpfs",
    "efivarfs",
    "fusectl",
    "hugetlbfs",
    "mqueue",
    "nsfs",
    "proc",
    "pstore",
    "ramfs",
    "rpc_pipefs",
    "securityfs",
    "sysfs",
    "tmpfs",
    "overlay",
    "squashfs",
    "tracefs",
}


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return int(value)


def _float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return float(value)


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def _stable_host_id() -> str:
    configured = os.getenv("OS_COLLECTOR_HOST_ID")
    if configured and configured.strip():
        return configured.strip()

    seed = None
    for path in (Path("/etc/machine-id"), Path("/var/lib/dbus/machine-id")):
        seed = _read_text(path)
        if seed:
            break
    if not seed:
        seed = socket.getfqdn() or socket.gethostname()

    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]
    return f"linux-{digest}"


def _os_name() -> str:
    os_release = _read_text(Path("/etc/os-release"))
    if os_release:
        values: dict[str, str] = {}
        for line in os_release.splitlines():
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key] = value.strip().strip('"')
        if values.get("PRETTY_NAME"):
            return values["PRETTY_NAME"]
    return platform.platform()


def _read_cpu_times() -> dict[str, int]:
    stat_path = PROC_ROOT / "stat"
    first_line = stat_path.read_text(encoding="utf-8").splitlines()[0]
    parts = first_line.split()
    if not parts or parts[0] != "cpu":
        raise RuntimeError(f"Unexpected {stat_path} format")

    values = [int(value) for value in parts[1:]]
    names = [
        "user",
        "nice",
        "system",
        "idle",
        "iowait",
        "irq",
        "softirq",
        "steal",
        "guest",
        "guest_nice",
    ]
    return {name: values[index] if index < len(values) else 0 for index, name in enumerate(names)}


def _cpu_percent(prev: dict[str, int], current: dict[str, int]) -> dict[str, float]:
    deltas = {key: max(0, current.get(key, 0) - prev.get(key, 0)) for key in current}
    total = sum(deltas.values())
    if total <= 0:
        return {
            "cpu_user_percent": 0.0,
            "cpu_system_percent": 0.0,
            "cpu_idle_percent": 0.0,
            "cpu_iowait_percent": 0.0,
            "cpu_irq_percent": 0.0,
            "cpu_softirq_percent": 0.0,
            "cpu_steal_percent": 0.0,
        }

    def pct(value: int) -> float:
        return round(value / total * 100, 2)

    return {
        "cpu_user_percent": pct(deltas.get("user", 0) + deltas.get("nice", 0)),
        "cpu_system_percent": pct(deltas.get("system", 0)),
        "cpu_idle_percent": pct(deltas.get("idle", 0)),
        "cpu_iowait_percent": pct(deltas.get("iowait", 0)),
        "cpu_irq_percent": pct(deltas.get("irq", 0)),
        "cpu_softirq_percent": pct(deltas.get("softirq", 0)),
        "cpu_steal_percent": pct(deltas.get("steal", 0)),
    }


def _read_meminfo() -> dict[str, int]:
    values: dict[str, int] = {}
    for line in (PROC_ROOT / "meminfo").read_text(encoding="utf-8").splitlines():
        if ":" not in line:
            continue
        key, raw_value = line.split(":", 1)
        parts = raw_value.strip().split()
        if not parts:
            continue
        value = int(parts[0])
        if len(parts) > 1 and parts[1].lower() == "kb":
            value *= 1024
        values[key] = value
    return values


def _memory_metrics() -> dict[str, float | int | None]:
    meminfo = _read_meminfo()
    total = meminfo.get("MemTotal", 0)
    available = meminfo.get("MemAvailable", meminfo.get("MemFree", 0))
    swap_total = meminfo.get("SwapTotal", 0)
    swap_free = meminfo.get("SwapFree", 0)

    memory_used_percent = round((total - available) / total * 100, 2) if total else None
    swap_used_percent = (
        round((swap_total - swap_free) / swap_total * 100, 2) if swap_total else 0.0
    )

    return {
        "memory_total_bytes": total,
        "memory_available_bytes": available,
        "memory_used_percent": memory_used_percent,
        "swap_total_bytes": swap_total,
        "swap_free_bytes": swap_free,
        "swap_used_percent": swap_used_percent,
    }


def _process_count() -> int:
    return sum(1 for path in PROC_ROOT.iterdir() if path.name.isdigit())


def _decode_mount_field(value: str) -> str:
    return codecs.decode(value, "unicode_escape")


def _filesystem_samples(host_id: str, collected_at: datetime) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    seen_mounts: set[str] = set()
    mounts_path = PROC_ROOT / "mounts"

    for line in mounts_path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        device, mount_point, filesystem_type = (
            _decode_mount_field(parts[0]),
            _decode_mount_field(parts[1]),
            parts[2],
        )
        if filesystem_type in PSEUDO_FILESYSTEM_TYPES or mount_point in seen_mounts:
            continue
        seen_mounts.add(mount_point)

        try:
            stat = os.statvfs(mount_point)
        except OSError as exc:
            logger.debug("Skipping filesystem %s: %s", mount_point, exc)
            continue

        total = stat.f_frsize * stat.f_blocks
        if total <= 0:
            continue
        free = stat.f_frsize * stat.f_bfree
        available = stat.f_frsize * stat.f_bavail
        used = max(0, total - free)
        used_for_percent = max(0, total - available)
        used_percent = round(used_for_percent / total * 100, 2)

        samples.append(
            {
                "host_id": host_id,
                "collected_at": collected_at,
                "mount_point": mount_point,
                "device": device,
                "filesystem_type": filesystem_type,
                "total_bytes": total,
                "used_bytes": used,
                "free_bytes": free,
                "available_bytes": available,
                "used_percent": used_percent,
            }
        )

    return samples


def _host_record(host_id: str) -> dict[str, str | None]:
    return {
        "host_id": host_id,
        "hostname": socket.getfqdn() or socket.gethostname(),
        "os_name": _os_name(),
        "kernel_release": platform.release(),
        "postgres_data_directory": os.getenv("OS_COLLECTOR_POSTGRES_DATA_DIRECTORY")
        or os.getenv("PGDATA")
        or None,
    }


def _metric_sample(
    host_id: str, collected_at: datetime, previous_cpu: dict[str, int], current_cpu: dict[str, int]
) -> dict[str, Any]:
    load1, load5, load15 = os.getloadavg()
    sample: dict[str, Any] = {
        "host_id": host_id,
        "collected_at": collected_at,
        "load1": round(load1, 2),
        "load5": round(load5, 2),
        "load15": round(load15, 2),
        "process_count": _process_count(),
    }
    sample.update(_cpu_percent(previous_cpu, current_cpu))
    sample.update(_memory_metrics())
    return sample


def _connect() -> Any:
    try:
        import psycopg
    except ImportError as exc:  # pragma: no cover - exercised only on missing dependency.
        raise SystemExit(
            "Missing dependency: install psycopg or run inside the DBA Monitor agent "
            "environment that already includes psycopg."
        ) from exc

    dsn = os.getenv("OS_COLLECTOR_DSN")
    if dsn:
        return psycopg.connect(dsn)
    return psycopg.connect()


def _write_sample(
    host: dict[str, str | None],
    metric: dict[str, Any],
    filesystems: list[dict[str, Any]],
    retention_days: int,
) -> None:
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                insert into dba_monitor.host (
                    host_id, hostname, os_name, kernel_release, postgres_data_directory
                )
                values (
                    %(host_id)s, %(hostname)s, %(os_name)s, %(kernel_release)s,
                    %(postgres_data_directory)s
                )
                on conflict (host_id) do update set
                    hostname = excluded.hostname,
                    os_name = excluded.os_name,
                    kernel_release = excluded.kernel_release,
                    postgres_data_directory = excluded.postgres_data_directory,
                    last_seen_at = now()
                """,
                host,
            )
            cur.execute(
                """
                insert into dba_monitor.os_metric_sample (
                    host_id, collected_at, load1, load5, load15,
                    cpu_user_percent, cpu_system_percent, cpu_idle_percent,
                    cpu_iowait_percent, cpu_irq_percent, cpu_softirq_percent,
                    cpu_steal_percent, memory_total_bytes, memory_available_bytes,
                    memory_used_percent, swap_total_bytes, swap_free_bytes,
                    swap_used_percent, process_count
                )
                values (
                    %(host_id)s, %(collected_at)s, %(load1)s, %(load5)s, %(load15)s,
                    %(cpu_user_percent)s, %(cpu_system_percent)s, %(cpu_idle_percent)s,
                    %(cpu_iowait_percent)s, %(cpu_irq_percent)s, %(cpu_softirq_percent)s,
                    %(cpu_steal_percent)s, %(memory_total_bytes)s,
                    %(memory_available_bytes)s, %(memory_used_percent)s,
                    %(swap_total_bytes)s, %(swap_free_bytes)s,
                    %(swap_used_percent)s, %(process_count)s
                )
                on conflict (host_id, collected_at) do nothing
                """,
                metric,
            )
            cur.executemany(
                """
                insert into dba_monitor.os_filesystem_sample (
                    host_id, collected_at, mount_point, device, filesystem_type,
                    total_bytes, used_bytes, free_bytes, available_bytes, used_percent
                )
                values (
                    %(host_id)s, %(collected_at)s, %(mount_point)s, %(device)s,
                    %(filesystem_type)s, %(total_bytes)s, %(used_bytes)s,
                    %(free_bytes)s, %(available_bytes)s, %(used_percent)s
                )
                on conflict (host_id, collected_at, mount_point) do nothing
                """,
                filesystems,
            )
            if retention_days > 0:
                cur.execute(
                    """
                    delete from dba_monitor.os_filesystem_sample
                    where collected_at < now() - make_interval(days => %s)
                    """,
                    (retention_days,),
                )
                cur.execute(
                    """
                    delete from dba_monitor.os_metric_sample
                    where collected_at < now() - make_interval(days => %s)
                    """,
                    (retention_days,),
                )


def collect_once(
    host_id: str, previous_cpu: dict[str, int], sample_seconds: float, retention_days: int
) -> dict[str, Any]:
    time.sleep(sample_seconds)
    current_cpu = _read_cpu_times()
    collected_at = datetime.now(timezone.utc)
    host = _host_record(host_id)
    metric = _metric_sample(host_id, collected_at, previous_cpu, current_cpu)
    filesystems = _filesystem_samples(host_id, collected_at)
    _write_sample(host, metric, filesystems, retention_days)
    return {
        "current_cpu": current_cpu,
        "collected_at": collected_at.isoformat(),
        "filesystem_count": len(filesystems),
    }


def run_loop(args: argparse.Namespace) -> None:
    host_id = _stable_host_id()
    previous_cpu = _read_cpu_times()
    logger.info("Starting DBA OS collector for host_id=%s", host_id)

    while True:
        started_at = time.monotonic()
        try:
            result = collect_once(
                host_id=host_id,
                previous_cpu=previous_cpu,
                sample_seconds=args.cpu_sample_seconds,
                retention_days=args.retention_days,
            )
            previous_cpu = result["current_cpu"]
            logger.info(
                "Collected OS metrics at %s with %s filesystem samples",
                result["collected_at"],
                result["filesystem_count"],
            )
        except Exception as exc:
            logger.exception("OS metric collection failed: %s", exc)
            if args.once:
                raise SystemExit(1) from exc

        if args.once:
            return

        elapsed = time.monotonic() - started_at
        time.sleep(max(0.0, args.interval - elapsed))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DBA Monitor local Linux OS collector")
    parser.add_argument("--once", action="store_true", help="collect one sample and exit")
    parser.add_argument(
        "--interval",
        type=int,
        default=_int_env("OS_COLLECTOR_INTERVAL_SECONDS", 60),
        help="collection interval in seconds",
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=_int_env("OS_COLLECTOR_RETENTION_DAYS", 30),
        help="delete samples older than this many days; set 0 to disable",
    )
    parser.add_argument(
        "--cpu-sample-seconds",
        type=float,
        default=_float_env("OS_COLLECTOR_CPU_SAMPLE_SECONDS", 1.0),
        help="seconds between /proc/stat reads for the first CPU delta",
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("OS_COLLECTOR_LOG_LEVEL", "INFO"),
        help="Python logging level",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, str(args.log_level).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    run_loop(args)


if __name__ == "__main__":
    main()

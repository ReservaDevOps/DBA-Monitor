from dataclasses import dataclass
import os


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return int(value)


def _optional_int_env(name: str) -> int | None:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return None
    return int(value)


def _optional_float_env(name: str) -> float | None:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return None
    return float(value)


@dataclass(frozen=True)
class Settings:
    app_host: str = os.getenv("APP_HOST", "0.0.0.0")
    app_port: int = int(os.getenv("APP_PORT", "8080"))
    api_token: str = os.getenv("AGENT_API_TOKEN", "")
    require_api_token: bool = _bool_env("REQUIRE_API_TOKEN", True)
    data_dir: str = os.getenv("DATA_DIR", "/data")
    reports_dir: str = os.getenv("REPORTS_DIR", "/reports")
    report_name: str = os.getenv("REPORT_NAME", "client-a")
    status_interval_seconds: int = int(os.getenv("STATUS_INTERVAL_SECONDS", "300"))
    daily_report_hour: int = int(os.getenv("DAILY_REPORT_HOUR", "2"))
    daily_report_minute: int = int(os.getenv("DAILY_REPORT_MINUTE", "0"))
    run_status_on_startup: bool = _bool_env("RUN_STATUS_ON_STARTUP", True)
    statement_timeout_ms: int = int(os.getenv("STATEMENT_TIMEOUT_MS", "30000"))
    max_databases_per_report: int = _int_env("MAX_DATABASES_PER_REPORT", 0)
    evolution_enabled: bool = _bool_env("EVOLUTION_ENABLED", False)
    evolution_api_url: str = os.getenv(
        "EVOLUTION_API_URL", "http://dba-evolution-api:8080"
    )
    evolution_api_key: str = os.getenv("EVOLUTION_API_KEY", "")
    evolution_instance: str = os.getenv("EVOLUTION_INSTANCE", "")
    evolution_target_group_jid: str = os.getenv("EVOLUTION_TARGET_GROUP_JID", "")
    evolution_send_pdf: bool = _bool_env("EVOLUTION_SEND_PDF", True)
    evolution_timeout_seconds: int = _int_env("EVOLUTION_TIMEOUT_SECONDS", 20)
    status_warnings_enabled: bool = _bool_env("STATUS_WARNINGS_ENABLED", False)
    status_warning_cooldown_seconds: int = _int_env(
        "STATUS_WARNING_COOLDOWN_SECONDS", 3600
    )
    status_warning_max_connections: int | None = _optional_int_env(
        "STATUS_WARNING_MAX_CONNECTIONS"
    )
    status_warning_max_connections_percent: int | None = _optional_int_env(
        "STATUS_WARNING_MAX_CONNECTIONS_PERCENT"
    )
    status_warning_max_long_queries: int | None = _optional_int_env(
        "STATUS_WARNING_MAX_LONG_QUERIES"
    )
    status_warning_max_waiting_locks: int | None = _optional_int_env(
        "STATUS_WARNING_MAX_WAITING_LOCKS"
    )
    status_warning_max_database_size_gb: int | None = _optional_int_env(
        "STATUS_WARNING_MAX_DATABASE_SIZE_GB"
    )
    os_metrics_enabled: bool = _bool_env("OS_METRICS_ENABLED", False)
    os_warning_max_filesystem_used_percent: float | None = _optional_float_env(
        "OS_WARNING_MAX_FILESYSTEM_USED_PERCENT"
    )
    os_warning_max_memory_used_percent: float | None = _optional_float_env(
        "OS_WARNING_MAX_MEMORY_USED_PERCENT"
    )
    os_warning_max_iowait_percent: float | None = _optional_float_env(
        "OS_WARNING_MAX_IOWAIT_PERCENT"
    )
    os_warning_max_collector_lag_seconds: float | None = _optional_float_env(
        "OS_WARNING_MAX_COLLECTOR_LAG_SECONDS"
    )


settings = Settings()

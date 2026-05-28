from dataclasses import dataclass
import os


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_host: str = os.getenv("APP_HOST", "0.0.0.0")
    app_port: int = int(os.getenv("APP_PORT", "8080"))
    data_dir: str = os.getenv("DATA_DIR", "/data")
    reports_dir: str = os.getenv("REPORTS_DIR", "/reports")
    report_name: str = os.getenv("REPORT_NAME", "client-a")
    status_interval_seconds: int = int(os.getenv("STATUS_INTERVAL_SECONDS", "300"))
    daily_report_hour: int = int(os.getenv("DAILY_REPORT_HOUR", "2"))
    daily_report_minute: int = int(os.getenv("DAILY_REPORT_MINUTE", "0"))
    run_status_on_startup: bool = _bool_env("RUN_STATUS_ON_STARTUP", True)
    statement_timeout_ms: int = int(os.getenv("STATEMENT_TIMEOUT_MS", "30000"))


settings = Settings()


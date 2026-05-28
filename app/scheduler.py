from apscheduler.schedulers.background import BackgroundScheduler

from app.collectors.status import collect_status
from app.reports.daily import generate_daily_report
from app.settings import settings
from app.storage.filesystem import save_status


scheduler = BackgroundScheduler(timezone="America/Sao_Paulo")


def collect_and_store_status() -> dict:
    snapshot = collect_status()
    save_status(snapshot)
    return snapshot


def start_scheduler() -> None:
    if scheduler.running:
        return

    scheduler.add_job(
        collect_and_store_status,
        "interval",
        seconds=settings.status_interval_seconds,
        id="status-collector",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        generate_daily_report,
        "cron",
        hour=settings.daily_report_hour,
        minute=settings.daily_report_minute,
        id="daily-report",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()

    if settings.run_status_on_startup:
        scheduler.add_job(
            collect_and_store_status,
            id="startup-status-collector",
            replace_existing=True,
            max_instances=1,
        )


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)


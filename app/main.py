from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
import uvicorn

from app.scheduler import collect_and_store_status, start_scheduler, stop_scheduler
from app.reports.daily import generate_daily_report
from app.settings import settings
from app.storage.filesystem import list_reports, load_latest_status


@asynccontextmanager
async def lifespan(_: FastAPI):
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()


app = FastAPI(title="DBA Monitor Agent", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/status")
def status() -> dict:
    latest = load_latest_status()
    if latest is None:
        latest = collect_and_store_status()
    return latest


@app.get("/metrics/latest")
def latest_metrics() -> dict:
    latest = load_latest_status()
    if latest is None:
        raise HTTPException(status_code=404, detail="No status snapshot collected yet")
    return latest


@app.get("/reports")
def reports() -> list[dict[str, str]]:
    return list_reports()


@app.post("/reports/run-now")
def run_report_now() -> dict:
    report = generate_daily_report()
    return {
        "report_name": report["report_name"],
        "collected_at": report["collected_at"],
        "summary": report["summary"],
        "csv_files": report["csv_files"],
        "html": report["html"],
        "pdf": report["pdf"],
        "output_dir": report["output_dir"],
    }


@app.get("/reports/{report_name}/{date_key}/html")
def report_html(report_name: str, date_key: str) -> FileResponse:
    path = Path(settings.reports_dir) / report_name / date_key / "summary.html"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Report HTML not found")
    return FileResponse(path, media_type="text/html")


@app.get("/reports/{report_name}/{date_key}/pdf")
def report_pdf(report_name: str, date_key: str) -> FileResponse:
    path = Path(settings.reports_dir) / report_name / date_key / "summary.pdf"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Report PDF not found")
    return FileResponse(path, media_type="application/pdf", filename=path.name)


if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.app_host, port=settings.app_port)

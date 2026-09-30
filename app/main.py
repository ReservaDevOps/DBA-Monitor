from contextlib import asynccontextmanager
import secrets

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
import uvicorn

from app.scheduler import collect_and_store_status, start_scheduler, stop_scheduler
from app.reports.daily import ReportAlreadyRunning, generate_daily_report
from app.settings import settings
from app.storage.filesystem import list_reports, load_latest_status, safe_report_file


@asynccontextmanager
async def lifespan(_: FastAPI):
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()


app = FastAPI(title="DBA Monitor Agent", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def require_api_token(request: Request, call_next):
    if settings.require_api_token and request.url.path != "/health":
        if not settings.api_token:
            return JSONResponse(
                status_code=503,
                content={"detail": "AGENT_API_TOKEN is required but not configured"},
            )
        token = request.headers.get("x-api-token", "")
        if not secrets.compare_digest(token, settings.api_token):
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API token"},
            )
    return await call_next(request)


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
    try:
        report = generate_daily_report()
    except ReportAlreadyRunning as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
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
    try:
        path = safe_report_file(report_name, date_key, "summary.html")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not path.exists():
        raise HTTPException(status_code=404, detail="Report HTML not found")
    return FileResponse(path, media_type="text/html")


@app.get("/reports/{report_name}/{date_key}/pdf")
def report_pdf(report_name: str, date_key: str) -> FileResponse:
    try:
        path = safe_report_file(report_name, date_key, "summary.pdf")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not path.exists():
        raise HTTPException(status_code=404, detail="Report PDF not found")
    return FileResponse(path, media_type="application/pdf", filename=path.name)


if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.app_host, port=settings.app_port)

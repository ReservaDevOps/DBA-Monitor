from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any

from app.settings import settings


SAFE_PATH_COMPONENT = re.compile(r"^[A-Za-z0-9_.-]+$")
REPORT_DATE_COMPONENT = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_report_component(value: str, field_name: str) -> str:
    if value in {".", ".."} or not SAFE_PATH_COMPONENT.fullmatch(value):
        raise ValueError(f"Invalid {field_name}")
    return value


def validate_report_date(value: str) -> str:
    if not REPORT_DATE_COMPONENT.fullmatch(value):
        raise ValueError("Invalid date_key")
    return value


def safe_report_file(report_name: str, date_key: str, filename: str) -> Path:
    report_name = validate_report_component(report_name, "report_name")
    date_key = validate_report_date(date_key)
    base = Path(settings.reports_dir).resolve()
    path = (base / report_name / date_key / filename).resolve()
    if base != path and base not in path.parents:
        raise ValueError("Report path escaped reports directory")
    return path


def ensure_dirs() -> None:
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.reports_dir).mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")


def append_jsonl(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(payload, sort_keys=True, default=str) + "\n")


def save_status(snapshot: dict) -> None:
    ensure_dirs()
    data_dir = Path(settings.data_dir)
    write_json(data_dir / "status" / "latest.json", snapshot)
    append_jsonl(data_dir / "status" / f"{datetime.now():%Y-%m-%d}.jsonl", snapshot)


def load_status_warning_state() -> dict:
    path = Path(settings.data_dir) / "status" / "warning-state.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def save_status_warning_state(state: dict) -> None:
    ensure_dirs()
    write_json(Path(settings.data_dir) / "status" / "warning-state.json", state)


def load_latest_status() -> dict | None:
    path = Path(settings.data_dir) / "status" / "latest.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def report_root(report_name: str, date_key: str) -> Path:
    report_name = validate_report_component(report_name, "report_name")
    date_key = validate_report_date(date_key)
    return Path(settings.reports_dir) / report_name / date_key


def list_reports() -> list[dict[str, str]]:
    root = Path(settings.reports_dir)
    if not root.exists():
        return []

    reports: list[dict[str, str]] = []
    for report_dir in sorted(root.glob("*/*"), reverse=True):
        if not report_dir.is_dir():
            continue
        html = report_dir / "summary.html"
        pdf = report_dir / "summary.pdf"
        reports.append(
            {
                "report_name": report_dir.parent.name,
                "date": report_dir.name,
                "html_url": f"/reports/{report_dir.parent.name}/{report_dir.name}/html",
                "pdf_url": f"/reports/{report_dir.parent.name}/{report_dir.name}/pdf",
                "html": str(html) if html.exists() else "",
                "pdf": str(pdf) if pdf.exists() else "",
                "path": str(report_dir),
            }
        )
    return reports

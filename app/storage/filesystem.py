from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any

from app.settings import settings


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


def load_latest_status() -> dict | None:
    path = Path(settings.data_dir) / "status" / "latest.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())


def report_root(report_name: str, date_key: str) -> Path:
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
                "html": str(html) if html.exists() else "",
                "pdf": str(pdf) if pdf.exists() else "",
                "path": str(report_dir),
            }
        )
    return reports


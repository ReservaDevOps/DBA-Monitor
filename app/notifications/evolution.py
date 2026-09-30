from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from app.settings import settings


logger = logging.getLogger(__name__)


def _evolution_path(action: str) -> str:
    base_url = settings.evolution_api_url.rstrip("/")
    instance = quote(settings.evolution_instance, safe="")
    return f"{base_url}/message/{action}/{instance}"


def _post_json(action: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    request = Request(
        _evolution_path(action),
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "apikey": settings.evolution_api_key,
        },
        method="POST",
    )
    with urlopen(request, timeout=settings.evolution_timeout_seconds) as response:
        body = response.read()
    if not body:
        return None
    return json.loads(body.decode("utf-8"))


def _report_message(report: dict[str, Any]) -> str:
    summary = report.get("summary", {})
    lines = [
        f"Relatorio diario DBA - {report.get('report_name', '')}",
        f"Coletado em: {report.get('collected_at', '')}",
        "",
        f"Banco: {summary.get('database', '')}",
        f"Servidor: {summary.get('server', '')}",
        f"Conexoes totais: {summary.get('total_connections', 0)}",
        f"Consultas longas: {summary.get('long_queries', 0)}",
        f"Locks em espera: {summary.get('waiting_locks', 0)}",
        f"Bancos analisados: {summary.get('scanned_databases', 0)}",
        f"Bancos com falha: {summary.get('failed_databases', 0)}",
        f"Maior banco: {summary.get('largest_database', '')} ({summary.get('largest_database_size', '')})",
    ]
    if settings.evolution_send_pdf and report.get("pdf"):
        lines.append("")
        lines.append("PDF do relatorio em anexo.")
    return "\n".join(lines)


def _send_pdf(report: dict[str, Any]) -> None:
    pdf_path = Path(report["pdf"])
    if not pdf_path.exists():
        logger.warning("Evolution PDF notification skipped: %s does not exist", pdf_path)
        return

    encoded = base64.b64encode(pdf_path.read_bytes()).decode("ascii")
    _post_json(
        "sendMedia",
        {
            "number": settings.evolution_target_group_jid,
            "mediatype": "document",
            "mimetype": "application/pdf",
            "fileName": pdf_path.name,
            "caption": f"Relatorio diario DBA - {report.get('report_name', '')}",
            "media": encoded,
        },
    )


def _has_evolution_settings() -> bool:
    if not settings.evolution_enabled:
        return False

    missing = [
        name
        for name, value in {
            "EVOLUTION_API_URL": settings.evolution_api_url,
            "EVOLUTION_API_KEY": settings.evolution_api_key,
            "EVOLUTION_INSTANCE": settings.evolution_instance,
            "EVOLUTION_TARGET_GROUP_JID": settings.evolution_target_group_jid,
        }.items()
        if not value
    ]
    if missing:
        logger.warning(
            "Evolution notification skipped: missing settings %s", ", ".join(missing)
        )
        return False

    return True


def send_text_notification(text: str) -> bool:
    if not _has_evolution_settings():
        return False

    _post_json(
        "sendText",
        {
            "number": settings.evolution_target_group_jid,
            "text": text,
        },
    )
    return True


def notify_daily_report(report: dict[str, Any]) -> None:
    if not _has_evolution_settings():
        return

    try:
        send_text_notification(_report_message(report))
        if settings.evolution_send_pdf and report.get("pdf"):
            _send_pdf(report)
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        logger.exception("Evolution notification failed: %s", exc)

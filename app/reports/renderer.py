from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates"

DATASET_LABELS = {
    "instance": "Instância",
    "database_sizes": "Tamanho dos Bancos",
    "table_sizes": "Maiores Tabelas",
    "connections": "Conexões",
    "long_queries": "Consultas em Execução há Mais de 5 Minutos",
    "locks": "Locks",
    "vacuum_health": "Saúde de Vacuum e Analyze",
    "pg_stat_statements_status": "Status do pg_stat_statements",
    "top_sql_by_total_time": "Top SQLs por Tempo Total",
    "top_sql_by_mean_time": "Top SQLs por Tempo Médio",
    "top_sql_by_io": "Top SQLs por I/O",
}

COLUMN_LABELS = {
    "application_name": "Aplicação",
    "available": "Disponível",
    "bytes": "Bytes",
    "calls": "Chamadas",
    "client_addr": "Cliente",
    "collected_at": "Coletado em",
    "database": "Banco",
    "database_name": "Banco",
    "database_user": "Usuário do Banco",
    "datname": "Banco",
    "dead_tuple_percent": "% Tuplas Mortas",
    "duration": "Duração",
    "granted": "Concedido",
    "largest_database": "Maior Banco",
    "largest_database_size": "Tamanho do Maior Banco",
    "last_analyze": "Último Analyze",
    "last_autoanalyze": "Último Autoanalyze",
    "last_autovacuum": "Último Autovacuum",
    "last_vacuum": "Último Vacuum",
    "locktype": "Tipo de Lock",
    "long_queries": "Consultas Longas",
    "locks": "Locks",
    "max_exec_time_ms": "Tempo Máx. (ms)",
    "mean_exec_time_ms": "Tempo Médio (ms)",
    "mode": "Modo",
    "n_dead_tup": "Tuplas Mortas",
    "n_live_tup": "Tuplas Vivas",
    "pg_stat_statements": "pg_stat_statements",
    "pid": "PID",
    "postmaster_start_time": "Início do PostgreSQL",
    "postgres_version": "Versão PostgreSQL",
    "pretty_size": "Tamanho",
    "query": "Trecho do SQL",
    "queryid": "ID da Consulta",
    "read_blocks": "Blocos Lidos",
    "reason": "Motivo",
    "relname": "Tabela",
    "rows": "Linhas",
    "rows_per_call": "Linhas/Chamada",
    "schemaname": "Schema",
    "server": "Servidor",
    "server_addr": "Endereço",
    "server_port": "Porta",
    "sessions": "Sessões",
    "shared_blks_dirtied": "Blocos Sujos",
    "shared_blks_hit": "Blocos em Cache",
    "shared_blks_read": "Blocos Lidos",
    "shared_blks_written": "Blocos Escritos",
    "state": "Estado",
    "table_name": "Tabela",
    "temp_blks_read": "Blocos Temp. Lidos",
    "temp_blks_written": "Blocos Temp. Escritos",
    "top_sql_by_io": "Top SQLs por I/O",
    "top_sql_by_mean_time": "Top SQLs por Tempo Médio",
    "top_sql_by_total_time": "Top SQLs por Tempo Total",
    "total_bytes": "Bytes Totais",
    "total_connections": "Conexões Totais",
    "total_exec_time_ms": "Tempo Total (ms)",
    "total_locks": "Locks Totais",
    "total_size": "Tamanho Total",
    "usename": "Usuário",
    "waiting_locks": "Locks em Espera",
}


def dataset_label(name: str) -> str:
    return DATASET_LABELS.get(name, name.replace("_", " ").title())


def column_label(name: str) -> str:
    return COLUMN_LABELS.get(name, name.replace("_", " ").title())


def _display_columns(dataset_name: str, rows: list[dict]) -> list[str]:
    if not rows:
        return []

    available = list(rows[0].keys())
    if dataset_name.startswith("top_sql_by_"):
        preferred = [
            "calls",
            "total_exec_time_ms",
            "mean_exec_time_ms",
            "max_exec_time_ms",
            "rows",
            "read_blocks",
            "query",
        ]
        return [column for column in preferred if column in available]

    return available[:6]


def _column_widths(columns: list[str], available_width: float) -> list[float] | None:
    if "query" not in columns:
        return None

    fixed = {
        "calls": 46,
        "total_exec_time_ms": 70,
        "mean_exec_time_ms": 70,
        "max_exec_time_ms": 70,
        "rows": 48,
        "read_blocks": 58,
    }
    widths = [fixed.get(column, 0) for column in columns]
    remaining = available_width - sum(widths)
    return [remaining if column == "query" else width for column, width in zip(columns, widths)]


def _cell_value(value: object, max_length: int = 180) -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.split())
    if len(text) > max_length:
        return f"{text[: max_length - 1]}..."
    return text


def render_html(report: dict, output_path: Path) -> None:
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html", "xml"]),
    )
    env.filters["column_label"] = column_label
    env.filters["dataset_label"] = dataset_label
    template = env.get_template("daily.html.j2")
    output_path.write_text(template.render(report=report), encoding="utf-8")


def render_pdf(report: dict, output_path: Path) -> None:
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=landscape(A4),
        leftMargin=24,
        rightMargin=24,
        topMargin=24,
        bottomMargin=24,
    )
    styles = getSampleStyleSheet()
    story = [
        Paragraph("Relatório Diário PostgreSQL", styles["Title"]),
        Paragraph(f"Relatório: {report['report_name']}", styles["Normal"]),
        Paragraph(f"Coletado em: {report['collected_at']}", styles["Normal"]),
        Spacer(1, 12),
    ]

    summary_rows = [["Métrica", "Valor"]]
    for key, value in report["summary"].items():
        summary_rows.append([column_label(key), str(value)])

    summary_table = Table(summary_rows, hAlign="LEFT")
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#efefef")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("PADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(summary_table)
    story.append(Spacer(1, 14))

    for dataset_name, rows in report["datasets"].items():
        story.append(Paragraph(dataset_label(dataset_name), styles["Heading2"]))
        if not rows:
            story.append(Paragraph("Nenhuma linha retornada.", styles["Normal"]))
            story.append(Spacer(1, 8))
            continue

        columns = _display_columns(dataset_name, rows)
        table_rows = [[column_label(column) for column in columns]]
        for row in rows[:20]:
            table_rows.append(
                [
                    Paragraph(_cell_value(row.get(column)), styles["BodyText"])
                    for column in columns
                ]
            )

        table = Table(
            table_rows,
            repeatRows=1,
            hAlign="LEFT",
            colWidths=_column_widths(columns, doc.width),
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#efefef")),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("PADDING", (0, 0), (-1, -1), 4),
                    ("FONTSIZE", (0, 0), (-1, -1), 7),
                ]
            )
        )
        story.append(table)
        story.append(Spacer(1, 12))

    doc.build(story)

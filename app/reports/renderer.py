from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup
from reportlab.graphics.shapes import Drawing, Line, PolyLine, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates"

DATASET_LABELS = {
    "instance": "Instância",
    "database_sizes": "Tamanho dos Bancos",
    "table_sizes": "Maiores Tabelas em Todos os Bancos",
    "connections": "Conexões",
    "long_queries": "Consultas em Execução há Mais de 5 Minutos",
    "locks": "Locks",
    "vacuum_health": "Saúde de Vacuum e Analyze em Todos os Bancos",
    "database_scan_status": "Status da Varredura de Bancos",
    "database_scan_errors": "Erros da Varredura de Bancos",
    "pg_stat_statements_status": "Status do pg_stat_statements",
    "pg_stat_statements_scan_errors": "Erros da Varredura do pg_stat_statements",
    "top_sql_by_total_time": "Top SQLs por Tempo Total",
    "top_sql_by_mean_time": "Top SQLs por Tempo Médio",
    "top_sql_by_io": "Top SQLs por I/O",
    "os_metrics_history": "Histórico de Métricas de SO",
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
    "discovered_databases": "Bancos Descobertos",
    "duration": "Duração",
    "error": "Erro",
    "error_type": "Tipo de Erro",
    "failed_databases": "Bancos com Falha",
    "granted": "Concedido",
    "largest_database": "Maior Banco",
    "largest_database_size": "Tamanho do Maior Banco",
    "last_analyze": "Último Analyze",
    "last_autoanalyze": "Último Autoanalyze",
    "last_autovacuum": "Último Autovacuum",
    "last_vacuum": "Último Vacuum",
    "limited": "Limitado",
    "locktype": "Tipo de Lock",
    "long_queries": "Consultas Longas",
    "locks": "Locks",
    "max_exec_time_ms": "Tempo Máx. (ms)",
    "max_databases_per_report": "Limite de Bancos por Relatório",
    "mean_exec_time_ms": "Tempo Médio (ms)",
    "mode": "Modo",
    "n_dead_tup": "Tuplas Mortas",
    "n_live_tup": "Tuplas Vivas",
    "pg_stat_statements": "pg_stat_statements",
    "pg_stat_statements_enabled_databases": "Bancos com pg_stat_statements",
    "pg_stat_statements_failed_databases": "Falhas no pg_stat_statements",
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
    "scanned_databases": "Bancos Analisados",
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
    "collector_lag_seconds": "Lag do Coletor (s)",
    "cpu_iowait_percent": "CPU iowait (%)",
    "cpu_used_percent": "CPU Usada (%)",
    "hostname": "Host",
    "max_filesystem_mount_point": "Filesystem Mais Cheio",
    "max_filesystem_used_percent": "Filesystem Mais Cheio (%)",
    "memory_used_percent": "Memória Usada (%)",
}

CHART_LINE_COLOR = "#2563eb"
CHART_THRESHOLD_COLOR = "#dc2626"
CHART_GRID_COLOR = "#d9e2ec"
CHART_TEXT_COLOR = "#334e68"


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
            "database_name",
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


def _chart_bounds(chart: dict) -> tuple[float, float]:
    values = [float(point["value"]) for point in chart.get("points", [])]
    threshold = chart.get("threshold")
    if threshold is not None:
        values.append(float(threshold))

    lower = 0.0
    configured_max = chart.get("max")
    if configured_max is not None:
        upper = float(configured_max)
    else:
        upper = max(values or [1.0])
        upper = max(1.0, upper * 1.2)
    if upper <= lower:
        upper = lower + 1.0
    return lower, upper


def _point_xy(
    index: int,
    value: float,
    count: int,
    lower: float,
    upper: float,
    left: float,
    top: float,
    plot_width: float,
    plot_height: float,
) -> tuple[float, float]:
    x = left + (plot_width * index / max(count - 1, 1))
    y = top + plot_height - ((value - lower) / (upper - lower) * plot_height)
    return x, y


def chart_svg(chart: dict) -> Markup:
    points = chart.get("points", [])
    if not points:
        return Markup("<p>Nenhum histórico disponível.</p>")

    width = 760
    height = 220
    left = 54
    right = 18
    top = 18
    bottom = 38
    plot_width = width - left - right
    plot_height = height - top - bottom
    lower, upper = _chart_bounds(chart)

    polyline_points = []
    for index, point in enumerate(points):
        x, y = _point_xy(
            index,
            float(point["value"]),
            len(points),
            lower,
            upper,
            left,
            top,
            plot_width,
            plot_height,
        )
        polyline_points.append(f"{x:.1f},{y:.1f}")

    grid_lines = []
    for step in range(5):
        value = lower + ((upper - lower) * step / 4)
        y = top + plot_height - ((value - lower) / (upper - lower) * plot_height)
        grid_lines.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}" '
            f'stroke="{CHART_GRID_COLOR}" stroke-width="1" />'
            f'<text x="8" y="{y + 4:.1f}" font-size="11" fill="{CHART_TEXT_COLOR}">'
            f'{value:.0f}{chart.get("unit", "")}</text>'
        )

    threshold_line = ""
    threshold = chart.get("threshold")
    if threshold is not None and lower <= float(threshold) <= upper:
        y = top + plot_height - ((float(threshold) - lower) / (upper - lower) * plot_height)
        threshold_line = (
            f'<line x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}" '
            f'stroke="{CHART_THRESHOLD_COLOR}" stroke-width="1.5" stroke-dasharray="5 4" />'
        )

    labels = ""
    if len(points) >= 2:
        labels = (
            f'<text x="{left}" y="{height - 12}" font-size="11" fill="{CHART_TEXT_COLOR}">'
            f'{points[0].get("label", "")}</text>'
            f'<text x="{width - right}" y="{height - 12}" font-size="11" fill="{CHART_TEXT_COLOR}" '
            f'text-anchor="end">{points[-1].get("label", "")}</text>'
        )

    return Markup(
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{chart.get("title", "grafico")}">'
        f'{"".join(grid_lines)}'
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}" '
        f'stroke="{CHART_TEXT_COLOR}" stroke-width="1" />'
        f'<line x1="{left}" y1="{top + plot_height}" x2="{width - right}" '
        f'y2="{top + plot_height}" stroke="{CHART_TEXT_COLOR}" stroke-width="1" />'
        f'{threshold_line}'
        f'<polyline points="{" ".join(polyline_points)}" fill="none" '
        f'stroke="{CHART_LINE_COLOR}" stroke-width="2.5" stroke-linejoin="round" '
        f'stroke-linecap="round" />'
        f'{labels}'
        f'</svg>'
    )


def _pdf_chart(chart: dict, width: float, height: float = 160) -> Drawing:
    drawing = Drawing(width, height)
    points = chart.get("points", [])
    if not points:
        drawing.add(String(0, height / 2, "Nenhum histórico disponível.", fontSize=9))
        return drawing

    left = 42
    right = 12
    top = 10
    bottom = 26
    plot_width = width - left - right
    plot_height = height - top - bottom
    lower, upper = _chart_bounds(chart)

    for step in range(5):
        value = lower + ((upper - lower) * step / 4)
        y = bottom + ((value - lower) / (upper - lower) * plot_height)
        drawing.add(
            Line(
                left,
                y,
                width - right,
                y,
                strokeColor=colors.HexColor(CHART_GRID_COLOR),
                strokeWidth=0.5,
            )
        )
        drawing.add(
            String(
                2,
                y - 3,
                f"{value:.0f}{chart.get('unit', '')}",
                fontSize=7,
                fillColor=colors.HexColor(CHART_TEXT_COLOR),
            )
        )

    drawing.add(Line(left, bottom, left, bottom + plot_height, strokeWidth=0.7))
    drawing.add(Line(left, bottom, width - right, bottom, strokeWidth=0.7))

    threshold = chart.get("threshold")
    if threshold is not None and lower <= float(threshold) <= upper:
        y = bottom + ((float(threshold) - lower) / (upper - lower) * plot_height)
        drawing.add(
            Line(
                left,
                y,
                width - right,
                y,
                strokeColor=colors.HexColor(CHART_THRESHOLD_COLOR),
                strokeWidth=0.8,
                strokeDashArray=[4, 3],
            )
        )

    pdf_points = []
    for index, point in enumerate(points):
        x = left + (plot_width * index / max(len(points) - 1, 1))
        y = bottom + ((float(point["value"]) - lower) / (upper - lower) * plot_height)
        pdf_points.extend([x, y])
    drawing.add(
        PolyLine(
            pdf_points,
            strokeColor=colors.HexColor(CHART_LINE_COLOR),
            strokeWidth=1.5,
        )
    )

    if len(points) >= 2:
        drawing.add(
            String(
                left,
                8,
                str(points[0].get("label", "")),
                fontSize=7,
                fillColor=colors.HexColor(CHART_TEXT_COLOR),
            )
        )
        drawing.add(
            String(
                width - right - 70,
                8,
                str(points[-1].get("label", "")),
                fontSize=7,
                fillColor=colors.HexColor(CHART_TEXT_COLOR),
            )
        )

    return drawing


def render_html(report: dict, output_path: Path) -> None:
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html", "xml"]),
    )
    env.filters["column_label"] = column_label
    env.filters["dataset_label"] = dataset_label
    env.filters["chart_svg"] = chart_svg
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

    charts = report.get("charts", [])
    if charts:
        story.append(Paragraph("Histórico de Métricas de SO", styles["Heading2"]))
        for chart in charts:
            story.append(Paragraph(str(chart.get("title", "")), styles["Heading3"]))
            story.append(_pdf_chart(chart, doc.width))
            story.append(Spacer(1, 8))
        story.append(Spacer(1, 8))

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

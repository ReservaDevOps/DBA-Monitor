from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates"


def render_html(report: dict, output_path: Path) -> None:
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template("daily.html.j2")
    output_path.write_text(template.render(report=report), encoding="utf-8")


def render_pdf(report: dict, output_path: Path) -> None:
    doc = SimpleDocTemplate(str(output_path), pagesize=A4)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("Daily PostgreSQL Report", styles["Title"]),
        Paragraph(f"Report: {report['report_name']}", styles["Normal"]),
        Paragraph(f"Collected at: {report['collected_at']}", styles["Normal"]),
        Spacer(1, 12),
    ]

    summary_rows = [["Metric", "Value"]]
    for key, value in report["summary"].items():
        summary_rows.append([key.replace("_", " ").title(), str(value)])

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
        story.append(Paragraph(dataset_name.replace("_", " ").title(), styles["Heading2"]))
        if not rows:
            story.append(Paragraph("No rows returned.", styles["Normal"]))
            story.append(Spacer(1, 8))
            continue

        columns = list(rows[0].keys())[:6]
        table_rows = [columns]
        for row in rows[:20]:
            table_rows.append([str(row.get(column, ""))[:80] for column in columns])

        table = Table(table_rows, repeatRows=1, hAlign="LEFT")
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


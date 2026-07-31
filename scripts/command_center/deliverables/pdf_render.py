"""Professional PDF generation (reportlab) with provenance and limitations."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

NAVY = colors.HexColor("#0B1F33")
LIME = colors.HexColor("#C5D93D")
GREEN = colors.HexColor("#2E7D32")
LIGHT = colors.HexColor("#F4F6F8")
MUTED = colors.HexColor("#5C6B7A")


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "cover_title": ParagraphStyle(
            "cover_title",
            parent=base["Title"],
            fontSize=22,
            textColor=NAVY,
            spaceAfter=12,
            alignment=TA_CENTER,
            leading=26,
        ),
        "cover_sub": ParagraphStyle(
            "cover_sub",
            parent=base["Normal"],
            fontSize=12,
            textColor=MUTED,
            alignment=TA_CENTER,
            spaceAfter=6,
        ),
        "h1": ParagraphStyle(
            "h1",
            parent=base["Heading1"],
            fontSize=14,
            textColor=NAVY,
            spaceBefore=14,
            spaceAfter=8,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base["Heading2"],
            fontSize=12,
            textColor=NAVY,
            spaceBefore=10,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "body",
            parent=base["Normal"],
            fontSize=10,
            leading=14,
            alignment=TA_JUSTIFY,
            textColor=colors.HexColor("#1A1A1A"),
        ),
        "bullet": ParagraphStyle(
            "bullet",
            parent=base["Normal"],
            fontSize=10,
            leading=13,
            leftIndent=12,
            spaceAfter=3,
        ),
        "footer": ParagraphStyle(
            "footer",
            parent=base["Normal"],
            fontSize=8,
            textColor=MUTED,
            alignment=TA_CENTER,
        ),
        "warn": ParagraphStyle(
            "warn",
            parent=base["Normal"],
            fontSize=9,
            textColor=colors.HexColor("#8A4B08"),
            leading=12,
            spaceAfter=4,
        ),
        "small": ParagraphStyle(
            "small",
            parent=base["Normal"],
            fontSize=8,
            textColor=MUTED,
            alignment=TA_LEFT,
        ),
    }


def write_executive_pdf(
    path: Path,
    *,
    title: str,
    client_label: str,
    generated_at: str | None = None,
    data_as_of: str | None = None,
    executive_summary: str,
    conclusions: list[str],
    indicators: list[tuple[str, str]],
    table_headers: list[str] | None = None,
    table_rows: list[list[Any]] | None = None,
    methodology: list[str],
    sources: list[str],
    limitations: list[str],
    legal_disclaimers: list[str] | None = None,
    version_id: str | None = None,
    provenance: dict[str, Any] | None = None,
    brand: str = "CONFENGE",
) -> Path:
    """Write a multi-section professional PDF. Never dumps raw JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    generated_at = generated_at or datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    styles = _styles()
    provenance = provenance or {}
    version_id = version_id or provenance.get("run_id") or "local"

    def _footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setStrokeColor(NAVY)
        canvas.setLineWidth(0.6)
        canvas.line(18 * mm, 14 * mm, A4[0] - 18 * mm, 14 * mm)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(MUTED)
        footer = f"{brand} · {client_label} · {title[:40]} · v={version_id} · p. {doc.page}"
        canvas.drawCentredString(A4[0] / 2, 8 * mm, footer)
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=18 * mm,
        title=title,
        author="EXTRA Command Center",
    )
    story: list[Any] = []

    # Cover
    story.append(Spacer(1, 28 * mm))
    story.append(Paragraph(brand, styles["cover_sub"]))
    story.append(Paragraph(title, styles["cover_title"]))
    story.append(Paragraph(client_label, styles["cover_sub"]))
    story.append(Paragraph(f"Gerado em: {generated_at}", styles["cover_sub"]))
    if data_as_of:
        story.append(Paragraph(f"Data de corte dos dados: {data_as_of}", styles["cover_sub"]))
    story.append(Paragraph(f"Versão / run: {version_id}", styles["cover_sub"]))
    story.append(Spacer(1, 10 * mm))
    story.append(
        Paragraph(
            "Documento de apoio à decisão. Conclusões jurídicas ou comerciais são preliminares "
            "e exigem revisão humana. Não há envio automático de mensagens.",
            styles["warn"],
        )
    )
    story.append(PageBreak())

    # Sumário executivo
    story.append(Paragraph("1. Sumário executivo", styles["h1"]))
    story.append(Paragraph(executive_summary.replace("\n", "<br/>"), styles["body"]))
    story.append(Paragraph("Principais conclusões", styles["h2"]))
    for c in conclusions:
        story.append(Paragraph(f"• {_esc(c)}", styles["bullet"]))

    # Indicadores
    if indicators:
        story.append(Paragraph("2. Indicadores", styles["h1"]))
        data = [["Indicador", "Valor"]] + [[_esc(a), _esc(b)] for a, b in indicators]
        t = Table(data, colWidths=[80 * mm, 80 * mm])
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("BACKGROUND", (0, 1), (-1, -1), LIGHT),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D0D7DE")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(t)

    # Table
    if table_headers and table_rows is not None:
        story.append(Paragraph("3. Detalhamento", styles["h1"]))
        # limit columns for page fit
        headers = [str(h) for h in table_headers[:6]]
        body_rows = []
        for row in table_rows[:40]:
            body_rows.append([_esc(x) for x in list(row)[:6]])
        data = [headers] + body_rows
        col_w = (160 * mm) / max(1, len(headers))
        t = Table(data, colWidths=[col_w] * len(headers), repeatRows=1)
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D0D7DE")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
                ]
            )
        )
        story.append(t)
        if len(table_rows) > 40:
            story.append(
                Paragraph(
                    f"Tabela truncada na impressão PDF: exibindo 40 de {len(table_rows)} linhas. "
                    "Use o workbook XLSX para o conjunto completo.",
                    styles["small"],
                )
            )

    # Methodology
    story.append(Paragraph("4. Metodologia", styles["h1"]))
    for line in methodology:
        story.append(Paragraph(f"• {_esc(line)}", styles["bullet"]))

    story.append(Paragraph("5. Fontes", styles["h1"]))
    for line in sources:
        story.append(Paragraph(f"• {_esc(line)}", styles["bullet"]))

    story.append(Paragraph("6. Limitações e ressalvas", styles["h1"]))
    for line in limitations:
        story.append(Paragraph(f"• {_esc(line)}", styles["warn"]))
    for line in legal_disclaimers or []:
        story.append(Paragraph(f"• {_esc(line)}", styles["warn"]))

    story.append(Paragraph("7. Proveniência", styles["h1"]))
    prov_items = {
        "run_id": version_id,
        "generated_at": generated_at,
        "data_as_of": data_as_of or "não informado",
        **{k: str(v) for k, v in provenance.items()},
    }
    for k, v in prov_items.items():
        story.append(Paragraph(f"• <b>{_esc(k)}</b>: {_esc(v)}", styles["bullet"]))

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return path


def _esc(value: Any) -> str:
    text = "" if value is None else str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )

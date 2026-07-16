#!/usr/bin/env python3
"""
Relatorio Executivo — Extra Construtora (PDF).

Gera PDF institucional (estetica Big Four) com analise de todas as oportunidades
do banco de dados, classificadas por ranking GO/REVIEW/NO_GO.

Seccoes:
  1. Capa — Extra Construtora, data, "Relatorio de Inteligencia em Licitacoes"
  2. Sumario Executivo — metricas-chave
  3. Ranking de Orgaos Compradores — top 20 orgaos por volume de editais (SC)
  4. Editais Abertos — GO — lista com justificativa, ordenados por score
  5. Editais Abertos — REVIEW — lista com o que falta para decidir
  6. Editais Abertos — NO_GO — lista com motivo da exclusao
  7. Contratos Vincendos — se disponivel em pncp_supplier_contracts
  8. Painel de Valores — distribuicao por modalidade, faixa de valores
  9. Concorrentes e Vencedores — se disponivel em pncp_raw_bids
  10. Metodologia e Confianca — fontes usadas, datas, limitacoes

Design: Big Four aesthetic — charcoal navy + bronze, Times-Roman serif,
three-rule tables. Identico ao intel_report.py.

Usage:
    python scripts/reports/executive_report.py
    python scripts/reports/executive_report.py --output output/reports/executivo-extra-2026-07-15.pdf
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, date, datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

DSN = os.getenv(
    "LOCAL_DATALAKE_DSN",
    "postgresql://test:test@127.0.0.1:5433/pncp_datalake",
)

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("ERROR: psycopg2 not installed. Run: pip install psycopg2-binary")
    sys.exit(1)

try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm, mm
    from reportlab.pdfgen import canvas as pdfgen_canvas
    from reportlab.platypus import (
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )
except ImportError:
    print("ERROR: reportlab not installed. Run: pip install reportlab")
    sys.exit(1)


# ============================================================
# DESIGN TOKENS — Big Four Aesthetic
# ============================================================

INK = colors.HexColor("#1B2A3D")
ACCENT = colors.HexColor("#8B7355")
SIGNAL_RED = colors.HexColor("#B5342A")
SIGNAL_GREEN = colors.HexColor("#1B7A3D")
SIGNAL_AMBER = colors.HexColor("#B8860B")

TEXT_COLOR = colors.HexColor("#2D3748")
TEXT_SECONDARY = colors.HexColor("#5A6577")
TEXT_MUTED = colors.HexColor("#8896A6")
RULE_COLOR = colors.HexColor("#C8CDD3")
RULE_HEAVY = colors.HexColor("#4A5568")

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 2.2 * cm

FOOTER_LINE1 = "Tiago Sasaki — Consultor de Inteligencia em Licitacoes"
FOOTER_LINE2 = "Relatorio confidencial — Extra Construtora"

# ============================================================
# DB layer
# ============================================================


def get_conn():
    return psycopg2.connect(DSN)


def query(conn, sql: str, params: list = None) -> list[dict]:
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(sql, params)
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    return rows


def scalar(conn, sql: str, params: list = None):
    cur = conn.cursor()
    cur.execute(sql, params)
    val = cur.fetchone()
    cur.close()
    return val[0] if val else None


# ============================================================
# Data queries
# ============================================================


def load_all_opportunities(conn) -> list[dict]:
    return query(
        conn,
        """SELECT id, source, source_id, source_url, content_hash,
                  orgao_nome, uf, municipio, modalidade, objeto,
                  valor_estimado, valor_homologado,
                  data_publicacao, data_abertura, data_encerramento,
                  ranking, ranking_score, ranking_confianca,
                  ranking_fatores, ranking_regras,
                  qualidade_score, qualidade_fatores,
                  link_edital, numero_controle_pncp, status_canonico
           FROM opportunity_intel
           WHERE is_active = true
           ORDER BY ranking, ranking_score DESC""",
    )


def load_orgao_ranking(conn, limit: int = 20) -> list[dict]:
    return query(
        conn,
        """SELECT orgao_nome, uf,
                  COUNT(*) AS qtd_editais,
                  COUNT(*) FILTER (WHERE ranking = 'GO') AS qtd_go,
                  ROUND(SUM(valor_estimado)::numeric, 2) AS total_valor_estimado,
                  ROUND(SUM(valor_homologado)::numeric, 2) AS total_valor_homologado
           FROM opportunity_intel
           WHERE is_active = true AND uf = 'SC' AND orgao_nome IS NOT NULL
           GROUP BY orgao_nome, uf
           ORDER BY qtd_editais DESC
           LIMIT %s""",
        (limit,),
    )


def load_vincendos(conn) -> list[dict]:
    return query(
        conn,
        """SELECT contrato_id, orgao_nome, fornecedor_nome, objeto_contrato,
                  valor_total, data_inicio, data_fim
           FROM pncp_supplier_contracts
           WHERE is_active = true
             AND data_fim BETWEEN CURRENT_DATE AND CURRENT_DATE + INTERVAL '180 days'
           ORDER BY data_fim ASC""",
    )


def load_concorrentes(conn) -> list[dict]:
    return query(
        conn,
        """SELECT orgao_razao_social, uf, municipio,
                  COUNT(*) AS qtd_vencidas,
                  ROUND(AVG(valor_total_estimado)::numeric, 2) AS ticket_medio,
                  ROUND(SUM(valor_total_estimado)::numeric, 2) AS total_contratado
           FROM pncp_raw_bids
           WHERE is_active = true
           GROUP BY orgao_razao_social, uf, municipio
           ORDER BY total_contratado DESC
           LIMIT 20""",
    )


def load_modalidade_panel(conn) -> list[dict]:
    return query(
        conn,
        """SELECT modalidade,
                  COUNT(*) AS qtd,
                  ROUND(AVG(valor_estimado)::numeric, 2) AS ticket_medio_estimado,
                  ROUND(AVG(valor_homologado)::numeric, 2) AS ticket_medio_homologado,
                  ROUND(SUM(valor_estimado)::numeric, 2) AS total_estimado,
                  ROUND(SUM(valor_homologado)::numeric, 2) AS total_homologado
           FROM opportunity_intel
           WHERE is_active = true
             AND modalidade IS NOT NULL
           GROUP BY modalidade
           ORDER BY qtd DESC""",
    )


# ============================================================
# Helpers
# ============================================================


def _s(value: str) -> str:
    if value is None:
        return ""
    return str(value)


def _currency(value, default="N/I"):
    if value is None:
        return default
    try:
        v = float(value)
    except (ValueError, TypeError):
        return default
    if v == 0:
        return "R$ 0,00"
    formatted = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {formatted}"


def _currency_short(value) -> str:
    if value is None:
        return "N/I"
    try:
        v = float(value)
    except (ValueError, TypeError):
        return "N/I"
    if v >= 1_000_000:
        formatted = f"{v / 1_000_000:,.1f}M".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {formatted}"
    if v >= 1_000:
        formatted = f"{v / 1_000:,.0f}K".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {formatted}"
    return _currency(v)


def _date_val(value):
    if not value:
        return "N/I"
    if isinstance(value, (date, datetime)):
        return value.strftime("%d/%m/%Y")
    text = str(value).strip()[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).strftime("%d/%m/%Y")
        except ValueError:
            continue
    return text


def _today() -> str:
    return datetime.now(UTC).strftime("%d/%m/%Y")


def _month_year() -> str:
    months = {
        1: "Janeiro",
        2: "Fevereiro",
        3: "Marco",
        4: "Abril",
        5: "Maio",
        6: "Junho",
        7: "Julho",
        8: "Agosto",
        9: "Setembro",
        10: "Outubro",
        11: "Novembro",
        12: "Dezembro",
    }
    now = datetime.now(UTC)
    return f"{months[now.month]} {now.year}"


def _trunc(text: str, n: int = 60) -> str:
    text = _s(text)
    return text if len(text) <= n else text[: n - 3].rstrip() + "..."


def _safe_float(v, d=0.0) -> float:
    try:
        return float(v) if v is not None else d
    except (ValueError, TypeError):
        return d


def _plural(n: int, singular: str, plural: str) -> str:
    return singular if n == 1 else plural


def _ranking_fatores_json(record: dict) -> dict:
    fatores = record.get("ranking_fatores")
    if fatores is None:
        return {"positivos": [], "negativos": [], "bloqueadores": []}
    if isinstance(fatores, str):
        import json

        try:
            return json.loads(fatores)
        except (json.JSONDecodeError, TypeError):
            return {"positivos": [], "negativos": [], "bloqueadores": []}
    if isinstance(fatores, dict):
        return fatores
    return {"positivos": [], "negativos": [], "bloqueadores": []}


# ============================================================
# Three-rule table
# ============================================================


def _three_rule_table(rows: list, col_widths: list, repeat_rows: int = 1) -> Table:
    t = Table(rows, colWidths=col_widths, repeatRows=repeat_rows)
    n = len(rows)
    style_cmds = [
        ("LINEABOVE", (0, 0), (-1, 0), 1.2, RULE_HEAVY),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, RULE_HEAVY),
        ("LINEBELOW", (0, n - 1), (-1, n - 1), 0.8, RULE_COLOR),
        *[("LINEBELOW", (0, i), (-1, i), 0.3, RULE_COLOR) for i in range(1, n - 1)],
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]
    t.setStyle(TableStyle(style_cmds))
    return t


def _section_heading(title: str, styles: dict) -> list:
    avail = PAGE_WIDTH - 2 * MARGIN
    rule_t = Table([[""]], colWidths=[avail], rowHeights=[1])
    rule_t.setStyle(
        TableStyle(
            [
                ("LINEBELOW", (0, 0), (0, 0), 0.6, ACCENT),
                ("TOPPADDING", (0, 0), (0, 0), 0),
                ("BOTTOMPADDING", (0, 0), (0, 0), 0),
            ]
        )
    )
    return [rule_t, Spacer(1, 2 * mm), Paragraph(title, styles["h1"])]


# ============================================================
# Styles
# ============================================================


def _build_styles() -> dict:
    base = getSampleStyleSheet()
    s = {}

    # Cover
    s["cover_title"] = ParagraphStyle(
        "cover_title",
        parent=base["Normal"],
        fontName="Times-Bold",
        fontSize=26,
        textColor=INK,
        alignment=TA_LEFT,
        leading=32,
        spaceAfter=4 * mm,
    )
    s["cover_subtitle"] = ParagraphStyle(
        "cover_subtitle",
        parent=base["Normal"],
        fontName="Times-Roman",
        fontSize=14,
        textColor=TEXT_SECONDARY,
        alignment=TA_LEFT,
        spaceAfter=3 * mm,
        leading=18,
    )
    s["cover_info"] = ParagraphStyle(
        "cover_info",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=9,
        textColor=TEXT_SECONDARY,
        alignment=TA_LEFT,
        leading=13,
        spaceAfter=1.5 * mm,
    )

    # Headings
    s["h1"] = ParagraphStyle(
        "h1_exec",
        parent=base["Normal"],
        fontName="Times-Bold",
        fontSize=14,
        textColor=INK,
        spaceBefore=8 * mm,
        spaceAfter=4 * mm,
        leading=18,
    )
    s["h2"] = ParagraphStyle(
        "h2_exec",
        parent=base["Normal"],
        fontName="Times-Bold",
        fontSize=11,
        textColor=INK,
        spaceBefore=5 * mm,
        spaceAfter=3 * mm,
        leading=14,
    )

    # Body
    s["body"] = ParagraphStyle(
        "body_exec",
        parent=base["Normal"],
        fontName="Times-Roman",
        fontSize=10,
        textColor=TEXT_COLOR,
        alignment=TA_JUSTIFY,
        leading=14,
        spaceAfter=2 * mm,
    )
    s["body_small"] = ParagraphStyle(
        "body_small_exec",
        parent=base["Normal"],
        fontName="Times-Roman",
        fontSize=9,
        textColor=TEXT_SECONDARY,
        leading=12,
        spaceAfter=1.5 * mm,
    )
    s["italic_note"] = ParagraphStyle(
        "italic_note_exec",
        parent=base["Normal"],
        fontName="Times-Italic",
        fontSize=9,
        textColor=SIGNAL_AMBER,
        leading=12,
        spaceAfter=1.5 * mm,
    )
    s["caption"] = ParagraphStyle(
        "caption_exec",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        textColor=TEXT_MUTED,
        leading=9,
    )

    # Metrics
    s["metric_value"] = ParagraphStyle(
        "mv_exec",
        parent=base["Normal"],
        fontName="Times-Bold",
        fontSize=22,
        textColor=INK,
        alignment=TA_CENTER,
        leading=22,
    )
    s["metric_label"] = ParagraphStyle(
        "ml_exec",
        parent=base["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        textColor=TEXT_MUTED,
        alignment=TA_CENTER,
        leading=9,
    )

    # Table cells
    for name, align in [("cell", TA_LEFT), ("cell_center", TA_CENTER), ("cell_right", TA_RIGHT)]:
        s[name] = ParagraphStyle(
            f"{name}_exec",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            textColor=TEXT_COLOR,
            leading=10,
            alignment=align,
        )
    s["cell_header"] = ParagraphStyle(
        "ch_exec",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        textColor=INK,
        leading=10,
        alignment=TA_LEFT,
    )
    s["cell_header_center"] = ParagraphStyle(
        "chc_exec",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        textColor=INK,
        leading=10,
        alignment=TA_CENTER,
    )
    s["cell_header_right"] = ParagraphStyle(
        "chr_exec",
        parent=base["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        textColor=INK,
        leading=10,
        alignment=TA_RIGHT,
    )

    return s


# ============================================================
# Canvas com numeração de páginas
# ============================================================


class _NumberedCanvas(pdfgen_canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states: list = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_page_number(total)
            pdfgen_canvas.Canvas.showPage(self)
        pdfgen_canvas.Canvas.save(self)

    def _draw_page_number(self, total: int):
        if self._pageNumber == 1:
            return
        self.saveState()
        self.setFont("Helvetica", 7)
        self.setFillColor(TEXT_MUTED)
        self.drawRightString(
            PAGE_WIDTH - MARGIN,
            MARGIN - 12 * mm,
            f"Pagina {self._pageNumber - 1} de {total - 1}",
        )
        self.restoreState()


def _draw_footer(canvas, doc):
    if canvas._pageNumber == 1:
        return
    canvas.saveState()
    y = MARGIN - 10 * mm
    canvas.setStrokeColor(RULE_COLOR)
    canvas.setLineWidth(0.4)
    canvas.line(MARGIN, y + 4 * mm, PAGE_WIDTH - MARGIN, y + 4 * mm)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(TEXT_MUTED)
    canvas.drawCentredString(PAGE_WIDTH / 2, y + 1.5 * mm, FOOTER_LINE1)
    canvas.drawCentredString(PAGE_WIDTH / 2, y - 2 * mm, FOOTER_LINE2)
    canvas.restoreState()


def _metric_cell(value: str, label: str, styles: dict) -> Table:
    inner = Table(
        [[Paragraph(value, styles["metric_value"])], [Paragraph(label, styles["metric_label"])]],
        colWidths=["*"],
    )
    inner.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ]
        )
    )
    return inner


# ============================================================
# SECTION BUILDERS
# ============================================================


def build_cover(data: dict, styles: dict) -> list:
    el = []
    el.append(Spacer(1, 80 * mm))

    avail = PAGE_WIDTH - 2 * MARGIN
    rule_t = Table([["", ""]], colWidths=[40 * mm, avail - 40 * mm])
    rule_t.setStyle(TableStyle([("LINEBELOW", (0, 0), (0, 0), 0.8, ACCENT)]))
    el.append(rule_t)
    el.append(Spacer(1, 6 * mm))

    el.append(Paragraph("RELATORIO DE INTELIGENCIA", styles["cover_title"]))
    el.append(Paragraph("EM LICITACOES", styles["cover_title"]))
    el.append(Paragraph("Extra Construtora", styles["cover_subtitle"]))
    el.append(Paragraph(_month_year(), styles["cover_info"]))
    el.append(Spacer(1, 40 * mm))
    el.append(
        Paragraph(
            "<b>Tiago Sasaki</b><br/>Consultor de Inteligencia em Licitacoes<br/>(48) 9 8834-4559",
            ParagraphStyle(
                "cover_attr",
                fontName="Helvetica",
                fontSize=9,
                textColor=TEXT_SECONDARY,
                alignment=TA_LEFT,
                leading=13,
            ),
        )
    )
    el.append(
        Paragraph(
            "Documento confidencial preparado exclusivamente para a Extra Construtora.",
            ParagraphStyle(
                "cover_conf",
                fontName="Helvetica",
                fontSize=8,
                textColor=TEXT_MUTED,
                alignment=TA_LEFT,
                leading=10,
                spaceBefore=4 * mm,
            ),
        )
    )
    el.append(PageBreak())
    return el


def build_sumario_executivo(stats: dict, styles: dict) -> list:
    el = []
    el.extend(_section_heading("Sumario Executivo", styles))
    el.append(Spacer(1, 4 * mm))

    total = stats.get("total_oportunidades", 0)
    total_go = stats.get("total_go", 0)
    total_no_go = stats.get("total_no_go", 0)
    valor_estimado_total = stats.get("valor_estimado_total", 0)
    orgaos_ativos = stats.get("orgaos_ativos", 0)
    confianca_high = stats.get("confianca_high", 0)

    # --- Quality indicator ---
    if total == 0:
        el.append(
            Paragraph(
                "Nao ha oportunidades ativas no banco de dados para o periodo analisado. "
                "Recomenda-se ampliar a janela de busca ou ajustar os filtros de compatibilidade.",
                styles["body"],
            )
        )
        return el

    # --- Key metrics row ---
    avail = PAGE_WIDTH - 2 * MARGIN
    col_w = avail / 4
    metrics_row = [
        [
            _metric_cell(str(total), "Oportunidades Totais", styles),
            _metric_cell(str(total_go), "Classificadas GO", styles),
            _metric_cell(str(orgaos_ativos), "Orgaos Ativos (SC)", styles),
            _metric_cell(_currency_short(valor_estimado_total), "Valor Est. Total", styles),
        ]
    ]
    metrics_t = Table(metrics_row, colWidths=[col_w, col_w, col_w, col_w])
    metrics_t.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    el.append(metrics_t)
    el.append(Spacer(1, 4 * mm))

    # --- Executive narrative ---
    lines = []
    lines.append(
        f"Foram identificadas {total} oportunidades ativas no banco de dados, "
        f"das quais {total_go} receberam classificacao GO "
        f"(score medio de {stats.get('score_medio_go', 0):.0f} pontos) e "
        f"{total_no_go} foram classificadas como NO_GO."
    )
    if valor_estimado_total > 0:
        lines.append(
            f"O valor estimado total das oportunidades e de aproximadamente "
            f"{_currency(valor_estimado_total)}, distribuido entre {orgaos_ativos} "
            f"orgaos compradores ativos no estado de Santa Catarina."
        )
    if confianca_high > 0:
        pct = confianca_high / total * 100
        lines.append(
            f"Das oportunidades analisadas, {confianca_high} ({pct:.0f}%) possuem "
            f"nivel de confianca HIGH, indicando consistencia elevada dos dados coletados."
        )
    el.append(Paragraph(" ".join(lines), styles["body"]))

    # --- Quality / freshness note ---
    fontes = stats.get("fontes_usadas", [])
    if fontes:
        el.append(
            Paragraph(
                f"Fontes consultadas: {', '.join(fontes)}. Data de geracao: {_today()}.",
                styles["caption"],
            )
        )

    el.append(Spacer(1, 4 * mm))

    # --- Portfolio KPI ---
    kpi_rows_data = [
        ("Oportunidades Totais (GO)", str(total_go)),
        ("Oportunidades NO_GO", str(total_no_go)),
        ("Valor Estimado Total", _currency_short(valor_estimado_total)),
        ("Score Medio GO", f"{stats.get('score_medio_go', 0):.0f} / 100"),
        ("Confianca Alta (HIGH)", f"{confianca_high} ({confianca_high / max(1, total) * 100:.0f}%)"),
        ("Orgaos Distintos em SC", str(orgaos_ativos)),
    ]
    kpi_header = [Paragraph("Indicador", styles["cell_header"]), Paragraph("Valor", styles["cell_header_right"])]
    kpi_table_rows = [kpi_header]
    for label, value in kpi_rows_data:
        kpi_table_rows.append([Paragraph(label, styles["cell"]), Paragraph(value, styles["cell_right"])])

    avail_kpi = PAGE_WIDTH - 2 * MARGIN
    kpi_col_widths = [avail_kpi * 0.6, avail_kpi * 0.4]
    el.append(Paragraph("Metricas do Portfolio", styles["h2"]))
    el.append(_three_rule_table(kpi_table_rows, kpi_col_widths))
    el.append(PageBreak())
    return el


def build_orgao_ranking(orgaos: list[dict], styles: dict) -> list:
    el = []
    el.extend(_section_heading("Ranking de Orgaos Compradores (SC)", styles))
    el.append(Spacer(1, 2 * mm))

    if not orgaos:
        el.append(Paragraph("Nao ha dados suficientes para gerar o ranking de orgaos.", styles["body"]))
        return el

    el.append(
        Paragraph(
            "Top 20 orgaos compradores em Santa Catarina por volume de editais ativos. "
            "Inclui numero de editais com classificacao GO e valores estimados.",
            styles["body"],
        )
    )
    el.append(Spacer(1, 3 * mm))

    avail = PAGE_WIDTH - 2 * MARGIN
    header = [
        Paragraph("#", styles["cell_header_center"]),
        Paragraph("Orgao", styles["cell_header"]),
        Paragraph("Editais", styles["cell_header_center"]),
        Paragraph("GO", styles["cell_header_center"]),
        Paragraph("Valor Est.", styles["cell_header_right"]),
    ]
    rows = [header]
    for idx, o in enumerate(orgaos, 1):
        rows.append(
            [
                Paragraph(str(idx), styles["cell_center"]),
                Paragraph(_trunc(o.get("orgao_nome", ""), 50), styles["cell"]),
                Paragraph(str(o.get("qtd_editais", 0)), styles["cell_center"]),
                Paragraph(str(o.get("qtd_go", 0)), styles["cell_center"]),
                Paragraph(_currency_short(o.get("total_valor_estimado")), styles["cell_right"]),
            ]
        )

    widths = [15, avail - 15 - 40 - 30 - 60, 40, 30, 60]
    el.append(_three_rule_table(rows, widths))

    el.append(Spacer(1, 4 * mm))
    el.append(
        Paragraph(
            "Nota: A coluna 'GO' indica quantos editais do orgao receberam "
            "classificacao GO (recomendados para participacao). "
            "Valores estimados podem incluir editais sem valor declarado (sigilosos).",
            styles["caption"],
        )
    )
    el.append(PageBreak())
    return el


def build_editais_go(oportunidades: list[dict], styles: dict) -> list:
    el = []
    el.extend(_section_heading("Editais Abertos — GO", styles))
    el.append(Spacer(1, 2 * mm))

    go_items = [o for o in oportunidades if o.get("ranking") == "GO"]
    go_items.sort(key=lambda x: _safe_float(x.get("ranking_score", 0)), reverse=True)

    if not go_items:
        el.append(
            Paragraph(
                "Nenhum edital classificado como GO no momento. "
                "Isso pode indicar que todos os editais viaveis ja foram processados "
                "ou que os criterios de triagem estao restritivos.",
                styles["body"],
            )
        )
        return el

    el.append(
        Paragraph(
            f"{len(go_items)} editais classificados como GO, ordenados por score de "
            f"prioridade. Cada entrada inclui justificativa baseada nos fatores de ranking.",
            styles["body_small"],
        )
    )
    el.append(Spacer(1, 3 * mm))

    for idx, ed in enumerate(go_items[:30], 1):
        score = ed.get("ranking_score", 0)
        score_color = SIGNAL_GREEN if score >= 80 else SIGNAL_AMBER if score >= 50 else SIGNAL_RED

        # Header row with score badge
        obj_text = _trunc(ed.get("objeto", "Sem objeto"), 90)
        score_label = f"Score: {score}"
        orgao = _trunc(ed.get("orgao_nome", ""), 40)
        municipio = _s(ed.get("municipio", ""))
        modalidade = _s(ed.get("modalidade", ""))
        valor = _currency_short(ed.get("valor_estimado"))

        meta_parts = [p for p in [orgao, municipio, modalidade] if p]
        meta_str = " | ".join(meta_parts)

        # Extract justificativa from ranking_fatores
        fatores = _ranking_fatores_json(ed)
        positivos = fatores.get("positivos", [])
        negativos = fatores.get("negativos", [])

        # Build detail block
        rules = ed.get("ranking_regras", [])
        if isinstance(rules, (list, tuple)):
            rules_str = "; ".join(str(r) for r in rules[:5])
        else:
            rules_str = str(rules)[:200]

        el.append(
            Paragraph(
                f"<b>{idx}. {_s(obj_text)}</b> "
                f'<font color="{score_color.hexval()}">[{score_label}]</font>'
                f"  {_s(meta_str)}  |  {_s(valor)}",
                ParagraphStyle(
                    f"go_title_{idx}",
                    parent=styles["edital_title"] if "edital_title" in styles else styles["h2"],
                    fontName="Times-Bold",
                    fontSize=9.5,
                    textColor=INK,
                    leading=12,
                    spaceAfter=1 * mm,
                ),
            )
        )

        # Positives
        if positivos:
            el.append(
                Paragraph(
                    f"<font color='#1B7A3D'>+ {'; '.join(_s(p) for p in positivos[:4])}</font>",
                    ParagraphStyle(
                        f"go_pos_{idx}",
                        parent=styles["body_small"],
                        fontName="Helvetica",
                        fontSize=7.5,
                        textColor=SIGNAL_GREEN,
                        leading=9,
                        leftIndent=6,
                        spaceAfter=0.5 * mm,
                    ),
                )
            )
        # Negatives (yellow flags)
        if negativos:
            el.append(
                Paragraph(
                    f"<font color='#B8860B'>-- {'; '.join(_s(n) for n in negativos[:3])}</font>",
                    ParagraphStyle(
                        f"go_neg_{idx}",
                        parent=styles["body_small"],
                        fontName="Helvetica",
                        fontSize=7.5,
                        textColor=SIGNAL_AMBER,
                        leading=9,
                        leftIndent=6,
                        spaceAfter=0.5 * mm,
                    ),
                )
            )
        # Regras
        if rules_str:
            el.append(
                Paragraph(
                    f"Regras: {rules_str}",
                    ParagraphStyle(
                        f"go_rules_{idx}",
                        parent=styles["caption"],
                        fontSize=6.5,
                        leading=8,
                        leftIndent=6,
                    ),
                )
            )

        el.append(Spacer(1, 2 * mm))

    if len(go_items) > 30:
        el.append(
            Paragraph(
                f"Lista truncada em 30 itens. Total de {len(go_items)} editais GO no banco de dados.",
                styles["caption"],
            )
        )

    el.append(PageBreak())
    return el


def build_editais_review(oportunidades: list[dict], styles: dict) -> list:
    el = []
    el.extend(_section_heading("Editais Abertos — REVIEW", styles))
    el.append(Spacer(1, 2 * mm))

    review_items = [o for o in oportunidades if o.get("ranking") == "REVIEW"]
    review_items.sort(key=lambda x: _safe_float(x.get("ranking_score", 0)), reverse=True)

    if not review_items:
        el.append(
            Paragraph(
                "Nenhum edital classificado como REVIEW no momento. "
                "Todos os editais foram categorizados como GO ou NO_GO.",
                styles["body"],
            )
        )
        el.append(PageBreak())
        return el

    el.append(
        Paragraph(
            f"{len(review_items)} editais aguardando classificacao definitiva (REVIEW). "
            "Abaixo o resumo do que falta para decidir.",
            styles["body_small"],
        )
    )
    el.append(Spacer(1, 3 * mm))

    for idx, ed in enumerate(review_items[:20], 1):
        score = ed.get("ranking_score", 0)
        obj_text = _trunc(ed.get("objeto", "Sem objeto"), 80)
        orgao = _trunc(ed.get("orgao_nome", ""), 35)
        municipio = _s(ed.get("municipio", ""))

        fatores = _ranking_fatores_json(ed)
        positivos = fatores.get("positivos", [])
        negativos = fatores.get("negativos", [])
        bloqueadores = fatores.get("bloqueadores", [])

        el.append(
            Paragraph(
                f"<b>{idx}. {_s(obj_text)}</b>  |  {_s(orgao)} / {_s(municipio)}  |  Score: {score}",
                ParagraphStyle(
                    f"rev_title_{idx}",
                    fontName="Times-Bold",
                    fontSize=9.5,
                    textColor=INK,
                    leading=12,
                    spaceAfter=1 * mm,
                ),
            )
        )

        # Faltam para decidir (blockers + negatives)
        pendentes = bloqueadores[:] + negativos[:]
        if pendentes:
            el.append(
                Paragraph(
                    f"Pendente: {'; '.join(_s(p) for p in pendentes[:5])}",
                    ParagraphStyle(
                        f"rev_pend_{idx}",
                        parent=styles["body_small"],
                        fontName="Helvetica",
                        fontSize=7.5,
                        textColor=SIGNAL_AMBER,
                        leading=9,
                        leftIndent=6,
                    ),
                )
            )
        else:
            el.append(
                Paragraph(
                    "Nenhum fator negativo ou bloqueador identificado. Recomenda-se revisao manual para deciso final.",
                    ParagraphStyle(
                        f"rev_none_{idx}",
                        parent=styles["body_small"],
                        fontName="Helvetica",
                        fontSize=7.5,
                        textColor=TEXT_MUTED,
                        leading=9,
                        leftIndent=6,
                    ),
                )
            )

        if positivos:
            el.append(
                Paragraph(
                    f"Pontos fortes: {'; '.join(_s(p) for p in positivos[:3])}",
                    ParagraphStyle(
                        f"rev_pos_{idx}",
                        parent=styles["body_small"],
                        fontName="Helvetica",
                        fontSize=7,
                        textColor=SIGNAL_GREEN,
                        leading=8,
                        leftIndent=6,
                    ),
                )
            )

        el.append(Spacer(1, 2 * mm))

    if len(review_items) > 20:
        el.append(Paragraph(f"Lista truncada. Total: {len(review_items)} editais REVIEW.", styles["caption"]))

    el.append(PageBreak())
    return el


def build_editais_no_go(oportunidades: list[dict], styles: dict) -> list:
    el = []
    el.extend(_section_heading("Editais Abertos — NO_GO", styles))
    el.append(Spacer(1, 2 * mm))

    no_go_items = [o for o in oportunidades if o.get("ranking") == "NO_GO"]

    if not no_go_items:
        el.append(Paragraph("Nenhum edital classificado como NO_GO.", styles["body"]))
        el.append(PageBreak())
        return el

    el.append(
        Paragraph(
            f"{len(no_go_items)} editais classificados como NAO PARTICIPAR (NO_GO). "
            "Cada entrada inclui o motivo da exclusao.",
            styles["body_small"],
        )
    )
    el.append(Spacer(1, 3 * mm))

    # Aggregate by motivo
    from collections import Counter

    motivos_aggregated = Counter()
    for ed in no_go_items:
        fatores = _ranking_fatores_json(ed)
        bloqueadores = fatores.get("bloqueadores", [])
        for b in bloqueadores:
            motivos_aggregated[b] += 1
        if not bloqueadores:
            negativos = fatores.get("negativos", [])
            for n in negativos:
                motivos_aggregated[n] += 1

    if motivos_aggregated:
        el.append(Paragraph("Distribuicao dos Motivos de Exclusao:", styles["h2"]))
        avail = PAGE_WIDTH - 2 * MARGIN
        motivo_rows = [[Paragraph("Motivo", styles["cell_header"]), Paragraph("Qtd", styles["cell_header_center"])]]
        for motivo, qtd in motivos_aggregated.most_common(10):
            motivo_rows.append(
                [
                    Paragraph(_s(motivo), styles["cell"]),
                    Paragraph(str(qtd), styles["cell_center"]),
                ]
            )
        el.append(_three_rule_table(motivo_rows, [avail - 40, 40]))
        el.append(Spacer(1, 4 * mm))

    # List items
    for idx, ed in enumerate(no_go_items[:20], 1):
        obj_text = _trunc(ed.get("objeto", "Sem objeto"), 70)
        orgao = _trunc(ed.get("orgao_nome", ""), 30)
        valor = _currency_short(ed.get("valor_estimado"))

        fatores = _ranking_fatores_json(ed)
        bloqueadores = fatores.get("bloqueadores", [])
        negativos = fatores.get("negativos", [])
        motivo_exclusao = (
            "; ".join(bloqueadores[:3]) if bloqueadores else "; ".join(negativos[:3]) if negativos else "N/I"
        )

        el.append(
            Paragraph(
                f"<b>{idx}. {_s(obj_text)}</b>  |  {_s(orgao)}  |  {_s(valor)}",
                ParagraphStyle(
                    f"ngo_title_{idx}",
                    fontName="Times-Bold",
                    fontSize=9,
                    textColor=TEXT_SECONDARY,
                    leading=11,
                    spaceAfter=1 * mm,
                ),
            )
        )
        el.append(
            Paragraph(
                f"<font color='#B5342A'>Exclusao: {_s(motivo_exclusao)}</font>",
                ParagraphStyle(
                    f"ngo_motivo_{idx}",
                    parent=styles["body_small"],
                    fontName="Helvetica",
                    fontSize=7.5,
                    textColor=SIGNAL_RED,
                    leading=9,
                    leftIndent=6,
                    spaceAfter=2 * mm,
                ),
            )
        )

    if len(no_go_items) > 20:
        el.append(Paragraph(f"Lista truncada. Total: {len(no_go_items)} editais NO_GO.", styles["caption"]))

    el.append(PageBreak())
    return el


def build_contratos_vincendos(vincendos: list[dict], styles: dict) -> list:
    el = []
    el.extend(_section_heading("Contratos Vincendos", styles))
    el.append(Spacer(1, 2 * mm))

    if not vincendos:
        el.append(
            Paragraph(
                "Nao ha dados de contratos vincendos disponiveis no momento. "
                "A tabela pncp_supplier_contracts nao possui registros com vencimento "
                "nos proximos 180 dias. Recomenda-se ativar o crawl de contratos para "
                "obter esta informacao em relatorios futuros.",
                styles["body"],
            )
        )
        el.append(PageBreak())
        return el

    el.append(
        Paragraph(
            f"{len(vincendos)} contratos com vencimento nos proximos 180 dias. "
            "Estes representam oportunidades de relicitacao ou aditivo.",
            styles["body_small"],
        )
    )
    el.append(Spacer(1, 3 * mm))

    avail = PAGE_WIDTH - 2 * MARGIN
    header = [
        Paragraph("Orgao", styles["cell_header"]),
        Paragraph("Fornecedor", styles["cell_header"]),
        Paragraph("Valor", styles["cell_header_right"]),
        Paragraph("Vencimento", styles["cell_header_center"]),
    ]
    rows = [header]
    for v in vincendos:
        rows.append(
            [
                Paragraph(_trunc(v.get("orgao_nome", ""), 35), styles["cell"]),
                Paragraph(_trunc(v.get("fornecedor_nome", ""), 30), styles["cell"]),
                Paragraph(_currency_short(v.get("valor_total")), styles["cell_right"]),
                Paragraph(_date_val(v.get("data_fim")), styles["cell_center"]),
            ]
        )

    widths = [avail * 0.35, avail * 0.30, avail * 0.20, avail * 0.15]
    el.append(_three_rule_table(rows, widths))

    el.append(PageBreak())
    return el


def build_painel_valores(modalidades: list[dict], stats: dict, styles: dict) -> list:
    el = []
    el.extend(_section_heading("Painel de Valores", styles))
    el.append(Spacer(1, 2 * mm))

    el.append(
        Paragraph(
            "Distribuicao dos valores por modalidade de contratacao. "
            "ATENCAO: Nao confundir valor estimado com valor homologado. "
            "O valor estimado e a previsao inicial do orgao; o homologado "
            "e o valor efetivamente contratado apos a licitacao.",
            styles["body_small"],
        )
    )
    el.append(Spacer(1, 3 * mm))

    if not modalidades:
        el.append(Paragraph("Dados insuficientes para gerar o painel de valores.", styles["body"]))
        el.append(PageBreak())
        return el

    avail = PAGE_WIDTH - 2 * MARGIN
    header = [
        Paragraph("Modalidade", styles["cell_header"]),
        Paragraph("Qtd", styles["cell_header_center"]),
        Paragraph("Ticket Medio Est.", styles["cell_header_right"]),
        Paragraph("Ticket Medio Hom.", styles["cell_header_right"]),
        Paragraph("Total Est.", styles["cell_header_right"]),
    ]
    rows = [header]
    for m in modalidades:
        rows.append(
            [
                Paragraph(_s(m.get("modalidade", "")), styles["cell"]),
                Paragraph(str(m.get("qtd", 0)), styles["cell_center"]),
                Paragraph(_currency_short(m.get("ticket_medio_estimado")), styles["cell_right"]),
                Paragraph(_currency_short(m.get("ticket_medio_homologado")), styles["cell_right"]),
                Paragraph(_currency_short(m.get("total_estimado")), styles["cell_right"]),
            ]
        )

    widths = [avail * 0.30, 30, avail * 0.20, avail * 0.20, avail * 0.20]
    el.append(_three_rule_table(rows, widths))

    el.append(Spacer(1, 4 * mm))

    # Value brackets
    el.append(Paragraph("Distribuicao por Faixa de Valor (Estimado)", styles["h2"]))
    faixas = {
        "Ate R$ 50K": 0,
        "R$ 50K a R$ 200K": 0,
        "R$ 200K a R$ 1M": 0,
        "R$ 1M a R$ 5M": 0,
        "Acima de R$ 5M": 0,
        "Sem valor (sigiloso)": 0,
    }
    for ed in stats.get("_raw_oportunidades", []):
        v = _safe_float(ed.get("valor_estimado"), None)
        if v is None or v == 0:
            faixas["Sem valor (sigiloso)"] += 1
        elif v <= 50000:
            faixas["Ate R$ 50K"] += 1
        elif v <= 200000:
            faixas["R$ 50K a R$ 200K"] += 1
        elif v <= 1_000_000:
            faixas["R$ 200K a R$ 1M"] += 1
        elif v <= 5_000_000:
            faixas["R$ 1M a R$ 5M"] += 1
        else:
            faixas["Acima de R$ 5M"] += 1

    faixa_rows = [[Paragraph("Faixa", styles["cell_header"]), Paragraph("Qtd", styles["cell_header_center"])]]
    for faixa, qtd in faixas.items():
        if qtd > 0:
            faixa_rows.append([Paragraph(faixa, styles["cell"]), Paragraph(str(qtd), styles["cell_center"])])

    el.append(_three_rule_table(faixa_rows, [avail * 0.5, 40]))

    el.append(Spacer(1, 3 * mm))
    el.append(
        Paragraph(
            "Nota: Valor estimado e a previsao do orgao contratante. "
            "Valor homologado e o valor efetivamente contratado, disponivel "
            "apos a conclusao da licitacao. Quando ha diferenca significativa, "
            "pode indicar desagio ou revisao de escopo.",
            styles["caption"],
        )
    )

    el.append(PageBreak())
    return el


def build_concorrentes(concorrentes: list[dict], styles: dict) -> list:
    el = []
    el.extend(_section_heading("Concorrentes e Vencedores", styles))
    el.append(Spacer(1, 2 * mm))

    if not concorrentes:
        el.append(
            Paragraph(
                "Nao ha dados de concorrentes e vencedores disponiveis. "
                "A tabela pncp_raw_bids possui registros, mas nao foi possivel "
                "extrair informacao de fornecedores vencedores. "
                "Recomenda-se enriquecer os dados com a fonte adequada.",
                styles["body"],
            )
        )
        el.append(PageBreak())
        return el

    el.append(
        Paragraph(
            "Orgaos que mais contrataram, com ticket medio e total contratado. Dados extraidos de pncp_raw_bids.",
            styles["body_small"],
        )
    )
    el.append(Spacer(1, 3 * mm))

    avail = PAGE_WIDTH - 2 * MARGIN
    header = [
        Paragraph("Orgao", styles["cell_header"]),
        Paragraph("Qtd", styles["cell_header_center"]),
        Paragraph("Ticket Medio", styles["cell_header_right"]),
        Paragraph("Total Contratado", styles["cell_header_right"]),
    ]
    rows = [header]
    for c in concorrentes:
        rows.append(
            [
                Paragraph(_trunc(c.get("orgao_razao_social", ""), 40), styles["cell"]),
                Paragraph(str(c.get("qtd_vencidas", 0)), styles["cell_center"]),
                Paragraph(_currency_short(c.get("ticket_medio")), styles["cell_right"]),
                Paragraph(_currency_short(c.get("total_contratado")), styles["cell_right"]),
            ]
        )

    widths = [avail * 0.40, 35, avail * 0.25, avail * 0.25]
    el.append(_three_rule_table(rows, widths))

    el.append(Spacer(1, 4 * mm))
    el.append(
        Paragraph(
            "Nota: Dados agregados por orgao contratante. Para analise de "
            "concorrentes especificos (empresas vencedoras), e necessario "
            "enriquecimento com dados de fornecedores.",
            styles["caption"],
        )
    )

    el.append(PageBreak())
    return el


def build_metodologia(stats: dict, oportunidades: list[dict], styles: dict) -> list:
    el = []
    el.extend(_section_heading("Metodologia e Confianca", styles))
    el.append(Spacer(1, 2 * mm))

    el.append(Paragraph("Fontes de Dados", styles["h2"]))
    fontes = stats.get("fontes_usadas", [])
    if fontes:
        for f in fontes:
            el.append(Paragraph(f"•  {f}", styles["bullet"] if "bullet" in styles else styles["body"]))
    else:
        el.append(Paragraph("•  PNCP (Portal Nacional de Contratacoes Publicas)", styles["body"]))
        el.append(Paragraph("•  SC Public Entities (base de orgaos catarinenses)", styles["body"]))

    el.append(Spacer(1, 3 * mm))

    # Confidence levels
    el.append(Paragraph("Niveis de Confianca", styles["h2"]))
    conf_counts = stats.get("confianca_dist", {})
    total = sum(conf_counts.values()) if conf_counts else len(oportunidades)
    if conf_counts:
        avail = PAGE_WIDTH - 2 * MARGIN
        conf_rows = [
            [
                Paragraph("Nivel", styles["cell_header"]),
                Paragraph("Qtd", styles["cell_header_center"]),
                Paragraph("%", styles["cell_header_right"]),
            ]
        ]
        for nivel in ("HIGH", "MEDIUM", "LOW"):
            qtd = conf_counts.get(nivel, 0)
            if qtd > 0:
                conf_rows.append(
                    [
                        Paragraph(nivel, styles["cell"]),
                        Paragraph(str(qtd), styles["cell_center"]),
                        Paragraph(f"{qtd / max(1, total) * 100:.1f}%", styles["cell_right"]),
                    ]
                )
        el.append(_three_rule_table(conf_rows, [avail * 0.3, avail * 0.3, avail * 0.3]))

    el.append(Spacer(1, 3 * mm))

    # Quality scores
    el.append(Paragraph("Qualidade dos Dados", styles["h2"]))
    qualidades = [o.get("qualidade_score", 0) or 0 for o in oportunidades]
    if qualidades:
        media_qual = sum(qualidades) / len(qualidades)
        el.append(
            Paragraph(
                f"Score medio de qualidade: {media_qual:.0f} / 100. "
                f"Este score reflete a completude e confiabilidade dos dados "
                f"coletados para cada oportunidade.",
                styles["body"],
            )
        )
    el.append(Spacer(1, 3 * mm))

    # Limitations
    el.append(Paragraph("Limitacoes e Riscos", styles["h2"]))
    limitacoes = [
        "Os dados sao coletados de fontes publicas e podem conter inconsistentes ou atrasos de atualizacao.",
        "Valores estimados sao divulgados pelos orgaos contratantes e podem "
        "diferir significativamente dos valores homologados.",
        "A classificacao GO/REVIEW/NO_GO e baseada em criterios objetivos "
        "configurados no sistema e nao substitui a analise juridica, "
        "contabil ou tecnica especializada.",
        "Editais sem valor declarado (sigilosos) tem sua analise limitada aos demais criterios disponiveis.",
        "Recomenda-se verificacao dos editais originais nos portais oficiais "
        "antes de qualquer decisao de participacao.",
    ]
    for lim in limitacoes:
        el.append(
            Paragraph(
                f"•  {lim}",
                ParagraphStyle(
                    "lim_exec",
                    parent=styles["body_small"],
                    fontSize=8,
                    leading=10,
                    spaceAfter=1 * mm,
                    leftIndent=6,
                ),
            )
        )

    el.append(Spacer(1, 4 * mm))
    el.append(
        Paragraph(
            f"Relatorio gerado em {_today()}. Proxima atualizacao recomendada: 7 dias.",
            styles["caption"],
        )
    )

    return el


# ============================================================
# MAIN GENERATOR
# ============================================================


def generate_executive_report(output_path: str):
    conn = get_conn()
    styles = _build_styles()

    try:
        # Load all data
        oportunidades = load_all_opportunities(conn)
        orgaos = load_orgao_ranking(conn)
        modalidades = load_modalidade_panel(conn)
        vincendos = load_vincendos(conn)
        concorrentes = load_concorrentes(conn)

        # Compute stats
        total = len(oportunidades)
        go_count = sum(1 for o in oportunidades if o.get("ranking") == "GO")
        no_go_count = sum(1 for o in oportunidades if o.get("ranking") == "NO_GO")
        review_count = sum(1 for o in oportunidades if o.get("ranking") == "REVIEW")

        go_scores = [_safe_float(o.get("ranking_score", 0)) for o in oportunidades if o.get("ranking") == "GO"]
        score_medio_go = sum(go_scores) / max(1, len(go_scores))

        valor_estimado_total = sum(_safe_float(o.get("valor_estimado"), 0) for o in oportunidades)
        orgaos_ativos = len({o.get("orgao_nome") for o in oportunidades if o.get("orgao_nome") and o.get("uf") == "SC"})

        confianca_dist = {}
        confianca_high = 0
        for o in oportunidades:
            c = o.get("ranking_confianca", "")
            confianca_dist[c] = confianca_dist.get(c, 0) + 1
            if c == "HIGH":
                confianca_high += 1

        stats = {
            "total_oportunidades": total,
            "total_go": go_count,
            "total_no_go": no_go_count,
            "total_review": review_count,
            "score_medio_go": score_medio_go,
            "valor_estimado_total": valor_estimado_total,
            "orgaos_ativos": orgaos_ativos,
            "confianca_high": confianca_high,
            "confianca_dist": confianca_dist,
            "fontes_usadas": ["PNCP (Portal Nacional de Contratacoes Publicas)"],
            "_raw_oportunidades": oportunidades,
        }

        # Build document
        elements = []

        # 1. Cover
        elements.extend(build_cover(stats, styles))

        # 2. Executive Summary
        elements.extend(build_sumario_executivo(stats, styles))

        # 3. Orgao Ranking
        elements.extend(build_orgao_ranking(orgaos, styles))

        # 4. Editais GO
        elements.extend(build_editais_go(oportunidades, styles))

        # 5. Editais REVIEW
        elements.extend(build_editais_review(oportunidades, styles))

        # 6. Editais NO_GO
        elements.extend(build_editais_no_go(oportunidades, styles))

        # 7. Contratos Vincendos
        elements.extend(build_contratos_vincendos(vincendos, styles))

        # 8. Painel de Valores
        elements.extend(build_painel_valores(modalidades, stats, styles))

        # 9. Concorrentes
        elements.extend(build_concorrentes(concorrentes, styles))

        # 10. Metodologia
        elements.extend(build_metodologia(stats, oportunidades, styles))

        # Generate PDF
        doc = SimpleDocTemplate(
            output_path,
            pagesize=A4,
            leftMargin=MARGIN,
            rightMargin=MARGIN,
            topMargin=18 * mm,
            bottomMargin=18 * mm,
            title="Relatorio Executivo - Extra Construtora",
            author="Tiago Sasaki",
        )
        doc.build(elements, onLaterPages=_draw_footer, canvasmaker=_NumberedCanvas)

        return output_path

    finally:
        conn.close()


# ============================================================
# CLI
# ============================================================


def main():
    parser = argparse.ArgumentParser(
        description="Gera PDF de Relatorio Executivo para Extra Construtora (dados reais do banco)"
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Caminho do PDF de saida (default: output/reports/executivo-extra-YYYY-MM-DD.pdf)",
    )
    args = parser.parse_args()

    today_str = datetime.now(UTC).strftime("%Y-%m-%d")
    output_path = args.output or f"output/reports/executivo-extra-{today_str}.pdf"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    result = generate_executive_report(output_path)
    print(f"PDF gerado: {result}")


if __name__ == "__main__":
    main()

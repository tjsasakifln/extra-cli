"""Multi-sheet Excel export for commercial reajuste queue."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.commercial.reajuste_14133.export.reports import FIELD_DICTIONARY, lead_flat_row

try:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
except ImportError as exc:  # pragma: no cover
    raise SystemExit("openpyxl required: pip install openpyxl") from exc


HEADER_FILL = PatternFill("solid", fgColor="1F4E79")
HEADER_FONT = Font(color="FFFFFF", bold=True)
MONEY_FORMAT = '#,##0.00'
DATE_FORMAT = "YYYY-MM-DD"


def _write_sheet(ws, rows: list[dict[str, Any]], *, freeze: bool = True) -> None:
    if not rows:
        ws.append(["(sem registros)"])
        return
    headers = list(rows[0].keys())
    ws.append(headers)
    for cell in ws[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    for row in rows:
        ws.append([row.get(h) for h in headers])
    # widths
    for i, h in enumerate(headers, start=1):
        width = min(48, max(12, len(str(h)) + 2))
        if h in {"objeto", "argumento_comercial", "evidencias_favoraveis", "lacunas", "riscos"}:
            width = 48
        ws.column_dimensions[get_column_letter(i)].width = width
    # formats
    money_cols = {
        i for i, h in enumerate(headers, start=1)
        if any(x in h for x in ("valor", "saldo", "teto", "base_potencialmente"))
    }
    date_cols = {
        i for i, h in enumerate(headers, start=1)
        if "data" in h or h in {"vigencia_final"}
    }
    for r in ws.iter_rows(min_row=2, max_row=ws.max_row):
        for i, cell in enumerate(r, start=1):
            if i in money_cols and isinstance(cell.value, (int, float)):
                cell.number_format = MONEY_FORMAT
            if i in date_cols and cell.value:
                cell.number_format = DATE_FORMAT
    if freeze:
        ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions


def export_workbook(out_dir: Path, run: dict[str, Any]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "leads_reajuste_14133.xlsx"
    wb = Workbook()

    def flat_list(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [lead_flat_row(x) for x in items]

    sheets: list[tuple[str, list[dict[str, Any]]]] = [
        ("TOP_LEADS", flat_list(run.get("top_leads") or [])),
        ("NACIONAL", flat_list(run.get("nacional") or [])),
        ("SUL_SC_PRIORITY", flat_list(run.get("sul_sc_priority") or [])),
    ]
    all_leads = run.get("leads") or []
    by_status = {
        "HOT_VERIFIED": [],
        "STRONG_CANDIDATES": [],
        "REVIEW_REQUIRED": [],
        "ALREADY_ADJUSTED": [],
    }
    for lead in all_leads:
        st = lead.get("classificacao")
        if st == "HOT_VERIFIED":
            by_status["HOT_VERIFIED"].append(lead)
        elif st == "STRONG_CANDIDATE":
            by_status["STRONG_CANDIDATES"].append(lead)
        elif st == "REVIEW_REQUIRED":
            by_status["REVIEW_REQUIRED"].append(lead)
        elif st == "ALREADY_ADJUSTED":
            by_status["ALREADY_ADJUSTED"].append(lead)

    for name, items in by_status.items():
        sheets.append((name, flat_list(items)))

    # EXCLUDED
    excl_rows = []
    for e in run.get("excluded") or []:
        excl_rows.append({
            "contrato_id": e.get("contrato_id"),
            "cnpj": e.get("cnpj"),
            "reason": e.get("reason"),
            "detail": str(e.get("detail") or ""),
        })
    sheets.append(("EXCLUDED", excl_rows or [{"contrato_id": "", "cnpj": "", "reason": "", "detail": ""}]))

    # DATA_QUALITY
    funnel = run.get("funnel") or {}
    dq = [{"metric": k, "value": v} for k, v in funnel.items()]
    metrics = run.get("metrics") or {}
    dq.extend({"metric": f"metrics.{k}", "value": v} for k, v in metrics.items())
    sheets.append(("DATA_QUALITY", dq))

    # METHODOLOGY
    meth = [
        {"item": "escopo", "valor": "Reajuste em sentido estrito — Lei 14.133/2021"},
        {"item": "exclui", "valor": "Reequilíbrio, repactuação, atualização por atraso, aditivo quantitativo"},
        {"item": "data_base", "valor": "Orçamento estimado; proxy só para prospecção"},
        {"item": "hot_rule", "valor": "HOT_VERIFIED exige 10 gates documentais; nunca só datas da tabela PNCP"},
        {"item": "as_of", "valor": run.get("as_of")},
        {"item": "module_version", "valor": run.get("module_version")},
        {"item": "source_mode", "valor": run.get("source_mode")},
    ]
    sheets.append(("METHODOLOGY", meth))

    # FIELD_DICTIONARY
    fd = [{"campo": k, "descricao": v} for k, v in FIELD_DICTIONARY]
    sheets.append(("FIELD_DICTIONARY", fd))

    first = True
    for name, rows in sheets:
        if first:
            ws = wb.active
            ws.title = name[:31]
            first = False
        else:
            ws = wb.create_sheet(name[:31])
        _write_sheet(ws, rows)

    wb.save(path)
    return path

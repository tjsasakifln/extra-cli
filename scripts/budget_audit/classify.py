"""Sheet classification — name alone is never sufficient proof."""

from __future__ import annotations

import re
from typing import Any

from scripts.budget_audit.constants import CLASSIFICATION_RULE_VERSION, SHEET_TYPES

# signals: (regex on name, type, weight)
_NAME_SIGNALS: list[tuple[re.Pattern[str], str, float]] = [
    (re.compile(r"bdi", re.I), "BDI", 0.35),
    # "planilha sintética" is a line-item budget sheet in BR practice, not only a summary
    (re.compile(r"planilha[_\s]*sint[eé]tic|servi[cç]os", re.I), "BUDGET_ANALYTICAL", 0.4),
    (re.compile(r"resumo|summary|fechamento", re.I), "BUDGET_SUMMARY", 0.3),
    (re.compile(r"sint[eé]tic", re.I), "BUDGET_SUMMARY", 0.15),
    # custo unitário composition / analytical cost sheet
    (re.compile(r"custo\s*unit[aá]rio|custo\s*unitario|plan\.?\s*de\s*custo", re.I), "COMPOSITIONS", 0.45),
    (re.compile(r"anal[ií]tic|or[cç]amento", re.I), "BUDGET_ANALYTICAL", 0.3),
    (re.compile(r"composi[cç]", re.I), "COMPOSITIONS", 0.35),
    (re.compile(r"insumo", re.I), "INPUTS", 0.35),
    (re.compile(r"material", re.I), "INPUTS", 0.2),
    (re.compile(r"m[aã]o\s*de\s*obra|labor|mo\b", re.I), "LABOR", 0.3),
    (re.compile(r"equip", re.I), "EQUIPMENT", 0.3),
    (re.compile(r"encargo|social", re.I), "SOCIAL_CHARGES", 0.35),
    (re.compile(r"cronograma|schedule", re.I), "SCHEDULE", 0.35),
    (re.compile(r"\babc\b|curva", re.I), "ABC_CURVE", 0.3),
    # memória de cálculo / quantitativos before generic quant match
    (re.compile(r"mem[oó]ria\s*de\s*c[aá]lculo|memoria\s*de\s*calculo|mem[oó]ria", re.I), "QUANTITY_MEMORY", 0.5),
    (re.compile(r"quantit", re.I), "QUANTITY_MEMORY", 0.3),
    (re.compile(r"proposta|proposta\s*comercial", re.I), "PROPOSAL", 0.3),
    (re.compile(r"sinapi|sicro|refer[eê]ncia", re.I), "REFERENCE_TABLE", 0.3),
]

_HEADER_SIGNALS: dict[str, list[tuple[re.Pattern[str], float]]] = {
    "BUDGET_ANALYTICAL": [
        (re.compile(r"item|c[oó]digo|descri", re.I), 0.15),
        (re.compile(r"unidade|unid", re.I), 0.15),
        (re.compile(r"quant", re.I), 0.15),
        (re.compile(r"pre[cç]o|valor|unit", re.I), 0.15),
        (re.compile(r"total", re.I), 0.1),
    ],
    "BUDGET_SUMMARY": [
        (re.compile(r"total|subtotal|grupo", re.I), 0.2),
        (re.compile(r"valor", re.I), 0.15),
    ],
    "COMPOSITIONS": [
        (re.compile(r"coef|coeficiente|consumo", re.I), 0.2),
        (re.compile(r"insumo|componente", re.I), 0.2),
        (re.compile(r"composi", re.I), 0.15),
    ],
    "BDI": [
        (re.compile(r"administra|lucro|risco|tribut|seguro|garantia|despesa\s*finance", re.I), 0.25),
        (re.compile(r"%|percent", re.I), 0.1),
        (re.compile(r"bdi", re.I), 0.2),
    ],
    "SOCIAL_CHARGES": [
        (re.compile(r"encargo|inss|fgts|rat|sal[aá]rio", re.I), 0.25),
        (re.compile(r"%|percent|incid", re.I), 0.15),
    ],
    "SCHEDULE": [
        (re.compile(r"m[eê]s|periodo|per[ií]odo|cronograma", re.I), 0.2),
        (re.compile(r"%|percent|valor", re.I), 0.1),
    ],
    "ABC_CURVE": [
        (re.compile(r"classe|participa|acumul", re.I), 0.25),
        (re.compile(r"abc", re.I), 0.2),
    ],
    "PROPOSAL": [
        (re.compile(r"proposta|desconto|lance", re.I), 0.2),
        (re.compile(r"pre[cç]o|valor", re.I), 0.1),
    ],
    "INPUTS": [
        (re.compile(r"insumo|c[oó]digo|pre[cç]o", re.I), 0.2),
        (re.compile(r"unidade", re.I), 0.1),
    ],
}


def _headers_from_cells(cells: list[dict[str, Any]], sheet: str, max_row: int = 5) -> list[str]:
    headers: list[str] = []
    for c in cells:
        if c.get("sheet") != sheet:
            continue
        if c.get("row", 999) > max_row:
            continue
        val = c.get("displayed_value") or c.get("cached_value")
        if isinstance(val, str) and val.strip():
            headers.append(val.strip())
    return headers


def classify_sheet(
    sheet_name: str,
    cells: list[dict[str, Any]],
    *,
    sheet_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    scores: dict[str, float] = {t: 0.0 for t in SHEET_TYPES}
    signals: list[str] = []
    headers = _headers_from_cells(cells, sheet_name)
    header_blob = " | ".join(headers)

    for pattern, stype, weight in _NAME_SIGNALS:
        if pattern.search(sheet_name):
            scores[stype] += weight
            signals.append(f"name:{pattern.pattern}->{stype}+{weight}")

    for stype, patterns in _HEADER_SIGNALS.items():
        for pattern, weight in patterns:
            if pattern.search(header_blob):
                scores[stype] += weight
                signals.append(f"header:{pattern.pattern}->{stype}+{weight}")

    # column presence heuristic: many numeric qty/price columns
    numeric_cells = sum(
        1
        for c in cells
        if c.get("sheet") == sheet_name and c.get("data_type") in {"number", "percent"}
    )
    if numeric_cells >= 20 and scores["BUDGET_ANALYTICAL"] > 0:
        scores["BUDGET_ANALYTICAL"] += 0.1
        signals.append("numeric_density+0.1")

    # Specialized sheet names beat generic budget header overlap
    specialized = (
        "COMPOSITIONS",
        "BDI",
        "SOCIAL_CHARGES",
        "SCHEDULE",
        "ABC_CURVE",
        "INPUTS",
        "PROPOSAL",
    )
    for stype in specialized:
        name_hit = any(
            s.startswith("name:") and f"->{stype}+" in s for s in signals
        )
        if name_hit and scores[stype] >= 0.3:
            scores[stype] += 0.35
            signals.append(f"name_specialization_boost:{stype}+0.35")

    # Prefer specialized sheet types on score ties (dict order would favor BUDGET_*)
    def _rank(item: tuple[str, float]) -> tuple[float, int]:
        stype, score = item
        specialty_bonus = 1 if stype in specialized else 0
        return (score, specialty_bonus)

    best_type, best_score = max(scores.items(), key=_rank)
    if best_score < 0.25:
        best_type = "UNKNOWN"
        confidence = best_score
        needs_review = True
    else:
        confidence = min(1.0, best_score)
        needs_review = confidence < 0.55

    # columns found
    columns_found = headers[:40]

    return {
        "sheet": sheet_name,
        "classification": best_type,
        "confidence": round(confidence, 4),
        "signals": signals,
        "headers": headers[:40],
        "columns_found": columns_found,
        "rule_version": CLASSIFICATION_RULE_VERSION,
        "needs_review": needs_review,
        "scores": {k: round(v, 4) for k, v in scores.items() if v > 0},
        "sheet_state": (sheet_meta or {}).get("state", "visible"),
    }


def classify_workbook(workbook_model: dict[str, Any]) -> list[dict[str, Any]]:
    cells = workbook_model.get("cells") or []
    results = []
    for sheet_meta in workbook_model.get("sheets") or []:
        name = sheet_meta["name"]
        results.append(classify_sheet(name, cells, sheet_meta=sheet_meta))
    return results

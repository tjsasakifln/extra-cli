"""Normalize budget items, compositions, BDI components from classified sheets."""

from __future__ import annotations

import re
from typing import Any

from scripts.budget_audit.units import normalize_unit

_HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "item_number": ("item", "nº", "no", "número", "numero", "ord", "seq"),
    "code": (
        "código do serviço",
        "codigo do servico",
        "código",
        "codigo",
        "cod",
        "code",
        "ref",
        "sinapi",
        "sicro",
    ),
    "description": (
        "descrição do serviço",
        "descricao do servico",
        "descrição do insumo",
        "descricao do insumo",
        "descrição",
        "descricao",
        "discriminacao",
        "discriminação",
        "serviço",
        "servico",
        "desc",
    ),
    "unit": (
        "unidade de medida",
        "unid. medida",
        "unid medida",
        "unidade",
        "unid",
        "un",
        "und",
        "u",
    ),
    "quantity": (
        "quanti dade",
        "quantidade",
        "qtd",
        "quant",
        "qtde",
        "qte",
    ),
    "unit_direct_cost": (
        "custo unitário",
        "custo unitario",
        "custo unit",
        "custo_unit",
        "cd unit",
        "r$/un",
        "rs/un",
        "valor unit sem bdi",
        "valor unitário sem bdi",
        "valor unitario sem bdi",
        "valor unit",  # only if no "com bdi" — scored below
        "valor unitário",
        "valor unitario",
    ),
    "unit_sale_price": (
        "valor unit com bdi",
        "valor unitário com bdi",
        "valor unitario com bdi",
        "preço unit com bdi",
        "preco unit com bdi",
        "pu com bdi",
        "preço unitário",
        "preco unitario",
        "preço unit",
        "preco unit",
        "pu",
        "p.unit",
    ),
    "total_sale_price": (
        "preço total",
        "preco total",
        "valor total",
        "vt",
        "total",
    ),
    "total_direct_cost": (
        "custo total",
        "total custo",
        "cd total",
        "custo total ",
    ),
    # Explicit BDI *percentage* headers only — never "valor unit com bdi"
    "bdi_pct": (
        "bdi %",
        "% bdi",
        "bdi(%)",
        "taxa bdi",
        "bdi (%)",
        "% de bdi",
        "percentual bdi",
    ),
    "unit_material_cost": ("material", "materiais", "mat"),
    "unit_labor_cost": ("mão de obra", "mao de obra", "mo", "labor"),
    "unit_equipment_cost": ("equipamento", "equip", "eq"),
}


def _norm_header(h: str) -> str:
    # collapse whitespace and soft hyphen / nbsp from Excel exports
    text = str(h).replace("\xa0", " ").replace("\u00ad", "")
    return re.sub(r"\s+", " ", text.strip().lower())


def _header_match_score(header: str, alias: str, field: str) -> float:
    """Score a header/alias match. Higher wins. 0 = no match."""
    h = header
    a = alias
    if not h or not a:
        return 0.0
    # Never treat monetary "…com BDI" columns as bdi_pct
    if field == "bdi_pct":
        if any(tok in h for tok in ("valor", "preço", "preco", "custo", "total", "unit")):
            return 0.0
        if h in {"bdi", "bdi %", "% bdi", "bdi(%)", "taxa bdi", "bdi (%)"}:
            return 100.0
        if a == h:
            return 90.0
        if a in h or h.startswith(a):
            return 50.0 + len(a)
        return 0.0
    # Sale with BDI must win over bare "valor unit"
    if field == "unit_sale_price":
        if "com bdi" in h:
            return 200.0 + len(h)
        if a == h:
            return 80.0
        if h.startswith(a) or a in h:
            # avoid bare "valor unit" capturing "valor unit com bdi" for sale
            # when alias is short price synonym
            if "com bdi" in h and "com bdi" not in a:
                return 0.0
            return 40.0 + len(a)
        return 0.0
    if field == "unit_direct_cost":
        if "com bdi" in h:
            return 0.0  # that column is sale with BDI
        if a == h:
            return 90.0
        if h.startswith(a) or a in h:
            return 50.0 + len(a)
        return 0.0
    # generic
    if a == h:
        return 100.0 + len(a)
    if h.startswith(a):
        return 70.0 + len(a)
    if a in h:
        return 40.0 + len(a)
    return 0.0


def map_columns(headers: list[str]) -> dict[str, int | None]:
    """Map logical field -> 0-based column index among header row values.

    Uses scored matching so 'bdi' never steals 'Valor Unit com BDI', and
    'Valor Unit' maps to direct cost while 'Valor Unit com BDI' maps to sale.
    """
    mapping: dict[str, int | None] = {k: None for k in _HEADER_ALIASES}
    normalized = [_norm_header(h) for h in headers]
    used_idx: set[int] = set()

    # Score all field/idx pairs, assign greedily by score
    candidates: list[tuple[float, str, int]] = []
    for field, aliases in _HEADER_ALIASES.items():
        for idx, h in enumerate(normalized):
            best = 0.0
            for alias in aliases:
                best = max(best, _header_match_score(h, alias, field))
            if best > 0:
                candidates.append((best, field, idx))
    candidates.sort(key=lambda t: (-t[0], t[1], t[2]))
    for score, field, idx in candidates:
        if mapping[field] is not None:
            continue
        if idx in used_idx:
            continue
        mapping[field] = idx
        used_idx.add(idx)

    # Post-fix: if both bare "valor unit" and "valor unit com bdi" exist
    norms = list(enumerate(normalized))
    with_bdi = next((i for i, h in norms if "com bdi" in h and "valor" in h), None)
    bare_vu = next(
        (i for i, h in norms if h in {"valor unit", "valor unitário", "valor unitario"} or (
            "valor unit" in h and "com bdi" not in h and "total" not in h
        )),
        None,
    )
    if with_bdi is not None:
        mapping["unit_sale_price"] = with_bdi
        if bare_vu is not None:
            mapping["unit_direct_cost"] = bare_vu
        # clear false bdi_pct if it pointed at sale-with-bdi column
        if mapping.get("bdi_pct") == with_bdi:
            mapping["bdi_pct"] = None
    return mapping


def _to_float(val: Any) -> float | None:
    if val is None:
        return None
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return float(val)
    if isinstance(val, str):
        s = val.strip()
        if not s or s in {"-", "—"}:
            return None
        s = s.replace("R$", "").replace("%", "").strip()
        s = s.replace(".", "").replace(",", ".") if s.count(",") == 1 and s.count(".") > 0 else s
        s = s.replace(",", ".") if "," in s and "." not in s else s
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _sheet_grid(cells: list[dict[str, Any]], sheet: str) -> dict[tuple[int, int], dict[str, Any]]:
    grid: dict[tuple[int, int], dict[str, Any]] = {}
    for c in cells:
        if c.get("sheet") != sheet:
            continue
        grid[(c["row"], c["column"])] = c
    return grid


def _detect_header_row(grid: dict[tuple[int, int], dict[str, Any]]) -> tuple[int, list[str], dict[int, int]]:
    """Return (header_row, headers_list, col_index_to_excel_col)."""
    rows: dict[int, dict[int, Any]] = {}
    for (r, col), cell in grid.items():
        rows.setdefault(r, {})[col] = cell.get("displayed_value") or cell.get("cached_value")

    best_row = 1
    best_score = -1
    best_headers: list[str] = []
    best_cols: dict[int, int] = {}

    for r, cols in sorted(rows.items())[:15]:
        texts = []
        col_map: dict[int, int] = {}
        for i, col in enumerate(sorted(cols.keys())):
            val = cols[col]
            if isinstance(val, str) and val.strip():
                texts.append(val.strip())
                col_map[len(texts) - 1] = col
        if not texts:
            continue
        mapping = map_columns(texts)
        score = sum(1 for v in mapping.values() if v is not None)
        if score > best_score:
            best_score = score
            best_row = r
            best_headers = texts
            best_cols = col_map
    return best_row, best_headers, best_cols


def extract_budget_items(
    document_id: str,
    sheet: str,
    cells: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    grid = _sheet_grid(cells, sheet)
    header_row, headers, idx_to_col = _detect_header_row(grid)
    col_map = map_columns(headers)

    # translate field -> excel column number
    field_cols: dict[str, int | None] = {}
    for field, idx in col_map.items():
        if idx is None:
            field_cols[field] = None
        else:
            field_cols[field] = idx_to_col.get(idx)

    items: list[dict[str, Any]] = []
    max_row = max((r for r, _ in grid.keys()), default=header_row)

    for r in range(header_row + 1, max_row + 1):
        def get(field: str) -> Any:
            col = field_cols.get(field)
            if col is None:
                return None
            cell = grid.get((r, col))
            if not cell:
                return None
            return cell.get("cached_value") if cell.get("cached_value") is not None else cell.get("displayed_value")

        def cell_ref(field: str) -> str | None:
            col = field_cols.get(field)
            if col is None:
                return None
            cell = grid.get((r, col))
            return f"{sheet}!{cell['coordinate']}" if cell else None

        code = get("code")
        desc = get("description")
        qty = _to_float(get("quantity"))
        # skip empty rows
        if code is None and desc is None and qty is None:
            continue
        # skip pure header echoes
        if isinstance(desc, str) and _norm_header(desc) in {_norm_header(h) for h in headers}:
            continue

        unit_raw = get("unit")
        unit_n = normalize_unit(str(unit_raw) if unit_raw is not None else None)
        unit_direct = _to_float(get("unit_direct_cost"))
        unit_sale = _to_float(get("unit_sale_price"))
        total_sale = _to_float(get("total_sale_price"))
        total_direct = _to_float(get("total_direct_cost"))
        bdi_pct = _to_float(get("bdi_pct"))
        # scale: if bdi looks like 0.25 treat as 25% only when number_format percent handled upstream
        # We keep raw; arithmetic layer interprets carefully

        item_id = f"{document_id}:{sheet}:{r}"
        warnings: list[str] = []
        if unit_n.normalized is None and unit_raw is not None:
            warnings.append("UNIT_UNKNOWN")

        source_cells = {f: cell_ref(f) for f in field_cols if cell_ref(f)}

        items.append(
            {
                "item_id": item_id,
                "source_document_id": document_id,
                "sheet": sheet,
                "row": r,
                "item_number": get("item_number"),
                "parent_item_number": None,
                "code": str(code).strip() if code is not None else None,
                "description": str(desc).strip() if desc is not None else None,
                "unit": unit_raw if unit_raw is None or isinstance(unit_raw, str) else str(unit_raw),
                "unit_normalized": unit_n.normalized,
                "unit_normalization": unit_n.to_dict(),
                "quantity": qty,  # None if absent — never zero-fill
                "unit_material_cost": _to_float(get("unit_material_cost")),
                "unit_labor_cost": _to_float(get("unit_labor_cost")),
                "unit_equipment_cost": _to_float(get("unit_equipment_cost")),
                "unit_other_cost": None,
                "unit_direct_cost": unit_direct,
                "bdi_pct": bdi_pct,
                "unit_sale_price": unit_sale,
                "total_direct_cost": total_direct,
                "total_sale_price": total_sale,
                "reference_system": None,
                "reference_month": None,
                "reference_locality": None,
                "reference_regime": None,
                "formula_cells": [
                    cell_ref(f)
                    for f in ("quantity", "unit_sale_price", "total_sale_price")
                    if cell_ref(f)
                ],
                "source_cells": source_cells,
                "normalization_warnings": warnings,
            }
        )

    column_mapping = {
        "sheet": sheet,
        "header_row": header_row,
        "headers": headers,
        "field_columns": field_cols,
        "fields_mapped": {k: v for k, v in field_cols.items() if v is not None},
    }
    return items, column_mapping


def extract_bdi_components(
    document_id: str,
    sheet: str,
    cells: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Extract BDI component rows: name + percentage from BDI sheet.

    Prefer description text (longest non-code label) over item codes like '1.1'.
    Preserve number_format so BDI scale interpretation can distinguish Excel % cells.
    """
    grid = _sheet_grid(cells, sheet)
    rows: dict[int, list[dict[str, Any]]] = {}
    for (r, _c), cell in grid.items():
        rows.setdefault(r, []).append(cell)

    components: list[dict[str, Any]] = []
    for r, cells_in_row in sorted(rows.items()):
        texts: list[tuple[str, dict[str, Any]]] = []
        numbers: list[tuple[float, dict[str, Any]]] = []
        for cell in sorted(cells_in_row, key=lambda x: x["column"]):
            val = cell.get("cached_value")
            if val is None:
                val = cell.get("displayed_value")
            if isinstance(val, str) and val.strip():
                texts.append((val.strip(), cell))
            elif isinstance(val, (int, float)) and not isinstance(val, bool):
                numbers.append((float(val), cell))
        if not texts or not numbers:
            continue

        # Prefer descriptive name over codes like "1.1" / section totals
        def _is_noise_label(t: str) -> bool:
            return bool(
                re.search(
                    r"^(componente|descri[cç][aã]o|item|%|percent|taxa|"
                    r"custos indiretos|impostos|lucro bruto|total|bonifica|"
                    r"f[oó]rmula|composi[cç][aã]o da taxa|munic[ií]pio)",
                    t,
                    re.I,
                )
            )

        def _name_score(pair: tuple[str, dict[str, Any]]) -> tuple[int, int, int]:
            t, cell = pair
            code_like = 1 if re.fullmatch(r"\d+(\.\d+)*", t) else 0
            noise = 1 if _is_noise_label(t) else 0
            # prefer earlier columns (description usually col B after code)
            return (noise, code_like, cell.get("column") or 99)

        name_candidates = sorted(texts, key=_name_score)
        name, name_cell = name_candidates[0]
        if _is_noise_label(name) or re.fullmatch(r"\d+(\.\d+)*", name):
            # try next candidate
            usable = [p for p in name_candidates if not _is_noise_label(p[0]) and not re.fullmatch(r"\d+(\.\d+)*", p[0])]
            if not usable:
                continue
            name, name_cell = usable[0]

        # Component rates: numeric cells not section subtotals alone
        rate_like = [(v, c) for v, c in numbers if abs(v) <= 100]
        if not rate_like:
            continue
        # Prefer General-format rates for components (percent-format often is total BDI row)
        pct, pct_cell = rate_like[0]
        general_rates = [
            (v, c)
            for v, c in rate_like
            if "%" not in str(c.get("number_format") or "")
        ]
        if general_rates:
            pct, pct_cell = general_rates[0]
        # Skip pure total rows where name looks like aggregate
        if re.search(r"^total\b", name, re.I):
            continue
        components.append(
            {
                "component_id": f"{document_id}:{sheet}:{r}",
                "source_document_id": document_id,
                "sheet": sheet,
                "row": r,
                "original_name": name,
                "component_code": next(
                    (t for t, _ in texts if re.fullmatch(r"\d+(\.\d+)*", t)),
                    None,
                ),
                "percentage": pct,
                "number_format": pct_cell.get("number_format"),
                "scale_note": "as_stored",
                "source_cells": {
                    "name": f"{sheet}!{name_cell['coordinate']}",
                    "percentage": f"{sheet}!{pct_cell['coordinate']}",
                },
            }
        )
    return components


def extract_composition_inputs(
    document_id: str,
    sheet: str,
    cells: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Heuristic composition input rows: code, desc, unit, coefficient, unit_price."""
    items, _mapping = extract_budget_items(document_id, sheet, cells)
    # reinterpret quantity as coefficient when sheet is COMPOSITIONS
    out = []
    for it in items:
        out.append(
            {
                "input_id": it["item_id"],
                "source_document_id": document_id,
                "sheet": sheet,
                "row": it["row"],
                "composition_code": None,
                "code": it.get("code"),
                "description": it.get("description"),
                "unit": it.get("unit"),
                "coefficient": it.get("quantity"),
                "unit_price": it.get("unit_sale_price") or it.get("unit_direct_cost"),
                "total": it.get("total_sale_price") or it.get("total_direct_cost"),
                "source_cells": it.get("source_cells"),
                "normalization_warnings": it.get("normalization_warnings") or [],
            }
        )
    return out


def normalize_case(
    document_id: str,
    sheet_classifications: list[dict[str, Any]],
    cells: list[dict[str, Any]],
) -> dict[str, Any]:
    budget_items: list[dict[str, Any]] = []
    compositions: list[dict[str, Any]] = []
    composition_inputs: list[dict[str, Any]] = []
    bdi_components: list[dict[str, Any]] = []
    social_charges: list[dict[str, Any]] = []
    schedule_items: list[dict[str, Any]] = []
    abc_items: list[dict[str, Any]] = []
    column_mappings: list[dict[str, Any]] = []
    units_used: list[dict[str, Any]] = []
    codes: list[dict[str, Any]] = []

    for sc in sheet_classifications:
        sheet = sc["sheet"]
        ctype = sc["classification"]
        if ctype in {"BUDGET_ANALYTICAL", "BUDGET_SUMMARY", "PROPOSAL", "QUANTITY_MEMORY"}:
            items, col_mapping = extract_budget_items(document_id, sheet, cells)
            budget_items.extend(items)
            column_mappings.append(col_mapping)
            for it in items:
                if it.get("unit_normalization"):
                    units_used.append(it["unit_normalization"])
                if it.get("code"):
                    codes.append({"code": it["code"], "sheet": sheet, "row": it["row"]})
        elif ctype == "COMPOSITIONS":
            inputs = extract_composition_inputs(document_id, sheet, cells)
            composition_inputs.extend(inputs)
            compositions.append(
                {
                    "composition_id": f"{document_id}:{sheet}",
                    "source_document_id": document_id,
                    "sheet": sheet,
                    "input_count": len(inputs),
                    "source_cells": {"sheet": sheet},
                }
            )
        elif ctype == "BDI":
            bdi_components.extend(extract_bdi_components(document_id, sheet, cells))
        elif ctype == "SOCIAL_CHARGES":
            # reuse BDI-like extractor for name/% pairs
            social_charges.extend(extract_bdi_components(document_id, sheet, cells))
        elif ctype == "SCHEDULE":
            items, _ = extract_budget_items(document_id, sheet, cells)
            for it in items:
                schedule_items.append(
                    {
                        "schedule_item_id": it["item_id"],
                        "code": it.get("code"),
                        "description": it.get("description"),
                        "total": it.get("total_sale_price"),
                        "sheet": sheet,
                        "row": it["row"],
                        "source_cells": it.get("source_cells"),
                    }
                )
        elif ctype == "ABC_CURVE":
            items, _ = extract_budget_items(document_id, sheet, cells)
            for it in items:
                abc_items.append(
                    {
                        "abc_item_id": it["item_id"],
                        "code": it.get("code"),
                        "description": it.get("description"),
                        "total": it.get("total_sale_price"),
                        "sheet": sheet,
                        "row": it["row"],
                        "source_cells": it.get("source_cells"),
                    }
                )
        elif ctype == "INPUTS":
            inputs = extract_composition_inputs(document_id, sheet, cells)
            composition_inputs.extend(inputs)

    return {
        "budget_items": budget_items,
        "compositions": compositions,
        "composition_inputs": composition_inputs,
        "bdi_components": bdi_components,
        "social_charges": social_charges,
        "schedule_items": schedule_items,
        "abc_items": abc_items,
        "column_mappings": column_mappings,
        "units": units_used,
        "codes": codes,
    }

"""Compose DataLake reads into dossier sections and findings.

Interpretation lives here, and it is deliberately thin: every finding is a fact
plus the question that fact opens. Nothing asserts a right, an imbalance, a
loss, or that an adjustment is due.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from scripts.dossier.constants import (
    ANNIVERSARY_MIN_MONTHS,
    COMPETITOR_LIMIT,
    DATA_HOLD,
    DATA_READY,
    DATA_REJECT,
    EXPIRING_WINDOW_DAYS,
    FINDING_ANNIVERSARY,
    FINDING_BUYER_CONCENTRATION,
    FINDING_EXPIRING_WINDOW,
    FINDING_LONG_HORIZON,
    FINDING_OPPORTUNITY_SAME_BUYER,
    FINDING_PRICE_POSITION,
    HHI_CONCENTRATION_THRESHOLD,
    LOW_PRECISION_CATEGORIES,
    MIN_BUYERS_READY,
    MIN_CONTRACTS_HOLD,
    MIN_CONTRACTS_READY,
    PANEL_OUT_OF_RANGE_FACTOR,
    POSITION_LOW_PRECISION_BUCKET,
    POSITION_OUT_OF_PANEL_RANGE,
    REASON_BUYER_LIST_TRUNCATED,
    REASON_IDENTITY_NOT_FOUND,
    REASON_INSUFFICIENT_BUYERS,
    REASON_INSUFFICIENT_CONTRACTS,
    REASON_LOW_PRECISION_BUCKET,
    REASON_NATIONAL_REFERENCE_HOLD,
    REASON_NO_COMPETITORS,
    REASON_NO_CONTRACTS,
    REASON_NO_EXPIRING,
    REASON_NO_OPPORTUNITIES,
    REASON_NO_PRICE_REFERENCE,
    REASON_PANEL_OUT_OF_RANGE,
    REASON_REFERENCE_SCOPE_UNAVAILABLE,
    REASON_TABLE_MISSING,
    REASON_VALUE_UNKNOWN,
    REFERENCE_SCOPE_BOTH,
    REFERENCE_SCOPE_NATIONAL,
    REFERENCE_SCOPE_REGIONAL,
    SECTION_BUYER_MAP,
    SECTION_COMPETITORS,
    SECTION_EXPIRING,
    SECTION_IDENTITY,
    SECTION_OPPORTUNITIES,
    SECTION_PRICE_PANEL,
    UNKNOWN,
)
from scripts.dossier.models import Finding, Section, SourceRead, money

POSITION_BELOW_P25 = "BELOW_P25"
POSITION_P25_P50 = "P25_P50"
POSITION_P50_P75 = "P50_P75"
POSITION_ABOVE_P75 = "ABOVE_P75"


def _dec(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _iso_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _months_between(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + (end.month - start.month) - (1 if end.day < start.day else 0)


def _missingness(rows: tuple[dict[str, Any], ...], field: str) -> float | None:
    if not rows:
        return None
    unknown = sum(1 for row in rows if _dec(row.get(field)) is None)
    return round(unknown / len(rows), 4)


def _unavailable(section_id: str, read: SourceRead) -> Section:
    return Section(
        section_id=section_id,
        state=DATA_HOLD,
        payload={},
        sources=(read.source,),
        observed_at=read.observed_at,
        row_count=0,
        reason_codes=read.reason_codes or (REASON_TABLE_MISSING,),
    )


def build_identity(read: SourceRead) -> Section:
    if not read.available:
        return _unavailable(SECTION_IDENTITY, read)
    if not read.rows:
        return Section(
            section_id=SECTION_IDENTITY,
            state=DATA_REJECT,
            payload={},
            sources=(read.source,),
            observed_at=read.observed_at,
            row_count=0,
            reason_codes=(REASON_IDENTITY_NOT_FOUND,),
        )
    row = read.rows[0]
    return Section(
        section_id=SECTION_IDENTITY,
        state=DATA_READY,
        payload={
            "cnpj14": row.get("cnpj14"),
            "razao_social": row.get("razao_social"),
            "nome_fantasia": row.get("nome_fantasia") or UNKNOWN,
            "cnae_principal": row.get("cnae_principal") or UNKNOWN,
            "situacao_cadastral": row.get("situacao_cadastral") or UNKNOWN,
            "municipio": row.get("municipio") or UNKNOWN,
            "uf": row.get("uf") or UNKNOWN,
            "registry_source": row.get("source") or UNKNOWN,
            "registry_source_date": row.get("source_date") or UNKNOWN,
        },
        sources=(read.source,),
        observed_at=read.observed_at,
        row_count=1,
    )


def build_buyer_map(buyers: SourceRead, contracts: SourceRead, totals: SourceRead) -> Section:
    """Buyer map. Display rows are capped; every total comes from ``totals``.

    Computing the share, the sum or the HHI over the capped display list would
    report a concentrated portfolio for any supplier with more buyers than the
    cap, and understate the money by the whole tail.
    """
    if not buyers.available or not totals.available:
        return _unavailable(SECTION_BUYER_MAP, buyers if not buyers.available else totals)
    rows = buyers.rows
    if not rows:
        return Section(
            section_id=SECTION_BUYER_MAP,
            state=DATA_REJECT,
            payload={},
            sources=(buyers.source,),
            observed_at=buyers.observed_at,
            row_count=0,
            reason_codes=(REASON_NO_CONTRACTS,),
        )

    total_row = totals.rows[0] if totals.rows else {}
    buyer_total = int(total_row.get("buyer_count") or 0)
    contract_total = int(total_row.get("contract_count") or 0)
    valued_total = _dec(total_row.get("valor_sum_valued"))
    hhi = _dec(total_row.get("hhi"))

    entries: list[dict[str, Any]] = []
    for row in rows:
        valor = _dec(row.get("valor_sum"))
        share = None
        if valor is not None and valued_total is not None and valued_total > 0:
            share = round(float(valor / valued_total), 4)
        entries.append(
            {
                "buyer_cnpj": row.get("buyer_cnpj"),
                "buyer_nome": row.get("buyer_nome") or UNKNOWN,
                "uf": row.get("uf") or UNKNOWN,
                "contract_count": int(row.get("contract_count") or 0),
                "valued_count": int(row.get("valued_count") or 0),
                "valor_sum": money(valor),
                "last_data_fim": row.get("last_data_fim") or UNKNOWN,
                "share_of_valued": share,
            }
        )

    reason_codes: list[str] = []
    if valued_total is None or valued_total <= 0:
        reason_codes.append(REASON_VALUE_UNKNOWN)
    if buyer_total < MIN_BUYERS_READY:
        reason_codes.append(REASON_INSUFFICIENT_BUYERS)
    if contract_total < MIN_CONTRACTS_READY:
        reason_codes.append(REASON_INSUFFICIENT_CONTRACTS)
    if buyer_total > len(entries):
        reason_codes.append(REASON_BUYER_LIST_TRUNCATED)

    state = DATA_READY
    if contract_total < MIN_CONTRACTS_HOLD:
        state = DATA_REJECT
    elif [c for c in reason_codes if c != REASON_BUYER_LIST_TRUNCATED]:
        state = DATA_HOLD

    return Section(
        section_id=SECTION_BUYER_MAP,
        state=state,
        payload={
            "buyer_count": buyer_total,
            "contract_count": contract_total,
            "displayed_buyer_count": len(entries),
            "valor_sum_valued": money(valued_total) if valued_total and valued_total > 0 else None,
            "hhi": None if hhi is None else round(float(hhi), 4),
            "hhi_basis": "valued_contract_value_all_buyers" if hhi is not None else UNKNOWN,
            "buyers": entries,
        },
        sources=(buyers.source,),
        observed_at=buyers.observed_at,
        row_count=len(entries),
        reason_codes=tuple(reason_codes),
        missingness=_missingness(contracts.rows, "valor") if contracts.rows else None,
    )


def build_competitors(read: SourceRead, limit: int = COMPETITOR_LIMIT) -> Section:
    if not read.available:
        return _unavailable(SECTION_COMPETITORS, read)
    rows = read.rows[:limit]
    if not rows:
        return Section(
            section_id=SECTION_COMPETITORS,
            state=DATA_HOLD,
            payload={"competitor_count": 0, "competitors": []},
            sources=(read.source,),
            observed_at=read.observed_at,
            row_count=0,
            reason_codes=(REASON_NO_COMPETITORS,),
        )
    competitors: list[dict[str, Any]] = [
        {
            "supplier_cnpj": row.get("supplier_cnpj"),
            "supplier_nome": row.get("supplier_nome") or UNKNOWN,
            "contract_count": int(row.get("contract_count") or 0),
            "valued_count": int(row.get("valued_count") or 0),
            "valor_sum": money(_dec(row.get("valor_sum"))),
            "shared_buyer_count": int(row.get("shared_buyer_count") or 0),
            "shared_categories": sorted((row.get("shared_categories") or "").split(","))
            if row.get("shared_categories")
            else [],
        }
        for row in rows
    ]
    categories = sorted({c for entry in competitors for c in (entry["shared_categories"] or [])})
    primary_category = categories[0] if len(categories) == 1 else (UNKNOWN if not categories else ",".join(categories))
    return Section(
        section_id=SECTION_COMPETITORS,
        state=DATA_READY if len(competitors) >= 1 else DATA_HOLD,
        payload={
            "competitor_count": len(competitors),
            "requested_limit": limit,
            "primary_category": primary_category,
            "selection_rule": (
                "fornecedores com contratos junto aos mesmos compradores e na categoria "
                "principal de contratos da própria empresa"
            ),
            "competitors": competitors,
        },
        sources=(read.source,),
        observed_at=read.observed_at,
        row_count=len(competitors),
        missingness=_missingness(rows, "valor_sum"),
    )


def _position(focal_median: Decimal, p25: Decimal | None, p50: Decimal | None, p75: Decimal | None) -> str:
    factor = Decimal(PANEL_OUT_OF_RANGE_FACTOR)
    if p75 is not None and p75 > 0 and focal_median > p75 * factor:
        return POSITION_OUT_OF_PANEL_RANGE
    if p25 is not None and p25 > 0 and focal_median * factor < p25:
        return POSITION_OUT_OF_PANEL_RANGE
    if p25 is not None and focal_median < p25:
        return POSITION_BELOW_P25
    if p75 is not None and focal_median > p75:
        return POSITION_ABOVE_P75
    if p50 is not None and focal_median < p50:
        return POSITION_P25_P50
    if p50 is not None:
        return POSITION_P50_P75
    return UNKNOWN


def _reference_metadata(row: dict[str, Any], scope_kind: str) -> dict[str, Any]:
    """Normalize the provenance carried by the scope-aware SQL view."""
    default_geography = (
        {"kind": "radius", "radius_km": 200, "label": "Florianopolis/SC reference base"}
        if scope_kind == REFERENCE_SCOPE_REGIONAL
        else {"kind": "country", "country": "BR"}
    )
    return {
        "scope_id": row.get("scope_id")
        or ("regional:unavailable" if scope_kind == REFERENCE_SCOPE_REGIONAL else "national:unavailable"),
        "scope_kind": scope_kind,
        "reference_state": row.get("reference_state") or DATA_HOLD,
        "geography": row.get("geography") or default_geography,
        "denominator": row.get("denominator")
        or {
            "eligible_contracts": int(row.get("qtd_contratos") or 0) or None,
            "expected_partitions": None,
            "queried_partitions": None,
            "closed_partitions": None,
        },
        "as_of": row.get("as_of") or UNKNOWN,
        "source": {
            "id": row.get("source_id") or "UNKNOWN",
            "version": row.get("source_version") or "UNKNOWN",
        },
        "sample_count": int(row.get("sample_count") or row.get("qtd_contratos") or 0) or None,
        "coverage": row.get("coverage"),
        "missingness": row.get("missingness"),
        "method": row.get("method") or {"status": "UNAVAILABLE"},
        "authority_hash": row.get("reference_hash") or "UNKNOWN",
        "limitations": list(row.get("limitations") or ["Reference authority unavailable."]),
    }


def _panel_hash(panel: dict[str, Any]) -> str:
    stable = {key: value for key, value in panel.items() if key != "hash"}
    payload = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _category_rows(rows: tuple[dict[str, Any], ...]) -> tuple[list[dict[str, Any]], list[str]]:
    categories: list[dict[str, Any]] = []
    reason_codes: list[str] = []
    for row in rows:
        if not row.get("categoria"):
            continue
        categoria = row.get("categoria")
        p25, p50, p75 = _dec(row.get("p25_valor")), _dec(row.get("p50_valor")), _dec(row.get("p75_valor"))
        focal_median = _dec(row.get("focal_median"))
        low_precision = categoria in LOW_PRECISION_CATEGORIES
        categories.append(
            {
                "categoria": categoria,
                "bucket_precision": "LOW" if low_precision else "NORMAL",
                "reference_contract_count": int(row.get("qtd_contratos") or 0),
                "reference_p25": money(p25),
                "reference_p50": money(p50),
                "reference_p75": money(p75),
                "reference_ticket_medio": money(_dec(row.get("ticket_medio"))),
                "focal_contract_count": int(row.get("focal_count") or 0),
                "focal_valued_count": int(row.get("focal_valued_count") or 0),
                "focal_median": money(focal_median),
                "focal_contract_count_in_scope": int(row.get("focal_count") or 0),
                "focal_position": (
                    POSITION_LOW_PRECISION_BUCKET
                    if low_precision
                    else (_position(focal_median, p25, p50, p75) if focal_median is not None else UNKNOWN)
                ),
            }
        )
    comparable = [
        c
        for c in categories
        if c["focal_position"] not in (UNKNOWN, POSITION_OUT_OF_PANEL_RANGE, POSITION_LOW_PRECISION_BUCKET)
    ]
    out_of_range = [c for c in categories if c["focal_position"] == POSITION_OUT_OF_PANEL_RANGE]
    if not comparable:
        reason_codes.append(REASON_NO_PRICE_REFERENCE)
    if out_of_range:
        reason_codes.append(REASON_PANEL_OUT_OF_RANGE)
    if [c for c in categories if c["bucket_precision"] == "LOW"]:
        reason_codes.append(REASON_LOW_PRECISION_BUCKET)
    return categories, reason_codes


def build_price_panel(read: SourceRead, reference_scope: str = REFERENCE_SCOPE_REGIONAL) -> Section:
    if not read.available:
        return _unavailable(SECTION_PRICE_PANEL, read)
    regional_rows = tuple(
        row for row in read.rows if row.get("scope_kind", REFERENCE_SCOPE_REGIONAL) == REFERENCE_SCOPE_REGIONAL
    )
    national_rows = tuple(row for row in read.rows if row.get("scope_kind") == REFERENCE_SCOPE_NATIONAL)
    categories, regional_reasons = _category_rows(regional_rows)
    comparable = [
        c
        for c in categories
        if c["focal_position"] not in (UNKNOWN, POSITION_OUT_OF_PANEL_RANGE, POSITION_LOW_PRECISION_BUCKET)
    ]
    out_of_range = [c for c in categories if c["focal_position"] == POSITION_OUT_OF_PANEL_RANGE]

    regional_meta = _reference_metadata(regional_rows[0] if regional_rows else {}, REFERENCE_SCOPE_REGIONAL)
    if regional_meta["reference_state"] != DATA_READY and REASON_REFERENCE_SCOPE_UNAVAILABLE not in regional_reasons:
        regional_reasons.append(REASON_REFERENCE_SCOPE_UNAVAILABLE)
    regional_panel = {
        **regional_meta,
        "state": DATA_READY if regional_meta["reference_state"] == DATA_READY and comparable else DATA_HOLD,
        "reason_codes": regional_reasons,
        "category_count": len(categories),
        "comparable_category_count": len(comparable),
        "categories": categories,
    }
    national_row = national_rows[0] if national_rows else {}
    national_meta = _reference_metadata(national_row, REFERENCE_SCOPE_NATIONAL)
    national_panel = {
        **national_meta,
        "state": DATA_HOLD,
        "reason_codes": [REASON_NATIONAL_REFERENCE_HOLD],
        "category_count": 0,
        "comparable_category_count": 0,
        "categories": [],
    }
    regional_panel["hash"] = _panel_hash(regional_panel)
    national_panel["hash"] = _panel_hash(national_panel)

    panels = []
    if reference_scope in (REFERENCE_SCOPE_REGIONAL, REFERENCE_SCOPE_BOTH):
        panels.append(regional_panel)
    if reference_scope in (REFERENCE_SCOPE_NATIONAL, REFERENCE_SCOPE_BOTH):
        panels.append(national_panel)
    if not panels:
        panels.append({**national_panel, "reason_codes": [REASON_REFERENCE_SCOPE_UNAVAILABLE]})

    selected_reasons: list[str] = []
    for panel in panels:
        for code in panel["reason_codes"]:
            if code not in selected_reasons:
                selected_reasons.append(code)
    state = DATA_READY if panels and all(panel["state"] == DATA_READY for panel in panels) else DATA_HOLD
    return Section(
        section_id=SECTION_PRICE_PANEL,
        state=state,
        payload={
            "requested_scope": reference_scope,
            "panels": panels,
            "category_count": len(categories),
            "comparable_category_count": len(comparable),
            "out_of_range_category_count": len(out_of_range),
            "out_of_range_factor": PANEL_OUT_OF_RANGE_FACTOR,
            "low_precision_categories": sorted(LOW_PRECISION_CATEGORIES),
            "value_semantic": "valor_integral_nominal",
            "unit": "BRL_TOTAL",
            "reference_scope": "explicit scope panels; inspect panels[].scope_id and panels[].state",
            "categories": categories,
        },
        sources=(read.source,),
        observed_at=read.observed_at,
        row_count=len(read.rows),
        reason_codes=tuple(selected_reasons),
    )


def build_expiring(read: SourceRead, window_days: int = EXPIRING_WINDOW_DAYS) -> Section:
    if not read.available:
        return _unavailable(SECTION_EXPIRING, read)
    rows = read.rows
    if not rows:
        return Section(
            section_id=SECTION_EXPIRING,
            state=DATA_HOLD,
            payload={"window_days": window_days, "contract_count": 0, "contracts": []},
            sources=(read.source,),
            observed_at=read.observed_at,
            row_count=0,
            reason_codes=(REASON_NO_EXPIRING,),
        )
    contracts = [
        {
            "contrato_id": row.get("contrato_id"),
            "orgao_cnpj": row.get("orgao_cnpj"),
            "orgao_nome": row.get("orgao_nome") or UNKNOWN,
            "objeto": row.get("objeto_contrato") or UNKNOWN,
            "valor": money(_dec(row.get("valor_contrato"))),
            "data_inicio": row.get("data_inicio_contrato") or UNKNOWN,
            "data_fim": row.get("data_fim_contrato") or UNKNOWN,
            "dias_ate_fim": int(row["dias_ate_fim"]) if row.get("dias_ate_fim") is not None else None,
            "uf": row.get("uf") or UNKNOWN,
        }
        for row in rows
    ]
    return Section(
        section_id=SECTION_EXPIRING,
        state=DATA_READY,
        payload={"window_days": window_days, "contract_count": len(contracts), "contracts": contracts},
        sources=(read.source,),
        observed_at=read.observed_at,
        row_count=len(contracts),
        missingness=_missingness(rows, "valor_contrato"),
    )


def build_opportunities(read: SourceRead) -> Section:
    if not read.available:
        return _unavailable(SECTION_OPPORTUNITIES, read)
    rows = read.rows
    if not rows:
        return Section(
            section_id=SECTION_OPPORTUNITIES,
            state=DATA_HOLD,
            payload={"opportunity_count": 0, "opportunities": []},
            sources=(read.source,),
            observed_at=read.observed_at,
            row_count=0,
            reason_codes=(REASON_NO_OPPORTUNITIES,),
        )
    opportunities = [
        {
            "bid_id": row.get("bid_id"),
            "pncp_id": row.get("pncp_id") or UNKNOWN,
            "objeto": row.get("objeto") or UNKNOWN,
            "valor_estimado": money(_dec(row.get("valor_estimado"))),
            "modalidade": row.get("modalidade") or UNKNOWN,
            "orgao_cnpj": row.get("orgao_cnpj"),
            "orgao_nome": row.get("orgao_nome") or UNKNOWN,
            "uf": row.get("uf") or UNKNOWN,
            "data_abertura": row.get("data_abertura") or UNKNOWN,
            "data_encerramento": row.get("data_encerramento") or UNKNOWN,
            "link_edital": row.get("link_edital") or UNKNOWN,
        }
        for row in rows
    ]
    return Section(
        section_id=SECTION_OPPORTUNITIES,
        state=DATA_READY,
        payload={
            "opportunity_count": len(opportunities),
            "selection_rule": "open bids published by buyers the focal company already contracts with",
            "opportunities": opportunities,
        },
        sources=(read.source,),
        observed_at=read.observed_at,
        row_count=len(opportunities),
        missingness=_missingness(rows, "valor_estimado"),
    )


def _finding_id(kind: str, subject: str) -> str:
    digest = hashlib.sha256(f"{kind}|{subject}".encode()).hexdigest()[:12]
    return f"{kind}:{digest}"


def build_findings(
    *,
    contracts: SourceRead,
    buyer_map: Section,
    price_panel: Section,
    expiring: Section,
    opportunities: Section,
    as_of: str,
    window_days: int = EXPIRING_WINDOW_DAYS,
) -> tuple[Finding, ...]:
    findings: list[Finding] = []
    as_of_date = _iso_date(as_of)

    if as_of_date is not None:
        for row in contracts.rows:
            start = _iso_date(row.get("data_inicio"))
            end = _iso_date(row.get("data_fim"))
            contrato_id = row.get("contrato_id")
            if start is None or contrato_id is None:
                continue
            running = end is None or end >= as_of_date
            months = _months_between(start, as_of_date)
            if running and months >= ANNIVERSARY_MIN_MONTHS:
                findings.append(
                    Finding(
                        finding_id=_finding_id(FINDING_ANNIVERSARY, contrato_id),
                        subject=contrato_id,
                        fact=(
                            f"Contrato com data de início {start.isoformat()} e "
                            f"{months} meses decorridos até {as_of_date.isoformat()}; "
                            f"data de fim registrada: {end.isoformat() if end else UNKNOWN}."
                        ),
                        question=(
                            "Houve repactuação ou reajuste contratual registrado a cada "
                            "aniversário deste contrato, conforme a cláusula econômica pactuada?"
                        ),
                        evidence_refs=(f"{contracts.source}:{contrato_id}",),
                        metrics={"months_since_start": months, "data_inicio": start.isoformat()},
                    )
                )
            if end is not None and end > as_of_date and (end - as_of_date).days > window_days:
                findings.append(
                    Finding(
                        finding_id=_finding_id(FINDING_LONG_HORIZON, contrato_id),
                        subject=contrato_id,
                        fact=(
                            f"Contrato com data de fim {end.isoformat()}, além da janela de "
                            f"{window_days} dias considerada neste dossiê."
                        ),
                        question="O planejamento de execução cobre o horizonte total do contrato?",
                        evidence_refs=(f"{contracts.source}:{contrato_id}",),
                        metrics={"days_to_end": (end - as_of_date).days},
                    )
                )

    for item in expiring.payload.get("contracts", []):
        contrato_id = item.get("contrato_id")
        if not contrato_id:
            continue
        findings.append(
            Finding(
                finding_id=_finding_id(FINDING_EXPIRING_WINDOW, contrato_id),
                subject=contrato_id,
                fact=(
                    f"Contrato com {item.get('orgao_nome')} encerra em {item.get('data_fim')} "
                    f"({item.get('dias_ate_fim')} dias)."
                ),
                question="Há saldo, aditivo ou prorrogação a tratar antes do encerramento?",
                evidence_refs=(f"{expiring.sources[0]}:{contrato_id}",),
                severity="ATTENTION",
                metrics={"dias_ate_fim": item.get("dias_ate_fim")},
            )
        )

    hhi = buyer_map.payload.get("hhi")
    if isinstance(hhi, (int, float)) and hhi >= HHI_CONCENTRATION_THRESHOLD:
        top = (buyer_map.payload.get("buyers") or [{}])[0]
        findings.append(
            Finding(
                finding_id=_finding_id(FINDING_BUYER_CONCENTRATION, str(buyer_map.payload.get("buyer_count"))),
                subject="carteira",
                fact=(
                    f"HHI de {hhi} sobre o valor contratado conhecido, distribuído entre "
                    f"{buyer_map.payload.get('buyer_count')} compradores; maior comprador: "
                    f"{top.get('buyer_nome', UNKNOWN)}."
                ),
                question="A carteira depende de poucos compradores em grau que a diretoria aceita?",
                evidence_refs=(f"{buyer_map.sources[0]}:hhi",),
                metrics={"hhi": hhi, "threshold": HHI_CONCENTRATION_THRESHOLD},
            )
        )

    for category in price_panel.payload.get("categories", []) if price_panel.state == DATA_READY else []:
        # A panel the focal sits orders of magnitude outside of is not a
        # reference; emitting a position from it would be a claim, not a fact.
        if category.get("focal_position") in (
            None,
            UNKNOWN,
            POSITION_OUT_OF_PANEL_RANGE,
            POSITION_LOW_PRECISION_BUCKET,
        ):
            continue
        findings.append(
            Finding(
                finding_id=_finding_id(FINDING_PRICE_POSITION, str(category.get("categoria"))),
                subject=str(category.get("categoria")),
                fact=(
                    f"Mediana dos contratos da empresa na categoria {category.get('categoria')}: "
                    f"{category.get('focal_median')}; referência p25/p50/p75 do painel: "
                    f"{category.get('reference_p25')}/{category.get('reference_p50')}/{category.get('reference_p75')}."
                ),
                question=(
                    "A posição observada corresponde ao porte de contrato que a empresa "
                    "pretende disputar nesta categoria?"
                ),
                evidence_refs=(f"{price_panel.sources[0]}:{category.get('categoria')}",),
                metrics={
                    "focal_position": category.get("focal_position"),
                    "focal_contract_count": category.get("focal_contract_count"),
                },
            )
        )

    for item in opportunities.payload.get("opportunities", []):
        bid_id = item.get("bid_id")
        if not bid_id:
            continue
        findings.append(
            Finding(
                finding_id=_finding_id(FINDING_OPPORTUNITY_SAME_BUYER, str(bid_id)),
                subject=str(bid_id),
                fact=(
                    f"Edital aberto de {item.get('orgao_nome')}, comprador com contrato já "
                    f"registrado com a empresa; encerramento: {item.get('data_encerramento')}."
                ),
                question="Esta oportunidade entra na fila de disputa?",
                evidence_refs=(f"{opportunities.sources[0]}:{bid_id}",),
                severity="ATTENTION",
                metrics={"data_encerramento": item.get("data_encerramento")},
            )
        )

    order = {
        FINDING_ANNIVERSARY: 0,
        FINDING_EXPIRING_WINDOW: 1,
        FINDING_BUYER_CONCENTRATION: 2,
        FINDING_PRICE_POSITION: 3,
        FINDING_OPPORTUNITY_SAME_BUYER: 4,
        FINDING_LONG_HORIZON: 5,
    }
    return tuple(sorted(findings, key=lambda f: (order.get(f.finding_id.split(":")[0], 99), f.finding_id)))

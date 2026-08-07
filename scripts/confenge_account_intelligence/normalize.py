"""Normalize company/universe JSON into a fact bag for the router."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from scripts.confenge_account_intelligence.models import cnpj14, cnpj_root, digits_only


def _parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    text = str(value).strip()[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any, default: int = 0) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "sim", "y"}


def normalize_record(raw: dict[str, Any], *, as_of: str | None = None) -> dict[str, Any]:
    """Build a normalized bag. Does not invent missing fields."""
    cnpj_raw = raw.get("cnpj14") or raw.get("cnpj") or raw.get("cnpj_root")
    root = cnpj_root(cnpj_raw)
    full = cnpj14(cnpj_raw)
    if full and len(digits_only(cnpj_raw)) == 14:
        full = digits_only(cnpj_raw)

    as_of_value = as_of or raw.get("as_of") or date.today().isoformat()
    as_of_date = _parse_date(as_of_value) or date.today()

    contracts_in = raw.get("contracts") or raw.get("portfolio") or []
    if not isinstance(contracts_in, list):
        contracts_in = []

    contracts: list[dict[str, Any]] = []
    for i, c in enumerate(contracts_in):
        if not isinstance(c, dict):
            continue
        start = _parse_date(c.get("start_date") or c.get("data_inicio") or c.get("signed_at"))
        end = _parse_date(c.get("end_date") or c.get("data_fim") or c.get("vigencia_fim"))
        pub = _parse_date(c.get("publication_date") or c.get("source_date") or c.get("data_publicacao"))
        age_days = None
        if start is not None:
            age_days = (as_of_date - start).days
        elif pub is not None:
            age_days = (as_of_date - pub).days
        addendum_count = _as_int(c.get("addendum_count") or c.get("aditivos_count"), 0)
        has_addendum = _boolish(c.get("has_addendum")) or addendum_count > 0
        has_reajuste = _boolish(c.get("has_reajuste") or c.get("reajuste_executed"))
        reajuste_evidence = c.get("reajuste_evidence")
        if reajuste_evidence in (None, "", [], {}):
            reajuste_evidence = None
        contracts.append(
            {
                "id": str(c.get("id") or c.get("contract_id") or f"contract-{i+1}"),
                "object": c.get("object") or c.get("objeto") or c.get("description"),
                "value_brl": _as_float(c.get("value_brl") or c.get("valor") or c.get("value")),
                "start_date": start.isoformat() if start else None,
                "end_date": end.isoformat() if end else None,
                "publication_date": pub.isoformat() if pub else None,
                "age_days": age_days,
                "uf": c.get("uf"),
                "orgao": c.get("orgao") or c.get("agency") or c.get("orgao_nome"),
                "has_addendum": has_addendum,
                "addendum_count": addendum_count,
                "has_reajuste": has_reajuste,
                "reajuste_evidence": reajuste_evidence,
                "measurement_issues": _boolish(c.get("measurement_issues") or c.get("medicao_contestada")),
                "glosa_signals": _boolish(c.get("glosa_signals") or c.get("has_glosa")),
                "reequilibrio_mention": _boolish(c.get("reequilibrio_mention")),
                "source_url": c.get("source_url") or c.get("url"),
                "source_document": c.get("source_document") or c.get("document"),
                "source_date": c.get("source_date") or (pub.isoformat() if pub else None),
                "source_location": c.get("source_location") or c.get("location"),
            }
        )

    signals_in = raw.get("signals") if isinstance(raw.get("signals"), dict) else {}
    signals = {
        "national_operation": _boolish(signals_in.get("national_operation")),
        "consortium_participation": _boolish(signals_in.get("consortium_participation")),
        "legal_claims_compliance_unit": _boolish(signals_in.get("legal_claims_compliance_unit")),
        "large_team_public_signal": _boolish(signals_in.get("large_team_public_signal")),
        "high_recurrence": _boolish(signals_in.get("high_recurrence")),
        "rapid_growth": _boolish(signals_in.get("rapid_growth")),
        "low_public_formalization": _boolish(signals_in.get("low_public_formalization")),
        "regional_only": _boolish(signals_in.get("regional_only")),
        "concentrated_functions": _boolish(signals_in.get("concentrated_functions")),
    }

    facts_in = raw.get("facts") if isinstance(raw.get("facts"), list) else []
    facts: list[dict[str, Any]] = []
    for i, f in enumerate(facts_in):
        if not isinstance(f, dict):
            continue
        facts.append(
            {
                "id": str(f.get("id") or f"fact-{i+1}"),
                "text": str(f.get("text") or f.get("statement") or ""),
                "epistemic_class": str(f.get("epistemic_class") or "weak_inference"),
                "confidence": float(f.get("confidence") if f.get("confidence") is not None else 0.5),
                "evidence_ids": list(f.get("evidence_ids") or []),
                "provenance": str(f.get("provenance") or "input.facts"),
                "as_of": f.get("as_of") or as_of_value,
            }
        )

    evidence_in = raw.get("evidence") if isinstance(raw.get("evidence"), list) else []
    evidence: list[dict[str, Any]] = []
    for i, e in enumerate(evidence_in):
        if not isinstance(e, dict):
            continue
        evidence.append(
            {
                "id": str(e.get("id") or f"ev-{i+1}"),
                "url": e.get("url"),
                "document": e.get("document") or e.get("title"),
                "date": e.get("date") or e.get("source_date"),
                "location": e.get("location"),
                "source_type": e.get("source_type"),
            }
        )

    # Auto-evidence from contracts when not already listed.
    existing_ids = {e["id"] for e in evidence}
    for c in contracts:
        eid = f"ev-contract-{c['id']}"
        if eid in existing_ids:
            continue
        if not any([c.get("source_url"), c.get("source_document"), c.get("source_date")]):
            # Still register a minimal provenance pointer for confirmed portfolio items.
            pass
        evidence.append(
            {
                "id": eid,
                "url": c.get("source_url"),
                "document": c.get("source_document") or c.get("object"),
                "date": c.get("source_date") or c.get("start_date") or c.get("publication_date"),
                "location": c.get("source_location") or c.get("uf"),
                "source_type": "public_contract",
            }
        )
        existing_ids.add(eid)

    commercial_state = str(raw.get("commercial_state") or raw.get("status") or "NEW").upper()
    human_outcome = raw.get("human_outcome")
    if isinstance(human_outcome, str):
        human_outcome = {"status": human_outcome}
    if human_outcome is not None and not isinstance(human_outcome, dict):
        human_outcome = {"status": str(human_outcome)}

    return {
        "cnpj_root": root,
        "cnpj14": full,
        "razao_social": raw.get("razao_social") or raw.get("company_name") or raw.get("name"),
        "nome_fantasia": raw.get("nome_fantasia") or raw.get("trade_name"),
        "municipio": raw.get("municipio") or raw.get("city"),
        "uf": raw.get("uf") or raw.get("state"),
        "cnae_principal": raw.get("cnae_principal") or raw.get("cnae"),
        "activity_class": raw.get("activity_class"),
        "as_of": as_of_date.isoformat(),
        "commercial_state": commercial_state,
        "human_outcome": human_outcome,
        "contracts": contracts,
        "signals": signals,
        "facts": facts,
        "evidence": evidence,
        "raw_keys": sorted(raw.keys()),
    }

"""Top-10 commercial quality gate (OBJECTIVE §8.1).

Publishable sector alone is not enough: each Top-10 firm must have
official RFB-authority registry resolution and non-null core cadastro.
"""

from __future__ import annotations

from typing import Any

from scripts.commercial_leads.sector_fit import PUBLISHABLE
from scripts.commercial_leads.supplier_registry import is_official_registry_source

# Strong sector classes required for Top-10 (CONFIRMED preferred; STRONG allowed
# only when still in PUBLISHABLE — pipeline already filters to publishable).
REQUIRED_SECTOR = PUBLISHABLE


def _registry_blob(item: dict[str, Any]) -> dict[str, Any]:
    reg = item.get("registry")
    if isinstance(reg, dict):
        return reg
    return {}


def _field(item: dict[str, Any], *keys: str) -> Any:
    reg = _registry_blob(item)
    for k in keys:
        if item.get(k) not in (None, "", "NOT_AVAILABLE", "NOT_COMPUTABLE"):
            return item.get(k)
        if reg.get(k) not in (None, "", "NOT_AVAILABLE", "NOT_COMPUTABLE"):
            return reg.get(k)
    return None


def official_registry_resolved(item: dict[str, Any]) -> bool:
    """True when cadastro is present and lineage is RFB-authority."""
    status = str(
        item.get("registry_resolution_status")
        or _registry_blob(item).get("resolution_status")
        or ""
    ).upper()
    if status in {"RESOLVED_OFFICIAL", "RESOLVED"}:
        # RESOLVED alone is not enough — require official source
        pass
    source = (
        item.get("registry_source")
        or _registry_blob(item).get("source")
        or item.get("source")
    )
    if not is_official_registry_source(source if source is None else str(source)):
        return False
    # Core cadastro must be non-null
    if not _field(item, "cnae_principal"):
        return False
    if not _field(item, "situacao_cadastral"):
        return False
    # Identity surface: at least razao or explicit registry row
    if not (
        item.get("razao_social")
        or _registry_blob(item).get("razao_social")
        or _field(item, "municipio")
    ):
        return False
    return True


def evaluate_top10_gate(leads: list[dict[str, Any]]) -> dict[str, Any]:
    """Evaluate Top-10 technical gate.

    Returns:
        {
          ok: bool,
          issues: list[str],
          out_of_scope_in_top10: int,
          official_registry_failures: int,
          n: int,
        }
    """
    top10 = list(leads[:10])
    ok = True
    issues: list[str] = []
    out_of_scope = 0
    official_failures = 0

    if len(top10) < 10 and len(leads) >= 10:
        ok = False
        issues.append("top10_slice_incomplete")

    for item in top10:
        cnpj = str(item.get("cnpj14") or "")
        if not cnpj or len(cnpj) != 14 or not cnpj.isdigit():
            ok = False
            issues.append("invalid_cnpj_in_top10")
        if str(item.get("commercial_state") or "").upper() == "DO_NOT_CONTACT":
            ok = False
            issues.append("do_not_contact_in_top10")
        if not (item.get("signals_fired") or item.get("signal_ids") or []):
            ok = False
            issues.append("top10_without_fired_signal")
        evidence = (
            item.get("evidence")
            or item.get("evidence_contract_ids_sample")
            or item.get("contracts_sample")
            or []
        )
        if not evidence:
            ok = False
            issues.append("top10_without_evidence")
        sfit = str(item.get("supplier_sector_fit") or "")
        if sfit not in REQUIRED_SECTOR:
            ok = False
            issues.append(f"top10_sector_not_strong:{sfit or 'MISSING'}")
            if sfit == "OUT_OF_SCOPE":
                out_of_scope += 1
        # Prefer CONFIRMED_ENGINEERING for commercial defensibility
        if sfit and sfit != "CONFIRMED_ENGINEERING" and sfit in REQUIRED_SECTOR:
            # STRONG is publishable but still flag for review package transparency
            issues.append(f"top10_sector_not_confirmed:{sfit}")
        cr = item.get("contract_relevance")
        if cr is not None and cr != "PASS":
            ok = False
            issues.append("top10_contract_relevance_fail")
        cs = item.get("commercial_signal_fit")
        if cs is not None and cs != "PASS":
            ok = False
            issues.append("top10_commercial_signal_fail")
        gf = item.get("geography_fit")
        if gf is not None and gf != "PASS":
            ok = False
            issues.append("top10_geography_fail")
        if not official_registry_resolved(item):
            ok = False
            official_failures += 1
            issues.append("top10_official_registry_unresolved")
            if not _field(item, "cnae_principal"):
                issues.append("top10_cnae_missing")
            if not _field(item, "situacao_cadastral"):
                issues.append("top10_situacao_missing")
            src = item.get("registry_source") or _registry_blob(item).get("source")
            if not is_official_registry_source(str(src) if src else None):
                issues.append("top10_registry_source_not_official")

    if out_of_scope:
        ok = False
        issues.append("out_of_scope_in_top10")

    # Dedupe while preserving order
    seen: set[str] = set()
    uniq: list[str] = []
    for iss in issues:
        if iss not in seen:
            seen.add(iss)
            uniq.append(iss)

    return {
        "ok": ok and official_failures == 0 and out_of_scope == 0,
        "issues": uniq,
        "out_of_scope_in_top10": out_of_scope,
        "official_registry_failures": official_failures,
        "all_confirmed_engineering": all(
            str(i.get("supplier_sector_fit") or "") == "CONFIRMED_ENGINEERING" for i in top10
        )
        if top10
        else False,
        "n": len(top10),
    }

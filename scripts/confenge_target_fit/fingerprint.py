"""Deterministic input fingerprint for target-fit recompute skip.

Includes only semantically relevant fields. Timestamps that do not change
classification semantics are excluded so unrelated ingestion clocks do not
force national recomputes.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from scripts.confenge_target_fit.models import CompanyInput


def _digits(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _norm_text(value: Any) -> str:
    if value is None:
        return ""
    s = str(value).strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def _contract_semantic_view(contract: dict[str, Any]) -> dict[str, Any]:
    """Fields that can change target-fit classification."""
    cid = (
        contract.get("contrato_id")
        or contract.get("id")
        or contract.get("numero_controle_pncp")
        or ""
    )
    obj = (
        contract.get("objeto_contrato")
        or contract.get("objeto")
        or contract.get("object")
        or ""
    )
    valor = contract.get("valor_total")
    if valor is None:
        valor = contract.get("valor_global")
    try:
        valor_n = round(float(valor), 2) if valor is not None else None
    except (TypeError, ValueError):
        valor_n = None
    # Status / vigência that can alter evidence quality
    status = _norm_text(contract.get("status") or contract.get("situacao") or "")
    data_fim = str(
        contract.get("data_fim")
        or contract.get("data_fim_vigencia")
        or contract.get("end_date")
        or ""
    )[:10]
    data_ini = str(
        contract.get("data_inicio")
        or contract.get("data_assinatura")
        or contract.get("start_date")
        or ""
    )[:10]
    orgao = _norm_text(
        contract.get("orgao_nome") or contract.get("orgao") or contract.get("agency")
    )
    # Consortium provenance flag when present
    consortium = bool(
        contract.get("is_consortium")
        or contract.get("consorcio")
        or contract.get("consortium")
    )
    # Branch CNPJ14 for lineage (not used alone for promotion)
    cnpj14 = _digits(
        contract.get("fornecedor_cnpj") or contract.get("ni_fornecedor") or ""
    )[:14]
    return {
        "id": str(cid),
        "obj": _norm_text(obj),
        "valor": valor_n,
        "status": status,
        "data_ini": data_ini,
        "data_fim": data_fim,
        "orgao": orgao,
        "consortium": consortium,
        "cnpj14": cnpj14,
    }


def build_fingerprint_payload(
    company: CompanyInput,
    *,
    target_fit_version: str,
) -> dict[str, Any]:
    contracts = [
        _contract_semantic_view(c)
        for c in company.contracts
        if isinstance(c, dict)
    ]
    # Stable sort by contract id then object hash
    contracts.sort(key=lambda c: (c.get("id") or "", c.get("obj") or ""))

    cnaes = sorted(
        {_digits(x) for x in (company.cnaes_secundarios or []) if _digits(x)}
    )
    ce = company.construction_evidence or {}
    # Only stable CE fields that affect classification paths
    ce_view = {
        "sector_fit": _norm_text(ce.get("sector_fit") or company.sector_fit or ""),
        "activity_class": _norm_text(
            ce.get("activity_class") or company.activity_class or ""
        ),
        "relevant_contract_count": int(ce.get("relevant_contract_count") or 0),
        "relevant_ratio": round(float(ce.get("relevant_ratio") or 0.0), 4),
    }
    branch_cnpjs = sorted(
        {
            _digits(value)[:14]
            for value in company.branch_cnpjs
            if len(_digits(value)) >= 14
        }
    )

    return {
        "company_key": company.company_key,
        "cnpj_raiz": _digits(company.cnpj_raiz)[:8],
        "razao": _norm_text(company.razao_social),
        "fantasia": _norm_text(company.nome_fantasia),
        "cnae_principal": _digits(company.cnae_principal),
        "cnaes_sec": cnaes,
        "contracts": contracts,
        "branch_cnpjs": branch_cnpjs,
        "construction_evidence": ce_view,
        "is_consortium_member": bool(company.is_consortium_member),
        "target_fit_version": target_fit_version,
        # Explicitly exclude: ingested_at, computed_at, random run ids
    }


def compute_input_fingerprint(
    company: CompanyInput,
    *,
    target_fit_version: str,
) -> str:
    payload = build_fingerprint_payload(company, target_fit_version=target_fit_version)
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def evidence_ids(evidence: list[dict[str, Any]] | None) -> list[str]:
    ids: list[str] = []
    for e in evidence or []:
        if not isinstance(e, dict):
            continue
        eid = e.get("id")
        if eid is not None:
            ids.append(str(eid))
    return sorted(set(ids))


def changed_evidence_ids(
    old: list[dict[str, Any]] | None,
    new: list[dict[str, Any]] | None,
) -> list[str]:
    a = set(evidence_ids(old))
    b = set(evidence_ids(new))
    return sorted(a.symmetric_difference(b))

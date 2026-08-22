"""Stage adapters: universe → intelligence input; intel/contacts → bridge shape.

Keeps mapping deterministic and epistemic. Does not invent facts or contacts.
"""

from __future__ import annotations

from datetime import date
from typing import Any


def _digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def universe_row_to_intelligence_input(
    row: dict[str, Any],
    *,
    as_of: str | None = None,
) -> dict[str, Any]:
    """Project a universe JSONL row into confenge-account-intelligence input shape."""
    portfolio = row.get("portfolio") if isinstance(row.get("portfolio"), dict) else {}
    recent = portfolio.get("recent_contracts") or []
    if not isinstance(recent, list):
        recent = []

    contracts: list[dict[str, Any]] = []
    for i, c in enumerate(recent):
        if not isinstance(c, dict):
            continue
        obj = str(c.get("objeto") or c.get("object") or c.get("objeto_contrato") or "")
        obj_l = obj.lower()
        # Only surface signals that appear in public object text or explicit fields.
        # Absence of a keyword is NOT proof of absence of the event.
        # Absence of reajuste proof is NOT positive economic evidence.
        # Avoid false positives on negated phrases ("sem aditivo").
        _neg = any(
            p in obj_l for p in ("sem aditiv", "sem glosa", "sem reajuste", "sem reequil", "sem medicao", "sem medição")
        )
        has_addendum = bool(c.get("has_addendum")) or (
            not _neg
            and any(
                tok in obj_l
                for tok in (
                    "termo aditiv",
                    "aditivo de",
                    "aditivos de",
                    "aditivo nº",
                    "aditivo n",
                    "apostilamento",
                    "supressão",
                    "supressao",
                    "acréscimo",
                    "acrescimo de",
                    "prorrogação",
                    "prorrogacao",
                    "alteração qualitativa",
                    "alteracao qualitativa",
                    "alteração quantitativa",
                    "alteracao quantitativa",
                    "extracontratual",
                )
            )
        )
        has_reajuste = bool(c.get("has_reajuste") or c.get("reajuste_executed")) or any(
            tok in obj_l for tok in ("reajuste", "repactua", "apostila de reajuste")
        )
        glosa = bool(c.get("glosa_signals") or c.get("measurement_issues")) or any(
            tok in obj_l
            for tok in (
                "glosa",
                "medição contest",
                "medicao contest",
                "medicao",
                "medição",
                "faturamento",
                "retenção",
                "retencao",
                "liquidação",
                "liquidacao",
            )
        )
        reequilibrio = bool(c.get("reequilibrio_mention")) or any(
            tok in obj_l for tok in ("reequil", "álea", "alea economica", "desequilíbrio", "desequilibrio")
        )
        budget_bdi = bool(c.get("budget_or_bdi_signal") or c.get("planilha_signal")) or any(
            tok in obj_l
            for tok in (
                "bdi",
                "planilha orcament",
                "planilha orçament",
                "composicao de custo",
                "composição de custo",
                "quantitativo",
                "orçamento de obra",
                "orcamento de obra",
            )
        )
        tender = bool(c.get("tender_or_proposal_signal")) or any(
            tok in obj_l
            for tok in (
                "edital",
                "licitacao",
                "licitação",
                "proposta comercial",
                "pregão",
                "pregao",
                "concorrência",
                "concorrencia",
            )
        )
        contracts.append(
            {
                "id": str(c.get("contrato_id") or c.get("id") or f"u-contract-{i + 1}"),
                "object": obj or None,
                "value_brl": c.get("valor_total") or c.get("value_brl"),
                "start_date": c.get("data_inicio") or c.get("start_date"),
                "end_date": c.get("data_fim") or c.get("end_date"),
                "publication_date": c.get("data_publicacao") or c.get("publication_date"),
                "uf": c.get("uf"),
                "orgao": c.get("orgao_nome") or c.get("orgao"),
                "has_addendum": has_addendum,
                "addendum_count": int(c.get("addendum_count") or (1 if has_addendum else 0)),
                "has_reajuste": has_reajuste,
                "glosa_signals": glosa,
                "measurement_issues": glosa,
                "reequilibrio_mention": reequilibrio,
                "budget_or_bdi_signal": budget_bdi,
                "planilha_signal": budget_bdi,
                "tender_or_proposal_signal": tender,
                "source_url": c.get("source_url"),
                "source_document": c.get("source_document") or "pncp",
                "source_date": c.get("data_publicacao") or c.get("source_date"),
            }
        )

    # Derive soft structure signals from observational portfolio stats only.
    ufs = portfolio.get("ufs_atuacao") or []
    if not isinstance(ufs, list):
        ufs = []
    contract_count = int(portfolio.get("contract_count_total") or 0)
    value_total = float(portfolio.get("value_total_brl") or 0.0)
    signals: dict[str, Any] = {
        "national_operation": len(ufs) >= 3,
        "regional_only": len(ufs) <= 1 and contract_count > 0,
        "high_recurrence": contract_count >= 8,
        "large_team_public_signal": value_total >= 50_000_000 and contract_count >= 10,
        "concentrated_functions": contract_count <= 2 and len(ufs) <= 1,
        "low_public_formalization": contract_count <= 1,
    }

    activity_classes = row.get("activity_classes") or []
    activity_class = None
    if isinstance(activity_classes, list) and activity_classes:
        activity_class = str(activity_classes[0])

    commercial_state = "NEW"
    if str(row.get("outreach_eligibility") or "").upper() == "DNC":
        commercial_state = "DO_NOT_CONTACT"

    as_of_value = as_of or row.get("as_of") or date.today().isoformat()
    cnpj = _digits(row.get("cnpj14") or row.get("cnpj") or "")
    ce = row.get("construction_evidence") if isinstance(row.get("construction_evidence"), dict) else {}

    return {
        "cnpj": cnpj,
        "cnpj14": cnpj,
        "cnpj_root": _digits(row.get("cnpj_root") or cnpj[:8]),
        "razao_social": row.get("razao_social"),
        "nome_fantasia": row.get("nome_fantasia"),
        "municipio": row.get("municipio"),
        "uf": row.get("uf"),
        "activity_class": activity_class or ce.get("activity_class"),
        "as_of": as_of_value,
        "commercial_state": commercial_state,
        "signals": signals,
        "contracts": contracts,
        "evidence": [],
        "source_lead_id": row.get("source_lead_id") or f"cnpj:{cnpj}",
        "priority_score": row.get("priority_score"),
        "priority_reason": row.get("priority_reason"),
        "construction_evidence": ce,
        "target_fit_class": ce.get("target_fit_class") or row.get("target_fit_class"),
        "target_fit_evidence": ce.get("target_fit_evidence") or row.get("target_fit_evidence") or [],
        "target_fit_reason_codes": ce.get("target_fit_reason_codes") or row.get("target_fit_reason_codes") or [],
        "target_fit_confidence": ce.get("target_fit_confidence") or row.get("target_fit_confidence"),
        "target_fit_version": ce.get("target_fit_version") or row.get("target_fit_version"),
        "portfolio_stats": {
            "contract_count_total": contract_count,
            "value_total_brl": value_total,
            "ufs_atuacao": ufs,
            "active_contract_count": portfolio.get("active_contract_count"),
            "relevant_contract_count": ce.get("relevant_contract_count"),
            "pass_contract_count": ce.get("relevant_contract_count"),
        },
    }


def intelligence_dossier_to_bridge_row(dossier: dict[str, Any]) -> dict[str, Any]:
    """Normalize confenge-account-intelligence-v1 dossier for warmbly_bridge join."""
    snap = dossier.get("account_snapshot") if isinstance(dossier.get("account_snapshot"), dict) else {}
    cnpj = _digits(snap.get("cnpj14") or dossier.get("cnpj14") or dossier.get("cnpj") or "")
    primary = dossier.get("primary_service") if isinstance(dossier.get("primary_service"), dict) else {}
    why = dossier.get("why_now") if isinstance(dossier.get("why_now"), dict) else {}
    dominant = dossier.get("dominant_state") if isinstance(dossier.get("dominant_state"), dict) else {}

    conf_facts = dossier.get("confirmed_facts") if isinstance(dossier.get("confirmed_facts"), list) else []
    strong = dossier.get("strong_inferences") if isinstance(dossier.get("strong_inferences"), list) else []
    weak = dossier.get("weak_inferences") if isinstance(dossier.get("weak_inferences"), list) else []

    evidence: list[dict[str, Any]] = []
    for i, item in enumerate(conf_facts):
        if not isinstance(item, dict):
            continue
        prov = item.get("provenance")
        if isinstance(prov, dict):
            prov_url = prov.get("url") or prov.get("source_url") or ""
            prov_doc = prov.get("document") or prov.get("source_document") or ""
            prov_date = prov.get("date") or prov.get("source_date") or ""
            prov_loc = prov.get("location") or prov.get("source_location") or ""
        else:
            # Provenance may be a free-text string in intelligence output.
            prov_url = ""
            prov_doc = str(prov) if prov else ""
            prov_date = ""
            prov_loc = ""
        evidence.append(
            {
                "id": str(item.get("id") or f"cf-{cnpj}-{i}"),
                "type": str(item.get("type") or "CONFIRMED_FACT"),
                "title": str(item.get("text") or item.get("title") or "")[:200],
                "url": str(item.get("source_url") or prov_url or ""),
                "document": str(item.get("source_document") or prov_doc or ""),
                "date": str(item.get("source_date") or prov_date or ""),
                "location": str(item.get("source_location") or prov_loc or ""),
                "excerpt": str(item.get("text") or "")[:500],
                "synthesis": str(item.get("text") or "")[:300],
                "epistemic_class": "CONFIRMED_FACT",
                "reliability": "HIGH",
                "consulted_at": str(dossier.get("generated_at") or ""),
            }
        )

    inferences: list[dict[str, Any]] = []
    for label, bucket, eclass in (
        ("si", strong, "STRONG_INFERENCE"),
        ("wi", weak, "WEAK_INFERENCE"),
    ):
        for i, item in enumerate(bucket):
            if not isinstance(item, dict):
                continue
            inferences.append(
                {
                    "id": str(item.get("id") or f"{label}-{cnpj}-{i}"),
                    "type": str(item.get("type") or eclass),
                    "title": str(item.get("text") or item.get("title") or "")[:200],
                    "synthesis": str(item.get("text") or "")[:300],
                    "epistemic_class": eclass,
                    "reliability": "MEDIUM" if eclass == "STRONG_INFERENCE" else "LOW",
                    "consulted_at": str(dossier.get("generated_at") or ""),
                }
            )

    # Prefer dossier contracts; else rebuild from portfolio_summary / input contracts.
    contracts = dossier.get("contracts") if isinstance(dossier.get("contracts"), list) else []
    if not contracts:
        # Intelligence dossier keeps portfolio_summary, not full contracts; carry
        # normalized contracts stashed by the pipeline on the dossier when present.
        contracts = dossier.get("_pipeline_contracts") if isinstance(dossier.get("_pipeline_contracts"), list) else []
    # Bridge feed contracts are opaque JSON objects for Warmbly.
    bridge_contracts: list[dict[str, Any]] = []
    for c in contracts:
        if not isinstance(c, dict):
            continue
        bridge_contracts.append(
            {
                "id": str(c.get("id") or c.get("contrato_id") or ""),
                "object": c.get("object") or c.get("objeto"),
                "value_brl": c.get("value_brl") or c.get("valor_total"),
                "start_date": c.get("start_date"),
                "end_date": c.get("end_date"),
                "publication_date": c.get("publication_date"),
                "agency": c.get("orgao") or c.get("agency"),
                "uf": c.get("uf"),
            }
        )

    commercial_state = str(dominant.get("state") or dossier.get("commercial_state") or "NEW").upper()

    # Map to confenge.service.v1 canonical — never invent REAJUSTE for unknown.
    raw_service = str(primary.get("service_id") or primary.get("service_code") or "")
    canonical_service = raw_service
    warmbly_service = raw_service
    try:
        from scripts.confenge_service_contract.mapping import (
            map_to_canonical,
            map_to_warmbly,
        )

        if raw_service:
            canonical_service = map_to_canonical(raw_service)
            warmbly_service = map_to_warmbly(raw_service)
    except Exception:
        # Fail closed: keep raw id; Warmbly must not default unknown → REAJUSTE.
        canonical_service = raw_service
        warmbly_service = raw_service

    why_summary = str(why.get("temporal_fact") or why.get("summary") or "")
    fact_mention = str(dossier.get("fact_to_mention") or "")
    razao = snap.get("razao_social") or dossier.get("razao_social") or ""
    why_you = str(
        dossier.get("why_this_account")
        or (f"empresa com execução pública de engenharia/construção observável: {razao}" if razao else "")
    )

    return {
        "cnpj14": cnpj,
        "cnpj_root": _digits(snap.get("cnpj_root") or dossier.get("cnpj_root") or cnpj[:8]),
        "razao_social": snap.get("razao_social") or dossier.get("razao_social"),
        "nome_fantasia": snap.get("nome_fantasia") or dossier.get("nome_fantasia"),
        "municipio": snap.get("municipio"),
        "uf": snap.get("uf"),
        "commercial_state": commercial_state,
        "source_lead_id": dossier.get("source_lead_id") or f"cnpj:{cnpj}",
        "target_fit_class": (
            dossier.get("target_fit_class")
            or snap.get("target_fit_class")
            or (
                (dossier.get("construction_evidence") or {}).get("target_fit_class")
                if isinstance(dossier.get("construction_evidence"), dict)
                else None
            )
        ),
        "why_this_account": why_you,
        "why_now": {
            "code": str(why.get("trigger") or why.get("code") or "").upper(),
            "summary": why_summary,
            "observed_at": str(why.get("observed_at") or dossier.get("as_of") or ""),
            "confidence": _confidence_from_epistemic(why.get("epistemic_class")),
            "evidence_ids": [e["id"] for e in evidence if e.get("epistemic_class") == "CONFIRMED_FACT"][:5],
        },
        "offer": {
            "service_code": warmbly_service or raw_service,
            "canonical_service_code": canonical_service or raw_service,
            "extra_cli_service_id": raw_service,
            "service_name": str(primary.get("label") or primary.get("service_name") or ""),
            "entry_offer": str(primary.get("approach_mode") or ""),
            "micro_offer_code": str(dossier.get("micro_offer_code") or primary.get("approach_mode") or ""),
            "rationale": str(dossier.get("service_fit_rationale") or ""),
        },
        "service_candidates": list(dossier.get("service_candidates") or []),
        "messaging": {
            "fact_to_mention": fact_mention,
            "question_to_ask": str(dossier.get("question_to_ask") or ""),
            "cta": str(dossier.get("cta") or ""),
            "claims_to_avoid": list(dossier.get("claims_to_avoid") or []),
            "why_this_account": why_you,
            # why_now also lives in lead.moment; mirror for copy generators that
            # only read messaging_context.
            "why_now": str(why.get("temporal_fact") or why.get("summary") or ""),
            "why_now_code": str(why.get("trigger") or why.get("code") or "").upper(),
        },
        "contracts": bridge_contracts,
        "evidence": evidence,
        "inferences": inferences,
        "primary_service": primary,
        "secondary_service": dossier.get("secondary_service"),
        "internal_structure_hypothesis": dossier.get("internal_structure_hypothesis"),
        "dominant_state": dominant,
        "schema_id": dossier.get("schema_id"),
        "as_of": dossier.get("as_of"),
        "source_hash": dossier.get("source_hash"),
    }


def _confidence_from_epistemic(value: Any) -> str:
    text = str(value or "").lower()
    if text in {"confirmed", "confirmed_fact", "high"}:
        return "HIGH"
    if text in {"strong_inference", "medium"}:
        return "MEDIUM"
    return "LOW"


# Contact verification status: resolution layer → Warmbly wire.
_VERIFICATION_MAP: dict[str, str] = {
    "OBSERVED": "OFFICIAL_SOURCE",
    "OFFICIAL_SOURCE": "OFFICIAL_SOURCE",
    "PUBLIC_DOCUMENT_RECENT": "PUBLIC_DOCUMENT_RECENT",
    "MULTIPLE_PUBLIC_SOURCES": "MULTIPLE_PUBLIC_SOURCES",
    "INSTITUTIONAL_GENERIC": "INSTITUTIONAL_GENERIC",
    "PUBLIC_POSSIBLY_STALE": "PUBLIC_POSSIBLY_STALE",
    "CANDIDATE_UNVERIFIED": "CANDIDATE_UNVERIFIED",
    "SYNTAX_INVALID": "INVALID",
    "NOT_AVAILABLE": "NOT_FOUND",
    "NOT_FOUND": "NOT_FOUND",
    "INVALID": "INVALID",
    "BOUNCED": "BOUNCED",
    "DO_NOT_CONTACT": "DO_NOT_CONTACT",
}


def contact_resolution_to_bridge_row(resolution: dict[str, Any]) -> dict[str, Any]:
    """Normalize confenge-contact-candidates-v1 row for warmbly_bridge join."""
    cnpj = _digits(resolution.get("cnpj14") or resolution.get("cnpj") or "")
    candidates = resolution.get("candidates")
    # Already-bridge-shaped?
    if isinstance(resolution.get("contacts"), list) and not candidates:
        return {
            "cnpj14": cnpj,
            "contacts": resolution["contacts"],
        }

    if not isinstance(candidates, list):
        candidates = []

    recommended_id = resolution.get("recommended_candidate_id")
    contacts: list[dict[str, Any]] = []
    for i, cand in enumerate(candidates):
        if not isinstance(cand, dict):
            continue
        src = cand.get("source") if isinstance(cand.get("source"), dict) else {}
        vs_raw = str(cand.get("verification_status") or "").upper()
        vs = _VERIFICATION_MAP.get(vs_raw, "CANDIDATE_UNVERIFIED" if cand.get("email") else "NOT_FOUND")
        if cand.get("dnc"):
            vs = "DO_NOT_CONTACT"
        if cand.get("bounce"):
            vs = "BOUNCED"
        conf = cand.get("confidence")
        if isinstance(conf, (int, float)):
            if conf >= 0.75:
                conf_s = "HIGH"
            elif conf >= 0.4:
                conf_s = "MEDIUM"
            else:
                conf_s = "LOW"
        else:
            conf_s = str(conf or "MEDIUM")

        is_rec = bool(cand.get("recommended"))
        if recommended_id and cand.get("candidate_id") == recommended_id:
            is_rec = True

        phone = cand.get("phone_e164") or cand.get("phone_raw") or cand.get("phone") or ""
        source_type = str(src.get("source_type") or cand.get("source_type") or "")
        contacts.append(
            {
                "source_contact_id": str(cand.get("candidate_id") or cand.get("source_contact_id") or f"ct-{cnpj}-{i}"),
                "name": str(cand.get("name") or ""),
                "role": str(cand.get("cargo") or cand.get("role") or ""),
                "email": str(cand.get("email") or cand.get("email_display") or ""),
                "phone": str(phone),
                "linkedin_url": str(cand.get("linkedin_public") or cand.get("linkedin_url") or ""),
                "source_url": str(src.get("source_url") or cand.get("source_url") or ""),
                "source": source_type,
                "source_type": source_type,
                "source_document": str(src.get("source_document") or cand.get("source_document") or ""),
                "source_date": str(src.get("source_date") or cand.get("source_date") or ""),
                "observed_at": str(src.get("observed_at") or cand.get("observed_at") or ""),
                "ownership_status": str(cand.get("ownership_status") or ""),
                "provenance": src or None,
                "verification_status": vs,
                "confidence": conf_s,
                "recommended": is_rec,
            }
        )

    return {
        "cnpj14": cnpj,
        "contacts": contacts,
        "official_domain": str(resolution.get("official_domain") or ""),
    }


def universe_row_for_bridge(row: dict[str, Any], *, rank: int) -> dict[str, Any]:
    """Project universe row into bridge universe join fields."""
    cnpj = _digits(row.get("cnpj14") or row.get("cnpj") or "")
    score = row.get("priority_score")
    try:
        score_f = float(score) if score is not None else 0.0
    except (TypeError, ValueError):
        score_f = 0.0

    if score_f >= 70:
        tier = "HIGH"
        conf = "HIGH"
    elif score_f >= 40:
        tier = "MEDIUM"
        conf = "MEDIUM"
    else:
        tier = "LOW"
        conf = "LOW"

    commercial_state = "NEW"
    if str(row.get("outreach_eligibility") or "").upper() == "DNC":
        commercial_state = "DO_NOT_CONTACT"

    construction = row.get("construction_evidence") if isinstance(row.get("construction_evidence"), dict) else {}
    return {
        "cnpj14": cnpj,
        "cnpj_root": _digits(row.get("cnpj_root") or cnpj[:8]),
        "razao_social": row.get("razao_social"),
        "nome_fantasia": row.get("nome_fantasia"),
        "municipio": row.get("municipio"),
        "uf": row.get("uf"),
        "website": row.get("website") or "",
        "rank": rank,
        "score": score_f,
        "tier": tier,
        "priority_confidence": conf,
        "commercial_state": commercial_state,
        "source_lead_id": row.get("source_lead_id") or f"cnpj:{cnpj}",
        "portfolio": row.get("portfolio"),
        "priority_score": score_f,
        "priority_reason": row.get("priority_reason"),
        "outreach_eligibility": row.get("outreach_eligibility"),
        "construction_evidence": construction,
        "target_fit_class": row.get("target_fit_class") or construction.get("target_fit_class"),
        "target_fit_confidence": row.get("target_fit_confidence")
        if row.get("target_fit_confidence") is not None
        else construction.get("target_fit_confidence"),
        "target_fit_version": row.get("target_fit_version") or construction.get("target_fit_version"),
        "target_fit_evidence": row.get("target_fit_evidence") or construction.get("target_fit_evidence") or [],
        "target_fit_reason_codes": row.get("target_fit_reason_codes")
        or construction.get("target_fit_reason_codes")
        or [],
    }

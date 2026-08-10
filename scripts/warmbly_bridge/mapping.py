"""Pure mapping: universe + account-intelligence + contacts → confenge.outreach.v1 leads.

No invention: missing fields stay empty/absent; inferences keep non-CONFIRMED epistemic class.
"""

from __future__ import annotations

import re
from typing import Any

from scripts.confenge_contact_resolution.mailbox_purpose import classify_mailbox_purpose
from scripts.confenge_contact_resolution.send_readiness import (
    classify_target_fit_send_tier,
    evaluate_email_send_ready,
)
from scripts.warmbly_bridge import EPISTEMIC_CLASSES, VERIFICATION_STATUSES
from scripts.warmbly_bridge.constants import DEFAULT_CLAIMS_TO_AVOID, DOMINANT_COMMERCIAL_STATES

_CNPJ_RE = re.compile(r"^\d{14}$")
_CONFIRMED = "CONFIRMED_FACT"
_INFERENCE_TYPES = frozenset(
    {
        "STRUCTURE_INFERENCE",
        "COMMERCIAL_HYPOTHESIS",
        "INFERENCE",
        "HYPOTHESIS",
        "SIGNAL",
    }
)


def digits_only(value: str | None) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def normalize_cnpj14(value: str | None) -> str:
    d = digits_only(value)
    return d if _CNPJ_RE.match(d) else ""


def index_by_cnpj(rows: list[dict[str, Any]], *, label: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        cnpj = normalize_cnpj14(str(row.get("cnpj14") or row.get("cnpj") or ""))
        if not cnpj:
            continue
        # last write wins for duplicates; deterministic later sort is by cnpj
        out[cnpj] = row
    if not out and rows:
        raise ValueError(f"{label}: no rows with valid cnpj14")
    return out


def _as_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _normalize_epistemic(class_value: str | None, *, is_inference: bool) -> str:
    raw = _as_str(class_value).upper()
    if raw in EPISTEMIC_CLASSES:
        if is_inference and raw == _CONFIRMED:
            # Never promote inference to confirmed fact.
            return "WEAK_INFERENCE"
        return raw
    if is_inference:
        return "COMMERCIAL_HYPOTHESIS"
    return "COMMERCIAL_HYPOTHESIS" if not raw else raw if raw in EPISTEMIC_CLASSES else "COMMERCIAL_HYPOTHESIS"


def _map_evidence_item(item: dict[str, Any], *, is_inference: bool, fallback_id: str) -> dict[str, Any]:
    eid = _as_str(item.get("id")) or fallback_id
    etype = _as_str(item.get("type"))
    inferred = is_inference or etype.upper() in _INFERENCE_TYPES or bool(item.get("is_inference"))
    return {
        "id": eid,
        "type": etype,
        "title": _as_str(item.get("title")),
        "url": _as_str(item.get("url")),
        "document": _as_str(item.get("document")),
        "date": _as_str(item.get("date")),
        "location": _as_str(item.get("location")),
        "excerpt": _as_str(item.get("excerpt")),
        "synthesis": _as_str(item.get("synthesis")),
        "epistemic_class": _normalize_epistemic(item.get("epistemic_class"), is_inference=inferred),
        "reliability": _as_str(item.get("reliability") or ("LOW" if inferred else "")),
        "consulted_at": _as_str(item.get("consulted_at")),
    }


def _map_contact_verification_status(raw: str, *, email: str, ownership: str) -> str:
    """Map contact-resolution statuses onto Warmbly wire verification_status set."""
    vs = (raw or "").strip().upper()
    if vs in VERIFICATION_STATUSES:
        return vs
    # Ownership-aware mapping from confenge_contact_resolution enums.
    if vs in {"VERIFIED", "OBSERVED"} or ownership in {"COMPANY_OWNED", "HUMAN_CONFIRMED"}:
        if ownership in {"COMPANY_OWNED", "HUMAN_CONFIRMED"}:
            return "OFFICIAL_SOURCE"
        return "INSTITUTIONAL_GENERIC" if email else "NOT_FOUND"
    if vs in {"REVIEW_REQUIRED"} or ownership == "LIKELY_COMPANY_OWNED":
        return "PUBLIC_POSSIBLY_STALE"
    if vs in {"PATTERN_GUESS", "CANDIDATE_UNVERIFIED", "SYNTAX_INVALID"}:
        return "CANDIDATE_UNVERIFIED" if email else "INVALID"
    if vs in {"NOT_AVAILABLE", ""}:
        return "CANDIDATE_UNVERIFIED" if email else "NOT_FOUND"
    return "CANDIDATE_UNVERIFIED" if email else "NOT_FOUND"


def _map_contact(item: dict[str, Any], *, idx: int, cnpj: str) -> dict[str, Any]:
    email = _as_str(item.get("email"))
    ownership = _as_str(item.get("ownership_status")).upper()
    vs = _map_contact_verification_status(
        _as_str(item.get("verification_status")),
        email=email,
        ownership=ownership,
    )
    enrollable = item.get("enrollable")
    if enrollable is None:
        # Default closed: only explicit COMPANY_OWNED / HUMAN_CONFIRMED are enrollable.
        enrollable = ownership in {"COMPANY_OWNED", "HUMAN_CONFIRMED"}
    else:
        enrollable = bool(enrollable)
    # Never mark pattern-guess / third-party as recommended for auto-send.
    recommended = bool(item.get("recommended", False))
    if not enrollable:
        recommended = False
    prov = item.get("provenance")
    if not isinstance(prov, dict):
        prov = {
            "source_type": _as_str(item.get("source_type")),
            "source_url": _as_str(item.get("source_url")),
            "source_document": _as_str(item.get("source_document")),
            "source_date": _as_str(item.get("source_date")),
        }
    out = {
        "source_contact_id": _as_str(item.get("source_contact_id")) or f"ct-{cnpj}-{idx}",
        "name": _as_str(item.get("name")),
        "role": _as_str(item.get("role") or item.get("role_class")),
        "role_class": _as_str(item.get("role_class") or item.get("role")),
        "email": email,
        "phone": _as_str(item.get("phone")),
        "linkedin_url": _as_str(item.get("linkedin_url")),
        "source_url": _as_str(item.get("source_url") or prov.get("source_url")),
        "source_document": _as_str(item.get("source_document") or prov.get("source_document")),
        "source_date": _as_str(item.get("source_date") or prov.get("source_date")),
        "verification_status": vs,
        "ownership_status": ownership,
        "ownership_reason": _as_str(item.get("ownership_reason")),
        "verification_reason": _as_str(item.get("verification_reason")),
        "third_party_type": _as_str(item.get("third_party_type")),
        "confidence": _as_str(item.get("confidence")),
        "enrollable": enrollable,
        "recommended": recommended,
        "provenance": prov,
    }
    # mailbox_purpose is independent of person role / ownership
    mp = classify_mailbox_purpose(email or None)
    out["mailbox_purpose"] = mp.purpose
    out["mailbox_purpose_send_blocked"] = mp.send_blocked
    if item.get("recipient_commercial_suitability"):
        out["recipient_commercial_suitability"] = _as_str(item.get("recipient_commercial_suitability"))
    if item.get("channel_send_eligibility") is not None:
        out["channel_send_eligibility"] = bool(item.get("channel_send_eligibility"))
    if item.get("email_send_ready") is not None:
        out["email_send_ready"] = bool(item.get("email_send_ready"))
    return out


def _map_moment(intel: dict[str, Any]) -> dict[str, Any]:
    why = intel.get("why_now") or intel.get("moment") or {}
    if not isinstance(why, dict):
        why = {}
    evidence_ids = why.get("evidence_ids")
    if not isinstance(evidence_ids, list):
        evidence_ids = []
    return {
        "code": _as_str(why.get("code")),
        "summary": _as_str(why.get("summary")),
        "observed_at": _as_str(why.get("observed_at")),
        "confidence": _as_str(why.get("confidence")),
        "evidence_ids": [str(x) for x in evidence_ids],
    }


def _map_offer(intel: dict[str, Any]) -> dict[str, Any]:
    offer = intel.get("offer") or {}
    if not isinstance(offer, dict):
        offer = {}
    # confenge.service.v1: service_code is Warmbly playbook; preserve ontology ids.
    return {
        "service_code": _as_str(offer.get("service_code") or offer.get("id")),
        "canonical_service_code": _as_str(
            offer.get("canonical_service_code") or offer.get("service_code") or offer.get("id")
        ),
        "extra_cli_service_id": _as_str(offer.get("extra_cli_service_id")),
        "service_name": _as_str(offer.get("service_name") or offer.get("label")),
        "entry_offer": _as_str(offer.get("entry_offer")),
        "micro_offer_code": _as_str(offer.get("micro_offer_code")),
        "rationale": _as_str(offer.get("rationale")),
    }


def _map_messaging(intel: dict[str, Any]) -> dict[str, Any]:
    msg = intel.get("messaging") or intel.get("messaging_context") or {}
    if not isinstance(msg, dict):
        msg = {}
    claims = msg.get("claims_to_avoid")
    if not isinstance(claims, list):
        claims = list(DEFAULT_CLAIMS_TO_AVOID)
    else:
        claims = [str(c) for c in claims]
        for default in DEFAULT_CLAIMS_TO_AVOID:
            if default not in claims:
                claims.append(default)
    out = {
        "fact_to_mention": _as_str(msg.get("fact_to_mention")),
        "question_to_ask": _as_str(msg.get("question_to_ask")),
        "cta": _as_str(msg.get("cta")),
        "claims_to_avoid": claims,
    }
    # Optional copy-audit fields (Warmbly ignores unknown extras in JSON).
    why = _as_str(msg.get("why_now") or msg.get("why_now_summary"))
    why_code = _as_str(msg.get("why_now_code"))
    if why:
        out["why_now"] = why
    if why_code:
        out["why_now_code"] = why_code
    return out


def map_lead(
    universe_row: dict[str, Any],
    *,
    intel: dict[str, Any] | None,
    contacts_row: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Map one universe row + optional intel/contacts into a feed lead.

    Returns None only when CNPJ is invalid (caller should skip).
    Missing intel still produces a lead with empty moment/offer/messaging —
    but export CLI requires all three input *files* to exist; empty fields are
    allowed only when the joined record lacks data for that CNPJ.
    """
    cnpj = normalize_cnpj14(str(universe_row.get("cnpj14") or universe_row.get("cnpj") or ""))
    if not cnpj:
        return None
    intel = intel or {}
    contacts_row = contacts_row or {}

    razao = _as_str(universe_row.get("razao_social") or universe_row.get("legal_name"))
    fantasia = _as_str(universe_row.get("nome_fantasia") or universe_row.get("trade_name"))
    commercial_state = _as_str(universe_row.get("commercial_state") or "NEW").upper() or "NEW"
    # Preserve dominant human states from intel override if present.
    intel_state = _as_str(intel.get("commercial_state")).upper()
    if intel_state in DOMINANT_COMMERCIAL_STATES:
        commercial_state = intel_state
    elif commercial_state not in DOMINANT_COMMERCIAL_STATES and intel_state:
        # Non-dominant intel state may enrich only when universe is still NEW-like.
        if commercial_state in {"", "NEW"}:
            commercial_state = intel_state

    evidence_items: list[dict[str, Any]] = []
    raw_evidence = intel.get("evidence") or []
    if isinstance(raw_evidence, list):
        for i, item in enumerate(raw_evidence):
            if isinstance(item, dict):
                evidence_items.append(_map_evidence_item(item, is_inference=False, fallback_id=f"ev-{cnpj}-{i}"))
    raw_inf = intel.get("inferences") or []
    if isinstance(raw_inf, list):
        for i, item in enumerate(raw_inf):
            if isinstance(item, dict):
                evidence_items.append(
                    _map_evidence_item(
                        item,
                        is_inference=True,
                        fallback_id=f"inf-{cnpj}-{i}",
                    )
                )

    moment = _map_moment(intel)
    if not moment["evidence_ids"]:
        moment["evidence_ids"] = [e["id"] for e in evidence_items if e.get("epistemic_class") == _CONFIRMED][:5]

    contact_list_raw = contacts_row.get("contacts")
    if contact_list_raw is None:
        # Accept confenge_contact_resolution resolution rows (candidates key).
        contact_list_raw = contacts_row.get("candidates")
    if contact_list_raw is None and "email" in contacts_row:
        contact_list_raw = [contacts_row]
    if not isinstance(contact_list_raw, list):
        contact_list_raw = []
    # Normalize resolution candidates → map_contact fields
    normalized: list[dict[str, Any]] = []
    for raw_c in contact_list_raw:
        if not isinstance(raw_c, dict):
            continue
        if "email" in raw_c or "phone" in raw_c or "value" in raw_c:
            if raw_c.get("value") and not raw_c.get("email") and "@" in str(raw_c.get("value")):
                raw_c = {**raw_c, "email": raw_c["value"]}
            elif raw_c.get("value") and not raw_c.get("phone"):
                raw_c = {**raw_c, "phone": raw_c.get("phone_e164") or raw_c["value"]}
            if raw_c.get("phone_e164") and not raw_c.get("phone"):
                raw_c = {**raw_c, "phone": raw_c["phone_e164"]}
            if raw_c.get("cargo") and not raw_c.get("role"):
                raw_c = {**raw_c, "role": raw_c["cargo"]}
            normalized.append(raw_c)
    contacts = [_map_contact(c, idx=i, cnpj=cnpj) for i, c in enumerate(normalized) if isinstance(c, dict)]

    contracts = intel.get("contracts") or universe_row.get("contracts") or []
    if not isinstance(contracts, list):
        contracts = []

    source_lead_id = _as_str(universe_row.get("source_lead_id") or intel.get("source_lead_id") or f"cnpj:{cnpj}")

    rank = universe_row.get("rank")
    try:
        rank_i = int(rank) if rank is not None else 0
    except (TypeError, ValueError):
        rank_i = 0
    score = universe_row.get("score")
    try:
        score_f = float(score) if score is not None else 0.0
    except (TypeError, ValueError):
        score_f = 0.0

    lead: dict[str, Any] = {
        "source_lead_id": source_lead_id,
        "company": {
            "cnpj14": cnpj,
            "cnpj_root": cnpj[:8],
            "razao_social": razao,
            "nome_fantasia": fantasia,
            "municipio": _as_str(universe_row.get("municipio") or universe_row.get("city")),
            "uf": _as_str(universe_row.get("uf") or universe_row.get("state")).upper(),
            "website": _as_str(universe_row.get("website") or universe_row.get("site")),
        },
        "priority": {
            "rank": rank_i,
            "score": score_f,
            "tier": _as_str(universe_row.get("tier")),
            "confidence": _as_str(universe_row.get("priority_confidence") or universe_row.get("confidence")),
        },
        "moment": moment,
        "offer": _map_offer(intel),
        "messaging_context": _map_messaging(intel),
        "contacts": contacts,
        "contracts": contracts,
        "evidence": evidence_items,
        "commercial_state": commercial_state,
    }
    # Optional additive activation block (backward-compatible; absent in legacy feeds)
    act = universe_row.get("activation") or intel.get("activation")
    if isinstance(act, dict) and act.get("state"):
        lead["activation"] = _map_activation(act)

    # target_fit_send_tier + EMAIL_SEND_READY (explicit; Warmbly must not re-score)
    msg_ctx = lead["messaging_context"] if isinstance(lead.get("messaging_context"), dict) else {}
    intel_msg = intel.get("messaging") if isinstance(intel.get("messaging"), dict) else {}
    # Prefer structured primary_service / service_candidates from intel (signals+evidence).
    primary_svc = intel.get("primary_service")
    if not isinstance(primary_svc, dict):
        primary_svc = {
            "service_id": lead["offer"].get("service_code") or lead["offer"].get("extra_cli_service_id"),
            "service_code": lead["offer"].get("service_code"),
            "supporting_signal_ids": intel.get("supporting_signal_ids")
            or intel.get("service_supporting_signal_ids")
            or [],
            "evidence_ids": moment.get("evidence_ids") or [],
        }
    service_candidates = intel.get("service_candidates")
    if not isinstance(service_candidates, list):
        service_candidates = [primary_svc] if primary_svc.get("service_id") or primary_svc.get("service_code") else []
    company_ctx = {
        **universe_row,
        **{k: v for k, v in intel.items() if k not in {"contacts", "candidates", "evidence", "inferences"}},
        "service_code": lead["offer"].get("service_code")
        or lead["offer"].get("extra_cli_service_id")
        or (primary_svc.get("service_id") if isinstance(primary_svc, dict) else None),
        "primary_service": primary_svc,
        "service_candidates": service_candidates,
        "factual_hook": msg_ctx.get("fact_to_mention")
        or intel.get("factual_hook")
        or intel.get("observed_fact")
        or intel_msg.get("fact_to_mention"),
        "observed_fact": intel.get("observed_fact")
        or msg_ctx.get("fact_to_mention")
        or intel_msg.get("fact_to_mention"),
        "why_this_account": intel.get("why_this_account")
        or intel_msg.get("why_this_account")
        or msg_ctx.get("why_this_account"),
        "why_now": intel.get("why_now")
        or intel_msg.get("why_now")
        or msg_ctx.get("why_now")
        or moment.get("summary"),
        "micro_offer_code": lead["offer"].get("micro_offer_code")
        or lead["offer"].get("entry_offer")
        or intel.get("micro_offer_code"),
        "cta": msg_ctx.get("cta") or intel_msg.get("cta") or intel.get("cta") or msg_ctx.get("question_to_ask"),
        "evidence_ids": moment.get("evidence_ids")
        or intel.get("evidence_ids")
        or [e.get("id") for e in evidence_items if isinstance(e, dict)],
        "canonical_universe_member": universe_row.get("canonical_universe_member", True),
        "construction_evidence": universe_row.get("construction_evidence")
        or intel.get("construction_evidence")
        or {},
        "portfolio": universe_row.get("portfolio")
        if isinstance(universe_row.get("portfolio"), dict)
        else (intel.get("portfolio") if isinstance(intel.get("portfolio"), dict) else {}),
        "offer": lead["offer"],
        "messaging": {**intel_msg, **msg_ctx},
    }
    fit = classify_target_fit_send_tier(company_ctx)
    lead["target_fit_send_tier"] = fit.tier
    lead["target_fit_reasons"] = list(fit.reasons)

    # Pick best email contact for company-level email_send_ready
    best_ready = False
    best_purpose = ""
    best_suitability = ""
    best_own = ""
    best_ver = ""
    for c in contacts:
        email = c.get("email") or ""
        if not email:
            continue
        # Fail-closed recompute: sticky VERIFIED/COMPANY_OWNED never bypass provenance taint.
        contact_for_prov = dict(c)
        if universe_row.get("official_domain"):
            contact_for_prov.setdefault("official_domain", universe_row.get("official_domain"))
        r = evaluate_email_send_ready(
            company=company_ctx,
            email=email,
            ownership_status=c.get("ownership_status"),
            verification_status=c.get("verification_status"),
            dnc=bool(c.get("dnc") or commercial_state in {"DO_NOT_CONTACT", "DNC"}),
            bounce=bool(c.get("bounce") or c.get("bounced")),
            account_blocked=commercial_state in {"BLOCKED", "LOST"},
            service_code=lead["offer"].get("service_code"),
            factual_evidence=bool(lead["messaging_context"].get("fact_to_mention") or evidence_items),
            evidence_ids=[str(x) for x in (moment.get("evidence_ids") or [])],
            target_fit=fit,
            contact=contact_for_prov,
        )
        c["mailbox_purpose"] = r.mailbox_purpose
        c["email_send_ready"] = r.email_send_ready
        c["recipient_commercial_suitability"] = r.recipient_commercial_suitability
        c["channel_send_eligibility"] = r.channel_send_eligibility
        c["provenance_chain_valid"] = r.provenance_chain_valid
        c["provenance_trust"] = r.provenance_trust
        c["root_source_type"] = r.root_source_type
        c["derived_from_fixture"] = r.derived_from_fixture
        # EMAIL_ONLY: enrollable for auto send queue means email_send_ready, not phone
        if r.email_send_ready:
            c["enrollable"] = True
            c["recommended"] = True
            best_ready = True
            best_purpose = r.mailbox_purpose
            best_suitability = r.recipient_commercial_suitability
            best_own = r.ownership_status
            best_ver = r.verification_status
        elif c.get("enrollable") and not email:
            # phone-only must never be enrollable for EMAIL_ONLY production feed
            c["enrollable"] = False
            c["recommended"] = False
        elif not r.email_send_ready and email:
            # Keep ownership enrollable flag for review queues but mark not email-send-ready
            c["email_send_ready"] = False
            # Tainted provenance must never remain enrollable for commercial send queues.
            if not r.provenance_chain_valid:
                c["enrollable"] = False
                c["recommended"] = False

    lead["email_send_ready"] = best_ready
    if best_purpose:
        lead["mailbox_purpose"] = best_purpose
    if best_suitability:
        lead["recipient_commercial_suitability"] = best_suitability
    if best_own:
        lead["ownership_status"] = best_own
    if best_ver:
        lead["verification_status"] = best_ver
    lead["service_code"] = lead["offer"].get("service_code")
    if isinstance(act, dict):
        lead["activation_state"] = act.get("state") or act.get("activation_state")
        lead["activation_score"] = act.get("score", act.get("activation_score"))
        lead["activation_reasons"] = act.get("reason_codes") or act.get("reasons") or []
        lead["next_best_action_at"] = act.get("next_best_action_at")
    return lead


def _map_activation(act: dict[str, Any]) -> dict[str, Any]:
    """Map activation planner projection into confenge.outreach.v1 lead.activation."""
    score_raw = act.get("score", act.get("activation_score", 0))
    try:
        score_f = float(score_raw)
    except (TypeError, ValueError):
        score_f = 0.0
    score_f = max(0.0, min(100.0, score_f))
    reasons = act.get("reason_codes") or act.get("reasons") or []
    if not isinstance(reasons, list):
        reasons = []
    components = act.get("score_components") or {}
    if not isinstance(components, dict):
        components = {}
    state = _as_str(act.get("state") or act.get("activation_state")).upper()
    out: dict[str, Any] = {
        "state": state,
        "score": round(score_f, 4),
        "reason_codes": [str(r) for r in reasons],
        "policy_version": _as_str(act.get("policy_version") or "confenge-activation-v1"),
        "evaluated_at": _as_str(act.get("evaluated_at")),
        "next_best_action_at": _as_str(act.get("next_best_action_at")) or None,
        "expires_at": _as_str(act.get("expires_at")) or None,
        "source_hash": _as_str(act.get("source_hash")),
        "score_components": {
            "trigger_strength": float(components.get("trigger_strength") or 0),
            "freshness": float(components.get("freshness") or 0),
            "evidence_quality": float(components.get("evidence_quality") or 0),
            "commercial_relevance": float(components.get("commercial_relevance") or 0),
        },
    }
    # Drop null optional timestamps for cleaner JSON (validators accept either)
    if not out["next_best_action_at"]:
        out["next_best_action_at"] = None
    if not out["expires_at"]:
        out["expires_at"] = None
    return out


def build_leads(
    universe_rows: list[dict[str, Any]],
    intel_rows: list[dict[str, Any]],
    contact_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Join inputs by cnpj14 and return stably sorted leads."""
    intel_by = index_by_cnpj(intel_rows, label="account-intelligence") if intel_rows else {}
    contacts_by = index_by_cnpj(contact_rows, label="contacts") if contact_rows else {}
    leads: list[dict[str, Any]] = []
    for row in universe_rows:
        cnpj = normalize_cnpj14(str(row.get("cnpj14") or row.get("cnpj") or ""))
        if not cnpj:
            continue
        lead = map_lead(row, intel=intel_by.get(cnpj), contacts_row=contacts_by.get(cnpj))
        if lead is not None:
            leads.append(lead)
    leads.sort(key=lambda lead: (lead["company"]["cnpj14"], lead["source_lead_id"]))
    return leads

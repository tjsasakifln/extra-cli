"""Pure mapping: universe + account-intelligence + contacts → confenge.outreach.v1 leads.

No invention: missing fields stay empty/absent; inferences keep non-CONFIRMED epistemic class.
"""

from __future__ import annotations

import re
from typing import Any

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


def _map_contact(item: dict[str, Any], *, idx: int, cnpj: str) -> dict[str, Any]:
    email = _as_str(item.get("email"))
    vs = _as_str(item.get("verification_status")).upper()
    if vs and vs not in VERIFICATION_STATUSES:
        vs = "CANDIDATE_UNVERIFIED" if email else "NOT_FOUND"
    if not vs:
        vs = "CANDIDATE_UNVERIFIED" if email else "NOT_FOUND"
    return {
        "source_contact_id": _as_str(item.get("source_contact_id")) or f"ct-{cnpj}-{idx}",
        "name": _as_str(item.get("name")),
        "role": _as_str(item.get("role")),
        "email": email,
        "phone": _as_str(item.get("phone")),
        "linkedin_url": _as_str(item.get("linkedin_url")),
        "source_url": _as_str(item.get("source_url")),
        "source_document": _as_str(item.get("source_document")),
        "source_date": _as_str(item.get("source_date")),
        "verification_status": vs,
        "confidence": _as_str(item.get("confidence")),
        "recommended": bool(item.get("recommended", False)),
    }


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
    return {
        "service_code": _as_str(offer.get("service_code") or offer.get("id")),
        "service_name": _as_str(offer.get("service_name") or offer.get("label")),
        "entry_offer": _as_str(offer.get("entry_offer")),
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
                evidence_items.append(
                    _map_evidence_item(item, is_inference=False, fallback_id=f"ev-{cnpj}-{i}")
                )
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
        moment["evidence_ids"] = [
            e["id"] for e in evidence_items if e.get("epistemic_class") == _CONFIRMED
        ][:5]

    contact_list_raw = contacts_row.get("contacts")
    if contact_list_raw is None and "email" in contacts_row:
        contact_list_raw = [contacts_row]
    if not isinstance(contact_list_raw, list):
        contact_list_raw = []
    contacts = [
        _map_contact(c, idx=i, cnpj=cnpj)
        for i, c in enumerate(contact_list_raw)
        if isinstance(c, dict)
    ]

    contracts = intel.get("contracts") or universe_row.get("contracts") or []
    if not isinstance(contracts, list):
        contracts = []

    source_lead_id = _as_str(
        universe_row.get("source_lead_id") or intel.get("source_lead_id") or f"cnpj:{cnpj}"
    )

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

    return {
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
            "confidence": _as_str(
                universe_row.get("priority_confidence") or universe_row.get("confidence")
            ),
        },
        "moment": moment,
        "offer": _map_offer(intel),
        "messaging_context": _map_messaging(intel),
        "contacts": contacts,
        "contracts": contracts,
        "evidence": evidence_items,
        "commercial_state": commercial_state,
    }


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

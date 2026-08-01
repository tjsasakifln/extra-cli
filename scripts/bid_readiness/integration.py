"""Canonical integration: bid_readiness consumes edital_case + technical_acervo.

This module is the **only** place bid_readiness should pull technical matching
from EXTRA acervo and structured edital requirements. It must not invent a
second acervo store.

Versioned contracts (v1):
- edital_requirement
- technical_acervo_evidence
- bid_document_evidence
- readiness_finding
- human_decision

Forbidden package states: READY_TO_SUBMIT, HABILITADA, PROPOSTA_APROVADA.
Allowed terminal: READY_FOR_HUMAN_REVIEW | NOT_READY | BLOCKED_*.
"""

from __future__ import annotations

from typing import Any

from scripts.bid_readiness.models import MatchStatus, TechnicalMatch

# Contract schema version for integrated findings
INTEGRATION_CONTRACT_VERSION = "1.0.0"

ALLOWED_PACKAGE_STATES = frozenset(
    {
        "READY_FOR_HUMAN_REVIEW",
        "NOT_READY",
        "BLOCKED_BY_MISSING_DOCUMENT",
        "BLOCKED_BY_EXPIRED_DOCUMENT",
        "BLOCKED_BY_INCONSISTENCY",
        "BLOCKED_BY_TECHNICAL_QUALIFICATION",
        "BLOCKED_BY_HUMAN_DECISION",
    }
)

FORBIDDEN_PACKAGE_STATES = frozenset(
    {
        "READY_TO_SUBMIT",
        "HABILITADA",
        "PROPOSTA_APROVADA",
        "PROPOSTA APROVADA",
    }
)


def _locator(
    *,
    document_id: str | None = None,
    document_hash: str | None = None,
    page: int | None = None,
    item: str | None = None,
    cell: str | None = None,
    sheet: str | None = None,
) -> dict[str, Any]:
    return {
        "document_id": document_id,
        "document_hash": document_hash,
        "page": page,
        "item": item,
        "cell": cell,
        "sheet": sheet,
    }


def edital_requirement_from_dict(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize an edital/tech requirement into the versioned contract."""
    return {
        "contract": "edital_requirement",
        "contract_version": INTEGRATION_CONTRACT_VERSION,
        "requirement_id": raw.get("requirement_id") or raw.get("id") or raw.get("code"),
        "text": raw.get("text") or raw.get("description") or raw.get("service") or "",
        "service": raw.get("service") or raw.get("object") or raw.get("text"),
        "quantity": raw.get("quantity"),
        "unit": raw.get("unit"),
        "mandatory": bool(raw.get("mandatory", True)),
        "required_document_type": raw.get("required_document_type") or raw.get("doc_type"),
        "allow_sum": bool(raw.get("allow_sum", False)),
        "origin": {
            "document_id": raw.get("document_id") or raw.get("source_document_id"),
            "document_hash": raw.get("document_hash") or raw.get("source_hash"),
            "page": raw.get("page"),
            "item": raw.get("item") or raw.get("item_code"),
            "cell": raw.get("cell"),
            "sheet": raw.get("sheet"),
            "extracted_text": (raw.get("extracted_text") or raw.get("text") or "")[:500],
            "rule_applied": raw.get("rule_applied") or "edital_case_or_requirements_json",
        },
        "limitations": list(raw.get("limitations") or []),
        "human_action_required": raw.get("human_action_required"),
    }


def match_technical_via_acervo(
    requirement: dict[str, Any],
    *,
    store: Any | None = None,
) -> dict[str, Any]:
    """Call canonical ``scripts.technical_acervo.match.match_requirement``.

    Never reimplements matching logic here.
    """
    from scripts.technical_acervo.match import match_requirement
    from scripts.technical_acervo.store import load_store

    acervo = store if store is not None else load_store()
    req = edital_requirement_from_dict(requirement)
    service = str(req.get("service") or req.get("text") or "")
    result = match_requirement(
        acervo,
        service=service,
        quantity=req.get("quantity"),
        unit=req.get("unit") or "m2",
        allow_sum=bool(req.get("allow_sum", False)),
    )
    adherence = result.get("adherence") or result.get("adherence_level") or "no_match"
    evidence_rows = result.get("evidence") or result.get("candidates") or result.get("hits") or []
    if not evidence_rows and result.get("best_individual"):
        evidence_rows = [result["best_individual"]]

    tech_evidences: list[dict[str, Any]] = []
    for row in evidence_rows if isinstance(evidence_rows, list) else []:
        if not isinstance(row, dict):
            continue
        tech_evidences.append(
            {
                "contract": "technical_acervo_evidence",
                "contract_version": INTEGRATION_CONTRACT_VERSION,
                "source": "data/extra_technical_acervo.json",
                "experience_id": row.get("experience_id"),
                "item_id": row.get("item_id") or row.get("id"),
                "document_type": row.get("document_type"),
                "evidence_level": row.get("evidence_level"),
                "quantity": row.get("quantity"),
                "unit": row.get("unit"),
                "service": row.get("service") or row.get("title"),
                "validity_status": row.get("validity_status") or row.get("status"),
                "limitations": list(row.get("limitations") or result.get("limitations") or []),
                "human_review_required": bool(
                    result.get("human_review_required")
                    or adherence in {"human_review_required", "evidence_limited"}
                ),
            }
        )

    # Map adherence → match status / technical match enum
    if adherence in {"full_individual"}:
        match_status = MatchStatus.SATISFIED.value
        tech = TechnicalMatch.EXACT_OBJECT_QUANTITY.value
    elif adherence in {"partial_individual"}:
        match_status = MatchStatus.PARTIALLY_SATISFIED.value
        tech = TechnicalMatch.EXACT_SERVICE_PARTIAL_QUANTITY.value
    elif adherence == "only_with_sum":
        if req.get("allow_sum"):
            match_status = MatchStatus.PARTIALLY_SATISFIED.value
            tech = TechnicalMatch.COMPOSITE_SUMMABLE.value
        else:
            match_status = MatchStatus.MISSING.value
            tech = TechnicalMatch.QUANTITY_INSUFFICIENT.value
    elif adherence == "human_review_required":
        match_status = MatchStatus.NEEDS_HUMAN.value
        tech = TechnicalMatch.NEEDS_ENGINEER_REVIEW.value
    else:
        match_status = MatchStatus.MISSING.value
        tech = TechnicalMatch.NO_MATCH.value

    # Unit mismatch signal from acervo result
    if result.get("unit_mismatch") or result.get("status") == "unit_mismatch":
        match_status = MatchStatus.INCONSISTENT.value
        tech = TechnicalMatch.UNIT_MISMATCH.value

    finding = {
        "contract": "readiness_finding",
        "contract_version": INTEGRATION_CONTRACT_VERSION,
        "requirement": req,
        "match_status": match_status,
        "technical_match": tech,
        "technical_acervo_evidence": tech_evidences,
        "bid_document_evidence": [],  # filled by document pipeline
        "acervo_raw": {
            "adherence": adherence,
            "allow_sum": req.get("allow_sum"),
            "sum_total": result.get("sum_total"),
            "limitations": result.get("limitations") or [],
            "human_review_required": result.get("human_review_required"),
        },
        "limitations": list(result.get("limitations") or [])
        + [
            "Acervo match is decision-support only; engineer review required.",
            "Default path forbids summing distinct works unless allow_sum=true.",
        ],
        "human_action_required": True
        if match_status
        in {
            MatchStatus.NEEDS_HUMAN.value,
            MatchStatus.MISSING.value,
            MatchStatus.PARTIALLY_SATISFIED.value,
            MatchStatus.INCONSISTENT.value,
        }
        else bool(result.get("human_review_required")),
    }
    return finding


def integrate_requirements(
    requirements: list[dict[str, Any]],
    *,
    store: Any | None = None,
) -> dict[str, Any]:
    """Run acervo match for each technical requirement; produce package state."""
    findings: list[dict[str, Any]] = []
    for req in requirements:
        findings.append(match_technical_via_acervo(req, store=store))

    blocked_tech = any(
        f.get("match_status")
        in {
            MatchStatus.MISSING.value,
            MatchStatus.INCONSISTENT.value,
            MatchStatus.EXPIRED.value,
        }
        and (f.get("requirement") or {}).get("mandatory", True)
        for f in findings
    )
    needs_human = any(f.get("human_action_required") for f in findings)

    if blocked_tech:
        package_status = "BLOCKED_BY_TECHNICAL_QUALIFICATION"
    elif needs_human:
        package_status = "READY_FOR_HUMAN_REVIEW"
    else:
        package_status = "READY_FOR_HUMAN_REVIEW"  # never auto-submit

    if package_status in FORBIDDEN_PACKAGE_STATES:
        raise RuntimeError(f"forbidden package state: {package_status}")

    human_decision = {
        "contract": "human_decision",
        "contract_version": INTEGRATION_CONTRACT_VERSION,
        "status": "PENDING_HUMAN",
        "allowed_outcomes": sorted(ALLOWED_PACKAGE_STATES),
        "forbidden_outcomes": sorted(FORBIDDEN_PACKAGE_STATES),
        "auto_submit": False,
        "auto_outreach": False,
    }

    return {
        "contract_version": INTEGRATION_CONTRACT_VERSION,
        "package_status": package_status,
        "findings": findings,
        "human_decision": human_decision,
        "sources": {
            "technical_acervo": "data/extra_technical_acervo.json",
            "edital_case": "scripts.edital_case (requirements + locators)",
            "bid_readiness": "scripts.bid_readiness (identity/validity/package)",
        },
        "non_claims": [
            "Not READY_TO_SUBMIT",
            "Not HABILITADA",
            "Not automatic proposal approval",
            "Technical match consumes technical_acervo only — no second base",
        ],
    }


def requirements_from_edital_case_pack(case_dir: Any) -> list[dict[str, Any]]:
    """Best-effort extract requirements from an edital_case output directory."""
    from pathlib import Path
    import json

    root = Path(case_dir)
    candidates = [
        root / "requirements.json",
        root / "edital_requirements.json",
        root / "checklist.json",
    ]
    for path in candidates:
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [edital_requirement_from_dict(x) for x in data if isinstance(x, dict)]
            if isinstance(data, dict) and isinstance(data.get("requirements"), list):
                return [
                    edital_requirement_from_dict(x)
                    for x in data["requirements"]
                    if isinstance(x, dict)
                ]
    return []

"""Import explicit human documentary review records.

Only this path may set human_review_completed=True.
Automated desk/AI packages must never call complete_human_review.

Completeness gate (v3 regime fix):
  reviewer, reviewed_at, decision, ≥1 document read with identifiable
  page/clause/section/cell, regime decision, confidence, technical note.
Incomplete imports become human_review_incomplete with completed=false.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

HUMAN_REVIEW_COMPLETED = "human_review_completed"
HUMAN_REVIEW_INCOMPLETE = "human_review_incomplete"
HUMAN_REVIEW_PENDING = "human_review_pending"
HUMAN_REVIEW_NONE = "human_review_none"

_ACCEPT_DECISIONS = frozenset(
    {"ACCEPT", "CONFIRMED", "APPROVED", "COMPLETE", "REGIME_UNRESOLVED"}
)
_VERIFIED_PROMOTE_DECISIONS = frozenset({"ACCEPT", "CONFIRMED", "APPROVED", "COMPLETE"})


def _as_list(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return []
        # CSV may store JSON arrays or semicolon-separated values
        if s.startswith("["):
            try:
                parsed = json.loads(s)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass
        return [p.strip() for p in s.replace("|", ";").split(";") if p.strip()]
    return [value]


def _has_identifiable_locus(rec: dict[str, Any]) -> bool:
    """At least one page, clause, section or cell identifiable."""
    for key in (
        "pages",
        "page",
        "clauses",
        "clause",
        "sections",
        "section",
        "cells",
        "cell",
        "locus",
        "document_locus",
    ):
        vals = _as_list(rec.get(key))
        if any(str(v).strip() for v in vals):
            return True
        raw = rec.get(key)
        if isinstance(raw, (int, float)) and raw is not None:
            return True
        if isinstance(raw, str) and raw.strip():
            return True
    return False


def _documents_read(rec: dict[str, Any]) -> list[Any]:
    for key in ("documents_read", "documents", "docs_read", "document_read"):
        docs = _as_list(rec.get(key))
        if docs:
            return docs
    # Single document field
    for key in ("document", "document_name", "arquivo"):
        if rec.get(key):
            return [rec[key]]
    return []


def _regime_decision_present(rec: dict[str, Any]) -> bool:
    """Regime confirmed or explicit unresolved decision."""
    for key in (
        "regime_confirmed",
        "regime_decision",
        "legal_regime",
        "regime",
        "regime_status",
    ):
        val = rec.get(key)
        if val is None or val == "":
            continue
        s = str(val).strip().lower()
        if s in {"", "null", "none", "n/a"}:
            continue
        return True
    decision = str(rec.get("decision") or "").strip().upper()
    if decision in {"REGIME_UNRESOLVED", "UNRESOLVED"}:
        return True
    # Explicit flag
    if rec.get("regime_unresolved") in {True, "true", "True", "1", 1, "yes"}:
        return True
    return False


def _technical_note(rec: dict[str, Any]) -> str:
    for key in ("notes", "technical_note", "observacao", "observation", "comentario"):
        val = rec.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _confidence_present(rec: dict[str, Any]) -> bool:
    val = rec.get("confidence") or rec.get("confidence_level") or rec.get("nivel_confianca")
    if val is None or val == "":
        return False
    return bool(str(val).strip())


def assess_human_review_completeness(rec: dict[str, Any]) -> dict[str, Any]:
    """Return completeness assessment for a raw review record.

    Does not silently discard incomplete records — marks status instead.
    """
    missing: list[str] = []
    reviewer = str(rec.get("reviewer") or "").strip()
    if not reviewer:
        missing.append("reviewer")
    reviewed_at = rec.get("reviewed_at") or rec.get("review_date") or rec.get("data_revisao")
    if not reviewed_at:
        missing.append("reviewed_at")
    decision = str(rec.get("decision") or "").strip()
    if not decision:
        missing.append("decision")
    docs = _documents_read(rec)
    if not docs:
        missing.append("documents_read")
    if not _has_identifiable_locus(rec):
        missing.append("page_clause_section_or_cell")
    if not _regime_decision_present(rec):
        missing.append("regime_decision")
    if not _confidence_present(rec):
        missing.append("confidence")
    if not _technical_note(rec):
        missing.append("technical_note")

    complete = len(missing) == 0
    decision_u = decision.upper()
    acceptish = decision_u in _ACCEPT_DECISIONS

    # VERIFIED promotion extra gates (informational; stage evaluator still checks)
    verified_missing: list[str] = []
    if acceptish and complete:
        if not (
            rec.get("clauses")
            or rec.get("clause")
            or rec.get("clausula_reajuste")
            or rec.get("clause_identified")
        ):
            verified_missing.append("clausula_reajuste_identificada")
        if not (
            rec.get("data_base_confirmed")
            or rec.get("data_base")
            or rec.get("exact_budget_date")
        ):
            verified_missing.append("data_base_confirmada")
        if not (
            rec.get("index_confirmed")
            or rec.get("indice")
            or rec.get("formula")
            or rec.get("index_or_formula")
        ):
            verified_missing.append("indice_ou_formula_confirmada")
        if not (
            rec.get("prior_adjustment")
            or rec.get("adjustment_history")
            or rec.get("historico_reajustes")
        ):
            verified_missing.append("historico_reajustes_analisado")
        if not (
            rec.get("document_link_validated")
            or rec.get("vinculo_documental")
            or rec.get("document_contract_link")
        ):
            # Soft: documents_read + locus already imply some binding
            if not docs:
                verified_missing.append("vinculo_documento_contrato")

    return {
        "complete": complete,
        "missing_fields": missing,
        "verified_promotion_gaps": verified_missing,
        "can_mark_completed": complete and acceptish,
        "can_promote_verified": complete
        and acceptish
        and decision_u in _VERIFIED_PROMOTE_DECISIONS
        and not verified_missing,
    }


def load_human_review_file(path: str | Path) -> dict[str, dict[str, Any]]:
    """Load JSON or CSV human review file keyed by contrato_id or cnpj.

    Incomplete records are retained with human_review_completed=false and
    human_review_status=human_review_incomplete (never silently dropped).
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"human-review-file not found: {p}")

    records: list[dict[str, Any]] = []
    if p.suffix.lower() == ".json":
        payload = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            records = [r for r in payload if isinstance(r, dict)]
        elif isinstance(payload, dict):
            if "reviews" in payload and isinstance(payload["reviews"], list):
                records = [r for r in payload["reviews"] if isinstance(r, dict)]
            elif "records" in payload and isinstance(payload["records"], list):
                records = [r for r in payload["records"] if isinstance(r, dict)]
            else:
                records = [payload]
    elif p.suffix.lower() == ".csv":
        with p.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            records = list(reader)
    else:
        raise ValueError(f"Unsupported human-review-file format: {p.suffix}")

    out: dict[str, dict[str, Any]] = {}
    for raw in records:
        rec = {k: (v.strip() if isinstance(v, str) else v) for k, v in raw.items()}
        # Keep records even without reviewer — mark incomplete
        decision = str(rec.get("decision") or "").strip().upper()
        rec["decision"] = decision

        assessment = assess_human_review_completeness(rec)
        rec["completeness"] = assessment
        rec["missing_fields"] = assessment["missing_fields"]

        # Never allow automated sources to pose as human
        source = str(rec.get("source") or rec.get("kind") or "").lower()
        if "ai" in source or "automated" in source or "machine" in source:
            rec["human_review_completed"] = False
            rec["human_review_status"] = HUMAN_REVIEW_INCOMPLETE
            rec["decision"] = "REJECT_AUTOMATED_SOURCE"
            rec["reject_reason"] = "automated_source"
        elif assessment["can_mark_completed"]:
            rec["human_review_completed"] = True
            rec["human_review_status"] = HUMAN_REVIEW_COMPLETED
            rec["can_promote_verified"] = assessment["can_promote_verified"]
        else:
            rec["human_review_completed"] = False
            if rec.get("reviewer") or rec.get("decision"):
                rec["human_review_status"] = HUMAN_REVIEW_INCOMPLETE
            else:
                rec["human_review_status"] = HUMAN_REVIEW_NONE

        cid = str(rec.get("contrato_id") or rec.get("contract_id") or "").strip()
        cnpj = "".join(ch for ch in str(rec.get("cnpj") or "") if ch.isdigit())[:14]
        if cid:
            out[cid] = rec
        elif len(cnpj) == 14:
            out.setdefault(cnpj, rec)
        else:
            # Retain orphan incomplete records under synthetic key
            key = f"incomplete:{len(out)}"
            out[key] = rec
        if len(cnpj) == 14 and cid:
            out.setdefault(cnpj, rec)
    return out


def human_review_done_for(
    records: dict[str, dict[str, Any]],
    *,
    contrato_id: str | None = None,
    cnpj: str | None = None,
) -> bool:
    """True only when an imported human review is complete and accepted."""
    rec = None
    if contrato_id and contrato_id in records:
        rec = records[contrato_id]
    elif cnpj:
        c = "".join(ch for ch in cnpj if ch.isdigit())[:14]
        rec = records.get(c)
    if not rec:
        return False
    if rec.get("human_review_completed") is True:
        return True
    # Fail-closed: reviewer+decision alone is NOT enough
    return False


def human_review_status_for(
    records: dict[str, dict[str, Any]],
    *,
    contrato_id: str | None = None,
    cnpj: str | None = None,
) -> str:
    rec = None
    if contrato_id and contrato_id in records:
        rec = records[contrato_id]
    elif cnpj:
        c = "".join(ch for ch in cnpj if ch.isdigit())[:14]
        rec = records.get(c)
    if not rec:
        return HUMAN_REVIEW_NONE
    return str(rec.get("human_review_status") or HUMAN_REVIEW_NONE)

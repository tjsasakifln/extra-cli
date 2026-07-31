"""Evidence-bound human decision rules for the review workbench."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

ALLOWED_DECISIONS = frozenset({"ACCEPT", "REJECT", "DEFER"})


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


def validate_decision_request(
    *,
    decision: str,
    rationale: str | None,
    return_by: str | None = None,
    artifact_hashes: dict[str, str] | None = None,
    presented_hashes: dict[str, str] | None = None,
    title: str | None = None,
) -> list[str]:
    """Return human-readable validation errors (empty = ok)."""
    errors: list[str] = []
    d = (decision or "").upper().strip()
    if d not in ALLOWED_DECISIONS:
        errors.append("Decisão deve ser ACCEPT, REJECT ou DEFER.")
        return errors
    rat = (rationale or "").strip()
    if d in {"REJECT", "DEFER"}:
        if len(rat) < 8:
            errors.append("REJECT e DEFER exigem justificativa real (mínimo 8 caracteres).")
        if title and rat == title.strip():
            errors.append("A justificativa não pode ser apenas o título do item.")
    if d == "DEFER":
        if not (return_by or "").strip():
            errors.append("DEFER exige data ou condição de retorno (return_by).")
    if d == "ACCEPT":
        # ACCEPT must bind to hashes of presented artifacts when provided
        presented = presented_hashes or {}
        bound = artifact_hashes or {}
        if presented:
            if not bound:
                errors.append("ACCEPT exige vínculo aos hashes dos artefatos apresentados.")
            else:
                for key, expected in presented.items():
                    if bound.get(key) != expected:
                        errors.append(
                            f"Hash divergente para «{key}»: a evidência mudou desde a apresentação."
                        )
    return errors


def build_decision_record(
    *,
    item_id: str,
    decision: str,
    actor: str,
    rationale: str | None,
    artifact_hashes: dict[str, str] | None,
    artifact_version: str | None,
    return_by: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "item_id": item_id,
        "decision": decision.upper().strip(),
        "actor": actor,
        "rationale": rationale,
        "artifact_hashes": dict(artifact_hashes or {}),
        "artifact_version": artifact_version,
        "return_by": return_by,
        "ts": _utcnow(),
        "obsolete": False,
        "payload": dict(payload or {}),
    }


def decision_is_obsolete(
    *,
    stored_hashes: dict[str, str] | None,
    current_hashes: dict[str, str] | None,
) -> bool:
    """If artifact content changed after ACCEPT, prior decision is obsolete."""
    stored = stored_hashes or {}
    current = current_hashes or {}
    if not stored:
        return False
    if not current:
        return True
    for k, v in stored.items():
        if current.get(k) != v:
            return True
    return False


def invalidate_decisions_for_hashes(
    decisions: list[dict[str, Any]],
    current_hashes: dict[str, str],
) -> list[dict[str, Any]]:
    """Mark ACCEPT decisions obsolete when hashes no longer match."""
    out: list[dict[str, Any]] = []
    for d in decisions:
        item = dict(d)
        if str(item.get("decision", "")).upper() == "ACCEPT":
            hashes = item.get("artifact_hashes") or (item.get("payload") or {}).get("artifact_hashes") or {}
            if decision_is_obsolete(stored_hashes=hashes, current_hashes=current_hashes):
                item["obsolete"] = True
                item["obsolete_reason"] = "artifact_hash_changed"
        out.append(item)
    return out

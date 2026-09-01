"""Deterministic rewrite of unsafe / unreadable claims.

Two branches, no heuristics:

* linked contract with ``end_date < today`` → explicit past frame anchored on
  that date; the lead becomes ``SAFE_HISTORICAL``.
* ``end_date >= today`` or ``end_date IS NULL`` → the present assertion is
  removed and the observed fact is preserved; the lead becomes
  ``SAFE_NO_CURRENT_CLAIM``.

``NEEDS_RESEARCH`` leads (unrecognized template, ``MATURE_NO_REAJUSTE``, or a
present claim that binds to no contract) go through the same neutralization —
AC 20's enforcement clause: an unreadable template must not publish unchanged
carrying its template's present claim.

Every rewritten lead is marked ``claim_safety.policy_authored_copy = true``: the
copy is no longer the generator's ambiguous template but a deterministic
rendering, and the classifier re-verifies its claim surface lexically.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from scripts.confenge_claim_safety.claim_surface import (
    ASSERTION_FIELDS,
    CLAIM_NONE,
    CLAIM_PRESENT,
    PRESENT_CLAIM_PATTERN,
    PRESENT_CORE,
    PRESENT_QUALIFIER,
    detect_temporal_claim,
    evidence_values,
    strip_evidence_spans,
)
from scripts.confenge_claim_safety.policy import (
    CLAIM_SAFETY_LEAD_KEY,
    CLAIM_SAFETY_POLICY_VERSION,
    POLICY_AUTHORED_COPY_KEY,
)

PAST_FRAME_TEMPLATE = "Vigência encerrada em {date}."
REWRITE_RULE_NEUTRALIZED = "present_assertion_removed"
REWRITE_RULE_PAST_FRAME = "past_frame_anchored_on_end_date"

# Used only when neutralization consumes the whole copy: the lead still needs a
# why_now, and an empty string is not a safe claim, it is a broken payload.
NEUTRAL_FALLBACK_TEXT = "Fato contratual público observado no input, sem afirmação de vigência atual."

# A present assertion usually hangs off a prepositional phrase ("com vigência
# ativa comprovada"). Excising only the token leaves mangled Portuguese, so the
# whole phrase up to the clause boundary goes.
_PRESENT_PHRASE = re.compile(
    rf"\s*\b(?:com|sob|em|sem|de)\s+{PRESENT_QUALIFIER}{PRESENT_CORE}\b[^,;:.!?]*",
    re.IGNORECASE,
)
_SEGMENT_SPLIT = re.compile(r"([,;:—.!?])")


class ClaimRewriteError(RuntimeError):
    """The copy could not be made claim-free deterministically."""


def _neutralize_segment(segment: str) -> str | None:
    """Neutralize one clause. ``None`` means the clause must be dropped entirely."""
    cleaned = segment
    while True:
        stripped = _PRESENT_PHRASE.sub("", cleaned)
        if stripped == cleaned:
            break
        cleaned = stripped
    cleaned = PRESENT_CLAIM_PATTERN.sub("", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    if detect_temporal_claim(cleaned) == CLAIM_PRESENT:
        # Deterministic last resort: a clause we cannot disarm is not published.
        return None
    return cleaned


def _neutralize(text: str) -> str:
    """Remove present-tense assertions of contractual currency from ``text``."""
    parts = _SEGMENT_SPLIT.split(text)
    rebuilt: list[str] = []
    for index in range(0, len(parts), 2):
        segment = parts[index]
        delimiter = parts[index + 1] if index + 1 < len(parts) else ""
        neutral = _neutralize_segment(segment)
        if neutral is None:
            continue
        if not neutral.strip() and not rebuilt:
            continue
        rebuilt.append(neutral + delimiter)
    cleaned = "".join(rebuilt)
    cleaned = re.sub(r"\s+([,;:.!?])", r"\1", cleaned)
    cleaned = re.sub(r"([,;:])\s*([.!?])", r"\2", cleaned)
    cleaned = re.sub(r"\s+(?:e|ou)\s*([.,;])", r"\1", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,;:—")
    if not cleaned or cleaned in {".", "…"}:
        return NEUTRAL_FALLBACK_TEXT
    return cleaned


def _format_end_date(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return None


def contract_end_date(contract: dict[str, Any] | None) -> date | None:
    if not isinstance(contract, dict):
        return None
    text = str(contract.get("end_date") or contract.get("vigencia_fim") or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def rewrite_text(text: str, *, past_frame: str | None) -> str:
    """Neutralize a single assertion field, optionally appending a past frame."""
    cleaned = _neutralize(text)
    if past_frame:
        if cleaned and not cleaned.endswith((".", "!", "?")):
            cleaned = f"{cleaned}."
        cleaned = f"{cleaned} {past_frame}".strip()
    return cleaned


def rewrite_lead(
    lead: dict[str, Any],
    *,
    contract: dict[str, Any] | None,
    today: date | None = None,
    reason_codes: tuple[str, ...] | list[str] = (),
) -> tuple[dict[str, Any], bool]:
    """Return ``(rewritten_lead, changed)``.

    The lead is copied; the caller's object is never mutated.
    """
    reference = today or date.today()
    end = contract_end_date(contract)
    past_frame = None
    rule = REWRITE_RULE_NEUTRALIZED
    if end is not None and end < reference:
        formatted = _format_end_date(end.isoformat())
        if formatted:
            past_frame = PAST_FRAME_TEMPLATE.format(date=formatted)
            rule = REWRITE_RULE_PAST_FRAME

    updated = dict(lead)
    changed = False
    for path in ASSERTION_FIELDS:
        parent_key, field_name = path[0], path[-1]
        parent = updated.get(parent_key)
        if not isinstance(parent, dict):
            continue
        original = parent.get(field_name)
        if not isinstance(original, str) or not original.strip():
            continue
        rewritten = rewrite_text(original, past_frame=past_frame)
        if rewritten != original:
            parent = dict(parent)
            parent[field_name] = rewritten
            updated[parent_key] = parent
            changed = True

    # Prove the neutralization actually worked before declaring the copy safe.
    values = evidence_values(updated)
    for path in ASSERTION_FIELDS:
        node: Any = updated
        for key in path:
            node = node.get(key) if isinstance(node, dict) else None
            if node is None:
                break
        if not isinstance(node, str):
            continue
        surface = strip_evidence_spans(node, values)
        if detect_temporal_claim(surface) == CLAIM_PRESENT:
            raise ClaimRewriteError(
                f"present assertion survived deterministic rewrite in {'.'.join(path)}: {surface!r}"
            )

    block = dict(updated.get(CLAIM_SAFETY_LEAD_KEY) or {})
    block.update(
        {
            POLICY_AUTHORED_COPY_KEY: True,
            "policy_version": CLAIM_SAFETY_POLICY_VERSION,
            "rewrite_rule": rule,
            "linked_contract_id": (str(contract.get("id") or "") or None) if isinstance(contract, dict) else None,
            "reason_codes": list(reason_codes),
        }
    )
    # No clock participates: a replay of the same corpus must produce byte-identical
    # chunks, otherwise idempotency (AC 11) becomes unobservable.
    updated[CLAIM_SAFETY_LEAD_KEY] = block
    return updated, changed


__all__ = [
    "CLAIM_NONE",
    "PAST_FRAME_TEMPLATE",
    "REWRITE_RULE_NEUTRALIZED",
    "REWRITE_RULE_PAST_FRAME",
    "ClaimRewriteError",
    "contract_end_date",
    "rewrite_lead",
    "rewrite_text",
]

"""Absolute deterministic veto: non-PASS verification can never become ACCEPT.

Invariant:
  verification.result != PASS  =>  review.verdict != ACCEPT  =>  publication forbidden

DeepSeek may downgrade PASS → REPAIR/BLOCK/ESCALATE.
DeepSeek must never upgrade FAIL/UNSAFE/INCOMPLETE/UNPROVEN → ACCEPT.
"""
from __future__ import annotations

from typing import Any

NON_PASS_RESULTS = frozenset({"FAIL", "UNSAFE", "INCOMPLETE", "UNPROVEN", "ERROR", "BLOCKED"})
ACCEPT_FORBIDDEN_WHEN = NON_PASS_RESULTS | frozenset({None, "", "UNKNOWN"})


def verification_blocks_accept(verification: dict[str, Any] | None) -> bool:
    if not verification:
        return True
    result = verification.get("result")
    if result != "PASS":
        return True
    # Any UNPROVEN criterion blocks even if aggregate was mis-labeled PASS
    for m in verification.get("criterion_matrix") or []:
        if m.get("status") in {"UNPROVEN", "FAIL"}:
            return True
    return False


def apply_absolute_veto(
    review: dict[str, Any],
    verification: dict[str, Any] | None,
) -> dict[str, Any]:
    """Force non-ACCEPT when verification is not PASS. Idempotent."""
    out = dict(review)
    result = (verification or {}).get("result")
    if not verification_blocks_accept(verification):
        out["_veto"] = {
            "applied": False,
            "reason": "verification PASS and matrix clean",
            "verification_result": result,
        }
        return out

    original = out.get("verdict")
    if original == "ACCEPT":
        # Absolute veto — model attempted illegal ACCEPT
        if result == "UNSAFE":
            out["verdict"] = "BLOCK"
        else:
            out["verdict"] = "REPAIR"
        out["summary"] = (
            f"ABSOLUTE_VETO: model verdict ACCEPT overridden "
            f"(verification.result={result!r}). "
            f"Original summary: {out.get('summary') or ''}"
        )[:2000]
        out.setdefault("failed_criteria", [])
        if isinstance(out["failed_criteria"], list):
            out["failed_criteria"] = list(out["failed_criteria"]) + [
                f"ABSOLUTE_VETO:ACCEPT_ON_{result}"
            ]
        hg = dict(out.get("human_gate") or {})
        if out["verdict"] == "BLOCK":
            hg["required"] = True
            hg["reason"] = f"ABSOLUTE_VETO on verification {result}"
        out["human_gate"] = hg
        out["_veto"] = {
            "applied": True,
            "original_verdict": original,
            "forced_verdict": out["verdict"],
            "verification_result": result,
            "reason": "verification non-PASS forbids ACCEPT",
        }
    else:
        out["_veto"] = {
            "applied": False,
            "reason": f"verdict already non-ACCEPT ({original})",
            "verification_result": result,
        }
    return out


def publication_forbidden(
    *,
    verification: dict[str, Any] | None,
    review: dict[str, Any] | None,
) -> tuple[bool, str]:
    if verification_blocks_accept(verification):
        return True, f"verification.result={((verification or {}).get('result'))!r} != PASS"
    if not review or review.get("verdict") != "ACCEPT":
        return True, f"review.verdict={((review or {}).get('verdict'))!r} != ACCEPT"
    if (review.get("_veto") or {}).get("applied"):
        return True, "absolute veto applied — publication forbidden"
    return False, "ok"

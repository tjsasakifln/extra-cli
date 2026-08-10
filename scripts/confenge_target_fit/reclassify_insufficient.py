"""Bulk-correct PROBABLE rows that lack positive ICP evidence (SHADOW).

Sets TARGET_INSUFFICIENT_EVIDENCE when reason_codes are only default_research
(or equivalent) and evidence is empty — without inventing new classifications
for rows that already carry positive evidence.

Safe, idempotent, resumable. Does not touch CONFIRMED.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from scripts.confenge_universe.target_fit import (
    TARGET_FIT_VERSION,
    TARGET_INSUFFICIENT_EVIDENCE,
    TARGET_PROBABLE_RESEARCH,
)

logger = logging.getLogger(__name__)

# Reason patterns that indicate "unknown" was mislabeled as PROBABLE
_INSUFFICIENT_REASON_MARKERS = frozenset(
    {
        "default_research",
        "no_sector_no_execution",
        "possible_label_without_positive_icp_evidence",
        "sector_label_without_positive_icp_evidence",
        "insufficient_positive_icp_evidence",
    }
)


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


def _is_empty_evidence(evidence: Any) -> bool:
    if evidence is None:
        return True
    if isinstance(evidence, str):
        s = evidence.strip()
        return s in {"", "[]", "{}", "null", "None"}
    if isinstance(evidence, (list, dict)):
        return len(evidence) == 0
    return True


def _reasons_list(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x) for x in raw]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(x) for x in parsed]
        except json.JSONDecodeError:
            return [raw]
    return []


def should_downgrade_probable_to_insufficient(
    *,
    reason_codes: Any,
    evidence: Any,
) -> bool:
    """True when PROBABLE has no positive evidence payload and only weak reasons."""
    if not _is_empty_evidence(evidence):
        return False
    reasons = _reasons_list(reason_codes)
    if not reasons:
        return True
    # Strip consortium notes — they are not positive ICP construction evidence
    core = [
        r
        for r in reasons
        if r
        not in {
            "CONSORTIUM_EVIDENCE",
            "consortium_contracts_present_conservative",
        }
        and not str(r).startswith("consortium")
    ]
    if not core:
        return True
    return all(
        r in _INSUFFICIENT_REASON_MARKERS or r.startswith("possible_or_single")
        for r in core
    ) and not any(
        "execution" in r and "single" not in r for r in core
    ) and "positive_cnae" not in " ".join(core)


def reclassify_shadow_probable_without_evidence(
    conn: Any,
    *,
    dry_run: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    """Rewrite SHADOW PROBABLE→INSUFFICIENT when evidence is empty / reasons weak."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT company_key, cnpj_raiz, reason_codes, evidence
            FROM confenge_target_fit_shadow
            WHERE shadow_class = %s
            """,
            (TARGET_PROBABLE_RESEARCH,),
        )
        rows = list(cur.fetchall() or [])

    candidates = []
    for r in rows:
        if should_downgrade_probable_to_insufficient(
            reason_codes=r.get("reason_codes"),
            evidence=r.get("evidence"),
        ):
            candidates.append(r)
        if limit is not None and len(candidates) >= limit:
            break

    updated = 0
    if not dry_run and candidates:
        with conn.cursor() as cur:
            for r in candidates:
                cur.execute(
                    """
                    UPDATE confenge_target_fit_shadow
                    SET shadow_class = %s,
                        shadow_confidence = LEAST(shadow_confidence, 0.25),
                        reason_codes = %s,
                        target_fit_version = %s,
                        updated_at = NOW()
                    WHERE company_key = %s
                      AND shadow_class = %s
                    """,
                    (
                        TARGET_INSUFFICIENT_EVIDENCE,
                        json.dumps(
                            list(_reasons_list(r.get("reason_codes")))
                            + ["reclassified_insufficient_no_positive_evidence"]
                        ),
                        TARGET_FIT_VERSION,
                        r["company_key"],
                        TARGET_PROBABLE_RESEARCH,
                    ),
                )
                updated += cur.rowcount
        conn.commit()

    return {
        "schema": "confenge.reclassify_insufficient.v1",
        "as_of": _utcnow(),
        "probable_scanned": len(rows),
        "candidates": len(candidates),
        "updated": updated,
        "dry_run": dry_run,
        "target_class": TARGET_INSUFFICIENT_EVIDENCE,
        "classifier_version": TARGET_FIT_VERSION,
    }

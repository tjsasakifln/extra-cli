"""Near-duplicate draft/batch gate for CONFENGE outreach.

Blocks a batch when bodies are near-clones across different companies despite
distinct facts. This is a regression detector, not a diversity quota.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

# Jaccard token similarity above this across different accounts → flag
DEFAULT_SIMILARITY_THRESHOLD = 0.82
# Fraction of pairs above threshold that triggers batch block
DEFAULT_PAIR_FRACTION_LIMIT = 0.35


_TOKEN_RE = re.compile(r"[a-z0-9à-ü]+", re.I)


def _tokens(text: str) -> set[str]:
    stop = {
        "de",
        "da",
        "do",
        "das",
        "dos",
        "a",
        "o",
        "e",
        "que",
        "em",
        "para",
        "com",
        "por",
        "um",
        "uma",
        "os",
        "as",
        "no",
        "na",
        "nos",
        "nas",
        "ao",
        "à",
        "pelo",
        "pela",
        "olá",
        "ola",
    }
    return {t.lower() for t in _TOKEN_RE.findall(text or "") if len(t) > 2 and t.lower() not in stop}


def jaccard(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


@dataclass
class NearDuplicateAudit:
    total_drafts: int
    compared_pairs: int
    high_similarity_pairs: int
    max_similarity: float
    pair_fraction_high: float
    threshold: float
    blocked: bool
    reason_codes: list[str] = field(default_factory=list)
    sample_pairs: list[dict[str, Any]] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def audit_near_duplicates(
    drafts: list[dict[str, Any]],
    *,
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    pair_fraction_limit: float = DEFAULT_PAIR_FRACTION_LIMIT,
) -> NearDuplicateAudit:
    """Audit a batch of draft dicts with keys: account_id/cnpj, body, subject optional."""
    bodies: list[tuple[str, str]] = []
    for d in drafts:
        if not isinstance(d, dict):
            continue
        key = str(d.get("cnpj") or d.get("account_id") or d.get("id") or len(bodies))
        body = str(d.get("body") or d.get("body_text") or d.get("BodyText") or "")
        if body.strip():
            bodies.append((key, body))

    n = len(bodies)
    high = 0
    pairs = 0
    max_sim = 0.0
    samples: list[dict[str, Any]] = []
    reasons: list[str] = []

    for i in range(n):
        for j in range(i + 1, n):
            if bodies[i][0] == bodies[j][0]:
                continue
            pairs += 1
            sim = jaccard(bodies[i][1], bodies[j][1])
            max_sim = max(max_sim, sim)
            if sim >= similarity_threshold:
                high += 1
                if len(samples) < 10:
                    samples.append(
                        {
                            "a": bodies[i][0],
                            "b": bodies[j][0],
                            "similarity": round(sim, 4),
                        }
                    )

    frac = (high / pairs) if pairs else 0.0
    blocked = False
    if n >= 3 and pairs > 0 and frac >= pair_fraction_limit:
        blocked = True
        reasons.append("near_duplicate_batch_fraction")
    if n >= 2 and max_sim >= 0.95 and high >= 1:
        # Extreme clone pair always review-worthy when multi-account
        blocked = True
        reasons.append("near_duplicate_extreme_pair")
    if not blocked:
        reasons.append("near_duplicate_ok")

    return NearDuplicateAudit(
        total_drafts=n,
        compared_pairs=pairs,
        high_similarity_pairs=high,
        max_similarity=round(max_sim, 4),
        pair_fraction_high=round(frac, 4),
        threshold=similarity_threshold,
        blocked=blocked,
        reason_codes=reasons,
        sample_pairs=samples,
    )


def subject_is_generic_contrato(subject: str, company: str | None = None) -> bool:
    s = (subject or "").strip().lower()
    if s.startswith("contrato ") or s == "contrato":
        return True
    if company and s == f"contrato {company.strip().lower()}":
        return True
    return False

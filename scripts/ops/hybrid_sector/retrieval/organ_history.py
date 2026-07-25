"""Canal D — organ history of engineering works.

Retrieves editals from organs with proven works history.
Does NOT auto-classify as opportunity solely by history.
"""
from __future__ import annotations

import re
from typing import Iterable

from scripts.ops.sector_classifier import normalize_text
from scripts.ops.hybrid_sector.models import RawOpportunity, RetrievalHit

DEFAULT_ORG_KEYWORDS = [
    "obras",
    "infraestrutura",
    "saneamento",
    "urbanismo",
    "engenharia",
    "paviment",
    "der ",
    "dem ",
    "seinfra",
    "secretaria de obras",
    "secretaria municipal de obras",
    "companhia de habitacao",
    "departamento de estradas",
    "daeb",
    "agesan",
    "casan",
    "smae",
]

# Patterns of past works in organ name / known engineering bodies
_HISTORY_PATTERNS = [
    re.compile(r"\bsecretaria\s+(municipal\s+)?de\s+obras\b", re.I),
    re.compile(r"\bdepartamento\s+de\s+estradas\b", re.I),
    re.compile(r"\bcompanhia\s+de\s+(saneamento|habitacao|agua)\b", re.I),
    re.compile(r"\binfraestrutura\b", re.I),
]


def retrieve_organ_history(
    universe: Iterable[RawOpportunity],
    *,
    organ_keywords: list[str] | None = None,
    known_engineering_orgs: set[str] | None = None,
) -> dict[str, RetrievalHit]:
    """Score by organ name history signals and optional known-org allowlist."""
    kws = [normalize_text(k) for k in (organ_keywords or DEFAULT_ORG_KEYWORDS)]
    known = {normalize_text(o) for o in (known_engineering_orgs or set())}
    scored: list[tuple[str, float, str]] = []

    for rec in universe:
        org = normalize_text(rec.orgao)
        if not org:
            continue
        score = 0.0
        reasons: list[str] = []
        if org in known:
            score += 1.0
            reasons.append("known_engineering_org")
        for kw in kws:
            if kw and kw in org:
                score += 0.4
                reasons.append(f"kw:{kw}")
                break
        for pat in _HISTORY_PATTERNS:
            if pat.search(org):
                score += 0.5
                reasons.append(f"pat:{pat.pattern[:30]}")
                break
        # Soft boost if organ already linked via categories of works in extra
        if score > 0:
            scored.append((rec.canonical_id, score, ",".join(reasons[:4])))

    scored.sort(key=lambda x: (-x[1], x[0]))
    hits: dict[str, RetrievalHit] = {}
    for rank, (cid, score, reason) in enumerate(scored, start=1):
        hits[cid] = RetrievalHit(
            channel="organ_history",
            score=score,
            rank=rank,
            reason=reason,
        )
    return hits

"""Diverse commercial sample from the full universe (not top-N score only)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def _digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _portfolio(row: dict[str, Any]) -> dict[str, Any]:
    p = row.get("portfolio")
    return p if isinstance(p, dict) else {}


def _contract_count(row: dict[str, Any]) -> int:
    try:
        return int(_portfolio(row).get("contract_count_total") or 0)
    except (TypeError, ValueError):
        return 0


def _value_total(row: dict[str, Any]) -> float:
    try:
        return float(_portfolio(row).get("value_total_brl") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _ufs(row: dict[str, Any]) -> list[str]:
    u = _portfolio(row).get("ufs_atuacao") or []
    return [str(x).upper() for x in u] if isinstance(u, list) else []


def _score(row: dict[str, Any]) -> float:
    try:
        return float(row.get("priority_score") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def classify_profile(row: dict[str, Any]) -> str:
    """Assign a commercial diversity bucket (observational, not a claim of size culture)."""
    if str(row.get("outreach_eligibility") or "").upper() == "DNC":
        return "dnc"
    n = _contract_count(row)
    v = _value_total(row)
    ufs = _ufs(row)
    if n == 0:
        return "no_strong_contract_fact"
    if n <= 2:
        return "few_contracts"
    if n >= 15 or v >= 100_000_000:
        return "extensive_portfolio"
    if len(ufs) >= 4 or v >= 50_000_000:
        return "national_structured"
    if len(ufs) <= 1 and n <= 5:
        return "regional_lean"
    return "mid_market"


# Profiles we deliberately want represented when available.
TARGET_PROFILES: tuple[str, ...] = (
    "regional_lean",
    "mid_market",
    "national_structured",
    "few_contracts",
    "extensive_portfolio",
    "no_strong_contract_fact",
    "dnc",
)


def select_diverse_sample(
    universe_rows: list[dict[str, Any]],
    *,
    limit: int,
    include_dnc: bool = True,
) -> list[dict[str, Any]]:
    """Pick up to `limit` rows with deliberate profile diversity.

    Not pure top-score. Fills quota round-robin across profiles, then tops up
    with remaining highest-score rows that were not selected.
    """
    if limit <= 0 or not universe_rows:
        return []

    by_profile: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in universe_rows:
        if not _digits(row.get("cnpj14") or row.get("cnpj")):
            continue
        profile = classify_profile(row)
        if profile == "dnc" and not include_dnc:
            continue
        by_profile[profile].append(row)

    for profile, rows in by_profile.items():
        rows.sort(key=_score, reverse=True)

    selected: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _take(row: dict[str, Any]) -> bool:
        cnpj = _digits(row.get("cnpj14") or row.get("cnpj"))
        if not cnpj or cnpj in seen:
            return False
        seen.add(cnpj)
        out = dict(row)
        out["_sample_profile"] = classify_profile(row)
        selected.append(out)
        return True

    # Round-robin across target profiles for baseline diversity.
    pointers = {p: 0 for p in TARGET_PROFILES}
    progress = True
    while len(selected) < limit and progress:
        progress = False
        for profile in TARGET_PROFILES:
            if len(selected) >= limit:
                break
            rows = by_profile.get(profile) or []
            i = pointers[profile]
            while i < len(rows):
                row = rows[i]
                i += 1
                if _take(row):
                    progress = True
                    break
            pointers[profile] = i

    # Top-up by score from anything not yet selected.
    if len(selected) < limit:
        remainder = sorted(universe_rows, key=_score, reverse=True)
        for row in remainder:
            if len(selected) >= limit:
                break
            _take(row)

    return selected


def sample_profile_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        profile = row.get("_sample_profile") or classify_profile(row)
        counts[str(profile)] += 1
    return dict(sorted(counts.items()))

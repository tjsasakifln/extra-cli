"""Versioned temporal direct-contracting thresholds (art. 75 I/II).

Amounts live only in config/legal/direct_contracting_thresholds.yaml.
Strict comparison: value must be strictly inferior to ceiling.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from scripts.public_agency import ELIGIBILITY_POTENTIAL, SUM_UNKNOWN

_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_PATH = _ROOT / "config/legal/direct_contracting_thresholds.yaml"


@dataclass(frozen=True)
class Threshold:
    threshold_id: str
    jurisdiction: str
    legal_framework: str
    legal_reference: str
    article: str
    object_class: str
    amount: float
    currency: str
    effective_from: date
    effective_until: date | None
    strict_comparison: bool
    source_title: str
    source_authority: str
    source_retrieved_at: str
    source_hash: str
    notes: str

    def active_on(self, as_of: date) -> bool:
        if as_of < self.effective_from:
            return False
        if self.effective_until is not None and as_of > self.effective_until:
            return False
        return True


def _parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    s = str(value)[:10]
    y, m, d = s.split("-")
    return date(int(y), int(m), int(d))


def load_threshold_catalog(path: Path | None = None) -> dict[str, Any]:
    p = path or _DEFAULT_PATH
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"invalid threshold catalog: {p}")
    return data


def catalog_hash(path: Path | None = None) -> str:
    p = path or _DEFAULT_PATH
    raw = p.read_bytes()
    return hashlib.sha256(raw).hexdigest()


def parse_thresholds(data: dict[str, Any] | None = None, path: Path | None = None) -> list[Threshold]:
    cat = data if data is not None else load_threshold_catalog(path)
    out: list[Threshold] = []
    for row in cat.get("thresholds") or []:
        out.append(
            Threshold(
                threshold_id=str(row["threshold_id"]),
                jurisdiction=str(row["jurisdiction"]),
                legal_framework=str(row["legal_framework"]),
                legal_reference=str(row["legal_reference"]),
                article=str(row["article"]),
                object_class=str(row["object_class"]),
                amount=float(row["amount"]),
                currency=str(row.get("currency") or "BRL"),
                effective_from=_parse_date(row["effective_from"]) or date.min,
                effective_until=_parse_date(row.get("effective_until")),
                strict_comparison=bool(row.get("strict_comparison", True)),
                source_title=str(row.get("source_title") or ""),
                source_authority=str(row.get("source_authority") or ""),
                source_retrieved_at=str(row.get("source_retrieved_at") or ""),
                source_hash=str(row.get("source_hash") or ""),
                notes=str(row.get("notes") or ""),
            )
        )
    return out


def get_threshold(
    object_class: str,
    *,
    as_of: date,
    jurisdiction: str = "BR_FEDERAL",
    path: Path | None = None,
) -> Threshold | None:
    matches = [
        t
        for t in parse_thresholds(path=path)
        if t.object_class == object_class
        and t.jurisdiction == jurisdiction
        and t.active_on(as_of)
    ]
    if not matches:
        return None
    # Prefer latest effective_from when multiple open
    matches.sort(key=lambda t: t.effective_from, reverse=True)
    return matches[0]


def is_strictly_below_ceiling(amount: float, ceiling: float, *, strict: bool = True) -> bool:
    if strict:
        return amount < ceiling
    return amount <= ceiling


def evaluate_potential_eligibility(
    amount: float | None,
    object_class: str,
    *,
    as_of: date,
    annual_sum_same_nature: float | None = None,
    annual_sum_known: bool = False,
    fragmentation_flag: bool = False,
    path: Path | None = None,
) -> dict[str, Any]:
    """Return eligibility assessment — never claims guaranteed direct contracting."""
    result: dict[str, Any] = {
        "eligibility_state": None,
        "potentially_eligible": False,
        "reason_codes": [],
        "threshold_id": None,
        "threshold_amount": None,
        "amount": amount,
        "object_class": object_class,
        "as_of": as_of.isoformat(),
        "annual_sum_state": None,
        "strict_comparison": True,
        "disclaimer": (
            "A definição do fundamento e do procedimento de contratação compete "
            "exclusivamente ao órgão ou entidade contratante."
        ),
    }

    if object_class == "REQUIRES_HUMAN_LEGAL_CLASSIFICATION":
        result["reason_codes"].append("OBJECT_CLASSIFICATION_AMBIGUOUS")
        result["eligibility_state"] = "NOT_ASSESSED_AMBIGUOUS_OBJECT"
        return result

    thr = get_threshold(object_class, as_of=as_of, path=path)
    if thr is None:
        result["reason_codes"].append("NO_ACTIVE_THRESHOLD")
        result["eligibility_state"] = "NOT_ASSESSED_NO_THRESHOLD"
        return result

    result["threshold_id"] = thr.threshold_id
    result["threshold_amount"] = thr.amount
    result["strict_comparison"] = thr.strict_comparison

    if amount is None:
        result["reason_codes"].append("AMOUNT_UNKNOWN")
        result["eligibility_state"] = "NOT_ASSESSED_AMOUNT_UNKNOWN"
        return result

    below = is_strictly_below_ceiling(float(amount), thr.amount, strict=thr.strict_comparison)
    if not below:
        result["reason_codes"].append("AMOUNT_NOT_STRICTLY_BELOW_CEILING")
        result["eligibility_state"] = "NOT_POTENTIALLY_ELIGIBLE_AMOUNT"
        return result

    if fragmentation_flag:
        result["reason_codes"].append("FRAGMENTATION_INDICATORS_PRESENT")
        result["eligibility_state"] = "NOT_POTENTIALLY_ELIGIBLE_FRAGMENTATION"
        return result

    if not annual_sum_known or annual_sum_same_nature is None:
        result["annual_sum_state"] = SUM_UNKNOWN
        result["reason_codes"].append(SUM_UNKNOWN)
        # May still be potentially eligible by unit amount, but MUST NOT claim
        # adherence to annual aggregate limit.
        result["eligibility_state"] = ELIGIBILITY_POTENTIAL
        result["potentially_eligible"] = True
        result["annual_limit_adherence_claimed"] = False
        result["reason_codes"].append("UNIT_AMOUNT_BELOW_CEILING_SUM_UNKNOWN")
        return result

    if float(annual_sum_same_nature) >= thr.amount:
        result["reason_codes"].append("SAME_NATURE_ANNUAL_SUM_ABOVE_OR_EQUAL_THRESHOLD")
        result["eligibility_state"] = "NOT_POTENTIALLY_ELIGIBLE_ANNUAL_SUM"
        result["annual_sum_state"] = "SAME_NATURE_ANNUAL_SUM_ABOVE_THRESHOLD"
        return result

    result["annual_sum_state"] = "SAME_NATURE_ANNUAL_SUM_BELOW_THRESHOLD"
    result["annual_limit_adherence_claimed"] = True
    result["eligibility_state"] = ELIGIBILITY_POTENTIAL
    result["potentially_eligible"] = True
    result["reason_codes"].append("UNIT_AND_ANNUAL_SUM_STRICTLY_BELOW")
    return result

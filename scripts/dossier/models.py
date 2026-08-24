"""Immutable records for the CONFENGE dossier engine."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from scripts.dossier.constants import (
    DATA_HOLD,
    DATA_READY,
    DATA_REJECT,
    DATA_STATE_RANK,
    REFERENCE_SCOPE_BOTH,
)

_NON_DIGITS = re.compile(r"\D+")


def digits_only(value: Any) -> str:
    if value is None:
        return ""
    return _NON_DIGITS.sub("", str(value))


def cnpj14(value: Any) -> str | None:
    """Return a 14-digit CNPJ or None. Never pads a shorter number."""
    digits = digits_only(value)
    return digits if len(digits) == 14 else None


def cnpj_root(value: Any) -> str | None:
    digits = digits_only(value)
    return digits[:8] if len(digits) >= 8 else None


def money(value: Decimal | int | float | None) -> str | None:
    """Serialize money as a fixed-point string. None stays None, never 0."""
    if value is None:
        return None
    return format(Decimal(str(value)).quantize(Decimal("0.01")), "f")


def worst_state(states: tuple[str, ...]) -> str:
    if not states:
        return DATA_REJECT
    return max(states, key=lambda s: DATA_STATE_RANK.get(s, DATA_STATE_RANK[DATA_REJECT]))


@dataclass(frozen=True)
class SourceRead:
    """One SELECT-only read from the DataLake, with its provenance."""

    source: str
    observed_at: str
    rows: tuple[dict[str, Any], ...] = ()
    reason_codes: tuple[str, ...] = ()
    available: bool = True

    @property
    def row_count(self) -> int:
        return len(self.rows)


@dataclass(frozen=True)
class Section:
    """A dossier section: payload plus the evidence needed to trust it."""

    section_id: str
    state: str
    payload: dict[str, Any]
    sources: tuple[str, ...]
    observed_at: str | None
    row_count: int
    reason_codes: tuple[str, ...] = ()
    missingness: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "section_id": self.section_id,
            "state": self.state,
            "sources": list(self.sources),
            "observed_at": self.observed_at,
            "row_count": self.row_count,
            "reason_codes": list(self.reason_codes),
            "missingness": self.missingness,
            "payload": self.payload,
        }


@dataclass(frozen=True)
class Finding:
    """A fact plus the question it opens. Never an assertion of a right."""

    finding_id: str
    subject: str
    fact: str
    question: str
    evidence_refs: tuple[str, ...]
    severity: str = "INFORMATIONAL"
    metrics: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "subject": self.subject,
            "fact": self.fact,
            "question": self.question,
            "evidence_refs": list(self.evidence_refs),
            "severity": self.severity,
            "metrics": dict(sorted(self.metrics.items())),
        }


@dataclass(frozen=True)
class DossierRequest:
    cnpj: str
    as_of: str
    catalog_mode: str
    consumer_id: str
    producer_sha: str | None = None
    competitor_limit: int | None = None
    expiring_window_days: int | None = None
    reference_scope: str = REFERENCE_SCOPE_BOTH


@dataclass(frozen=True)
class DossierResult:
    request: DossierRequest
    dossier_id: str
    data_state: str
    sections: tuple[Section, ...]
    findings: tuple[Finding, ...]
    reason_codes: tuple[str, ...]
    limitations: tuple[str, ...]

    @property
    def is_ready(self) -> bool:
        return self.data_state == DATA_READY

    @property
    def is_hold(self) -> bool:
        return self.data_state == DATA_HOLD

"""Canonical types for corporate email-pattern inference.

A pattern is derived evidence, never an observation. MX is not a mailbox.
SMTP accept is not identity. Catch-all lowers evidentiary value.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from scripts.decision_unit_intelligence.email_discovery import (
    EMAIL_DISCOVERY_POLICY_VERSION,
    PATTERN_EVIDENCE_VERSION,
    EmailDiscoveryClass,
)
from scripts.decision_unit_intelligence.models import EpistemicClass

PATTERN_ENGINE_VERSION = "dui.email-patterns.v1"
DEFAULT_CANDIDATE_BUDGET = 2
STRONG_MIN_INDEPENDENT = 3
SUBSTANTIAL_CONFLICT_RATIO = 0.34

# Pattern ids that may be derived from OBSERVED person mail. No blind extras.
SUPPORTED_PATTERN_IDS = (
    "first.last",
    "firstlast",
    "first_initial+last",
    "first+last_initial",
    "last.first",
    "first",
    "alias",
    "first.compoundlast",
)

INFERRED_PATTERN_DISCOVERY_CLASSES = frozenset(
    {
        EmailDiscoveryClass.INFERRED_PATTERN_EMAIL.value,
        "INFERRED_PATTERN_MX_OK",
        "INFERRED_PATTERN_CATCH_ALL",
        "INFERRED_PATTERN_REJECTED",
    }
)


class PatternState(StrEnum):
    PATTERN_OBSERVED = "PATTERN_OBSERVED"
    PATTERN_STRONG = "PATTERN_STRONG"
    PATTERN_AMBIGUOUS = "PATTERN_AMBIGUOUS"


class InferredPatternState(StrEnum):
    INFERRED_PATTERN_EMAIL = "INFERRED_PATTERN_EMAIL"
    INFERRED_PATTERN_MX_OK = "INFERRED_PATTERN_MX_OK"
    INFERRED_PATTERN_CATCH_ALL = "INFERRED_PATTERN_CATCH_ALL"
    INFERRED_PATTERN_REJECTED = "INFERRED_PATTERN_REJECTED"


class InferredGrade(StrEnum):
    INFERRED_HIGH = "INFERRED_HIGH"
    INFERRED_UNVERIFIED = "INFERRED_UNVERIFIED"


@dataclass(frozen=True)
class EmailPatternPolicy:
    candidate_budget: int = DEFAULT_CANDIDATE_BUDGET
    strong_min_independent: int = STRONG_MIN_INDEPENDENT
    smtp_authorized: bool = False
    pattern_version: str = PATTERN_EVIDENCE_VERSION
    engine_version: str = PATTERN_ENGINE_VERSION
    discovery_policy_version: str = EMAIL_DISCOVERY_POLICY_VERSION


@dataclass(frozen=True)
class ObservedPersonEmail:
    """An OBSERVED mailbox already bound to a real person on a corporate domain."""

    email: str
    person_name: str
    domain: str
    source_url: str | None = None
    observed_at: str | None = None
    epistemic_class: EpistemicClass = EpistemicClass.OBSERVED
    person_id: str | None = None
    account_id: str | None = None
    source_type: str = "public_page"


@dataclass(frozen=True)
class KnownPerson:
    person_name: str
    corroborated: bool = True
    person_id: str | None = None
    account_id: str | None = None
    already_has_observed_email: bool = False


@dataclass(frozen=True)
class PatternSupportExample:
    email: str
    person_name: str
    person_id: str | None
    source_url: str | None
    observed_at: str | None
    account_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PatternRecord:
    pattern_id: str
    domain: str
    version: str
    state: PatternState
    score: float
    supporting_examples: tuple[PatternSupportExample, ...]
    supporting_emails: tuple[str, ...]
    supporting_people: tuple[str, ...]
    source_urls: tuple[str, ...]
    observed_at: tuple[str, ...]
    exclusions: tuple[str, ...]
    conflicts: tuple[str, ...]
    independent_example_count: int
    consistency: float
    freshness: float
    reason_codes: tuple[str, ...]
    epistemic_class: EpistemicClass
    separator: str = ""
    alias_tokens: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["state"] = self.state.value
        payload["epistemic_class"] = self.epistemic_class.value
        return payload


@dataclass(frozen=True)
class TechnicalCheck:
    syntax: str
    domain: str
    dns: str
    mx: str
    catch_all: str
    smtp: str
    reason_codes: tuple[str, ...]
    mx_is_not_mailbox_proof: bool = True
    smtp_is_not_identity_proof: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PatternCandidate:
    email: str
    person_name: str
    person_id: str | None
    account_id: str | None
    domain: str
    pattern_id: str
    pattern_state: PatternState
    candidate_state: InferredPatternState
    inferred_grade: InferredGrade
    epistemic_class: EpistemicClass
    discovery_class: str
    supporting_emails: tuple[str, ...]
    supporting_people: tuple[str, ...]
    source_urls: tuple[str, ...]
    reason_codes: tuple[str, ...]
    technical: TechnicalCheck | None = None
    mx_is_not_mailbox_proof: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["pattern_state"] = self.pattern_state.value
        payload["candidate_state"] = self.candidate_state.value
        payload["inferred_grade"] = self.inferred_grade.value
        payload["epistemic_class"] = self.epistemic_class.value
        return payload


@dataclass
class EmailPatternResult:
    domain: str | None
    ingested: tuple[ObservedPersonEmail, ...] = ()
    exclusions: tuple[str, ...] = ()
    patterns: tuple[PatternRecord, ...] = ()
    candidates: tuple[PatternCandidate, ...] = ()
    reason_codes: tuple[str, ...] = ()
    policy: EmailPatternPolicy = field(default_factory=EmailPatternPolicy)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": "confenge.email_patterns.v1",
            "engine_version": self.policy.engine_version,
            "pattern_version": self.policy.pattern_version,
            "domain": self.domain,
            "ingested": [asdict(item) | {"epistemic_class": item.epistemic_class.value} for item in self.ingested],
            "exclusions": list(self.exclusions),
            "patterns": [item.to_dict() for item in self.patterns],
            "candidates": [item.to_dict() for item in self.candidates],
            "reason_codes": list(self.reason_codes),
            "policy": asdict(self.policy),
        }

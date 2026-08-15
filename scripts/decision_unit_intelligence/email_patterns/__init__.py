"""Isolated corporate email-pattern engine.

OBSERVED same-domain person emails → supported pattern → INFERRED candidate.
A pattern is never an observation. MX/SMTP never prove identity.
"""

from scripts.decision_unit_intelligence.email_patterns.engine import (
    InjectedTechnicalAdapter,
    PassiveVerifierAdapter,
    apply_technical_checks,
    assert_pattern_not_promoted_to_observed,
    candidate_to_evidence,
    derive_domain_patterns,
    emit_pattern_candidates,
    ingest_observed_person_emails,
    is_inferred_pattern_discovery_class,
    run_email_patterns,
)
from scripts.decision_unit_intelligence.email_patterns.types import (
    DEFAULT_CANDIDATE_BUDGET,
    INFERRED_PATTERN_DISCOVERY_CLASSES,
    PATTERN_ENGINE_VERSION,
    STRONG_MIN_INDEPENDENT,
    EmailPatternPolicy,
    EmailPatternResult,
    InferredGrade,
    InferredPatternState,
    KnownPerson,
    ObservedPersonEmail,
    PatternCandidate,
    PatternRecord,
    PatternState,
    TechnicalCheck,
)

__all__ = [
    "DEFAULT_CANDIDATE_BUDGET",
    "INFERRED_PATTERN_DISCOVERY_CLASSES",
    "PATTERN_ENGINE_VERSION",
    "STRONG_MIN_INDEPENDENT",
    "EmailPatternPolicy",
    "EmailPatternResult",
    "InferredGrade",
    "InferredPatternState",
    "InjectedTechnicalAdapter",
    "KnownPerson",
    "ObservedPersonEmail",
    "PassiveVerifierAdapter",
    "PatternCandidate",
    "PatternRecord",
    "PatternState",
    "TechnicalCheck",
    "apply_technical_checks",
    "assert_pattern_not_promoted_to_observed",
    "candidate_to_evidence",
    "derive_domain_patterns",
    "emit_pattern_candidates",
    "ingest_observed_person_emails",
    "is_inferred_pattern_discovery_class",
    "run_email_patterns",
]

"""Pure domain logic for reajuste 14.133 (no I/O)."""

from scripts.commercial.reajuste_14133.domain.dates import (
    DateField,
    consolidate_dates,
    interregno_days,
    next_anniversary,
)
from scripts.commercial.reajuste_14133.domain.eligibility import (
    EligibilityResult,
    evaluate_eligibility,
)
from scripts.commercial.reajuste_14133.domain.finance import (
    FinanceEstimate,
    estimate_reajuste,
)
from scripts.commercial.reajuste_14133.domain.obra_classifier import (
    ConstructionClassification,
    classify_construction,
)
from scripts.commercial.reajuste_14133.domain.regime import (
    RegimeResult,
    classify_legal_regime,
)
from scripts.commercial.reajuste_14133.domain.scoring import (
    ScoreBreakdown,
    score_lead,
)

__all__ = [
    "DateField",
    "consolidate_dates",
    "interregno_days",
    "next_anniversary",
    "EligibilityResult",
    "evaluate_eligibility",
    "FinanceEstimate",
    "estimate_reajuste",
    "ConstructionClassification",
    "classify_construction",
    "RegimeResult",
    "classify_legal_regime",
    "ScoreBreakdown",
    "score_lead",
]

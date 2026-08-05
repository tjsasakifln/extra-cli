"""Pure domain logic for reajuste 14.133 (no I/O)."""

from scripts.commercial.reajuste_14133.domain.data_base_exact import (
    EXACT_DATA_BASE_SATISFYING,
    extract_exact_data_base,
    is_exact_data_base_state,
)
from scripts.commercial.reajuste_14133.domain.dates import (
    DateField,
    consolidate_dates,
    interregno_days,
    next_anniversary,
)
from scripts.commercial.reajuste_14133.domain.document_link import (
    DOCUMENT_LINK_CONFLICT,
    DOCUMENT_LINK_PARTIAL,
    DOCUMENT_LINK_UNVERIFIED,
    DOCUMENT_LINK_VERIFIED,
    invalidate_signals_on_conflict,
    verify_document_link,
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
from scripts.commercial.reajuste_14133.domain.outreach import (
    OutreachResult,
    evaluate_outreach,
)
from scripts.commercial.reajuste_14133.domain.regime import (
    RegimeResult,
    classify_legal_regime,
)
from scripts.commercial.reajuste_14133.domain.scoring import (
    ScoreBreakdown,
    score_lead,
)
from scripts.commercial.reajuste_14133.domain.supplier_portfolio import (
    consolidate_suppliers,
    dedupe_economic_opportunities,
)
from scripts.commercial.reajuste_14133.domain.value_quality import (
    ValueQualityResult,
    validate_contract_value,
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
    "OutreachResult",
    "evaluate_outreach",
    "RegimeResult",
    "classify_legal_regime",
    "ScoreBreakdown",
    "score_lead",
    "consolidate_suppliers",
    "dedupe_economic_opportunities",
    "ValueQualityResult",
    "validate_contract_value",
    "verify_document_link",
    "invalidate_signals_on_conflict",
    "DOCUMENT_LINK_VERIFIED",
    "DOCUMENT_LINK_PARTIAL",
    "DOCUMENT_LINK_CONFLICT",
    "DOCUMENT_LINK_UNVERIFIED",
    "extract_exact_data_base",
    "is_exact_data_base_state",
    "EXACT_DATA_BASE_SATISFYING",
]

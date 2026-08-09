"""Indexability Quality Gate for organic / programmatic / data-driven pages.

HTML generation ≠ permission to index. This gate is mandatory and fail-closed.
"""

from __future__ import annotations

from typing import Any

# Minimum thresholds (parametrizable via kwargs)
DEFAULT_MIN_SAMPLE = 8
DEFAULT_MIN_SCORE = 55
DEFAULT_MIN_DIFFERENTIATION = 0.35


def indexability_quality_gate(
    *,
    distinct_intent: bool,
    own_information: bool,
    sample_size: int = 0,
    semantic_differentiation: float = 0.0,
    independent_utility: bool,
    data_confidence: float = 0.0,
    non_redundant: bool,
    no_cannibalization: bool,
    has_context_interpretation: bool,
    identifiable_update: bool,
    useful_internal_links: bool,
    contextual_cta: bool,
    has_provenance: bool,
    min_sample: int = DEFAULT_MIN_SAMPLE,
    min_score: int = DEFAULT_MIN_SCORE,
    content_value_score: int = 0,
    legal_safe: bool = True,
) -> dict[str, Any]:
    """Return gate decision. indexable only if all mandatory criteria pass."""
    fails: list[str] = []
    warnings: list[str] = []

    checks = {
        "distinct_intent": distinct_intent,
        "own_information": own_information,
        "sample_sufficient": int(sample_size) >= int(min_sample),
        "semantic_differentiation": float(semantic_differentiation) >= DEFAULT_MIN_DIFFERENTIATION,
        "independent_utility": independent_utility,
        "data_confidence": float(data_confidence) >= 0.45,
        "non_redundant": non_redundant,
        "no_cannibalization": no_cannibalization,
        "has_context_interpretation": has_context_interpretation,
        "identifiable_update": identifiable_update,
        "useful_internal_links": useful_internal_links,
        "contextual_cta": contextual_cta,
        "has_provenance": has_provenance,
        "legal_safe": legal_safe,
        "content_value_floor": int(content_value_score) >= int(min_score),
    }

    labels = {
        "distinct_intent": "intent_not_distinct",
        "own_information": "no_own_information",
        "sample_sufficient": f"sample<{min_sample}",
        "semantic_differentiation": "low_semantic_differentiation",
        "independent_utility": "no_independent_utility",
        "data_confidence": "low_data_confidence",
        "non_redundant": "redundant_content",
        "no_cannibalization": "cannibalization_risk",
        "has_context_interpretation": "missing_interpretation",
        "identifiable_update": "no_identifiable_update",
        "useful_internal_links": "missing_internal_links",
        "contextual_cta": "missing_contextual_cta",
        "has_provenance": "missing_provenance",
        "legal_safe": "legal_risk",
        "content_value_floor": f"score<{min_score}",
    }

    for key, ok in checks.items():
        if not ok:
            fails.append(labels[key])

    # Soft warnings (do not block alone)
    if int(sample_size) < min_sample * 2:
        warnings.append("sample_thin_margin")
    if float(semantic_differentiation) < 0.55:
        warnings.append("differentiation_marginal")

    indexable = len(fails) == 0
    if not indexable:
        decision = "noindex"
        if "cannibalization_risk" in fails or "redundant_content" in fails:
            decision = "merge_or_canonical"
        if "sample<" in " ".join(fails) or "no_own_information" in fails:
            decision = "do_not_create"
    else:
        decision = "indexable_candidate"

    return {
        "indexable": indexable,
        "decision": decision,
        "fails": fails,
        "warnings": warnings,
        "checks": checks,
        "note": (
            "Indexability Quality Gate is mandatory. Score cannot compensate "
            "for failed criteria. Generated HTML is not index permission."
        ),
    }


def gate_from_opportunity(opp: dict[str, Any], **overrides: Any) -> dict[str, Any]:
    """Apply gate using fields commonly present on opportunity dicts.

    Existing service/editorial improves use a lighter sample floor (min_sample=1)
    because the asset already exists; new programmatic/data pages stay strict.
    """
    dl = opp.get("datalake_evidence") or {}
    sample = int(
        overrides.get(
            "sample_size",
            dl.get("record_count")
            or dl.get("contract_count")
            or opp.get("sample_size")
            or 0,
        )
    )
    unique = bool(opp.get("unique_data_available"))
    action = str(opp.get("action") or "")
    source = str(opp.get("source") or "")
    cannibal = opp.get("cannibalization") or {}
    score = int((opp.get("score") if opp.get("score") is not None else 0) or 0)
    existing = bool(opp.get("existing_url"))
    is_existing_editorial = existing and action in {"improve", "keep"} and (
        source in {"demand_graph", "gsc_page", "datalake_problem_service"}
        or str(dl.get("dataset") or "") == "web-cfg-editorial"
    )

    # New programmatic pages need real sample; existing pages are not "created"
    min_sample = 1 if is_existing_editorial else DEFAULT_MIN_SAMPLE
    min_score = 40 if is_existing_editorial else DEFAULT_MIN_SCORE
    if is_existing_editorial and sample < 1:
        sample = 1

    kwargs = {
        "distinct_intent": bool(opp.get("distinct_intent", True)),
        "own_information": unique
        or bool(opp.get("own_information"))
        or is_existing_editorial,
        "sample_size": sample,
        "semantic_differentiation": float(
            opp.get("semantic_differentiation")
            or (0.7 if unique else 0.55 if is_existing_editorial else 0.25)
        ),
        "independent_utility": bool(
            opp.get("independent_utility", unique or action in {"improve", "keep"})
        ),
        "data_confidence": float(opp.get("confidence") or dl.get("confidence") or 0.5),
        "non_redundant": not bool(cannibal.get("risk") or cannibal.get("urls")),
        "no_cannibalization": not bool(cannibal.get("risk")),
        "has_context_interpretation": bool(
            opp.get("has_interpretation")
            or (opp.get("rationale") and len(str(opp.get("rationale"))) > 40)
        ),
        "identifiable_update": bool(
            opp.get("freshness") or dl.get("as_of") or dl.get("data_as_of") or is_existing_editorial
        ),
        "useful_internal_links": bool(opp.get("suggested_internal_links")),
        "contextual_cta": bool(opp.get("suggested_cta") or opp.get("service_fit")),
        "has_provenance": bool(
            dl.get("dataset") or dl.get("sources") or opp.get("provenance") or is_existing_editorial
        ),
        "content_value_score": score,
        "legal_safe": "legal_risk" not in (opp.get("penalties") or []),
        "min_sample": min_sample,
        "min_score": min_score,
    }
    kwargs.update(
        {
            k: v
            for k, v in overrides.items()
            if k
            in kwargs
            or k
            in {
                "min_sample",
                "min_score",
                "legal_safe",
                "content_value_score",
            }
        }
    )
    return indexability_quality_gate(**kwargs)

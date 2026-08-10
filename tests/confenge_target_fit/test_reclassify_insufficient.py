"""PROBABLE without positive evidence must reclassify to INSUFFICIENT."""

from __future__ import annotations

from scripts.confenge_target_fit.reclassify_insufficient import (
    should_downgrade_probable_to_insufficient,
)


def test_default_research_empty_evidence_downgrades() -> None:
    assert should_downgrade_probable_to_insufficient(
        reason_codes=["default_research"],
        evidence=[],
    )


def test_positive_evidence_keeps_probable() -> None:
    assert not should_downgrade_probable_to_insufficient(
        reason_codes=["possible_or_single_execution_needs_research"],
        evidence=[{"type": "CONTRACT_EXECUTION", "excerpt": "pavimentacao"}],
    )


def test_cnae_positive_reason_without_evidence_list_still_needs_payload() -> None:
    # Empty evidence + only default → downgrade
    assert should_downgrade_probable_to_insufficient(
        reason_codes=["default_research", "CONSORTIUM_EVIDENCE"],
        evidence=None,
    )


def test_consortium_only_evidence_is_not_positive_icp() -> None:
    assert should_downgrade_probable_to_insufficient(
        reason_codes=["default_research", "CONSORTIUM_EVIDENCE"],
        evidence=[
            {
                "id": "consortium",
                "type": "CONSORTIUM_EVIDENCE",
                "excerpt": "consortium contracts present",
            }
        ],
    )

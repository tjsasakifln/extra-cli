"""#350: aggregated evidence never proves entity coverage."""

from __future__ import annotations

from scripts.coverage.covered_entity import MISSING_EVIDENCE
from scripts.national_claims.gate import decide
from scripts.national_claims.identity import dual_coverage_from_rows, split_evidence
from scripts.national_claims.loader import request_from_dict
from scripts.national_claims.models import EvidenceRow
from scripts.national_claims.sample_fixtures import fixture_source_wide_only


def test_aggregated_evidence_does_not_prove_entity_coverage() -> None:
    request = request_from_dict(fixture_source_wide_only())
    split = split_evidence(request.evidence)
    assert split.source_wide_count == 1
    assert split.mapped_count == 0
    gate = dual_coverage_from_rows(request.evidence)
    assert gate["classification"] == MISSING_EVIDENCE
    assert gate["numerator_rows"] == []
    assert gate["measurement_success"] is False
    payload = decide(request)
    assert payload["identity"]["source_wide"] == 1
    assert payload["identity"]["proves_entity_coverage"] is False
    assert payload["identity"]["proves_dual_coverage"] is False
    assert "aggregated_evidence_not_entity_coverage" in payload["reason_codes"]
    assert payload["authorization_state"] != "AUTHORIZED"


def test_unmappable_is_fail_closed_and_kept() -> None:
    rows = (
        EvidenceRow(
            source="pncp",
            entity_id="ghost",
            state="success_with_data",
            metadata={"identity_status": "unmappable"},
        ),
    )
    split = split_evidence(rows)
    assert split.unmappable_count == 1
    gate = dual_coverage_from_rows(rows)
    assert gate["reason"] == "unmappable_evidence_cannot_drop"
    assert gate["numerator_rows"] == []


def test_source_wide_row_is_not_silently_dropped() -> None:
    rows = (
        EvidenceRow(
            source="pncp",
            entity_id=None,
            canonical_entity_key=None,
            count_obtained=800,
            metadata={"pipeline": "resilient_cycle"},
        ),
        EvidenceRow(
            source="pncp",
            entity_id="10",
            canonical_entity_key="ent-10",
            state="success_with_data",
            metadata={},
        ),
    )
    split = split_evidence(rows)
    assert split.source_wide_count == 1
    assert split.mapped_count == 1
    gate = dual_coverage_from_rows(rows)
    assert gate["source_wide_count"] == 1
    assert len(gate["numerator_rows"]) == 1

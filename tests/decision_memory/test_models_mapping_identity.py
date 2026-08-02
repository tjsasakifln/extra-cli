"""Unit tests: models, mapping, identity, temporal, idempotency (no DB)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from scripts.decision_memory.idempotency import decision_idempotency_key
from scripts.decision_memory.identity import (
    IdentityConflict,
    extract_source_identifiers,
    index_identifier_keys,
    resolve_opportunity_key,
)
from scripts.decision_memory.mapping import MappingAmbiguousError, map_legacy_decision
from scripts.decision_memory.models import (
    ActionRecordInput,
    DecisionRecordInput,
    HumanDecision,
    OutcomeRecordInput,
    OutcomeType,
)
from scripts.decision_memory.temporal import (
    TemporalIntegrity,
    classify_decision_temporal,
    classify_outcome_temporal,
    is_strong_prospective,
)


def test_legacy_mapping() -> None:
    assert map_legacy_decision("ACCEPT")[0] is HumanDecision.GO
    assert map_legacy_decision("DEFER")[0] is HumanDecision.REVIEW
    assert map_legacy_decision("REJECT")[0] is HumanDecision.NO_GO
    with pytest.raises(MappingAmbiguousError):
        map_legacy_decision("MAYBE")
    with pytest.raises(MappingAmbiguousError):
        map_legacy_decision(None)


def test_decision_requires_actor_and_justification() -> None:
    with pytest.raises(ValidationError):
        DecisionRecordInput(
            client_id="c",
            opportunity_key="o",
            actor="",
            justification="ok",
            human_decision=HumanDecision.GO,
        )
    with pytest.raises(ValidationError):
        DecisionRecordInput(
            client_id="c",
            opportunity_key="o",
            actor="a",
            justification="  ",
            human_decision=HumanDecision.GO,
        )


def test_action_owner_due_policy() -> None:
    from uuid import uuid4

    with pytest.raises(ValidationError):
        ActionRecordInput(
            client_id="c",
            decision_event_id=uuid4(),
            opportunity_key="o",
            description="do thing",
            actor="a",
            # no owner, no reason
        )
    ok = ActionRecordInput(
        client_id="c",
        decision_event_id=uuid4(),
        opportunity_key="o",
        description="do thing",
        actor="a",
        owner_absent_reason="to be assigned in board",
        due_absent_reason="deadline unknown at decision time",
    )
    assert ok.owner is None


def test_outcome_requires_evidence() -> None:
    with pytest.raises(ValidationError):
        OutcomeRecordInput(
            client_id="c",
            opportunity_key="o",
            outcome_type=OutcomeType.WIN,
            observed_at=datetime.now(UTC),
            source="pncp",
            evidence_hash="",
            actor="a",
        )


def test_identity_deterministic_and_conflict() -> None:
    key1 = resolve_opportunity_key(
        client_id="c",
        identifiers={"numero_controle_pncp": "ABC-1"},
    )
    key2 = resolve_opportunity_key(
        client_id="c",
        identifiers={"numero_controle_pncp": "ABC-1"},
    )
    assert key1 == key2 == "ABC-1"
    idx = index_identifier_keys(
        [
            ("KEY-A", {"external_id": "x1"}),
            ("KEY-B", {"external_id": "x1"}),
        ]
    )
    with pytest.raises(IdentityConflict):
        resolve_opportunity_key(
            client_id="c",
            identifiers={"external_id": "x1"},
            explicit_key="KEY-A",
            known_keys_for_identifiers=idx,
        )


def test_extract_identifiers_from_actionable_shape() -> None:
    ids = extract_source_identifiers(
        {
            "opportunity_id": "op-1",
            "evidence": {"numero_controle_pncp": "pncp-9"},
            "source": "pncp",
        }
    )
    assert ids["opportunity_id"] == "op-1"
    assert ids["numero_controle_pncp"] == "pncp-9"


def test_idempotency_stable() -> None:
    a = decision_idempotency_key(
        client_id="c",
        opportunity_key="o",
        human_decision="GO",
        actor="a",
        justification="j",
        decided_at="2026-01-01T00:00:00Z",
        evidence_hash="e",
        legacy_decision="ACCEPT",
    )
    b = decision_idempotency_key(
        client_id="c",
        opportunity_key="o",
        human_decision="GO",
        actor="a",
        justification="j",
        decided_at="2026-01-01T00:00:00Z",
        evidence_hash="e",
        legacy_decision="ACCEPT",
    )
    assert a == b
    assert a.startswith("dm.decision:")


def test_temporal_integrity() -> None:
    now = datetime.now(UTC)
    assert (
        classify_decision_temporal(
            decided_at=now,
            first_outcome_at=None,
            is_backfill=False,
        )
        is TemporalIntegrity.PROSPECTIVE
    )
    assert (
        classify_decision_temporal(
            decided_at=now,
            first_outcome_at=now - timedelta(days=1),
            is_backfill=True,
            order_provable=False,
        )
        is TemporalIntegrity.HISTORICAL_UNVERIFIED
    )
    assert (
        classify_outcome_temporal(
            observed_at=now,
            prior_decision_at=None,
            is_backfill=False,
        )
        is TemporalIntegrity.OUTCOME_WITHOUT_PRIOR_DECISION
    )
    assert is_strong_prospective(TemporalIntegrity.PROSPECTIVE)
    assert not is_strong_prospective(TemporalIntegrity.HISTORICAL_UNVERIFIED)


def test_client_id_required_no_silent_extra() -> None:
    from scripts.decision_memory.db import require_client_id

    with pytest.raises(ValueError, match="client_id"):
        require_client_id(None)
    with pytest.raises(ValueError, match="client_id"):
        require_client_id("  ")
    assert require_client_id("acme") == "acme"

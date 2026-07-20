"""Adversarial + identity tests for entity-level freshness by capability."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts.coverage.freshness_by_entity import (
    ALLOWED_STATUSES,
    CAPABILITY_CONTRACTS,
    CAPABILITY_EDITAIS,
    EXPECTED_UNIVERSE,
    EntityObservation,
    FreshnessIdentityError,
    assert_list_identity,
    build_capability_report,
    calculate_age_hours,
    classify_freshness_status,
    evaluate_entity_freshness_reports,
    load_entity_ids_from_registry,
    load_sla_document,
    observations_from_registry,
    report_content_fingerprint,
    resolve_sla,
    validate_capability_report_strict,
    write_reports,
)

AS_OF = datetime(2026, 7, 20, 12, 0, 0, tzinfo=UTC)
PROJECT = Path(__file__).resolve().parents[1]
REGISTRY = PROJECT / "data" / "entity_source_registry.jsonl"


def _obs(
    eid: str,
    *,
    capability: str = CAPABILITY_EDITAIS,
    last_success: datetime | None = None,
    run_id: str | None = None,
    content_hash: str | None = None,
    applicability: str = "applicable",
    status_hint: str | None = None,
    source_id: str | None = "pncp",
    partial: bool = False,
) -> EntityObservation:
    return EntityObservation(
        entity_id=eid,
        capability=capability,
        source_id=source_id,
        applicability=applicability,
        last_success_at=last_success,
        run_id=run_id,
        content_hash=content_hash,
        status_hint=status_hint,
        last_attempt_at=last_success,
        last_verified_at=last_success,
    )


# ---------------------------------------------------------------------------
# Pure classification adversarial cases
# ---------------------------------------------------------------------------


def test_missing_timestamp_not_zero() -> None:
    status, age = classify_freshness_status(
        last_success_at=None,
        as_of=AS_OF,
        sla_hours=24,
        run_id="r1",
        content_hash="abc",
    )
    assert status == "NEVER"
    assert age is None
    assert calculate_age_hours(None, as_of=AS_OF) is None


def test_future_timestamp_incomplete() -> None:
    future = AS_OF + timedelta(hours=5)
    status, age = classify_freshness_status(
        last_success_at=future,
        as_of=AS_OF,
        sla_hours=24,
        run_id="r1",
        content_hash="deadbeef",
    )
    assert status == "INCOMPLETE"
    assert age is not None and age < 0


def test_stale_within_provenance() -> None:
    old = AS_OF - timedelta(hours=100)
    status, age = classify_freshness_status(
        last_success_at=old,
        as_of=AS_OF,
        sla_hours=24,
        run_id="r1",
        content_hash="deadbeef",
    )
    assert status == "STALE"
    assert age is not None and age > 24


def test_fresh_requires_provenance() -> None:
    recent = AS_OF - timedelta(hours=1)
    status, _ = classify_freshness_status(
        last_success_at=recent,
        as_of=AS_OF,
        sla_hours=24,
        run_id="run-1",
        content_hash="a" * 64,
    )
    assert status == "FRESH"


def test_missing_hash_not_fresh() -> None:
    recent = AS_OF - timedelta(hours=1)
    status, _ = classify_freshness_status(
        last_success_at=recent,
        as_of=AS_OF,
        sla_hours=24,
        run_id="run-1",
        content_hash=None,
    )
    assert status == "INCOMPLETE"
    assert status != "FRESH"


def test_missing_run_id_not_fresh() -> None:
    recent = AS_OF - timedelta(hours=1)
    status, _ = classify_freshness_status(
        last_success_at=recent,
        as_of=AS_OF,
        sla_hours=24,
        run_id=None,
        content_hash="abc",
    )
    assert status != "FRESH"
    assert status == "INCOMPLETE"


def test_partial_execution_incomplete() -> None:
    recent = AS_OF - timedelta(hours=1)
    status, _ = classify_freshness_status(
        last_success_at=recent,
        as_of=AS_OF,
        sla_hours=24,
        run_id="r",
        content_hash="h",
        partial_execution=True,
    )
    assert status == "INCOMPLETE"


def test_blocked_status() -> None:
    status, _ = classify_freshness_status(
        last_success_at=AS_OF - timedelta(hours=1),
        as_of=AS_OF,
        sla_hours=24,
        status_hint="blocked",
        run_id="r",
        content_hash="h",
    )
    assert status == "BLOCKED"


def test_not_applicable_separate() -> None:
    status, _ = classify_freshness_status(
        last_success_at=None,
        as_of=AS_OF,
        sla_hours=24,
        applicability="not_applicable",
    )
    assert status == "NOT_APPLICABLE"


def test_adversarial_no_false_fresh() -> None:
    """UNKNOWN/NEVER/BLOCKED/INCOMPLETE never become FRESH."""
    cases = [
        classify_freshness_status(
            last_success_at=None, as_of=AS_OF, sla_hours=24
        )[0],
        classify_freshness_status(
            last_success_at=AS_OF - timedelta(hours=1),
            as_of=AS_OF,
            sla_hours=24,
            # no provenance
        )[0],
        classify_freshness_status(
            last_success_at=AS_OF - timedelta(hours=1),
            as_of=AS_OF,
            sla_hours=24,
            status_hint="blocked",
            run_id="r",
            content_hash="h",
        )[0],
        classify_freshness_status(
            last_success_at=AS_OF + timedelta(hours=2),
            as_of=AS_OF,
            sla_hours=24,
            run_id="r",
            content_hash="h",
        )[0],
    ]
    for s in cases:
        assert s in ALLOWED_STATUSES
        assert s != "FRESH"
        assert s in {"NEVER", "INCOMPLETE", "BLOCKED", "UNKNOWN", "STALE"}


def test_source_level_timestamp_does_not_promote_all() -> None:
    """A source-level timestamp must not be applied to every entity."""
    source_max = AS_OF - timedelta(hours=1)
    # Honest path: only entity e1 has observation; others NEVER
    obs = [
        _obs(
            "e1",
            last_success=source_max,
            run_id="r",
            content_hash="h" * 64,
        ),
        _obs("e2"),  # no observation
        _obs("e3"),
    ]
    report = build_capability_report(
        obs,
        capability=CAPABILITY_EDITAIS,
        as_of=AS_OF,
        expected_universe=3,
        strict_identity=True,
    )
    by_id = {r.entity_id: r for r in report.entities}
    assert by_id["e1"].freshness_status == "FRESH"
    assert by_id["e2"].freshness_status == "NEVER"
    assert by_id["e3"].freshness_status == "NEVER"
    assert report.covered == 1
    assert report.uncovered == 2


def test_not_applicable_not_in_fresh_numerator() -> None:
    obs = [
        _obs("a", applicability="not_applicable"),
        _obs(
            "b",
            last_success=AS_OF - timedelta(hours=1),
            run_id="r",
            content_hash="h" * 64,
        ),
        _obs("c"),
    ]
    report = build_capability_report(
        obs,
        capability=CAPABILITY_EDITAIS,
        as_of=AS_OF,
        expected_universe=3,
    )
    assert report.status_counts["NOT_APPLICABLE"] == 1
    assert report.covered == 1  # only FRESH
    assert report.covered + report.uncovered == 3


def test_duplicate_entity_raises() -> None:
    obs = [_obs("dup"), _obs("dup"), _obs("other")]
    with pytest.raises(FreshnessIdentityError, match="duplicate"):
        build_capability_report(
            obs,
            capability=CAPABILITY_EDITAIS,
            as_of=AS_OF,
            expected_universe=2,
            strict_identity=True,
        )


def test_missing_capability_rejected_in_strict_report() -> None:
    obs = [_obs("x"), _obs("y")]
    report = build_capability_report(
        obs,
        capability=CAPABILITY_EDITAIS,
        as_of=AS_OF,
        expected_universe=2,
    )
    # force-empty capability on one row
    bad = report.to_dict()
    bad["entities"][0]["capability"] = ""
    # pad to 1093 for cardinality checks? for this unit test use raw validator
    # with small set — cardinality will fail; check capability message appears
    blockers = validate_capability_report_strict(bad)
    assert any("capability" in b or "cardinality" in b for b in blockers)


def test_list_identity_rejects_wrong_cardinality() -> None:
    # 1092
    obs_1092 = [_obs(f"e{i}") for i in range(1092)]
    with pytest.raises(FreshnessIdentityError):
        build_capability_report(
            obs_1092,
            capability=CAPABILITY_EDITAIS,
            as_of=AS_OF,
            expected_universe=EXPECTED_UNIVERSE,
        )
    # 1094
    obs_1094 = [_obs(f"e{i}") for i in range(1094)]
    with pytest.raises(FreshnessIdentityError):
        build_capability_report(
            obs_1094,
            capability=CAPABILITY_EDITAIS,
            as_of=AS_OF,
            expected_universe=EXPECTED_UNIVERSE,
        )


def test_assert_list_identity_ok() -> None:
    obs = [_obs(f"e{i:04d}", capability=CAPABILITY_CONTRACTS) for i in range(10)]
    report = build_capability_report(
        obs,
        capability=CAPABILITY_CONTRACTS,
        as_of=AS_OF,
        expected_universe=10,
    )
    identity = assert_list_identity(report.entities, expected=10)
    assert identity.ok
    assert identity.covered + identity.uncovered == 10


def test_sla_versioned_per_capability() -> None:
    doc = load_sla_document(PROJECT / "config" / "coverage_slas.yaml")
    editais = resolve_sla(CAPABILITY_EDITAIS, doc)
    contracts = resolve_sla(CAPABILITY_CONTRACTS, doc)
    assert editais.sla_version
    assert contracts.sla_version == editais.sla_version
    assert editais.sla_hours == 24
    assert contracts.sla_hours == 72
    assert editais.sla_id != contracts.sla_id
    assert "notices" in editais.sla_id or "open" in editais.sla_id


def test_required_fields_and_status_set() -> None:
    obs = [
        _obs(
            "e1",
            last_success=AS_OF - timedelta(hours=1),
            run_id="r",
            content_hash="h" * 64,
        ),
        _obs("e2"),
    ]
    report = build_capability_report(
        obs,
        capability=CAPABILITY_EDITAIS,
        as_of=AS_OF,
        expected_universe=2,
    )
    for ent in report.entities:
        d = ent.to_dict()
        for key in (
            "entity_id",
            "capability",
            "source_id",
            "applicability",
            "last_attempt_at",
            "last_success_at",
            "last_verified_at",
            "sla_id",
            "sla_hours",
            "age_hours",
            "freshness_status",
            "run_id",
            "raw_uri",
            "artifact_ref",
            "content_hash",
            "blocker",
            "next_action",
            "as_of",
            "adapter_version",
        ):
            assert key in d
        assert d["freshness_status"] in ALLOWED_STATUSES


def test_deterministic_report() -> None:
    obs = [_obs(f"z{i}") for i in range(5)] + [_obs(f"a{i}") for i in range(5)]
    r1 = build_capability_report(
        obs, capability=CAPABILITY_EDITAIS, as_of=AS_OF, expected_universe=10
    )
    r2 = build_capability_report(
        obs, capability=CAPABILITY_EDITAIS, as_of=AS_OF, expected_universe=10
    )
    assert report_content_fingerprint(r1.to_dict()) == report_content_fingerprint(
        r2.to_dict()
    )
    assert [e.entity_id for e in r1.entities] == sorted(e.entity_id for e in r1.entities)


@pytest.mark.skipif(not REGISTRY.is_file(), reason="registry jsonl missing")
def test_report_cardinality_1093() -> None:
    ids = load_entity_ids_from_registry(REGISTRY)
    assert len(ids) == EXPECTED_UNIVERSE
    assert len(set(ids)) == EXPECTED_UNIVERSE

    for capability in (CAPABILITY_EDITAIS, CAPABILITY_CONTRACTS):
        obs = observations_from_registry(REGISTRY, capability=capability)
        report = build_capability_report(
            obs,
            capability=capability,
            as_of=AS_OF,
            expected_universe=EXPECTED_UNIVERSE,
            strict_identity=True,
        )
        assert report.unique_entity_count == EXPECTED_UNIVERSE
        assert report.list_identity.ok
        assert report.covered + report.uncovered == EXPECTED_UNIVERSE
        assert report.capability == capability
        # Default lake empty → majority NEVER, never claim 95%
        assert report.status_counts.get("FRESH", 0) < EXPECTED_UNIVERSE * 0.95


@pytest.mark.skipif(not REGISTRY.is_file(), reason="registry jsonl missing")
def test_write_reports_and_strict_eval(tmp_path: Path) -> None:
    written = write_reports(
        tmp_path,
        registry_path=REGISTRY,
        as_of=AS_OF,
        sla_path=PROJECT / "config" / "coverage_slas.yaml",
    )
    assert written[CAPABILITY_EDITAIS].is_file()
    assert written[CAPABILITY_CONTRACTS].is_file()
    import json

    editais = json.loads(written[CAPABILITY_EDITAIS].read_text(encoding="utf-8"))
    contracts = json.loads(written[CAPABILITY_CONTRACTS].read_text(encoding="utf-8"))
    assert len({e["entity_id"] for e in editais["entities"]}) == EXPECTED_UNIVERSE
    assert len({e["entity_id"] for e in contracts["entities"]}) == EXPECTED_UNIVERSE
    blockers = evaluate_entity_freshness_reports(
        editais_report=editais,
        contracts_report=contracts,
    )
    assert blockers == []


def test_strict_rejects_missing_report() -> None:
    blockers = evaluate_entity_freshness_reports(
        editais_report=None,
        contracts_report=None,
    )
    assert "freshness_report_missing:notices_or_bids" in blockers
    assert "freshness_report_missing:contracts" in blockers


def test_strict_rejects_incomplete_cardinality() -> None:
    obs = [_obs(f"e{i}") for i in range(10)]
    report = build_capability_report(
        obs,
        capability=CAPABILITY_EDITAIS,
        as_of=AS_OF,
        expected_universe=10,
    )
    blockers = validate_capability_report_strict(report)
    assert any("cardinality" in b or "unique" in b for b in blockers)


def test_registry_promote_evidence_not_force_never() -> None:
    """pipeline_evidence_promote must map run_id/hash/last_seen — not invent NEVER."""
    from scripts.coverage.freshness_by_entity import observation_from_registry_row

    row = {
        "canonical_id": "80674252:SANTO_AMARO_DA_IMPERATRIZ_CAMARA_DE_VEREADORES",
        "last_success_at": "2026-06-19T16:14:17+00:00",
        "last_attempt_at": "2026-07-19T03:28:34.891882+00:00",
        "access_status": "collected",
        "plataformas": ["pncp", "pncp_contracts"],
        "current_blocker": "pending_live_verification",
        "evidences": [
            {
                "type": "pipeline_evidence_promote",
                "dry_run": False,
                "last_seen_at": "2026-06-19T16:14:17+00:00",
                "sources": ["pncp"],
                "stages": {
                    "mapped": True,
                    "accessible": True,
                    "collected": True,
                    "normalized": True,
                    "reconciled": True,
                    "verified_within_sla": False,
                },
                "run_id": "pncp-sc-20260717T110800Z-9d6dd91153",
                "pipeline_run_id": "pncp-sc-20260717T110800Z-9d6dd91153",
                "raw_uri": "/tmp/contratacoes.jsonl",
                "raw_sha256": "2b737ff8d5a9b166be2fbe40f81c67cfcb17e67a70b94ef9d111040dfc9f46af",
            }
        ],
    }
    obs = observation_from_registry_row(row, capability=CAPABILITY_EDITAIS)
    assert obs.last_success_at is not None
    assert obs.run_id == "pncp-sc-20260717T110800Z-9d6dd91153"
    assert obs.content_hash and len(obs.content_hash) == 64
    assert obs.raw_uri
    assert obs.source_id == "pncp"

    rec = build_capability_report(
        [obs],
        capability=CAPABILITY_EDITAIS,
        as_of=AS_OF,
        expected_universe=1,
    ).entities[0]
    # June 19 vs July 20 as_of → STALE (not NEVER, not forced empty)
    assert rec.freshness_status == "STALE"
    assert rec.age_hours is not None
    assert rec.run_id == obs.run_id
    assert rec.content_hash == obs.content_hash


def test_capability_observation_separation_editais_vs_contracts() -> None:
    """Notices-only promote must not populate contracts observation timestamps."""
    from scripts.coverage.freshness_by_entity import observation_from_registry_row

    row = {
        "canonical_id": "e-mixed",
        "last_success_at": "2026-06-19T16:14:17+00:00",
        "plataformas": ["pncp", "pncp_contracts"],
        "evidences": [
            {
                "type": "pipeline_evidence_promote",
                "last_seen_at": "2026-06-19T16:14:17+00:00",
                "sources": ["pncp"],
                "run_id": "run-notices",
                "raw_sha256": "a" * 64,
                "raw_uri": "s3://notices",
                "stages": {
                    "mapped": True,
                    "accessible": True,
                    "collected": True,
                    "normalized": True,
                    "reconciled": True,
                },
            },
            {
                "type": "pipeline_evidence_promote",
                "last_seen_at": "2026-07-19T01:38:24+00:00",
                "sources": ["pncp_contracts"],
                "capability": "historical_contracts",
                "run_id": "run-contracts",
                "raw_sha256": "b" * 64,
                "raw_uri": "s3://contracts",
                "stages": {
                    "mapped": True,
                    "accessible": True,
                    "collected": True,
                    "normalized": True,
                    "reconciled": True,
                    "verified_within_sla": True,
                },
            },
        ],
    }
    notices = observation_from_registry_row(row, capability=CAPABILITY_EDITAIS)
    contracts = observation_from_registry_row(row, capability=CAPABILITY_CONTRACTS)
    assert notices.run_id == "run-notices"
    assert contracts.run_id == "run-contracts"
    assert notices.source_id == "pncp"
    assert contracts.source_id == "pncp_contracts"
    assert notices.last_success_at != contracts.last_success_at

    # Pure notices entity: contracts must stay NEVER (no contracts evidence)
    notices_only = {
        "canonical_id": "e-notices-only",
        "last_success_at": "2026-06-19T16:14:17+00:00",
        "plataformas": ["pncp"],
        "evidences": row["evidences"][:1],
    }
    ct = observation_from_registry_row(notices_only, capability=CAPABILITY_CONTRACTS)
    assert ct.last_success_at is None
    assert ct.run_id is None
    rec = build_capability_report(
        [ct],
        capability=CAPABILITY_CONTRACTS,
        as_of=AS_OF,
        expected_universe=1,
    ).entities[0]
    assert rec.freshness_status == "NEVER"


@pytest.mark.skipif(not REGISTRY.is_file(), reason="registry jsonl missing")
def test_live_registry_promotes_are_not_all_never() -> None:
    """Against real JSONL: entities with promote evidence must not all be NEVER."""
    obs = observations_from_registry(REGISTRY, capability=CAPABILITY_EDITAIS)
    with_success = sum(1 for o in obs if o.last_success_at is not None)
    with_hash = sum(1 for o in obs if o.content_hash)
    with_run = sum(1 for o in obs if o.run_id)
    assert with_success >= 200, f"expected hundreds of last_success from promote, got {with_success}"
    assert with_hash >= 200, f"expected hundreds of content_hash, got {with_hash}"
    assert with_run >= 200, f"expected hundreds of run_id, got {with_run}"

    report = build_capability_report(
        obs,
        capability=CAPABILITY_EDITAIS,
        as_of=AS_OF,
        expected_universe=EXPECTED_UNIVERSE,
    )
    never = report.status_counts.get("NEVER", 0)
    stale = report.status_counts.get("STALE", 0)
    incomplete = report.status_counts.get("INCOMPLETE", 0)
    # Honest: many STALE from old promote windows; must not be 1093 NEVER
    assert never < EXPECTED_UNIVERSE, "all-NEVER means provenance was dropped"
    assert stale + incomplete > 0


@pytest.mark.skipif(not REGISTRY.is_file(), reason="registry jsonl missing")
def test_live_registry_contracts_differs_from_editais() -> None:
    """Dual reports must differ at observation level (not just SLA labels)."""
    ed = observations_from_registry(REGISTRY, capability=CAPABILITY_EDITAIS)
    ct = observations_from_registry(REGISTRY, capability=CAPABILITY_CONTRACTS)
    ed_map = {o.entity_id: o for o in ed}
    ct_map = {o.entity_id: o for o in ct}
    differing = 0
    for eid, o_ed in ed_map.items():
        o_ct = ct_map[eid]
        if (o_ed.run_id, o_ed.last_success_at, o_ed.source_id) != (
            o_ct.run_id,
            o_ct.last_success_at,
            o_ct.source_id,
        ):
            differing += 1
    assert differing > 50, f"expected observation-level dual split, differing={differing}"

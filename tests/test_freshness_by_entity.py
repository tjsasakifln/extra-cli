"""Adversarial + identity tests for entity-level freshness (canonical universe).

No skip for missing operational files: small-wave uses synthetic IDs;
full set-equality uses the real seed when present (required for identity tests).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts.coverage.freshness_by_entity import (
    ALLOWED_STATUSES,
    CAPABILITY_CONTRACTS,
    CAPABILITY_EDITAIS,
    EntityObservation,
    FreshnessIdentityError,
    assert_set_identity,
    build_acceptance_manifest,
    build_capability_report,
    calculate_age_hours,
    classify_freshness_status,
    empty_observation,
    evaluate_entity_freshness_reports,
    file_sha256,
    load_canonical_population,
    load_sla_document,
    ordered_ids_sha256,
    reconcile_registry_row,
    report_content_fingerprint,
    resolve_sla,
    verify_manifest_against_reports,
    write_reports,
)
from scripts.lib.universe import load_canonical_universe

AS_OF = datetime(2026, 7, 20, 12, 0, 0, tzinfo=UTC)
PROJECT = Path(__file__).resolve().parents[1]
SEED = PROJECT / "Extra - alvos de licitação. R-0.xlsx"
REGISTRY = PROJECT / "data" / "entity_source_registry.jsonl"

# Small-wave synthetic canonical population
WAVE0_IDS = [
    "extra-wave0-fresh",
    "extra-wave0-stale",
    "extra-wave0-never",
    "extra-wave0-inc-hash",
    "extra-wave0-inc-run",
    "extra-wave0-inc-future",
    "extra-wave0-editais-only",
    "extra-wave0-contracts-only",
    "extra-wave0-dup-a",
    "extra-wave0-noncanon-guard",  # stays NEVER unless non-canonical obs injected
]


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


def test_missing_hash_not_fresh_or_stale() -> None:
    recent = AS_OF - timedelta(hours=1)
    status, _ = classify_freshness_status(
        last_success_at=recent,
        as_of=AS_OF,
        sla_hours=24,
        run_id="run-1",
        content_hash=None,
    )
    assert status == "INCOMPLETE"
    assert status not in {"FRESH", "STALE"}

    old = AS_OF - timedelta(hours=100)
    status_old, _ = classify_freshness_status(
        last_success_at=old,
        as_of=AS_OF,
        sla_hours=24,
        run_id="run-1",
        content_hash=None,
    )
    assert status_old == "INCOMPLETE"
    assert status_old != "STALE"


def test_missing_run_id_not_fresh_or_stale() -> None:
    recent = AS_OF - timedelta(hours=1)
    status, _ = classify_freshness_status(
        last_success_at=recent,
        as_of=AS_OF,
        sla_hours=24,
        run_id=None,
        content_hash="abc",
    )
    assert status == "INCOMPLETE"
    assert status not in {"FRESH", "STALE"}


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
    cases = [
        classify_freshness_status(
            last_success_at=None, as_of=AS_OF, sla_hours=24
        )[0],
        classify_freshness_status(
            last_success_at=AS_OF - timedelta(hours=1),
            as_of=AS_OF,
            sla_hours=24,
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


# ---------------------------------------------------------------------------
# Small-wave fixture (manual review gate before scaling to 1093)
# ---------------------------------------------------------------------------


def _wave0_observations_editais() -> list[EntityObservation]:
    recent = AS_OF - timedelta(hours=2)
    old = AS_OF - timedelta(hours=100)
    future = AS_OF + timedelta(hours=3)
    return [
        _obs(
            "extra-wave0-fresh",
            last_success=recent,
            run_id="run-fresh",
            content_hash="h" * 64,
        ),
        _obs(
            "extra-wave0-stale",
            last_success=old,
            run_id="run-stale",
            content_hash="s" * 64,
        ),
        _obs("extra-wave0-never"),
        _obs(
            "extra-wave0-inc-hash",
            last_success=recent,
            run_id="run-nohash",
            content_hash=None,
        ),
        _obs(
            "extra-wave0-inc-run",
            last_success=recent,
            run_id=None,
            content_hash="x" * 64,
        ),
        _obs(
            "extra-wave0-inc-future",
            last_success=future,
            run_id="run-fut",
            content_hash="f" * 64,
        ),
        _obs(
            "extra-wave0-editais-only",
            last_success=recent,
            run_id="run-e",
            content_hash="e" * 64,
            source_id="pncp",
        ),
        # contracts-only entity: no editais obs → NEVER for editais
        # noncanon-guard: empty → NEVER
    ]


def _wave0_observations_contracts() -> list[EntityObservation]:
    recent = AS_OF - timedelta(hours=2)
    return [
        _obs(
            "extra-wave0-contracts-only",
            capability=CAPABILITY_CONTRACTS,
            last_success=recent,
            run_id="run-c",
            content_hash="c" * 64,
            source_id="pncp_contracts",
        ),
        # editais-only must NOT promote contracts
    ]


def test_wave0_classification_matrix() -> None:
    """Small wave: FRESH/STALE/NEVER/INCOMPLETE×3 + capability isolation."""
    report = build_capability_report(
        _wave0_observations_editais(),
        capability=CAPABILITY_EDITAIS,
        canonical_entity_ids=WAVE0_IDS,
        as_of=AS_OF,
        strict_identity=True,
    )
    by_id = {r.entity_id: r for r in report.entities}
    assert by_id["extra-wave0-fresh"].freshness_status == "FRESH"
    assert by_id["extra-wave0-stale"].freshness_status == "STALE"
    assert by_id["extra-wave0-never"].freshness_status == "NEVER"
    assert by_id["extra-wave0-never"].age_hours is None
    assert by_id["extra-wave0-inc-hash"].freshness_status == "INCOMPLETE"
    assert by_id["extra-wave0-inc-run"].freshness_status == "INCOMPLETE"
    assert by_id["extra-wave0-inc-future"].freshness_status == "INCOMPLETE"
    assert by_id["extra-wave0-editais-only"].freshness_status == "FRESH"
    assert by_id["extra-wave0-contracts-only"].freshness_status == "NEVER"
    assert by_id["extra-wave0-dup-a"].freshness_status == "NEVER"
    assert report.list_identity.ok
    assert report.list_identity.duplicate_count == 0
    assert report.list_identity.missing_count == 0
    assert report.list_identity.extra_count == 0
    # Breaches nominal
    breach_ids = {b["entity_id"] for b in report.breaches}
    assert "extra-wave0-never" in breach_ids
    assert "extra-wave0-stale" in breach_ids
    assert "extra-wave0-fresh" not in breach_ids


def test_wave0_capability_separation() -> None:
    editais = build_capability_report(
        _wave0_observations_editais(),
        capability=CAPABILITY_EDITAIS,
        canonical_entity_ids=WAVE0_IDS,
        as_of=AS_OF,
    )
    contracts = build_capability_report(
        _wave0_observations_contracts(),
        capability=CAPABILITY_CONTRACTS,
        canonical_entity_ids=WAVE0_IDS,
        as_of=AS_OF,
    )
    e_by = {r.entity_id: r for r in editais.entities}
    c_by = {r.entity_id: r for r in contracts.entities}
    # Editais FRESH must not make contracts FRESH
    assert e_by["extra-wave0-editais-only"].freshness_status == "FRESH"
    assert c_by["extra-wave0-editais-only"].freshness_status == "NEVER"
    # Contracts FRESH must not make editais FRESH
    assert c_by["extra-wave0-contracts-only"].freshness_status == "FRESH"
    assert e_by["extra-wave0-contracts-only"].freshness_status == "NEVER"
    # Same entity set
    assert {r.entity_id for r in editais.entities} == set(WAVE0_IDS)
    assert {r.entity_id for r in contracts.entities} == set(WAVE0_IDS)


def test_wave0_duplicate_rejected() -> None:
    obs = [
        _obs("extra-wave0-fresh"),
        _obs("extra-wave0-fresh"),
    ]
    with pytest.raises(FreshnessIdentityError, match="duplicate"):
        build_capability_report(
            obs,
            capability=CAPABILITY_EDITAIS,
            canonical_entity_ids=["extra-wave0-fresh", "extra-wave0-never"],
            as_of=AS_OF,
            strict_identity=True,
        )


def test_wave0_non_canonical_rejected() -> None:
    obs = [
        _obs("extra-wave0-fresh"),
        _obs("not-in-universe-xyz"),
    ]
    with pytest.raises(FreshnessIdentityError, match="non-canonical"):
        build_capability_report(
            obs,
            capability=CAPABILITY_EDITAIS,
            canonical_entity_ids=["extra-wave0-fresh"],
            as_of=AS_OF,
            strict_identity=True,
        )


def test_absence_not_zero_or_fresh() -> None:
    report = build_capability_report(
        [],
        capability=CAPABILITY_EDITAIS,
        canonical_entity_ids=["a", "b", "c"],
        as_of=AS_OF,
    )
    assert report.covered == 0
    assert all(r.freshness_status == "NEVER" for r in report.entities)
    assert all(r.age_hours is None for r in report.entities)


def test_source_level_timestamp_does_not_promote_all() -> None:
    source_max = AS_OF - timedelta(hours=1)
    obs = [
        _obs(
            "e1",
            last_success=source_max,
            run_id="r",
            content_hash="h" * 64,
        ),
    ]
    report = build_capability_report(
        obs,
        capability=CAPABILITY_EDITAIS,
        canonical_entity_ids=["e1", "e2", "e3"],
        as_of=AS_OF,
        strict_identity=True,
    )
    by_id = {r.entity_id: r for r in report.entities}
    assert by_id["e1"].freshness_status == "FRESH"
    assert by_id["e2"].freshness_status == "NEVER"
    assert by_id["e3"].freshness_status == "NEVER"


def test_determinism_same_as_of() -> None:
    obs = _wave0_observations_editais()
    r1 = build_capability_report(
        obs,
        capability=CAPABILITY_EDITAIS,
        canonical_entity_ids=WAVE0_IDS,
        as_of=AS_OF,
    )
    r2 = build_capability_report(
        obs,
        capability=CAPABILITY_EDITAIS,
        canonical_entity_ids=WAVE0_IDS,
        as_of=AS_OF,
    )
    assert report_content_fingerprint(r1.to_dict()) == report_content_fingerprint(
        r2.to_dict()
    )


def test_breaches_contain_entity_id_and_status() -> None:
    report = build_capability_report(
        _wave0_observations_editais(),
        capability=CAPABILITY_EDITAIS,
        canonical_entity_ids=WAVE0_IDS,
        as_of=AS_OF,
    )
    assert report.breaches
    for b in report.breaches:
        assert "entity_id" in b
        assert "freshness_status" in b
        assert b["freshness_status"] != "FRESH"


# ---------------------------------------------------------------------------
# Cardinality / set identity adversarial
# ---------------------------------------------------------------------------


def test_reject_wrong_cardinality_1092_1094() -> None:
    # Simulates wrong population sizes against a fixed expected set of 1093
    expected = [f"e{i:04d}" for i in range(1093)]
    obs_1092 = [_obs(f"e{i:04d}") for i in range(1092)]
    # 1092 observations over 1093 canonical → missing filled as NEVER, identity OK
    # To reject wrong denominator, pass wrong canonical set size:
    with pytest.raises(FreshnessIdentityError):
        # force expected 1093 but only build with 1092 ids as canonical
        short = [f"e{i:04d}" for i in range(1092)]
        build_capability_report(
            obs_1092,
            capability=CAPABILITY_EDITAIS,
            canonical_entity_ids=short,
            as_of=AS_OF,
            strict_identity=True,
        )
        # That succeeds (1092==1092). Reject via assert against 1093:
        report = build_capability_report(
            obs_1092,
            capability=CAPABILITY_EDITAIS,
            canonical_entity_ids=short,
            as_of=AS_OF,
        )
        assert_set_identity(report.entities, canonical_entity_ids=expected)

    # 1094 as canonical vs 1093 expected
    long_ids = [f"e{i:04d}" for i in range(1094)]
    report_long = build_capability_report(
        [_obs(i) for i in long_ids],
        capability=CAPABILITY_EDITAIS,
        canonical_entity_ids=long_ids,
        as_of=AS_OF,
    )
    with pytest.raises(FreshnessIdentityError):
        assert_set_identity(report_long.entities, canonical_entity_ids=expected)


def test_reject_1092_and_1094_as_canonical_vs_real_seed() -> None:
    """Explicit fail-closed when caller pretends wrong universe sizes."""
    if not SEED.is_file():
        pytest.fail(f"canonical seed required for identity tests: {SEED}")
    real_ids, _ = load_canonical_population(SEED)
    assert len(real_ids) == 1093

    # Build report for real 1093
    report = build_capability_report(
        [],
        capability=CAPABILITY_EDITAIS,
        canonical_entity_ids=real_ids,
        as_of=AS_OF,
    )
    assert report.list_identity.ok
    assert report.denominator == 1093

    # Compare against corrupted expected sets
    with pytest.raises(FreshnessIdentityError):
        assert_set_identity(report.entities, canonical_entity_ids=real_ids[:1092])
    with pytest.raises(FreshnessIdentityError):
        assert_set_identity(
            report.entities,
            canonical_entity_ids=real_ids + ["extra-forged-id"],
        )


# ---------------------------------------------------------------------------
# Full canonical set equality (real seed)
# ---------------------------------------------------------------------------


def test_set_equality_with_load_canonical_universe() -> None:
    if not SEED.is_file():
        pytest.fail(f"canonical seed required: {SEED}")
    ids, universe = load_canonical_population(SEED)
    included = sorted(e.entity_id for e in universe.included)
    assert ids == included
    assert ordered_ids_sha256(ids) == ordered_ids_sha256(included)

    report_e = build_capability_report(
        [],
        capability=CAPABILITY_EDITAIS,
        canonical_entity_ids=ids,
        as_of=AS_OF,
        seed_path=str(SEED),
        seed_sha256=universe.seed_sha256,
    )
    report_c = build_capability_report(
        [],
        capability=CAPABILITY_CONTRACTS,
        canonical_entity_ids=ids,
        as_of=AS_OF,
        seed_path=str(SEED),
        seed_sha256=universe.seed_sha256,
    )
    e_set = {r.entity_id for r in report_e.entities}
    c_set = {r.entity_id for r in report_c.entities}
    canon = set(ids)
    assert e_set == canon
    assert c_set == canon
    assert e_set == c_set
    assert report_e.list_identity.expected_ids_sha256 == ordered_ids_sha256(ids)
    assert report_e.list_identity.observed_ids_sha256 == ordered_ids_sha256(ids)
    # len alone is not enough — force wrong identity with same count
    forged = [f"forged-{i:04d}" for i in range(len(ids))]
    assert len(forged) == len(ids)
    with pytest.raises(FreshnessIdentityError):
        assert_set_identity(report_e.entities, canonical_entity_ids=forged)


def test_operational_write_reports_set_equality(tmp_path: Path) -> None:
    if not SEED.is_file() or not REGISTRY.is_file():
        pytest.fail("seed and registry required for operational identity test")
    written, reports, meta = write_reports(
        tmp_path,
        seed_path=SEED,
        registry_path=REGISTRY,
        as_of=AS_OF,
        strict=True,
    )
    ids, universe = load_canonical_population(SEED)
    assert meta["canonical_count"] == len(ids)
    assert meta["seed_sha256"] == universe.seed_sha256
    for cap in (CAPABILITY_EDITAIS, CAPABILITY_CONTRACTS):
        report = reports[cap]
        observed = {r.entity_id for r in report.entities}
        assert observed == set(ids)
        assert report.list_identity.ok
        assert report.list_identity.duplicate_count == 0
        assert report.list_identity.missing_count == 0
        assert report.list_identity.extra_count == 0
        assert report.covered + report.uncovered == len(ids)
        assert written[cap].is_file()
    blockers = evaluate_entity_freshness_reports(
        editais_report=reports[CAPABILITY_EDITAIS],
        contracts_report=reports[CAPABILITY_CONTRACTS],
        canonical_entity_ids=ids,
    )
    assert blockers == []


def test_reconcile_registry_covers_all_included() -> None:
    if not SEED.is_file() or not REGISTRY.is_file():
        pytest.fail("seed and registry required")
    universe = load_canonical_universe(SEED)
    included = {e.entity_id for e in universe.included}
    mapped: set[str] = set()
    with REGISTRY.open(encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line)
            result = reconcile_registry_row(row, universe)
            assert result.entity_id is not None, result
            assert result.entity_id in included
            assert result.entity_id not in mapped
            mapped.add(result.entity_id)
    assert mapped == included


# ---------------------------------------------------------------------------
# Manifest hash integrity
# ---------------------------------------------------------------------------


def test_manifest_hashes_and_tamper(tmp_path: Path) -> None:
    if not SEED.is_file() or not REGISTRY.is_file():
        pytest.fail("seed and registry required")
    written, reports, meta = write_reports(
        tmp_path,
        seed_path=SEED,
        registry_path=REGISTRY,
        as_of=AS_OF,
        strict=True,
    )
    sla = resolve_sla(CAPABILITY_EDITAIS, load_sla_document())
    manifest = build_acceptance_manifest(
        seed_path=SEED,
        registry_path=REGISTRY,
        as_of=AS_OF,
        sla_version=sla.sla_version,
        command=["python", "-m", "scripts.coverage.freshness_by_entity", "--strict"],
        exit_code=0,
        written=written,
        reports=reports,
        meta=meta,
    )
    assert manifest["exit_code"] == 0
    assert manifest["identity"]["duplicate_count"] == 0
    assert manifest["identity"]["missing_count"] == 0
    assert manifest["identity"]["extra_count"] == 0
    assert manifest["unreconciled_count"] == 0
    assert manifest["seed_sha256"]
    assert manifest["registry_sha256"]
    assert len(manifest["reports"][CAPABILITY_EDITAIS]["sha256"]) == 64
    assert len(manifest["reports"][CAPABILITY_CONTRACTS]["sha256"]) == 64
    # valid verification
    assert (
        verify_manifest_against_reports(
            manifest,
            editais_path=written[CAPABILITY_EDITAIS],
            contracts_path=written[CAPABILITY_CONTRACTS],
        )
        == []
    )
    # tamper editais report
    path = written[CAPABILITY_EDITAIS]
    original = path.read_text(encoding="utf-8")
    path.write_text(original + "\n", encoding="utf-8")
    blockers = verify_manifest_against_reports(
        manifest,
        editais_path=path,
        contracts_path=written[CAPABILITY_CONTRACTS],
    )
    assert "editais_sha256_mismatch" in blockers
    # restore and tamper contracts
    path.write_text(original, encoding="utf-8")
    cpath = written[CAPABILITY_CONTRACTS]
    cpath.write_text(cpath.read_text(encoding="utf-8") + " ", encoding="utf-8")
    blockers2 = verify_manifest_against_reports(
        manifest,
        editais_path=written[CAPABILITY_EDITAIS],
        contracts_path=cpath,
    )
    assert "contracts_sha256_mismatch" in blockers2


def test_sla_versioned_per_capability() -> None:
    doc = load_sla_document(PROJECT / "config" / "coverage_slas.yaml")
    editais = resolve_sla(CAPABILITY_EDITAIS, doc)
    contracts = resolve_sla(CAPABILITY_CONTRACTS, doc)
    assert editais.sla_hours == 24
    assert contracts.sla_hours == 72
    assert editais.sla_version == contracts.sla_version
    assert editais.sla_id != contracts.sla_id


def test_empty_observation_helper() -> None:
    obs = empty_observation("x", CAPABILITY_EDITAIS)
    assert obs.entity_id == "x"
    assert obs.last_success_at is None


def test_file_sha256_stable(tmp_path: Path) -> None:
    p = tmp_path / "t.bin"
    p.write_bytes(b"abc")
    assert file_sha256(p) == file_sha256(p)

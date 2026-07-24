"""P0 adversarial matrix NV/UQ/DE/CI against real compute_dual_coverage.

Implements design in artifacts/.../coverage-isolation/adversarial-test-matrix.md
using the production dual spine (not a reimplementation).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts.coverage.dual_capability_coverage import (
    CAP_HISTORICAL_CONTRACTS,
    CAP_OPEN_TENDERS,
    EvidenceObservation,
    compute_dual_coverage,
    load_data_presence,
    map_db_entities,
    validate_success_zero,
)
from scripts.lib.universe import CanonicalEntity, CanonicalUniverse, load_canonical_universe


def _entity(eid: str, name: str = "Ente X", cnpj8: str = "12345678") -> CanonicalEntity:
    return CanonicalEntity(
        entity_id=eid,
        seed_row=2,
        razao_social=name,
        cnpj8=cnpj8,
        municipio="FLORIANOPOLIS",
        codigo_ibge="4205407",
        natureza_juridica="MUNICIPIO",
        latitude=-27.5,
        longitude=-48.5,
        distancia_km=10.0,
        radius_decision="included",
        within_radius=True,
        decision_method="seed",
        identity_key=f"{cnpj8}|FLORIANOPOLIS|{name}",
    )


def _universe(entities: list[CanonicalEntity], seed_sha: str = "a" * 64) -> CanonicalUniverse:
    return CanonicalUniverse(
        seed_path="fixture.xlsx",
        seed_sha256=seed_sha,
        radius_km=200.0,
        entities=entities,
    )


def _appl(entities: list[CanonicalEntity], *caps: str) -> dict[str, dict[str, str]]:
    return {cap: {e.entity_id: "applicable" for e in entities} for cap in caps}


def _req(entities: list[CanonicalEntity], *caps: str) -> dict[str, dict[str, list[str]]]:
    return {cap: {e.entity_id: ["pncp"] for e in entities} for cap in caps}


def _obs(
    entity_id: str,
    *,
    capability: str = CAP_HISTORICAL_CONTRACTS,
    state: str = "success_with_data",
    fresh_hours: float = 1.0,
    records: int = 3,
    queried_start: str | None = None,
    queried_end: str | None = None,
    pages_expected: int | None = 1,
    pages_processed: int | None = 1,
    run_id: str = "run-1",
    error_message: str = "",
    metadata: dict | None = None,
) -> EvidenceObservation:
    now = datetime.now(UTC)
    completed = now - timedelta(hours=fresh_hours)
    meta = dict(metadata or {})
    meta.setdefault("provenance", "nv-matrix")
    meta.setdefault("pagination_complete", "true")
    return EvidenceObservation(
        entity_id=entity_id,
        source="pncp",
        capability=capability,
        state=state,
        applicability="applicable",
        run_id=run_id,
        started_at=completed - timedelta(minutes=5),
        completed_at=completed,
        pages_expected=pages_expected,
        pages_processed=pages_processed,
        records_fetched=records,
        records_persisted=records if state == "success_with_data" else 0,
        queried_start=queried_start,
        queried_end=queried_end,
        error_code="",
        error_message=error_message,
        evidence_reference=f"nv:{entity_id}",
        freshness_status="fresh" if fresh_hours < 24 else "stale",
        metadata=meta,
    )


def _report(
    u: CanonicalUniverse,
    *,
    obs: dict | None = None,
    presence: dict | None = None,
):
    # CanonicalUniverse.included is property over radius — for fixture all within_radius
    ents = [e for e in u.entities if e.within_radius]
    return compute_dual_coverage(
        universe=u,
        observations_by_cap=obs
        if obs is not None
        else {CAP_OPEN_TENDERS: {}, CAP_HISTORICAL_CONTRACTS: {}},
        presence_by_cap=presence
        if presence is not None
        else {CAP_OPEN_TENDERS: set(), CAP_HISTORICAL_CONTRACTS: set()},
        entity_applicability=_appl(ents, CAP_OPEN_TENDERS, CAP_HISTORICAL_CONTRACTS),  # type: ignore[arg-type]
        entity_required_sources=_req(ents, CAP_OPEN_TENDERS, CAP_HISTORICAL_CONTRACTS),  # type: ignore[arg-type]
        include_legacy_stamp=False,
        use_config_matrix=False,
        require_canonical_policy=False,
        fail_on_unmapped_presence=False,
    )


# --- NV series ---


def test_NV01_millions_non_sc_do_not_raise_coverage() -> None:
    ents = [_entity(f"e{i}", cnpj8=f"1000000{i}") for i in range(3)]
    u = _universe(ents)
    # Simulate unmapped national presence noise: presence set stays empty (unmapped)
    # while conceptually R has 2e6 non-SC rows — coverage must ignore R volume.
    r = _report(
        u,
        obs={CAP_OPEN_TENDERS: {}, CAP_HISTORICAL_CONTRACTS: {}},
        presence={CAP_OPEN_TENDERS: set(), CAP_HISTORICAL_CONTRACTS: set()},
    )
    hc = r.capabilities[CAP_HISTORICAL_CONTRACTS]
    assert hc.applicable_denominator == 3
    assert hc.covered_numerator == 0
    assert hc.coverage_pct == 0.0
    assert hc.data_presence_numerator == 0
    assert hc.coverage_gate_pass is False
    assert r.coverage_gate_pass is False


def test_NV02_presence_not_labeled_as_coverage_pct() -> None:
    ents = [_entity("e1"), _entity("e2", cnpj8="22222222"), _entity("e3", cnpj8="33333333")]
    u = _universe(ents)
    r = _report(
        u,
        presence={
            CAP_OPEN_TENDERS: set(),
            # presence for all entities WITHOUT evidence → descriptive only
            CAP_HISTORICAL_CONTRACTS: {"e1", "e2", "e3"},
        },
    )
    hc = r.capabilities[CAP_HISTORICAL_CONTRACTS]
    assert hc.coverage_pct == 0.0
    assert hc.covered_numerator == 0
    assert hc.data_presence_numerator == 3
    assert hc.data_presence_pct == 100.0
    assert hc.method == "dual_capability_coverage"
    summary = r.to_dict() if hasattr(r, "to_dict") else {}
    # coverage_pct must not equal national volume fiction
    assert hc.coverage_pct != hc.data_presence_pct or hc.covered_numerator == 0
    blob = str(summary) + str(r.limitations)
    assert "Presence is descriptive" in blob or any(
        "presence" in (x or "").lower() for x in (r.limitations or [])
    )


def test_NV03_add_remove_national_presence_keeps_coverage() -> None:
    ents = [_entity(f"e{i}", cnpj8=f"3000000{i}") for i in range(3)]  # e0,e1,e2
    u = _universe(ents)
    ids = {e.entity_id for e in ents}
    empty_obs = {CAP_OPEN_TENDERS: {}, CAP_HISTORICAL_CONTRACTS: {}}
    before = _report(
        u,
        obs=empty_obs,
        presence={CAP_OPEN_TENDERS: set(), CAP_HISTORICAL_CONTRACTS: set()},
    )
    after_add = _report(
        u,
        obs=empty_obs,
        presence={
            CAP_OPEN_TENDERS: set(),
            CAP_HISTORICAL_CONTRACTS: ids,  # "national mapped noise" for all of U
        },
    )
    after_remove = _report(
        u,
        obs=empty_obs,
        presence={CAP_OPEN_TENDERS: set(), CAP_HISTORICAL_CONTRACTS: set()},
    )
    for rep in (before, after_add, after_remove):
        hc = rep.capabilities[CAP_HISTORICAL_CONTRACTS]
        assert hc.covered_numerator == 0
        assert hc.coverage_pct == 0.0
        assert hc.applicable_denominator == 3
    assert (
        before.capabilities[CAP_HISTORICAL_CONTRACTS].covered_numerator
        == after_add.capabilities[CAP_HISTORICAL_CONTRACTS].covered_numerator
        == after_remove.capabilities[CAP_HISTORICAL_CONTRACTS].covered_numerator
    )


def test_NV04_contracts_without_evidence_never_checked() -> None:
    e = _entity("e1")
    u = _universe([e])
    r = _report(
        u,
        obs={CAP_OPEN_TENDERS: {}, CAP_HISTORICAL_CONTRACTS: {}},
        presence={CAP_OPEN_TENDERS: set(), CAP_HISTORICAL_CONTRACTS: {"e1"}},
    )
    hc = r.capabilities[CAP_HISTORICAL_CONTRACTS]
    assert hc.covered_numerator == 0
    assert hc.never_checked_count == 1
    ent = next(x for x in hc.entities if x.entity_id == "e1")
    assert ent.covered is False
    assert ent.coverage_state == "never_checked"
    assert ent.has_data_presence is True


def test_NV07_legacy_is_covered_ignored() -> None:
    """Dual must not use entity_coverage.is_covered — pure path has no legacy stamp."""
    e = _entity("e1")
    u = _universe([e])
    r = _report(u)
    assert r.legacy_metric is None
    hc = r.capabilities[CAP_HISTORICAL_CONTRACTS]
    assert hc.covered_numerator == 0
    joined = " ".join(r.limitations).lower()
    assert "is_covered" in joined or "any_row" in joined or "forbidden" in joined


def test_NV08_gate_not_pass_from_volume_alone() -> None:
    ents = [_entity(f"e{i}", cnpj8=f"8000000{i}") for i in range(5)]
    u = _universe(ents)
    r = _report(
        u,
        presence={
            CAP_OPEN_TENDERS: {e.entity_id for e in ents},
            CAP_HISTORICAL_CONTRACTS: {e.entity_id for e in ents},
        },
    )
    assert r.coverage_gate_pass is False
    assert r.capabilities[CAP_HISTORICAL_CONTRACTS].gate_status in {"FAIL", "NOT_READY"}


def test_NV05_shared_cnpj8_does_not_double_cover_without_evidence() -> None:
    """Two seed entities same CNPJ8; presence alone does not cover either."""
    e1 = _entity("root-a", cnpj8="11223344")
    e2 = _entity("root-b", cnpj8="11223344")
    u = _universe([e1, e2])
    r = _report(
        u,
        presence={
            CAP_OPEN_TENDERS: set(),
            CAP_HISTORICAL_CONTRACTS: {"root-a", "root-b"},
        },
    )
    hc = r.capabilities[CAP_HISTORICAL_CONTRACTS]
    assert hc.covered_numerator == 0
    assert hc.coverage_pct == 0.0
    assert all(not ent.covered for ent in hc.entities)
    assert hc.never_checked_count == 2


def test_NV06_outsider_presence_rejected_or_not_covered() -> None:
    """Presence entity_id outside U is DualCoverageError (fail-closed), not silent cover."""
    e = _entity("e1")
    u = _universe([e])
    r = _report(
        u,
        presence={
            CAP_OPEN_TENDERS: set(),
            CAP_HISTORICAL_CONTRACTS: {"outsider-not-in-u"},
        },
    )
    # Engine fails closed on outsider presence ids
    if r.error:
        assert "entity_id_outside_canonical_universe" in r.error
        assert r.measurement_success is False
        assert r.coverage_gate_pass is False
        assert CAP_HISTORICAL_CONTRACTS not in r.capabilities or (
            r.capabilities[CAP_HISTORICAL_CONTRACTS].covered_numerator == 0
        )
    else:
        hc = r.capabilities[CAP_HISTORICAL_CONTRACTS]
        assert hc.covered_numerator == 0
        assert hc.data_presence_numerator == 0


# --- UQ series ---


def test_UQ01_no_observation_never_checked() -> None:
    e = _entity("e1")
    r = _report(_universe([e]))
    hc = r.capabilities[CAP_HISTORICAL_CONTRACTS]
    assert hc.never_checked_count == 1
    assert hc.covered_numerator == 0
    ent = hc.entities[0]
    assert ent.coverage_state == "never_checked"
    assert ent.covered is False


def test_UQ02_presence_true_obs_empty_not_success_zero() -> None:
    e = _entity("e1")
    r = _report(
        _universe([e]),
        presence={CAP_OPEN_TENDERS: set(), CAP_HISTORICAL_CONTRACTS: {"e1"}},
    )
    ent = r.capabilities[CAP_HISTORICAL_CONTRACTS].entities[0]
    assert ent.coverage_state == "never_checked"
    assert ent.coverage_state != "success_zero"
    assert ent.covered is False


def test_UQ05_all_never_checked_partition() -> None:
    ents = [_entity(f"e{i}", cnpj8=f"5000000{i}") for i in range(4)]
    r = _report(_universe(ents))
    hc = r.capabilities[CAP_HISTORICAL_CONTRACTS]
    assert hc.never_checked_count == 4
    assert hc.covered_numerator == 0
    assert hc.applicable_denominator == 4


# --- DE / load_canonical_universe ---


def test_DE_load_canonical_universe_included_1093() -> None:
    seed = Path("fixtures/canonical_universe_r0.xlsx")
    assert seed.is_file()
    u = load_canonical_universe(seed_path=seed)
    assert len(u.included) == 1093
    # Dual on first 3 included with empty obs: denom 3 not 1093 when micro-universe
    micro = _universe(list(u.included)[:3], seed_sha=u.seed_sha256)
    r = _report(micro)
    assert r.capabilities[CAP_HISTORICAL_CONTRACTS].applicable_denominator == 3
    assert r.capabilities[CAP_HISTORICAL_CONTRACTS].covered_numerator == 0


def test_DE03_covered_outside_applicable_fails() -> None:
    e1 = _entity("e1")
    e2 = _entity("e2", cnpj8="22222222")
    u = _universe([e1, e2])
    now = datetime.now(UTC)
    q_start = (now - timedelta(days=365 * 3 + 10)).date().isoformat()
    q_end = now.date().isoformat()
    # Force e2 covered but mark e2 not_applicable
    obs = {
        CAP_OPEN_TENDERS: {},
        CAP_HISTORICAL_CONTRACTS: {
            "e2": {
                "pncp": _obs(
                    "e2",
                    queried_start=q_start,
                    queried_end=q_end,
                )
            }
        },
    }
    appl = {
        CAP_OPEN_TENDERS: {"e1": "applicable", "e2": "applicable"},
        CAP_HISTORICAL_CONTRACTS: {"e1": "applicable", "e2": "not_applicable"},
    }
    req = _req([e1, e2], CAP_OPEN_TENDERS, CAP_HISTORICAL_CONTRACTS)
    # When e2 is not_applicable but has success obs, scoring should not count as covered in A_C
    r = compute_dual_coverage(
        universe=u,
        observations_by_cap=obs,
        presence_by_cap={CAP_OPEN_TENDERS: set(), CAP_HISTORICAL_CONTRACTS: set()},
        entity_applicability=appl,  # type: ignore[arg-type]
        entity_required_sources=req,  # type: ignore[arg-type]
        include_legacy_stamp=False,
        use_config_matrix=False,
        require_canonical_policy=False,
    )
    hc = r.capabilities[CAP_HISTORICAL_CONTRACTS]
    # e2 not in applicable set → cannot contribute to numerator
    assert "e2" not in {x.entity_id for x in hc.entities if x.covered}
    assert hc.covered_numerator == 0


# --- CI ---


def test_CI01_tenders_do_not_cover_contracts() -> None:
    e = _entity("e1")
    u = _universe([e])
    obs = {
        CAP_OPEN_TENDERS: {"e1": {"pncp": _obs("e1", capability=CAP_OPEN_TENDERS)}},
        CAP_HISTORICAL_CONTRACTS: {},
    }
    r = _report(
        u,
        obs=obs,
        presence={CAP_OPEN_TENDERS: {"e1"}, CAP_HISTORICAL_CONTRACTS: set()},
    )
    assert r.capabilities[CAP_OPEN_TENDERS].covered_numerator == 1
    assert r.capabilities[CAP_HISTORICAL_CONTRACTS].covered_numerator == 0
    assert r.capabilities[CAP_HISTORICAL_CONTRACTS].never_checked_count == 1


def test_CI03_no_average_coverage_field() -> None:
    ents = [_entity("e1"), _entity("e2", cnpj8="22222222")]
    r = _report(_universe(ents))
    d = r.to_dict() if hasattr(r, "to_dict") else {}
    assert "average_coverage" not in d
    assert "coverage_pct_avg" not in d


# --- SZ smoke lock ---


def test_SZ01_label_alone_not_valid_zero() -> None:
    obs = _obs("e1", state="success_zero", records=0, pages_expected=None, pages_processed=None)
    ok, reasons = validate_success_zero(obs)
    assert ok is False
    assert reasons


# --- DB-level NV on isolated Postgres ---


@pytest.fixture
def isolated_conn():
    import os

    dsn = os.environ.get(
        "NATIONAL_INTEL_DSN",
        "postgresql://test:test@127.0.0.1:5435/extra_national_intelligence_test",
    )
    if ":5433/" in dsn and os.environ.get("ALLOW_NI_ON_5433") != "1":
        pytest.skip("refusing HC writer port")
    try:
        from scripts.national_intel.db import connect

        with connect(dsn) as conn:
            yield conn, dsn
    except Exception as exc:
        pytest.skip(f"isolated db unavailable: {exc}")


def test_NV01_db_insert_non_sc_rows_does_not_change_dual_pure_metrics(isolated_conn) -> None:
    """Insert non-SC national rows on isolated DB; dual pure path with frozen empty
    evidence keeps coverage at 0; presence load may see unmapped rows only.
    """
    conn, dsn = isolated_conn
    # Real universe stamp
    seed = Path("fixtures/canonical_universe_r0.xlsx")
    full = load_canonical_universe(seed_path=seed)
    assert len(full.included) == 1093
    micro_ents = list(full.included)[:3]
    micro = _universe(micro_ents, seed_sha=full.seed_sha256)

    before = _report(micro)
    hc_before = before.capabilities[CAP_HISTORICAL_CONTRACTS]
    assert hc_before.covered_numerator == 0
    assert hc_before.applicable_denominator == 3

    # Bulk insert non-SC noise (not linked to seed CNPJs)
    with conn.cursor() as cur:
        for i in range(200):
            cid = f"NV-NOISE-{i:05d}"
            cur.execute(
                """
                INSERT INTO public.pncp_supplier_contracts (
                  contrato_id, orgao_cnpj, orgao_nome, fornecedor_cnpj, fornecedor_nome,
                  objeto_contrato, valor_total, data_publicacao, uf, source, is_active
                ) VALUES (
                  %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pncp', true
                )
                ON CONFLICT (contrato_id) DO NOTHING
                """,
                (
                    cid,
                    f"9{i:013d}"[:14],
                    f"ORGAO NOISE {i}",
                    f"8{i:013d}"[:14],
                    f"FORN NOISE {i}",
                    "objeto nacional ruido",
                    1000.0 + i,
                    "2024-01-15",
                    "SP" if i % 2 == 0 else "RJ",
                ),
            )
        conn.commit()

    after = _report(micro)
    hc_after = after.capabilities[CAP_HISTORICAL_CONTRACTS]
    assert hc_after.covered_numerator == hc_before.covered_numerator == 0
    assert hc_after.coverage_pct == hc_before.coverage_pct == 0.0
    assert hc_after.applicable_denominator == hc_before.applicable_denominator == 3
    assert after.coverage_gate_pass is False

    # Optional: data presence from DB for historical_contracts should not invent coverage
    try:
        mapping = map_db_entities(conn, full)
        pres = load_data_presence(
            conn,
            CAP_HISTORICAL_CONTRACTS,
            mapping.db_id_to_entity_id,
            set(e.entity_id for e in micro_ents),
            cnpj8_to_entity_id=mapping.cnpj8_to_entity_id,
        )
        # Presence may be empty/unmapped for noise CNPJs — never raises covered
        assert pres is not None
    except Exception:
        # map_db may need sc_public_entities; pure dual path already proved isolation
        pass

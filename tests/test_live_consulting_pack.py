"""Tests for EXTRA-LIVE-CONSULTING-PACK-01 live consulting pack.

Unit tests drive shipped functions. Isolation and schema collision are
structural. Full population path runs when CAMPAIGN_TEST_DSN has data.
"""

from __future__ import annotations

import inspect
import json
from datetime import date
from pathlib import Path

import pytest

from scripts.ops import live_consulting_pack as lcp

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _make_cnpj(base12: str) -> str:
    weights1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    weights2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]

    def digit(value: str, weights: list[int]) -> str:
        remainder = sum(int(n) * w for n, w in zip(value, weights, strict=True)) % 11
        return str(0 if remainder < 2 else 11 - remainder)

    first = base12 + digit(base12, weights1)
    return first + digit(first, weights2)


@pytest.fixture(scope="module")
def populated_campaign_dsn() -> str:
    """Seed a material deterministic population on the real isolated DB."""
    from psycopg2.extras import Json

    from scripts.testing.real_db_guard import admit_ready_connection, canonical_dsn

    dsn = canonical_dsn()
    conn, _ = admit_ready_connection(
        dsn=dsn,
        required_tables=("pncp_supplier_contracts",),
        context="live_consulting_pack",
    )
    lcp.assert_isolation(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT cnpj_8, razao_social, municipio
                FROM sc_public_entities
                WHERE raio_200km IS TRUE AND is_active IS TRUE
                ORDER BY cnpj_8
                LIMIT 12
                """
            )
            organs = cur.fetchall()
            assert len(organs) == 12
            records = []
            engineering_objects = (
                "reforma predial e obra de engenharia",
                "pavimentacao asfaltica de via publica",
                "drenagem pluvial urbana",
                "construcao de escola municipal",
            )
            for index in range(120):
                supplier = _make_cnpj(f"{20000000 + (index % 20):08d}0001")
                organ_row = organs[index % len(organs)]
                organ = _make_cnpj(f"{organ_row[0]}0001")
                records.append(
                    {
                        "contrato_id": f"REALDB-LCP-{index:03d}",
                        "orgao_cnpj": organ,
                        "orgao_nome": organ_row[1],
                        "fornecedor_cnpj": supplier,
                        "fornecedor_nome": f"Fornecedor Engenharia {index % 20:02d}",
                        "supplier_id_type": "CNPJ",
                        "supplier_identifier": supplier,
                        "supplier_country": "BR",
                        "objeto_contrato": engineering_objects[(index // 12) % 4],
                        "valor_total": str(100000 + index * 1000),
                        "data_inicio": "2025-01-15",
                        "data_fim": "2027-01-15",
                        "data_publicacao": "2025-01-10",
                        "data_assinatura": "2025-01-15",
                        "uf": "SC",
                        "municipio": organ_row[2] or "Florianopolis",
                        "source": "lcp_real_db_test",
                        "source_id": f"REALDB-LCP-{index:03d}",
                    }
                )
            cur.execute("DELETE FROM pncp_supplier_contracts WHERE source = 'lcp_real_db_test'")
            cur.execute(
                "SELECT * FROM upsert_pncp_supplier_contracts(%s::jsonb)",
                (Json(records),),
            )
            assert len(cur.fetchall()) == 120
        conn.commit()
        yield dsn
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM pncp_supplier_contracts WHERE source = 'lcp_real_db_test'")
        conn.commit()
        conn.close()


def test_mask_dsn_hides_password() -> None:
    masked = lcp.mask_dsn("postgresql://test:secret@127.0.0.1:5436/db")
    assert "secret" not in masked
    assert "test" in masked
    assert "***" in masked


def test_assert_isolation_accepts_local() -> None:
    r = lcp.assert_isolation("postgresql://test:test@127.0.0.1:5436/extra_live_pack_rc")
    assert r["isolation_ok"] is True
    assert r["production_touched"] is False


def test_assert_isolation_rejects_prod_markers() -> None:
    with pytest.raises(SystemExit) as ei:
        lcp.assert_isolation("postgresql://u:p@ec-prod:5432/extra_prod")
    assert "ISOLATION_FAIL" in str(ei.value)


def test_assert_isolation_rejects_non_local_host() -> None:
    with pytest.raises(SystemExit):
        lcp.assert_isolation("postgresql://u:p@db.example.com:5432/x")


def test_migration_060_exists_and_059_coverage_preserved() -> None:
    m060 = PROJECT_ROOT / "db/migrations/060_national_contracts_intelligence_layers.sql"
    m059 = PROJECT_ROOT / "db/migrations/059_coverage_evidence_canonical_entity_unique.sql"
    bad = PROJECT_ROOT / "db/migrations/059_national_contracts_intelligence_layers.sql"
    assert m060.is_file(), "intel layers must be renumbered to 060"
    assert m059.is_file(), "coverage spine 059 must remain"
    assert not bad.exists(), "must not collide with 059 coverage migration"
    text = m060.read_text(encoding="utf-8")
    assert "v_intel_contracts_raw_national" in text
    assert "NOT operational" in text or "NOT operational SC coverage" in text


def test_live_pack_module_entrypoint_registered() -> None:
    assert hasattr(lcp, "run_pack")
    assert hasattr(lcp, "main")
    # structural: package final + deliverables importable
    from scripts.ops import deliverable_a_org_ranking as a
    from scripts.ops import deliverable_b_competitors as b
    from scripts.ops import deliverable_package_final as pkg

    assert callable(a.build_report_from_rows)
    assert callable(b.select_competitors)
    assert callable(pkg.reconcile_package)


def test_competitor_population_counters_share_cnpj_eligibility_filter() -> None:
    source = inspect.getsource(lcp.build_deliverable_b)

    assert source.count("supplier_id_type = 'CNPJ'") >= 3


def test_national_intel_is_internal_engine() -> None:
    from scripts.national_intel import agencies, competitors

    assert callable(agencies.run_agencies)
    assert callable(competitors.run_competitors)


@pytest.mark.real_db
def test_population_stats_full_not_sample(populated_campaign_dsn: str, tmp_path: Path) -> None:
    conn = lcp.connect(populated_campaign_dsn)
    try:
        pop = lcp.population_stats(conn, uf="SC")
    finally:
        conn.close()
    assert pop["eligible_population"] >= 100
    assert pop["sample_label"] == "FULL_ELIGIBLE_POPULATION"
    assert pop["not_sample_of_n"] is True


@pytest.mark.real_db
def test_run_pack_end_to_end_real_path(populated_campaign_dsn: str, tmp_path: Path) -> None:
    """Drive shipped run_pack on isolated DSN — not fixtures as universe."""
    out = tmp_path / "pack"
    pack = lcp.run_pack(
        dsn=populated_campaign_dsn,
        out_dir=out,
        uf="SC",
        export_limit=50,
        target_competitors=15,
        as_of=date(2026, 7, 23),
    )
    assert pack["production_touched"] is False
    assert pack["reconcile"]["status"] == "PASS"
    assert pack["population"]["eligible_population"] >= 100
    assert pack["deliverable_a"]["status"] in {"OK", "PARTIAL"}, pack["deliverable_a"]
    assert pack["deliverable_a"]["n_rows"] >= 1
    # B: OK with >=15 or honest INSUFFICIENT
    assert pack["deliverable_b"]["status"] in {"OK", "INSUFFICIENT", "PARTIAL"}
    if pack["deliverable_b"]["status"] == "OK":
        assert int(pack["deliverable_b"]["valid_count"]) >= 15
    assert (out / "extra_live_consulting_pack.xlsx").is_file()
    assert (out / "extra_live_consulting_pack.pdf").is_file()
    assert (out / "pack-manifest.json").is_file()
    # export limit must not silently redefine universe
    a = json.loads((out / "deliverable_a.json").read_text(encoding="utf-8"))
    assert a["population"]["export_is_not_universe"] is True
    assert a["population"]["eligible_population"] == pack["population"]["eligible_population"]


def test_cli_verify_isolation_exit_codes() -> None:
    assert lcp.main(["verify-isolation", "--dsn", "postgresql://t:t@127.0.0.1:5436/x"]) == 0
    assert lcp.main(["verify-isolation", "--dsn", "postgresql://t:t@ec-prod:5432/x"]) == 2

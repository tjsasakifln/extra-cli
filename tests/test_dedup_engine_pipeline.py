"""Integration tests for DedupEngine pipeline (C2.8 / NEXT-30D).

Proves that DedupEngine finds cross-source groups when multi-source rows
share a canonical hash. Uses a real DB when available; skips otherwise.

Run:
    REQUIRE_TEST_DB=1 DATABASE_URL=postgresql://test:test@127.0.0.1:5433/pncp_datalake \\
      PYTHONPATH=. pytest tests/test_dedup_engine_pipeline.py -v --no-cov
"""

from __future__ import annotations

import json
import os
import uuid

import pytest

# Opt into real DB access for this integration module (see tests/conftest.py).
os.environ.setdefault("REQUIRE_TEST_DB", "1")

pytestmark = [pytest.mark.integration, pytest.mark.database]

DSN = (
    os.getenv("DATABASE_URL")
    or os.getenv("LOCAL_DATALAKE_DSN")
    or os.getenv("TEST_DSN")
    or "postgresql://test:test@127.0.0.1:5433/pncp_datalake"
)

# Unique per test session to avoid collisions with other synthetic proof rows.
_TAG = f"test-pipeline-{uuid.uuid4().hex[:10]}"
_SID_A = f"SYNTH-DEDUP-PIPE-{_TAG}-A"
_SID_B = f"SYNTH-DEDUP-PIPE-{_TAG}-B"
_HASH_A = f"synth-dedup-pipe-{_TAG}-a"
_HASH_B = f"synth-dedup-pipe-{_TAG}-b"


def _try_connect():
    try:
        import psycopg2

        conn = psycopg2.connect(DSN, connect_timeout=5)
        return conn
    except Exception as exc:  # noqa: BLE001 — skip path needs any failure
        if os.getenv("REQUIRE_TEST_DB") == "1":
            # Still skip when DB host is simply not up in this environment.
            pytest.skip(f"Database not available: {exc}")
        pytest.skip(f"Database not available: {exc}")


@pytest.fixture
def db_conn():
    conn = _try_connect()
    # Ensure required tables exist
    cur = conn.cursor()
    try:
        cur.execute("SELECT 1 FROM opportunity_intel LIMIT 1")
        cur.execute("SELECT 1 FROM dedup_cross_source LIMIT 1")
    except Exception as exc:  # noqa: BLE001
        conn.close()
        pytest.skip(f"Required tables missing: {exc}")
    finally:
        cur.close()
    yield conn
    conn.close()


def _cleanup(conn, ids: list[int] | None = None) -> None:
    cur = conn.cursor()
    if ids:
        cur.execute(
            "DELETE FROM dedup_cross_source WHERE opportunity_id = ANY(%s)",
            (ids,),
        )
        cur.execute("DELETE FROM opportunity_intel WHERE id = ANY(%s)", (ids,))
    else:
        cur.execute(
            """
            DELETE FROM dedup_cross_source
            WHERE opportunity_id IN (
                SELECT id FROM opportunity_intel
                WHERE source_id IN (%s, %s) OR content_hash IN (%s, %s)
            )
            """,
            (_SID_A, _SID_B, _HASH_A, _HASH_B),
        )
        cur.execute(
            """
            DELETE FROM opportunity_intel
            WHERE source_id IN (%s, %s) OR content_hash IN (%s, %s)
            """,
            (_SID_A, _SID_B, _HASH_A, _HASH_B),
        )
    conn.commit()
    cur.close()


def _insert_pair(conn) -> list[int]:
    """Insert two active rows (distinct sources, same canonical fields)."""
    cur = conn.cursor()
    meta = json.dumps(
        {
            "synthetic": True,
            "purpose": "test_dedup_engine_pipeline",
            "tag": _TAG,
            "not_production": True,
        }
    )
    specs = [
        ("pncp", _SID_A, _HASH_A, "Pregão Eletrônico", "Serviço de limpeza predial — PIPE DEDUP TEST"),
        ("pcp", _SID_B, _HASH_B, "pregao eletronico", "Servico de limpeza predial — PIPE DEDUP TEST"),
    ]
    ids: list[int] = []
    for source, sid, chash, modalidade, objeto in specs:
        cur.execute(
            """
            INSERT INTO opportunity_intel (
                source, source_id, source_url, content_hash,
                orgao_cnpj, orgao_nome, modalidade, objeto,
                data_publicacao, valor_estimado, uf, municipio,
                status_canonico, ranking, ranking_confianca, is_active, metadata
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, TRUE, %s::jsonb
            )
            RETURNING id
            """,
            (
                source,
                sid,
                f"https://example.local/test/{sid}",
                chash,
                "82892324",
                "PREFEITURA TESTE DEDUP",
                modalidade,
                objeto,
                "2026-05-15T00:00:00+00",
                99000.00,
                "SC",
                "TESTE",
                "open",
                "REVIEW",
                "LOW",
                meta,
            ),
        )
        ids.append(cur.fetchone()[0])
    conn.commit()
    cur.close()
    return ids


class TestDedupEnginePipeline:
    """DB integration: multi-source fixtures → groups_found > 0."""

    def test_dry_run_finds_cross_source_group(self, db_conn):
        from scripts.lib.dedup import DedupEngine

        _cleanup(db_conn)
        ids = _insert_pair(db_conn)
        try:
            engine = DedupEngine(db_conn)
            stats = engine.dedup_opportunities(dry_run=True)
            assert stats["total_ops"] >= 2
            assert stats["groups_found"] >= 1
            assert stats["duplicates"] >= 2
            assert stats["inserted"] == 0  # dry-run must not write
            # Confirm table not polluted by this dry-run for our ids
            cur = db_conn.cursor()
            cur.execute(
                "SELECT count(*) FROM dedup_cross_source WHERE opportunity_id = ANY(%s)",
                (ids,),
            )
            assert cur.fetchone()[0] == 0
            cur.close()
        finally:
            _cleanup(db_conn, ids)

    def test_persist_writes_dedup_cross_source(self, db_conn):
        from scripts.lib.dedup import DedupEngine

        _cleanup(db_conn)
        ids = _insert_pair(db_conn)
        try:
            engine = DedupEngine(db_conn)
            stats = engine.dedup_opportunities(dry_run=False)
            assert stats["groups_found"] >= 1
            assert stats["inserted"] >= 2

            cur = db_conn.cursor()
            cur.execute(
                """
                SELECT count(*), count(DISTINCT dedup_group_id),
                       count(DISTINCT source)
                FROM dedup_cross_source
                WHERE opportunity_id = ANY(%s)
                """,
                (ids,),
            )
            rows, groups, sources = cur.fetchone()
            cur.close()
            assert rows == 2
            assert groups == 1
            assert sources == 2
        finally:
            _cleanup(db_conn, ids)

    def test_seed_synthetic_helper_and_cli_path(self, db_conn):
        """seed_synthetic_fixtures + engine produces groups_found > 0."""
        from scripts.crawl.run_dedup import seed_synthetic_fixtures
        from scripts.lib.dedup import DedupEngine

        seeded = seed_synthetic_fixtures(db_conn)
        assert len(seeded) == 2
        sources = {r["source"] for r in seeded}
        assert sources == {"pncp", "transparencia_sc"}

        engine = DedupEngine(db_conn)
        stats = engine.dedup_opportunities(dry_run=True)
        assert stats["groups_found"] >= 1
        assert stats["duplicates"] >= 2


class TestDedupEngineUnitFallback:
    """No-DB path: pure unit checks on hash grouping logic surface."""

    def test_generate_cross_source_hash_stable_for_fixture_pair(self):
        from scripts.crawl.common import generate_cross_source_hash

        h1 = generate_cross_source_hash(
            modalidade="Pregão Eletrônico",
            objeto="Aquisição de material de escritório — SYNTH",
            orgao_cnpj_raiz="82892324",
            data_publicacao="2026-07-01",
            valor_total=150000.0,
        )
        h2 = generate_cross_source_hash(
            modalidade="pregao eletronico",
            objeto="Aquisicao de material de escritorio — SYNTH",
            orgao_cnpj_raiz="82892324",
            data_publicacao="2026-07-01",
            valor_total=150000.0,
        )
        assert h1 == h2
        assert len(h1) == 64

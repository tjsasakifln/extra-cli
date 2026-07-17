"""Tests for migration 052 — unified official acts (DOE + DOM).

Covers:
- SQL file structure / idempotent markers
- Real PG apply (when REQUIRE_TEST_DB=1 or local 5433 reachable)
- Unique key behaviour (source, record_hash)
- SQL upsert_official_acts idempotency
- Python OfficialActsStore helpers
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MIGRATION = PROJECT_ROOT / "db" / "migrations" / "052_official_acts.sql"
ROLLBACK = PROJECT_ROOT / "db" / "rollback" / "052_official_acts_rollback.sql"

DEFAULT_DSN = os.getenv(
    "TEST_DSN",
    os.getenv("LOCAL_DATALAKE_DSN", "postgresql://test:test@127.0.0.1:5433/pncp_datalake"),
)


def _pg_available(dsn: str) -> bool:
    try:
        import psycopg2

        conn = psycopg2.connect(dsn, connect_timeout=3)
        conn.close()
        return True
    except Exception:
        return False


# Opt into real DB when local PG on 5433 is reachable (disables conftest mock).
_PG_OK = _pg_available(DEFAULT_DSN)
if _PG_OK:
    os.environ.setdefault("REQUIRE_TEST_DB", "1")

EXPECTED_TABLES = {
    "official_act_resources",
    "official_acts",
    "official_act_classifications",
    "official_act_links",
    "official_act_source_links",
    "official_act_matches",
}

EXPECTED_INDEX_FRAGMENTS = {
    "uq_oa_source_record_hash",
    "uq_oa_source_external_id",
    "idx_oa_orgao",
    "idx_oa_municipio",
    "idx_oa_publication_date",
    "idx_oa_category",
    "idx_oa_record_hash",
    "idx_oa_source",
}


# ---------------------------------------------------------------------------
# Unit: file structure (no DB required)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_migration_file_exists():
    assert MIGRATION.exists(), f"Missing migration: {MIGRATION}"
    assert ROLLBACK.exists(), f"Missing rollback: {ROLLBACK}"


@pytest.mark.unit
def test_migration_is_idempotent_sql():
    text = MIGRATION.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS" in text
    assert "CREATE UNIQUE INDEX IF NOT EXISTS" in text
    assert "CREATE INDEX IF NOT EXISTS" in text
    assert "upsert_official_acts" in text
    assert "publication_date" in text
    assert "edition_date" in text
    assert "event_date" in text
    assert "date_semantics" in text
    assert "record_hash" in text
    assert "raw_json" in text
    assert "raw_text" in text
    # Rollback must not live under migrations/ (conftest applies all *.sql)
    assert "052_official_acts_rollback.sql" not in [
        p.name for p in (PROJECT_ROOT / "db" / "migrations").glob("*.sql")
    ]


@pytest.mark.unit
def test_migration_defines_all_expected_tables():
    text = MIGRATION.read_text(encoding="utf-8")
    for table in EXPECTED_TABLES:
        assert f"CREATE TABLE IF NOT EXISTS public.{table}" in text, table


@pytest.mark.unit
def test_migration_indexes_cover_required_axes():
    text = MIGRATION.read_text(encoding="utf-8")
    for frag in EXPECTED_INDEX_FRAGMENTS:
        assert frag in text, f"missing index marker {frag}"


@pytest.mark.unit
def test_rollback_drops_in_safe_order():
    text = ROLLBACK.read_text(encoding="utf-8")
    # Child tables before parents (DROP TABLE lines only)
    drop_lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip().upper().startswith("DROP TABLE")
    ]
    assert any("official_act_matches" in line for line in drop_lines)
    assert any("official_acts" in line for line in drop_lines)
    idx_matches = next(i for i, l in enumerate(drop_lines) if "official_act_matches" in l)
    idx_acts = next(i for i, l in enumerate(drop_lines) if l.endswith("official_acts CASCADE;"))
    idx_resources = next(i for i, l in enumerate(drop_lines) if "official_act_resources" in l)
    assert idx_matches < idx_acts < idx_resources
    assert "DROP VIEW IF EXISTS" in text
    assert "DROP FUNCTION IF EXISTS" in text


@pytest.mark.unit
def test_compute_record_hash_stable():
    from scripts.schema.official_acts import compute_record_hash

    a = compute_record_hash("ciga_ckan", external_id="COD-1", title="X")
    b = compute_record_hash("ciga_ckan", external_id="COD-1", title="Y")
    assert a == b  # external_id wins
    assert len(a) == 64
    c = compute_record_hash("ciga_ckan", title="Homologação", publication_date="2026-01-01")
    d = compute_record_hash("ciga_ckan", title="Homologação", publication_date="2026-01-01")
    assert c == d
    assert a != c


# ---------------------------------------------------------------------------
# Integration: real PostgreSQL
# ---------------------------------------------------------------------------


requires_pg = pytest.mark.skipif(
    not _PG_OK and os.getenv("REQUIRE_TEST_DB") != "1",
    reason=f"PostgreSQL not reachable at {DEFAULT_DSN}; set REQUIRE_TEST_DB=1 to force fail",
)


@pytest.fixture(scope="module")
def dsn() -> str:
    if os.getenv("REQUIRE_TEST_DB") == "1" and not _PG_OK:
        pytest.fail(f"REQUIRE_TEST_DB=1 but cannot connect to {DEFAULT_DSN}")
    if not _PG_OK:
        pytest.skip(f"PostgreSQL not reachable: {DEFAULT_DSN}")
    return DEFAULT_DSN


@pytest.fixture(scope="module")
def applied_migration(dsn: str):
    """Apply 052 twice (idempotency) and yield DSN."""
    import psycopg2

    sql = MIGRATION.read_text(encoding="utf-8")
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            cur.execute(sql)  # second apply must succeed
        yield dsn
    finally:
        conn.close()


@pytest.fixture
def conn(applied_migration: str):
    import psycopg2

    c = psycopg2.connect(applied_migration)
    c.autocommit = True
    yield c
    c.close()


@pytest.fixture
def clean_acts(conn):
    """Remove rows created by this test module (source prefix test_oa_)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM official_act_matches
            WHERE act_id IN (SELECT id FROM official_acts WHERE source LIKE 'test_oa_%')
            """
        )
        cur.execute(
            """
            DELETE FROM official_act_source_links
            WHERE source LIKE 'test_oa_%'
               OR act_id IN (SELECT id FROM official_acts WHERE source LIKE 'test_oa_%')
            """
        )
        cur.execute(
            """
            DELETE FROM official_act_links
            WHERE act_id IN (SELECT id FROM official_acts WHERE source LIKE 'test_oa_%')
            """
        )
        cur.execute(
            """
            DELETE FROM official_act_classifications
            WHERE act_id IN (SELECT id FROM official_acts WHERE source LIKE 'test_oa_%')
            """
        )
        cur.execute("DELETE FROM official_acts WHERE source LIKE 'test_oa_%'")
        cur.execute("DELETE FROM official_act_resources WHERE source LIKE 'test_oa_%'")
    yield
    with conn.cursor() as cur:
        cur.execute(
            """
            DELETE FROM official_act_matches
            WHERE act_id IN (SELECT id FROM official_acts WHERE source LIKE 'test_oa_%')
            """
        )
        cur.execute(
            """
            DELETE FROM official_act_source_links
            WHERE source LIKE 'test_oa_%'
               OR act_id IN (SELECT id FROM official_acts WHERE source LIKE 'test_oa_%')
            """
        )
        cur.execute(
            """
            DELETE FROM official_act_links
            WHERE act_id IN (SELECT id FROM official_acts WHERE source LIKE 'test_oa_%')
            """
        )
        cur.execute(
            """
            DELETE FROM official_act_classifications
            WHERE act_id IN (SELECT id FROM official_acts WHERE source LIKE 'test_oa_%')
            """
        )
        cur.execute("DELETE FROM official_acts WHERE source LIKE 'test_oa_%'")
        cur.execute("DELETE FROM official_act_resources WHERE source LIKE 'test_oa_%'")


@requires_pg
@pytest.mark.integration
@pytest.mark.database
def test_tables_exist_after_migration(conn, applied_migration):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = ANY(%s)
            """,
            (list(EXPECTED_TABLES),),
        )
        found = {r[0] for r in cur.fetchall()}
    assert found == EXPECTED_TABLES


@requires_pg
@pytest.mark.integration
@pytest.mark.database
def test_upsert_function_exists(conn, applied_migration):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT proname FROM pg_proc
            WHERE proname IN ('upsert_official_acts', 'upsert_official_act_resource')
            """
        )
        names = {r[0] for r in cur.fetchall()}
    assert "upsert_official_acts" in names
    assert "upsert_official_act_resource" in names


@requires_pg
@pytest.mark.integration
@pytest.mark.database
def test_unique_source_record_hash(conn, clean_acts):
    source = "test_oa_unique"
    rh = hashlib.sha256(b"unique-hash-1").hexdigest()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO official_acts (source, record_hash, title, publication_date, date_semantics)
            VALUES (%s, %s, 'Act A', '2026-07-01', 'publication_from_source_data')
            """,
            (source, rh),
        )
        with pytest.raises(Exception):
            cur.execute(
                """
                INSERT INTO official_acts (source, record_hash, title)
                VALUES (%s, %s, 'Act A dup')
                """,
                (source, rh),
            )


@requires_pg
@pytest.mark.integration
@pytest.mark.database
def test_upsert_official_acts_idempotent(conn, clean_acts):
    source = "test_oa_upsert"
    rh = hashlib.sha256(f"idem-{uuid.uuid4()}".encode()).hexdigest()
    payload = [
        {
            "source": source,
            "external_id": "EXT-1",
            "record_hash": rh,
            "title": "Homologação Pregão 1/2026",
            "raw_text": "Homologação do pregão eletrônico nº 1/2026",
            "raw_json": {"codigo": "EXT-1", "titulo": "Homologação"},
            "category": "homologacao",
            "category_source": "classifier",
            "category_confidence": "high",
            "orgao_nome": "Prefeitura de Teste",
            "municipio": "Florianópolis",
            "uf": "SC",
            "publication_date": "2026-07-01",
            "edition_date": "2026-07-01",
            "event_date": None,
            "date_semantics": "publication_from_source_data;edition_equals_publication",
            "run_id": "run-test-1",
            "proveniencia": {"portal": source, "run_id": "run-test-1"},
        }
    ]
    blob = json.dumps(payload)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT action, act_id, record_hash FROM upsert_official_acts(%s::jsonb)",
            (blob,),
        )
        first = cur.fetchall()
        assert len(first) == 1
        assert first[0][0] == "inserted"
        act_id = first[0][1]

        # Second upsert same hash → updated, same id
        payload[0]["title"] = "Homologação Pregão 1/2026 (atualizado)"
        payload[0]["run_id"] = "run-test-2"
        blob2 = json.dumps(payload)
        cur.execute(
            "SELECT action, act_id, record_hash FROM upsert_official_acts(%s::jsonb)",
            (blob2,),
        )
        second = cur.fetchall()
        assert len(second) == 1
        assert second[0][0] == "updated"
        assert second[0][1] == act_id

        cur.execute(
            "SELECT COUNT(*) FROM official_acts WHERE source = %s AND record_hash = %s",
            (source, rh),
        )
        assert cur.fetchone()[0] == 1

        # date_semantics preserved / title refreshed
        cur.execute(
            "SELECT title, publication_date, date_semantics, run_id FROM official_acts WHERE id = %s",
            (act_id,),
        )
        title, pub, sem, run_id = cur.fetchone()
        assert "atualizado" in title
        assert str(pub) == "2026-07-01"
        assert "publication_from_source_data" in (sem or "")
        assert run_id == "run-test-2"


@requires_pg
@pytest.mark.integration
@pytest.mark.database
def test_upsert_resource_idempotent(conn, clean_acts):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT upsert_official_act_resource(
                'test_oa_res', 'res-1', 'pkg-1', 'domsc-publicacoes-de-07-2026',
                'Publicações Jul/2026', 'https://example.test/r1', 'json',
                %s, 'etag-1', NULL, 1024, 'run-r1', 'fetched', '{}'::jsonb
            )
            """,
            (hashlib.sha256(b"body").hexdigest(),),
        )
        id1 = cur.fetchone()[0]
        cur.execute(
            """
            SELECT upsert_official_act_resource(
                'test_oa_res', 'res-1', 'pkg-1', 'domsc-publicacoes-de-07-2026',
                'Publicações Jul/2026 v2', 'https://example.test/r1', 'json',
                %s, 'etag-2', NULL, 2048, 'run-r2', 'parsed', '{"k":1}'::jsonb
            )
            """,
            (hashlib.sha256(b"body").hexdigest(),),
        )
        id2 = cur.fetchone()[0]
        assert id1 == id2
        cur.execute(
            "SELECT COUNT(*) FROM official_act_resources WHERE source = 'test_oa_res' AND resource_id = 'res-1'"
        )
        assert cur.fetchone()[0] == 1


@requires_pg
@pytest.mark.integration
@pytest.mark.database
def test_python_store_helpers(applied_migration, clean_acts):
    from scripts.schema.official_acts import OfficialActsStore, compute_record_hash

    store = OfficialActsStore(applied_migration)
    source = "test_oa_py"
    external_id = f"PY-{uuid.uuid4().hex[:8]}"
    rh = compute_record_hash(source, external_id=external_id, title="Extrato de Contrato")

    res_id = store.upsert_resource(
        source=source,
        resource_id="py-res-1",
        package_name="domsc-test",
        resource_url="https://example.test/py",
        format="json",
        content_sha256=hashlib.sha256(b"py-body").hexdigest(),
        run_id="run-py-1",
        fetch_status="fetched",
    )
    assert res_id > 0

    act_id = store.upsert_act(
        {
            "source": source,
            "external_id": external_id,
            "record_hash": rh,
            "title": "Extrato de Contrato 99/2026",
            "raw_text": "Extrato do contrato nº 99/2026",
            "category": "extrato_contrato",
            "category_source": "classifier",
            "category_confidence": "high",
            "municipio": "Joinville",
            "uf": "SC",
            "publication_date": "2026-06-15",
            "date_semantics": "publication_from_source_data",
            "resource_fk": res_id,
            "run_id": "run-py-1",
            "raw_json": {"codigo": external_id},
        }
    )
    assert act_id > 0

    # Idempotent second call
    act_id2 = store.upsert_act(
        {
            "source": source,
            "external_id": external_id,
            "record_hash": rh,
            "title": "Extrato de Contrato 99/2026",
            "run_id": "run-py-2",
        }
    )
    assert act_id2 == act_id

    link_id = store.add_link(
        act_id,
        "https://example.test/act/99",
        link_type="source_page",
        is_primary=True,
    )
    assert link_id > 0
    link_id2 = store.add_link(
        act_id,
        "https://example.test/act/99",
        link_type="source_page",
    )
    assert link_id2 == link_id

    class_id = store.add_classification(
        act_id,
        "extrato_contrato",
        confidence="high",
        method="deterministic_rules",
        classifier_version="act_classifier_v1",
        evidence="extrato do contrato",
    )
    assert class_id > 0

    match_id = store.add_match(
        act_id,
        match_type="contract",
        target_table="pncp_supplier_contracts",
        target_id="SC-TEST-99",
        match_method="manual",
        match_confidence="low",
        matched_by="test",
    )
    assert match_id > 0

    obs_hash = compute_record_hash("test_oa_other", external_id=external_id)
    obs_id = store.link_source_observation(
        act_id,
        source="test_oa_other",
        record_hash=obs_hash,
        external_id=external_id,
        run_id="run-other",
    )
    assert obs_id > 0


@requires_pg
@pytest.mark.integration
@pytest.mark.database
def test_view_active_acts(conn, clean_acts):
    source = "test_oa_view"
    rh = hashlib.sha256(b"view-act").hexdigest()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO official_acts (
                source, record_hash, title, status, is_active,
                publication_date, date_semantics, category, municipio, uf
            ) VALUES (
                %s, %s, 'Aviso de licitação', 'active', TRUE,
                '2026-07-10', 'publication_from_source_data', 'aviso_licitacao',
                'Blumenau', 'SC'
            )
            """,
            (source, rh),
        )
        cur.execute(
            """
            SELECT COUNT(*) FROM v_official_acts_active
            WHERE source = %s AND record_hash = %s
            """,
            (source, rh),
        )
        assert cur.fetchone()[0] == 1

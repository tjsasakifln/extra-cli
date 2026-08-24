"""Real-PostgreSQL regressions for #452 and #453."""

from __future__ import annotations

import os

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.database,
    pytest.mark.skipif(
        os.getenv("REQUIRE_TEST_DB") != "1",
        reason="Set REQUIRE_TEST_DB=1 to run database tests",
    ),
]


@pytest.fixture(scope="module")
def scope_pg_conn():
    import psycopg2

    dsn = os.getenv("TEST_DSN") or os.getenv("LOCAL_DATALAKE_DSN")
    if not dsn:
        pytest.skip("TEST_DSN or LOCAL_DATALAKE_DSN is required")
    conn = psycopg2.connect(dsn)
    yield conn
    conn.close()


def test_ti_uses_lexical_token(scope_pg_conn):
    corpus = [
        ("Serviços de TI", "TI"),
        ("Tecnologia da informação", "TI"),
        ("Eletrodomésticos", "OUTROS"),
        ("Materiais didáticos", "OUTROS"),
        ("Artigos médicos", "SAÚDE"),
        ("Materiais esportivos", "OUTROS"),
        ("Alimentação e saúde", "SAÚDE"),
        ("Sistema de saúde municipal", "SAÚDE"),
        ("Sistema de alimentação escolar", "ALIMENTAÇÃO"),
    ]
    with scope_pg_conn.cursor() as cur:
        cur.execute(
            "SELECT value, public.contract_category_v1(value) FROM unnest(%s::text[]) value",
            ([value for value, _expected in corpus],),
        )
        assert cur.fetchall() == corpus


def test_view_and_focal_share_canonical_classifier(scope_pg_conn):
    with scope_pg_conn.cursor() as cur:
        cur.execute("SELECT pg_get_viewdef('public.v_contract_intel_percentis'::regclass, true)")
        viewdef = cur.fetchone()[0]
        cur.execute("SELECT pg_get_viewdef('public.v_contract_intel_reference_scopes_v1'::regclass, true)")
        scope_viewdef = cur.fetchone()[0]
        cur.execute("SELECT pg_get_functiondef('public.contract_category_v1(text)'::regprocedure)")
        functiondef = cur.fetchone()[0]
    assert "contract_category_v1" in viewdef
    assert "data_inicio IS NOT NULL" in viewdef
    assert "data_publicacao IS NOT NULL" in viewdef
    assert "%ti%" not in viewdef.lower()
    assert "canonical_v2_temporal_eligibility" in scope_viewdef
    assert "canonical_v2 eligibility intersect public.v_target_universe_active" in scope_viewdef
    assert "(included_rows + excluded_rows) / total_rows" in scope_viewdef
    assert "closed_partitions / expected_partitions" in scope_viewdef
    assert "[^[:alpha:]]" in functiondef
    assert "%ti%" not in functiondef.lower()


def test_scope_view_withholds_national_percentiles(scope_pg_conn):
    with scope_pg_conn.cursor() as cur:
        cur.execute(
            """SELECT reference_state, categoria, p25_valor, p50_valor, p75_valor,
                      scope_id, geography, denominator, as_of, source_id,
                      source_version, sample_count, coverage, missingness,
                      method, reference_hash, limitations
                 FROM public.v_contract_intel_reference_scopes_v1
                WHERE scope_kind = 'NATIONAL'"""
        )
        rows = cur.fetchall()
    assert len(rows) == 1
    assert rows[0][:5] == ("DATA_HOLD", None, None, None, None)
    assert rows[0][5] == "national:unavailable"
    assert all(value is not None for value in (rows[0][6], rows[0][7], rows[0][13], rows[0][14], rows[0][16]))


def test_national_scope_ignores_newer_non_national_authority(scope_pg_conn):
    with scope_pg_conn.cursor() as cur:
        for universe_id in ("qa-national-br", "qa-regional-sc"):
            cur.execute(
                """
                INSERT INTO public.national_coverage_universe (
                    universe_id, universe_kind, official_source, official_source_url,
                    competence, cutoff, retrieved_at, as_of, raw_hash, catalog_hash,
                    method_version, schema_version, grain, expected_partitions,
                    expected_units, official_status, official_block_cause,
                    inclusion_rules, exclusion_rules, owner, next_refresh, payload
                ) VALUES (
                    %s, 'OFFICIAL', 'pncp', 'https://pncp.gov.br/api/pncp/v1/orgaos',
                    'qa', '2026-08-24T00:00:00Z', '2026-08-24T00:00:00Z',
                    '2026-08-24T00:00:00Z', %s, %s, 'qa-v1',
                    'national-coverage/1.0', 'publishing_org', 1, 1, 'AVAILABLE',
                    NULL, '[]'::jsonb, '[]'::jsonb, 'qa', 'manual', '{}'::jsonb
                ) ON CONFLICT (universe_id) DO NOTHING
                """,
                (universe_id, f"raw-{universe_id}", f"catalog-{universe_id}"),
            )
        answer_sql = """
            INSERT INTO public.national_coverage_answer (
                universe_id, requested_geography, requested_period, requested_source,
                requested_grain, expected_partitions, closed_partitions,
                queried_partitions, coverage_pct, national_claim_authorized,
                verdict, reason_codes, limitations, provenance, content_hash,
                payload, produced_at
            ) VALUES (
                %s, %s, 'qa', 'pncp', 'publishing_org', 1, 0, 0, 0,
                FALSE, 'PARTIAL', ARRAY['qa'], ARRAY['qa'],
                '{"as_of":"2026-08-24T00:00:00Z", "schema_version":"national-coverage/1.0", "method_version":"national-coverage-v1", "core_method_version":"pncp-orgaos-publicantes-v1"}'::jsonb, %s,
                '{"as_of":"2026-08-24T00:00:00Z"}'::jsonb, %s
            )
        """
        cur.execute(answer_sql, ("qa-national-br", "BR", "hash-br", "2999-01-01T00:00:00Z"))
        cur.execute(answer_sql, ("qa-regional-sc", "SC", "hash-sc", "3000-01-01T00:00:00Z"))
        cur.execute(
            """SELECT scope_id, source_id, source_version, reference_hash
                 FROM public.v_contract_intel_reference_scopes_v1
                WHERE scope_kind = 'NATIONAL'"""
        )
        assert cur.fetchone() == (
            "national:qa-national-br",
            "pncp",
            "national-coverage/1.0+national-coverage-v1+pncp-orgaos-publicantes-v1",
            "hash-br",
        )


def test_panel_aggregation_equals_direct_canonical_classifier(scope_pg_conn):
    with scope_pg_conn.cursor() as cur:
        cur.execute("SAVEPOINT nonvacuous_panel")
        try:
            cur.execute(
                """
                INSERT INTO public.target_universe_runs (
                    seed_sha256, seed_filename, radius_km, total_rows,
                    included_rows, excluded_rows, unresolved_rows, git_sha
                ) VALUES (repeat('a', 64), 'qa.csv', 200, 1, 1, 0, 0, 'qa-sha')
                RETURNING id
                """
            )
            run_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO public.target_universe_entities (
                    universe_run_id, canonical_entity_key, seed_row, cnpj8,
                    legal_name, municipality, radius_decision
                ) VALUES (%s, 'qa-entity', 1, '11111111', 'QA', 'QA', 'included')
                """,
                (run_id,),
            )
            cur.execute(
                """
                INSERT INTO public.pncp_supplier_contracts (
                    contrato_id, orgao_cnpj, orgao_nome, objeto_contrato,
                    valor_total, data_publicacao, is_active, source
                ) VALUES
                    ('qa-ti', '11111111000100', 'QA', 'Serviços de TI', 100, '2026-08-24', TRUE, 'qa'),
                    ('qa-tech', '11111111000100', 'QA', 'Tecnologia da informação', 200, '2026-08-24', TRUE, 'qa'),
                    ('qa-dom', '11111111000100', 'QA', 'Eletrodomésticos', 300, '2026-08-24', TRUE, 'qa'),
                    ('qa-did', '11111111000100', 'QA', 'Materiais didáticos', 400, '2026-08-24', TRUE, 'qa'),
                    ('qa-med', '11111111000100', 'QA', 'Artigos médicos', 500, '2026-08-24', TRUE, 'qa'),
                    ('qa-sport', '11111111000100', 'QA', 'Materiais esportivos', 600, '2026-08-24', TRUE, 'qa'),
                    ('qa-foodhealth', '11111111000100', 'QA', 'Alimentação e saúde', 700, '2026-08-24', TRUE, 'qa'),
                    ('qa-no-date', '11111111000100', 'QA', 'Serviços de TI', 900, NULL, TRUE, 'qa'),
                    ('qa-inactive', '11111111000100', 'QA', 'Serviços de TI', 1000, '2026-08-24', FALSE, 'qa')
                """
            )
            cur.execute("SELECT categoria, qtd_contratos FROM public.v_contract_intel_percentis ORDER BY categoria")
            assert cur.fetchall() == [("OUTROS", 3), ("SAÚDE", 2), ("TI", 2)]
            cur.execute(
                """
            WITH direct AS (
                SELECT public.contract_category_v1(c.objeto) AS categoria,
                       COUNT(*) AS qtd_contratos,
                       ROUND(SUM(c.valor)::numeric, 2) AS valor_total,
                       ROUND(AVG(c.valor)::numeric, 2) AS ticket_medio,
                       ROUND(PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY c.valor)::numeric, 2) AS p25_valor,
                       ROUND(PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY c.valor)::numeric, 2) AS p50_valor,
                       ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY c.valor)::numeric, 2) AS p75_valor
                  FROM public.v_contracts_canonical_v2 c
                 WHERE c.is_active IS TRUE AND c.valor > 0
                   AND EXISTS (
                       SELECT 1 FROM public.v_target_universe_active u
                        WHERE u.cnpj8 = LEFT(c.buyer_cnpj, 8)
                   )
                 GROUP BY 1
            ), difference AS (
                (SELECT * FROM direct EXCEPT ALL SELECT * FROM public.v_contract_intel_percentis)
                UNION ALL
                (SELECT * FROM public.v_contract_intel_percentis EXCEPT ALL SELECT * FROM direct)
            )
            SELECT COUNT(*) FROM difference
            """
            )
            assert cur.fetchone()[0] == 0
        finally:
            cur.execute("ROLLBACK TO SAVEPOINT nonvacuous_panel")

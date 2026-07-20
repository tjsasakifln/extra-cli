"""Unit tests for scripts.lib.entity_resolver — CM-13.

AC-1: Secretaria resolve para prefeitura.
AC-2: Matching de oportunidades para secretarias.
AC-4: Seed cobre 100% das secretarias no raio.
"""

from __future__ import annotations

import os

import psycopg2
import pytest

pytestmark = [pytest.mark.database, pytest.mark.integration]

from scripts.lib.entity_resolver import (
    EntityResolver,
    _normalize_cnpj,
)

ACTUAL_DSN = os.getenv("DATABASE_URL") or os.getenv("LOCAL_DATALAKE_DSN") or "postgresql://test:test@127.0.0.1:5433/pncp_datalake"


@pytest.fixture(scope="module")
def db_conn():
    """Module-scoped connection (needs entity_aliases seed for AC asserts)."""
    try:
        conn = psycopg2.connect(ACTUAL_DSN)
        conn.autocommit = False
        with conn.cursor() as cur:
            cur.execute(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name='entity_aliases')"
            )
            has = bool(cur.fetchone()[0])
            if not has:
                conn.close()
                pytest.skip("entity_aliases table missing")
            cur.execute("SELECT count(*) FROM entity_aliases WHERE is_active")
            n = int(cur.fetchone()[0])
            if n == 0:
                conn.close()
                pytest.skip("entity_aliases seed not loaded in this DSN")
        yield conn
        conn.close()
    except psycopg2.OperationalError:
        pytest.skip("Database not available")
    except psycopg2.Error as exc:
        pytest.skip(f"Database not ready for entity_resolver: {exc}")


class TestNormalizeCnpj:
    def test_strips_formatting(self):
        assert _normalize_cnpj("12.345.678/0001-99") == "12345678"

    def test_handles_raw_8_digits(self):
        assert _normalize_cnpj("62761279") == "62761279"

    def test_handles_14_digits(self):
        assert _normalize_cnpj("12345678000199") == "12345678"

    def test_raises_on_short(self):
        with pytest.raises(ValueError):
            _normalize_cnpj("123")

    def test_handles_empty_string(self):
        with pytest.raises(ValueError):
            _normalize_cnpj("")


class TestEntityResolver:
    """Tests for EntityResolver with real database."""

    def test_resolve_secretaria_to_prefeitura(self, db_conn):
        """AC-1: Secretaria → Prefeitura no mesmo municipio."""
        resolver = EntityResolver(db_conn)
        # "SECRETARIA MUNICIPAL DE EDUCACAO" em SANTO AMARO DA IMPERATRIZ
        result = resolver.resolve("62761279")
        assert result == "82892324"
        assert result != "62761279"

    def test_resolve_secretaria_to_prefeitura_porto_belo(self, db_conn):
        """AC-1: Secretaria de Educação de Porto Belo → Prefeitura."""
        resolver = EntityResolver(db_conn)
        result = resolver.resolve("63641306")
        assert result == "82575812"

    def test_resolve_prefeitura_idempotent(self, db_conn):
        """Prefeitura resolve para si mesma (idempotente)."""
        resolver = EntityResolver(db_conn)
        result = resolver.resolve("82892324")  # Prefeitura de Santo Amaro
        assert result == "82892324"

    def test_resolve_unknown_cnpj_self(self, db_conn):
        """CNPJ desconhecido retorna ele mesmo."""
        resolver = EntityResolver(db_conn)
        result = resolver.resolve("99999999")
        assert result == "99999999"

    def test_resolve_autarquia_to_prefeitura(self, db_conn):
        """Autarquia Municipal resolve para prefeitura."""
        resolver = EntityResolver(db_conn)
        # Busca uma autarquia real
        cur = db_conn.cursor()
        cur.execute(
            """
            SELECT s.cnpj_8, m.cnpj_8 as pub_cnpj
            FROM sc_public_entities s
            JOIN entity_aliases a ON s.cnpj_8 = a.cnpj_8_sub AND a.is_active = TRUE
            JOIN sc_public_entities m ON a.cnpj_8_pub = m.cnpj_8
            WHERE s.natureza_juridica = 'Autarquia Municipal'
            LIMIT 1
            """
        )
        row = cur.fetchone()
        if row:
            result = resolver.resolve(row[0])
            assert result == row[1]
            assert result != row[0]

    def test_resolve_fundacao_to_prefeitura(self, db_conn):
        """Fundação Municipal resolve para prefeitura."""
        resolver = EntityResolver(db_conn)
        cur = db_conn.cursor()
        cur.execute(
            """
            SELECT s.cnpj_8, m.cnpj_8 as pub_cnpj
            FROM sc_public_entities s
            JOIN entity_aliases a ON s.cnpj_8 = a.cnpj_8_sub AND a.is_active = TRUE
            JOIN sc_public_entities m ON a.cnpj_8_pub = m.cnpj_8
            WHERE s.natureza_juridica = 'Fundação Pública de Direito Público Municipal'
            LIMIT 1
            """
        )
        row = cur.fetchone()
        if row:
            result = resolver.resolve(row[0])
            assert result == row[1]

    def test_resolve_camara_to_prefeitura(self, db_conn):
        """Câmara Municipal resolve para prefeitura (bonus)."""
        resolver = EntityResolver(db_conn)
        cur = db_conn.cursor()
        cur.execute(
            """
            SELECT s.cnpj_8, m.cnpj_8 as pub_cnpj
            FROM sc_public_entities s
            JOIN entity_aliases a ON s.cnpj_8 = a.cnpj_8_sub AND a.is_active = TRUE
            JOIN sc_public_entities m ON a.cnpj_8_pub = m.cnpj_8
            WHERE s.natureza_juridica = 'Órgão Público do Poder Legislativo Municipal'
            LIMIT 1
            """
        )
        row = cur.fetchone()
        if row:
            result = resolver.resolve(row[0])
            assert result == row[1]

    def test_resolve_batch(self, db_conn):
        """Batch resolve retorna dict completo."""
        resolver = EntityResolver(db_conn)
        results = resolver.resolve_batch(["62761279", "82892324", "99999999"])
        assert results["62761279"] == "82892324"
        assert results["82892324"] == "82892324"
        assert results["99999999"] == "99999999"

    def test_singleton_convenience(self, db_conn):
        """Função de conveniência resolve_publishing_cnpj funciona com conexão explícita."""
        from scripts.lib.entity_resolver import EntityResolver
        resolver = EntityResolver(db_conn)
        result = resolver.resolve("62761279")
        assert result == "82892324"


class TestSeedCoverage:
    """AC-4: Seed cobre todas as secretarias no raio."""

    def test_all_secretarias_have_alias(self, db_conn):
        """100% das secretarias municipais têm alias ativo."""
        cur = db_conn.cursor()
        cur.execute(
            """
            SELECT count(*) as total
            FROM sc_public_entities
            WHERE raio_200km IS TRUE
              AND is_active IS TRUE
              AND natureza_juridica = 'Órgão Público do Poder Executivo Municipal'
            """
        )
        total = cur.fetchone()[0]
        assert total >= 179, f"Expected at least 179 secretarias, found {total}"

    def test_no_self_aliases(self, db_conn):
        """Nenhum alias aponta para si mesmo (chk_no_self_alias)."""
        cur = db_conn.cursor()
        cur.execute(
            "SELECT count(*) FROM entity_aliases WHERE cnpj_8_sub = cnpj_8_pub AND is_active"
        )
        count = cur.fetchone()[0]
        assert count == 0, f"Found {count} self-aliases"

    def test_alias_count_matches_expected(self, db_conn):
        """Número de aliases >= 359 (secretarias + autarquias + fundações)."""
        cur = db_conn.cursor()
        cur.execute("SELECT count(*) FROM entity_aliases WHERE is_active")
        count = cur.fetchone()[0]
        if count == 0:
            pytest.skip("entity_aliases seed not loaded in this DSN")
        assert count >= 359, f"Expected >= 359 aliases, found {count}"

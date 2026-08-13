"""Unit and opt-in PostgreSQL tests for the PCP ingestion boundary."""

import json
import os
import urllib.error
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from scripts.crawl import pcp_crawler as pcp
from scripts.crawl.ingestion._base.crawler import CrawlRequest, FetchResult

# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------

MOCK_RECORD = {
    "codigoLicitacao": "12345",
    "resumo": "Contratacao de servico de limpeza",
    "unidadeCompradora": {
        "nomeUnidadeCompradora": "Prefeitura Municipal de Florianopolis",
        "CNPJ": "12345678000199",
        "cidade": "Florianopolis",
        "uf": "SC",
    },
    "dataHoraPublicacao": "2025-06-15T10:00:00Z",
    "dataHoraInicioPropostas": "2025-07-01T08:00:00Z",
    "dataHoraFinalPropostas": "2025-07-15T18:00:00Z",
    "tipoLicitacao": {
        "modalidadeLicitacao": "Pregao Eletronico",
    },
}

MOCK_RECORD_MUNICIPAL = {
    "codigoLicitacao": "67890",
    "resumo": "Aquisicao de equipamentos",
    "unidadeCompradora": {
        "nomeUnidadeCompradora": "Camara Municipal de Sao Jose",
        "CNPJ": "98765432000188",
        "cidade": "Sao Jose",
        "uf": "SC",
    },
    "dataHoraPublicacao": "2025-06-20T14:30:00Z",
    "dataHoraInicioPropostas": "2025-07-05T09:00:00Z",
    "tipoLicitacao": {
        "modalidadeLicitacao": "Concorrencia",
    },
}

MOCK_RECORD_ESTADUAL = {
    "codigoLicitacao": "11111",
    "resumo": "Obra de infraestrutura rodoviaria",
    "unidadeCompradora": {
        "nomeUnidadeCompradora": "DEINFRA - Departamento de Infraestrutura",
        "CNPJ": "55555555000155",
        "cidade": "Florianopolis",
        "uf": "SC",
    },
    "dataHoraPublicacao": "2025-06-25T10:00:00Z",
    "tipoLicitacao": {
        "modalidadeLicitacao": "Tomada de Precos",
    },
}

MOCK_RECORD_NO_CNPJ = {
    "codigoLicitacao": "22222",
    "resumo": "Servico sem CNPJ",
    "unidadeCompradora": {
        "nomeUnidadeCompradora": "Orgao Sem CNPJ",
        "CNPJ": "",
        "cidade": "Palhoca",
        "uf": "SC",
    },
    "dataHoraPublicacao": "2025-06-30T10:00:00Z",
    "tipoLicitacao": {
        "modalidadeLicitacao": "Dispensa de Licitação",
    },
}

# ---------------------------------------------------------------------------
# crawl()
# ---------------------------------------------------------------------------


class TestCrawl:
    """Tests for crawl()."""

    @patch("scripts.crawl.pcp_crawler._fetch_page", return_value=([], False))
    def test_crawl_incremental_returns_list(self, mock_fetch):
        """crawl('incremental') returns a list even when API returns no data."""
        result = pcp.crawl(mode="incremental")
        assert isinstance(result, list)

    @patch("scripts.crawl.pcp_crawler.provenance_fail")
    @patch("scripts.crawl.pcp_crawler.provenance_complete")
    @patch("scripts.crawl.pcp_crawler.provenance_start", return_value="pcp-deferred-1")
    @patch("scripts.crawl.pcp_crawler._fetch_page", return_value=([MOCK_RECORD], False))
    def test_structured_crawl_defers_terminal_provenance(
        self,
        _mock_fetch,
        _mock_start,
        mock_complete,
        mock_fail,
    ):
        result = pcp.crawl(
            CrawlRequest(
                mode="incremental",
                date_from=date(2026, 8, 13),
                date_to=date(2026, 8, 13),
            )
        )

        assert isinstance(result, FetchResult)
        assert result.status == "success"
        assert result.provenance["run_id"] == "pcp-deferred-1"
        assert result.provenance["terminal_deferred"] is True
        assert result.pages_fetched == result.pages_expected == 1
        mock_complete.assert_not_called()
        mock_fail.assert_not_called()

    def test_monitor_upsert_failure_fails_same_deferred_run(self, monkeypatch):
        from scripts.crawl import monitor

        fetch = FetchResult(
            status="success",
            records=[MOCK_RECORD],
            request_completed=True,
            pages_fetched=1,
            pages_expected=1,
            provenance={
                "run_id": "pcp-monitor-upsert-fail",
                "source": "pcp",
                "terminal_deferred": True,
                "pages_completed": 1,
            },
        )
        crawler = SimpleNamespace(
            crawl=lambda _request: fetch,
            transform=lambda _records: [{"pncp_id": "pcp_12345", "content_hash": "same"}],
            UPSERT_FUNCTION="upsert_pncp_raw_bids",
        )
        connection = SimpleNamespace(rollback=lambda: None, close=lambda: None)

        monkeypatch.setattr(monitor, "_get_conn", lambda: connection)
        monkeypatch.setattr(monitor, "_start_ingestion_run", lambda *_args: 91)
        monkeypatch.setattr(monitor, "_load_crawler", lambda _source: crawler)
        monkeypatch.setattr(monitor, "_finish_ingestion_run", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(monitor, "_record_evidence", lambda *_args, **_kwargs: None)
        monkeypatch.setattr(
            "scripts.crawl.credential_validator.validate_source_credentials",
            lambda _source: (True, []),
        )
        monkeypatch.setattr(
            monitor,
            "_upsert_raw_records",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("content hash collision")),
        )

        with (
            patch("scripts.crawl.provenance_sync.provenance_complete") as complete,
            patch("scripts.crawl.provenance_sync.provenance_fail") as fail,
        ):
            result = monitor.crawl_source("pcp", entities=[], mode="incremental")

        assert result.status == "failed"
        assert "content hash collision" in (result.error_message or "")
        complete.assert_not_called()
        fail.assert_called_once()
        assert fail.call_args.kwargs["run_id"] == "pcp-monitor-upsert-fail"
        assert fail.call_args.kwargs["records_fetched"] == 1
        assert fail.call_args.kwargs["records_failed"] == 1
        assert fetch.provenance["terminal_state"] == "failed"


# ---------------------------------------------------------------------------
# transform()
# ---------------------------------------------------------------------------


class TestTransform:
    """Tests for transform()."""

    def test_transform_empty_list(self):
        """transform([]) returns an empty list."""
        result = pcp.transform([])
        assert isinstance(result, list)
        assert len(result) == 0

    def test_transform_mock_record(self):
        """transform() normalizes a PCP v2 record with all 16 fields."""
        result = pcp.transform([MOCK_RECORD])
        assert len(result) == 1

        record = result[0]

        # Verify all pncp_raw_bids fields are present
        assert record["pncp_id"] == "pcp_12345"
        assert record["objeto_compra"] == "Contratacao de servico de limpeza"
        assert record["valor_total_estimado"] is None  # v2 listing does not include value
        assert record["modalidade_id"] == 5  # Pregao Eletronico
        assert record["modalidade_nome"] == "Pregao Eletronico"
        assert record["esfera_id"] == 3  # Municipal
        assert record["uf"] == "SC"
        assert record["municipio"] == "Florianopolis"
        assert record["codigo_municipio_ibge"] == ""  # PCP v2 does not provide IBGE code
        assert record["orgao_razao_social"] == "Prefeitura Municipal de Florianopolis"
        assert record["orgao_cnpj"] == "12345678000199"
        assert record["data_publicacao"] == "2025-06-15"
        assert record["data_abertura"] == "2025-07-01"
        assert record["data_encerramento"] == "2025-07-15"
        assert record["link_pncp"] is not None
        assert record["content_hash"] is not None

        # Count total fields (16 campos)
        expected_fields = {
            "pncp_id",
            "objeto_compra",
            "valor_total_estimado",
            "modalidade_id",
            "modalidade_nome",
            "esfera_id",
            "uf",
            "municipio",
            "codigo_municipio_ibge",
            "orgao_razao_social",
            "orgao_cnpj",
            "data_publicacao",
            "data_abertura",
            "data_encerramento",
            "link_pncp",
            "content_hash",
        }
        assert set(record.keys()) == expected_fields, (
            f"Field mismatch. Extra: {set(record.keys()) - expected_fields}. "
            f"Missing: {expected_fields - set(record.keys())}"
        )

    def test_transform_dedup(self):
        """transform() keeps records with the same pncp_id (DB-level dedup).

        PCP v2 transform does NOT deduplicate in-memory — dedup is handled
        by upsert_pncp_raw_bids at the database level. This test verifies
        that transform preserves both records with the same pncp_id.
        """
        result = pcp.transform([MOCK_RECORD, MOCK_RECORD])
        assert len(result) == 2, f"Expected 2 records (no in-memory dedup), got {len(result)}"

    def test_transform_hash_includes_process_identity(self):
        first = pcp.transform([MOCK_RECORD])[0]
        other = dict(MOCK_RECORD)
        other["codigoLicitacao"] = "99999"
        second = pcp.transform([other])[0]
        assert first["content_hash"]
        assert first["content_hash"] != ""
        assert first["content_hash"] != second["content_hash"]
        assert first["content_hash"] == pcp.transform([MOCK_RECORD])[0]["content_hash"]

    def test_fetch_page_raises_after_exhausted_server_errors(self, monkeypatch):
        monkeypatch.setattr(pcp, "PCP_MAX_RETRIES", 0)
        monkeypatch.setattr(pcp.time, "sleep", lambda _seconds: None)

        def boom(_req, timeout=None):
            del timeout
            raise urllib.error.HTTPError(
                url="https://example.test/pcp",
                code=500,
                msg="server",
                hdrs={},
                fp=None,
            )

        monkeypatch.setattr(pcp.urllib.request, "urlopen", boom)
        with pytest.raises(urllib.error.HTTPError):
            pcp._fetch_page(1, "2026-08-13", "2026-08-13")


@pytest.mark.real_db
@pytest.mark.skipif(
    os.getenv("REQUIRE_REAL_DB") != "1",
    reason="Set REQUIRE_REAL_DB=1 for the PostgreSQL content-hash proof",
)
def test_postgres_content_hash_collision_is_deterministic_and_reconciled():
    import psycopg2

    dsn = os.getenv("LOCAL_DATALAKE_DSN") or os.getenv("DATABASE_URL")
    if not dsn:
        pytest.fail("REQUIRE_REAL_DB=1 requires LOCAL_DATALAKE_DSN or DATABASE_URL")

    prefix = f"test_pcp_hash_{os.getpid()}"
    hash_one = f"{prefix}_hash_one"
    hash_two = f"{prefix}_hash_two"
    hash_three = f"{prefix}_hash_three"

    def record(suffix: str, content_hash: str | None, *, synthetic: bool = False) -> dict:
        return {
            "pncp_id": f"{prefix}_{suffix}",
            "numero_controle_pncp": f"{prefix}_{suffix}",
            "objeto_compra": f"record {suffix}",
            "content_hash": content_hash,
            "source": "pcp",
            "source_id": suffix,
            "synthetic_id": synthetic,
        }

    connection = psycopg2.connect(dsn)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL statement_timeout = '30s'")

            batch = [record("b", hash_one), record("a", hash_one)]
            cursor.execute("SELECT * FROM upsert_pncp_raw_bids(%s::jsonb)", (json.dumps(batch),))
            assert cursor.fetchone() == (1, 0, 1)
            cursor.execute(
                "SELECT pncp_id FROM pncp_raw_bids WHERE content_hash = %s",
                (hash_one,),
            )
            assert cursor.fetchone()[0] == f"{prefix}_a"

            cursor.execute(
                "SELECT * FROM upsert_pncp_raw_bids(%s::jsonb)",
                (json.dumps(list(reversed(batch))),),
            )
            assert cursor.fetchone() == (0, 0, 2)

            cursor.execute(
                "SELECT * FROM upsert_pncp_raw_bids(%s::jsonb)",
                (json.dumps([record("c", hash_one)]),),
            )
            assert cursor.fetchone() == (0, 0, 1)

            cursor.execute(
                "SELECT * FROM upsert_pncp_raw_bids(%s::jsonb)",
                (json.dumps([record("d", hash_two)]),),
            )
            assert cursor.fetchone() == (1, 0, 0)
            cursor.execute(
                "SELECT * FROM upsert_pncp_raw_bids(%s::jsonb)",
                (json.dumps([record("d", hash_three)]),),
            )
            assert cursor.fetchone() == (0, 1, 0)
            cursor.execute(
                "SELECT * FROM upsert_pncp_raw_bids(%s::jsonb)",
                (json.dumps([record("d", hash_one)]),),
            )
            assert cursor.fetchone() == (0, 0, 1)
            cursor.execute(
                "SELECT content_hash FROM pncp_raw_bids WHERE pncp_id = %s",
                (f"{prefix}_d",),
            )
            assert cursor.fetchone()[0] == hash_three

            null_hash = record("e", None)
            cursor.execute(
                "SELECT * FROM upsert_pncp_raw_bids(%s::jsonb)",
                (json.dumps([null_hash]),),
            )
            assert cursor.fetchone() == (1, 0, 0)
            null_hash["objeto_compra"] = "record e updated without hash"
            cursor.execute(
                "SELECT * FROM upsert_pncp_raw_bids(%s::jsonb)",
                (json.dumps([null_hash]),),
            )
            assert cursor.fetchone() == (0, 1, 0)
            cursor.execute(
                "SELECT objeto_compra FROM pncp_raw_bids WHERE pncp_id = %s",
                (f"{prefix}_e",),
            )
            assert cursor.fetchone()[0] == "record e updated without hash"

            cursor.execute(
                "SELECT COUNT(*), COUNT(DISTINCT content_hash) "
                "FROM pncp_raw_bids WHERE pncp_id = ANY(%s)",
                ([f"{prefix}_a", f"{prefix}_d"],),
            )
            assert cursor.fetchone() == (2, 2)
    finally:
        connection.rollback()
        connection.close()


# ---------------------------------------------------------------------------
# modalidade mapping
# ---------------------------------------------------------------------------


class TestModalidadeMapping:
    """Tests for _map_modalidade()."""

    def test_pregao_eletronico(self):
        """Pregao Eletronico maps to modalidade_id=5."""
        mid, name = pcp._map_modalidade("Pregao Eletronico")
        assert mid == 5
        assert name == "Pregao Eletronico"

    def test_pregao_presencial(self):
        """Pregao Presencial maps to modalidade_id=6."""
        mid, name = pcp._map_modalidade("Pregao Presencial")
        assert mid == 6

    def test_concorrencia(self):
        """Concorrencia maps to modalidade_id=4."""
        mid, name = pcp._map_modalidade("Concorrencia")
        assert mid == 4

    def test_concorrencia_antiga(self):
        """Concorrencia Antiga maps to modalidade_id=1."""
        mid, name = pcp._map_modalidade("Concorrencia Antiga")
        assert mid == 1

    def test_tomada_de_precos(self):
        """Tomada de Precos maps to modalidade_id=2."""
        mid, name = pcp._map_modalidade("Tomada de Precos")
        assert mid == 2

    def test_convite(self):
        """Convite maps to modalidade_id=3."""
        mid, name = pcp._map_modalidade("Convite")
        assert mid == 3

    def test_inexigibilidade(self):
        """Inexigibilidade maps to modalidade_id=8."""
        mid, name = pcp._map_modalidade("Inexigibilidade")
        assert mid == 8

    def test_dispensa_licitacao(self):
        """Dispensa de Licitação maps to modalidade_id=7."""
        mid, name = pcp._map_modalidade("Dispensa de Licitação")
        assert mid == 7

    def test_dispensa_shorthand(self):
        """'Dispensa' shorthand maps to modalidade_id=7."""
        mid, name = pcp._map_modalidade("Dispensa")
        assert mid == 7

    def test_leilao(self):
        """Leilao maps to modalidade_id=10."""
        mid, name = pcp._map_modalidade("Leilao")
        assert mid == 10

    def test_contratacao_direta(self):
        """Contratacao Direta maps to modalidade_id=7."""
        mid, name = pcp._map_modalidade("Contratacao Direta")
        assert mid == 7

    def test_unknown_modalidade(self):
        """Unknown modalidade returns (0, raw)."""
        mid, name = pcp._map_modalidade("Modalidade Desconhecida XYZ")
        assert mid == 0
        assert name == "Modalidade Desconhecida XYZ"

    def test_empty_modalidade(self):
        """Empty modalidade returns (0, '')."""
        mid, name = pcp._map_modalidade("")
        assert mid == 0
        assert name == ""

    def test_modalidade_with_numbering(self):
        """Modalidade with numbering prefix is normalized correctly."""
        mid, name = pcp._map_modalidade("1. Pregao Eletronico")
        assert mid == 5

    def test_modalidade_with_accent(self):
        """Modalidade with accents is normalized correctly."""
        mid, name = pcp._map_modalidade("Pregão Eletrônico")
        assert mid == 5


# ---------------------------------------------------------------------------
# esfera inference
# ---------------------------------------------------------------------------


class TestEsferaInference:
    """Tests for _infer_esfera()."""

    def test_municipal_prefeitura(self):
        """'Prefeitura Municipal de ...' infers esfera_id=3."""
        assert pcp._infer_esfera("Prefeitura Municipal de Florianopolis") == 3

    def test_municipal_camara(self):
        """'Camara Municipal de ...' infers esfera_id=3."""
        assert pcp._infer_esfera("Camara Municipal de Sao Jose") == 3

    def test_estadual_secretaria(self):
        """'Secretaria de Estado de ...' infers esfera_id=2."""
        assert pcp._infer_esfera("Secretaria de Estado da Saude") == 2

    def test_estadual_deinfra(self):
        """'DEINFRA' infers esfera_id=2."""
        assert pcp._infer_esfera("DEINFRA - Departamento de Infraestrutura") == 2

    def test_federal_ministerio(self):
        """'Ministerio da ...' infers esfera_id=1."""
        assert pcp._infer_esfera("Ministerio da Saude") == 1

    def test_federal_universidade(self):
        """'Universidade Federal ...' infers esfera_id=1."""
        assert pcp._infer_esfera("Universidade Federal do Rio Grande do Sul") == 1

    def test_estadual_udesc(self):
        """'UDESC' infers esfera_id=2."""
        assert pcp._infer_esfera("UDESC - Universidade do Estado") == 2

    def test_default_municipal(self):
        """Unknown organization defaults to esfera_id=3."""
        assert pcp._infer_esfera("Empresa Privada Ltda") == 3

    def test_empty_string(self):
        """Empty string defaults to esfera_id=3."""
        assert pcp._infer_esfera("") == 3

"""AC9 / AC10 — verifier fail-closed e whitelist de key-set no conteudo real."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from scripts.confenge_live_intelligence import schema as li_schema
from scripts.confenge_live_intelligence.producer import build_snapshot
from scripts.confenge_live_intelligence.verifier import (
    LiveIntelligenceVerificationError,
    verify_snapshot,
)
from tests.confenge_live_intelligence.conftest import SEED_PREFIX, seed_bid

pytestmark = pytest.mark.real_db

AS_OF = date(2026, 9, 2)
UTC_NOW = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
CREATED_BY = f"{SEED_PREFIX}verifier"


def _universe():
    company = li_schema.LiveCompany(
        company_root8="11222333",
        source_as_of=UTC_NOW,
        date_resolver_version="ca-v2-precedence/1.0",
        observed_objects=("Reforma de escola municipal com estrutura metalica pesada",),
        observed_value_bands=("100K_1M",),
        observed_ufs=("SC",),
        observed_buyer_cnpjs=("12345678000199",),
        most_recent_contracting_date=date(2025, 5, 1),
        contracting_date_state=li_schema.OBSERVED,
    )
    opportunity = li_schema.LiveOpportunity(
        opportunity_id=f"{SEED_PREFIX}OP-VERIFY",
        source="pncp",
        source_as_of=UTC_NOW,
        objeto="Reforma de unidade basica de saude com estrutura metalica",
        objeto_state=li_schema.OBSERVED,
        valor_estimado_brl=Decimal("250000"),
        valor_state=li_schema.OBSERVED,
        valor_band="100K_1M",
        modalidade="Pregao",
        modalidade_state=li_schema.OBSERVED,
        uf="SC",
        geo_state=li_schema.OBSERVED,
        orgao_cnpj="12345678000199",
        orgao_state=li_schema.OBSERVED,
        data_encerramento=date(2026, 10, 1),
        deadline_state=li_schema.DEADLINE_OPEN,
    )
    return [opportunity], [company]


def _build(conn):
    opportunities, companies = _universe()
    return build_snapshot(conn, as_of=AS_OF, created_by=CREATED_BY, opportunities=opportunities, companies=companies)


def test_verify_on_the_same_connection_that_built_the_snapshot(live_conn) -> None:
    """REL-001, caminho de VERIFY — hash nao pode depender do fuso da sessao.

    Todo teste verde de verify passava por acidente: ou o universo era injetado
    (desviando da projecao, que e quem chama ``fetch_source_watermark`` e pina o
    fuso), ou o verify rodava em conexao NOVA, no fuso default. Nenhum exercitava
    o estado que um build real DEIXA na conexao: sessao em ``CUTOFF_TIMEZONE``.
    Nesse estado, a coluna ``TIMESTAMPTZ`` ``source_as_of`` voltava com outro
    ``tzinfo``, o ``isoformat()`` mudava e o verifier falhava FECHADO sobre um
    snapshot intacto (medido antes da correcao: "hash de linha divergente
    (opportunity, opportunity_hash)"). Este teste usa a PROJECAO real e a MESMA
    conexao, nessa ordem — e a unica combinacao que discrimina.
    """
    seed_bid(live_conn, suffix="VERIFY-TZ-001", data_encerramento=datetime(2026, 12, 1, 12, 0, tzinfo=UTC))
    result = build_snapshot(live_conn, as_of=date(2026, 10, 1), created_by=CREATED_BY)
    assert result.state != li_schema.SNAPSHOT_BLOCKED, f"anti-vacuidade: build BLOCKED ({result.blockers})"
    assert result.observed_opportunity_count >= 1, "anti-vacuidade: nada projetado"

    with live_conn.cursor() as cur:
        cur.execute("SHOW TimeZone")
        pinned = cur.fetchone()["TimeZone"]
    assert pinned == li_schema.CUTOFF_TIMEZONE, (
        f"pre-condicao do teste ausente: a sessao ficou em {pinned}, nao em {li_schema.CUTOFF_TIMEZONE}"
    )

    report = verify_snapshot(live_conn, result.snapshot_id)
    assert "row_hashes_rederived" in report.checks


def test_verifier_accepts_a_consistent_snapshot(live_conn) -> None:
    result = _build(live_conn)
    report = verify_snapshot(live_conn, result.snapshot_id)
    assert report.state == li_schema.SNAPSHOT_READY
    assert report.verified_opportunities == 1
    assert report.verified_companies == 1
    assert report.verified_fits == 1
    for check in (
        "terminal_state_sealed",
        "row_hashes_rederived",
        "payload_keyset_whitelisted",
        "fit_state_derivation",
        "aggregate_hashes_rederived",
        "content_hash_rederived",
        "exclusion_counts_reconciled",
    ):
        assert check in report.checks


def test_unknown_snapshot_fails_closed(live_conn) -> None:
    with pytest.raises(LiveIntelligenceVerificationError):
        verify_snapshot(live_conn, f"{SEED_PREFIX}does-not-exist")


@pytest.mark.parametrize(
    "column",
    ["universe_hash", "policy_hash", "schema_hash", "data_hash", "fit_hash", "content_hash"],
)
def test_tampered_aggregate_hash_fails_closed(live_conn, column: str) -> None:
    result = _build(live_conn)
    forged = "0" * 64
    with live_conn.cursor() as cur:
        cur.execute(
            f"UPDATE public.confenge_live_intelligence_snapshots SET {column} = %s WHERE snapshot_id = %s",
            (forged, result.snapshot_id),
        )
    live_conn.commit()
    with pytest.raises(LiveIntelligenceVerificationError) as exc:
        verify_snapshot(live_conn, result.snapshot_id)
    assert column in str(exc.value) or "content_hash" in str(exc.value)


def test_tampered_row_content_fails_closed(live_conn) -> None:
    """Conteudo alterado sem recomputar o hash de linha ⇒ divergencia explicita."""
    result = _build(live_conn)
    with live_conn.cursor() as cur:
        cur.execute(
            "UPDATE public.confenge_live_intelligence_opportunities SET objeto = %s WHERE snapshot_id = %s",
            ("Objeto adulterado depois do selo do snapshot", result.snapshot_id),
        )
    live_conn.commit()
    with pytest.raises(LiveIntelligenceVerificationError) as exc:
        verify_snapshot(live_conn, result.snapshot_id)
    assert "opportunity_hash" in str(exc.value)


def test_tampered_exclusion_count_fails_closed(live_conn) -> None:
    result = _build(live_conn)
    with live_conn.cursor() as cur:
        cur.execute(
            "UPDATE public.confenge_live_intelligence_snapshots "
            "SET state = 'PARTIAL', excluded_opportunity_count = 1 WHERE snapshot_id = %s",
            (result.snapshot_id,),
        )
    live_conn.commit()
    with pytest.raises(LiveIntelligenceVerificationError):
        verify_snapshot(live_conn, result.snapshot_id)


def test_verifier_never_returns_partial_success(live_conn) -> None:
    """AC9 — nao existe caminho de retorno degradado: ou report valido, ou excecao."""
    result = _build(live_conn)
    with live_conn.cursor() as cur:
        cur.execute(
            "UPDATE public.confenge_live_intelligence_fit SET dim_geography = 'NO_MATCH', "
            "fit_state = 'OBSERVED_FIT' WHERE snapshot_id = %s",
            (result.snapshot_id,),
        )
    live_conn.commit()
    with pytest.raises(LiveIntelligenceVerificationError):
        verify_snapshot(live_conn, result.snapshot_id)


def test_persisted_payload_keyset_stays_within_schema(live_conn) -> None:
    """AC10 sobre o conteudo REALMENTE persistido, nao apenas sobre o objeto Python."""
    result = _build(live_conn)
    verify_snapshot(live_conn, result.snapshot_id)  # inclui a checagem de whitelist
    with live_conn.cursor() as cur:
        cur.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = %s",
            ("confenge_live_intelligence_opportunities",),
        )
        columns = {r["column_name"] for r in cur.fetchall()}
    for column in columns:
        assert not any(term in column.lower() for term in li_schema.FORBIDDEN_PII_KEY_TERMS), column


def test_blocked_snapshot_verification_requires_blockers(live_conn) -> None:
    result = build_snapshot(live_conn, as_of=None, created_by=CREATED_BY)
    report = verify_snapshot(live_conn, result.snapshot_id)
    assert report.state == li_schema.SNAPSHOT_BLOCKED

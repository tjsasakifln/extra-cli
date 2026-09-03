"""AC8 — o criterio de estado do snapshot e alcancavel nas tres direcoes.

Marcador reportado por este arquivo: ``LIVE_INTELLIGENCE_HANDOFF_READY``.
"""

from __future__ import annotations

import os
import time
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from scripts.confenge_live_intelligence import schema as li_schema
from scripts.confenge_live_intelligence import sources as li_sources
from scripts.confenge_live_intelligence.producer import (
    build_snapshot,
    project_companies,
)
from tests.confenge_live_intelligence.conftest import (
    LIVE_TABLES,
    SEED_PREFIX,
    seed_bid,
    today_cutoff_tz,
)

pytestmark = pytest.mark.real_db

AS_OF = date(2026, 9, 2)
UTC_NOW = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)
CREATED_BY = f"{SEED_PREFIX}producer-state"


def _company(**overrides) -> li_schema.LiveCompany:
    base = dict(
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
    base.update(overrides)
    return li_schema.LiveCompany(**base)


def _opportunity(**overrides) -> li_schema.LiveOpportunity:
    base = dict(
        opportunity_id=f"{SEED_PREFIX}OP-1",
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
    base.update(overrides)
    return li_schema.LiveOpportunity(**base)


def test_ready_canonical_is_reachable_with_unknown_in_optional_dimensions(live_conn) -> None:
    """READY exige zero exclusao — UNKNOWN em dimensao OPCIONAL nao exclui (R11)."""
    opportunity = _opportunity(
        valor_estimado_brl=None,
        valor_state=li_schema.UNKNOWN,
        valor_band=None,
        orgao_cnpj=None,
        orgao_state=li_schema.UNKNOWN,
        reason_codes=(li_schema.REASON_VALUE_MISSING, li_schema.REASON_ORGAO_MISSING),
    )
    result = build_snapshot(
        live_conn,
        as_of=AS_OF,
        created_by=CREATED_BY,
        opportunities=[opportunity],
        companies=[_company()],
    )
    assert result.state == li_schema.SNAPSHOT_READY
    assert result.excluded_opportunity_count == 0
    assert result.excluded_company_count == 0
    assert result.content_hash is not None
    assert result.blockers == ()
    assert result.handoff_marker == "YES"


def test_partial_when_required_dimension_is_unknown(live_conn) -> None:
    opportunity = _opportunity(uf=None, geo_state=li_schema.UNKNOWN, reason_codes=(li_schema.REASON_GEO_MISSING,))
    result = build_snapshot(
        live_conn,
        as_of=AS_OF,
        created_by=CREATED_BY,
        opportunities=[opportunity],
        companies=[_company()],
    )
    assert result.state == li_schema.SNAPSHOT_PARTIAL
    assert result.excluded_opportunity_count > 0
    assert result.content_hash is not None
    assert result.blockers == ()
    assert result.handoff_marker == "PARTIAL"

    with live_conn.cursor() as cur:
        cur.execute(
            "SELECT closed_at, content_hash, blockers FROM public.confenge_live_intelligence_snapshots "
            "WHERE snapshot_id = %s",
            (result.snapshot_id,),
        )
        row = cur.fetchone()
    assert row["closed_at"] is not None
    assert row["content_hash"] is not None
    assert row["blockers"] == []


def test_partial_when_contracting_date_is_unresolved(live_conn) -> None:
    """``dim_recency`` nao resolvida ⇒ empresa excluida ⇒ PARTIAL (caso real sem #531)."""
    company = _company(
        most_recent_contracting_date=None,
        contracting_date_state=li_schema.UNKNOWN,
        row_completeness_state=li_schema.ROW_EXCLUDED_UNRESOLVED_DATE,
        exclusion_reason_codes=(li_schema.REASON_CONTRACTING_DATE_UNRESOLVED,),
        reason_codes=(li_schema.REASON_CONTRACTING_DATE_UNRESOLVED,),
    )
    result = build_snapshot(
        live_conn,
        as_of=AS_OF,
        created_by=CREATED_BY,
        opportunities=[_opportunity()],
        companies=[company],
    )
    assert result.state == li_schema.SNAPSHOT_PARTIAL
    assert result.excluded_company_count == 1


def test_blocked_when_as_of_date_is_missing(live_conn) -> None:
    """REL-002 — a data civil do snapshot BLOCKED vem de ``CUTOFF_TIMEZONE``.

    ``date.today()`` resolvia no fuso do SO. Como ``as_of_date`` compoe o
    ``snapshot_id`` do BLOCKED, entre ~21:00 e 00:00 UTC o mesmo bloqueio
    gerava dois ids. A asserção abaixo discrimina: a data vem do MESMO fuso que
    ``pin_session_timezone``/``policy_hash`` selam, importado por nome.
    """
    result = build_snapshot(live_conn, as_of=None, created_by=CREATED_BY)
    assert result.state == li_schema.SNAPSHOT_BLOCKED
    assert li_schema.BLOCKER_AS_OF_MISSING in result.blockers
    assert result.content_hash is None
    expected_date = today_cutoff_tz()
    assert result.as_of_date == expected_date, (
        f"as_of_date={result.as_of_date} nao e a data civil de {li_schema.CUTOFF_TIMEZONE} "
        f"({expected_date}) — REL-002 regrediu"
    )
    assert result.snapshot_id == f"LI-{expected_date.isoformat()}-BLOCKED-{result.universe_hash[:20]}"


def test_blocked_as_of_date_is_immune_to_the_os_timezone(live_conn) -> None:
    """REL-002 — a prova que DISCRIMINA em qualquer hora do dia.

    A asserção do teste acima so pega ``date.today()`` dentro da janela em que
    o fuso do SO e ``CUTOFF_TIMEZONE`` discordam da data civil (~3h/dia). Rodar
    o mesmo build sob DOIS fusos de SO cujos offsets distam 25h
    (``Pacific/Kiritimati`` UTC+14 e ``Pacific/Niue`` UTC-11) torna a prova
    determinística: com ``date.today()`` as duas datas civis NUNCA coincidem;
    com a derivacao de ``CUTOFF_TIMEZONE`` sao sempre a mesma.
    """
    original_tz = os.environ.get("TZ")
    observed: dict[str, date] = {}
    try:
        for tz_name in ("Pacific/Kiritimati", "Pacific/Niue"):
            os.environ["TZ"] = tz_name
            time.tzset()
            result = build_snapshot(live_conn, as_of=None, created_by=CREATED_BY)
            observed[tz_name] = result.as_of_date
    finally:
        if original_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = original_tz
        time.tzset()

    assert len(set(observed.values())) == 1, (
        f"as_of_date do snapshot BLOCKED seguiu o fuso do SO: {observed} — REL-002 regrediu"
    )
    assert next(iter(observed.values())) == today_cutoff_tz()


def test_blocked_when_watermark_is_missing(live_conn) -> None:
    """Watermark ausente e blocker da lista fechada (§7.2) — nao degradacao.

    O DELETE abaixo e DELIBERADAMENTE escopado ao prefixo ``LI-TEST-``. NAO
    ampliar: contra um datalake populado, este teste deve FALHAR (ha watermark
    real) em vez de passar apagando dados de producao. A direcao de falha e a
    correta e e intencional.
    """
    with live_conn.cursor() as cur:
        cur.execute("DELETE FROM public.pncp_raw_bids WHERE pncp_id LIKE %s", (f"{SEED_PREFIX}%",))
    live_conn.commit()
    # NOTA (TD-LI-6, ratificado): a unica alteracao nesta rodada e a REMOCAO do
    # kwarg `require_watermark`, que deixou de existir (o watermark passou a ser
    # pre-condicao do caminho de projecao, REL-001). As asserções — BLOCKED e
    # BLOCKER_WATERMARK_MISSING — permanecem INTACTAS, e a divida TD-LI-6
    # (falha determinística contra DSN com dados alheios) permanece aberta e
    # inalterada. Esta rodada nao a reabre nem a fecha.
    result = build_snapshot(live_conn, as_of=AS_OF, created_by=CREATED_BY)
    assert result.state == li_schema.SNAPSHOT_BLOCKED
    assert li_schema.BLOCKER_WATERMARK_MISSING in result.blockers
    assert result.blockers != ()


def test_blocked_snapshot_is_persisted_with_blockers(live_conn) -> None:
    result = build_snapshot(
        live_conn,
        as_of=AS_OF,
        created_by=CREATED_BY,
        opportunities=[_opportunity()],
        companies=[_company()],
        extra_blockers=[li_schema.BLOCKER_HASH_DIVERGENCE],
    )
    assert result.state == li_schema.SNAPSHOT_BLOCKED
    with live_conn.cursor() as cur:
        cur.execute(
            "SELECT state, blockers, closed_at FROM public.confenge_live_intelligence_snapshots WHERE snapshot_id = %s",
            (result.snapshot_id,),
        )
        row = cur.fetchone()
    assert row["state"] == "BLOCKED"
    assert row["blockers"] == [li_schema.BLOCKER_HASH_DIVERGENCE]
    assert row["closed_at"] is None


def test_empty_public_contract_id_is_a_blocker() -> None:
    """``public_contract_id()`` vazio sem opt-in legacy e blocker, nao descarte."""
    rows = [{"id": 42, "supplier_cnpj": "11222333000181", "objeto": "x", "uf": "SC"}]
    companies, blockers = project_companies(rows, source_as_of=UTC_NOW)
    assert companies == []
    assert li_schema.BLOCKER_EMPTY_CONTRACT_ID in blockers


def test_legacy_surrogate_requires_explicit_opt_in() -> None:
    rows = [
        {
            "id": 42,
            "supplier_cnpj": "11222333000181",
            "objeto": "Reforma de escola",
            "uf": "SC",
            "data_assinatura": date(2025, 1, 10),
        }
    ]
    companies, blockers = project_companies(rows, source_as_of=UTC_NOW, allow_legacy_surrogate=True)
    assert blockers == []
    assert len(companies) == 1
    assert companies[0].company_root8 == "11222333"


def _engine_row_counts(conn) -> dict[str, int]:
    """Contagem TOTAL por tabela do motor, SEM filtrar por ``snapshot_id``.

    Por que sem filtro (TEST-001). O teste antigo contava
    ``WHERE snapshot_id = %s`` — e era exatamente por isso que a acumulacao de
    REL-001 era invisivel: as linhas extras caiam sob OUTRO ``snapshot_id``.
    Contagem total mais ``COUNT(DISTINCT snapshot_id)`` e o unico par que
    detecta acumulacao.
    """
    counts: dict[str, int] = {}
    with conn.cursor() as cur:
        for table in LIVE_TABLES:
            cur.execute(f"SELECT COUNT(*)::int AS n FROM public.{table}")  # noqa: S608
            counts[table] = int(cur.fetchone()["n"])
    return counts


def test_replay_over_the_real_projection_is_idempotent(live_conn) -> None:
    """REL-001/TEST-001 — dois builds sobre o MESMO snapshot de entrada.

    Este teste NAO injeta ``opportunities``/``companies``: se injetasse,
    desviaria em ``build_snapshot`` e ``project_opportunity``/
    ``project_companies`` nunca seriam chamados — foi assim que o teste anterior
    mascarou REL-001. Tambem NAO fixa ``source_as_of``: o valor e derivado pelo
    proprio producer a partir do watermark observado da fonte, que e justamente
    o campo que a producao randomizava com ``datetime.now()``.
    """
    seed_bid(live_conn, suffix="REPLAY-001", data_encerramento=datetime(2026, 12, 1, 12, 0, tzinfo=UTC))
    as_of = date(2026, 10, 1)

    before = _engine_row_counts(live_conn)
    first = build_snapshot(live_conn, as_of=as_of, created_by=CREATED_BY)
    after_first = _engine_row_counts(live_conn)
    second = build_snapshot(live_conn, as_of=as_of, created_by=CREATED_BY)
    after_second = _engine_row_counts(live_conn)

    assert first.state != li_schema.SNAPSHOT_BLOCKED, (
        f"anti-vacuidade: o build entrou em BLOCKED ({first.blockers}) e a projecao nao foi exercitada"
    )
    assert first.observed_opportunity_count >= 1, "anti-vacuidade: nenhuma oportunidade projetada"

    assert first.snapshot_id == second.snapshot_id, "snapshot_id divergiu entre replays — REL-001 regrediu"
    assert first.content_hash == second.content_hash, "content_hash divergiu entre replays"
    assert first.data_hash == second.data_hash, "data_hash divergiu entre replays (source_as_of instavel)"
    assert first.universe_hash == second.universe_hash

    assert after_second == after_first, (
        "as tabelas do motor ACUMULARAM linhas no replay (contagem total, sem filtro de snapshot_id): "
        f"apos o 1o build={after_first}, apos o 2o={after_second}"
    )
    assert after_first != before, "anti-vacuidade: o 1o build nao persistiu nada"

    with live_conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(DISTINCT snapshot_id)::int AS n FROM public.confenge_live_intelligence_snapshots "
            "WHERE created_by LIKE %s",
            (f"{SEED_PREFIX}%",),
        )
        assert int(cur.fetchone()["n"]) == 1, "dois replays produziram snapshot_id distintos"


def test_company_projection_source_as_of_comes_from_the_source_watermark(live_conn) -> None:
    """REL-001, lado COMPANY — o sitio que o build sozinho nao alcanca.

    ``v_contracts_canonical_v2`` pode nao ter fornecedor no DSN de teste (e nao
    ha como semear sem escrever em tabela do plano outbound, proibido por
    AR-1/AR-2). Sem este teste, o teste de replay acima passaria mesmo que
    ``project_companies`` continuasse em relogio de parede. As linhas sao
    sinteticas em memoria; o ``source_as_of`` e RE-LIDO do watermark real a cada
    chamada — nada pinado a mao.
    """
    rows = [
        {
            "contrato_id": f"{SEED_PREFIX}CT-1",
            "supplier_cnpj": "11222333000181",
            "supplier_nome": "Construtora Sintetica LI-TEST",
            "objeto": "Reforma de escola municipal com estrutura metalica",
            "valor": "250000.00",
            "uf": "SC",
            "buyer_cnpj": "12345678000199",
            "data_assinatura": date(2025, 5, 1),
        }
    ]

    def _project_once() -> li_schema.LiveCompany:
        watermark = li_sources.fetch_source_watermark(live_conn, "pncp")
        assert watermark is not None, "sem watermark a projecao e indefinida (ramo BLOCKED do producer)"
        companies, blockers = project_companies(
            rows, source_as_of=watermark["watermark_at"], allow_legacy_surrogate=True
        )
        assert blockers == []
        assert len(companies) == 1
        return companies[0]

    seed_bid(live_conn, suffix="CO-WM-001", data_encerramento=datetime(2026, 12, 1, 12, 0, tzinfo=UTC))
    first = _project_once()
    second = _project_once()

    assert first.source_as_of == second.source_as_of, "source_as_of da COMPANY nao e estavel — relogio de parede"
    assert first.portfolio_hash() == second.portfolio_hash(), "portfolio_hash divergiu para o mesmo portfolio"

    with live_conn.cursor() as cur:
        cur.execute("SELECT MAX(updated_at) AS w FROM public.pncp_raw_bids WHERE source = 'pncp'")
        watermark_at = cur.fetchone()["w"]
    assert first.source_as_of == watermark_at, (
        f"source_as_of={first.source_as_of} nao e o watermark da fonte ({watermark_at})"
    )


def test_handoff_marker_is_reported(live_conn) -> None:
    result = build_snapshot(
        live_conn,
        as_of=AS_OF,
        created_by=CREATED_BY,
        opportunities=[_opportunity()],
        companies=[_company()],
    )
    marker = result.as_dict()["LIVE_INTELLIGENCE_HANDOFF_READY"]
    assert marker in {"YES", "PARTIAL", "NO"}
    print(f"LIVE_INTELLIGENCE_HANDOFF_READY={marker}")

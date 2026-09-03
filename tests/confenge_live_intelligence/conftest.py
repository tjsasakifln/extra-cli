"""Fixtures de banco real para o motor inbound.

Politica seguida (conftest raiz + ``scripts/testing/real_db_guard.py``):
``@pytest.mark.real_db`` sem ``REQUIRE_REAL_DB=1`` faz SKIP limpo antes de
qualquer conexao; com ``REQUIRE_REAL_DB=1`` o skip vira falha nomeada.

Toda semente e prefixada com ``LI-TEST-`` e removida por DELETE escopado ao
prefixo. Nenhuma tabela do pipeline outbound (target-fit, sector, opportunity
intel, canonical snapshots) e escrita em nenhum momento.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from scripts.confenge_live_intelligence.schema import CUTOFF_TIMEZONE

SEED_PREFIX = "LI-TEST-"
LIVE_TABLES = (
    "confenge_live_intelligence_events",
    "confenge_live_intelligence_fit",
    "confenge_live_intelligence_companies",
    "confenge_live_intelligence_opportunities",
    "confenge_live_intelligence_source_watermarks",
    "confenge_live_intelligence_snapshots",
)

REQUIRED_TABLES = (
    "pncp_raw_bids",
    "confenge_live_intelligence_snapshots",
    "confenge_live_intelligence_opportunities",
    "confenge_live_intelligence_companies",
    "confenge_live_intelligence_fit",
)


def _open_connection() -> tuple[Any, str]:
    from scripts.testing.real_db_guard import admit_ready_connection

    def opener(dsn: str, **kwargs: Any) -> Any:
        import psycopg2
        import psycopg2.extras

        return psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor, **kwargs)

    # LI-W2 / AC10 e TD-LI-6 — `make li-equiv` exporta `LI_EQUIV_DSN` (DSN
    # ADMINISTRATIVO apontando para `extra_li_equiv`; o role restrito
    # `li_equiv_runner` e usado apenas por `test_outbound_equivalence.py`, que e
    # onde a restricao de privilegio E a prova) e as MESMAS
    # suites passam a rodar contra o banco ISOLADO `extra_li_equiv`, sem alterar
    # nenhuma asserção e sem ampliar o escopo do `DELETE ... LIKE 'LI-TEST-%'`
    # abaixo. A correcao do nao-determinismo de
    # `test_blocked_when_watermark_is_missing` e isolamento de banco, nao
    # relaxamento de assert: o watermark de `extra_test` e compartilhado com as
    # demais suites e contamina o caso BLOCKED.
    # `real_db_guard` nao e tocado (infra compartilhada): a redirecao e local e
    # restaurada no `finally`.
    equivalence_dsn = os.environ.get("LI_EQUIV_DSN", "").strip()
    previous = os.environ.get("LOCAL_DATALAKE_DSN")
    if equivalence_dsn:
        os.environ["LOCAL_DATALAKE_DSN"] = equivalence_dsn
    try:
        return admit_ready_connection(
            required_tables=REQUIRED_TABLES,
            required_views=("v_open_opportunities_canonical",),
            context="confenge_live_intelligence",
            opener=opener,
        )
    finally:
        if equivalence_dsn:
            if previous is None:
                os.environ.pop("LOCAL_DATALAKE_DSN", None)
            else:
                os.environ["LOCAL_DATALAKE_DSN"] = previous


@pytest.fixture
def live_conn() -> Iterator[Any]:
    conn, _dsn = _open_connection()
    try:
        _cleanup(conn)
        yield conn
    finally:
        try:
            _cleanup(conn)
        finally:
            conn.close()


def _cleanup(conn: Any) -> None:
    owned = "SELECT snapshot_id FROM public.confenge_live_intelligence_snapshots WHERE created_by LIKE %s"
    with conn.cursor() as cur:
        for table in LIVE_TABLES:
            if table == "confenge_live_intelligence_snapshots":
                continue
            cur.execute(
                f"DELETE FROM public.{table} WHERE snapshot_id IN ({owned})",
                (f"{SEED_PREFIX}%",),
            )
        cur.execute(
            "DELETE FROM public.confenge_live_intelligence_snapshots WHERE created_by LIKE %s",
            (f"{SEED_PREFIX}%",),
        )
        cur.execute("DELETE FROM public.pncp_raw_bids WHERE pncp_id LIKE %s", (f"{SEED_PREFIX}%",))
    conn.commit()


def seed_bid(
    conn: Any,
    *,
    suffix: str,
    objeto: str = "Reforma de unidade basica de saude com estrutura metalica",
    valor: str | None = "250000.00",
    uf: str | None = "SC",
    orgao_cnpj: str | None = "12345678000199",
    data_encerramento: datetime | None = None,
    data_publicacao: datetime | None = None,
) -> str:
    """Insere um edital sintetico em ``pncp_raw_bids``. Sempre prefixado."""
    pncp_id = f"{SEED_PREFIX}{suffix}"
    if data_publicacao is None:
        data_publicacao = datetime.now(tz=UTC) - timedelta(days=120)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO public.pncp_raw_bids (
                pncp_id, objeto_compra, valor_total_estimado, modalidade_id, modalidade_nome,
                uf, municipio, orgao_cnpj, orgao_razao_social,
                data_publicacao, data_encerramento, source, source_id, is_active, updated_at
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (pncp_id) DO UPDATE SET
                objeto_compra = EXCLUDED.objeto_compra,
                data_encerramento = EXCLUDED.data_encerramento
            """,
            (
                pncp_id,
                objeto,
                valor,
                6,
                "Pregao Eletronico",
                uf,
                "Florianopolis",
                orgao_cnpj,
                "Prefeitura Sintetica LI-TEST",
                data_publicacao,
                data_encerramento,
                "pncp",
                pncp_id,
                True,
                datetime.now(tz=UTC),
            ),
        )
    conn.commit()
    return pncp_id


def today_cutoff_tz() -> date:
    """Data civil de hoje no MESMO fuso que o motor fixa (TD-LI-7 / RULING-LI-04).

    Por que NAO e ``datetime.now(tz=UTC).date()``. O leitor as-of do motor
    (``live_open_opportunities_as_of``) resolve a data civil sob o ``TimeZone``
    que ``sources.pin_session_timezone()`` fixa — ``CUTOFF_TIMEZONE``. Derivar a
    data do teste em UTC abre uma janela de ~3h/dia (entre ~21:00 e 00:00 UTC)
    em que teste e motor operam em datas civis diferentes: o teste pede
    ``as_of(D)`` enquanto o motor considera hoje ``D-1``. Isso contaminava
    ``test_as_of_recovers_row_excluded_by_the_view`` e, pior, a unica evidencia
    de AR-1 (``test_no_outbound_write_runtime.py``), acao BLOQUEANTE do gate
    HIGH-RISK do @architect.

    Fonte de fuso UNICA. O nome do fuso e **importado** de
    ``scripts.confenge_live_intelligence.schema.CUTOFF_TIMEZONE`` — a mesma
    constante que ``pin_session_timezone()`` usa como default e que
    ``policy_hash()`` sela. Reescrever ``"America/Sao_Paulo"`` a mao aqui seria
    uma SEGUNDA fonte de verdade: exatamente o modo de falha que AR-2 fechou
    para a allowlist de escrita, e permitiria a divergencia voltar sem nada
    quebrar. O motor NAO foi alterado — a funcao as-of esta correta.
    """
    return datetime.now(tz=ZoneInfo(CUTOFF_TIMEZONE)).date()

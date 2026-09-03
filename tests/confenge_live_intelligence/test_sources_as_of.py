"""AC4 / AC5 — leitor as-of sobre a tabela base e replay cross-timezone."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from scripts.confenge_live_intelligence import producer, sources
from scripts.confenge_live_intelligence.schema import CUTOFF_TIMEZONE
from tests.confenge_live_intelligence.conftest import seed_bid, today_cutoff_tz

pytestmark = pytest.mark.real_db


def test_fixture_civil_date_matches_the_engine_timezone(live_conn) -> None:
    """TD-LI-7 — guarda determinística da correção, válida a qualquer hora.

    Por que este teste existe e por que ele nao pode ser substituido por "a
    suite ficou verde". TD-LI-7 se manifesta em ~3h/dia (entre ~21:00 e 00:00
    UTC): fora da janela, ``datetime.now(tz=UTC).date()`` e a data civil em
    ``CUTOFF_TIMEZONE`` coincidem e o defeito e invisivel. Uma execucao verde as
    14:00 UTC nao discrimina codigo corrigido de codigo defeituoso. Esta
    asserção discrimina em **qualquer** hora, porque compara a data do fixture
    com a data civil que o **proprio banco** resolve sob o fuso do motor — a
    mesma resolucao que ``live_open_opportunities_as_of`` faz internamente.

    Limite declarado do "qualquer hora". ``datetime.now()`` do Python e ``now()``
    do PostgreSQL sao duas leituras de relogio distintas: uma execucao que
    atravesse exatamente 00:00:00 em ``CUTOFF_TIMEZONE`` pode ler ``D-1`` de um
    lado e ``D`` do outro. Janela de fracao de segundo, uma vez por dia, e nao
    e o defeito de TD-LI-7 (que durava ~3h). Fica declarada em vez de
    silenciosa — esta story ja gastou duas rodadas em flakes de fuso mal
    diagnosticados e um flake nao explicado aqui custaria uma terceira.

    Cobre tambem uma lacuna que a derivacao pura em Python deixaria: divergencia
    entre a tzdata do Python e a do PostgreSQL. Se as duas bases de fuso
    discordarem, o replay as-of deixa de ser deterministico e isto quebra.

    ``SET TimeZone`` explicito: a sessao de ``live_conn`` pode chegar em
    ``Etc/UTC`` (default do banco de teste). O motor fixa o fuso antes de ler;
    aqui reproduzimos essa pre-condicao em vez de assumi-la.
    """
    sources.pin_session_timezone(live_conn)
    with live_conn.cursor() as cur:
        cur.execute("SELECT (now() AT TIME ZONE %s)::date AS civil_date", (CUTOFF_TIMEZONE,))
        row = cur.fetchone()
    engine_civil_date = row["civil_date"] if isinstance(row, dict) else row[0]
    assert today_cutoff_tz() == engine_civil_date, (
        f"fixture resolveu {today_cutoff_tz()} e o banco resolveu {engine_civil_date} "
        f"sob {CUTOFF_TIMEZONE}: a data civil do teste divergiu da do motor (TD-LI-7)"
    )


def test_as_of_recovers_row_excluded_by_the_view(live_conn) -> None:
    """AC4 — edital encerrado ontem reaparece em ``as_of(ontem)``.

    A view ``v_open_opportunities_canonical`` filtra ``>= CURRENT_DATE`` e a
    linha e irrecuperavel por qualquer consulta descendente (R2). O leitor vai a
    ``pncp_raw_bids``.
    """
    today = today_cutoff_tz()
    yesterday = today - timedelta(days=1)
    closed_at = datetime.now(tz=UTC) - timedelta(days=1)
    bid_id = seed_bid(
        live_conn,
        suffix="closed-yesterday",
        data_encerramento=closed_at,
        data_publicacao=datetime.now(tz=UTC) - timedelta(days=200),
    )

    as_of_past = {r["bid_id"] for r in sources.fetch_open_opportunities_as_of(live_conn, yesterday)}
    assert bid_id in as_of_past, "leitor as-of nao recuperou a linha excluida pela view"

    canonical = {r["bid_id"] for r in sources.fetch_canonical_open_opportunities(live_conn)}
    assert bid_id not in canonical, "fixture invalida: a view ainda enxerga o edital encerrado"


def test_as_of_current_date_equals_canonical_view(live_conn) -> None:
    """AC4 (2a metade) — a funcao e generalizacao estrita da view."""
    seed_bid(
        live_conn,
        suffix="open-future",
        data_encerramento=datetime.now(tz=UTC) + timedelta(days=30),
    )
    seed_bid(
        live_conn,
        suffix="closed-past",
        data_encerramento=datetime.now(tz=UTC) - timedelta(days=10),
        data_publicacao=datetime.now(tz=UTC) - timedelta(days=200),
    )
    as_of_today = {r["bid_id"] for r in sources.fetch_open_opportunities_as_of(live_conn, today_cutoff_tz())}
    canonical = {r["bid_id"] for r in sources.fetch_canonical_open_opportunities(live_conn)}
    assert as_of_today == canonical


def test_session_timezone_is_pinned_before_reading(live_conn) -> None:
    with live_conn.cursor() as cur:
        cur.execute("SET TimeZone TO 'UTC'")
    sources.fetch_open_opportunities_as_of(live_conn, today_cutoff_tz())
    assert sources.session_timezone(live_conn) == "America/Sao_Paulo"


def _boundary_encerramento():
    """02:30Z do dia D: 23:30 do dia D-1 em America/Sao_Paulo (UTC-3)."""
    base = datetime.now(tz=UTC) + timedelta(days=30)
    return base.replace(hour=2, minute=30, second=0, microsecond=0)


def test_boundary_row_is_timezone_sensitive_without_pinning(live_conn) -> None:
    """Guarda anti-vacuidade de AC5: sem fixar TZ, o conjunto REALMENTE muda."""
    boundary = _boundary_encerramento()
    bid_id = seed_bid(live_conn, suffix="tz-boundary", data_encerramento=boundary)
    as_of = boundary.date()

    seen: dict[str, set[str]] = {}
    for tz_name in ("UTC", "America/Sao_Paulo"):
        with live_conn.cursor() as cur:
            cur.execute("SET TimeZone TO %s", (tz_name,))
            cur.execute(
                "SELECT bid_id FROM public.live_open_opportunities_as_of(%s) ORDER BY bid_id",
                (as_of,),
            )
            seen[tz_name] = {r["bid_id"] for r in cur.fetchall()}
    assert bid_id in seen["UTC"]
    assert bid_id not in seen["America/Sao_Paulo"]
    assert seen["UTC"] != seen["America/Sao_Paulo"], "fixture de fronteira nao e sensivel a fuso"


def test_universe_hash_is_identical_across_session_timezones(live_conn) -> None:
    """AC5 — mesmo ``as_of`` ⇒ mesmo ``universe_hash`` sob UTC e America/Sao_Paulo."""
    boundary = _boundary_encerramento()
    seed_bid(live_conn, suffix="tz-boundary", data_encerramento=boundary)
    as_of = boundary.date()

    hashes: list[str] = []
    for tz_name in ("UTC", "America/Sao_Paulo"):
        with live_conn.cursor() as cur:
            cur.execute("SET TimeZone TO %s", (tz_name,))
        rows = sources.fetch_open_opportunities_as_of(live_conn, as_of)
        # `source_as_of` vem do watermark REAL da fonte, re-lido a cada volta —
        # nada pinado a mao (REL-001/TEST-001). O watermark nao entra em
        # `universe_hash`, mas a projecao passou a exigi-lo por proveniencia.
        watermark = sources.fetch_source_watermark(live_conn, "pncp")
        assert watermark is not None, "sem watermark a projecao e indefinida (ramo BLOCKED do producer)"
        opportunities = [
            producer.project_opportunity(r, as_of=as_of, source_as_of=watermark["watermark_at"]) for r in rows
        ]
        hashes.append(producer.universe_hash_of(opportunities, [], as_of=as_of))
    assert hashes[0] == hashes[1], "universe_hash divergiu entre fusos: replay nao determinístico"

"""AR-1 — smoke de nao-interferencia outbound observado em RUNTIME.

Gate HIGH-RISK do @architect (ADR-040, secao "Gate HIGH-RISK de arquitetura
sobre o reescopo do AC2"), acao AR-1.

Por que este arquivo existe. O AC11 prova ausencia de **literal** (e, com AR-2,
ausencia de DML dinamico fora da allowlist). Ambas as provas sao estaticas: um
caminho de escrita construido de forma que o parser nao reconheca continuaria
invisivel. Este teste nao inspeciona codigo — observa o **conteudo** de cada
objeto outbound protegido antes e depois de ``cli build`` + ``cli verify``
completos e exige igualdade byte-a-byte do dump ordenado. Prova comportamento
observado, nao ausencia de import.

Janela de checksum (conforme AR-1). Abre **depois** do ``seed_bid()`` e fecha
**depois** do producer: a fixture escreve em ``pncp_raw_bids`` sob a excecao
escopada a ``LI-TEST-`` ratificada pelo @po (RULING-LI-02), e envolver o seed
produziria falha confusa atribuida ao motor.

Condicionalidade declarada. A asserção de checksum e **incondicional** — e a
afirmacao P0 e ela vale tambem no caminho ``BLOCKED``. Apenas a asserção sobre
``cli verify`` e condicionada a o build ter alcancado estado verificavel
(``READY_CANONICAL``/``PARTIAL``): sob ``pncp_raw_bids`` poluida por suites
alheias o build pode fechar ``BLOCKED`` (TD-LI-6), e nesse caso ``verify``
falharia por motivo que nada tem a ver com a claim deste teste.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from scripts.confenge_live_intelligence import cli as li_cli
from tests.confenge_live_intelligence.conftest import SEED_PREFIX, seed_bid, today_cutoff_tz
from tests.test_live_intelligence_outbound_equivalence import PROTECTED_OBJECTS

pytestmark = pytest.mark.real_db

CREATED_BY = f"{SEED_PREFIX}ar1-runtime-smoke"


def _protected_relkinds(conn: Any) -> dict[str, str]:
    """``relkind`` de cada objeto de ``PROTECTED_OBJECTS`` existente no banco.

    Tabelas e views (``r``, ``p``, ``v``, ``m``, ``f``). O que nao existe nao
    pode ser escrito; o que existe tem de ser checado — sem lista paralela.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.relname AS relname, c.relkind AS relkind
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relkind IN ('r', 'p', 'v', 'm', 'f')
              AND c.relname = ANY(%s)
            """,
            (list(PROTECTED_OBJECTS),),
        )
        rows = cur.fetchall()
    found = {
        (row["relname"] if isinstance(row, dict) else row[0]): (row["relkind"] if isinstance(row, dict) else row[1])
        for row in rows
    }
    presentes = {obj: found[obj] for obj in PROTECTED_OBJECTS if obj in found}
    assert presentes, "nenhum objeto outbound protegido existe no banco — checksum seria vacuo"
    return presentes


def _existing_protected_objects(conn: Any) -> list[str]:
    return list(_protected_relkinds(conn))


def _fingerprint(conn: Any, objects: list[str]) -> dict[str, tuple[int, str | None]]:
    """``COUNT(*)`` + md5 do dump ordenado de cada objeto.

    Ordena por ``t::text`` (nao por ``ctid``) para que views tambem sejam
    cobertas e para que o hash nao dependa da ordem fisica das linhas.
    """
    out: dict[str, tuple[int, str | None]] = {}
    for obj in objects:
        with conn.cursor() as cur:
            # nosec/noqa justificado: `obj` vem de PROTECTED_OBJECTS, lista
            # literal do proprio teste, e foi confirmado em pg_class.
            cur.execute(
                f"SELECT count(*) AS n, md5(coalesce(string_agg(t::text, chr(10) ORDER BY t::text), '')) AS h FROM public.\"{obj}\" t"  # noqa: S608
            )
            row = cur.fetchone()
        if isinstance(row, dict):
            out[obj] = (int(row["n"]), row["h"])
        else:
            out[obj] = (int(row[0]), row[1])
    conn.commit()
    return out


def _run_cli(argv: list[str]) -> tuple[int, str]:
    import contextlib
    import io

    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = li_cli.main(argv)
    return code, buffer.getvalue()


def test_build_and_verify_leave_every_protected_object_byte_identical(live_conn: Any, capsys: Any) -> None:
    """AR-1 — a claim P0: o motor nao pode tocar o estado outbound."""
    # Fora da janela de checksum: a fixture escreve em pncp_raw_bids (excecao
    # LI-TEST- ratificada). A janela abre DEPOIS disto, conforme AR-1.
    seed_bid(
        live_conn,
        suffix="AR1-001",
        data_encerramento=datetime.now(tz=UTC) + timedelta(days=30),
    )
    live_conn.commit()

    protegidos = _existing_protected_objects(live_conn)
    antes = _fingerprint(live_conn, protegidos)

    with capsys.disabled():
        build_code, build_out = _run_cli(
            [
                "build",
                "--effective-date",
                today_cutoff_tz().isoformat(),
                "--created-by",
                CREATED_BY,
            ]
        )
    payload = json.loads(build_out)
    snapshot_id = payload["snapshot_id"]
    state = payload["state"]
    assert build_code in (0, 2), f"cli build retornou codigo inesperado {build_code}"

    verify_code: int | None = None
    if state in ("READY_CANONICAL", "PARTIAL"):
        with capsys.disabled():
            verify_code, _ = _run_cli(["verify", "--snapshot-id", snapshot_id])

    depois = _fingerprint(live_conn, protegidos)

    # --- a asserção P0, incondicional ---------------------------------------
    divergentes = {obj: (antes[obj], depois[obj]) for obj in protegidos if antes[obj] != depois[obj]}
    assert not divergentes, (
        "AR-1 violado — o motor alterou objeto outbound protegido em runtime.\n"
        + "\n".join(f"  {obj}: antes={a} depois={d}" for obj, (a, d) in divergentes.items())
        + f"\n(snapshot_id={snapshot_id}, state={state})\n"
        + "ANTES DE CONCLUIR ESCRITA OUTBOUND: se o objeto divergente for uma VIEW sobre "
        "pncp_raw_bids (v_open_opportunities_canonical filtra por CURRENT_DATE), o "
        "fingerprint pode mudar sozinho na virada de meia-noite, com zero escrita. "
        "Verifique a fronteira de CURRENT_DATE antes de tratar como P0 — esta story ja "
        "gastou duas rodadas em flakes de fuso mal diagnosticados (TD-LI-7)."
    )

    # --- condicional, declarada no docstring do modulo ----------------------
    if verify_code is not None:
        assert verify_code == 0, f"cli verify falhou para {snapshot_id} em estado {state}"


def test_engine_did_write_its_own_tables_in_the_same_run(live_conn: Any, capsys: Any) -> None:
    """Anti-vacuidade: sem escrita propria, AR-1 provaria apenas um no-op.

    Se ``build`` nao escrevesse nada, os checksums outbound seriam identicos
    trivialmente e o teste anterior nao provaria nada. Este teste ancora o
    outro: o mesmo caminho de codigo escreve, de fato, em
    ``confenge_live_intelligence_snapshots``.
    """
    seed_bid(
        live_conn,
        suffix="AR1-002",
        data_encerramento=datetime.now(tz=UTC) + timedelta(days=30),
    )
    live_conn.commit()

    with capsys.disabled():
        _, build_out = _run_cli(
            [
                "build",
                "--effective-date",
                today_cutoff_tz().isoformat(),
                "--created-by",
                CREATED_BY,
            ]
        )
    snapshot_id = json.loads(build_out)["snapshot_id"]

    live_conn.commit()
    with live_conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM public.confenge_live_intelligence_snapshots WHERE snapshot_id = %s",
            (snapshot_id,),
        )
        row = cur.fetchone()
    n = int(row["n"] if isinstance(row, dict) else row[0])
    assert n == 1, "o build nao persistiu seu proprio snapshot — AR-1 seria prova de um no-op"


def test_fingerprint_detects_a_single_row_change(live_conn: Any) -> None:
    """Dentes do instrumento: um checksum cego passaria sempre.

    Usa ``pncp_raw_bids`` sob a excecao escopada ``LI-TEST-`` ja ratificada
    (RULING-LI-02) — a unica tabela de ``PROTECTED_OBJECTS`` em que este ciclo
    tem autorizacao de escrita, e apenas por prefixo, com teardown no
    ``live_conn``. Nenhuma outra tabela protegida e tocada.
    """
    relkinds = _protected_relkinds(live_conn)
    protegidos = list(relkinds)
    assert "pncp_raw_bids" in protegidos
    antes = _fingerprint(live_conn, protegidos)

    seed_bid(
        live_conn,
        suffix="AR1-TEETH",
        data_encerramento=datetime.now(tz=UTC) + timedelta(days=30),
    )
    live_conn.commit()

    depois = _fingerprint(live_conn, protegidos)
    assert depois["pncp_raw_bids"] != antes["pncp_raw_bids"], (
        "o fingerprint nao detectou uma linha nova — o instrumento de AR-1 e cego"
    )
    assert depois["pncp_raw_bids"][0] == antes["pncp_raw_bids"][0] + 1

    # Views sobre ``pncp_raw_bids`` mudam POR CONSTRUCAO quando a tabela base
    # muda (``v_open_opportunities_canonical`` projeta editais abertos). Isso e
    # propriedade da view, nao escrita. A clausula de ausencia de efeito
    # colateral incide portanto sobre as TABELAS BASE — que sao os objetos que
    # de fato podem ser escritos, e o que AR-1 protege.
    tabelas_base = [obj for obj in protegidos if relkinds[obj] in ("r", "p") and obj != "pncp_raw_bids"]
    assert tabelas_base, "nenhuma tabela base protegida alem de pncp_raw_bids — clausula vacua"
    outras = {obj: (antes[obj], depois[obj]) for obj in tabelas_base if antes[obj] != depois[obj]}
    assert not outras, f"efeito colateral inesperado do seed em tabela base: {outras}"

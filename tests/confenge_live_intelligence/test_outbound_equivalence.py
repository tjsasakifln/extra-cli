"""AC10 / TD-LI-6 — prova de equivalencia outbound contra o banco ISOLADO.

Proposicao provada aqui, mais estreita que a da story irma: **rodar
``build_snapshot``/``export`` nao escreve em nenhuma tabela outbound.** Tres
instrumentos independentes:

1. **Conteudo** — ``md5(string_agg(t::text, '|' ORDER BY t::text))`` + ``count(*)``
   por objeto outbound, identico BEFORE/AFTER.
2. **Catalogo** — delta de ``n_tup_ins/n_tup_upd/n_tup_del`` em
   ``pg_stat_all_tables`` (apos ``pg_stat_clear_snapshot()``) igual a zero para
   todo objeto fora de ``ALLOWED_WRITE_TARGETS``.
3. **Estrutural** — o build roda sob o role dedicado ``li_equiv_runner``, com
   ``SELECT`` e nada mais nos objetos outbound: DML outbound falha por
   **permissao**, nao apenas por asserção de teste.

Este arquivo **exige** ``LI_EQUIV_RUNNER_DSN`` (exportado por ``make li-equiv``). Sem
ele faz SKIP: rodar contra ``extra_test`` compartilhado seria exatamente a causa
raiz de TD-LI-6 que o isolamento existe para eliminar.

Nao confundir com ``tests/test_live_intelligence_outbound_equivalence.py``
(estatico, sobre o texto das migrations): instrumento diferente, proposicao
diferente.
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from scripts.confenge_live_intelligence.schema import ALLOWED_WRITE_TARGETS
from tests.test_live_intelligence_outbound_equivalence import PROTECTED_OBJECTS

# O marcador `real_db` so e aplicado quando o banco isolado EXISTE.
#
# Motivo, e nao e cosmetico: `tests/conftest.py:29-44` transforma QUALQUER skip
# de um item marcado `real_db` em FALHA quando `REQUIRE_REAL_DB=1` ("execucao ou
# falha nomeada"). Este arquivo depende de um database que so
# `make li-equiv` provisiona (`extra_li_equiv` + role `li_equiv_runner`), e a
# alternativa — rodar contra `extra_test` compartilhado — e exatamente a causa
# raiz de TD-LI-6 que o isolamento existe para eliminar. Declarar `real_db` sem
# o banco seria afirmar uma capacidade que o ambiente nao tem.
_EQUIV_RUNNER_DSN = os.environ.get("LI_EQUIV_RUNNER_DSN", "").strip()
pytestmark = (
    [pytest.mark.real_db]
    if _EQUIV_RUNNER_DSN
    else [
        pytest.mark.skip(reason="LI_EQUIV_RUNNER_DSN ausente — rode `make li-equiv` (banco isolado + role restrito).")
    ]
)

REPO_ROOT = Path(__file__).resolve().parents[2]
AS_OF = date(2026, 4, 1)
CREATED_BY = "LI-TEST-equiv-outbound"


def _equivalence_dsn() -> str:
    """DSN do role RESTRITO. Sob o DSN administrativo a prova do AC10 seria vacua."""
    assert _EQUIV_RUNNER_DSN, "pytestmark deveria ter pulado este modulo"
    return _EQUIV_RUNNER_DSN


@pytest.fixture
def equiv_conn() -> Any:
    import psycopg2
    import psycopg2.extras

    dsn = _equivalence_dsn()
    conn = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        yield conn
    finally:
        conn.close()


def _existing_protected(conn: Any) -> dict[str, str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.relname AS relname, c.relkind AS relkind
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind IN ('r','p','v','m','f')
              AND c.relname = ANY(%s)
            """,
            (list(PROTECTED_OBJECTS),),
        )
        rows = cur.fetchall() or []
    found = {r["relname"]: r["relkind"] for r in rows}
    assert found, "nenhum objeto outbound existe em extra_li_equiv — a prova seria vacua"
    return found


def _fingerprint(conn: Any, objects: list[str]) -> dict[str, tuple[int, str | None]]:
    out: dict[str, tuple[int, str | None]] = {}
    with conn.cursor() as cur:
        # Fuso FIXO nas duas capturas. `t::text` renderiza TIMESTAMPTZ no fuso da
        # SESSAO, e o motor fixa `CUTOFF_TIMEZONE` em `pin_session_timezone()`:
        # sem isto o md5 mudaria por REPRESENTACAO, com zero escrita, e a falha
        # seria atribuida ao motor. Mesma classe de TD-LI-7.
        cur.execute("SET TimeZone TO 'UTC'")
    for obj in objects:
        with conn.cursor() as cur:
            # `obj` vem de PROTECTED_OBJECTS (lista do proprio teste) e foi
            # confirmado em pg_class.
            cur.execute(
                f"SELECT count(*) AS n, md5(coalesce(string_agg(t::text, '|' ORDER BY t::text), '')) AS h "  # noqa: S608
                f'FROM public."{obj}" t'
            )
            row = cur.fetchone()
        out[obj] = (int(row["n"]), row["h"])
    conn.rollback()
    return out


def _tuple_stats(conn: Any) -> dict[str, tuple[int, int, int]]:
    with conn.cursor() as cur:
        cur.execute("SELECT pg_stat_clear_snapshot()")
        cur.execute(
            """
            SELECT relname, n_tup_ins, n_tup_upd, n_tup_del
            FROM pg_stat_all_tables WHERE schemaname = 'public'
            """
        )
        rows = cur.fetchall() or []
    conn.rollback()
    return {r["relname"]: (int(r["n_tup_ins"]), int(r["n_tup_upd"]), int(r["n_tup_del"])) for r in rows}


def _wait_for_flushed_stats(
    conn: Any, *, timeout_seconds: float = 15.0
) -> tuple[dict[str, tuple[int, int, int]], dict[str, tuple[int, int, int]]]:
    """Aguarda o flush das estatisticas, ancorado na escrita do PROPRIO motor."""
    import time

    deadline = time.monotonic() + timeout_seconds
    stats: dict[str, tuple[int, int, int]] = {}
    engine: dict[str, tuple[int, int, int]] = {}
    while True:
        stats = _tuple_stats(conn)
        engine = {n: s for n, s in stats.items() if n in ALLOWED_WRITE_TARGETS and s[0] > 0}
        if engine or time.monotonic() > deadline:
            return stats, engine
        time.sleep(0.25)


def test_dsn_guard_refuses_anything_but_the_isolated_database() -> None:
    """Guarda fail-closed do dono (Task 10) — nunca extra_test, nunca producao."""
    from scripts.ops.li_equiv_db import LiEquivGuardError, assert_isolated_target

    with pytest.raises(LiEquivGuardError):
        assert_isolated_target("postgresql://test:test@127.0.0.1:5433/extra_test")
    with pytest.raises(LiEquivGuardError):
        assert_isolated_target("postgresql://u:p@db.producao.interno:5432/extra_li_equiv")
    assert assert_isolated_target("postgresql://u:p@127.0.0.1:5433/extra_li_equiv")


def test_runner_role_grants_come_from_the_single_write_allowlist() -> None:
    """AR-2/ADR-040 — o laco de GRANT itera sobre a allowlist, nao sobre lista propria.

    A proposicao POSITIVA (`for table in WRITE_TARGET_ORDER:`) e o que da dentes a
    este teste. A negativa sozinha ("nenhum literal de tabela do motor") passaria
    trivialmente num script que nem mencionasse as tabelas.
    """
    source = (REPO_ROOT / "scripts" / "ops" / "li_equiv_db.py").read_text(encoding="utf-8")
    assert "from scripts.confenge_live_intelligence.schema import WRITE_TARGET_ORDER" in source, (
        "a allowlist precisa ser IMPORTADA POR NOME do pacote do motor"
    )
    assert "for table in WRITE_TARGET_ORDER:" in source, (
        "os grants precisam ser derivados do laco sobre WRITE_TARGET_ORDER"
    )
    for table in ALLOWED_WRITE_TARGETS:
        assert f'"{table}"' not in source, f"literal de tabela do motor no script: {table}"


def test_runner_role_has_write_privilege_on_every_allowlist_table(equiv_conn) -> None:
    """Contraprova do teste acima: a derivacao chegou de fato ao catalogo."""
    from scripts.ops.li_equiv_db import EQUIV_ROLE

    with equiv_conn.cursor() as cur:
        for table in sorted(ALLOWED_WRITE_TARGETS):
            cur.execute(
                """
                SELECT has_table_privilege(%s, %s, 'SELECT') AS s,
                       has_table_privilege(%s, %s, 'INSERT') AS i,
                       has_table_privilege(%s, %s, 'UPDATE') AS u,
                       has_table_privilege(%s, %s, 'DELETE') AS d
                """,
                (EQUIV_ROLE, table) * 4,
            )
            row = cur.fetchone()
            assert all(row[k] for k in ("s", "i", "u", "d")), (
                f"{table} esta em WRITE_TARGET_ORDER mas o role nao tem DML nela: {dict(row)}"
            )
    equiv_conn.rollback()


def test_build_and_export_do_not_touch_any_outbound_object(equiv_conn, tmp_path) -> None:
    """AC10 — conteudo identico E delta de tuplas zero fora da allowlist."""
    from scripts.confenge_live_intelligence.export import export_bundle
    from scripts.confenge_live_intelligence.producer import build_snapshot

    protected = list(_existing_protected(equiv_conn))
    before_content = _fingerprint(equiv_conn, protected)
    before_stats = _tuple_stats(equiv_conn)

    result = build_snapshot(equiv_conn, as_of=AS_OF, created_by=CREATED_BY)
    assert result.state != "BLOCKED", f"build fechou BLOCKED em extra_li_equiv: {result.blockers}"
    export_bundle(equiv_conn, snapshot_id=result.snapshot_id, out_dir=tmp_path / "bundle")

    after_content = _fingerprint(equiv_conn, protected)

    divergent = {o: (before_content[o], after_content[o]) for o in protected if before_content[o] != after_content[o]}
    assert not divergent, f"conteudo outbound alterado pelo motor: {divergent}"

    # `pgstat_report_stat` so descarrega as estatisticas pendentes do backend a
    # cada ~1s (PGSTAT_MIN_INTERVAL). Ler `pg_stat_all_tables` imediatamente apos
    # o commit devolveria ZERO para TODA tabela — inclusive as outbound — e o
    # delta zero seria um FALSO PASSE. A espera e ancorada na escrita do proprio
    # motor: quando ela aparece, o flush ocorreu, e so entao o delta outbound
    # significa alguma coisa.
    after_stats, engine_moved = _wait_for_flushed_stats(equiv_conn)
    assert engine_moved, (
        "as estatisticas nunca acusaram a escrita do proprio motor — sem flush, o delta outbound abaixo seria vacuo"
    )

    moved = {
        name: (before_stats.get(name, (0, 0, 0)), stats)
        for name, stats in after_stats.items()
        if name not in ALLOWED_WRITE_TARGETS and before_stats.get(name, (0, 0, 0)) != stats
    }
    assert not moved, f"pg_stat_all_tables acusa escrita fora da allowlist: {moved}"


@pytest.mark.parametrize("table", sorted(PROTECTED_OBJECTS))
def test_runner_role_has_no_write_privilege_on_outbound_object(equiv_conn, table: str) -> None:
    """Reforco ESTRUTURAL: o role NAO TEM privilegio de escrita — catalogo, nao opiniao."""
    from scripts.ops.li_equiv_db import EQUIV_ROLE

    with equiv_conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s) AS oid", (f"public.{table}",))
        if cur.fetchone()["oid"] is None:
            pytest.skip(f"{table} inexistente em extra_li_equiv")
        cur.execute(
            """
            SELECT has_table_privilege(%s, %s, 'SELECT') AS can_select,
                   has_table_privilege(%s, %s, 'INSERT') AS can_insert,
                   has_table_privilege(%s, %s, 'UPDATE') AS can_update,
                   has_table_privilege(%s, %s, 'DELETE') AS can_delete
            """,
            (EQUIV_ROLE, table) * 4,
        )
        privileges = cur.fetchone()
    equiv_conn.rollback()
    assert privileges["can_select"], f"{table}: o role precisa de SELECT para o motor funcionar"
    for verb in ("insert", "update", "delete"):
        assert not privileges[f"can_{verb}"], f"{table}: role tem {verb.upper()} em objeto outbound"


@pytest.mark.parametrize(
    "table",
    sorted(t for t in PROTECTED_OBJECTS if not t.startswith("v_")),
)
def test_runner_role_dml_on_outbound_base_table_raises(equiv_conn, table: str) -> None:
    """Prova em RUNTIME, so para tabela base: view nao e atualizavel por outro motivo.

    Views multi-tabela levantam ``ObjectNotInPrerequisiteState`` antes de checar
    permissao — aceitar essa excecao aqui tornaria a prova ambigua. Para elas
    vale a asserção de catalogo do teste acima.
    """
    import psycopg2

    with equiv_conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s) AS oid", (f"public.{table}",))
        if cur.fetchone()["oid"] is None:
            pytest.skip(f"{table} inexistente em extra_li_equiv")
    equiv_conn.rollback()
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        with equiv_conn.cursor() as cur:
            cur.execute(f'DELETE FROM public."{table}" WHERE false')  # noqa: S608
    equiv_conn.rollback()


def test_seed_exercises_root_branch_and_unhashable_buyer(equiv_conn) -> None:
    """A semente precisa ter dentes: raiz + filial do mesmo CNPJ-8 e buyer != 14."""
    with equiv_conn.cursor() as cur:
        cur.execute(
            "SELECT fornecedor_cnpj, orgao_cnpj FROM public.pncp_supplier_contracts "
            "WHERE contrato_id LIKE 'LI-EQUIV-%' ORDER BY contrato_id"
        )
        rows = cur.fetchall() or []
    equiv_conn.rollback()
    suppliers = [r["fornecedor_cnpj"] for r in rows]
    assert len(suppliers) >= 2
    assert len({s[:8] for s in suppliers}) == 1, "raiz e filial devem compartilhar o CNPJ-8"
    assert len(set(suppliers)) == 2, "raiz e filial devem ser estabelecimentos distintos"
    assert any(len(str(r["orgao_cnpj"] or "")) != 14 for r in rows), (
        "sem buyer_cnpj != 14 digitos o caminho fail-closed do AC6 nao e exercitado"
    )

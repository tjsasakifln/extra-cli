"""AC3 + DoD de rollback — barreira select-only por objeto e ciclo reversivel.

Este arquivo prova, contra PostgreSQL real:

* AC3 (1a parte) — nenhum grant alem do REVOKE explicito existe sobre os objetos
  criados pela 104, nem para ``PUBLIC`` nem para ``smartlic_public_reader``.
* AC3 (2a parte) — a §9 da 104 (``ALTER DEFAULT PRIVILEGES``) foi REMOVIDA pelo
  @data-engineer depois de medido que o mecanismo e inerte no PostgreSQL 16. A
  condicional do AC3 ("QUANDO a 104 adicionar ``ALTER DEFAULT PRIVILEGES``...")
  tem antecedente FALSO: a 104 nao emite mais nenhum. Os testes desta secao
  passam a provar o que de fato existe — a barreira e feita EXCLUSIVAMENTE de
  ``REVOKE`` explicito por objeto — e servem de guarda de regressao caso a §9
  volte.
* DoD de rollback — aplicar 104 → rodar rollback → catalogo sem residuo
  (``pg_default_acl``, ``pg_roles``, ACLs de ``public``) → reaplicar 104 sem erro.

Os scripts sao executados pelo MESMO parser de ``scripts.ops.apply_migrations``
usado em producao (``split_sql``/``is_executable``), e nao pelo ``psql``: e a
disciplina que o repo ja adota e evita divergencia de parsing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from scripts.ops.apply_migrations import is_executable, split_sql

pytestmark = pytest.mark.real_db

REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = REPO_ROOT / "db" / "migrations" / "104_confenge_live_intelligence_v1.sql"
ROLLBACK = REPO_ROOT / "db" / "rollback" / "104_confenge_live_intelligence_v1_rollback.sql"

ENGINE_TABLES = (
    "confenge_live_intelligence_snapshots",
    "confenge_live_intelligence_source_watermarks",
    "confenge_live_intelligence_opportunities",
    "confenge_live_intelligence_companies",
    "confenge_live_intelligence_fit",
    "confenge_live_intelligence_events",
)
ENGINE_FUNCTION = "live_open_opportunities_as_of"
ENGINE_ROLE = "confenge_live_intel_reader"
SIMULATED_FUTURE_ROLE = "li_test_future_migration_owner"


def _run_sql_file(conn: Any, path: Path) -> None:
    statements = [s for s in split_sql(path.read_text(encoding="utf-8")) if is_executable(s)]
    assert statements, f"{path.name}: nenhum statement executavel"
    conn.rollback()
    old_autocommit = conn.autocommit
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            for statement in statements:
                cur.execute(statement)
    finally:
        conn.autocommit = old_autocommit


def _catalog_snapshot(conn: Any) -> dict[str, Any]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT defaclrole::regrole::text AS role,
                   defaclnamespace::regnamespace::text AS ns,
                   defaclobjtype AS objtype,
                   defaclacl::text AS acl
            FROM pg_default_acl ORDER BY 1, 2, 3
            """
        )
        default_acl = [dict(r) for r in cur.fetchall()]
        cur.execute(
            """
            SELECT c.relname, COALESCE(c.relacl::text, '') AS acl
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind IN ('r', 'v', 'm', 'p')
            ORDER BY 1
            """
        )
        rel_acl = {r["relname"]: r["acl"] for r in cur.fetchall()}
        cur.execute(
            """
            SELECT p.proname, COALESCE(p.proacl::text, '') AS acl
            FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = 'public' ORDER BY 1
            """
        )
        pro_acl = {r["proname"]: r["acl"] for r in cur.fetchall()}
        cur.execute("SELECT rolname FROM pg_roles WHERE rolname NOT LIKE 'pg\\_%' ORDER BY 1")
        roles = sorted(r["rolname"] for r in cur.fetchall())
    return {"default_acl": default_acl, "rel_acl": rel_acl, "pro_acl": pro_acl, "roles": roles}


# --- AC3 (1a parte) --------------------------------------------------------


@pytest.mark.parametrize("table", ENGINE_TABLES)
def test_engine_table_has_no_grant_to_public_or_legacy_reader(live_conn, table: str) -> None:
    with live_conn.cursor() as cur:
        cur.execute(
            "SELECT COALESCE(relacl::text, '') AS acl FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = %s",
            (table,),
        )
        row = cur.fetchone()
    assert row is not None, f"tabela {table} ausente: migration 104 nao aplicada"
    acl = row["acl"]
    assert "=arwdDxt/" not in acl.replace("test=arwdDxt/", ""), acl
    assert "smartlic_public_reader" not in acl, f"{table}: grant vazado para o reader legado"
    # PUBLIC aparece em aclitem como entrada iniciando por '=' logo apos '{' ou ','
    assert "{=" not in acl and ",=" not in acl, f"{table}: grant para PUBLIC"


def test_engine_function_grants_are_minimal(live_conn) -> None:
    with live_conn.cursor() as cur:
        cur.execute(
            "SELECT COALESCE(proacl::text, '') AS acl FROM pg_proc p "
            "JOIN pg_namespace n ON n.oid = p.pronamespace "
            "WHERE n.nspname = 'public' AND p.proname = %s",
            (ENGINE_FUNCTION,),
        )
        row = cur.fetchone()
    assert row is not None
    acl = row["acl"]
    assert acl, "proacl NULL significa default (EXECUTE para PUBLIC) — REVOKE nao aplicado"
    assert "smartlic_public_reader" not in acl
    assert "{=" not in acl and ",=" not in acl, f"EXECUTE concedido a PUBLIC: {acl}"
    assert f"{ENGINE_ROLE}=X/" in acl


def test_engine_reader_role_has_only_select(live_conn) -> None:
    with live_conn.cursor() as cur:
        cur.execute("SELECT 1 AS ok FROM pg_roles WHERE rolname = %s", (ENGINE_ROLE,))
        assert cur.fetchone() is not None, "role dedicado ausente"
        cur.execute(
            """
            SELECT table_name, privilege_type
            FROM information_schema.table_privileges
            WHERE grantee = %s AND table_schema = 'public'
            ORDER BY 1, 2
            """,
            (ENGINE_ROLE,),
        )
        grants = [(r["table_name"], r["privilege_type"]) for r in cur.fetchall()]
    assert grants, "role dedicado sem nenhum grant"
    for table, privilege in grants:
        assert privilege == "SELECT", f"{table}: privilegio alem de SELECT ({privilege})"
        assert table.startswith("confenge_live_intelligence_"), f"grant fora do motor: {table}"


def test_engine_role_has_no_grant_over_outbound_objects(live_conn) -> None:
    with live_conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name FROM information_schema.table_privileges
            WHERE grantee = %s AND table_schema = 'public'
              AND table_name NOT LIKE 'confenge_live_intelligence_%%'
            """,
            (ENGINE_ROLE,),
        )
        leaked = [r["table_name"] for r in cur.fetchall()]
    assert leaked == [], f"role do motor recebeu grant sobre objeto fora do motor: {leaked}"


# --- AC3 (2a parte): escopo por role ---------------------------------------


def test_future_migration_under_a_different_role_is_not_affected(live_conn) -> None:
    """AC3 — objeto criado por role DISTINTA nao herda nenhum default da 104.

    Com a §9 removida a 104 nao emite mais ``ALTER DEFAULT PRIVILEGES`` algum
    (ver ``test_104_barrier_is_explicit_revokes_without_default_privileges``),
    logo nao existe mecanismo que pudesse vazar para uma migration futura. O
    teste e RETIDO como guarda de regressao: se a §9 voltar sem escopo de role,
    a ACL do objeto criado aqui sob outra role deixaria de ser a default do
    PostgreSQL e a assercao quebraria.
    """
    old_autocommit = live_conn.autocommit
    live_conn.autocommit = True
    try:
        with live_conn.cursor() as cur:
            cur.execute(
                f"DROP TABLE IF EXISTS public.{SIMULATED_FUTURE_ROLE}_tbl; "
                f"DROP FUNCTION IF EXISTS public.{SIMULATED_FUTURE_ROLE}_fn()"
            )
            cur.execute("SELECT 1 AS ok FROM pg_roles WHERE rolname = %s", (SIMULATED_FUTURE_ROLE,))
            if cur.fetchone() is None:
                cur.execute(f"CREATE ROLE {SIMULATED_FUTURE_ROLE} NOLOGIN")
            cur.execute(f"GRANT {SIMULATED_FUTURE_ROLE} TO CURRENT_USER")
            cur.execute(f"GRANT CREATE ON SCHEMA public TO {SIMULATED_FUTURE_ROLE}")
            cur.execute(f"SET ROLE {SIMULATED_FUTURE_ROLE}")
            cur.execute(f"CREATE TABLE public.{SIMULATED_FUTURE_ROLE}_tbl (id INT)")
            cur.execute(f"CREATE FUNCTION public.{SIMULATED_FUTURE_ROLE}_fn() RETURNS INT LANGUAGE sql AS 'SELECT 1'")
            cur.execute("RESET ROLE")

            cur.execute(
                "SELECT relacl::text AS acl FROM pg_class c JOIN pg_namespace n "
                "ON n.oid = c.relnamespace WHERE n.nspname='public' AND relname = %s",
                (f"{SIMULATED_FUTURE_ROLE}_tbl",),
            )
            table_acl = cur.fetchone()["acl"]
            cur.execute(
                "SELECT proacl::text AS acl FROM pg_proc p JOIN pg_namespace n "
                "ON n.oid = p.pronamespace WHERE n.nspname='public' AND proname = %s",
                (f"{SIMULATED_FUTURE_ROLE}_fn",),
            )
            function_acl = cur.fetchone()["acl"]

        # Default do PostgreSQL para objeto novo: relacl/proacl NULL. Se a 104
        # tivesse escopo database/schema-wide, aqui apareceria uma ACL explicita.
        assert table_acl is None, f"tabela de outra role afetada pelos defaults da 104: {table_acl}"
        assert function_acl is None, f"funcao de outra role afetada pelos defaults da 104: {function_acl}"
    finally:
        with live_conn.cursor() as cur:
            cur.execute("RESET ROLE")
            cur.execute(f"DROP TABLE IF EXISTS public.{SIMULATED_FUTURE_ROLE}_tbl")
            cur.execute(f"DROP FUNCTION IF EXISTS public.{SIMULATED_FUTURE_ROLE}_fn()")
            cur.execute(f"REVOKE ALL ON SCHEMA public FROM {SIMULATED_FUTURE_ROLE}")
            cur.execute(f"DROP OWNED BY {SIMULATED_FUTURE_ROLE}")
            cur.execute(f"DROP ROLE IF EXISTS {SIMULATED_FUTURE_ROLE}")
        live_conn.autocommit = old_autocommit


def test_104_barrier_is_explicit_revokes_without_default_privileges(live_conn) -> None:
    """A barreira da 104 sao os REVOKE explicitos por objeto — e so eles.

    A §9 (``ALTER DEFAULT PRIVILEGES``) FOI REMOVIDA da 104 pelo @data-engineer
    apos ser medido que o mecanismo e inerte no PostgreSQL 16. Este teste nao
    testa mais o residuo de catalogo de um mecanismo que nao existe; testa o que
    de fato existe agora:

    1. **Estatico** — nenhum statement EXECUTAVEL da 104 emite ``ALTER DEFAULT
       PRIVILEGES`` (a verificacao e por statement, via o parser real de
       ``apply_migrations``: o arquivo menciona o termo varias vezes em COMENTARIO
       explicando a remocao, e uma busca por substring no texto bruto daria falso
       positivo), e existe ``REVOKE`` explicito para ``PUBLIC`` e para
       ``smartlic_public_reader`` sobre cada uma das 6 tabelas do motor e sobre a
       funcao as-of.
    2. **Catalogo** — ``pg_default_acl`` continua sem entrada em ``public``.
       Isso e agora uma GUARDA DE REGRESSAO, nao a medicao do achado: a secao 3
       do rollback foi deliberadamente esvaziada porque nao ha o que reverter, e
       ela so precisa voltar a emitir o GRANT inverso se a §9 retornar e passar a
       gravar linha.
    """
    statements = [s for s in split_sql(MIGRATION.read_text(encoding="utf-8")) if is_executable(s)]
    assert statements, "104: nenhum statement executavel"

    offenders = [s for s in statements if "ALTER DEFAULT PRIVILEGES" in " ".join(s.upper().split())]
    assert offenders == [], f"104 voltou a emitir ALTER DEFAULT PRIVILEGES: {offenders}"

    # ``split_sql`` mantem o comentario que precede o statement colado a ele, entao
    # a busca e por conteudo do statement, nao por igualdade da string inteira.
    normalized = [" ".join(s.upper().split()) for s in statements]

    def _emitted(fragment: str) -> bool:
        return any(fragment in statement for statement in normalized)

    for table in ENGINE_TABLES:
        for grantee in ("PUBLIC", "SMARTLIC_PUBLIC_READER"):
            expected = f"REVOKE ALL ON TABLE PUBLIC.{table.upper()} FROM {grantee}"
            assert _emitted(expected), f"104 sem REVOKE explicito: {expected}"
    for grantee in ("PUBLIC", "SMARTLIC_PUBLIC_READER"):
        expected = f"REVOKE ALL ON FUNCTION PUBLIC.{ENGINE_FUNCTION.upper()}(DATE) FROM {grantee}"
        assert _emitted(expected), f"104 sem REVOKE explicito na funcao: {expected}"

    with live_conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*)::int AS n FROM pg_default_acl d
            JOIN pg_namespace n ON n.oid = d.defaclnamespace
            WHERE n.nspname = 'public'
            """
        )
        entries = cur.fetchone()["n"]
    assert entries == 0, (
        "pg_default_acl com entrada em public: a §9 da 104 foi removida, entao "
        "nada aqui deveria gravar linha. Se a §9 voltar, a secao 3 do rollback "
        "precisa voltar a emitir o GRANT inverso"
    )


# --- DoD: rollback ---------------------------------------------------------


def test_rollback_removes_every_object_and_reapply_is_clean(live_conn) -> None:
    """Ciclo completo: 104 aplicada → rollback → catalogo limpo → 104 reaplicada."""
    before_rollback = _catalog_snapshot(live_conn)
    assert ENGINE_ROLE in before_rollback["roles"]
    for table in ENGINE_TABLES:
        assert table in before_rollback["rel_acl"]

    try:
        _run_sql_file(live_conn, ROLLBACK)
        after = _catalog_snapshot(live_conn)

        for table in ENGINE_TABLES:
            assert table not in after["rel_acl"], f"{table} sobreviveu ao rollback"
        assert ENGINE_FUNCTION not in after["pro_acl"], "funcao as-of sobreviveu ao rollback"
        assert ENGINE_ROLE not in after["roles"], "role do motor sobreviveu ao rollback"
        assert after["default_acl"] == [], f"rollback deixou residuo em pg_default_acl: {after['default_acl']}"
        for name, acl in after["rel_acl"].items():
            assert acl == before_rollback["rel_acl"].get(name, acl), (
                f"ACL de objeto pre-existente mudou apos o rollback: {name}"
            )
    finally:
        _run_sql_file(live_conn, MIGRATION)

    restored = _catalog_snapshot(live_conn)
    assert ENGINE_ROLE in restored["roles"], "reaplicacao da 104 falhou em recriar o role"
    for table in ENGINE_TABLES:
        assert table in restored["rel_acl"], f"reaplicacao da 104 nao recriou {table}"
    assert restored["rel_acl"] == before_rollback["rel_acl"], "ACLs divergiram apos rollback+reapply"
    assert restored["pro_acl"] == before_rollback["pro_acl"], "ACLs de funcao divergiram"
    assert restored["default_acl"] == before_rollback["default_acl"]
    assert restored["roles"] == before_rollback["roles"]

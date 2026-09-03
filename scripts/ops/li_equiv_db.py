"""LI-W2 Task 10 / AC10 — banco isolado ``extra_li_equiv`` e role ``li_equiv_runner``.

**Dono unico do provisionamento.** Nenhuma migration (104, 105 ou futura) concede
DML nas tabelas do motor: ``confenge_live_intel_reader`` e role de LEITURA e vive
em todo database que aplicar a 104, produção inclusive. Alarga-lo para satisfazer
um teste local contradiria o proprio AC10.

**Fato de PostgreSQL que dita o desenho: ``CREATE ROLE`` e cluster-global.**
"Role local do ``extra_li_equiv``" nao existe; o que e por-database sao os
*grants*. Daí: nome distinto e nao colidente (``li_equiv_runner``), criado so por
este script, so no cluster de teste local, com grants exclusivamente dentro de
``extra_li_equiv``, e teardown obrigatorio — role vazado e residuo de catalogo
**cluster-global** que quebra
``test_rollback_removes_every_object_and_reapply_is_clean`` de forma concorrente.

**Grants derivados de ``schema.WRITE_TARGET_ORDER``, importado por nome.** Uma
segunda lista literal aqui seria uma segunda allowlist — o defeito que AR-2/
ADR-040 ja rejeitou. Enumerar "so INSERT/DELETE" por palpite tambem quebraria o
persist, que faz ``UPDATE``, e o ``USAGE`` de sequence.

**Guarda fail-closed na entrada:** aborta se o dbname do DSN nao for
``extra_li_equiv`` ou se o host nao for loopback. Este script nunca pode ser
apontado para ``extra_test`` nem para producao por engano de variavel de
ambiente, e nao entra em nenhum caminho de deploy.

Uso::

    python3 -m scripts.ops.li_equiv_db up      # cria, migra ate a 105, semeia, concede
    python3 -m scripts.ops.li_equiv_db dsn        # DSN do role restrito li_equiv_runner
    python3 -m scripts.ops.li_equiv_db admin-dsn  # DSN administrativo no MESMO banco
    python3 -m scripts.ops.li_equiv_db down    # teardown idempotente
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from scripts.confenge_live_intelligence.schema import WRITE_TARGET_ORDER
from scripts.confenge_live_intelligence.sources import AS_OF_FUNCTION

EQUIV_DB = "extra_li_equiv"
EQUIV_ROLE = "li_equiv_runner"
# Senha efemera: o role so existe entre `up` e `down`, so no cluster local, e o
# DSN nunca sai da maquina. Nao e segredo de producao.
EQUIV_PASSWORD = "li_equiv_runner_local"  # noqa: S105 - credencial efemera de teste local, ver comentario acima
MAINTENANCE_DB = "postgres"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", ""})

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED_FILE = REPO_ROOT / "fixtures" / "confenge_live_intelligence" / "equivalence_seed.sql"

DEFAULT_ADMIN_DSN = "postgresql://test:test@127.0.0.1:5433/extra_test"


class LiEquivGuardError(RuntimeError):
    """DSN fora do alvo permitido. Fail-closed, sem aviso e sem prosseguir."""


def admin_dsn() -> str:
    return os.environ.get("LOCAL_DATALAKE_DSN") or DEFAULT_ADMIN_DSN


def _with_database(dsn: str, dbname: str) -> str:
    parts = urlsplit(dsn)
    return urlunsplit((parts.scheme, parts.netloc, f"/{dbname}", parts.query, parts.fragment))


def runner_dsn(dsn: str | None = None) -> str:
    """DSN do role dedicado, apontando para ``extra_li_equiv``."""
    parts = urlsplit(dsn or admin_dsn())
    host = parts.hostname or "127.0.0.1"
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme}://{EQUIV_ROLE}:{EQUIV_PASSWORD}@{host}{port}/{EQUIV_DB}"


def assert_isolated_target(dsn: str) -> str:
    """Guarda fail-closed: dbname == ``extra_li_equiv`` **e** host loopback."""
    parts = urlsplit(dsn)
    dbname = (parts.path or "").lstrip("/")
    host = (parts.hostname or "").lower()
    if dbname != EQUIV_DB:
        raise LiEquivGuardError(
            f"DSN aponta para o database {dbname!r}, nao para {EQUIV_DB!r} — abortado (AC10). "
            "Este script nunca escreve em extra_test nem em producao."
        )
    if host not in LOOPBACK_HOSTS:
        raise LiEquivGuardError(f"DSN aponta para host nao-loopback {host!r} — abortado (AC10).")
    return dsn


def _connect(dsn: str, *, autocommit: bool = True) -> Any:
    import psycopg2
    import psycopg2.extras

    conn = psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)
    conn.autocommit = autocommit
    return conn


def _exec(conn: Any, sql: str, params: Any = None) -> None:
    with conn.cursor() as cur:
        cur.execute(sql, params)


# --- provisionamento --------------------------------------------------------


def _create_database(admin: str) -> None:
    conn = _connect(_with_database(admin, MAINTENANCE_DB))
    try:
        _exec(
            conn,
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()",
            (EQUIV_DB,),
        )
        _exec(conn, f'DROP DATABASE IF EXISTS "{EQUIV_DB}"')
        _exec(conn, f'CREATE DATABASE "{EQUIV_DB}" TEMPLATE template0')
        with conn.cursor() as cur:
            cur.execute("SELECT 1 AS ok FROM pg_roles WHERE rolname = %s", (EQUIV_ROLE,))
            exists = cur.fetchone() is not None
        if not exists:
            _exec(
                conn,
                f"CREATE ROLE {EQUIV_ROLE} NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT "
                f"LOGIN PASSWORD '{EQUIV_PASSWORD}'",
            )
        _exec(conn, f'GRANT CONNECT ON DATABASE "{EQUIV_DB}" TO {EQUIV_ROLE}')
    finally:
        conn.close()


def _apply_migrations(target: str) -> None:
    from scripts.ops.apply_migrations import main as apply_main

    code = apply_main(["--dsn", assert_isolated_target(target)])
    if code not in (0, None):
        raise RuntimeError(f"apply_migrations falhou em {EQUIV_DB} (codigo {code})")


def _apply_seed(target: str) -> None:
    from scripts.ops.apply_migrations import is_executable, split_sql

    if not SEED_FILE.is_file():
        raise FileNotFoundError(f"seed determinístico ausente: {SEED_FILE}")
    conn = _connect(assert_isolated_target(target))
    try:
        with conn.cursor() as cur:
            for statement in split_sql(SEED_FILE.read_text(encoding="utf-8")):
                if is_executable(statement):
                    cur.execute(statement)
    finally:
        conn.close()


def _grant_runner(target: str) -> None:
    """Grants do role dedicado — derivados de ``WRITE_TARGET_ORDER``, nunca de lista propria.

    * DML completo (``SELECT/INSERT/UPDATE/DELETE``) apenas nas tabelas da
      allowlist, mais ``USAGE`` nas sequences que pertencem a elas (podem ser
      zero: as tabelas do motor tem PK ``TEXT``, sem ``serial`` — zero nao e erro).
    * ``SELECT`` e **nada mais** em qualquer outro objeto de ``public``, o que
      inclui todo objeto outbound: qualquer DML outbound falha por permissao, nao
      apenas por asserção de teste.
    """
    conn = _connect(assert_isolated_target(target))
    try:
        _exec(conn, f"GRANT USAGE ON SCHEMA public TO {EQUIV_ROLE}")
        _exec(conn, f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {EQUIV_ROLE}")
        # Leitor as-of do motor: a 104 o revoga de PUBLIC. `EXECUTE` aqui e
        # privilegio de LEITURA (a funcao e um SELECT sobre `pncp_raw_bids`), e o
        # nome vem de `sources.AS_OF_FUNCTION` — sem segundo literal.
        _exec(conn, f"GRANT EXECUTE ON FUNCTION {AS_OF_FUNCTION}(DATE) TO {EQUIV_ROLE}")
        for table in WRITE_TARGET_ORDER:
            _exec(
                conn,
                f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public."{table}" TO {EQUIV_ROLE}',
            )
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT s.relname AS seq
                FROM pg_class s
                JOIN pg_depend d ON d.objid = s.oid AND d.classid = 'pg_class'::regclass
                JOIN pg_class t ON t.oid = d.refobjid
                JOIN pg_namespace n ON n.oid = s.relnamespace
                WHERE s.relkind = 'S' AND n.nspname = 'public' AND t.relname = ANY(%s)
                """,
                (list(WRITE_TARGET_ORDER),),
            )
            sequences = [row["seq"] for row in (cur.fetchall() or [])]
        for sequence in sequences:
            _exec(conn, f'GRANT USAGE, SELECT ON SEQUENCE public."{sequence}" TO {EQUIV_ROLE}')
    finally:
        conn.close()


def up(admin: str | None = None) -> str:
    """Cria, migra ate a 105, semeia e concede. Devolve o DSN do runner."""
    admin = admin or admin_dsn()
    target = _with_database(admin, EQUIV_DB)
    _create_database(admin)
    _apply_migrations(target)
    _apply_seed(target)
    _grant_runner(target)
    return runner_dsn(admin)


def down(admin: str | None = None) -> None:
    """Teardown obrigatorio e idempotente. Nao deixa role nem database residual."""
    admin = admin or admin_dsn()
    target = _with_database(admin, EQUIV_DB)
    maintenance = _connect(_with_database(admin, MAINTENANCE_DB))
    try:
        with maintenance.cursor() as cur:
            cur.execute("SELECT 1 AS ok FROM pg_database WHERE datname = %s", (EQUIV_DB,))
            database_exists = cur.fetchone() is not None
            cur.execute("SELECT 1 AS ok FROM pg_roles WHERE rolname = %s", (EQUIV_ROLE,))
            role_exists = cur.fetchone() is not None

        # `DROP OWNED BY` roda DENTRO do database alvo — e por-database.
        if database_exists and role_exists:
            inner = _connect(assert_isolated_target(target))
            try:
                _exec(inner, f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {EQUIV_ROLE}")
                _exec(inner, f"REVOKE ALL ON SCHEMA public FROM {EQUIV_ROLE}")
                _exec(inner, f"DROP OWNED BY {EQUIV_ROLE}")
            finally:
                inner.close()

        if database_exists:
            _exec(
                maintenance,
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()",
                (EQUIV_DB,),
            )
            _exec(maintenance, f'DROP DATABASE IF EXISTS "{EQUIV_DB}"')
        if role_exists:
            _exec(maintenance, f"DROP ROLE IF EXISTS {EQUIV_ROLE}")
    finally:
        maintenance.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="li-equiv-db", description=__doc__)
    parser.add_argument("command", choices=("up", "down", "dsn", "admin-dsn"))
    parser.add_argument("--admin-dsn", default=None)
    args = parser.parse_args(argv)

    try:
        if args.command == "up":
            print(up(args.admin_dsn))
        elif args.command == "down":
            down(args.admin_dsn)
            print(f"{EQUIV_DB}/{EQUIV_ROLE} removidos")
        elif args.command == "dsn":
            print(runner_dsn(args.admin_dsn))
        else:
            # DSN administrativo NO MESMO banco isolado. Usado pelas suites que
            # precisam de DML de fixture (o `DELETE ... LIKE 'LI-TEST-%'` de
            # `conftest.py`), que o role restrito por desenho NAO pode executar.
            # O role restrito continua sendo o do AC10 — sao papeis distintos.
            print(assert_isolated_target(_with_database(args.admin_dsn or admin_dsn(), EQUIV_DB)))
    except LiEquivGuardError as exc:
        print(f"LI_EQUIV_GUARD: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

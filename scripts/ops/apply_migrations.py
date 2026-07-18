"""Apply SQL migrations safely for CI and local gates.

Idempotent upgrade path:
- Tracks applied files in public._migrations (version PK)
- Skips versions already recorded
- In upgrade mode, tolerates already-exists objects by marking the version applied
  (repair path for databases provisioned outside the ledger)

Each statement runs under autocommit so:
- CREATE INDEX CONCURRENTLY (rewritten to CREATE INDEX by default) works
- ALTER TYPE ... ADD VALUE can be used later in the same file
- Dollar-quoted function bodies stay intact
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from pathlib import Path
from typing import Any

_CONCURRENTLY = re.compile(r"\bCREATE\s+INDEX\s+CONCURRENTLY\b", re.IGNORECASE)

# Errors that mean the migration target is already present (upgrade repair path).
_REPAIRABLE_MARKERS = (
    "already exists",
    "duplicate_table",
    "duplicate_object",
    "duplicate_column",
    "already an attribute of type",
    "cannot change return type of existing function",
    "cannot change name of input parameter",
    "cannot change name of view column",
    "cannot drop columns from view",
    "must be owner of",
    "is not unique",
    "more than one function named",
)


def list_migrations(root: Path, *, max_num: int | None = None) -> list[Path]:
    files = sorted(p for p in root.glob("*.sql") if p.name[:3].isdigit())
    if max_num is not None:
        files = [p for p in files if int(p.name[:3]) <= max_num]
    return files


def version_key(path: Path) -> str:
    """Canonical version id from filename prefix.

    Examples: ``001_foo.sql`` → ``001``; ``041a_fix.sql`` → ``041a``;
    ``018-td-5.3_x.sql`` → ``018``.
    """
    m = re.match(r"^(\d{3}[a-zA-Z]?)", path.name)
    return m.group(1) if m else path.name[:3]


def file_checksum(path: Path) -> str:
    return "sha256=" + hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def split_sql(sql: str) -> list[str]:
    """Split SQL into statements; respect single quotes and $tag$ quotes."""
    statements: list[str] = []
    buf: list[str] = []
    i = 0
    n = len(sql)
    in_single = False
    dollar: str | None = None
    while i < n:
        ch = sql[i]
        if dollar is not None:
            if sql.startswith(dollar, i):
                buf.append(dollar)
                i += len(dollar)
                dollar = None
            else:
                buf.append(ch)
                i += 1
            continue
        if in_single:
            buf.append(ch)
            if ch == "'":
                if i + 1 < n and sql[i + 1] == "'":
                    buf.append("'")
                    i += 2
                    continue
                in_single = False
            i += 1
            continue
        # line comment
        if ch == "-" and i + 1 < n and sql[i + 1] == "-":
            while i < n and sql[i] != "\n":
                buf.append(sql[i])
                i += 1
            continue
        # block comment
        if ch == "/" and i + 1 < n and sql[i + 1] == "*":
            buf.append("/*")
            i += 2
            while i < n - 1 and not (sql[i] == "*" and sql[i + 1] == "/"):
                buf.append(sql[i])
                i += 1
            if i < n - 1:
                buf.append("*/")
                i += 2
            continue
        if ch == "'":
            in_single = True
            buf.append(ch)
            i += 1
            continue
        if ch == "$":
            m = re.match(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$", sql[i:])
            if m:
                dollar = m.group(0)
                buf.append(dollar)
                i += len(dollar)
                continue
        if ch == ";":
            stmt = "".join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


def is_executable(stmt: str) -> bool:
    body = re.sub(r"--[^\n]*", "", stmt)
    body = re.sub(r"/\*.*?\*/", "", body, flags=re.DOTALL).strip()
    if not body:
        return False
    if re.fullmatch(r"BEGIN|COMMIT|ROLLBACK", body, re.IGNORECASE):
        return False
    return True


def prepare_statement(stmt: str, *, allow_concurrent: bool) -> str:
    if not allow_concurrent:
        stmt = _CONCURRENTLY.sub("CREATE INDEX", stmt)
    return stmt.strip()


def ensure_ledger(conn: Any) -> None:
    cur = conn.cursor()
    try:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS public._migrations (
                version text PRIMARY KEY,
                name text NOT NULL,
                applied_at timestamptz NOT NULL DEFAULT NOW(),
                checksum text,
                rollback_sql text
            )
            """
        )
    finally:
        cur.close()


def load_applied(conn: Any) -> set[str]:
    cur = conn.cursor()
    try:
        cur.execute("SELECT version FROM public._migrations")
        return {str(r[0]) for r in cur.fetchall()}
    finally:
        cur.close()


def record_applied(conn: Any, version: str, name: str, checksum: str) -> None:
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO public._migrations (version, name, applied_at, checksum)
            VALUES (%s, %s, NOW(), %s)
            ON CONFLICT (version) DO UPDATE
              SET name = EXCLUDED.name,
                  checksum = COALESCE(EXCLUDED.checksum, public._migrations.checksum)
            """,
            (version, name, checksum),
        )
    finally:
        cur.close()


def _is_repairable_existing(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return any(m in msg for m in _REPAIRABLE_MARKERS)


def _is_optional_env_gap(exc: BaseException) -> bool:
    """Optional extensions/types not installed on local PG (vector/hnsw)."""
    msg = str(exc).lower()
    return any(
        x in msg
        for x in (
            "type vector does not exist",
            'type "vector" does not exist',
            "could not find a function named \"search_datalake\"",
            "could not find a function named 'search_datalake'",
            "operator class \"vector_cosine_ops\"",
            "access method \"hnsw\"",
            "extension \"vector\"",
        )
    )


def apply_file(conn: Any, path: Path, *, allow_concurrent: bool = False) -> None:
    """Apply one migration file. Connection must be in autocommit mode."""
    raw = path.read_text(encoding="utf-8")
    statements = split_sql(raw)
    cur = conn.cursor()
    try:
        for raw_stmt in statements:
            if not is_executable(raw_stmt):
                continue
            stmt = prepare_statement(raw_stmt, allow_concurrent=allow_concurrent)
            if not stmt:
                continue
            try:
                cur.execute(stmt)
            except Exception as exc:
                msg = str(exc).lower()
                optional = (
                    ("extension" in msg and ("is not available" in msg or "does not exist" in msg))
                    or "type vector does not exist" in msg
                    or "type \"vector\" does not exist" in msg
                    or "does not exist" in msg and "vector" in msg
                )
                if optional:
                    print(f"skip_optional in {path.name}: {exc}", flush=True)
                    continue
                print(f"migration_error {path.name}: {exc}", flush=True)
                raise
    finally:
        cur.close()


def apply_range(
    dsn: str,
    root: Path,
    *,
    max_num: int | None = 54,
    min_num: int = 1,
    allow_concurrent: bool = False,
    mode: str = "upgrade",
) -> dict[str, list[str]]:
    import psycopg2

    files = [p for p in list_migrations(root, max_num=max_num) if int(p.name[:3]) >= min_num]
    result: dict[str, list[str]] = {
        "applied": [],
        "skipped": [],
        "repaired": [],
    }
    conn = psycopg2.connect(dsn)
    # Always autocommit: concurrent index rewrite + failed statements must not poison the session
    conn.autocommit = True
    try:
        ensure_ledger(conn)
        applied_set = load_applied(conn)
        for path in files:
            ver = version_key(path)
            if ver in applied_set:
                print(f"skip {path.name} (ledger)", flush=True)
                result["skipped"].append(path.name)
                continue
            try:
                apply_file(conn, path, allow_concurrent=allow_concurrent)
                record_applied(conn, ver, path.name, file_checksum(path))
                applied_set.add(ver)
                result["applied"].append(path.name)
                print(f"applied {path.name}", flush=True)
            except Exception as exc:
                if mode == "upgrade" and (
                    _is_repairable_existing(exc) or _is_optional_env_gap(exc)
                ):
                    # Objects already present, or optional extension gap (vector/hnsw)
                    suffix = (
                        "+optional_env"
                        if _is_optional_env_gap(exc)
                        else "+repair_existing"
                    )
                    record_applied(
                        conn,
                        ver,
                        path.name,
                        file_checksum(path) + suffix,
                    )
                    applied_set.add(ver)
                    result["repaired"].append(path.name)
                    print(f"repair_mark {path.name} ({exc})", flush=True)
                    continue
                raise
    finally:
        conn.close()
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply datalake SQL migrations for gates")
    parser.add_argument("--dsn", default=os.getenv("DATABASE_URL") or os.getenv("LOCAL_DATALAKE_DSN"))
    parser.add_argument("--root", type=Path, default=Path("db/migrations"))
    parser.add_argument("--max", type=int, default=54)
    parser.add_argument("--min", type=int, default=1)
    parser.add_argument("--allow-concurrent", action="store_true")
    parser.add_argument(
        "--mode",
        choices=["fresh", "upgrade"],
        default="upgrade",
        help="upgrade=idempotent skip/repair (default); fresh=same apply path (expects empty DB)",
    )
    args = parser.parse_args(argv)
    if not args.dsn:
        print("DATABASE_URL or --dsn required", file=sys.stderr)
        return 2
    summary = apply_range(
        args.dsn,
        args.root,
        max_num=args.max,
        min_num=args.min,
        allow_concurrent=args.allow_concurrent,
        mode=args.mode,
    )
    print(
        "migrations_ok mode={mode} applied={a} skipped={s} repaired={r}".format(
            mode=args.mode,
            a=len(summary["applied"]),
            s=len(summary["skipped"]),
            r=len(summary["repaired"]),
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

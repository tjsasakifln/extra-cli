"""Apply SQL migrations safely for CI and local gates.

Each statement runs under autocommit so:
- CREATE INDEX CONCURRENTLY (rewritten to CREATE INDEX by default) works
- ALTER TYPE ... ADD VALUE can be used later in the same file
- Dollar-quoted function bodies stay intact
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any

_CONCURRENTLY = re.compile(r"\bCREATE\s+INDEX\s+CONCURRENTLY\b", re.IGNORECASE)


def list_migrations(root: Path, *, max_num: int | None = None) -> list[Path]:
    files = sorted(p for p in root.glob("*.sql") if p.name[:3].isdigit())
    if max_num is not None:
        files = [p for p in files if int(p.name[:3]) <= max_num]
    return files


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


def apply_file(conn: Any, path: Path, *, allow_concurrent: bool = False) -> None:
    raw = path.read_text(encoding="utf-8")
    statements = split_sql(raw)
    prev = conn.autocommit
    conn.autocommit = True
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
                if "extension" in msg and ("is not available" in msg or "does not exist" in msg):
                    print(f"skip_optional_extension in {path.name}: {exc}", flush=True)
                    continue
                print(f"migration_error {path.name}: {exc}", flush=True)
                raise
    finally:
        cur.close()
        conn.autocommit = prev


def apply_range(
    dsn: str,
    root: Path,
    *,
    max_num: int | None = 54,
    min_num: int = 1,
    allow_concurrent: bool = False,
) -> list[str]:
    import psycopg2

    files = [p for p in list_migrations(root, max_num=max_num) if int(p.name[:3]) >= min_num]
    applied: list[str] = []
    conn = psycopg2.connect(dsn)
    try:
        for path in files:
            apply_file(conn, path, allow_concurrent=allow_concurrent)
            applied.append(path.name)
            print(f"applied {path.name}", flush=True)
    finally:
        conn.close()
    return applied


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply datalake SQL migrations for gates")
    parser.add_argument("--dsn", default=os.getenv("DATABASE_URL") or os.getenv("LOCAL_DATALAKE_DSN"))
    parser.add_argument("--root", type=Path, default=Path("db/migrations"))
    parser.add_argument("--max", type=int, default=54)
    parser.add_argument("--min", type=int, default=1)
    parser.add_argument("--allow-concurrent", action="store_true")
    parser.add_argument("--mode", choices=["fresh", "upgrade"], default="fresh")
    args = parser.parse_args(argv)
    if not args.dsn:
        print("DATABASE_URL or --dsn required", file=sys.stderr)
        return 2
    applied = apply_range(
        args.dsn,
        args.root,
        max_num=args.max,
        min_num=args.min,
        allow_concurrent=args.allow_concurrent,
    )
    print(f"migrations_ok mode={args.mode} count={len(applied)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

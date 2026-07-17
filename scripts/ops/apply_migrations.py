"""Apply SQL migrations safely for CI and local gates.

Handles CREATE INDEX CONCURRENTLY (cannot run inside a transaction block) by
executing those statements alone under autocommit. Supports fresh-install and
upgrade-from-snapshot paths used by the resilience gate.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any

_CONCURRENTLY = re.compile(r"\bCREATE\s+INDEX\s+CONCURRENTLY\b", re.IGNORECASE)
_BEGIN = re.compile(r"^\s*BEGIN\s*;\s*$", re.IGNORECASE | re.MULTILINE)
_COMMIT = re.compile(r"^\s*COMMIT\s*;\s*$", re.IGNORECASE | re.MULTILINE)


def list_migrations(root: Path, *, max_num: int | None = None) -> list[Path]:
    files = sorted(p for p in root.glob("*.sql") if p.name[:3].isdigit())
    if max_num is not None:
        files = [p for p in files if int(p.name[:3]) <= max_num]
    return files


def split_statements(sql: str) -> list[str]:
    """Naive statement splitter that respects simple dollar-quotes and strings."""
    statements: list[str] = []
    buf: list[str] = []
    i = 0
    in_single = False
    dollar_tag: str | None = None
    while i < len(sql):
        ch = sql[i]
        if dollar_tag:
            if sql.startswith(dollar_tag, i):
                buf.append(dollar_tag)
                i += len(dollar_tag)
                dollar_tag = None
                continue
            buf.append(ch)
            i += 1
            continue
        if in_single:
            buf.append(ch)
            if ch == "'" and not (i + 1 < len(sql) and sql[i + 1] == "'"):
                in_single = False
            elif ch == "'" and i + 1 < len(sql) and sql[i + 1] == "'":
                buf.append("'")
                i += 2
                continue
            i += 1
            continue
        if ch == "'":
            in_single = True
            buf.append(ch)
            i += 1
            continue
        if ch == "$":
            m = re.match(r"\$[A-Za-z0-9_]*\$", sql[i:])
            if m:
                dollar_tag = m.group(0)
                buf.append(dollar_tag)
                i += len(dollar_tag)
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


def normalize_statement(stmt: str, *, allow_concurrent: bool) -> str | None:
    s = stmt.strip()
    if not s:
        return None
    # Drop comment-only / empty payloads (psycopg2 rejects empty execute).
    without_comments = re.sub(r"--[^\n]*", "", s)
    without_comments = re.sub(r"/\*.*?\*/", "", without_comments, flags=re.DOTALL).strip()
    if not without_comments:
        return None
    if re.fullmatch(r"BEGIN", without_comments, re.IGNORECASE) or re.fullmatch(
        r"COMMIT", without_comments, re.IGNORECASE
    ):
        return None  # runner owns transactions
    if not allow_concurrent and _CONCURRENTLY.search(s):
        s = _CONCURRENTLY.sub("CREATE INDEX", s)
    s = s.strip()
    return s or None


def apply_file(conn: Any, path: Path, *, allow_concurrent: bool = False) -> None:
    sql = path.read_text(encoding="utf-8")
    # Strip outer transaction wrappers; runner decides.
    sql = _BEGIN.sub("", sql)
    sql = _COMMIT.sub("", sql)
    statements = split_statements(sql)
    cur = conn.cursor()
    try:
        for raw in statements:
            stmt = normalize_statement(raw, allow_concurrent=allow_concurrent)
            if not stmt:
                continue
            if not stmt.strip():
                continue
            needs_autocommit = bool(_CONCURRENTLY.search(stmt))
            if needs_autocommit:
                # Must not be inside an open transaction.
                prev = conn.autocommit
                conn.autocommit = True
                try:
                    cur.execute(stmt)
                finally:
                    conn.autocommit = prev
            else:
                cur.execute(stmt)
        if not conn.autocommit:
            conn.commit()
    except Exception:
        if not conn.autocommit:
            conn.rollback()
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
) -> list[str]:
    import psycopg2

    files = [p for p in list_migrations(root, max_num=max_num) if int(p.name[:3]) >= min_num]
    applied: list[str] = []
    conn = psycopg2.connect(dsn)
    conn.autocommit = False
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
    parser.add_argument(
        "--allow-concurrent",
        action="store_true",
        help="Keep CREATE INDEX CONCURRENTLY (default: rewrite to CREATE INDEX for CI empty DBs)",
    )
    parser.add_argument(
        "--mode",
        choices=["fresh", "upgrade"],
        default="fresh",
        help="fresh=from empty; upgrade=from --min (after a prior snapshot)",
    )
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

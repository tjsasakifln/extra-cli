"""Apply SQL migrations safely for CI and local gates.

Handles CREATE INDEX CONCURRENTLY (cannot run inside a transaction block) by
rewriting to CREATE INDEX on empty CI databases. Executes each file as a whole
script under autocommit to preserve dollar-quoted function bodies.
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


def prepare_sql(sql: str, *, allow_concurrent: bool) -> str:
    # Runner owns transaction boundaries.
    sql = _BEGIN.sub("", sql)
    sql = _COMMIT.sub("", sql)
    if not allow_concurrent:
        sql = _CONCURRENTLY.sub("CREATE INDEX", sql)
    return sql.strip()


def apply_file(conn: Any, path: Path, *, allow_concurrent: bool = False) -> None:
    raw = path.read_text(encoding="utf-8")
    sql = prepare_sql(raw, allow_concurrent=allow_concurrent)
    if not sql:
        print(f"skip_empty {path.name}", flush=True)
        return
    # Whole-file execute preserves dollar-quoted PL/pgSQL bodies.
    prev = conn.autocommit
    conn.autocommit = True
    cur = conn.cursor()
    try:
        try:
            cur.execute(sql)
        except Exception as exc:
            msg = str(exc).lower()
            if "extension" in msg and ("is not available" in msg or "does not exist" in msg):
                print(f"skip_optional_extension in {path.name}: {exc}", flush=True)
                return
            # If multi-statement failed mid-way on optional vector types, re-raise.
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

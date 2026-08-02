#!/usr/bin/env python3
"""Local PostgreSQL backup + restore proof (DoD §14).

Creates a pg_dump of the source DSN into backups/local-proof/, then restores
into a *separate* database name and validates table counts / provenance tables
when present.

Environment:
  LOCAL_DATALAKE_DSN or DATABASE_URL — source database (required)
  BACKUP_PROOF_DIR — default backups/local-proof

Exit 0 on success; non-zero on failure.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse, urlunparse

REPO = Path(__file__).resolve().parents[2]


def _parse_dsn(dsn: str) -> dict[str, str]:
    # postgresql://user:pass@host:port/db
    u = urlparse(dsn)
    return {
        "scheme": u.scheme or "postgresql",
        "user": u.username or "postgres",
        "password": u.password or "",
        "host": u.hostname or "127.0.0.1",
        "port": str(u.port or 5432),
        "dbname": (u.path or "/postgres").lstrip("/") or "postgres",
    }


def _dsn_with_db(parts: dict[str, str], dbname: str) -> str:
    auth = parts["user"]
    if parts["password"]:
        auth = f"{parts['user']}:{parts['password']}"
    netloc = f"{auth}@{parts['host']}:{parts['port']}"
    return urlunparse((parts["scheme"], netloc, f"/{dbname}", "", "", ""))


def _env_for_pg(parts: dict[str, str]) -> dict[str, str]:
    env = os.environ.copy()
    env["PGPASSWORD"] = parts["password"]
    return env


def _run(cmd: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 — caller builds fixed argv (psql/pg_dump), shell=False
        cmd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def table_count(parts: dict[str, str], dbname: str) -> int:
    env = _env_for_pg(parts)
    sql = "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';"
    r = _run(
        [
            "psql",
            "-h",
            parts["host"],
            "-p",
            parts["port"],
            "-U",
            parts["user"],
            "-d",
            dbname,
            "-tAc",
            sql,
        ],
        env,
    )
    if r.returncode != 0:
        raise RuntimeError(f"psql count failed: {r.stderr}")
    return int((r.stdout or "0").strip() or "0")


def _psql_scalar(parts: dict[str, str], dbname: str, sql: str) -> str:
    env = _env_for_pg(parts)
    r = _run(
        [
            "psql",
            "-h",
            parts["host"],
            "-p",
            parts["port"],
            "-U",
            parts["user"],
            "-d",
            dbname,
            "-tAc",
            sql,
        ],
        env,
    )
    if r.returncode != 0:
        raise RuntimeError(f"psql failed: {r.stderr}")
    return (r.stdout or "").strip()


def integrity_snapshot(parts: dict[str, str], dbname: str) -> dict[str, object]:
    """Row counts + md5 fingerprints for key operational tables when present.

    Gate G requires more than table inventory equality — compare processes,
    documents, versions and queue-like state where schema has them.
    """
    env_tables = _psql_scalar(
        parts,
        dbname,
        "SELECT string_agg(table_name, ',' ORDER BY table_name) "
        "FROM information_schema.tables WHERE table_schema='public'",
    )
    present = set((env_tables or "").split(",")) if env_tables else set()
    # Prefer domain tables; fall back to any public tables with rows
    candidates = [
        "process_documents",
        "document_versions",
        "documents",
        "processes",
        "entity_source_state",
        "entity_source_queue",
        "source_runs",
        "document_inventory",
        "pncp_supplier_contracts",
        "opportunities",
        "jobs",
        "command_center_jobs",
    ]
    row_counts: dict[str, int] = {}
    fingerprints: dict[str, str] = {}
    # Only allowlisted identifiers — never interpolate operator input.
    safe_tables = {c for c in candidates if c.replace("_", "").isalnum()}
    for t in candidates:
        if t not in present or t not in safe_tables:
            continue
        try:
            n = int(
                _psql_scalar(
                    parts,
                    dbname,
                    'SELECT count(*) FROM "' + t + '"',  # noqa: S608 — t allowlisted identifier
                )
                or "0"
            )
        except RuntimeError:
            continue
        row_counts[t] = n
        # Content fingerprint (not ctid — ctid changes across restore).
        try:
            if n == 0:
                fingerprints[t] = "empty"
            else:
                # t is allowlisted alphanumeric identifier only (safe_tables)
                sql = "SELECT md5(string_agg(row_hash, ',' ORDER BY row_hash)) FROM (SELECT md5(t::text) AS row_hash FROM \"" + t + "\" AS t ORDER BY md5(t::text) LIMIT 5000) s"  # noqa: S608
                fp = _psql_scalar(parts, dbname, sql)
                fingerprints[t] = fp or "empty"
        except RuntimeError:
            fingerprints[t] = "unavailable"
    return {
        "public_tables": len(present),
        "row_counts": row_counts,
        "fingerprints": fingerprints,
        "compared_tables": sorted(row_counts.keys()),
    }


def ensure_db(parts: dict[str, str], dbname: str) -> None:
    env = _env_for_pg(parts)
    # connect to postgres maintenance db
    maint = "postgres" if parts["dbname"] != "postgres" else parts["dbname"]
    check = _run(
        [
            "psql",
            "-h",
            parts["host"],
            "-p",
            parts["port"],
            "-U",
            parts["user"],
            "-d",
            maint,
            "-tAc",
            f"SELECT 1 FROM pg_database WHERE datname='{dbname}'",  # noqa: S608 — local dbname identifier only
        ],
        env,
    )
    if check.returncode != 0:
        raise RuntimeError(check.stderr)
    if (check.stdout or "").strip() == "1":
        drop = _run(
            [
                "psql",
                "-h",
                parts["host"],
                "-p",
                parts["port"],
                "-U",
                parts["user"],
                "-d",
                maint,
                "-c",
                f"DROP DATABASE {dbname};",
            ],
            env,
        )
        if drop.returncode != 0:
            raise RuntimeError(drop.stderr)
    create = _run(
        [
            "psql",
            "-h",
            parts["host"],
            "-p",
            parts["port"],
            "-U",
            parts["user"],
            "-d",
            maint,
            "-c",
            f"CREATE DATABASE {dbname};",
        ],
        env,
    )
    if create.returncode != 0:
        raise RuntimeError(create.stderr)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--dsn",
        default=os.environ.get("LOCAL_DATALAKE_DSN") or os.environ.get("DATABASE_URL"),
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=REPO / "backups" / "local-proof",
    )
    p.add_argument("--restore-db", default="extra_restore_proof")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    if not args.dsn:
        print("LOCAL_DATALAKE_DSN/DATABASE_URL required", file=sys.stderr)
        return 2
    if shutil.which("pg_dump") is None or shutil.which("psql") is None:
        print("pg_dump and psql required", file=sys.stderr)
        return 2

    parts = _parse_dsn(args.dsn)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    dump_path = args.out_dir / f"proof-{parts['dbname']}-{stamp}.dump"

    env = _env_for_pg(parts)
    dump = _run(
        [
            "pg_dump",
            "-h",
            parts["host"],
            "-p",
            parts["port"],
            "-U",
            parts["user"],
            "-d",
            parts["dbname"],
            "-Fc",
            "-f",
            str(dump_path),
        ],
        env,
    )
    if dump.returncode != 0:
        print(dump.stderr, file=sys.stderr)
        return 1

    src_tables = table_count(parts, parts["dbname"])
    src_integrity = integrity_snapshot(parts, parts["dbname"])
    ensure_db(parts, args.restore_db)
    restore = _run(
        [
            "pg_restore",
            "-h",
            parts["host"],
            "-p",
            parts["port"],
            "-U",
            parts["user"],
            "-d",
            args.restore_db,
            "--no-owner",
            "--no-acl",
            str(dump_path),
        ],
        env,
    )
    # pg_restore may return 1 with warnings; treat only hard fail
    dst_tables = table_count(parts, args.restore_db)
    dst_integrity = integrity_snapshot(parts, args.restore_db)
    row_counts_match = src_integrity.get("row_counts") == dst_integrity.get("row_counts")
    fingerprints_match = src_integrity.get("fingerprints") == dst_integrity.get("fingerprints")
    compared = list(src_integrity.get("compared_tables") or [])
    report = {
        "ok": dump_path.is_file() and dst_tables >= 0 and src_tables >= 0,
        "generated_at": datetime.now(UTC).isoformat(),
        "source_db": parts["dbname"],
        "restore_db": args.restore_db,
        "dump_path": str(dump_path.relative_to(REPO)) if dump_path.is_relative_to(REPO) else str(dump_path),
        "dump_bytes": dump_path.stat().st_size if dump_path.is_file() else 0,
        "source_public_tables": src_tables,
        "restore_public_tables": dst_tables,
        "pg_restore_exit": restore.returncode,
        "pg_restore_stderr_tail": (restore.stderr or "")[-500:],
        "integrity": {
            "source": src_integrity,
            "restore": dst_integrity,
            "row_counts_match": row_counts_match,
            "fingerprints_match": fingerprints_match,
            "compared_tables": compared,
        },
        "claims": {
            "backup_exists": dump_path.is_file() and dump_path.stat().st_size > 0,
            "restore_separate_db": args.restore_db != parts["dbname"],
            "tables_restored": dst_tables > 0 or src_tables == 0,
            "table_inventory_equal": src_tables == dst_tables,
            "domain_row_counts_equal": row_counts_match,
            "domain_fingerprints_equal": fingerprints_match,
        },
        "limitations": [
            "Storage Box / external backup path not exercised in this local proof.",
            "Universe seed re-import is a separate step after restore (see universe_reimport_cmd).",
            "Fingerprints use ctid samples (≤5000 rows/table) for speed; full-table digests optional.",
        ],
        "recovery_instruction": (
            "pg_restore -d <target_db> backups/local-proof/<dump>; "
            "or bash scripts/restore-database.sh when available."
        ),
        "universe_reimport_cmd": (
            "python3 -c \"from scripts.lib.universe import load_canonical_universe; "
            "u=load_canonical_universe(); print(u.summary())\""
        ),
    }
    # Require integrity when domain tables exist; otherwise inventory equality
    integrity_ok = True
    if compared:
        integrity_ok = bool(row_counts_match and fingerprints_match)
    report["ok"] = (
        report["claims"]["backup_exists"]
        and report["claims"]["restore_separate_db"]
        and (report["claims"]["tables_restored"] or src_tables == 0)
        and report["claims"]["table_inventory_equal"]
        and integrity_ok
    )
    out_json = args.out_dir / f"proof-report-{stamp}.json"
    out_json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(
            f"local_backup_restore_proof: ok={report['ok']} "
            f"src_tables={src_tables} dst_tables={dst_tables} "
            f"integrity_tables={len(compared)} "
            f"row_counts_match={row_counts_match} "
            f"fingerprints_match={fingerprints_match} "
            f"dump={dump_path.name}"
        )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())

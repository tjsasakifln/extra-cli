"""Prove golden path on a freshly created empty database (DoD §12.1 clean env)."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

REPO = Path(__file__).resolve().parents[2]
_PSQL = "psql"  # resolved from PATH in local/CI (not shell-expanded)


def _parts(dsn: str) -> dict[str, str]:
    u = urlparse(dsn)
    return {
        "scheme": u.scheme or "postgresql",
        "user": u.username or "test",
        "password": u.password or "test",
        "host": u.hostname or "127.0.0.1",
        "port": str(u.port or 5432),
        "dbname": (u.path or "/postgres").lstrip("/") or "postgres",
    }


def _dsn(parts: dict[str, str], dbname: str) -> str:
    auth = parts["user"]
    if parts["password"]:
        auth = f"{parts['user']}:{parts['password']}"
    return urlunparse(
        (parts["scheme"], f"{auth}@{parts['host']}:{parts['port']}", f"/{dbname}", "", "", "")
    )


def _psql_env(parts: dict[str, str]) -> dict[str, str]:
    env = os.environ.copy()
    env["PGPASSWORD"] = parts["password"]
    return env


def _psql(parts: dict[str, str], dbname: str, sql: str) -> subprocess.CompletedProcess[str]:
    # psql binary comes from PATH in local/CI; argv is fully controlled (shell=False).
    argv = [
        _PSQL,
        "-h",
        parts["host"],
        "-p",
        parts["port"],
        "-U",
        parts["user"],
        "-d",
        dbname,
        "-v",
        "ON_ERROR_STOP=1",
        "-c",
        sql,
    ]
    return subprocess.run(  # noqa: S603 — fixed argv, shell=False
        argv,
        env=_psql_env(parts),
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )


def recreate_db(admin_dsn: str, clean_name: str) -> dict[str, Any]:
    parts = _parts(admin_dsn)
    # terminate + drop + create as separate autocommit statements
    # clean_name / user come from controlled local tooling args, not external SQL input.
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", clean_name):
        raise ValueError(f"invalid clean db name: {clean_name!r}")
    user = parts["user"]
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", user):
        raise ValueError(f"invalid db user: {user!r}")
    # Identifiers validated via re.fullmatch above (safe literal interpolation for local tooling).
    term_sql = f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '{clean_name}' AND pid <> pg_backend_pid();"  # noqa: S608
    drop_sql = f"DROP DATABASE IF EXISTS {clean_name};"  # noqa: S608
    create_sql = f"CREATE DATABASE {clean_name} OWNER {user};"  # noqa: S608
    term = _psql(parts, "postgres", term_sql)
    drop = _psql(parts, "postgres", drop_sql)
    create = _psql(parts, "postgres", create_sql)
    return {
        "term_exit": term.returncode,
        "drop_exit": drop.returncode,
        "drop_err": (drop.stderr or "")[-200:],
        "create_exit": create.returncode,
        "create_err": (create.stderr or "")[-200:],
        "ok": create.returncode == 0,
        "dsn": _dsn(parts, clean_name),
    }


def apply_migrations(dsn: str) -> dict[str, Any]:
    """Apply all migrations via canonical apply_migrations (upgrade mode)."""
    r1 = subprocess.run(  # noqa: S603
        [
            sys.executable,
            "-m",
            "scripts.ops.apply_migrations",
            f"--dsn={dsn}",
        ],
        cwd=str(REPO),
        text=True,
        capture_output=True,
        check=False,
        timeout=600,
    )
    return {
        "batch1_exit": r1.returncode,
        "batch1_stdout": (r1.stdout or "")[-800:],
        "batch1_stderr": (r1.stderr or "")[-400:],
        "extras": {},
        "ok": r1.returncode == 0,
    }




def table_count(dsn: str) -> int:
    import psycopg2

    conn = psycopg2.connect(dsn, connect_timeout=5)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"
            )
            return int(cur.fetchone()[0])
    finally:
        conn.close()


def run_golden(dsn: str, ledger: Path) -> dict[str, Any]:
    env = os.environ.copy()
    env["LOCAL_DATALAKE_DSN"] = dsn
    env["DATABASE_URL"] = dsn
    # Clean env foundation: migrations+seeds already applied; validate spreadsheet,
    # skip freshness (no live data yet); allow-zero for empty sources.
    r = subprocess.run(  # noqa: S603 — fixed module invocation via sys.executable, shell=False
        [
            sys.executable,
            "-m",
            "scripts.golden_path",
            "--sources",
            "pncp",
            "--skip-migrations",
            "--skip-seeds",
            "--skip-sources",
            "--skip-freshness",
            "--allow-zero",
            f"--ledger-output={ledger}",
            "--dsn",
            dsn,
        ],
        cwd=str(REPO),
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=600,
    )
    return {
        "exit": r.returncode,
        "stdout": (r.stdout or "")[-1500:],
        "stderr": (r.stderr or "")[-400:],
        "ok": r.returncode == 0,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Golden path clean-environment proof")
    p.add_argument(
        "--admin-dsn",
        default=os.getenv("LOCAL_DATALAKE_DSN") or None,
        help="Admin DSN with CREATE/DROP privilege (required; LOCAL_DATALAKE_DSN). No weak password default.",
    )
    p.add_argument("--db-name", default="extra_clean")
    p.add_argument(
        "--report",
        default=str(REPO / "output" / "golden-path" / "clean-env-report.json"),
    )
    p.add_argument(
        "--confirm-drop",
        action="store_true",
        help="Required to DROP/CREATE the clean database (destructive).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print plan only; do not drop/create DB or run migrations.",
    )
    args = p.parse_args(argv)
    if not args.admin_dsn and not args.dry_run:
        print("ERROR: --admin-dsn or LOCAL_DATALAKE_DSN is required", file=sys.stderr)
        return 2
    if not args.admin_dsn:
        args.admin_dsn = "postgresql://test:test@127.0.0.1:5433/extra_test"  # dry-run plan only

    report: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "steps": {},
        "dry_run": bool(args.dry_run),
    }
    if args.dry_run:
        report["plan"] = {
            "would_drop_create": args.db_name,
            "admin_dsn_host": _parts(args.admin_dsn).get("host"),
            "next": "Re-run with --confirm-drop to execute",
        }
        report["ok"] = True
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2, default=str)[:2000])
        return 0
    if not args.confirm_drop:
        print(
            "REFUSING destructive DROP/CREATE without --confirm-drop "
            f"(db={args.db_name}). Use --dry-run to preview.",
            file=sys.stderr,
        )
        return 3

    rec = recreate_db(args.admin_dsn, args.db_name)
    report["steps"]["recreate_db"] = rec
    if not rec["ok"]:
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, indent=2))
        return 2

    dsn = rec["dsn"]
    mig = apply_migrations(dsn)
    report["steps"]["migrations"] = mig
    # seeds (public fixture via resolve_default_seed_path)
    seed_r = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "scripts.golden_path", "--skip-freshness", "--allow-zero",
         "--skip-migrations", "--execute-coverage-only", "--dsn", dsn],
        cwd=str(REPO), env={**os.environ, "LOCAL_DATALAKE_DSN": dsn},
        text=True, capture_output=True, check=False, timeout=180,
    )
    # Prefer direct seed scripts for entities
    seed1 = subprocess.run(  # noqa: S603
        [sys.executable, str(REPO / "db" / "seed" / "001_sc_entities.py"), "--dsn", dsn],
        cwd=str(REPO), env={**os.environ, "LOCAL_DATALAKE_DSN": dsn},
        text=True, capture_output=True, check=False, timeout=180,
    )
    seed2 = subprocess.run(  # noqa: S603
        [sys.executable, str(REPO / "db" / "seed" / "002_entity_aliases.py"), "--dsn", dsn],
        cwd=str(REPO), env={**os.environ, "LOCAL_DATALAKE_DSN": dsn},
        text=True, capture_output=True, check=False, timeout=120,
    )
    report["steps"]["seeds"] = {
        "entities_exit": seed1.returncode,
        "aliases_exit": seed2.returncode,
        "ok": seed1.returncode == 0,
        "entities_tail": (seed1.stdout or seed1.stderr or "")[-400:],
    }
    try:
        n = table_count(dsn)
    except Exception as exc:  # noqa: BLE001
        n = -1
        report["steps"]["table_count_error"] = str(exc)
    report["steps"]["public_tables"] = n

    ledger = REPO / "output" / "golden-path" / f"ledger-clean-{args.db_name}.json"
    gp = run_golden(dsn, ledger)
    report["steps"]["golden_path"] = gp
    report["steps"]["ledger_path"] = str(ledger)
    parts = _parts(dsn)
    report["clean_dsn_hint"] = f"{parts['host']}:{parts['port']}/{args.db_name}"
    report["ok"] = bool(rec["ok"] and mig.get("ok") and report["steps"].get("seeds",{}).get("ok") and n >= 5 and gp["ok"])
    report["limitations"] = [
        "vector extension optional (014 skipped if unavailable)",
        "clean env proof: empty DB → migrations → golden_path (--skip-freshness --allow-zero); sources may be zero on empty net",
        "Live crawl can be re-run after clean bootstrap with data sources",
    ]
    report["claims"] = {
        "allowed": [
            "Golden path executed on freshly created empty database",
            "Schema created from empty DB then golden path bootstrap",
        ],
        "forbidden": ["LOCAL_READY", "95% coverage from clean env alone"],
    }

    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: report[k] for k in ("ok", "clean_dsn_hint", "steps")}, indent=2, default=str)[:3500])
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

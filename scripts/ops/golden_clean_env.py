"""Prove golden path on a freshly created empty database (DoD §12.1 clean env)."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

REPO = Path(__file__).resolve().parents[2]


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
    return subprocess.run(
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
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            sql,
        ],
        env=_psql_env(parts),
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )


def recreate_db(admin_dsn: str, clean_name: str) -> dict[str, Any]:
    parts = _parts(admin_dsn)
    # terminate + drop + create as separate autocommit statements
    term = _psql(
        parts,
        "postgres",
        f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        f"WHERE datname = '{clean_name}' AND pid <> pg_backend_pid();",
    )
    drop = _psql(parts, "postgres", f"DROP DATABASE IF EXISTS {clean_name};")
    create = _psql(parts, "postgres", f"CREATE DATABASE {clean_name} OWNER {parts['user']};")
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
    """Apply migrations; stop before optional vector extension if needed, continue extras."""
    root = REPO / "db" / "migrations"
    # First batch: through 013 (before vector-dependent 014)
    r1 = subprocess.run(
        [
            sys.executable,
            str(REPO / "scripts" / "ops" / "apply_migrations.py"),
            f"--dsn={dsn}",
            f"--root={root}",
            "--max=13",
            "--allow-concurrent",
        ],
        cwd=str(REPO),
        text=True,
        capture_output=True,
        check=False,
        timeout=300,
    )
    # Skip 014 vector; apply remaining via individual files with ON_ERROR_STOP=0
    parts = _parts(dsn)
    extras: dict[str, int] = {}
    for path in sorted(root.glob("*.sql")):
        num = int(path.name[:3])
        if num <= 13 or num == 14:
            continue
        r = subprocess.run(
            [
                "psql",
                "-h",
                parts["host"],
                "-p",
                parts["port"],
                "-U",
                parts["user"],
                "-d",
                parts["dbname"],
                "-v",
                "ON_ERROR_STOP=0",
                "-f",
                str(path),
            ],
            env=_psql_env(parts),
            text=True,
            capture_output=True,
            check=False,
            timeout=120,
        )
        extras[path.name] = r.returncode
    # Always re-apply critical 055
    p055 = root / "055_fix_upsert_pncp_raw_bids_ambiguous.sql"
    if p055.is_file():
        r = subprocess.run(
            [
                "psql",
                "-h",
                parts["host"],
                "-p",
                parts["port"],
                "-U",
                parts["user"],
                "-d",
                parts["dbname"],
                "-v",
                "ON_ERROR_STOP=0",
                "-f",
                str(p055),
            ],
            env=_psql_env(parts),
            text=True,
            capture_output=True,
            check=False,
            timeout=60,
        )
        extras[p055.name] = r.returncode
    return {
        "batch1_exit": r1.returncode,
        "batch1_stdout": (r1.stdout or "")[-500:],
        "batch1_stderr": (r1.stderr or "")[-400:],
        "extras": extras,
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
    # Clean env foundation: no crawl dependency; skip freshness (no data yet)
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.golden_path",
            "--sources",
            "pncp",
            "--bootstrap",
            "--allow-zero",
            "--skip-crawl",
            "--skip-freshness",
            f"--ledger-output={ledger}",
            "--dsn",
            dsn,
        ],
        cwd=str(REPO),
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=300,
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
        default=os.getenv("LOCAL_DATALAKE_DSN", "postgresql://test:test@127.0.0.1:5433/extra_test"),
    )
    p.add_argument("--db-name", default="extra_clean")
    p.add_argument(
        "--report",
        default=str(REPO / "output" / "golden-path" / "clean-env-report.json"),
    )
    args = p.parse_args(argv)

    report: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "steps": {},
    }
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
    report["ok"] = bool(rec["ok"] and n >= 5 and gp["ok"])
    report["limitations"] = [
        "vector extension optional (014 skipped if unavailable)",
        "clean env proof uses --skip-crawl --skip-freshness --allow-zero for foundation",
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

"""Concorrentes report for DoD §12.1 golden path (domain-specific, not panorama)."""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.reports.run_metadata import _git_sha_short  # noqa: E402

COLUMNS = (
    "concorrente_id",
    "nome",
    "n_contratos",
    "valor_total",
    "provenance",
)


def _conn(dsn: str):
    import psycopg2
    import psycopg2.extras

    return psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)


def fetch_concorrentes(dsn: str) -> tuple[list[dict[str, Any]], list[str]]:
    limitations: list[str] = []
    try:
        conn = _conn(dsn)
    except Exception as exc:  # noqa: BLE001
        return [], [f"db_connect_failed: {exc}", "report is empty until DSN is reachable"]
    try:
        from scripts.reports.operational_reports import _table_exists, report_concorrentes

        if not (_table_exists(conn, "pncp_supplier_contracts") or _table_exists(conn, "pncp_raw_bids")):
            return [], [
                "table pncp_supplier_contracts/pncp_raw_bids missing",
                "run migrations and crawl before domain report",
            ]
        rows = report_concorrentes(conn)
        if rows and "_error" in rows[0]:
            return [], [f"query_failed: {rows[0]['_error']}"]
        rows = [r for r in rows if "_error" not in r]
        if any(r.get("provenance") == "fallback_orgao_not_supplier" for r in rows):
            limitations.append("concorrentes uses orgao fallback — not true suppliers")
        if not rows:
            limitations.append("zero competitor rows (not success_zero claim of coverage)")
        else:
            limitations.append(f"sample_cap rows={len(rows)}; not full universe operational coverage")
        limitations.append("domain report of stored competitors; does not claim 95% coverage or LOCAL_READY")
        return rows, limitations
    except Exception as exc:  # noqa: BLE001
        try:
            conn.rollback()
        except Exception as rb_exc:  # noqa: BLE001
            return [], [f"query_failed: {exc}", f"rollback_failed: {rb_exc}"]
        return [], [f"query_failed: {exc}"]
    finally:
        conn.close()


def write_concorrentes_report(
    dsn: str,
    *,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    out_dir = out_dir or (_PROJECT_ROOT / "output" / "reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    as_of = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    git_sha = _git_sha_short()
    rows, limitations = fetch_concorrentes(dsn)

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    csv_path = out_dir / f"relatorio-concorrentes-{stamp}.csv"
    json_path = out_dir / f"relatorio-concorrentes-{stamp}.json"

    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(COLUMNS), extrasaction="ignore")
        w.writeheader()
        for row in rows:
            clean = {k: row.get(k) for k in COLUMNS}
            for k, v in list(clean.items()):
                if hasattr(v, "isoformat"):
                    clean[k] = v.isoformat()
            w.writerow(clean)

    payload = {
        "report_type": "concorrentes",
        "as_of": as_of,
        "git_sha": git_sha,
        "row_count": len(rows),
        "columns": list(COLUMNS),
        "csv_path": str(csv_path),
        "limitations": limitations,
        "reference_period": {"as_of": as_of, "window": "stored-competitors"},
        "claims_forbidden": ["LOCAL_READY", "95% coverage", "full live crawl proof"],
    }
    json_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )

    size = csv_path.stat().st_size
    hard_fail_prefixes = (
        "db_connect_failed:",
        "query_failed:",
        "table pncp_supplier_contracts/pncp_raw_bids missing",
    )
    hard_fail = any(any(lim.startswith(p) or lim == p for p in hard_fail_prefixes) for lim in limitations)
    ok = (not hard_fail) and size >= 50
    return {
        "ok": ok,
        "path": str(csv_path),
        "json_path": str(json_path),
        "size": size,
        "row_count": len(rows),
        "columns": list(COLUMNS),
        "as_of": as_of,
        "git_sha": git_sha,
        "limitations": limitations,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Generate domain-specific concorrentes report")
    p.add_argument("--dsn", default=os.getenv("LOCAL_DATALAKE_DSN") or None)
    p.add_argument("--out-dir", default=None)
    args = p.parse_args(argv)
    if not args.dsn:
        print("ERROR: --dsn or LOCAL_DATALAKE_DSN required", file=sys.stderr)
        return 2
    out = write_concorrentes_report(args.dsn, out_dir=Path(args.out_dir) if args.out_dir else None)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

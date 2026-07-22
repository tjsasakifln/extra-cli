"""Editais report for DoD §12.1 golden path (domain-specific, not panorama).

Produces CSV (+ JSON sidecar) of active editais from pncp_raw_bids.
Honest empty: writes header + limitations when zero rows.
"""

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
    "pncp_id",
    "objeto_compra",
    "orgao_razao_social",
    "orgao_cnpj",
    "uf",
    "municipio",
    "modalidade_nome",
    "valor_total_estimado",
    "data_publicacao",
    "data_encerramento",
    "link_pncp",
    "source",
    "is_active",
)


def _conn(dsn: str):
    import psycopg2
    import psycopg2.extras

    return psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)


def fetch_editais(dsn: str, *, limit: int = 5000) -> tuple[list[dict[str, Any]], list[str]]:
    limitations: list[str] = []
    try:
        conn = _conn(dsn)
    except Exception as exc:  # noqa: BLE001
        return [], [f"db_connect_failed: {exc}", "report is empty until DSN is reachable"]
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT EXISTS (
                  SELECT 1 FROM information_schema.tables
                  WHERE table_schema='public' AND table_name='pncp_raw_bids'
                ) AS ok
                """
            )
            if not cur.fetchone()["ok"]:
                return [], ["table pncp_raw_bids missing", "run migrations and crawl before domain report"]
            cur.execute(
                """
                SELECT
                  pncp_id,
                  objeto_compra,
                  orgao_razao_social,
                  orgao_cnpj,
                  uf,
                  municipio,
                  modalidade_nome,
                  valor_total_estimado,
                  data_publicacao,
                  data_encerramento,
                  link_pncp,
                  source,
                  is_active
                FROM pncp_raw_bids
                WHERE COALESCE(is_active, true) = true
                ORDER BY data_publicacao DESC NULLS LAST, pncp_id
                LIMIT %s
                """,
                (limit,),
            )
            rows = [dict(r) for r in cur.fetchall()]
        if not rows:
            limitations.append("zero active editais in pncp_raw_bids (not success_zero claim of coverage)")
        else:
            limitations.append(f"sample_cap={limit}; not full universe operational coverage")
        limitations.append("domain report of stored editais; does not claim 95% coverage or LOCAL_READY")
        return rows, limitations
    except Exception as exc:  # noqa: BLE001
        conn.rollback()
        return [], [f"query_failed: {exc}"]
    finally:
        conn.close()


def write_editais_report(
    dsn: str,
    *,
    out_dir: Path | None = None,
    limit: int = 5000,
) -> dict[str, Any]:
    out_dir = out_dir or (_PROJECT_ROOT / "output" / "reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    as_of = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    git_sha = _git_sha_short()
    rows, limitations = fetch_editais(dsn, limit=limit)

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    csv_path = out_dir / f"relatorio-editais-{stamp}.csv"
    json_path = out_dir / f"relatorio-editais-{stamp}.json"

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
        "report_type": "editais",
        "as_of": as_of,
        "git_sha": git_sha,
        "row_count": len(rows),
        "columns": list(COLUMNS),
        "csv_path": str(csv_path),
        "limitations": limitations,
        "reference_period": {"as_of": as_of, "window": "stored-active-editais"},
        "claims_forbidden": ["LOCAL_READY", "95% coverage", "full live crawl proof"],
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")

    size = csv_path.stat().st_size
    hard_fail_prefixes = (
        "db_connect_failed:",
        "query_failed:",
        "table pncp_raw_bids missing",
    )
    hard_fail = any(
        any(lim.startswith(p) or lim == p for p in hard_fail_prefixes) for lim in limitations
    )
    # Header-only empty is OK when table exists (honest zero + limitations).
    # Connect/query/table failures must not soft-pass.
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
    p = argparse.ArgumentParser(description="Generate domain-specific editais report")
    p.add_argument("--dsn", default=os.getenv("LOCAL_DATALAKE_DSN") or None)
    p.add_argument("--out-dir", default=None)
    p.add_argument("--limit", type=int, default=5000)
    args = p.parse_args(argv)
    if not args.dsn:
        print("ERROR: --dsn or LOCAL_DATALAKE_DSN required", file=sys.stderr)
        return 2
    out = write_editais_report(args.dsn, out_dir=Path(args.out_dir) if args.out_dir else None, limit=args.limit)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

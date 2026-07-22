"""Contratos report for DoD §12.1 golden path (domain-specific, not panorama).

Produces CSV (+ JSON sidecar) of active contracts aggregated by ente/fornecedor
from pncp_supplier_contracts. Honest empty: header + limitations when zero rows.
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

COLUMNS_ENTE = (
    "ente_id",
    "ente_nome",
    "n_contratos",
    "valor_total",
    "valor_semantica",
)

COLUMNS_FORN = (
    "fornecedor_id",
    "nome_fornecedor",
    "n_contratos",
    "valor_total",
    "ticket_medio",
    "valor_semantica",
)


def _conn(dsn: str):
    import psycopg2
    import psycopg2.extras

    return psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)


def fetch_contratos(dsn: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """Return (por_ente, por_fornecedor, limitations)."""
    limitations: list[str] = []
    try:
        conn = _conn(dsn)
    except Exception as exc:  # noqa: BLE001
        return [], [], [f"db_connect_failed: {exc}", "report is empty until DSN is reachable"]
    try:
        from scripts.reports.operational_reports import (
            _table_exists,
            report_contratos_por_ente,
            report_contratos_por_fornecedor,
        )

        if not _table_exists(conn, "pncp_supplier_contracts"):
            return [], [], [
                "table pncp_supplier_contracts missing",
                "run migrations and crawl before domain report",
            ]

        ente = report_contratos_por_ente(conn)
        forn = report_contratos_por_fornecedor(conn)
        if ente and "_error" in ente[0]:
            limitations.append(f"query_failed: ente: {ente[0]['_error']}")
            ente = []
        if forn and "_error" in forn[0]:
            limitations.append(f"query_failed: fornecedor: {forn[0]['_error']}")
            forn = []
        ente = [r for r in ente if "_error" not in r]
        forn = [r for r in forn if "_error" not in r]
        if any(lim.startswith("query_failed:") for lim in limitations):
            return ente, forn, limitations
        if not ente and not forn:
            limitations.append(
                "zero active contracts in pncp_supplier_contracts "
                "(not success_zero claim of coverage)"
            )
        else:
            limitations.append(
                f"sample aggregated rows ente={len(ente)} fornecedor={len(forn)}; "
                "not full universe operational coverage"
            )
        limitations.append(
            "domain report of stored contracts; does not claim 95% coverage or LOCAL_READY"
        )
        return ente, forn, limitations
    except Exception as exc:  # noqa: BLE001
        try:
            conn.rollback()
        except Exception as rb_exc:  # noqa: BLE001
            limitations = [f"query_failed: {exc}", f"rollback_failed: {rb_exc}"]
            return [], [], limitations
        return [], [], [f"query_failed: {exc}"]
    finally:
        conn.close()


def write_contratos_report(
    dsn: str,
    *,
    out_dir: Path | None = None,
) -> dict[str, Any]:
    out_dir = out_dir or (_PROJECT_ROOT / "output" / "reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    as_of = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    git_sha = _git_sha_short()
    ente, forn, limitations = fetch_contratos(dsn)

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    csv_path = out_dir / f"relatorio-contratos-{stamp}.csv"
    json_path = out_dir / f"relatorio-contratos-{stamp}.json"
    csv_forn_path = out_dir / f"relatorio-contratos-fornecedor-{stamp}.csv"

    # Primary domain file: contratos por ente (stable identity for golden path)
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(COLUMNS_ENTE), extrasaction="ignore")
        w.writeheader()
        for row in ente:
            clean = {k: row.get(k) for k in COLUMNS_ENTE}
            for k, v in list(clean.items()):
                if hasattr(v, "isoformat"):
                    clean[k] = v.isoformat()
            w.writerow(clean)

    with csv_forn_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(COLUMNS_FORN), extrasaction="ignore")
        w.writeheader()
        for row in forn:
            clean = {k: row.get(k) for k in COLUMNS_FORN}
            for k, v in list(clean.items()):
                if hasattr(v, "isoformat"):
                    clean[k] = v.isoformat()
            w.writerow(clean)

    payload = {
        "report_type": "contratos",
        "as_of": as_of,
        "git_sha": git_sha,
        "row_count_ente": len(ente),
        "row_count_fornecedor": len(forn),
        "row_count": len(ente) + len(forn),
        "columns_ente": list(COLUMNS_ENTE),
        "columns_fornecedor": list(COLUMNS_FORN),
        "csv_path": str(csv_path),
        "csv_fornecedor_path": str(csv_forn_path),
        "limitations": limitations,
        "reference_period": {"as_of": as_of, "window": "stored-active-contracts"},
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
        "table pncp_supplier_contracts missing",
    )
    hard_fail = any(
        any(lim.startswith(p) or lim == p for p in hard_fail_prefixes) for lim in limitations
    )
    # Header-only is OK when table empty (honest zero). Connect/query fails must not soft-pass.
    ok = (not hard_fail) and size >= 50
    return {
        "ok": ok,
        "path": str(csv_path),
        "path_fornecedor": str(csv_forn_path),
        "json_path": str(json_path),
        "size": size,
        "row_count": len(ente) + len(forn),
        "row_count_ente": len(ente),
        "row_count_fornecedor": len(forn),
        "columns": list(COLUMNS_ENTE),
        "as_of": as_of,
        "git_sha": git_sha,
        "limitations": limitations,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Generate domain-specific contratos report")
    p.add_argument("--dsn", default=os.getenv("LOCAL_DATALAKE_DSN") or None)
    p.add_argument("--out-dir", default=None)
    args = p.parse_args(argv)
    if not args.dsn:
        print("ERROR: --dsn or LOCAL_DATALAKE_DSN required", file=sys.stderr)
        return 2
    out = write_contratos_report(args.dsn, out_dir=Path(args.out_dir) if args.out_dir else None)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

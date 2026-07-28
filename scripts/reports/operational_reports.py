#!/usr/bin/env python3
"""Operational analytical reports for DoD §12.2 (next 8 report types).

1. contratos por ente
2. contratos por fornecedor
3. concorrentes
4. concentração (HHI only when n sufficient; else limitation)
5. referências de valores (estimated ≠ homologated ≠ contracted)
6. completude de campos essenciais
7. coverage (presence/signal — not operational 95%)
8. recall (requires gold sample; else NOT_READY)

Honest empty + limitations. Never claims LOCAL_READY or 95% operational coverage.
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

from scripts.reports.run_metadata import (  # noqa: E402
    build_run_metadata,
    new_run_id,
    validate_operational_metadata,
)

REPORT_FILES = {
    "contratos_por_ente": "relatorio_contratos_por_ente.csv",
    "contratos_por_fornecedor": "relatorio_contratos_por_fornecedor.csv",
    "concorrentes": "relatorio_concorrentes.csv",
    "concentracao": "relatorio_concentracao.csv",
    "referencias_valores": "relatorio_referencias_valores.csv",
    "completude": "relatorio_completude.csv",
    "coverage": "relatorio_coverage.csv",
    "recall": "relatorio_recall.csv",
}

ESSENTIAL_BID_FIELDS = (
    "pncp_id",
    "objeto_compra",
    "orgao_cnpj",
    "uf",
    "municipio",
    "data_encerramento",
    "link_pncp",
    "valor_total_estimado",
)


def _conn(dsn: str):
    import psycopg2
    import psycopg2.extras

    return psycopg2.connect(dsn, cursor_factory=psycopg2.extras.RealDictCursor)


class OperationalReportError(RuntimeError):
    """Fail-closed error for analytical operational reports."""


def _q(conn, sql: str, params: tuple | list | None = None) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        try:
            cur.execute(sql, params or ())
            return [dict(r) for r in cur.fetchall()]
        except Exception as exc:  # noqa: BLE001
            if hasattr(conn, "rollback"):
                conn.rollback()
            raise OperationalReportError(str(exc)) from exc


def _table_exists(conn, name: str) -> bool:
    rows = _q(
        conn,
        "SELECT 1 AS ok FROM information_schema.tables WHERE table_schema='public' AND table_name=%s",
        (name,),
    )
    return bool(rows)


def _write_csv(path: Path, rows: list[dict[str, Any]], headers: list[str] | None = None) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    if any(isinstance(r, dict) and "_error" in r for r in rows):
        raise OperationalReportError("refusing to write CSV containing _error rows (fail-closed)")
    clean = list(rows)
    if headers is None:
        headers = []
        for r in clean:
            for k in r:
                if k not in headers:
                    headers.append(k)
    if not headers:
        headers = ["note"]
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=headers, extrasaction="ignore")
        w.writeheader()
        for r in clean:
            w.writerow({k: r.get(k) for k in headers})
    return len(clean)


def report_contratos_por_ente(conn) -> list[dict[str, Any]]:
    if not _table_exists(conn, "pncp_supplier_contracts"):
        return []  # table pncp_supplier_contracts missing → empty + limitation upstream
    # Schema canonical: orgao_cnpj, orgao_nome, valor_total (not valor_global/homologado)
    # SUM only over non-null valor_total; missing values are not coerced into the fact row as zero fill.
    rows = _q(
        conn,
        """
        SELECT
            COALESCE(orgao_cnpj, 'UNKNOWN') AS ente_id,
            COALESCE(orgao_nome, 'N/I') AS ente_nome,
            COUNT(*) AS n_contratos,
            SUM(valor_total) FILTER (WHERE valor_total IS NOT NULL) AS valor_total,
            COUNT(*) FILTER (WHERE valor_total IS NULL) AS n_valor_ausente,
            'valor_total (schema pncp_supplier_contracts); nulls not zero-filled' AS valor_semantica
        FROM pncp_supplier_contracts
        WHERE is_active IS TRUE
        GROUP BY 1, 2
        HAVING COUNT(*) > 0
        ORDER BY n_contratos DESC, valor_total DESC NULLS LAST
        LIMIT 500
        """,
    )
    # Propagate query failure — never silent empty success
    return rows


def report_contratos_por_fornecedor(conn) -> list[dict[str, Any]]:
    if not _table_exists(conn, "pncp_supplier_contracts"):
        return []  # table pncp_supplier_contracts missing → empty + limitation upstream
    rows = _q(
        conn,
        """
        SELECT
            COALESCE(fornecedor_cnpj, 'UNKNOWN') AS fornecedor_id,
            COALESCE(fornecedor_nome, 'N/I') AS nome_fornecedor,
            COUNT(*) AS n_contratos,
            SUM(valor_total) FILTER (WHERE valor_total IS NOT NULL) AS valor_total,
            COUNT(*) FILTER (WHERE valor_total IS NULL) AS n_valor_ausente,
            CASE WHEN COUNT(*) FILTER (WHERE valor_total IS NOT NULL) > 0
                 THEN SUM(valor_total) FILTER (WHERE valor_total IS NOT NULL)
                      / COUNT(*) FILTER (WHERE valor_total IS NOT NULL)
                 ELSE NULL END AS ticket_medio,
            'ticket_medio = sum(valor_total válido) / n_válidos; nulls not zero-filled' AS valor_semantica
        FROM pncp_supplier_contracts
        WHERE is_active IS TRUE
          AND fornecedor_cnpj IS NOT NULL
          AND btrim(fornecedor_cnpj) <> ''
        GROUP BY 1, 2
        HAVING COUNT(*) > 0
        ORDER BY n_contratos DESC, valor_total DESC NULLS LAST
        LIMIT 500
        """,
    )
    return rows


def report_concorrentes(conn) -> list[dict[str, Any]]:
    """Observable winners/competitors from supplier contracts only.

    Fail-closed: never present contracting authority (órgão) as competitor.
    When suppliers are unavailable, return empty list with explicit provenance
    marker row only if query fails; otherwise empty (callers must read limitations).
    """
    if not _table_exists(conn, "pncp_supplier_contracts"):
        return []  # table pncp_supplier_contracts missing → empty + limitation upstream
    rows = _q(
        conn,
        """
        SELECT
            fornecedor_cnpj AS concorrente_id,
            COALESCE(fornecedor_nome, 'N/I') AS nome,
            COUNT(*) AS n_contratos,
            SUM(valor_total) FILTER (WHERE valor_total IS NOT NULL) AS valor_total,
            COUNT(*) FILTER (WHERE valor_total IS NULL) AS n_valor_ausente,
            'from_pncp_supplier_contracts' AS provenance,
            'winner_identified' AS role
        FROM pncp_supplier_contracts
        WHERE is_active IS TRUE
          AND fornecedor_cnpj IS NOT NULL
          AND btrim(fornecedor_cnpj) <> ''
          AND (
                orgao_cnpj IS NULL
                OR btrim(fornecedor_cnpj) <> btrim(orgao_cnpj)
              )
        GROUP BY 1, 2
        HAVING COUNT(*) > 0
        ORDER BY n_contratos DESC
        LIMIT 15
        """,
    )
    # No orgao fallback — empty list is honest absence of observable suppliers
    return rows or []


def report_concentracao(conn) -> tuple[list[dict[str, Any]], list[str]]:
    """HHI only when enough supplier contract mass; else limitations."""
    limitations: list[str] = []
    fornecedores = report_contratos_por_fornecedor(conn)
    clean = [r for r in fornecedores if (r.get("n_contratos") or 0) > 0]
    if not clean:
        # try competitors from bids as weak signal
        comps = report_concorrentes(conn)
        clean = list(comps)
        if not clean:
            limitations.append("No supplier/contract mass for HHI; concentration report empty")
            return [], limitations
        metric_key = "n_editais" if "n_editais" in clean[0] else "n_contratos"
        limitations.append("Concentration based on orgao editais fallback — NOT market HHI")
    else:
        metric_key = "n_contratos"

    total = sum(float(r.get(metric_key) or r.get("valor_total") or 0) for r in clean)
    if total <= 0:
        limitations.append("Zero mass for concentration")
        return [], limitations
    if len(clean) < 3:
        limitations.append("n_players < 3 — HHI not defensable as market concentration")

    rows: list[dict[str, Any]] = []
    hhi = 0.0
    for r in clean:
        mass = float(r.get(metric_key) or r.get("valor_total") or 0)
        share = mass / total
        hhi += share * share
        rows.append(
            {
                "player_id": r.get("fornecedor_id") or r.get("concorrente_id"),
                "nome": r.get("nome_fornecedor") or r.get("nome"),
                "mass": mass,
                "market_share_pct": round(share * 100, 4),
                "metric": metric_key,
            }
        )
    rows.append(
        {
            "player_id": "_HHI",
            "nome": "Herfindahl-Hirschman Index",
            "mass": None,
            "market_share_pct": round(hhi * 10000, 4) if hhi <= 1 else round(hhi, 4),
            "metric": "HHI_0_10000" if hhi <= 1 else "HHI",
        }
    )
    # store HHI in 0-10000 scale in last row
    if hhi <= 1:
        rows[-1]["market_share_pct"] = round(hhi * 10000, 2)
    # Orgão fallback or n_players < 3 → LOW; only MEDIUM with real suppliers + n>=3
    is_orgao_proxy = any("NOT market HHI" in x for x in limitations) or metric_key == "n_editais"
    level = "LOW" if (len(clean) < 3 or is_orgao_proxy) else "MEDIUM"
    for r in rows:
        r["defensability"] = level
    return rows, limitations


def report_referencias_valores(conn) -> list[dict[str, Any]]:
    if not _table_exists(conn, "pncp_raw_bids"):
        return []
    return _q(
        conn,
        """
        SELECT
            COALESCE(modalidade_nome, 'N/I') AS modalidade,
            COUNT(*) AS n,
            AVG(valor_total_estimado) AS ticket_medio_estimado,
            MIN(valor_total_estimado) AS min_estimado,
            MAX(valor_total_estimado) AS max_estimado,
            'valor_total_estimado' AS valor_semantica,
            'NOT homologado/contratado/pago' AS disclaimer
        FROM pncp_raw_bids
        WHERE is_active IS TRUE
          AND valor_total_estimado IS NOT NULL
          AND valor_total_estimado > 0
        GROUP BY 1
        ORDER BY n DESC
        LIMIT 50
        """,
    )


def report_completude(conn) -> list[dict[str, Any]]:
    if not _table_exists(conn, "pncp_raw_bids"):
        return []
    # ESSENTIAL_BID_FIELDS is a fixed internal column allow-list (not user input).
    field_exprs = ", ".join(f"COUNT({f}) AS filled_{f}" for f in ESSENTIAL_BID_FIELDS)
    rows = _q(
        conn,
        f"""
        SELECT
            COUNT(*) AS n_active,
            {field_exprs}
        FROM pncp_raw_bids
        WHERE is_active IS TRUE
        """,  # noqa: S608 — field list is fixed ESSENTIAL_BID_FIELDS allow-list
    )
    if not rows:
        return []
    n = int(rows[0].get("n_active") or 0)
    out: list[dict[str, Any]] = []
    for f in ESSENTIAL_BID_FIELDS:
        filled = int(rows[0].get(f"filled_{f}") or 0)
        pct = (filled / n * 100.0) if n else 0.0
        out.append(
            {
                "field": f,
                "n_active": n,
                "filled": filled,
                "completeness_pct": round(pct, 2),
                "status": "OK" if n and pct >= 95 else ("EMPTY" if n == 0 else "BELOW_95"),
            }
        )
    if n:
        # overall essential completeness (all fields non-null)
        overall = _q(
            conn,
            """
            SELECT COUNT(*) AS complete_rows FROM pncp_raw_bids
            WHERE is_active IS TRUE
              AND pncp_id IS NOT NULL AND objeto_compra IS NOT NULL
              AND orgao_cnpj IS NOT NULL AND uf IS NOT NULL
            """,
        )
        complete = int((overall[0] or {}).get("complete_rows") or 0) if overall else 0
        out.append(
            {
                "field": "_overall_core",
                "n_active": n,
                "filled": complete,
                "completeness_pct": round(complete / n * 100.0, 2),
                "status": "OK" if complete / n >= 0.95 else "BELOW_95",
            }
        )
    return out


def report_coverage(conn) -> list[dict[str, Any]]:
    """Presence/signal coverage — NOT operational 95% claim."""
    out: list[dict[str, Any]] = []
    n_entities = 0
    if _table_exists(conn, "sc_public_entities"):
        r = _q(conn, "SELECT COUNT(*) AS n FROM sc_public_entities WHERE is_active IS TRUE")
        n_entities = int((r[0] or {}).get("n") or 0) if r else 0
    n_bids = 0
    n_matched = 0
    if _table_exists(conn, "pncp_raw_bids"):
        r = _q(
            conn,
            """
            SELECT COUNT(*) AS n_bids,
                   COUNT(matched_entity_id) AS n_matched
            FROM pncp_raw_bids WHERE is_active IS TRUE
            """,
        )
        if r:
            n_bids = int(r[0].get("n_bids") or 0)
            n_matched = int(r[0].get("n_matched") or 0)
    n_contracts = 0
    if _table_exists(conn, "pncp_supplier_contracts"):
        r = _q(conn, "SELECT COUNT(*) AS n FROM pncp_supplier_contracts")
        n_contracts = int((r[0] or {}).get("n") or 0) if r else 0

    den = n_entities if n_entities else None
    out.append(
        {
            "metric": "entities_in_sc_public_entities",
            "numerator": n_entities,
            "denominator": n_entities,
            "pct": 100.0 if n_entities else None,
            "kind": "presence",
            "claim": "NOT operational coverage",
        }
    )
    out.append(
        {
            "metric": "active_bids_presence",
            "numerator": n_bids,
            "denominator": den,
            "pct": round(n_bids / den * 100, 4) if den else None,
            "kind": "signal",
            "claim": "NOT operational coverage",
        }
    )
    out.append(
        {
            "metric": "bids_matched_to_entity",
            "numerator": n_matched,
            "denominator": n_bids if n_bids else den,
            "pct": round(n_matched / n_bids * 100, 4) if n_bids else None,
            "kind": "signal",
            "claim": "NOT operational coverage",
        }
    )
    out.append(
        {
            "metric": "contracts_rows",
            "numerator": n_contracts,
            "denominator": den,
            "pct": None,
            "kind": "presence",
            "claim": "NOT operational coverage",
        }
    )
    out.append(
        {
            "metric": "operational_coverage_strict",
            "numerator": 0,
            "denominator": 1093,
            "pct": 0.0,
            "kind": "operational",
            "claim": "campaign_truth: remains ~0% until entity stages complete",
        }
    )
    return out


def report_recall(conn) -> tuple[list[dict[str, Any]], list[str]]:
    """Recall requires independent gold sample; without it, NOT_READY."""
    limitations = [
        "No stratified gold sample loaded in this DB — recall NOT_READY",
        "Do not treat presence of bids as recall ≥95%",
    ]
    n_bids = 0
    if _table_exists(conn, "pncp_raw_bids"):
        r = _q(conn, "SELECT COUNT(*) AS n FROM pncp_raw_bids WHERE is_active IS TRUE")
        n_bids = int((r[0] or {}).get("n") or 0) if r else 0
    rows = [
        {
            "metric": "recall_relevant_tenders",
            "status": "NOT_READY",
            "tp": None,
            "fn": None,
            "recall_pct": None,
            "gold_sample_size": 0,
            "system_active_bids": n_bids,
            "note": "Gold sample required for recall calculation",
        }
    ]
    return rows, limitations


def build_reports(conn) -> dict[str, Any]:
    """Build analytical reports. SQL failures raise OperationalReportError."""
    import hashlib
    import time

    limitations: list[str] = []
    t0 = time.perf_counter()
    contratos_ente = report_contratos_por_ente(conn)
    if not contratos_ente:
        limitations.append("contratos_por_ente empty (no contracts or table)")

    contratos_forn = report_contratos_por_fornecedor(conn)
    if not contratos_forn:
        limitations.append("contratos_por_fornecedor empty")

    concorrentes = report_concorrentes(conn)
    if any(r.get("provenance") == "fallback_orgao_not_supplier" for r in concorrentes):
        limitations.append("concorrentes uses orgao fallback — not true suppliers")
    if not concorrentes:
        limitations.append("concorrentes empty")

    concentracao, lim_c = report_concentracao(conn)
    limitations.extend(lim_c)

    refs = report_referencias_valores(conn)
    if not refs:
        limitations.append("referencias_valores empty")

    completude = report_completude(conn)
    if not completude:
        limitations.append("completude empty")

    coverage = report_coverage(conn)
    recall, lim_r = report_recall(conn)
    limitations.extend(lim_r)

    counts = {
        "contratos_por_ente": len(contratos_ente),
        "contratos_por_fornecedor": len(contratos_forn),
        "concorrentes": len(concorrentes),
        "concentracao": len(concentracao),
        "referencias_valores": len(refs),
        "completude": len(completude),
        "coverage": len(coverage),
        "recall": len(recall),
    }
    data_rows = sum(counts[k] for k in counts if k != "recall")
    status = "SUCCESS" if data_rows > 0 else "SUCCESS_ZERO"
    reliability = "READY" if data_rows > 0 and not limitations else (
        "NOT_READY" if data_rows == 0 else "PARTIAL"
    )
    schema_version = None
    if _table_exists(conn, "_migrations"):
        rows = _q(
            conn,
            "SELECT version FROM _migrations ORDER BY applied_at DESC NULLS LAST LIMIT 1",
        )
        schema_version = str(rows[0].get("version")) if rows else None
    payload_hash = hashlib.sha256(
        json.dumps({"counts": counts, "schema": schema_version}, sort_keys=True).encode()
    ).hexdigest()

    return {
        "contratos_por_ente": contratos_ente,
        "contratos_por_fornecedor": contratos_forn,
        "concorrentes": concorrentes,
        "concentracao": concentracao,
        "referencias_valores": refs,
        "completude": completude,
        "coverage": coverage,
        "recall": recall,
        "meta": {
            "limitations": limitations,
            "errors": [],
            "counts": counts,
            "status": status,
            "reliability": reliability,
            "schema_version": schema_version,
            "dataset_hash": payload_hash,
            "duration_seconds": round(time.perf_counter() - t0, 4),
            "period": {
                "as_of_date": datetime.now(UTC).date().isoformat(),
                "data_window": "all_active",
            },
            "source": "postgresql",
        },
    }


def write_reports(
    out_dir: Path,
    payload: dict[str, Any],
    *,
    run_id: str | None = None,
    duration_seconds: float | None = None,
) -> dict[str, Any]:
    import hashlib

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rid = run_id or new_run_id("ops-reports")
    files: dict[str, Any] = {}
    artifact_hashes: dict[str, str] = {}
    for key, filename in REPORT_FILES.items():
        path = out_dir / filename
        rows = payload.get(key) or []
        n = _write_csv(path, rows if isinstance(rows, list) else [])
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        artifact_hashes[filename] = digest
        files[key] = {
            "path": str(path),
            "rows": n,
            "bytes": path.stat().st_size,
            "sha256": digest,
        }

    meta = payload.get("meta") or {}
    limitations = list(meta.get("limitations") or [])
    reliability = meta.get("reliability") or ("PARTIAL" if limitations else "READY")
    status = meta.get("status") or "SUCCESS"
    dur = duration_seconds if duration_seconds is not None else meta.get("duration_seconds")

    shared = build_run_metadata(
        run_id=rid,
        artifact_kind="operational_reports",
        script="scripts/reports/operational_reports.py",
        db_schema_version=meta.get("schema_version"),
        dataset_hash=meta.get("dataset_hash"),
        source=meta.get("source") or "postgresql",
        capability="operational_reports_12_2",
        period=meta.get("period"),
        parameters={},
        reliability=reliability,
        limitations=limitations,
        errors=list(meta.get("errors") or []),
        duration_seconds=dur,
        artifact_hashes=artifact_hashes,
    )
    # Keep legacy reliability labels for older consumers
    reliability_legacy = (
        "TRUSTED"
        if reliability == "READY"
        else ("DEGRADED" if reliability == "PARTIAL" else "UNTRUSTED")
    )
    manifest = {
        **shared,
        "section": "12.2-reports",
        "reports": files,
        "counts": meta.get("counts"),
        "status": status,
        "reliability": reliability,
        "reliability_legacy": reliability_legacy,
        "claims": {
            "allowed": [
                "Eight analytical report CSVs generated from PostgreSQL",
                "Value semantics labeled (estimado vs homologado)",
                "Recall explicitly NOT_READY without gold sample",
                "SUCCESS_ZERO when empty with documented limitations",
            ],
            "forbidden": [
                "LOCAL_READY",
                "operational coverage 95%",
                "recall 95%",
                "PRE_VPS_FINAL_READY",
                "PROJECT_DONE",
                "empty CSV after SQL error as success",
            ],
        },
    }
    missing = validate_operational_metadata(manifest)
    if missing:
        limitations.append(f"metadata_incomplete:{','.join(missing)}")
        manifest["limitations"] = limitations
    man_path = out_dir / "manifest.json"
    man_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    manifest["manifest_path"] = str(man_path)
    manifest["artifact_hashes"]["manifest.json"] = hashlib.sha256(
        man_path.read_bytes()
    ).hexdigest()
    return manifest


def run(dsn: str, out_dir: Path) -> dict[str, Any]:
    import time

    t0 = time.perf_counter()
    conn = _conn(dsn)
    try:
        payload = build_reports(conn)
    finally:
        conn.close()
    return write_reports(
        out_dir, payload, duration_seconds=round(time.perf_counter() - t0, 4)
    )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="DoD §12.2 operational analytical reports")
    p.add_argument("--dsn", default=os.environ.get("LOCAL_DATALAKE_DSN") or os.environ.get("DATABASE_URL"))
    p.add_argument("--out", type=Path, default=Path("output/operational-reports"))
    p.add_argument("--json", action="store_true")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Build reports in memory; do not write CSV files",
    )
    args = p.parse_args(argv)
    if not args.dsn:
        print("ERROR: --dsn required", file=sys.stderr)
        return 2
    try:
        if args.dry_run:
            conn = _conn(args.dsn)
            try:
                payload = build_reports(conn)
            finally:
                conn.close()
            summary = {
                "dry_run": True,
                "counts": (payload.get("meta") or {}).get("counts"),
                "limitations": (payload.get("meta") or {}).get("limitations"),
                "status": (payload.get("meta") or {}).get("status"),
                "reliability": (payload.get("meta") or {}).get("reliability"),
                "would_write": str(args.out),
            }
            print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))
            return 0
        man = run(args.dsn, args.out)
    except OperationalReportError as exc:
        print(
            json.dumps(
                {"ok": False, "error": str(exc), "error_type": "OperationalReportError"},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1
    except Exception as exc:  # noqa: BLE001
        print(
            json.dumps(
                {"ok": False, "error": str(exc), "error_type": type(exc).__name__},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1
    if args.json:
        print(json.dumps(man, indent=2, ensure_ascii=False, default=str))
    else:
        print(
            f"run_id={man['run_id']} status={man.get('status')} "
            f"reliability={man['reliability']}"
        )
        for k, v in (man.get("counts") or {}).items():
            print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

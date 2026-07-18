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
import math
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.reports.run_metadata import _git_sha_short, new_run_id  # noqa: E402

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


def _q(conn, sql: str, params: tuple | list | None = None) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        try:
            cur.execute(sql, params or ())
            return [dict(r) for r in cur.fetchall()]
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            return [{"_error": str(exc)}]


def _table_exists(conn, name: str) -> bool:
    rows = _q(
        conn,
        "SELECT 1 AS ok FROM information_schema.tables WHERE table_schema='public' AND table_name=%s",
        (name,),
    )
    return bool(rows) and "_error" not in rows[0]


def _write_csv(path: Path, rows: list[dict[str, Any]], headers: list[str] | None = None) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = [r for r in rows if "_error" not in r]
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
        return []
    # Schema canonical: orgao_cnpj, orgao_nome, valor_total (not valor_global/homologado)
    rows = _q(
        conn,
        """
        SELECT
            COALESCE(orgao_cnpj, 'UNKNOWN') AS ente_id,
            COALESCE(orgao_nome, 'N/I') AS ente_nome,
            COUNT(*) AS n_contratos,
            SUM(COALESCE(valor_total, 0)) AS valor_total,
            'valor_total (schema pncp_supplier_contracts)' AS valor_semantica
        FROM pncp_supplier_contracts
        WHERE is_active IS TRUE
        GROUP BY 1, 2
        HAVING COUNT(*) > 0
        ORDER BY n_contratos DESC, valor_total DESC NULLS LAST
        LIMIT 500
        """,
    )
    if rows and "_error" in rows[0]:
        return []
    return rows


def report_contratos_por_fornecedor(conn) -> list[dict[str, Any]]:
    if not _table_exists(conn, "pncp_supplier_contracts"):
        return []
    rows = _q(
        conn,
        """
        SELECT
            COALESCE(fornecedor_cnpj, 'UNKNOWN') AS fornecedor_id,
            COALESCE(fornecedor_nome, 'N/I') AS nome_fornecedor,
            COUNT(*) AS n_contratos,
            SUM(COALESCE(valor_total, 0)) AS valor_total,
            CASE WHEN COUNT(*) > 0
                 THEN SUM(COALESCE(valor_total, 0)) / COUNT(*)
                 ELSE NULL END AS ticket_medio,
            'ticket_medio = valor_total / n_contratos (schema valor_total)' AS valor_semantica
        FROM pncp_supplier_contracts
        WHERE is_active IS TRUE
        GROUP BY 1, 2
        HAVING COUNT(*) > 0
        ORDER BY n_contratos DESC, valor_total DESC NULLS LAST
        LIMIT 500
        """,
    )
    if rows and "_error" in rows[0]:
        return []
    return rows


def report_concorrentes(conn) -> list[dict[str, Any]]:
    """Observable competitors from contracts; fallback orgaos if no suppliers."""
    if _table_exists(conn, "pncp_supplier_contracts"):
        rows = _q(
            conn,
            """
            SELECT
                COALESCE(fornecedor_cnpj, 'UNKNOWN') AS concorrente_id,
                COALESCE(fornecedor_nome, 'N/I') AS nome,
                COUNT(*) AS n_contratos,
                SUM(COALESCE(valor_total, 0)) AS valor_total,
                'from_pncp_supplier_contracts' AS provenance
            FROM pncp_supplier_contracts
            WHERE is_active IS TRUE
            GROUP BY 1, 2
            HAVING COUNT(*) > 0
            ORDER BY n_contratos DESC
            LIMIT 15
            """,
        )
        if rows and "_error" not in rows[0]:
            n_total = sum(int(r.get("n_contratos") or 0) for r in rows if "_error" not in r)
            if n_total > 0:
                return rows
    if not _table_exists(conn, "pncp_raw_bids"):
        return []
    return _q(
        conn,
        """
        SELECT
            COALESCE(orgao_cnpj, 'UNKNOWN') AS concorrente_id,
            COALESCE(orgao_razao_social, 'N/I') AS nome,
            COUNT(*) AS n_editais,
            SUM(COALESCE(valor_total_estimado, 0)) AS valor_estimado_total,
            'fallback_orgao_not_supplier' AS provenance
        FROM pncp_raw_bids
        WHERE is_active IS TRUE AND orgao_cnpj IS NOT NULL
        GROUP BY 1, 2
        ORDER BY n_editais DESC
        LIMIT 15
        """,
    )


def report_concentracao(conn) -> tuple[list[dict[str, Any]], list[str]]:
    """HHI only when enough supplier contract mass; else limitations."""
    limitations: list[str] = []
    fornecedores = report_contratos_por_fornecedor(conn)
    clean = [r for r in fornecedores if "_error" not in r and (r.get("n_contratos") or 0) > 0]
    if not clean:
        # try competitors from bids as weak signal
        comps = report_concorrentes(conn)
        clean = [r for r in comps if "_error" not in r]
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
    rows = _q(
        conn,
        f"""
        SELECT
            COUNT(*) AS n_active,
            {", ".join(f"COUNT({f}) AS filled_{f}" for f in ESSENTIAL_BID_FIELDS)}
        FROM pncp_raw_bids
        WHERE is_active IS TRUE
        """,
    )
    if not rows or "_error" in rows[0]:
        return rows or []
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
        complete = int((overall[0] or {}).get("complete_rows") or 0) if overall and "_error" not in overall[0] else 0
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
        n_entities = int((r[0] or {}).get("n") or 0) if r and "_error" not in r[0] else 0
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
        if r and "_error" not in r[0]:
            n_bids = int(r[0].get("n_bids") or 0)
            n_matched = int(r[0].get("n_matched") or 0)
    n_contracts = 0
    if _table_exists(conn, "pncp_supplier_contracts"):
        r = _q(conn, "SELECT COUNT(*) AS n FROM pncp_supplier_contracts")
        n_contracts = int((r[0] or {}).get("n") or 0) if r and "_error" not in r[0] else 0

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
        n_bids = int((r[0] or {}).get("n") or 0) if r and "_error" not in r[0] else 0
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
    limitations: list[str] = []
    contratos_ente = report_contratos_por_ente(conn)
    if contratos_ente and "_error" in contratos_ente[0]:
        limitations.append(f"contratos_por_ente: {contratos_ente[0]['_error']}")
        contratos_ente = []
    elif not contratos_ente:
        limitations.append("contratos_por_ente empty (no contracts or table)")

    contratos_forn = report_contratos_por_fornecedor(conn)
    if contratos_forn and "_error" in contratos_forn[0]:
        limitations.append(f"contratos_por_fornecedor: {contratos_forn[0]['_error']}")
        contratos_forn = []
    elif not contratos_forn:
        limitations.append("contratos_por_fornecedor empty")

    concorrentes = report_concorrentes(conn)
    if concorrentes and "_error" in concorrentes[0]:
        limitations.append(f"concorrentes: {concorrentes[0]['_error']}")
        concorrentes = []
    # if fallback provenance, note it
    if any(r.get("provenance") == "fallback_orgao_not_supplier" for r in concorrentes if "_error" not in r):
        limitations.append("concorrentes uses orgao fallback — not true suppliers")

    concentracao, lim_c = report_concentracao(conn)
    limitations.extend(lim_c)

    refs = report_referencias_valores(conn)
    if refs and "_error" in refs[0]:
        limitations.append(f"referencias: {refs[0]['_error']}")
        refs = []

    completude = report_completude(conn)
    if completude and "_error" in completude[0]:
        limitations.append(f"completude: {completude[0]['_error']}")
        completude = []

    coverage = report_coverage(conn)
    recall, lim_r = report_recall(conn)
    limitations.extend(lim_r)

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
            "counts": {
                k: len([r for r in (v if isinstance(v, list) else []) if "_error" not in r])
                for k, v in {
                    "contratos_por_ente": contratos_ente,
                    "contratos_por_fornecedor": contratos_forn,
                    "concorrentes": concorrentes,
                    "concentracao": concentracao,
                    "referencias_valores": refs,
                    "completude": completude,
                    "coverage": coverage,
                    "recall": recall,
                }.items()
            },
        },
    }


def write_reports(out_dir: Path, payload: dict[str, Any], *, run_id: str | None = None) -> dict[str, Any]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rid = run_id or new_run_id("ops-reports")
    generated_at = datetime.now(UTC).isoformat()
    files: dict[str, Any] = {}
    for key, filename in REPORT_FILES.items():
        path = out_dir / filename
        rows = payload.get(key) or []
        n = _write_csv(path, rows if isinstance(rows, list) else [])
        files[key] = {"path": str(path), "rows": n, "bytes": path.stat().st_size}

    meta = payload.get("meta") or {}
    reliability = "DEGRADED" if meta.get("limitations") else "TRUSTED"
    if any("NOT_READY" in str(r) for r in (payload.get("recall") or [])):
        reliability = "DEGRADED"

    manifest = {
        "schema_version": 1,
        "run_id": rid,
        "generated_at": generated_at,
        "git_sha": _git_sha_short(),
        "section": "12.2-reports",
        "reports": files,
        "counts": meta.get("counts"),
        "limitations": meta.get("limitations") or [],
        "reliability": reliability,
        "claims": {
            "allowed": [
                "Eight analytical report CSVs generated from PostgreSQL",
                "Value semantics labeled (estimado vs homologado)",
                "Recall explicitly NOT_READY without gold sample",
            ],
            "forbidden": [
                "LOCAL_READY",
                "operational coverage 95%",
                "recall 95%",
                "PRE_VPS_FINAL_READY",
                "PROJECT_DONE",
            ],
        },
    }
    man_path = out_dir / "manifest.json"
    man_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    manifest["manifest_path"] = str(man_path)
    return manifest


def run(dsn: str, out_dir: Path) -> dict[str, Any]:
    conn = _conn(dsn)
    try:
        payload = build_reports(conn)
    finally:
        conn.close()
    return write_reports(out_dir, payload)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="DoD §12.2 operational analytical reports")
    p.add_argument("--dsn", default=os.environ.get("LOCAL_DATALAKE_DSN") or os.environ.get("DATABASE_URL"))
    p.add_argument("--out", type=Path, default=Path("output/operational-reports"))
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    if not args.dsn:
        print("ERROR: --dsn required", file=sys.stderr)
        return 2
    man = run(args.dsn, args.out)
    if args.json:
        print(json.dumps(man, indent=2, ensure_ascii=False, default=str))
    else:
        print(f"run_id={man['run_id']} reliability={man['reliability']}")
        for k, v in (man.get("counts") or {}).items():
            print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

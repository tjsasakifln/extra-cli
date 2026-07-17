#!/usr/bin/env python3
"""Commercial sample report for Extra Construtora (SC) — artifact-first.

Builds an honest advisory sample from committed artifacts and optional DB.
Never hides low coverage or stale freshness. Does not invent GO for 3y.

Usage:
  PYTHONPATH=. python3 scripts/reports/commercial_sample_sc.py \\
    --output output/reports/commercial-sample-sc.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _load_json(path: Path) -> dict[str, Any] | list[Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _disclaimer(coverage_pct: float | None, pilot_status: str | None, freshness: dict | None) -> list[str]:
    notes: list[str] = []
    if coverage_pct is not None and coverage_pct < 50:
        notes.append(
            f"Cobertura bruta de editais ~{coverage_pct:.2f}% — amostra incompleta; "
            "não use como universo exaustivo de SC."
        )
    if pilot_status and pilot_status != "success":
        notes.append(
            f"Piloto de contratos PNCP status={pilot_status}; "
            "backfill nacional 90d/3y NÃO autorizado."
        )
    if freshness:
        overall = freshness.get("overall") or {}
        failing = overall.get("failing_sources") or []
        if failing:
            notes.append(
                "Fontes críticas sem prova de freshness: " + ", ".join(str(s) for s in failing)
            )
    notes.append(
        "Datas em pncp_supplier_contracts.data_publicacao podem refletir "
        "dataAssinatura histórica (semântica legada) — não interpretar MIN/MAX "
        "como cobertura da janela de coleta."
    )
    notes.append("VPS/infra remota não deve ser tratada como operacional sem evidência.")
    return notes


def _db_sample(dsn: str | None, limit: int = 15) -> dict[str, Any]:
    if not dsn:
        return {"available": False, "reason": "no DSN"}
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
    except ImportError:
        return {"available": False, "reason": "psycopg2 missing"}

    try:
        conn = psycopg2.connect(dsn, connect_timeout=5)
    except Exception as e:  # noqa: BLE001 — soft fail for report
        return {"available": False, "reason": f"connect failed: {type(e).__name__}"}

    out: dict[str, Any] = {"available": True}
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT COUNT(*) AS n FROM pncp_supplier_contracts")
        out["contracts_total"] = int((cur.fetchone() or {}).get("n") or 0)
        cur.execute(
            """
            SELECT COUNT(*) AS n FROM pncp_supplier_contracts
            WHERE uf = 'SC' OR uf IS NULL
            """
        )
        out["contracts_sc_or_null_uf"] = int((cur.fetchone() or {}).get("n") or 0)
        cur.execute(
            """
            SELECT orgao_nome, orgao_cnpj, COUNT(*) AS n, SUM(valor_total) AS valor_sum
            FROM pncp_supplier_contracts
            WHERE uf = 'SC'
            GROUP BY 1, 2
            ORDER BY n DESC NULLS LAST
            LIMIT %s
            """,
            (limit,),
        )
        out["top_orgaos_sc"] = [dict(r) for r in cur.fetchall()]
        for row in out["top_orgaos_sc"]:
            if row.get("valor_sum") is not None:
                row["valor_sum"] = float(row["valor_sum"])
        cur.execute(
            """
            SELECT fornecedor_nome, fornecedor_cnpj, COUNT(*) AS n, SUM(valor_total) AS valor_sum
            FROM pncp_supplier_contracts
            WHERE uf = 'SC' AND fornecedor_cnpj IS NOT NULL
            GROUP BY 1, 2
            ORDER BY n DESC NULLS LAST
            LIMIT %s
            """,
            (limit,),
        )
        out["top_fornecedores_sc"] = [dict(r) for r in cur.fetchall()]
        for row in out["top_fornecedores_sc"]:
            if row.get("valor_sum") is not None:
                row["valor_sum"] = float(row["valor_sum"])
        try:
            cur.execute("SELECT COUNT(*) AS n FROM pncp_raw_bids WHERE uf = 'SC'")
            out["raw_bids_sc"] = int((cur.fetchone() or {}).get("n") or 0)
        except Exception:  # noqa: BLE001
            out["raw_bids_sc"] = None
        cur.close()
    except Exception as e:  # noqa: BLE001
        out["query_error"] = f"{type(e).__name__}: {e}"
    finally:
        conn.close()
    return out


def build_report(*, dsn: str | None = None) -> dict[str, Any]:
    pilot = _load_json(_PROJECT_ROOT / "output/contracts/pilot-90d-next30d.json") or {}
    metrics = _load_json(_PROJECT_ROOT / "output/coverage/next30d-metrics-final.json") or {}
    freshness = _load_json(_PROJECT_ROOT / "output/readiness/freshness-gate.json") or {}
    coverage_gate = _load_json(_PROJECT_ROOT / "output/coverage/coverage-gate-report.json") or {}

    coverage_pct = metrics.get("editais_crude_pct")
    if coverage_pct is None and isinstance(coverage_gate, dict):
        coverage_pct = coverage_gate.get("editais_crude_pct")

    pilot_status = pilot.get("status") or metrics.get("pilot_status")
    path_proof = pilot.get("path_proof") or {}

    report: dict[str, Any] = {
        "report": "commercial-sample-sc",
        "audience": "Extra Construtora / consultoria B2G SC",
        "generated_at": datetime.now(UTC).isoformat(),
        "confidence": "low_to_medium",
        "coverage": {
            "editais_crude_pct": coverage_pct,
            "covered_200km": metrics.get("covered_200km"),
            "editais_denominator": metrics.get("editais_denominator"),
            "methodology_note": (
                "Cobertura bruta = órgãos/municípios cobertos no recorte 200km "
                "sobre denominador documentado; NÃO é 95% DoD."
            ),
        },
        "freshness": {
            "artifact": "output/readiness/freshness-gate.json",
            "all_critical_fresh": (freshness.get("overall") or {}).get("all_critical_sources_fresh"),
            "failing_sources": (freshness.get("overall") or {}).get("failing_sources"),
            "generated_at": freshness.get("generated_at"),
        },
        "contracts_pilot": {
            "status": pilot_status,
            "go_no_go_3y": pilot.get("go_no_go_3y") or metrics.get("go_no_go_3y"),
            "go_no_go_path": pilot.get("go_no_go_path") or metrics.get("go_no_go_path"),
            "path_proof_status": path_proof.get("status"),
            "path_proof_days": path_proof.get("days"),
            "full_90d": (pilot.get("full_90d_session") or {}).get("status"),
            "totals_path_or_session": pilot.get("totals"),
            "db_snapshot_in_artifact": pilot.get("db"),
        },
        "opportunities": {
            "note": (
                "Lista de abertas exige PNCP editais frescos + ranking; "
                "freshness atual indica fontes críticas sem last_success_at em artefato."
            ),
            "open_sample": [],
            "ranking_available": False,
        },
        "db_sample": _db_sample(dsn),
        "claims_allowed": [
            "Path proof de 1 dia de contratos PNCP foi demonstrado em artefato partial.",
            "Cobertura bruta de editais permanece da ordem de poucos pontos percentuais (~4.76%).",
            "Existem dezenas de milhares de contratos persistidos por runs parciais/cumulativos.",
            "CKAN Dados SC e CIGA expõem Action API pública sem token (descoberta em sessão).",
        ],
        "claims_forbidden": [
            "Universo completo de editais SC coberto",
            "Piloto nacional 90d de contratos concluído",
            "GO para backfill 3 anos não supervisionado",
            "VPS operacional",
            "CONTRATOS_95 / editais 95%",
        ],
        "disclaimers": _disclaimer(
            float(coverage_pct) if coverage_pct is not None else None,
            str(pilot_status) if pilot_status else None,
            freshness if isinstance(freshness, dict) else None,
        ),
    }
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="Commercial sample SC report (honest)")
    ap.add_argument(
        "--output",
        default="output/reports/commercial-sample-sc.json",
        help="Output JSON path",
    )
    ap.add_argument(
        "--dsn",
        default=os.getenv("DATABASE_URL") or os.getenv("LOCAL_DATALAKE_DSN"),
        help="Optional PostgreSQL DSN for live sample",
    )
    args = ap.parse_args()
    report = build_report(dsn=args.dsn)
    out = Path(args.output)
    if not out.is_absolute():
        out = _PROJECT_ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps({"wrote": str(out), "confidence": report["confidence"], "disclaimers": len(report["disclaimers"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

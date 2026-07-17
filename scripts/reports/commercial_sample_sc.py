#!/usr/bin/env python3
"""Commercial sample report for Extra Construtora (SC) — artifact-first.

Builds an honest advisory sample from committed artifacts, session runs
(Compras SC, DOM/CIGA, DOE), coverage metrics, reconciliation and optional DB.
Never hides low coverage or stale freshness. Does not invent GO for 3y.

Usage:
  PYTHONPATH=. python3 -m scripts.reports.commercial_sample_sc \\
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

from scripts.reports.commercial_b2g_session import (  # noqa: E402
    build_session_report,
    write_all,
    write_csv_bundle,
    write_html,
    write_xlsx,
)


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


def build_report(*, dsn: str | None = None, include_session: bool = True) -> dict[str, Any]:
    pilot = _load_json(_PROJECT_ROOT / "output/contracts/pilot-90d-next30d.json") or {}
    metrics = _load_json(_PROJECT_ROOT / "output/coverage/next30d-metrics-final.json") or {}
    freshness = _load_json(_PROJECT_ROOT / "output/readiness/freshness-gate.json") or {}
    coverage_gate = _load_json(_PROJECT_ROOT / "output/coverage/coverage-gate-report.json") or {}

    coverage_pct = metrics.get("editais_crude_pct")
    if coverage_pct is None and isinstance(coverage_gate, dict):
        coverage_pct = coverage_gate.get("editais_crude_pct")

    pilot_status = pilot.get("status") or metrics.get("pilot_status")
    path_proof = pilot.get("path_proof") or {}

    session: dict[str, Any] | None = None
    if include_session:
        try:
            session = build_session_report(dsn=dsn)
        except Exception as e:  # noqa: BLE001 — sample must still build without session
            session = {"available": False, "error": f"{type(e).__name__}: {e}"}

    open_sample: list[dict[str, Any]] = []
    ranking_available = False
    opp_note = (
        "Lista de abertas exige PNCP editais frescos + ranking; "
        "freshness atual indica fontes críticas sem last_success_at em artefato."
    )
    if isinstance(session, dict) and session.get("report") == "commercial-b2g-session-sc":
        open_sample = list(session.get("opportunities_open") or [])
        ranking_available = bool((session.get("org_ranking") or {}).get("available"))
        sc = session.get("sc_compras") or {}
        if sc.get("available"):
            opp_note = (
                f"Amostra Compras SC mode={sc.get('mode')} live_fetch={sc.get('live_fetch')} "
                f"run_id={sc.get('run_id')}; open={len(open_sample)}. "
                "Não é universo completo do portal."
            )

    base_disclaimers = _disclaimer(
        float(coverage_pct) if coverage_pct is not None else None,
        str(pilot_status) if pilot_status else None,
        freshness if isinstance(freshness, dict) else None,
    )
    # Merge session disclaimers (dedupe)
    merged_disc: list[str] = list(base_disclaimers)
    if isinstance(session, dict):
        for d in session.get("disclaimers") or []:
            if d not in merged_disc:
                merged_disc.append(d)

    confidence = "low_to_medium"
    if isinstance(session, dict) and session.get("confidence"):
        confidence = str(session["confidence"])

    report: dict[str, Any] = {
        "report": "commercial-sample-sc",
        "audience": "Extra Construtora / consultoria B2G SC",
        "generated_at": datetime.now(UTC).isoformat(),
        "confidence": confidence,
        "run_id": (session or {}).get("run_id") if isinstance(session, dict) else None,
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
            "note": opp_note,
            "open_sample": open_sample,
            "recently_published": (session or {}).get("opportunities_recent")
            if isinstance(session, dict)
            else [],
            "ranking_available": ranking_available,
            "status_counts": (
                ((session or {}).get("sc_compras") or {}).get("opportunities") or {}
            ).get("status_counts")
            if isinstance(session, dict)
            else {},
            "buyer_orgs_top": (
                ((session or {}).get("sc_compras") or {}).get("opportunities") or {}
            ).get("buyer_orgs_top")
            if isinstance(session, dict)
            else [],
            "modalities": (
                ((session or {}).get("sc_compras") or {}).get("opportunities") or {}
            ).get("modalities")
            if isinstance(session, dict)
            else [],
            "gaps_in_sample": (
                ((session or {}).get("sc_compras") or {}).get("opportunities") or {}
            ).get("gaps_in_sample")
            if isinstance(session, dict)
            else {},
        },
        "session_sources": {
            "sc_compras": {
                "run_id": ((session or {}).get("sc_compras") or {}).get("run_id"),
                "live_fetch": ((session or {}).get("sc_compras") or {}).get("live_fetch"),
                "mode": ((session or {}).get("sc_compras") or {}).get("mode"),
                "available": ((session or {}).get("sc_compras") or {}).get("available"),
            }
            if isinstance(session, dict)
            else None,
            "dom_ciga": {
                "run_id": ((session or {}).get("dom_ciga") or {}).get("run_id"),
                "live_fetch": ((session or {}).get("dom_ciga") or {}).get("live_fetch"),
                "records_loaded": ((session or {}).get("dom_ciga") or {}).get("records_loaded"),
                "procurement_like_count": ((session or {}).get("dom_ciga") or {}).get(
                    "procurement_like_count"
                ),
                "act_category_counts": ((session or {}).get("dom_ciga") or {}).get(
                    "act_category_counts"
                ),
            }
            if isinstance(session, dict)
            else None,
            "doe_sc": {
                "run_id": ((session or {}).get("doe_sc") or {}).get("run_id"),
                "live_fetch": ((session or {}).get("doe_sc") or {}).get("live_fetch"),
                "act_categories": ((session or {}).get("doe_sc") or {}).get("act_categories"),
                "mode": ((session or {}).get("doe_sc") or {}).get("mode"),
            }
            if isinstance(session, dict)
            else None,
            "reconciliation": (session or {}).get("reconciliation")
            if isinstance(session, dict)
            else None,
            "live_fetch_summary": (session or {}).get("live_fetch_summary")
            if isinstance(session, dict)
            else None,
            "evidence_chain": (session or {}).get("evidence_chain")
            if isinstance(session, dict)
            else None,
            "key_findings": (session or {}).get("key_findings") if isinstance(session, dict) else None,
            "status_changes": (session or {}).get("status_changes")
            if isinstance(session, dict)
            else None,
            "recent_dom_acts": ((session or {}).get("dom_ciga") or {}).get("recent_procurement_acts")
            if isinstance(session, dict)
            else [],
            "recent_doe_acts": ((session or {}).get("doe_sc") or {}).get("sample_recent_acts")
            if isinstance(session, dict)
            else [],
            "org_ranking": (session or {}).get("org_ranking") if isinstance(session, dict) else None,
            "winning_suppliers": ((session or {}).get("db_sample") or {}).get("winning_suppliers_sc")
            if isinstance(session, dict)
            else None,
            "similar_contracts": ((session or {}).get("db_sample") or {}).get("similar_contracts_sc")
            if isinstance(session, dict)
            else None,
        },
        "db_sample": _db_sample(dsn)
        if not (isinstance(session, dict) and (session.get("db_sample") or {}).get("available"))
        else {
            "available": True,
            "contracts_total": (session.get("db_sample") or {}).get("contracts_total"),
            "contracts_sc_or_null_uf": (session.get("db_sample") or {}).get("contracts_sc"),
            "top_orgaos_sc": (session.get("db_sample") or {}).get("top_orgaos_sc"),
            "top_fornecedores_sc": (session.get("db_sample") or {}).get("winning_suppliers_sc"),
            "raw_bids_sc": (session.get("db_sample") or {}).get("raw_bids_sc"),
            "similar_contracts_sc": (session.get("db_sample") or {}).get("similar_contracts_sc"),
            "live_fetch": (session.get("db_sample") or {}).get("live_fetch"),
        },
        "claims_allowed": [
            "Path proof de 1 dia de contratos PNCP foi demonstrado em artefato partial.",
            "Cobertura bruta de editais permanece da ordem de poucos pontos percentuais (~4.76%).",
            "Existem dezenas de milhares de contratos persistidos por runs parciais/cumulativos.",
            "CKAN Dados SC e CIGA expõem Action API pública sem token (descoberta em sessão).",
            "Amostra Compras SC / DOM / DOE desta sessão com live_fetch e gaps documentados.",
        ],
        "claims_forbidden": [
            "Universo completo de editais SC coberto",
            "Piloto nacional 90d de contratos concluído",
            "GO para backfill 3 anos não supervisionado",
            "VPS operacional",
            "CONTRATOS_95 / editais 95%",
            "Smoke DOM/DOE como cobertura estadual completa",
        ],
        "disclaimers": merged_disc,
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
    ap.add_argument(
        "--no-session",
        action="store_true",
        help="Skip loading session artifacts (legacy sample only)",
    )
    ap.add_argument(
        "--also-session-bundle",
        action="store_true",
        default=True,
        help="Also write commercial-b2g-session-sc.{json,csv,xlsx,html} (default: on)",
    )
    ap.add_argument(
        "--no-session-bundle",
        action="store_true",
        help="Do not write the multi-format session bundle",
    )
    ap.add_argument(
        "--formats",
        default="json,csv,xlsx,html",
        help="Comma list of formats for the sample output side-car (csv,xlsx,html)",
    )
    args = ap.parse_args()
    report = build_report(dsn=args.dsn, include_session=not args.no_session)
    out = Path(args.output)
    if not out.is_absolute():
        out = _PROJECT_ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    extras: dict[str, str] = {}
    formats = {f.strip().lower() for f in args.formats.split(",") if f.strip()}
    stem = out.with_suffix("")
    # Build a session-shaped view for multi-format writers when session present
    session_view: dict[str, Any] | None = None
    if not args.no_session:
        try:
            session_view = build_session_report(dsn=args.dsn)
        except Exception:  # noqa: BLE001
            session_view = None

    if session_view and "csv" in formats:
        extras["csv"] = str(write_csv_bundle(session_view, Path(str(stem) + ".csv")))
    if session_view and "xlsx" in formats:
        xp = write_xlsx(session_view, Path(str(stem) + ".xlsx"))
        if xp:
            extras["xlsx"] = str(xp)
    if session_view and "html" in formats:
        extras["html"] = str(write_html(session_view, Path(str(stem) + ".html")))

    bundle_paths: dict[str, str] = {}
    if not args.no_session_bundle and args.also_session_bundle and session_view:
        bundle_paths = write_all(
            session_view,
            output_dir=out.parent,
            basename="commercial-b2g-session-sc",
        )

    print(
        json.dumps(
            {
                "wrote": str(out),
                "extras": extras,
                "session_bundle": bundle_paths,
                "run_id": report.get("run_id"),
                "confidence": report["confidence"],
                "disclaimers": len(report["disclaimers"]),
                "open_sample": len((report.get("opportunities") or {}).get("open_sample") or []),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

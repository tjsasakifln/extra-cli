#!/usr/bin/env python3
"""Classify the national PNCP contracts backfill from a live checkpoint.

Drives the shipped window planner in ``run_contracts_90d_pilot`` — does not
re-implement date windows and does not start a crawler.

Verdict tokens (exactly one):

* ``BACKFILL_COMPLETO``
* ``BACKFILL_PARCIAL``
* ``BACKFILL_INCOMPLETO``

The planned set is campaign ``hc_closure_3y`` (2023-07-20 → 2026-07-23).
A later 2025+ canary (issue #249) is reported separately and never upgrades
or silently replaces this planned set.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from scripts.crawl.contracts_crawler import CONTRACTS_WINDOW_DAYS
from scripts.crawl.run_contracts_90d_pilot import (
    count_planned_windows,
    iter_planned_window_keys,
)

VERDICT_COMPLETO = "BACKFILL_COMPLETO"
VERDICT_PARCIAL = "BACKFILL_PARCIAL"
VERDICT_INCOMPLETO = "BACKFILL_INCOMPLETO"
VALID_VERDICTS = frozenset({VERDICT_COMPLETO, VERDICT_PARCIAL, VERDICT_INCOMPLETO})

HC_CLOSURE_START = date(2023, 7, 20)
HC_CLOSURE_END = date(2026, 7, 23)
INCREMENTAL_SLA_HOURS = 168
MIN_NATIONAL_ROWS = 1_000_000
PARCIAL_MIN_COMPLETED_RATIO = 0.80
CAMPAIGN_ID = "hc_closure_3y"

STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_BLOCKED = "blocked"
STATUS_NEVER_RAN = "never_ran"


def parse_iso_date(value: str) -> date:
    return date.fromisoformat(str(value)[:10])


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} is not a JSON object")
    return payload


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def current_failed_windows(checkpoint: dict[str, Any]) -> set[str]:
    """Windows currently failed — not the cumulative ``total_windows_failed`` counter."""
    completed = {str(k) for k in (checkpoint.get("completed_windows") or [])}
    failed: set[str] = set()
    listed = checkpoint.get("failed_windows") or []
    if isinstance(listed, list):
        failed.update(str(k) for k in listed)
    windows = checkpoint.get("windows")
    if isinstance(windows, list):
        for item in windows:
            if not isinstance(item, dict):
                continue
            key = str(item.get("window_key") or item.get("key") or "")
            status = str(item.get("status") or "").lower()
            if key and status == STATUS_FAILED:
                failed.add(key)
    results = checkpoint.get("window_results")
    if isinstance(results, dict):
        for key, item in results.items():
            if isinstance(item, dict) and str(item.get("terminal") or "").upper() == "FAILED":
                failed.add(str(key))
    return failed - completed


def current_blocked_windows(checkpoint: dict[str, Any]) -> set[str]:
    completed = {str(k) for k in (checkpoint.get("completed_windows") or [])}
    blocked: set[str] = set()
    listed = checkpoint.get("blocked_windows") or []
    if isinstance(listed, list):
        blocked.update(str(k) for k in listed)
    return blocked - completed


def build_window_matrix(
    checkpoint: dict[str, Any],
    *,
    start: date = HC_CLOSURE_START,
    end: date = HC_CLOSURE_END,
    window_days: int = CONTRACTS_WINDOW_DAYS,
) -> dict[str, Any]:
    planned = iter_planned_window_keys(start, end, window_days)
    completed = {str(k) for k in (checkpoint.get("completed_windows") or [])}
    failed = current_failed_windows(checkpoint)
    blocked = current_blocked_windows(checkpoint)
    rows: list[dict[str, Any]] = []
    for key in planned:
        if key in completed:
            status = STATUS_COMPLETED
        elif key in failed:
            status = STATUS_FAILED
        elif key in blocked:
            status = STATUS_BLOCKED
        else:
            status = STATUS_NEVER_RAN
        rows.append({"window_key": key, "status": status, "in_planned_set": True})
    never_ran = [row["window_key"] for row in rows if row["status"] == STATUS_NEVER_RAN]
    failed_in_set = [row["window_key"] for row in rows if row["status"] == STATUS_FAILED]
    blocked_in_set = [row["window_key"] for row in rows if row["status"] == STATUS_BLOCKED]
    completed_in_set = [row["window_key"] for row in rows if row["status"] == STATUS_COMPLETED]
    return {
        "campaign": CAMPAIGN_ID,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "window_days": window_days,
        "planned_windows": planned,
        "planned_count": count_planned_windows(start, end, window_days),
        "completed_in_set": completed_in_set,
        "failed_in_set": failed_in_set,
        "blocked_in_set": blocked_in_set,
        "never_ran": never_ran,
        "cumulative_windows_failed_counter": checkpoint.get("total_windows_failed"),
        "last_error": checkpoint.get("last_error"),
        "rows": rows,
    }


def _lake_span_covers_planned(lake: dict[str, Any] | None, start: date, end: date) -> bool:
    if not lake:
        return False
    try:
        min_pub = parse_iso_date(str(lake["min_data_publicacao"]))
        max_pub = parse_iso_date(str(lake["max_data_publicacao"]))
    except (KeyError, TypeError, ValueError):
        return False
    return min_pub <= start and max_pub >= end


def _incremental_within_sla(lake: dict[str, Any] | None) -> bool | None:
    if not lake:
        return None
    incremental = lake.get("incremental")
    if not isinstance(incremental, dict):
        return None
    if "within_sla" in incremental:
        return bool(incremental["within_sla"])
    age = incremental.get("age_hours")
    sla = float(incremental.get("sla_hours") or INCREMENTAL_SLA_HOURS)
    if age is None:
        return None
    return float(age) <= sla


def classify_verdict(
    matrix: dict[str, Any],
    lake: dict[str, Any] | None = None,
    *,
    start: date = HC_CLOSURE_START,
    end: date = HC_CLOSURE_END,
) -> str:
    planned = int(matrix["planned_count"])
    completed_n = len(matrix["completed_in_set"])
    failed_n = len(matrix["failed_in_set"])
    blocked_n = len(matrix["blocked_in_set"])
    never_n = len(matrix["never_ran"])
    holes = failed_n + blocked_n + never_n
    count_all = int((lake or {}).get("count_all") or 0)
    span_ok = _lake_span_covers_planned(lake, start, end) if lake else True
    volume_ok = count_all >= MIN_NATIONAL_ROWS if lake else True
    incremental_ok = _incremental_within_sla(lake)
    planned_complete = planned > 0 and completed_n == planned and holes == 0
    if planned_complete and span_ok and volume_ok and incremental_ok is not False:
        return VERDICT_COMPLETO
    if planned_complete:
        return VERDICT_PARCIAL
    if planned > 0 and completed_n / planned >= PARCIAL_MIN_COMPLETED_RATIO and holes > 0:
        return VERDICT_PARCIAL
    return VERDICT_INCOMPLETO


def build_answers(matrix: dict[str, Any], lake: dict[str, Any] | None, verdict: str) -> dict[str, Any]:
    lake = lake or {}
    incremental = lake.get("incremental") if isinstance(lake.get("incremental"), dict) else {}
    period = {
        "checkpoint_span": f"{matrix['start']} → {matrix['end']}",
        "lake_min_data_publicacao": lake.get("min_data_publicacao"),
        "lake_max_data_publicacao": lake.get("max_data_publicacao"),
        "ingested_at_min": lake.get("min_ingested_at"),
        "ingested_at_max": lake.get("max_ingested_at"),
    }
    return {
        "q1_backfill_completo_ja_ocorreu": verdict == VERDICT_COMPLETO,
        "q2_periodo": period,
        "q3_contratos_persistidos": lake.get("count_all"),
        "q4_janela_failed_no_planned_set": matrix["failed_in_set"],
        "q5_janela_blocked_no_planned_set": matrix["blocked_in_set"],
        "q6_janela_never_ran_no_planned_set": matrix["never_ran"],
        "q7_incremental_ok": incremental.get("within_sla"),
        "q8_apenas_residuos_administrativos": lake.get("q8_admin_only"),
        "verdict": verdict,
    }


def build_report(
    *,
    checkpoint: dict[str, Any],
    checkpoint_path: str,
    checkpoint_sha256: str,
    lake: dict[str, Any] | None = None,
    canary: dict[str, Any] | None = None,
    comparison: list[dict[str, Any]] | None = None,
    recommended_plan: list[str] | None = None,
    measured_at: str | None = None,
    host_sha: str | None = None,
    laptop_sha: str | None = None,
    reprocess_started: bool = False,
) -> dict[str, Any]:
    matrix = build_window_matrix(checkpoint)
    verdict = classify_verdict(matrix, lake)
    answers = build_answers(matrix, lake, verdict)
    lake = lake or {}
    canary_summary = None
    if canary:
        canary_summary = {
            "completed_windows": len(canary.get("completed_windows") or []),
            "failed_windows": list(canary.get("failed_windows") or []),
            "blocked_windows": list(canary.get("blocked_windows") or []),
            "total_contracts_fetched": canary.get("total_contracts_fetched"),
            "updated_at": canary.get("updated_at"),
            "note": (
                "Campanha posterior (2025-01-01 / #249 / national-2025-canary). "
                "Não é o planned set hc_closure_3y. Falhas de reprocessamento "
                "não reabrem o backfill nacional de 3 anos."
            ),
        }
    return {
        "as_of": measured_at or datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "campaign": CAMPAIGN_ID,
        "verdict": verdict,
        "reprocess_started": reprocess_started,
        "checkpoint": {
            "path": checkpoint_path,
            "sha256": checkpoint_sha256,
            "updated_at": checkpoint.get("updated_at"),
            "total_contracts_fetched": checkpoint.get("total_contracts_fetched"),
            "total_windows_completed": checkpoint.get("total_windows_completed"),
            "planned_windows": checkpoint.get("planned_windows") or checkpoint.get("total_windows_planned"),
            "cumulative_windows_failed_counter": checkpoint.get("total_windows_failed"),
            "last_error": checkpoint.get("last_error"),
            "run_ids": (checkpoint.get("meta") or {}).get("run_ids"),
        },
        "host_sha": host_sha,
        "laptop_sha": laptop_sha,
        "window_matrix": matrix,
        "coverage": {
            "planned": matrix["planned_count"],
            "completed": len(matrix["completed_in_set"]),
            "failed": len(matrix["failed_in_set"]),
            "blocked": len(matrix["blocked_in_set"]),
            "never_ran": len(matrix["never_ran"]),
            "span_days": (parse_iso_date(matrix["end"]) - parse_iso_date(matrix["start"])).days + 1,
            "lake_in_3y_span": lake.get("in_3y_span"),
            "lake_after_backfill_end": lake.get("after_backfill_end"),
        },
        "freshness": lake.get("incremental") or {},
        "contratos_persistidos": {
            "count_all": lake.get("count_all"),
            "count_active": lake.get("count_active"),
            "count_inactive": lake.get("count_inactive"),
            "min_data_publicacao": lake.get("min_data_publicacao"),
            "max_data_publicacao": lake.get("max_data_publicacao"),
            "sources": lake.get("sources"),
        },
        "dataset": {
            "table": "pncp_supplier_contracts",
            "database": "pncp_datalake",
            "host": lake.get("host"),
            "count_all": lake.get("count_all"),
            "min_data_publicacao": lake.get("min_data_publicacao"),
            "max_data_publicacao": lake.get("max_data_publicacao"),
            "checkpoint_sha256": checkpoint_sha256,
            "checkpoint_fetched": checkpoint.get("total_contracts_fetched"),
        },
        "answers": answers,
        "canary_separate_campaign": canary_summary,
        "documented_vs_real": comparison or [],
        "recommended_plan": recommended_plan or [],
        "non_claims": ["LOCAL_READY", "VPS_OPERATIONAL", "PROJECT_DONE"],
    }


def render_html(report: dict[str, Any]) -> str:
    verdict = str(report["verdict"])
    answers = report["answers"]
    matrix = report["window_matrix"]
    rows_html = "".join(
        (
            f"<tr class='{html.escape(row['status'])}'>"
            f"<td>{html.escape(row['window_key'])}</td>"
            f"<td>{html.escape(row['status'])}</td></tr>"
        )
        for row in matrix["rows"]
    )
    comparison_html = "".join(
        (
            "<tr>"
            f"<td>{html.escape(str(item.get('artifact')))}</td>"
            f"<td>{html.escape(str(item.get('documented')))}</td>"
            f"<td>{html.escape(str(item.get('real')))}</td>"
            f"<td>{html.escape(str(item.get('class')))}</td>"
            "</tr>"
        )
        for item in report.get("documented_vs_real") or []
    )
    plan_html = "".join(f"<li>{html.escape(step)}</li>" for step in report.get("recommended_plan") or [])
    q8 = answers.get("q8_apenas_residuos_administrativos")
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8"/>
  <title>Auditoria backfill nacional PNCP — {html.escape(verdict)}</title>
  <style>
    body {{ font-family: ui-sans-serif, system-ui, sans-serif; margin: 2rem; color: #111; }}
    .verdict {{ font-size: 1.6rem; font-weight: 700; padding: .6rem 1rem; border-radius: 8px; }}
    .BACKFILL_COMPLETO {{ background: #d1fae5; }}
    .BACKFILL_PARCIAL {{ background: #fef3c7; }}
    .BACKFILL_INCOMPLETO {{ background: #fee2e2; }}
    table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
    th, td {{ border: 1px solid #d1d5db; padding: .4rem .6rem; text-align: left; font-size: .92rem; }}
    th {{ background: #f3f4f6; }}
    tr.completed td:last-child {{ color: #047857; }}
    tr.failed td:last-child, tr.blocked td:last-child, tr.never_ran td:last-child {{ color: #b91c1c; }}
    code {{ background: #f3f4f6; padding: 0 .25rem; }}
  </style>
</head>
<body>
  <h1>Auditoria do backfill nacional PNCP (contratos)</h1>
  <p class="verdict {html.escape(verdict)}">{html.escape(verdict)}</p>
  <p>Medido em <code>{html.escape(str(report.get("as_of")))}</code> · campanha
     <code>{html.escape(str(report.get("campaign")))}</code>.
     Não declara <code>VPS_OPERATIONAL</code> / <code>LOCAL_READY</code> / <code>PROJECT_DONE</code>.</p>
  <h2>Oito perguntas</h2>
  <ol>
    <li>Backfill completo já ocorreu? <strong>{answers["q1_backfill_completo_ja_ocorreu"]}</strong></li>
    <li>Período? checkpoint {html.escape(str(answers["q2_periodo"]["checkpoint_span"]))} ·
        lake {html.escape(str(answers["q2_periodo"]["lake_min_data_publicacao"]))} →
        {html.escape(str(answers["q2_periodo"]["lake_max_data_publicacao"]))}</li>
    <li>Contratos persistidos? <strong>{html.escape(str(answers["q3_contratos_persistidos"]))}</strong></li>
    <li>Janela FAILED no planned set? <code>{html.escape(str(answers["q4_janela_failed_no_planned_set"]))}</code></li>
    <li>Janela BLOCKED no planned set? <code>{html.escape(str(answers["q5_janela_blocked_no_planned_set"]))}</code></li>
    <li>Janela never-ran no planned set? <code>{
        html.escape(str(answers["q6_janela_never_ran_no_planned_set"]))
    }</code></li>
    <li>Incremental dentro do SLA? <strong>{html.escape(str(answers["q7_incremental_ok"]))}</strong></li>
    <li>Só resíduos administrativos nas issues? <strong>{html.escape(str(q8))}</strong></li>
  </ol>
  <h2>Cobertura / freshness / dataset</h2>
  <pre>{
        html.escape(
            json.dumps(
                {
                    "coverage": report.get("coverage"),
                    "freshness": report.get("freshness"),
                    "dataset": report.get("dataset"),
                    "checkpoint": report.get("checkpoint"),
                    "host_sha": report.get("host_sha"),
                    "reprocess_started": report.get("reprocess_started"),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    }</pre>
  <h2>Matriz de janelas (planned set hc_closure_3y)</h2>
  <table>
    <thead><tr><th>window_key</th><th>status</th></tr></thead>
    <tbody>{rows_html}</tbody>
  </table>
  <h2>Documentado vs real</h2>
  <table>
    <thead><tr><th>artefato</th><th>documentado</th><th>real (VPS 2026-08-16)</th><th>classe</th></tr></thead>
    <tbody>{comparison_html}</tbody>
  </table>
  <h2>Plano recomendado</h2>
  <ol>{plan_html}</ol>
  <h2>Campanha posterior (não decide o veredito 3y)</h2>
  <pre>{html.escape(json.dumps(report.get("canary_separate_campaign"), indent=2, ensure_ascii=False))}</pre>
</body>
</html>
"""


def write_deliverables(report: dict[str, Any], out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "decision.json": json.dumps(
            {
                "verdict": report["verdict"],
                "as_of": report["as_of"],
                "campaign": report["campaign"],
                "reprocess_started": report["reprocess_started"],
                "non_claims": report["non_claims"],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        "window-matrix.json": json.dumps(report["window_matrix"], indent=2, ensure_ascii=False) + "\n",
        "timeline.json": json.dumps(
            {
                "checkpoint_run_ids": report["checkpoint"].get("run_ids"),
                "checkpoint_updated_at": report["checkpoint"].get("updated_at"),
                "lake_ingested_min": report["answers"]["q2_periodo"]["ingested_at_min"],
                "lake_ingested_max": report["answers"]["q2_periodo"]["ingested_at_max"],
                "publication_min": report["contratos_persistidos"].get("min_data_publicacao"),
                "publication_max": report["contratos_persistidos"].get("max_data_publicacao"),
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        "coverage.json": json.dumps(report["coverage"], indent=2, ensure_ascii=False) + "\n",
        "freshness.json": json.dumps(report["freshness"], indent=2, ensure_ascii=False) + "\n",
        "contratos-persistidos.json": json.dumps(report["contratos_persistidos"], indent=2, ensure_ascii=False) + "\n",
        "dataset.json": json.dumps(report["dataset"], indent=2, ensure_ascii=False) + "\n",
        "documented-vs-real.json": json.dumps(report["documented_vs_real"], indent=2, ensure_ascii=False) + "\n",
        "recommended-plan.json": json.dumps(report["recommended_plan"], indent=2, ensure_ascii=False) + "\n",
        "report.json": json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        "report.html": render_html(report),
    }
    written: dict[str, str] = {}
    for name, content in files.items():
        path = out_dir / name
        path.write_text(content, encoding="utf-8")
        written[name] = str(path)
    return written


def _cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--lake", type=Path, default=None)
    parser.add_argument("--canary", type=Path, default=None)
    parser.add_argument("--comparison", type=Path, default=None)
    parser.add_argument("--plan", type=Path, default=None)
    parser.add_argument("--out-dir", required=True, type=Path)
    parser.add_argument("--host-sha", default=None)
    parser.add_argument("--laptop-sha", default=None)
    parser.add_argument("--reprocess-started", action="store_true")
    args = parser.parse_args(argv)
    checkpoint = load_json(args.checkpoint)
    lake = load_json(args.lake) if args.lake else None
    canary = load_json(args.canary) if args.canary else None
    comparison = None
    if args.comparison:
        raw = json.loads(args.comparison.read_text(encoding="utf-8"))
        comparison = raw if isinstance(raw, list) else raw.get("items")
    plan = None
    if args.plan:
        raw_plan = json.loads(args.plan.read_text(encoding="utf-8"))
        plan = raw_plan if isinstance(raw_plan, list) else raw_plan.get("steps")
    report = build_report(
        checkpoint=checkpoint,
        checkpoint_path=str(args.checkpoint),
        checkpoint_sha256=sha256_file(args.checkpoint),
        lake=lake,
        canary=canary,
        comparison=comparison,
        recommended_plan=plan,
        host_sha=args.host_sha,
        laptop_sha=args.laptop_sha,
        reprocess_started=args.reprocess_started,
    )
    write_deliverables(report, args.out_dir)
    print(json.dumps({"verdict": report["verdict"], "out_dir": str(args.out_dir)}))
    return 0 if report["verdict"] in VALID_VERDICTS else 2


if __name__ == "__main__":
    raise SystemExit(_cli())

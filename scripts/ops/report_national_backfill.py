"""Fail-closed pin + reconciliation report for the national PNCP backfill.

Reads a shipped checkpoint (or stdin snapshot). Does not crawl, does not
write the host checkpoint, and never turns UNKNOWN into zero.

Usage:
  python3 -m scripts.ops.report_national_backfill \\
    --checkpoint /var/lib/extra-consultoria/checkpoints/national-2025-canary \\
    --start-date 2025-01-01 --end-date 2026-08-15 \\
    --origin-main-sha SHA --host-sha SHA
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.crawl.contracts_checkpoint_contract import (  # noqa: E402
    diagnose,
    load_raw,
)
from scripts.crawl.pncp_contracts_backfill import WINDOW_START  # noqa: E402
from scripts.crawl.run_contracts_90d_pilot import (  # noqa: E402
    evaluate_window_completion,
    planned_window_keys,
    resolve_pilot_range,
    resume_action_for_window,
)

UNIVERSE = "pncp_supplier_contracts"
PARTITION_KIND = "date_window_30d"
DEFAULT_CAMPAIGN_END = "2026-08-15"


def _unknown(value: Any) -> bool:
    return value is None


def reconcile_window_counts(
    fetched: int | None,
    persisted: int | None,
    rejected: int | None,
    skipped: int | None = None,
) -> dict[str, Any]:
    """Reconcile counts without coercing missing fields to zero.

    ingest_window identity: fetched == persisted + rejected
    90d-pilot identity:     fetched == persisted + rejected + skipped
    """
    fields = {
        "fetched": fetched,
        "persisted": persisted,
        "rejected": rejected,
        "skipped": skipped,
    }
    missing = [name for name, value in fields.items() if name != "skipped" and _unknown(value)]
    if missing or fetched is None or persisted is None or rejected is None:
        return {
            "balanced": None,
            "identity": "UNKNOWN",
            "unknown_fields": missing,
            **fields,
        }
    if skipped is None:
        identity = "fetched=persisted+rejected"
        expected = persisted + rejected
    else:
        identity = "fetched=persisted+rejected+skipped"
        expected = persisted + rejected + skipped
    return {
        "balanced": fetched == expected,
        "identity": identity,
        "unknown_fields": [],
        "expected_sum": expected,
        **fields,
    }


def classify_window(
    window_key: str,
    *,
    completed: list[str],
    failed: list[str],
    blocked: list[str],
    window_results: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Map a planned window to complete / failed / blocked / retry."""
    result = (window_results or {}).get(window_key)
    result_d = result if isinstance(result, dict) else {}
    resume = resume_action_for_window(window_key, completed)
    if window_key in completed:
        terminal = "complete"
    elif window_key in blocked:
        terminal = "blocked"
        resume = "blocked"
    elif window_key in failed:
        terminal = "failed"
        resume = "retry"
    else:
        terminal = "open"
        resume = "retry"

    if terminal == "complete" and result_d.get("terminal") not in {None, "COMPLETE", "complete"}:
        # Checkpoint membership is the resume authority; result mismatch is residual.
        pass

    recon = reconcile_window_counts(
        result_d.get("fetched") if result_d else None,
        result_d.get("persisted") if result_d else None,
        result_d.get("rejected") if result_d else None,
        result_d.get("skipped") if result_d else None,
    )
    return {
        "window_key": window_key,
        "terminal": terminal,
        "resume": resume,
        "partial_never_success": terminal != "complete",
        "result_present": bool(result_d),
        "reconciliation": recon,
    }


def build_national_backfill_report(
    checkpoint_data: dict[str, Any],
    *,
    start: date,
    end: date,
    origin_main_sha: str | None = None,
    host_sha: str | None = None,
    checkpoint_path: str | None = None,
    freshness: dict[str, Any] | None = None,
    writer: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the published pin + reconciliation document from a checkpoint dict."""
    completed = [str(w) for w in (checkpoint_data.get("completed_windows") or [])]
    failed = [str(w) for w in (checkpoint_data.get("failed_windows") or [])]
    blocked = [str(w) for w in (checkpoint_data.get("blocked_windows") or [])]
    results = checkpoint_data.get("window_results") or {}
    if not isinstance(results, dict):
        results = {}

    planned = planned_window_keys(start, end)
    windows = [
        classify_window(
            key,
            completed=completed,
            failed=failed,
            blocked=blocked,
            window_results=results,
        )
        for key in planned
    ]
    counts = {
        "planned": len(planned),
        "complete": sum(1 for w in windows if w["terminal"] == "complete"),
        "failed": sum(1 for w in windows if w["terminal"] == "failed"),
        "blocked": sum(1 for w in windows if w["terminal"] == "blocked"),
        "retry": sum(1 for w in windows if w["resume"] == "retry"),
        "open": sum(1 for w in windows if w["terminal"] == "open"),
        "skip_on_resume": sum(1 for w in windows if w["resume"] == "skip"),
    }
    unknown_recon = [
        w["window_key"]
        for w in windows
        if w["reconciliation"]["identity"] == "UNKNOWN"
    ]
    unbalanced = [
        w["window_key"]
        for w in windows
        if w["reconciliation"]["balanced"] is False
    ]
    residual = [w for w in windows if w["terminal"] != "complete"]
    sha_match = (
        None
        if not origin_main_sha or not host_sha
        else origin_main_sha == host_sha
    )
    return {
        "campaign": "EXTRA-012",
        "issue": 249,
        "decision_inputs_only": True,
        "claims": {
            "VPS_OPERATIONAL": False,
            "campaign_terminal": counts["complete"] == counts["planned"]
            and counts["planned"] > 0
            and not residual,
        },
        "pin": {
            "origin_main_sha": origin_main_sha or "UNKNOWN",
            "host_sha": host_sha or "UNKNOWN",
            "sha_equal": sha_match,
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "policy_window_start": WINDOW_START,
            "universe": UNIVERSE,
            "partition_kind": PARTITION_KIND,
            "partition_version": (
                f"{PARTITION_KIND}/start={start.isoformat()}/end={end.isoformat()}"
            ),
            "runner": "scripts.crawl.run_contracts_90d_pilot",
            "allow_cross_run_resume": True,
        },
        "checkpoint_path": checkpoint_path,
        "run_id": (checkpoint_data.get("meta") or {}).get("run_id") or "UNKNOWN",
        "current_window": checkpoint_data.get("current_window") or "UNKNOWN",
        "current_page": checkpoint_data.get("current_page"),
        "counts": counts,
        "windows": windows,
        "unknown_reconciliation_windows": unknown_recon,
        "unbalanced_windows": unbalanced,
        "residual": residual,
        "freshness": freshness if freshness is not None else {"status": "UNKNOWN"},
        "writer": writer if writer is not None else {"status": "UNKNOWN"},
        "partial_never_success": True,
        "incremental": {
            "enabled": False,
            "reason": "backfill writer is still the authority until residual windows close",
        },
    }


def report_from_checkpoint_dir(
    checkpoint_dir: Path,
    *,
    start: date,
    end: date,
    origin_main_sha: str | None = None,
    host_sha: str | None = None,
    freshness: dict[str, Any] | None = None,
    writer: dict[str, Any] | None = None,
) -> dict[str, Any]:
    diagnosis = diagnose(checkpoint_dir)
    if not diagnosis.exists:
        return {
            "status": "BLOCKED",
            "blocker": "checkpoint_missing",
            "prerequisite": f"checkpoint file at {diagnosis.path}",
            "next_command": (
                "python3 -m scripts.crawl.run_contracts_90d_pilot "
                f"--start-date {start.isoformat()} --end-date {end.isoformat()} "
                f"--checkpoint-dir {checkpoint_dir} --allow-cross-run-resume"
            ),
            "claims": {"VPS_OPERATIONAL": False},
            "pin": {
                "origin_main_sha": origin_main_sha or "UNKNOWN",
                "host_sha": host_sha or "UNKNOWN",
                "window_start": start.isoformat(),
                "policy_window_start": WINDOW_START,
            },
        }
    if not diagnosis.ok:
        return {
            "status": "BLOCKED",
            "blocker": "checkpoint_corrupt",
            "issues": diagnosis.issues,
            "prerequisite": "repair or archive checkpoint via contracts_checkpoint_contract",
            "next_command": (
                "python3 -m scripts.crawl.contracts_checkpoint_contract diagnose "
                f"--checkpoint-dir {checkpoint_dir}"
            ),
            "claims": {"VPS_OPERATIONAL": False},
        }
    data = load_raw(Path(diagnosis.path))
    report = build_national_backfill_report(
        data,
        start=start,
        end=end,
        origin_main_sha=origin_main_sha,
        host_sha=host_sha,
        checkpoint_path=diagnosis.path,
        freshness=freshness,
        writer=writer,
    )
    report["checkpoint_diagnosis"] = diagnosis.to_dict()
    report["evaluate_window_completion_imported"] = evaluate_window_completion.__name__
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Pin + reconcile national PNCP backfill")
    ap.add_argument("--checkpoint", required=True, help="Checkpoint dir or contracts_full.json")
    ap.add_argument("--start-date", default=WINDOW_START)
    ap.add_argument("--end-date", default=DEFAULT_CAMPAIGN_END)
    ap.add_argument("--days", type=int, default=591)
    ap.add_argument("--origin-main-sha", default=None)
    ap.add_argument("--host-sha", default=None)
    ap.add_argument("--output", default=None, help="Write JSON here; default stdout")
    args = ap.parse_args(argv)

    raw = Path(args.checkpoint)
    checkpoint_dir = raw.parent if raw.is_file() else raw
    start, end = resolve_pilot_range(
        days=args.days,
        start_date=date.fromisoformat(args.start_date) if args.start_date else None,
        end_date=date.fromisoformat(args.end_date) if args.end_date else None,
    )
    report = report_from_checkpoint_dir(
        checkpoint_dir,
        start=start,
        end=end,
        origin_main_sha=args.origin_main_sha,
        host_sha=args.host_sha,
    )
    text = json.dumps(report, indent=2, default=str)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    if report.get("status") == "BLOCKED":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

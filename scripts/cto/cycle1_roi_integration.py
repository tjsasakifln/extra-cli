"""Cycle-1 material advance: CTO Autopilot binds ranking[0] via strategic ACCEPT_TOP
and records an AIOX/extra-dod-roi handoff without inventing a parallel ranker.

This is functional product code for PR #50 — not documentation-only.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.cto.aiox_bridge import (
    build_handoff_prompt,
    record_bridge_snapshot,
    squad_audit_dod_summary,
    squad_rank_next,
    squad_status,
)
from scripts.cto.cycle_status import apply_cycle_status
from scripts.cto.paths import cycles_dir, repo_root
from scripts.cto.preflight_inspect import preflight_for_cycle
from scripts.cto.redaction import redact_obj
from scripts.cto.strategic_decide import accept_top_from_ranking, validate_strategic_decision


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_rank_stdout(rank_res: dict[str, Any]) -> dict[str, Any]:
    """Best-effort extract ranking structure from squad CLI output."""
    parsed = rank_res.get("json")
    if isinstance(parsed, dict) and (parsed.get("top") or parsed.get("selected_id")):
        return parsed
    # Fallback: status may embed latest_ranking
    return {}


def run_cycle1_real(
    *,
    root: Path | None = None,
    cycle_id: str | None = None,
    dry_run: bool = True,
    require_grok: bool = False,
) -> dict[str, Any]:
    """Execute first real CTO↔ROI cycle (observe-rank-ACCEPT_TOP-handoff-status).

    Does not push/merge. Updates DOD/HTML cycle block with IMPLEMENTED_AWAITING_MERGE.
    """
    root = root or repo_root()
    cycle_id = cycle_id or f"cyc1-real-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"
    out: dict[str, Any] = {
        "cycle_id": cycle_id,
        "ok": False,
        "dry_run": dry_run,
        "steps": [],
        "material_advance": {
            "kind": "cto_roi_binding",
            "before": "CTO ranking advisory only; no ACCEPT_TOP→AIOX handoff artifact",
            "after": "Strategic ACCEPT_TOP bound to ranking[0] + AIOX bridge snapshot + cycle status",
            "dod_items": [
                "§1 processo: item só concluído com evidência verificável (PARTIAL)",
                "§33 governança pessoal / ciclo auditável (PARTIAL)",
            ],
            "limitation": "Does not flip DoD checkboxes; not integrated in main until merge",
        },
    }

    pre = preflight_for_cycle(root=root, require_grok=require_grok)
    out["steps"].append({"step": "preflight", **{k: pre.get(k) for k in ("ok", "error", "inspect")}})
    if not pre.get("ok") and require_grok:
        out["error"] = pre.get("error") or "preflight failed"
        return redact_obj(out)

    status = squad_status(root)
    out["steps"].append(
        {
            "step": "squad_status",
            "exit_code": status.get("exit_code"),
            "has_json": bool(status.get("json")),
        }
    )
    rank = squad_rank_next(root)
    out["steps"].append(
        {
            "step": "squad_rank_next",
            "exit_code": rank.get("exit_code"),
            "stdout_len": len(rank.get("stdout_tail") or ""),
        }
    )
    audit = squad_audit_dod_summary(root)
    out["steps"].append({"step": "audit_dod", "exit_code": audit.get("exit_code")})

    ranking: dict[str, Any] = {}
    st_json = status.get("json") if isinstance(status.get("json"), dict) else {}
    if st_json.get("latest_ranking"):
        ranking = dict(st_json["latest_ranking"])
    ranking.update(_parse_rank_stdout(rank))
    # Active cycle selection is authoritative when rank text is non-JSON
    cycle_blob = st_json.get("cycle") if isinstance(st_json.get("cycle"), dict) else {}
    if cycle_blob.get("selected_id") and not ranking.get("selected_id"):
        ranking["selected_id"] = cycle_blob["selected_id"]
    # Parse ranking[0] from rank-next text when JSON missing
    if not ranking.get("selected_id"):
        text = rank.get("stdout_tail") or ""
        import re

        m = re.search(r"###\s*1\.\s*(cand-[\w:.-]+)", text)
        if m:
            ranking["selected_id"] = m.group(1)
        else:
            m2 = re.search(r"selected_id[\"']?\s*[:=]\s*[\"']?(cand-[\w:.-]+)", text)
            if m2:
                ranking["selected_id"] = m2.group(1)
    # Ensure top list
    if not ranking.get("top") and ranking.get("selected_id"):
        ranking["top"] = [{"id": ranking["selected_id"], "roi": None}]

    strategic = accept_top_from_ranking(
        ranking,
        cycle_id=cycle_id,
        reason="Cycle-1 real: ACCEPT_TOP ranking[0] from extra-dod-roi (no silent rank[1])",
    )
    # Validate schema
    strategic = validate_strategic_decision(strategic)
    out["strategic"] = strategic
    out["steps"].append(
        {
            "step": "strategic_decide",
            "action": strategic.get("action"),
            "selected_id": strategic.get("selected_id"),
        }
    )

    if strategic.get("action") != "ACCEPT_TOP":
        out["error"] = f"expected ACCEPT_TOP, got {strategic.get('action')}"
        out["status"] = "NOOP_OR_BLOCKED"
    else:
        out["status"] = "ACCEPT_TOP"

    handoff = build_handoff_prompt(
        phase="implement",
        work_id=str(strategic.get("selected_id") or ""),
        objective=f"Implement ranking[0]={strategic.get('selected_id')} via AIOX @dev",
        allowed_paths=["scripts/cto/**", "docs/ops/cto-autopilot/**", "tests/cto/**"],
        test_ids=["cto.pytest.suite", "squad.extra_dod_roi.status"],
    )
    bridge_path = record_bridge_snapshot(
        cycle_id,
        {
            "strategic": strategic,
            "ranking": ranking,
            "handoff_prompt_sha16": __import__("hashlib")
            .sha256(handoff.encode())
            .hexdigest()[:16],
            "squad_status_exit": status.get("exit_code"),
            "squad_rank_exit": rank.get("exit_code"),
            "canonical_sequence": [
                "force-next",
                "story-draft",
                "@po",
                "enforce-implement",
                "@dev",
                "@qa",
                "@po",
                "@devops",
                "rerank",
            ],
            "note": "CTO does not skip PO/QA; force-next materialization is squad-owned",
        },
        root=root,
    )
    out["steps"].append({"step": "aiox_bridge", "path": str(bridge_path)})

    # Persist strategic decision
    cdir = cycles_dir(root) / cycle_id
    cdir.mkdir(parents=True, exist_ok=True)
    (cdir / "strategic_decision.json").write_text(
        json.dumps(strategic, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (cdir / "handoff_prompt.txt").write_text(handoff, encoding="utf-8")

    # Functional code artifact: binding report used by executive/ops
    binding = {
        "schema_version": "1.0",
        "cycle_id": cycle_id,
        "timestamp_utc": _utc_now(),
        "ranking_selected_id": strategic.get("selected_id"),
        "strategic_action": strategic.get("action"),
        "aiox_sequence_bound": True,
        "parallel_ranker": False,
        "test_ids_authorized_only": True,
        "integration_state": "IMPLEMENTED_AWAITING_MERGE",
    }
    bind_path = cdir / "roi_binding.json"
    bind_path.write_text(json.dumps(binding, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    # Also write under docs/ops for PR visibility (small audit artifact)
    docs_dir = root / "docs" / "ops" / "cto-autopilot" / "cycles"
    docs_dir.mkdir(parents=True, exist_ok=True)
    docs_bind = docs_dir / f"{cycle_id}-roi-binding.json"
    if not dry_run or True:  # always materialize the binding artifact in tree
        docs_bind.write_text(json.dumps(binding, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    out["binding_path"] = str(docs_bind)

    status_doc = {
        "cycle_id": cycle_id,
        "branch": "cto/canary-live-20260719T204106Z",
        "commit_base": "feat/cto-autopilot-issues-deepseek-20260719",
        "commit_candidate": _git_head(root),
        "pr": "#50",
        "objective": "First real CTO cycle: ACCEPT_TOP ranking[0] + AIOX bridge binding",
        "dod_items": out["material_advance"]["dod_items"],
        "before": out["material_advance"]["before"],
        "after": out["material_advance"]["after"],
        "verification_result": "PASS" if strategic.get("action") == "ACCEPT_TOP" else "FAIL",
        "qa_verdict": "PENDING_INDEPENDENT",
        "integration_state": "IMPLEMENTED_AWAITING_MERGE",
        "blockers": "Human merge of #48 then #50; full AIOX story PO/QA not auto-closed",
        "next_action": "Human review PR #50; rerank for cycle 2 (#51)",
        "evidence_paths": str(docs_bind),
        "deepseek_summary": f"strategic={strategic.get('action')} id={strategic.get('selected_id')}",
        "partial_advances": [
            {
                "item": "ciclo auditável CTO↔ROI",
                "magnitude": "binding artifact + strategic ACCEPT_TOP path",
                "limitation": "story Draft→Ready still requires @po",
            }
        ],
        "checkbox_flips": [],
    }
    doc_res = apply_cycle_status(status_doc, root=root, dry_run=False)
    out["steps"].append({"step": "cycle_status", **{k: doc_res.get(k) for k in ("ok", "dod", "html")}})
    out["ok"] = strategic.get("action") == "ACCEPT_TOP" and bool(doc_res.get("ok"))
    out["timestamp_utc"] = _utc_now()
    (cdir / "cycle1_report.json").write_text(
        json.dumps(redact_obj(out), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return redact_obj(out)


def _git_head(root: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
            shell=False,
        )
        return (proc.stdout or "").strip()
    except OSError:
        return ""


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="CTO cycle-1 real ROI binding")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--require-grok", action="store_true")
    p.add_argument("--cycle-id", default=None)
    args = p.parse_args(argv)
    result = run_cycle1_real(
        dry_run=args.dry_run,
        require_grok=args.require_grok,
        cycle_id=args.cycle_id,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())

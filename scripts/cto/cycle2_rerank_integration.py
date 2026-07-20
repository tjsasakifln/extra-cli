"""Cycle-2 material advance (PR #51): rerank after cycle-1 is **formally complete**.

Rules (fail-closed):
- No exclude-list as a substitute for completing cycle 1.
- Never pick ranking[1] directly.
- Cycle 2 may ACCEPT_TOP only when fresh rank-next returns a **new** ranking[0]
  because cycle-1's candidate is no longer eligible (story Done + completed).
- If cycle 1 is still open/Draft, return BLOCKED_HUMAN — do not invent selection.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
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

# Story completion evidence for cycle-1 (must be real — never simulated here)
CYCLE1_STORY_ID = "ROI-cand-dyn-slice-cb906bb58392"
CYCLE1_CANDIDATE_ID = "cand-dyn-slice:cb906bb58392"


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


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


def _parse_top_from_rank_text(text: str) -> list[dict[str, Any]]:
    """Parse '### N. cand-... ROI=x' lines from rank-next text output."""
    items: list[dict[str, Any]] = []
    for m in re.finditer(
        r"###\s*(\d+)\.\s*(cand-[\w:.-]+)\s+ROI=([0-9.]+)",
        text or "",
    ):
        items.append(
            {
                "rank": int(m.group(1)),
                "id": m.group(2),
                "roi": float(m.group(3)),
            }
        )
    items.sort(key=lambda x: x["rank"])
    return items


def prove_cycle1_complete(
    root: Path,
    *,
    cycle1_selected_id: str = CYCLE1_CANDIDATE_ID,
    cycle1_story_id: str = CYCLE1_STORY_ID,
) -> dict[str, Any]:
    """Return ok=True only when cycle-1 story is formally Done with PO close + QA.

    Does **not** invent completion. Missing/Draft/InProgress → BLOCKED_HUMAN.
    """
    state_path = root / ".aiox" / "state" / "stories" / f"{cycle1_story_id}.json"
    story_md = root / "docs" / "stories" / f"{cycle1_story_id}.md"
    evidence: dict[str, Any] = {
        "cycle1_selected_id": cycle1_selected_id,
        "story_id": cycle1_story_id,
        "state_path": str(state_path),
        "story_md_exists": story_md.is_file(),
    }
    if not state_path.is_file():
        return {
            "ok": False,
            "blocked_reason": "BLOCKED_HUMAN",
            "who": "@po/@dev/@qa",
            "detail": f"cycle-1 story state missing: {state_path}",
            "next_action": "Complete cycle-1 SDC to Done before cycle-2",
            "evidence": evidence,
        }
    try:
        st = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "ok": False,
            "blocked_reason": "BLOCKED_HUMAN",
            "who": "@devops",
            "detail": f"unreadable story state: {exc}",
            "evidence": evidence,
        }
    evidence.update(
        {
            "status": st.get("status"),
            "po_validated": st.get("po_validated"),
            "po_closed": st.get("po_closed"),
            "qa_verdict": st.get("qa_verdict"),
        }
    )
    status = str(st.get("status") or "")
    qa = str(st.get("qa_verdict") or "").upper()
    po_closed = bool(st.get("po_closed"))
    complete = status == "Done" and po_closed and qa in {"PASS", "CONCERNS", "WAIVED"}
    if not complete:
        return {
            "ok": False,
            "blocked_reason": "BLOCKED_HUMAN",
            "who": "@po then @dev then independent @qa then @po close",
            "detail": (
                f"cycle-1 not complete: status={status!r} po_closed={po_closed} "
                f"qa_verdict={qa!r} — exclude-list must NOT be used as substitute"
            ),
            "command": (
                "Complete AIOX SDC for ROI-cand-dyn-slice-cb906bb58392 until "
                "status=Done, po_closed=true, qa_verdict in PASS|CONCERNS|WAIVED"
            ),
            "artifact": str(state_path),
            "next_action": "Only after cycle-1 Done, re-run rank-next and cycle2-real",
            "evidence": evidence,
        }
    return {"ok": True, "evidence": evidence}


def run_cycle2_real(
    *,
    root: Path | None = None,
    cycle_id: str | None = None,
    cycle1_selected_id: str = CYCLE1_CANDIDATE_ID,
    dry_run: bool = True,
    require_grok: bool = False,
) -> dict[str, Any]:
    root = root or repo_root()
    cycle_id = cycle_id or f"cyc2-real-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"

    out: dict[str, Any] = {
        "cycle_id": cycle_id,
        "ok": False,
        "dry_run": dry_run,
        "steps": [],
        "rerank_required": True,
        "exclude_list_used": False,
        "material_advance": {
            "kind": "cto_roi_rerank_second_slice",
            "before": f"cycle-1 bound {cycle1_selected_id}",
            "after": "fresh rank-next ranking[0] only after cycle-1 formal completion",
            "dod_items": [
                "§29 rastreabilidade (2º slice) — só após ciclo 1 Done",
            ],
            "limitation": "No exclude-list; no ranking[1] shortcut",
        },
    }

    # Gate 1: cycle-1 formally complete (no exclude-list workaround)
    c1 = prove_cycle1_complete(root, cycle1_selected_id=cycle1_selected_id)
    out["steps"].append({"step": "prove_cycle1_complete", **{k: c1.get(k) for k in (
        "ok", "blocked_reason", "who", "detail", "next_action", "command", "artifact"
    ) if k in c1}})
    out["cycle1_proof"] = c1
    if not c1.get("ok"):
        out["status"] = "BLOCKED_HUMAN"
        out["error"] = c1.get("detail") or "cycle1 incomplete"
        out["blocked"] = {
            "who": c1.get("who"),
            "command": c1.get("command"),
            "artifact": c1.get("artifact"),
            "next_action": c1.get("next_action"),
        }
        return redact_obj(out)

    pre = preflight_for_cycle(root=root, require_grok=require_grok)
    out["steps"].append({"step": "preflight", "ok": pre.get("ok")})
    if not pre.get("ok") and require_grok:
        out["error"] = pre.get("error")
        return redact_obj(out)

    # Gate 2: fresh ranking — accept natural ranking[0] only
    rank = squad_rank_next(root)
    status = squad_status(root)
    audit = squad_audit_dod_summary(root)
    out["steps"].append({"step": "rerank", "exit_code": rank.get("exit_code")})
    out["steps"].append({"step": "status", "exit_code": status.get("exit_code")})
    out["steps"].append({"step": "audit_dod", "exit_code": audit.get("exit_code")})

    text = (
        rank.get("stdout_text")
        or rank.get("stdout_head")
        or rank.get("stdout_tail")
        or ""
    )
    top = _parse_top_from_rank_text(text)
    st_json = status.get("json") if isinstance(status.get("json"), dict) else {}
    if not top and st_json.get("latest_ranking"):
        lr = st_json["latest_ranking"]
        top = list(lr.get("top") or [])
        for i, item in enumerate(top):
            item.setdefault("rank", i + 1)

    out["ranking_top"] = top[:5]
    if not top:
        out["error"] = "empty_ranking"
        out["status"] = "BLOCKED_HUMAN"
        return redact_obj(out)

    # Natural ranking[0] only — never ranking[1] shortcut
    chosen = top[0]
    out["chosen"] = chosen
    out["natural_ranking_0"] = chosen.get("id")

    if chosen.get("id") == cycle1_selected_id:
        out["ok"] = False
        out["status"] = "BLOCKED_HUMAN"
        out["error"] = (
            f"ranking[0] is still cycle-1 candidate {cycle1_selected_id}; "
            "completion evidence may not have made it ineligible. Do not use "
            "exclude-list or ranking[1]."
        )
        out["blocked"] = {
            "who": "@sm/@po (mark cycle-1 work completed in ranker filters)",
            "command": "python3 squads/extra-dod-roi/scripts/cli.py rank-next",
            "artifact": "rank-next output with new ranking[0]",
            "next_action": "Ensure cycle-1 candidate is COMPLETED in ROI state, then re-rank",
        }
        return redact_obj(out)

    ranking = {
        "selected_id": chosen["id"],
        "top": [{"id": chosen["id"], "roi": chosen.get("roi")}],
    }
    strategic = accept_top_from_ranking(
        ranking,
        cycle_id=cycle_id,
        reason=(
            f"Cycle-2: ACCEPT_TOP natural ranking[0]={chosen['id']} "
            f"after cycle-1 {cycle1_selected_id} completed (no exclude-list)"
        ),
    )
    strategic = validate_strategic_decision(strategic)
    out["strategic"] = strategic
    out["status"] = strategic.get("action")

    cdir = cycles_dir(root) / cycle_id
    cdir.mkdir(parents=True, exist_ok=True)
    chain_payload = {
        "cycle_id": cycle_id,
        "parent_cycle_selected": cycle1_selected_id,
        "selected_id": chosen.get("id"),
        "exclude_list_used": False,
        "natural_ranking_0": True,
        "ranking_top_ids": [t.get("id") for t in top[:5]],
        "timestamp_utc": _utc_now(),
        "head": _git_head(root),
        "cycle1_proof": c1.get("evidence"),
    }
    chain_bytes = json.dumps(chain_payload, sort_keys=True, default=str).encode()
    chain_hash = hashlib.sha256(chain_bytes).hexdigest()
    chain_doc = {**chain_payload, "chain_sha256": chain_hash, "schema_version": "1.0"}
    (cdir / "evidence_chain.json").write_text(
        json.dumps(chain_doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    docs_dir = root / "docs" / "ops" / "cto-autopilot" / "cycles"
    docs_dir.mkdir(parents=True, exist_ok=True)
    docs_path = docs_dir / f"{cycle_id}-evidence-chain.json"
    docs_path.write_text(
        json.dumps(chain_doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    out["evidence_chain_path"] = str(docs_path)
    out["steps"].append({"step": "evidence_chain", "sha256": chain_hash})

    handoff = build_handoff_prompt(
        phase="implement",
        work_id=str(chosen.get("id") or ""),
        objective=f"Cycle-2 implement {chosen.get('id')} after natural rerank",
        allowed_paths=[
            "scripts/cto/**",
            "docs/ops/cto-autopilot/**",
            "tests/cto/**",
        ],
        test_ids=["cto.pytest.suite"],
    )
    record_bridge_snapshot(
        cycle_id,
        {
            "strategic": out.get("strategic"),
            "exclude_list_used": False,
            "chosen": chosen,
            "handoff_prompt_sha16": hashlib.sha256(handoff.encode()).hexdigest()[:16],
            "parent_cycle": cycle1_selected_id,
            "note": "Natural ranking[0] only after cycle-1 Done; no exclude-list",
        },
        root=root,
    )
    (cdir / "handoff_prompt.txt").write_text(handoff, encoding="utf-8")
    if out.get("strategic"):
        (cdir / "strategic_decision.json").write_text(
            json.dumps(out["strategic"], indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    ok = (out.get("strategic") or {}).get("action") == "ACCEPT_TOP"
    out["ok"] = ok

    status_doc = {
        "cycle_id": cycle_id,
        "branch": "cto/canary-live-20260719T215031Z",
        "commit_base": "cto/canary-live-20260719T204106Z",
        "commit_candidate": _git_head(root),
        "pr": "#51",
        "objective": "Second real CTO cycle after natural rerank (cycle-1 Done)",
        "dod_items": out["material_advance"]["dod_items"],
        "before": out["material_advance"]["before"],
        "after": out["material_advance"]["after"] + f" selected={chosen.get('id')}",
        "verification_result": "PASS" if ok else "FAIL",
        "qa_verdict": "PENDING_INDEPENDENT",
        "integration_state": "IMPLEMENTED_AWAITING_MERGE" if ok else "BLOCKED_HUMAN",
        "blockers": "Independent QA; human merge of stack",
        "next_action": "Human review #48/#50/#51 after cycle-1 Done",
        "evidence_paths": str(docs_path),
        "deepseek_summary": f"natural ranking[0] ACCEPT_TOP {chosen.get('id')}",
        "partial_advances": [],
        "checkbox_flips": [],
    }
    doc_res = apply_cycle_status(status_doc, root=root, dry_run=False)
    out["steps"].append({"step": "cycle_status", "ok": doc_res.get("ok")})
    out["timestamp_utc"] = _utc_now()

    # Material product advance: reconstruct evidence package (§29)
    try:
        from scripts.ops.evidence_reconstruct import reconstruct_from_artifacts
        recon = reconstruct_from_artifacts(root=root)
        out["steps"].append({
            "step": "evidence_reconstruct",
            "status": recon.get("status"),
            "output_path": recon.get("output_path"),
            "n_verified": len(recon.get("verified_artifacts") or []),
        })
        out["evidence_reconstruct"] = {
            "status": recon.get("status"),
            "missing": recon.get("missing"),
            "dod_partial": recon.get("dod_partial"),
        }
        # copy summary into docs/ops cycles
        docs_dir = root / "docs" / "ops" / "cto-autopilot" / "cycles"
        docs_dir.mkdir(parents=True, exist_ok=True)
        (docs_dir / f"{cycle_id}-reconstruct.json").write_text(
            __import__("json").dumps({
                "status": recon.get("status"),
                "verified": recon.get("verified_artifacts"),
                "missing": recon.get("missing"),
                "dod_partial": recon.get("dod_partial"),
            }, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception as exc:
        out["steps"].append({"step": "evidence_reconstruct", "error": str(exc)})

    (cdir / "cycle2_report.json").write_text(
        json.dumps(redact_obj(out), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return redact_obj(out)


def main(argv: list[str] | None = None) -> int:
    import argparse

    p = argparse.ArgumentParser(description="CTO cycle-2 real after natural rerank")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--require-grok", action="store_true")
    p.add_argument("--cycle-id", default=None)
    p.add_argument("--cycle1-selected-id", default=CYCLE1_CANDIDATE_ID)
    args = p.parse_args(argv)
    result = run_cycle2_real(
        dry_run=args.dry_run,
        require_grok=args.require_grok,
        cycle_id=args.cycle_id,
        cycle1_selected_id=args.cycle1_selected_id,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

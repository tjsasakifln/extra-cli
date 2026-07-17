#!/usr/bin/env python3
"""FOOL-PROOF entry: inevitably select ranking[0] and bind AIOX sequence.

Only supported way to start write-work via extra-dod-roi:

1. Acquire cycle lock
2. Re-rank (fresh truth)
3. Abort cleanly if NO_UNLOCKED
4. Build execution card for ranking[0] ONLY
5. Advance cycle state machine
6. Materialize AIOX story Draft + state file
7. Print irrevocable next steps (@po -> @dev -> @qa -> @po -> @devops)
8. Does NOT implement code (blocked until STORY_READY after @po)

Usage:
  python squads/extra-dod-roi/scripts/force_next.py
  python squads/extra-dod-roi/scripts/cli.py force-next
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
SQUAD_DIR = SCRIPT_DIR.parent
REPO = SQUAD_DIR.parent.parent

sys.path.insert(0, str(SCRIPT_DIR))
from cycle_state import advance, new_cycle, save_cycle, utcnow  # noqa: E402
from rank_next_cli import run_rank_next  # noqa: E402


def run(cmd: list[str], *, quiet: bool = False) -> int:
    if quiet:
        return subprocess.call(
            cmd,
            cwd=str(REPO),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    return subprocess.call(cmd, cwd=str(REPO))


def build_card(
    selected: dict[str, Any], rank: dict[str, Any], cycle_id: str
) -> dict[str, Any]:
    return {
        "version": "1.0.0",
        "card_id": f"card-{selected['id']}-{cycle_id}",
        "cycle_id": cycle_id,
        "created_at": utcnow(),
        "candidate_id": selected["id"],
        "title": selected.get("title"),
        "status": "READY_FOR_STORY",
        "foolproof": True,
        "selection_rule": "ranking[0] only — non-negotiable",
        "roi": selected.get("roi"),
        "roi_dimensions": {
            "value": selected.get("value"),
            "cost": selected.get("cost"),
        },
        "roi_justification": selected.get("justification"),
        "dod_refs": selected.get("dod_refs"),
        "problem": selected.get("justification"),
        "evidence": rank.get("divergences"),
        "why_unlocked": selected.get("why_unlocked"),
        "alternatives_discarded": rank.get("discarded_attractive"),
        "planned_files": selected.get("planned_files"),
        "risks": selected.get("risks"),
        "dependencies": selected.get("dependencies"),
        "acceptance_criteria": selected.get("acceptance_criteria"),
        "test_commands": selected.get("test_commands"),
        "rollback": (
            "Revert feature branch commits; never update DoD on failure; no merge."
        ),
        "allowed_claims": (rank.get("dod_summary") or {}).get("allowed_claims") or [],
        "forbidden_claims": (rank.get("dod_summary") or {}).get("forbidden_claims")
        or [],
        "agents": {
            "orchestrator": "roi-orchestrator",
            "implementer": "delivery-engineer / @dev",
            "qa": "adversarial-qa-auditor / @qa",
            "po": "@po",
            "sm": "@sm (draft materialized)",
            "devops": "evidence-release-steward / @devops",
        },
        "aiox_sequence": [
            "STORY_DRAFT (done by force-next)",
            "STORY_READY (@po validate — MANDATORY)",
            "IMPLEMENTING (@dev on non-main branch — only this candidate)",
            "IN_REVIEW (@dev handoff)",
            "QA (@qa independent — MANDATORY)",
            "PO_CLOSE (@po — MANDATORY)",
            "PUBLISH (@devops draft PR — no auto-merge)",
            "RERANK (force-next again)",
        ],
        "handoff_plan": (
            "After story Draft: stop for @po. After Ready: @dev only. "
            "After InReview: @qa only. Never self-QA."
        ),
    }


def print_banner(payload: dict[str, Any]) -> None:
    lines = [
        "",
        "=" * 72,
        "extra-dod-roi :: FORCE-NEXT (FOOL-PROOF / AIOX-BOUND)",
        "=" * 72,
        f"cycle_id:     {payload.get('cycle_id')}",
        f"selected_id:  {payload.get('selected_id')}",
        f"ROI:          {payload.get('roi')}",
        f"story_id:     {payload.get('story_id')}",
        f"story_file:   {payload.get('story_file')}",
        f"phase:        {payload.get('phase')}",
        f"outcome:      {payload.get('outcome')}",
        "",
        "INEVITABLE NEXT STEPS (no skipping):",
    ]
    for i, step in enumerate(payload.get("mandatory_steps") or [], 1):
        lines.append(f"  {i}. {step}")
    lines.extend(
        [
            "",
            "HARD RULES:",
            "  - Only ranking[0] may be implemented this cycle",
            "  - @po must set Ready before any product code",
            "  - @qa must be independent of @dev",
            "  - DoD checkboxes only after QA PASS/CONCERNS/WAIVED + evidence",
            "  - @devops only for push; draft PR never auto-merged",
            "  - On completion: run force-next again (RERANK)",
            "=" * 72,
            "",
        ]
    )
    print("\n".join(lines))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Fool-proof force-next ROI cycle binder")
    p.add_argument("--fetch", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument(
        "--skip-lock",
        action="store_true",
        help="Dangerous; default acquires lock",
    )
    args = p.parse_args(argv)

    if not args.skip_lock:
        rc = run(
            [
                sys.executable,
                str(SCRIPT_DIR / "cycle_lock.py"),
                "acquire",
                f"--squad={SQUAD_DIR}",
                "--owner=force-next",
            ],
            quiet=args.json,
        )
        if rc != 0:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": "LOCK_HELD",
                        "hint": "cycle_lock.py status/release if stale",
                    }
                ),
                file=sys.stderr,
            )
            return 2

    rank = run_rank_next(REPO, top_n=5, write_state=True, fetch=args.fetch)
    selected = rank.get("selected")
    if not selected:
        cycle = new_cycle()
        cycle["phase"] = "DONE"
        cycle["status"] = "completed"
        cycle["outcome"] = "NO_UNLOCKED_WORK"
        cycle["abort"] = None
        save_cycle(cycle)
        out = {
            "ok": True,
            "outcome": "NO_UNLOCKED_WORK",
            "blockers": rank.get("blockers"),
            "divergences": rank.get("divergences"),
            "message": "No unlocked work. Do not invent tasks. Resolve blockers or wait.",
            "cycle_id": cycle["cycle_id"],
            "selected_id": None,
            "phase": "DONE",
            "mandatory_steps": [
                "Review blockers: python squads/extra-dod-roi/scripts/cli.py show-blockers",
                "Do NOT implement lower-priority or blocked work",
            ],
        }
        if args.json:
            print(json.dumps(out, indent=2, ensure_ascii=False))
        else:
            print_banner(out)
            print(json.dumps(out, indent=2, ensure_ascii=False))
        if not args.skip_lock:
            run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "cycle_lock.py"),
                    "release",
                    f"--squad={SQUAD_DIR}",
                ],
                quiet=args.json,
            )
        return 0

    cycle = new_cycle()
    cycle = advance(
        cycle,
        "RANKED",
        actor="force-next",
        evidence={
            "selected_id": selected["id"],
            "selected_roi": selected.get("roi"),
            "outcome": None,
        },
    )

    card = build_card(selected, rank, cycle["cycle_id"])
    card_dir = SQUAD_DIR / "state" / "execution-cards"
    card_dir.mkdir(parents=True, exist_ok=True)
    card_path = card_dir / "current.json"
    card_path.write_text(
        json.dumps(card, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (card_dir / f"{cycle['cycle_id']}.json").write_text(
        json.dumps(card, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    cycle = advance(
        cycle,
        "CARD",
        actor="force-next",
        evidence={"execution_card_path": str(card_path.relative_to(REPO))},
    )

    rc = run(
        [
            sys.executable,
            str(SCRIPT_DIR / "materialize_aiox_story.py"),
            f"--cycle-id={cycle['cycle_id']}",
        ],
        quiet=True,
    )
    if rc != 0:
        cycle["abort"] = {"code": "NO_STORY", "reason": "materialize failed"}
        cycle["status"] = "aborted"
        cycle["outcome"] = "ABORTED_UNSAFE_STATE"
        save_cycle(cycle)
        if not args.skip_lock:
            run(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "cycle_lock.py"),
                    "release",
                    f"--squad={SQUAD_DIR}",
                ],
                quiet=args.json,
            )
        return 2

    card = json.loads(card_path.read_text(encoding="utf-8"))
    cycle = advance(
        cycle,
        "STORY_DRAFT",
        actor="force-next/@sm-materializer",
        evidence={
            "story_id": card.get("story_id"),
            "story_file": card.get("story_file"),
            "story_state_file": card.get("story_state_file"),
            "implementer_agent": "delivery-engineer",
            "qa_agent": "adversarial-qa-auditor",
        },
    )

    sid = card.get("story_id")
    mandatory = [
        f"@po *validate-story-draft {sid}  -> Ready + po_validated=true "
        f"in .aiox/state/stories/{sid}.json",
        "python squads/extra-dod-roi/scripts/enforce_aiox_path.py implement  # must PASS",
        f"@dev implement ONLY story {sid} / candidate {selected['id']} on non-main branch",
        "@dev mark InReview + handoff to @qa (never self-QA)",
        "@qa *qa-gate -> PASS|CONCERNS|FAIL|WAIVED (independent)",
        "If FAIL: return @dev (rework) then @qa again",
        "@po *close-story after acceptable QA",
        "@devops draft PR / publish path (no auto-merge, no force-push)",
        "python squads/extra-dod-roi/scripts/cli.py force-next  # RERANK next ROI",
    ]

    out = {
        "ok": True,
        "foolproof": True,
        "outcome": "BOUND_TO_AIOX_SDC",
        "cycle_id": cycle["cycle_id"],
        "phase": cycle["phase"],
        "next_phase_required": cycle.get("next_phase_required"),
        "selected_id": selected["id"],
        "roi": selected.get("roi"),
        "title": selected.get("title"),
        "story_id": card.get("story_id"),
        "story_file": card.get("story_file"),
        "story_state_file": card.get("story_state_file"),
        "execution_card": str(card_path.relative_to(REPO)),
        "divergences": rank.get("divergences"),
        "blockers_still_open": rank.get("blockers"),
        "mandatory_steps": mandatory,
        "message": (
            "Cycle bound to ranking[0]. Implementation is BLOCKED until @po Ready. "
            "Any other work is a process violation."
        ),
    }

    if not args.skip_lock:
        run(
            [
                sys.executable,
                str(SCRIPT_DIR / "cycle_lock.py"),
                "release",
                f"--squad={SQUAD_DIR}",
            ],
            quiet=args.json,
        )

    if args.json:
        print(json.dumps(out, indent=2, ensure_ascii=False))
    else:
        print_banner(out)
        print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

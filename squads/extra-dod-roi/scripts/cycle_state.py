#!/usr/bin/env python3
"""Fool-proof cycle state machine for extra-dod-roi.

Phases are strictly ordered. No skip. No pick-your-own-candidate.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
SQUAD_DIR = SCRIPT_DIR.parent

# Ordered, non-skippable
PHASES = [
    "INIT",
    "RANKED",
    "CARD",
    "STORY_DRAFT",
    "STORY_READY",
    "IMPLEMENTING",
    "IN_REVIEW",
    "QA",
    "PO_CLOSE",
    "PUBLISH",
    "RERANK",
    "DONE",
]

# Legal transitions only (forward + rework)
TRANSITIONS: dict[str, set[str]] = {
    "INIT": {"RANKED", "DONE"},  # DONE if NO_UNLOCKED
    "RANKED": {"CARD", "DONE"},  # DONE if NO_UNLOCKED after rank
    "CARD": {"STORY_DRAFT"},
    "STORY_DRAFT": {"STORY_READY"},
    "STORY_READY": {"IMPLEMENTING"},
    "IMPLEMENTING": {"IN_REVIEW"},
    "IN_REVIEW": {"QA"},
    "QA": {"PO_CLOSE", "IMPLEMENTING"},  # FAIL → rework
    "PO_CLOSE": {"PUBLISH"},
    "PUBLISH": {"RERANK"},
    "RERANK": {"DONE", "RANKED"},  # DONE ends cycle; RANKED starts next
    "DONE": {"INIT"},  # new cycle
}

ABORT = {
    "SKIP_PHASE",
    "WRONG_CANDIDATE",
    "STALE_RANK",
    "SELF_QA",
    "NO_STORY",
    "PO_NOT_READY",
    "QA_NOT_PASS",
    "DOD_PREMATURE",
    "MAIN_WRITE",
    "SCOPE_DRIFT",
    "HUMAN_BLOCKER",
    "NO_UNLOCKED",
    "ILLEGAL_TRANSITION",
    "MISSING_ARTIFACT",
}


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def cycle_path() -> Path:
    return SQUAD_DIR / "state" / "cycles" / "current.json"


def load_cycle() -> dict[str, Any] | None:
    p = cycle_path()
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def save_cycle(data: dict[str, Any]) -> Path:
    p = cycle_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = utcnow()
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    # archive
    arch = SQUAD_DIR / "state" / "cycles" / f"{data['cycle_id']}.json"
    arch.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


def new_cycle(seed: dict[str, Any] | None = None) -> dict[str, Any]:
    cid = f"cyc-{utcnow().replace(':', '')}"
    data = {
        "version": "1.0.0",
        "cycle_id": cid,
        "mode": "strict",
        "foolproof": True,
        "status": "running",
        "phase": "INIT",
        "created_at": utcnow(),
        "updated_at": utcnow(),
        "selected_id": None,
        "selected_roi": None,
        "execution_card_path": None,
        "story_id": None,
        "story_file": None,
        "story_state_file": None,
        "implementer_agent": None,
        "qa_agent": None,
        "qa_verdict": None,
        "aiox_sequence_log": [],
        "abort": None,
        "outcome": None,
        "next_phase_required": "RANKED",
        "enforcement": {
            "policy": "data/enforcement-policy.yaml",
            "binding": "data/aiox-binding.yaml",
            "allow_skip": False,
            "selection_rule": "ranking[0] only",
        },
    }
    if seed:
        data.update(seed)
    return data


def log_event(cycle: dict[str, Any], event: str, detail: dict[str, Any] | None = None) -> None:
    cycle.setdefault("aiox_sequence_log", []).append(
        {"at": utcnow(), "event": event, "phase": cycle.get("phase"), "detail": detail or {}}
    )


def advance(cycle: dict[str, Any], to_phase: str, *, actor: str, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    cur = cycle["phase"]
    allowed = TRANSITIONS.get(cur, set())
    if to_phase not in allowed:
        cycle["abort"] = {
            "code": "ILLEGAL_TRANSITION",
            "from": cur,
            "to": to_phase,
            "allowed": sorted(allowed),
            "actor": actor,
        }
        cycle["status"] = "aborted"
        cycle["outcome"] = "ABORTED_UNSAFE_STATE"
        log_event(cycle, "ABORT_ILLEGAL_TRANSITION", cycle["abort"])
        save_cycle(cycle)
        raise SystemExit(
            f"ILLEGAL_TRANSITION: {cur} → {to_phase}; allowed={sorted(allowed)}"
        )
    cycle["phase"] = to_phase
    # next required
    idx = PHASES.index(to_phase) if to_phase in PHASES else -1
    if to_phase == "DONE":
        cycle["next_phase_required"] = None
        cycle["status"] = "completed"
    elif to_phase == "QA" and (evidence or {}).get("qa_verdict") == "FAIL":
        cycle["next_phase_required"] = "IMPLEMENTING"
    else:
        # default next along happy path
        happy = {
            "INIT": "RANKED",
            "RANKED": "CARD",
            "CARD": "STORY_DRAFT",
            "STORY_DRAFT": "STORY_READY",
            "STORY_READY": "IMPLEMENTING",
            "IMPLEMENTING": "IN_REVIEW",
            "IN_REVIEW": "QA",
            "QA": "PO_CLOSE",
            "PO_CLOSE": "PUBLISH",
            "PUBLISH": "RERANK",
            "RERANK": "DONE",
        }
        cycle["next_phase_required"] = happy.get(to_phase)
    log_event(cycle, "ADVANCE", {"to": to_phase, "actor": actor, "evidence": evidence or {}})
    if evidence:
        if "selected_id" in evidence:
            cycle["selected_id"] = evidence["selected_id"]
        if "selected_roi" in evidence:
            cycle["selected_roi"] = evidence["selected_roi"]
        if "story_id" in evidence:
            cycle["story_id"] = evidence["story_id"]
        if "story_file" in evidence:
            cycle["story_file"] = evidence["story_file"]
        if "story_state_file" in evidence:
            cycle["story_state_file"] = evidence["story_state_file"]
        if "execution_card_path" in evidence:
            cycle["execution_card_path"] = evidence["execution_card_path"]
        if "implementer_agent" in evidence:
            cycle["implementer_agent"] = evidence["implementer_agent"]
        if "qa_agent" in evidence:
            cycle["qa_agent"] = evidence["qa_agent"]
        if "qa_verdict" in evidence:
            cycle["qa_verdict"] = evidence["qa_verdict"]
        if "outcome" in evidence:
            cycle["outcome"] = evidence["outcome"]
    save_cycle(cycle)
    return cycle


def require_phase(cycle: dict[str, Any], expected: str) -> None:
    if cycle.get("phase") != expected:
        raise SystemExit(
            f"SKIP_PHASE: current={cycle.get('phase')} expected={expected} "
            f"next_required={cycle.get('next_phase_required')}"
        )


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Cycle state machine")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show")
    sub.add_parser("init")
    p_adv = sub.add_parser("advance")
    p_adv.add_argument("--to", required=True)
    p_adv.add_argument("--actor", default="roi-orchestrator")
    p_adv.add_argument("--evidence-json", default=None)
    p_abort = sub.add_parser("abort")
    p_abort.add_argument("--code", required=True)
    p_abort.add_argument("--reason", default="")
    args = p.parse_args(argv)

    if args.cmd == "show":
        c = load_cycle()
        print(json.dumps(c or {"phase": None, "message": "no active cycle"}, indent=2, ensure_ascii=False))
        return 0
    if args.cmd == "init":
        c = new_cycle()
        save_cycle(c)
        print(json.dumps(c, indent=2, ensure_ascii=False))
        return 0
    if args.cmd == "advance":
        c = load_cycle() or new_cycle()
        ev = json.loads(args.evidence_json) if args.evidence_json else {}
        c = advance(c, args.to, actor=args.actor, evidence=ev)
        print(json.dumps(c, indent=2, ensure_ascii=False))
        return 0
    if args.cmd == "abort":
        c = load_cycle() or new_cycle()
        c["abort"] = {"code": args.code, "reason": args.reason, "at": utcnow()}
        c["status"] = "aborted"
        c["outcome"] = "ABORTED_UNSAFE_STATE"
        log_event(c, "ABORT", c["abort"])
        save_cycle(c)
        print(json.dumps(c, indent=2, ensure_ascii=False))
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

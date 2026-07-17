#!/usr/bin/env python3
"""Fail-closed preflight for any write phase of extra-dod-roi.

Exit 0 = allowed to proceed.
Exit 2 = blocked (prints JSON abort).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
SQUAD_DIR = SCRIPT_DIR.parent
REPO = SQUAD_DIR.parent.parent  # squads/extra-dod-roi -> repo root


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fail(code: str, message: str, **extra: Any) -> int:
    payload = {"ok": False, "abort_code": code, "message": message, "at": utcnow(), **extra}
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 2


def ok(message: str, **extra: Any) -> int:
    print(json.dumps({"ok": True, "message": message, "at": utcnow(), **extra}, indent=2, ensure_ascii=False))
    return 0


def git(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=str(REPO), text=True).strip()
    except Exception as e:
        return ""


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_stale_rank(rank: dict[str, Any]) -> list[str]:
    reasons = []
    head = git("rev-parse", "HEAD")
    dod_hash = sha256_file(REPO / "DOD.md")
    r_head = (rank.get("git") or {}).get("head") or rank.get("repo_head")
    r_dod = rank.get("dod_hash")
    if r_head and head and r_head != head:
        reasons.append(f"HEAD changed: rank={r_head[:8]} now={head[:8]}")
    if r_dod and dod_hash and r_dod != dod_hash:
        reasons.append("DOD.md hash changed since rank")
    # age
    gen = rank.get("generated_at")
    if gen:
        try:
            # 2026-07-17T21:34:02Z
            dt = datetime.strptime(gen, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            age_h = (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0
            if age_h > 4:
                reasons.append(f"ranking age {age_h:.1f}h > 4h")
        except ValueError:
            pass
    return reasons


def check_phase(action: str) -> int:
    """Validate prerequisites for a named action."""
    cycle = load_json(SQUAD_DIR / "state" / "cycles" / "current.json")
    rank = load_json(SQUAD_DIR / "state" / "rankings" / "latest.json")
    card = load_json(SQUAD_DIR / "state" / "execution-cards" / "current.json")

    branch = git("rev-parse", "--abbrev-ref", "HEAD")

    if action in ("implement", "execute-next", "story-ready-to-implement"):
        if branch in ("main", "master"):
            return fail("MAIN_WRITE", "Product implementation forbidden on main; create isolated branch", branch=branch)

    if action in ("force-next", "run-cycle", "rank"):
        return ok("rank/force-next entry allowed", branch=branch)

    if action == "card":
        if not rank:
            return fail("MISSING_ARTIFACT", "No ranking; run force-next/rank-next first")
        stale = check_stale_rank(rank)
        if stale:
            return fail("STALE_RANK", "Re-run rank-next before card", reasons=stale)
        if not rank.get("selected_id"):
            return fail("NO_UNLOCKED", "No selected candidate in ranking")
        return ok("card allowed for selected", selected_id=rank.get("selected_id"))

    if action == "materialize-story":
        if not rank or not card:
            return fail("MISSING_ARTIFACT", "Need ranking + execution card")
        if card.get("candidate_id") != rank.get("selected_id"):
            return fail(
                "WRONG_CANDIDATE",
                "Execution card candidate_id must equal ranking selected_id (#1 only)",
                card=card.get("candidate_id"),
                selected=rank.get("selected_id"),
            )
        stale = check_stale_rank(rank)
        if stale:
            return fail("STALE_RANK", "Ranking stale", reasons=stale)
        return ok("materialize story allowed", selected_id=rank.get("selected_id"))

    if action in ("implement", "execute-next"):
        if not cycle:
            return fail("MISSING_ARTIFACT", "No cycle state; run force-next")
        if cycle.get("phase") not in ("STORY_READY", "IMPLEMENTING"):
            return fail(
                "SKIP_PHASE",
                f"Implement only from STORY_READY/IMPLEMENTING; current={cycle.get('phase')}",
                next_required=cycle.get("next_phase_required"),
            )
        if not cycle.get("story_id") or not cycle.get("story_state_file"):
            return fail("NO_STORY", "AIOX story not materialized")
        state_path = REPO / cycle["story_state_file"]
        st = load_json(state_path)
        if not st:
            return fail("NO_STORY", f"Missing state file {cycle['story_state_file']}")
        if not st.get("po_validated") or st.get("status") not in ("Ready", "InProgress"):
            return fail(
                "PO_NOT_READY",
                "Story must be Ready with po_validated=true before implement",
                status=st.get("status"),
                po_validated=st.get("po_validated"),
            )
        if card and card.get("candidate_id") != cycle.get("selected_id"):
            return fail("WRONG_CANDIDATE", "Cycle selected_id drift vs card")
        if rank and cycle.get("selected_id") != rank.get("selected_id"):
            # allow if rank refreshed to same id; if different, abort
            if cycle.get("selected_id") != rank.get("selected_id"):
                return fail(
                    "WRONG_CANDIDATE",
                    "Cannot implement non-#1 work; re-rank or finish current cycle",
                    cycle_selected=cycle.get("selected_id"),
                    rank_selected=rank.get("selected_id"),
                )
        return ok(
            "implement allowed",
            story_id=cycle.get("story_id"),
            phase=cycle.get("phase"),
            branch_required_not_main=True,
        )

    if action == "qa":
        if not cycle:
            return fail("MISSING_ARTIFACT", "No cycle")
        if cycle.get("phase") not in ("IN_REVIEW", "QA"):
            return fail("SKIP_PHASE", f"QA only after IN_REVIEW; current={cycle.get('phase')}")
        impl = cycle.get("implementer_agent") or "delivery-engineer"
        qa = cycle.get("qa_agent") or "adversarial-qa-auditor"
        if impl == qa:
            return fail("SELF_QA", "Implementer and QA must differ", implementer=impl, qa=qa)
        return ok("qa allowed", implementer=impl, qa=qa)

    if action == "po-close":
        if not cycle:
            return fail("MISSING_ARTIFACT", "No cycle")
        if cycle.get("phase") not in ("QA", "PO_CLOSE"):
            return fail("SKIP_PHASE", f"PO close only after QA; current={cycle.get('phase')}")
        if cycle.get("qa_verdict") not in ("PASS", "CONCERNS", "WAIVED"):
            return fail("QA_NOT_PASS", "Cannot PO-close without acceptable QA verdict", verdict=cycle.get("qa_verdict"))
        return ok("po-close allowed")

    if action == "publish":
        if not cycle:
            return fail("MISSING_ARTIFACT", "No cycle")
        if cycle.get("phase") not in ("PO_CLOSE", "PUBLISH"):
            return fail("SKIP_PHASE", f"Publish only after PO_CLOSE; current={cycle.get('phase')}")
        st_file = cycle.get("story_state_file")
        if st_file:
            st = load_json(REPO / st_file)
            if st and not st.get("po_closed"):
                return fail("PO_NOT_READY", "po_closed must be true before publish path")
        return ok("publish path allowed (draft PR; @devops only for push)")

    if action == "dod-update":
        if not cycle or cycle.get("qa_verdict") not in ("PASS", "CONCERNS", "WAIVED"):
            return fail("DOD_PREMATURE", "DoD updates forbidden before QA PASS/CONCERNS/WAIVED")
        if cycle.get("phase") not in ("PO_CLOSE", "PUBLISH", "RERANK", "DONE"):
            return fail("DOD_PREMATURE", f"DoD update not allowed in phase {cycle.get('phase')}")
        return ok("dod update gate open (still require evidence checklist)")

    return fail("UNKNOWN_ACTION", f"Unknown action {action}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument(
        "action",
        choices=[
            "force-next",
            "run-cycle",
            "rank",
            "card",
            "materialize-story",
            "implement",
            "execute-next",
            "qa",
            "po-close",
            "publish",
            "dod-update",
            "story-ready-to-implement",
        ],
    )
    args = p.parse_args(argv)
    return check_phase(args.action)


if __name__ == "__main__":
    raise SystemExit(main())

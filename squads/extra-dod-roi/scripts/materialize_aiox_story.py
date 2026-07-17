#!/usr/bin/env python3
"""Materialize AIOX story + state file from execution card (ranking[0] only).

Emulates @sm draft output so the inevitable SDC path can continue:
  STORY_DRAFT -> @po validate -> STORY_READY -> @dev implement -> ...
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
SQUAD_DIR = SCRIPT_DIR.parent
REPO = SQUAD_DIR.parent.parent


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slugify(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")[:60]


def risk_for_candidate(cand: dict[str, Any]) -> str:
    text = json.dumps(cand).lower()
    high = [
        "secret",
        "auth",
        "migration",
        "vps",
        "infra",
        "security",
        "credential",
        "ci/cd",
        "protocol",
    ]
    if any(h in text for h in high):
        return "HIGH-RISK"
    return "STANDARD"


def build_story_md(
    story_id: str, card: dict[str, Any], cand: dict[str, Any], cycle_id: str
) -> str:
    ac_list = cand.get("acceptance_criteria") or card.get("acceptance_criteria") or []
    ac_lines = []
    for i, ac in enumerate(ac_list, 1):
        ac_lines.append(
            f"{i}. **Given** the current mainline and DoD constraints, "
            f"**When** this slice is delivered, **Then** {ac}"
        )
    if not ac_lines:
        ac_lines.append(
            "1. **Then** acceptance criteria from execution card are met with evidence."
        )
    ac_md = "\n".join(ac_lines)

    tests = cand.get("test_commands") or card.get("test_commands") or []
    tests_md = "\n".join(f"- `{t}`" for t in tests) or (
        "- (define during PO validation if missing — cannot Ready without tests)"
    )
    files = cand.get("planned_files") or card.get("planned_files") or []
    files_md = "\n".join(f"- `{f}`" for f in files) or (
        "- (scoped during implementation; must not exceed card)"
    )

    alts = card.get("alternatives_discarded") or []
    alts_md = "\n".join(f"- {x}" for x in alts) or "- See rank-next discarded list"
    risks = cand.get("risks") or []
    risks_md = "\n".join(f"- {r}" for r in risks) or "- (none listed)"
    deps = cand.get("dependencies") or []
    deps_md = "\n".join(f"- {d}" for d in deps) or "- (none)"
    allowed = card.get("allowed_claims") or []
    allowed_md = "\n".join(f"- {c}" for c in allowed) or "- Only claims backed by new evidence"
    forbidden = card.get("forbidden_claims") or [
        "PRE_VPS_FINAL_READY without live canary",
        "LOCAL_RESILIENCE_READY restored without new proof",
        "95% coverage without strict operational metric",
    ]
    forbidden_md = "\n".join(f"- {c}" for c in forbidden)
    dod_refs = ", ".join(cand.get("dod_refs") or []) or "—"
    problem = card.get("problem") or cand.get("justification") or "See execution card."
    evidence = card.get("evidence") or "See ranking divergences and DoD truth matrix."
    rollback = (
        card.get("rollback")
        or "Revert atomic commits on feature branch; do not merge; leave DoD unchanged."
    )
    title = card.get("title") or cand.get("title")
    day = utcnow()[:10]

    return f"""# Story: {title}

**Story ID:** `{story_id}`  
**Epic:** EPIC-EXTRA-DOD-ROI (evergreen)  
**Status:** Draft  
**Risk level:** **{risk_for_candidate(cand)}**  
**Source:** squad `extra-dod-roi` force-next (cycle `{cycle_id}`)  
**Candidate ID:** `{cand.get("id")}`  
**ROI:** `{cand.get("roi")}`  
**DoD refs:** {dod_refs}

> **FOOL-PROOF BINDING:** This story was materialized exclusively from ranking[0].
> Implementing any other work while this cycle is active is **forbidden**.
> AIOX sequence is mandatory: @sm (done) -> @po -> @dev -> @qa -> @po -> @devops.

---

## Story

As **Tiago (operator of Extra Consultoria B2G tooling)**,  
I want **{cand.get("title")}**,  
so that **the project advances the highest-ROI unlocked DoD gate without false greens**.

---

## Problem / Value

### Problem

{problem}

### Evidence of problem

{evidence}

### Value / ROI justification

{cand.get("justification")}

**Score:** ROI={cand.get("roi")} value={cand.get("value")} cost={cand.get("cost")}

### Why unlocked

{cand.get("why_unlocked")}

### Alternatives discarded

{alts_md}

---

## Scope

### IN

- Work defined by candidate `{cand.get("id")}` only
- Tests and evidence required by acceptance criteria
- AIOX state transitions honored

### OUT

- Any lower-ROI unlocked item (must wait for next cycle)
- Blocked external work unless this card is exactly that and resources exist
- Scope expansion / architecture tourism without DoD link
- Portal publico, multi-tenant, billing, K8s/Kafka/Redis/ES without demonstrated need
- Physical works tracking / auto-protocol without human action

---

## Acceptance Criteria

{ac_md}

---

## Test commands

{tests_md}

---

## Files (planned)

{files_md}

---

## Risks

{risks_md}

## Dependencies

{deps_md}

## Rollback

{rollback}

## Claims if PASS

{allowed_md}

## Claims still forbidden

{forbidden_md}

---

## AIOX DoD for this story

- [ ] @po validated (Ready)
- [ ] @dev implemented on non-main branch
- [ ] Tests/lint per risk level
- [ ] @qa independent verdict PASS|CONCERNS|WAIVED (not implementer)
- [ ] @po closed
- [ ] @devops draft PR / publish path (no auto-merge)
- [ ] DoD.md checkboxes only if evidence authorizes

---

## Change Log

| Date | Agent | Change |
|------|-------|--------|
| {day} | extra-dod-roi / @sm-materializer | Draft from ranking[0] force-next |

---

*Generated by squads/extra-dod-roi/scripts/materialize_aiox_story.py — do not hand-edit candidate_id binding.*
"""


def build_state(
    story_id: str,
    story_rel: str,
    card: dict[str, Any],
    cand: dict[str, Any],
    cycle_id: str,
) -> dict[str, Any]:
    risk = risk_for_candidate(cand)
    files = cand.get("planned_files") or card.get("planned_files") or []
    scope_files = []
    for f in files:
        if isinstance(f, str) and not f.startswith("("):
            scope_files.append(f)
    if not scope_files:
        scope_files = ["docs/stories/" + story_rel.split("/")[-1]]
    return {
        "story_id": story_id,
        "title": card.get("title") or cand.get("title"),
        "epic_id": "EPIC-EXTRA-DOD-ROI",
        "risk_level": risk,
        "status": "Draft",
        "story_file": story_rel,
        "created_at": utcnow(),
        "updated_at": utcnow(),
        "created_by": "extra-dod-roi-force-next",
        "po_validated": False,
        "qa_verdict": "PENDING",
        "po_closed": False,
        "publication_authorized": False,
        "scope_files": scope_files,
        "reviewed_commit": None,
        "gates": {
            "lint": "PENDING",
            "typecheck": "PENDING",
            "tests": "PENDING",
            "build": "NA",
        },
        "rollback_plan": card.get("rollback")
        or "Revert branch commits; no DoD edits.",
        "snapshot_evidence": None,
        "maintenance_mode": False,
        "extra_dod_roi": {
            "cycle_id": cycle_id,
            "candidate_id": cand.get("id"),
            "roi": cand.get("roi"),
            "foolproof": True,
            "selection_rule": "ranking[0] only",
            "aiox_sequence_required": [
                "STORY_DRAFT",
                "STORY_READY",
                "IMPLEMENTING",
                "IN_REVIEW",
                "QA",
                "PO_CLOSE",
                "PUBLISH",
                "RERANK",
            ],
        },
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--cycle-id", default=None)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    rank_path = SQUAD_DIR / "state" / "rankings" / "latest.json"
    card_path = SQUAD_DIR / "state" / "execution-cards" / "current.json"
    if not rank_path.is_file():
        print(json.dumps({"ok": False, "error": "NO_RANKING"}))
        return 2
    rank = json.loads(rank_path.read_text(encoding="utf-8"))
    selected_id = rank.get("selected_id")
    selected = rank.get("selected") or next(
        (c for c in (rank.get("ranking") or []) if c.get("id") == selected_id),
        None,
    )
    if not selected:
        print(json.dumps({"ok": False, "error": "NO_SELECTED"}))
        return 2

    if not card_path.is_file():
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "NO_CARD",
                    "hint": "run force-next to build card",
                }
            )
        )
        return 2
    card = json.loads(card_path.read_text(encoding="utf-8"))
    if card.get("candidate_id") != selected_id:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "WRONG_CANDIDATE",
                    "card": card.get("candidate_id"),
                    "selected": selected_id,
                }
            )
        )
        return 2

    cycle_id = args.cycle_id or card.get("cycle_id") or "unknown"
    slug = slugify(selected_id or selected.get("title") or "roi-slice")
    story_id = f"ROI-{slug}"
    story_rel = f"docs/stories/{story_id}.md"
    state_rel = f".aiox/state/stories/{story_id}.json"

    md = build_story_md(story_id, card, selected, cycle_id)
    state = build_state(story_id, story_rel, card, selected, cycle_id)

    if args.dry_run:
        print(
            json.dumps(
                {
                    "ok": True,
                    "dry_run": True,
                    "story_id": story_id,
                    "story_file": story_rel,
                },
                indent=2,
            )
        )
        return 0

    story_path = REPO / story_rel
    state_path = REPO / state_rel
    story_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    story_path.write_text(md, encoding="utf-8")
    state_path.write_text(
        json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    card["story_id"] = story_id
    card["story_file"] = story_rel
    card["story_state_file"] = state_rel
    card_path.write_text(
        json.dumps(card, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(
        json.dumps(
            {
                "ok": True,
                "story_id": story_id,
                "story_file": story_rel,
                "story_state_file": state_rel,
                "status": "Draft",
                "next_mandatory": (
                    "AIOX @po *validate-story-draft -> Ready (po_validated=true)"
                ),
                "forbidden": "Do not implement until STORY_READY",
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

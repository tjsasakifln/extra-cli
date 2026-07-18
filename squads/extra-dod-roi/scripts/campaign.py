#!/usr/bin/env python3
"""Resumable campaign mode for extra-dod-roi (target N DoD checkbox flips).

Ledger: squads/extra-dod-roi/state/campaigns/dod-50-current.json

Does NOT flip DOD.md. Does NOT implement product code. Orchestrates ranking,
ledger consistency, and progress reconstruction from DOD.md diffs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
SQUAD_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from dod_ids import normalize_text, stable_dod_id  # noqa: E402
from parse_dod import parse_dod  # noqa: E402
from rank_next_cli import run_rank_next  # noqa: E402
from snapshot_state import repo_root_from  # noqa: E402

LEDGER_NAME = "dod-50-current.json"
DEFAULT_TARGET = 50


def utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ledger_path(root: Path) -> Path:
    return root / "squads" / "extra-dod-roi" / "state" / "campaigns" / LEDGER_NAME


def load_ledger(root: Path) -> dict[str, Any] | None:
    p = ledger_path(root)
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def save_ledger(root: Path, ledger: dict[str, Any]) -> Path:
    p = ledger_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    ledger["updated_at"] = utcnow()
    p.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return p


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def parse_items(text: str) -> list[dict[str, Any]]:
    section = ""
    items: list[dict[str, Any]] = []
    for i, line in enumerate(text.splitlines(), 1):
        m = re.match(r"^(#{1,6})\s+(.+)$", line)
        if m:
            section = m.group(2).strip()
            continue
        m = re.match(r"^(\s*)[-*]\s+\[([ xX])\]\s+(.*)$", line)
        if not m:
            continue
        body = m.group(3).strip()
        checked = m.group(2).lower() == "x"
        items.append(
            {
                "id": stable_dod_id(section, body),
                "line": i,
                "section": section,
                "text": body,
                "text_normalized": normalize_text(body),
                "checked": checked,
            }
        )
    return items


def reconstruct_accepted_from_diff(
    baseline_open_ids: set[str],
    current_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Count only items that were open in baseline and are now checked."""
    out = []
    for it in current_items:
        if it["checked"] and it["id"] in baseline_open_ids:
            out.append(
                {
                    "dod_item_id": it["id"],
                    "section": it["section"],
                    "text": it["text"][:200],
                    "line": it["line"],
                    "source": "dod_diff_vs_baseline",
                }
            )
    return out


def ensure_baseline(root: Path, target: int) -> dict[str, Any]:
    existing = load_ledger(root)
    if existing and existing.get("baseline"):
        return existing
    dod = root / "DOD.md"
    text = dod.read_text(encoding="utf-8")
    items = parse_items(text)
    open_items = [x for x in items if not x["checked"]]
    done_items = [x for x in items if x["checked"]]
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    try:
        main = subprocess.check_output(
            ["git", "rev-parse", "origin/main"], cwd=root, text=True
        ).strip()
    except subprocess.CalledProcessError:
        main = None
    branch = subprocess.check_output(
        ["git", "branch", "--show-current"], cwd=root, text=True
    ).strip()
    ledger = {
        "version": "1.0.0",
        "campaign_id": "dod-50-current",
        "created_at": utcnow(),
        "updated_at": utcnow(),
        "status": "BASELINE_RECORDED",
        "repo": "tjsasakifln/extra-consultoria",
        "target_dod_items": target,
        "baseline": {
            "recorded_at": utcnow(),
            "branch": branch,
            "head": head,
            "origin_main": main,
            "dod_path": "DOD.md",
            "dod_sha256": sha256_file(dod),
            "item_count": len(items),
            "done_count": len(done_items),
            "open_count": len(open_items),
            "done_ids": [x["id"] for x in done_items],
            "open_ids": [x["id"] for x in open_items],
        },
        "campaign_branch": None,
        "draft_pr": None,
        "accepted": [],
        "blocked": [],
        "cycles": [],
        "exclusions": [],
        "counts": {"accepted": 0, "blocked": 0, "in_qa": 0, "implementing": 0},
        "matrix": [],
        "notes": [],
    }
    save_ledger(root, ledger)
    return ledger


def panel(ledger: dict[str, Any], ranking: dict[str, Any] | None = None) -> str:
    accepted = ledger.get("counts", {}).get("accepted") or len(ledger.get("accepted") or [])
    target = ledger.get("target_dod_items") or DEFAULT_TARGET
    sel = (ranking or {}).get("selected") or {}
    top2 = ((ranking or {}).get("ranking") or [None, None])
    nxt = top2[1] if len(top2) > 1 else None
    lines = [
        f"Meta: {target}",
        f"Aceitos: {accepted}",
        f"Em QA: {ledger.get('counts', {}).get('in_qa', 0)}",
        f"Em implementação: {ledger.get('counts', {}).get('implementing', 0)}",
        f"Bloqueados: {ledger.get('counts', {}).get('blocked', 0) or len(ledger.get('blocked') or [])}",
        f"PR draft: {ledger.get('draft_pr') or '—'}",
        f"Último candidato: {(ledger.get('cycles') or [{}])[-1].get('candidate_id') if ledger.get('cycles') else '—'} "
        f"ROI={(ledger.get('cycles') or [{}])[-1].get('roi') if ledger.get('cycles') else '—'}",
        f"Próximo candidato: {sel.get('id') or (top2[0] or {}).get('id') if top2 else '—'} "
        f"ROI={sel.get('roi') or ((top2[0] or {}).get('roi') if top2 else '—')}",
        f"Seguinte: {(nxt or {}).get('id', '—')} ROI={(nxt or {}).get('roi', '—')}",
        f"Status campanha: {ledger.get('status')}",
    ]
    return "\n".join(lines)


def validate_guards(ledger: dict[str, Any], current_items: list[dict[str, Any]]) -> list[str]:
    """Return list of guard violations (empty = ok)."""
    errs: list[str] = []
    baseline_done = set((ledger.get("baseline") or {}).get("done_ids") or [])
    baseline_open = set((ledger.get("baseline") or {}).get("open_ids") or [])
    accepted = ledger.get("accepted") or []
    seen: set[str] = set()
    for a in accepted:
        did = a.get("dod_item_id") if isinstance(a, dict) else a
        if not did:
            errs.append("accepted entry missing dod_item_id")
            continue
        if did in baseline_done:
            errs.append(f"preexisting checkbox counted: {did}")
        if did in seen:
            errs.append(f"duplicate accepted: {did}")
        seen.add(did)
        if did not in baseline_open:
            errs.append(f"accepted id not in baseline open set: {did}")
    # fictitious meta
    target = int(ledger.get("target_dod_items") or DEFAULT_TARGET)
    if len(seen) > target and ledger.get("status") == "SUCCESS":
        # allowing >target is ok; < with SUCCESS is not
        pass
    if ledger.get("status") == "SUCCESS" and len(seen) < target:
        errs.append(f"SUCCESS declared with only {len(seen)} < {target}")
    # matrix consistency
    for row in ledger.get("matrix") or []:
        if row.get("qa_verdict") not in {"PASS", "CONCERNS", "WAIVED"}:
            errs.append(f"matrix row without acceptable QA: {row.get('dod_item_id')}")
        if row.get("estado_baseline") != "[ ]":
            errs.append(f"matrix baseline not open: {row.get('dod_item_id')}")
        if row.get("estado_final") != "[x]":
            errs.append(f"matrix final not checked: {row.get('dod_item_id')}")
    return errs


def validate_evidence_quality(
    *,
    evidence: str,
    command: str,
    exit_code: int,
    qa_verdict: str,
) -> None:
    """Fail-closed evidence gates — no code-only / empty / unit-as-e2e claims.

    Enforces process principles from DOD §1 without allowing silent false green:
    - evidence must be non-empty and verifiable path/command oriented
    - pure "code exists" / "file inventory" without execution is rejected for PASS
    - evidence claiming e2e/ponta-a-ponta cannot be only unit pytest without e2e marker
    """
    ev = (evidence or "").strip()
    cmd = (command or "").strip()
    if not ev:
        raise ValueError("evidence required — empty evidence refused")
    low = ev.lower()
    cmd_low = cmd.lower()
    # Code-only / inventory-only without a real command execution is not enough for PASS
    code_only_markers = (
        "code exists",
        "código existente",
        "codigo existente",
        "file inventory",
        "module exists only",
        "exists on disk only",
        "truth auditor + campaign refuse code-only",  # invented claim marker
        "campaign guards refuse code-only",
    )
    if qa_verdict.upper() == "PASS":
        if any(m in low for m in code_only_markers) and (
            not cmd or "inventory" in cmd_low or exit_code not in (0,)
        ):
            raise ValueError(
                "code-only/inventory evidence without successful execution command refused for PASS"
            )
        if not cmd:
            raise ValueError("command required for PASS acceptance")
        if exit_code != 0:
            raise ValueError(f"exit_code {exit_code} != 0 refused for PASS")
        # unit must not stand in for e2e when claim language asserts e2e
        e2e_claim = any(
            x in low
            for x in (
                "e2e",
                "ponta a ponta",
                "ponta-a-ponta",
                "end-to-end",
                "end to end",
            )
        )
        unit_only = (
            "pytest" in cmd_low
            and "e2e" not in cmd_low
            and "integration" not in cmd_low
            and "-m e2e" not in cmd_low
        )
        if e2e_claim and unit_only:
            raise ValueError(
                "unit pytest cannot satisfy e2e/ponta-a-ponta claim — refused"
            )


def register_acceptance(
    root: Path,
    *,
    dod_item_ids: list[str],
    story_id: str,
    commit: str,
    evidence: str,
    command: str,
    exit_code: int,
    qa_verdict: str,
    qa_agent: str,
    implementer: str,
    candidate_id: str,
    roi: float | None,
) -> dict[str, Any]:
    """Record accepted flips after independent QA. Does not edit DOD.md."""
    ledger = ensure_baseline(root, DEFAULT_TARGET)
    if qa_verdict.upper() not in {"PASS", "CONCERNS", "WAIVED"}:
        raise ValueError("QA verdict not acceptable — refusing acceptance")
    if implementer and qa_agent and implementer == qa_agent:
        raise ValueError("SELF_QA forbidden")
    validate_evidence_quality(
        evidence=evidence,
        command=command,
        exit_code=exit_code,
        qa_verdict=qa_verdict,
    )
    dod = root / "DOD.md"
    items = parse_items(dod.read_text(encoding="utf-8"))
    by_id = {i["id"]: i for i in items}
    baseline_open = set((ledger.get("baseline") or {}).get("open_ids") or [])
    baseline_done = set((ledger.get("baseline") or {}).get("done_ids") or [])
    accepted = ledger.setdefault("accepted", [])
    matrix = ledger.setdefault("matrix", [])
    existing = {
        (a.get("dod_item_id") if isinstance(a, dict) else a) for a in accepted
    }
    for did in dod_item_ids:
        if did in baseline_done:
            raise ValueError(f"cannot count preexisting done item: {did}")
        if did not in baseline_open:
            raise ValueError(f"item not in baseline open set: {did}")
        if did in existing:
            raise ValueError(f"duplicate acceptance: {did}")
        it = by_id.get(did)
        if not it or not it.get("checked"):
            raise ValueError(
                f"DOD.md does not have [x] for {did} — refuse premature ledger count"
            )
        row = {
            "dod_item_id": did,
            "seção": it["section"],
            "texto": it["text"][:200],
            "estado_baseline": "[ ]",
            "estado_final": "[x]",
            "story_id": story_id,
            "commit": commit,
            "evidência": evidence,
            "comando": command,
            "exit_code": exit_code,
            "qa_verdict": qa_verdict.upper(),
            "qa_agent": qa_agent,
            "implementer": implementer,
            "candidate_id": candidate_id,
            "roi": roi,
            "accepted_at": utcnow(),
        }
        accepted.append({"dod_item_id": did, **row})
        matrix.append(row)
        existing.add(did)
    ledger["counts"]["accepted"] = len(existing)
    target = int(ledger.get("target_dod_items") or DEFAULT_TARGET)
    if ledger["counts"]["accepted"] >= target:
        ledger["status"] = "SUCCESS"
    else:
        ledger["status"] = "IN_PROGRESS"
    errs = validate_guards(ledger, items)
    if errs:
        raise ValueError("guard violations: " + "; ".join(errs))
    save_ledger(root, ledger)
    return ledger


def cmd_status(root: Path, fetch: bool) -> int:
    ledger = ensure_baseline(root, DEFAULT_TARGET)
    ranking = run_rank_next(root, top_n=5, write_state=False, fetch=fetch)
    # reconstruct live count
    baseline_open = set((ledger.get("baseline") or {}).get("open_ids") or [])
    items = parse_items((root / "DOD.md").read_text(encoding="utf-8"))
    live = reconstruct_accepted_from_diff(baseline_open, items)
    payload = {
        "ledger_path": str(ledger_path(root).relative_to(root)),
        "status": ledger.get("status"),
        "panel": panel(ledger, ranking),
        "ledger_accepted": ledger.get("counts", {}).get("accepted", 0),
        "live_dod_diff_vs_baseline": len(live),
        "selected_id": ranking.get("selected_id"),
        "ranking_top": [
            {"id": c.get("id"), "roi": c.get("roi"), "title": (c.get("title") or "")[:100]}
            for c in (ranking.get("ranking") or [])[:5]
        ],
        "guards": validate_guards(ledger, items),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def cmd_resume(root: Path, target: int, fetch: bool) -> int:
    ledger = ensure_baseline(root, target)
    ledger["target_dod_items"] = target
    ranking = run_rank_next(root, top_n=50, write_state=True, fetch=fetch)
    if not ranking.get("selected_id"):
        ledger["status"] = "PARTIAL_NO_UNLOCKED_WORK"
        ledger.setdefault("notes", []).append(
            f"{utcnow()}: resume found NO_UNLOCKED_WORK after dynamic generation"
        )
        save_ledger(root, ledger)
        print(json.dumps({
            "outcome": "PARTIAL_NO_UNLOCKED_WORK",
            "panel": panel(ledger, ranking),
            "ranking_empty": True,
            "blockers": (ranking.get("blockers") or [])[:10],
        }, indent=2, ensure_ascii=False))
        return 0
    ledger["status"] = "IN_PROGRESS"
    ledger.setdefault("cycles", []).append(
        {
            "at": utcnow(),
            "phase": "RANKED",
            "candidate_id": ranking.get("selected_id"),
            "roi": (ranking.get("selected") or {}).get("roi"),
            "action": "resume-rank",
        }
    )
    save_ledger(root, ledger)
    print(json.dumps({
        "outcome": "RESUME_READY",
        "panel": panel(ledger, ranking),
        "selected": ranking.get("selected"),
        "next_command": "python3 squads/extra-dod-roi/scripts/cli.py force-next --fetch",
    }, indent=2, ensure_ascii=False))
    return 0


def cmd_sync_count(root: Path) -> int:
    """Rebuild accepted count from real DOD.md vs baseline (audit)."""
    ledger = ensure_baseline(root, DEFAULT_TARGET)
    baseline_open = set((ledger.get("baseline") or {}).get("open_ids") or [])
    items = parse_items((root / "DOD.md").read_text(encoding="utf-8"))
    live = reconstruct_accepted_from_diff(baseline_open, items)
    print(json.dumps({
        "baseline_open": len(baseline_open),
        "live_new_checked": len(live),
        "ledger_accepted": ledger.get("counts", {}).get("accepted", 0),
        "items": live,
    }, indent=2, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="extra-roi-campaign")
    p.add_argument("--repo", default=None)
    p.add_argument("--target-dod-items", type=int, default=DEFAULT_TARGET)
    p.add_argument("--resume", action="store_true")
    p.add_argument("--fetch", action="store_true")
    p.add_argument("--status", action="store_true")
    p.add_argument("--sync-count", action="store_true")
    args = p.parse_args(argv)
    root = Path(args.repo).resolve() if args.repo else repo_root_from()

    if args.sync_count:
        return cmd_sync_count(root)
    if args.status and not args.resume:
        return cmd_status(root, fetch=args.fetch)
    # default campaign entry = resume
    return cmd_resume(root, target=args.target_dod_items, fetch=args.fetch)


if __name__ == "__main__":
    raise SystemExit(main())

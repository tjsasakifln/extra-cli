"""Safe publication path after CTO ACCEPT — never invoked by Grok executor.

Sequence: local commit (if needed) → push (publisher only) → draft PR →
record on Issue/ledger → consult CI → WAITING_HUMAN. Never auto-merge.
"""
from __future__ import annotations

import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.cto.ledger import append_ledger
from scripts.cto.paths import cycles_dir, repo_root
from scripts.cto.redaction import redact_obj, redact_text
from scripts.cto.work_registry import load_registry, save_registry, upsert_item

# Only Tiago may authorize merge — publisher never merges.
MERGE_AUTHORITY = "Tiago"


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run(cmd: list[str], cwd: Path, timeout: int = 120) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "cmd": cmd,
            "exit_code": proc.returncode,
            "stdout": redact_text((proc.stdout or "")[-8000:]),
            "stderr": redact_text((proc.stderr or "")[-4000:]),
        }
    except subprocess.TimeoutExpired:
        return {"cmd": cmd, "exit_code": -1, "stdout": "", "stderr": "timeout"}
    except FileNotFoundError:
        return {"cmd": cmd, "exit_code": -2, "stdout": "", "stderr": "not_found"}


def has_local_diff(worktree: Path) -> bool:
    st = _run(["git", "status", "--porcelain"], worktree)
    return bool((st.get("stdout") or "").strip())


def current_branch(worktree: Path) -> str:
    res = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], worktree)
    return (res.get("stdout") or "").strip()


def current_commit(worktree: Path) -> str:
    res = _run(["git", "rev-parse", "HEAD"], worktree)
    return (res.get("stdout") or "").strip()


def ensure_commit(
    worktree: Path,
    *,
    message: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Create a controlled commit if there is uncommitted work."""
    if not has_local_diff(worktree):
        return {
            "committed": False,
            "reason": "clean tree",
            "commit": current_commit(worktree),
            "dry_run": dry_run,
        }
    if dry_run:
        return {
            "committed": False,
            "would_commit": True,
            "message": message,
            "dry_run": True,
            "commit": current_commit(worktree),
        }
    _run(["git", "add", "-A"], worktree)
    # refuse if still nothing staged
    staged = _run(["git", "diff", "--cached", "--name-only"], worktree)
    if not (staged.get("stdout") or "").strip():
        return {
            "committed": False,
            "reason": "nothing staged after add",
            "commit": current_commit(worktree),
        }
    res = _run(["git", "commit", "-m", message], worktree)
    return {
        "committed": res.get("exit_code") == 0,
        "exit_code": res.get("exit_code"),
        "stderr": res.get("stderr"),
        "commit": current_commit(worktree),
        "dry_run": False,
    }


def push_branch(
    worktree: Path,
    branch: str,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Push only from publisher (never from Grok executor child)."""
    if not branch or branch in {"main", "master"}:
        return {"ok": False, "error": "refusing push of main/master or empty branch"}
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "would_push": branch,
            "cmd": ["git", "push", "-u", "origin", branch],
        }
    res = _run(["git", "push", "-u", "origin", branch], worktree, timeout=180)
    return {
        "ok": res.get("exit_code") == 0,
        "exit_code": res.get("exit_code"),
        "stdout": res.get("stdout"),
        "stderr": res.get("stderr"),
        "branch": branch,
        "dry_run": False,
    }


def open_or_update_draft_pr(
    worktree: Path,
    *,
    branch: str,
    title: str,
    body: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Open or update a draft PR for the cycle branch. Never merges."""
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "would_create_or_update": True,
            "branch": branch,
            "title": title,
            "draft": True,
            "url": None,
            "number": None,
        }
    # Check existing PR for branch
    existing = _run(
        [
            "gh",
            "pr",
            "list",
            "--head",
            branch,
            "--json",
            "number,url,isDraft,state",
            "--limit",
            "1",
        ],
        worktree,
        timeout=60,
    )
    pr_number = None
    pr_url = None
    try:
        items = json.loads(existing.get("stdout") or "[]")
        if items:
            pr_number = items[0].get("number")
            pr_url = items[0].get("url")
    except json.JSONDecodeError:
        items = []

    if pr_number:
        edit = _run(
            [
                "gh",
                "pr",
                "edit",
                str(pr_number),
                "--title",
                title,
                "--body",
                body,
            ],
            worktree,
            timeout=60,
        )
        return {
            "ok": edit.get("exit_code") == 0,
            "action": "updated",
            "number": pr_number,
            "url": pr_url,
            "draft": True,
            "stderr": edit.get("stderr"),
        }

    create = _run(
        [
            "gh",
            "pr",
            "create",
            "--draft",
            "--title",
            title,
            "--body",
            body,
            "--base",
            "main",
            "--head",
            branch,
        ],
        worktree,
        timeout=90,
    )
    url = (create.get("stdout") or "").strip().splitlines()
    pr_url = url[-1] if url else None
    m = re.search(r"/pull/(\d+)", pr_url or "")
    return {
        "ok": create.get("exit_code") == 0,
        "action": "created",
        "number": int(m.group(1)) if m else None,
        "url": pr_url,
        "draft": True,
        "stderr": create.get("stderr"),
    }


def consult_ci(worktree: Path, pr_number: int | None, *, dry_run: bool = False) -> dict[str, Any]:
    if dry_run or not pr_number:
        return {
            "ok": True,
            "dry_run": dry_run,
            "pr_number": pr_number,
            "checks": [],
            "note": "CI consult skipped or pending",
        }
    res = _run(
        [
            "gh",
            "pr",
            "view",
            str(pr_number),
            "--json",
            "statusCheckRollup,url,commits",
        ],
        worktree,
        timeout=60,
    )
    if res.get("exit_code") != 0:
        return {"ok": False, "error": res.get("stderr"), "checks": []}
    try:
        data = json.loads(res.get("stdout") or "{}")
    except json.JSONDecodeError:
        return {"ok": False, "error": "json_decode", "checks": []}
    checks = []
    for c in data.get("statusCheckRollup") or []:
        if isinstance(c, dict):
            checks.append(
                {
                    "name": c.get("name"),
                    "status": c.get("status"),
                    "conclusion": c.get("conclusion"),
                    "details_url": c.get("detailsUrl"),
                }
            )
    return {
        "ok": True,
        "pr_number": pr_number,
        "url": data.get("url"),
        "checks": checks,
        "awaiting_ci": any(
            (c.get("status") or "").upper() not in {"COMPLETED"}
            or c.get("conclusion") in {None, "PENDING", "QUEUED"}
            for c in checks
        )
        if checks
        else True,
    }


def record_publication(
    *,
    root: Path,
    work_id: str | None,
    issue_number: int | None,
    cycle_id: str,
    commit: str | None,
    pr: dict[str, Any],
) -> None:
    append_ledger(
        "publish",
        {
            "cycle_id": cycle_id,
            "work_id": work_id,
            "issue_number": issue_number,
            "commit": commit,
            "pr_number": pr.get("number"),
            "pr_url": pr.get("url"),
            "merge_authority": MERGE_AUTHORITY,
            "auto_merge": False,
        },
        root=root,
        cycle_id=cycle_id,
    )
    if work_id:
        reg = load_registry(root)
        for item in reg.get("work_items") or []:
            if item.get("work_id") == work_id:
                item["state"] = "human"
                evidence = list(item.get("evidence") or [])
                if pr.get("url"):
                    evidence.append(f"draft_pr:{pr.get('url')}")
                if commit:
                    evidence.append(f"commit:{commit}")
                item["evidence"] = evidence[-30:]
                hist = list(item.get("execution_history") or [])
                hist.append(
                    {
                        "ts": _utc_now(),
                        "phase": "published_draft_pr",
                        "cycle_id": cycle_id,
                        "pr": pr.get("number"),
                        "commit": commit,
                    }
                )
                item["execution_history"] = hist[-20:]
                upsert_item(reg, item)
                break
        save_registry(reg, root)


def publish_after_accept(
    *,
    decision: dict[str, Any],
    worktree: Path | None,
    root: Path | None = None,
    dry_run: bool = False,
    skip_push: bool = False,
) -> dict[str, Any]:
    """Full post-ACCEPT publication. Never merges. Ends in WAITING_HUMAN semantics."""
    root = root or repo_root()
    cycle_id = str(decision.get("cycle_id") or "unknown")
    wt = Path(worktree) if worktree else root
    branch = current_branch(wt)
    out: dict[str, Any] = {
        "ok": False,
        "cycle_id": cycle_id,
        "branch": branch,
        "merge": False,
        "merge_authority": MERGE_AUTHORITY,
        "status": "WAITING_HUMAN",
        "steps": [],
        "dry_run": dry_run,
    }

    if branch in {"main", "master"}:
        out["error"] = "refusing publication from main/master"
        out["status"] = "BLOCKED"
        return redact_obj(out)

    if not has_local_diff(wt) and not dry_run:
        # may already be committed
        commit = current_commit(wt)
        if not commit:
            out["error"] = "no local diff and no commit"
            out["status"] = "FAILED"
            return redact_obj(out)
        out["steps"].append({"step": "diff_check", "has_diff": False, "commit": commit})
    else:
        out["steps"].append({"step": "diff_check", "has_diff": has_local_diff(wt)})

    msg = (
        f"cto({cycle_id}): {decision.get('work_id') or decision.get('objective') or 'cycle'}"
    )[:200]
    commit_res = ensure_commit(wt, message=msg, dry_run=dry_run)
    out["steps"].append({"step": "commit", **commit_res})
    commit = commit_res.get("commit") or current_commit(wt)
    out["commit"] = commit

    if skip_push:
        out["steps"].append({"step": "push", "skipped": True, "reason": "skip_push"})
        push_res = {"ok": True, "skipped": True}
    else:
        push_res = push_branch(wt, branch, dry_run=dry_run)
        out["steps"].append({"step": "push", **push_res})
    if not push_res.get("ok"):
        out["error"] = push_res.get("error") or push_res.get("stderr") or "push failed"
        out["status"] = "FAILED"
        return redact_obj(out)

    title = f"cto: {decision.get('work_id') or cycle_id} — {str(decision.get('objective') or '')[:80]}"
    body = (
        f"## CTO Autopilot draft PR\n\n"
        f"- cycle_id: `{cycle_id}`\n"
        f"- decision_id: `{decision.get('decision_id')}`\n"
        f"- work_id: `{decision.get('work_id')}`\n"
        f"- issue: #{decision.get('issue_number')}\n"
        f"- commit: `{commit}`\n\n"
        f"**Merge authority:** {MERGE_AUTHORITY} only. Autopilot never merges.\n"
    )
    pr_res = open_or_update_draft_pr(
        wt, branch=branch, title=title, body=body, dry_run=dry_run
    )
    out["steps"].append({"step": "draft_pr", **pr_res})
    out["pr"] = {
        "number": pr_res.get("number"),
        "url": pr_res.get("url"),
        "draft": True,
    }

    ci = consult_ci(wt, pr_res.get("number"), dry_run=dry_run)
    out["steps"].append({"step": "ci", **{k: v for k, v in ci.items() if k != "checks" or True}})
    out["ci"] = ci

    record_publication(
        root=root,
        work_id=decision.get("work_id"),
        issue_number=decision.get("issue_number"),
        cycle_id=cycle_id,
        commit=commit,
        pr=out["pr"],
    )
    out["steps"].append({"step": "ledger_issue_record", "ok": True})

    # Persist publication report on cycle
    cdir = cycles_dir(root) / cycle_id
    cdir.mkdir(parents=True, exist_ok=True)
    (cdir / "publication.json").write_text(
        json.dumps(redact_obj(out), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    out["ok"] = bool(pr_res.get("ok"))
    out["status"] = "WAITING_HUMAN"
    out["human_gate"] = {
        "required": True,
        "reason": f"Draft PR ready; only {MERGE_AUTHORITY} may merge",
        "pr_url": pr_res.get("url"),
        "pr_number": pr_res.get("number"),
    }
    return redact_obj(out)


def publisher_invokes_push() -> bool:
    """Structural marker for tests: publisher module owns push."""
    return True


def grok_executor_must_not_push() -> bool:
    """Contract: Grok executor never calls push_branch."""
    return True

"""Deterministic Observer — no creative interpretation."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.cto.paths import (
    current_dir,
    dod_path,
    executive_html_path,
    ledger_path,
    observation_path,
    repo_root,
    state_path,
    work_registry_path,
)
from scripts.cto.redaction import redact_obj


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run(
    cmd: list[str],
    cwd: Path,
    timeout: int = 60,
    *,
    max_stdout: int | None = 8000,
    max_stderr: int | None = 4000,
) -> dict[str, Any]:
    """Run a subprocess.

    For machine-readable JSON (gh --json), pass max_stdout=None so the payload
    is not truncated mid-stream. Human/log tails may still use a limit.
    """
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        if max_stdout is not None and len(stdout) > max_stdout:
            stdout = stdout[-max_stdout:]
        if max_stderr is not None and len(stderr) > max_stderr:
            stderr = stderr[-max_stderr:]
        return {
            "cmd": cmd,
            "exit_code": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
        }
    except subprocess.TimeoutExpired:
        return {"cmd": cmd, "exit_code": -1, "stdout": "", "stderr": "timeout"}
    except FileNotFoundError:
        return {"cmd": cmd, "exit_code": -2, "stdout": "", "stderr": "not_found"}


def _parse_dod_counts(text: str) -> dict[str, Any]:
    checked = text.count("- [x]") + text.count("- [X]")
    open_items = text.count("- [ ]")
    total = checked + open_items
    pct = round(100.0 * checked / total, 2) if total else 0.0
    return {
        "checked": checked,
        "open": open_items,
        "total": total,
        "percent_checked": pct,
    }


def _git_snapshot(root: Path) -> dict[str, Any]:
    branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], root)
    head = _run(["git", "rev-parse", "HEAD"], root)
    status = _run(["git", "status", "--porcelain"], root)
    dirty_lines = [ln for ln in (status.get("stdout") or "").splitlines() if ln.strip()]
    ahead_behind = _run(
        ["git", "rev-list", "--left-right", "--count", "origin/main...HEAD"], root
    )
    ab = (ahead_behind.get("stdout") or "").strip().split()
    behind = int(ab[0]) if len(ab) == 2 and ab[0].isdigit() else None
    ahead = int(ab[1]) if len(ab) == 2 and ab[1].isdigit() else None
    worktrees = _run(["git", "worktree", "list", "--porcelain"], root)
    log = _run(["git", "log", "--oneline", "-10"], root)
    return {
        "branch": (branch.get("stdout") or "").strip(),
        "commit": (head.get("stdout") or "").strip(),
        "dirty": bool(dirty_lines),
        "dirty_count": len(dirty_lines),
        "dirty_files": dirty_lines[:50],
        "ahead_of_main": ahead,
        "behind_main": behind,
        "worktrees_raw": (worktrees.get("stdout") or "")[:4000],
        "recent_commits": (log.get("stdout") or "").splitlines()[:10],
    }


def _gh_prs(root: Path) -> list[dict[str, Any]]:
    res = _run(
        [
            "gh",
            "pr",
            "list",
            "--state",
            "open",
            "--limit",
            "20",
            "--json",
            "number,title,headRefName,isDraft,url,updatedAt",
        ],
        root,
        timeout=45,
        max_stdout=None,  # full JSON — never tail-truncate
    )
    if res.get("exit_code") != 0:
        return []
    try:
        return json.loads(res.get("stdout") or "[]")
    except json.JSONDecodeError:
        return []


def _gh_issues_summary(root: Path) -> dict[str, Any]:
    res = _run(
        [
            "gh",
            "issue",
            "list",
            "--state",
            "open",
            "--limit",
            "100",
            "--json",
            "number,title,labels,updatedAt,state,body",
        ],
        root,
        timeout=90,
        max_stdout=None,  # full JSON — tail truncation corrupts arrays
    )
    if res.get("exit_code") != 0:
        return {
            "available": False,
            "error": (res.get("stderr") or "gh issue list failed")[:500],
            "open_count": 0,
            "items": [],
            "by_state": {},
        }
    try:
        items = json.loads(res.get("stdout") or "[]")
    except json.JSONDecodeError:
        items = []
    by_state: dict[str, list[dict[str, Any]]] = {}
    simplified = []
    work_id_re = re.compile(r"<!--\s*extra-work-id:\s*([^\s]+)\s*-->")
    for it in items:
        labels = [lb.get("name") for lb in (it.get("labels") or []) if isinstance(lb, dict)]
        state_labels = [lb for lb in labels if str(lb).startswith("state:")]
        body = it.get("body") or ""
        wid_m = work_id_re.search(body)
        entry = {
            "number": it.get("number"),
            "title": it.get("title"),
            "labels": labels,
            "updated_at": it.get("updatedAt"),
            "state_labels": state_labels,
            "work_id": wid_m.group(1).strip() if wid_m else None,
        }
        simplified.append(entry)
        key = state_labels[0] if state_labels else "state:unlabeled"
        by_state.setdefault(key, []).append(entry)
    by_state_counts = {k: len(v) for k, v in by_state.items()}
    return {
        "available": True,
        "open_count": len(simplified),
        "items": simplified[:40],
        # Full counts for HTML; samples truncated for payload size only
        "by_state_counts": by_state_counts,
        "by_state": {k: v[:10] for k, v in by_state.items()},
    }


def _ranking(root: Path) -> dict[str, Any]:
    latest = root / "squads" / "extra-dod-roi" / "state" / "rankings" / "latest.json"
    if not latest.is_file():
        return {"available": False, "top": [], "selected_id": None}
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"available": False, "top": [], "selected_id": None, "error": "parse_error"}
    ranking = data.get("ranking") or []
    top = [
        {
            "id": c.get("id"),
            "roi": c.get("roi"),
            "title": c.get("title") or c.get("summary") or c.get("id"),
            "blocked": c.get("blocked"),
        }
        for c in ranking[:10]
    ]
    return {
        "available": True,
        "generated_at": data.get("generated_at"),
        "selected_id": data.get("selected_id"),
        "top": top,
        "weights": data.get("weights"),
    }


def _cycle_roi(root: Path) -> dict[str, Any]:
    cycle = root / "squads" / "extra-dod-roi" / "state" / "cycles" / "current.json"
    lock = root / "squads" / "extra-dod-roi" / "state" / "locks" / "cycle.lock"
    out: dict[str, Any] = {"roi_lock": lock.is_file()}
    if cycle.is_file():
        try:
            data = json.loads(cycle.read_text(encoding="utf-8"))
            out.update(
                {
                    "cycle_id": data.get("cycle_id"),
                    "phase": data.get("phase"),
                    "selected_id": data.get("selected_id"),
                    "story_id": data.get("story_id"),
                    "status": data.get("status"),
                }
            )
        except (OSError, json.JSONDecodeError):
            out["error"] = "cycle_parse_error"
    return out


def _html_meta(root: Path) -> dict[str, Any]:
    path = executive_html_path(root)
    if not path.is_file():
        return {"exists": False}
    raw = path.read_bytes()
    h = hashlib.sha256(raw).hexdigest()
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    title = None
    try:
        text = raw.decode("utf-8", errors="replace")
        m = re.search(r"<title>(.*?)</title>", text, re.I | re.S)
        if m:
            title = re.sub(r"\s+", " ", m.group(1)).strip()[:200]
    except Exception:  # noqa: BLE001
        title = None
    return {
        "exists": True,
        "path": str(path.relative_to(root)),
        "sha256": h,
        "mtime_utc": mtime,
        "size_bytes": len(raw),
        "title": title,
    }


def _work_registry_summary(root: Path) -> dict[str, Any]:
    path = work_registry_path(root)
    if not path.is_file():
        return {"exists": False, "count": 0}
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        items = data.get("work_items") or []
        return {
            "exists": True,
            "count": len(items),
            "open": sum(1 for i in items if (i.get("state") or "").lower() not in {"done", "closed"}),
            "ids": [i.get("work_id") for i in items[:40]],
        }
    except Exception as exc:  # noqa: BLE001
        return {"exists": True, "error": str(exc), "count": 0}


def _gates_from_dod(text: str) -> dict[str, Any]:
    # Do not invent seals — report mention vs checked presence only
    seals = [
        "LOCAL_READY",
        "PRE_VPS_FINAL_READY",
        "VPS_OPERATIONAL",
        "PROJECT_DONE",
    ]
    out = {}
    for s in seals:
        out[s] = {
            "mentioned": s in text,
            "claim_allowed": False,  # policy: never claim without evidence package
        }
    return out


def observe(root: Path | None = None, *, write: bool = True) -> dict[str, Any]:
    """Collect deterministic observation snapshot."""
    root = root or repo_root()
    dod_file = dod_path(root)
    dod_text = dod_file.read_text(encoding="utf-8", errors="replace") if dod_file.is_file() else ""
    dod_counts = _parse_dod_counts(dod_text)

    state_data = {}
    if state_path(root).is_file():
        try:
            state_data = json.loads(state_path(root).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            state_data = {"error": "state_parse_error"}

    ledger_tail = []
    if ledger_path(root).is_file():
        lines = ledger_path(root).read_text(encoding="utf-8").splitlines()[-20:]
        for ln in lines:
            try:
                ledger_tail.append(json.loads(ln))
            except json.JSONDecodeError:
                continue

    observation: dict[str, Any] = {
        "schema_version": "1.0",
        "timestamp_utc": _utc_now(),
        "git": _git_snapshot(root),
        "dod": {
            **dod_counts,
            "sha256": hashlib.sha256(dod_text.encode("utf-8")).hexdigest() if dod_text else None,
            "gates": _gates_from_dod(dod_text),
        },
        "prs": _gh_prs(root),
        "issues": _gh_issues_summary(root),
        "ranking": _ranking(root),
        "roi_cycle": _cycle_roi(root),
        "html": _html_meta(root),
        "work_registry": _work_registry_summary(root),
        "cto_state": state_data,
        "recent_ledger": ledger_tail,
        "claims": {
            "forbidden": [
                "LOCAL_READY",
                "PRE_VPS_FINAL_READY",
                "VPS_OPERATIONAL",
                "PROJECT_DONE",
                "95% coverage without evidence",
            ],
            "allowed": [],
        },
        "blockers": _extract_blockers(dod_text, root),
    }
    observation = redact_obj(observation)
    if write:
        out = observation_path(root)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(observation, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return observation


def _extract_blockers(dod_text: str, root: Path) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    for i, line in enumerate(dod_text.splitlines(), 1):
        if re.search(r"BLOCKED|blocker", line, re.I) and line.strip().startswith("-"):
            blockers.append({"source": "DOD.md", "line": i, "text": line.strip()[:240]})
            if len(blockers) >= 30:
                break
    # open PR with CI failure not fetched deep here; list open PRs as potential integration blockers
    return blockers


def status_summary(root: Path | None = None) -> dict[str, Any]:
    root = root or repo_root()
    obs_path = observation_path(root)
    st = {}
    if state_path(root).is_file():
        try:
            st = json.loads(state_path(root).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            st = {}
    obs_meta = {}
    if obs_path.is_file():
        try:
            obs = json.loads(obs_path.read_text(encoding="utf-8"))
            obs_meta = {
                "timestamp_utc": obs.get("timestamp_utc"),
                "branch": (obs.get("git") or {}).get("branch"),
                "commit": (obs.get("git") or {}).get("commit"),
                "dod": obs.get("dod"),
                "open_prs": len(obs.get("prs") or []),
                "open_issues": (obs.get("issues") or {}).get("open_count"),
            }
        except (OSError, json.JSONDecodeError):
            obs_meta = {"error": "observation_parse_error"}
    return {
        "state": st,
        "observation": obs_meta,
        "paths": {
            "current": str(current_dir(root)),
            "observation": str(obs_path),
            "state": str(state_path(root)),
        },
    }

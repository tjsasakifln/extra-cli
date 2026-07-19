"""Deterministic Observer — no creative interpretation."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from scripts.cto.paths import (
    current_dir,
    cycles_dir,
    dod_path,
    executive_html_path,
    ledger_path,
    observation_path,
    repo_root,
    state_path,
    work_registry_path,
)
from scripts.cto.redaction import redact_obj
from scripts.cto.work_registry import (
    load_registry,
    readiness_for_item,
    work_item_public_view,
)

# Ranking older than this is marked stale (must refresh or flag before decide)
RANKING_STALE_SECONDS = 6 * 3600


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


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
        "worktrees": _parse_worktrees(worktrees.get("stdout") or ""),
        "recent_commits": (log.get("stdout") or "").splitlines()[:10],
    }


def _parse_worktrees(raw: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    cur: dict[str, Any] = {}
    for ln in raw.splitlines():
        if not ln.strip():
            if cur:
                items.append(cur)
                cur = {}
            continue
        if ln.startswith("worktree "):
            if cur:
                items.append(cur)
            cur = {"path": ln[len("worktree ") :].strip()}
        elif ln.startswith("HEAD "):
            cur["head"] = ln[len("HEAD ") :].strip()
        elif ln.startswith("branch "):
            cur["branch"] = ln[len("branch ") :].strip()
        elif ln == "bare":
            cur["bare"] = True
        elif ln == "detached":
            cur["detached"] = True
    if cur:
        items.append(cur)
    return items[:30]


def _summarize_checks(rollup: list[Any] | None) -> dict[str, Any]:
    checks = []
    failed_jobs: list[dict[str, Any]] = []
    conclusions = set()
    for c in rollup or []:
        if not isinstance(c, dict):
            continue
        entry = {
            "name": c.get("name"),
            "status": c.get("status"),
            "conclusion": c.get("conclusion"),
            "details_url": c.get("detailsUrl"),
            "workflow": c.get("workflowName"),
            "started_at": c.get("startedAt"),
            "completed_at": c.get("completedAt"),
        }
        checks.append(entry)
        conclusions.add(str(c.get("conclusion") or c.get("status") or "").upper())
        if str(c.get("conclusion") or "").upper() in {"FAILURE", "TIMED_OUT", "CANCELLED", "ERROR"}:
            failed_jobs.append(
                {
                    "job": c.get("name"),
                    "conclusion": c.get("conclusion"),
                    "failed_steps": [c.get("name")],  # rollup has job-level names
                    "details_url": c.get("detailsUrl"),
                    "workflow": c.get("workflowName"),
                }
            )
    overall = "UNKNOWN"
    if not checks:
        overall = "NO_CHECKS"
    elif any(x in conclusions for x in ("FAILURE", "TIMED_OUT", "ERROR")):
        overall = "FAILURE"
    elif "SUCCESS" in conclusions and all(
        str(c.get("conclusion") or "").upper() in {"SUCCESS", "SKIPPED", "NEUTRAL", ""}
        or str(c.get("status") or "").upper() == "COMPLETED"
        for c in checks
    ):
        # pending?
        if any(str(c.get("status") or "").upper() not in {"COMPLETED", ""} for c in checks):
            overall = "PENDING"
        else:
            overall = "SUCCESS"
    elif any(str(c.get("status") or "").upper() in {"IN_PROGRESS", "QUEUED", "PENDING"} for c in checks):
        overall = "PENDING"
    return {
        "overall": overall,
        "checks": checks,
        "failed_jobs": failed_jobs,
        "failed_job_names": [f["job"] for f in failed_jobs],
        "failed_step_names": [s for f in failed_jobs for s in (f.get("failed_steps") or [])],
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
            "number,title,headRefName,baseRefName,isDraft,url,updatedAt,"
            "statusCheckRollup,commits,headRefOid,body",
        ],
        root,
        timeout=90,
        max_stdout=None,
    )
    if res.get("exit_code") != 0:
        return []
    try:
        raw_items = json.loads(res.get("stdout") or "[]")
    except json.JSONDecodeError:
        return []
    out = []
    for it in raw_items:
        commits = it.get("commits") or []
        head_oid = it.get("headRefOid")
        if not head_oid and commits:
            last = commits[-1] if isinstance(commits[-1], dict) else {}
            head_oid = last.get("oid") or (last.get("commit") or {}).get("oid")
        ci = _summarize_checks(it.get("statusCheckRollup"))
        out.append(
            {
                "number": it.get("number"),
                "title": it.get("title"),
                "head_ref": it.get("headRefName"),
                "base_ref": it.get("baseRefName"),
                "branch": it.get("headRefName"),
                "commit": head_oid,
                "is_draft": it.get("isDraft"),
                "url": it.get("url"),
                "updated_at": it.get("updatedAt"),
                "ci": ci,
                "ci_status": ci.get("overall"),
                "ci_conclusion": ci.get("overall"),
                "failed_jobs": ci.get("failed_jobs"),
                "failed_job_names": ci.get("failed_job_names"),
                "failed_step_names": ci.get("failed_step_names"),
                "body_excerpt": (it.get("body") or "")[:400],
            }
        )
    return out


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
        max_stdout=None,
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
            "body_excerpt": body[:500],
        }
        simplified.append(entry)
        key = state_labels[0] if state_labels else "state:unlabeled"
        by_state.setdefault(key, []).append(entry)
    by_state_counts = {k: len(v) for k, v in by_state.items()}
    return {
        "available": True,
        "open_count": len(simplified),
        "items": simplified[:40],
        "by_state_counts": by_state_counts,
        "by_state": {k: v[:10] for k, v in by_state.items()},
    }


def _parse_generated_at(raw: Any) -> datetime | None:
    if not raw:
        return None
    if isinstance(raw, (int, float)):
        try:
            return datetime.fromtimestamp(float(raw), tz=UTC)
        except (OSError, ValueError, OverflowError):
            return None
    s = str(raw).strip()
    for fmt in (
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            if fmt.endswith("%z") and s.endswith("Z"):
                s2 = s[:-1] + "+0000"
                return datetime.strptime(s2, "%Y-%m-%dT%H:%M:%S%z")
            return datetime.strptime(s, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def ranking_freshness(root: Path, *, max_age_seconds: int = RANKING_STALE_SECONDS) -> dict[str, Any]:
    """Compute ranking freshness from latest.json mtime/generated_at."""
    latest = root / "squads" / "extra-dod-roi" / "state" / "rankings" / "latest.json"
    if not latest.is_file():
        return {
            "available": False,
            "stale": True,
            "reason": "latest.json missing",
            "path": str(latest),
            "max_age_seconds": max_age_seconds,
        }
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "available": False,
            "stale": True,
            "reason": f"parse_error: {exc}",
            "path": str(latest),
        }
    mtime = datetime.fromtimestamp(latest.stat().st_mtime, tz=UTC)
    generated = _parse_generated_at(data.get("generated_at") or data.get("timestamp"))
    ref = generated or mtime
    age = (datetime.now(UTC) - ref).total_seconds()
    stale = age > max_age_seconds
    return {
        "available": True,
        "stale": stale,
        "age_seconds": int(age),
        "max_age_seconds": max_age_seconds,
        "generated_at": data.get("generated_at"),
        "mtime_utc": mtime.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "path": str(latest.relative_to(root)) if latest.is_relative_to(root) else str(latest),
        "selected_id": data.get("selected_id"),
        "reason": "stale ranking" if stale else "fresh",
    }


def ensure_ranking_current(
    root: Path,
    *,
    max_age_seconds: int = RANKING_STALE_SECONDS,
    try_refresh: bool = True,
) -> dict[str, Any]:
    """Refresh ranking before decide, or mark explicitly stale.

    Never treat old latest.json as current without flagging.
    """
    info = ranking_freshness(root, max_age_seconds=max_age_seconds)
    if info.get("available") and not info.get("stale"):
        return {**info, "refreshed": False, "used_as_current": True}
    refreshed = False
    refresh_error = None
    if try_refresh and (root / "squads" / "extra-dod-roi" / "scripts" / "cli.py").is_file():
        res = _run(
            [
                "python3",
                "squads/extra-dod-roi/scripts/cli.py",
                "rank-next",
            ],
            root,
            timeout=180,
            max_stdout=4000,
        )
        refreshed = res.get("exit_code") == 0
        if not refreshed:
            refresh_error = (res.get("stderr") or res.get("stdout") or "rank-next failed")[:500]
        info = ranking_freshness(root, max_age_seconds=max_age_seconds)
    return {
        **info,
        "refreshed": refreshed,
        "refresh_error": refresh_error,
        "used_as_current": bool(info.get("available") and not info.get("stale")),
        "explicitly_stale": bool(info.get("stale")),
    }


def _ranking(root: Path) -> dict[str, Any]:
    latest = root / "squads" / "extra-dod-roi" / "state" / "rankings" / "latest.json"
    freshness = ranking_freshness(root)
    if not latest.is_file():
        return {
            "available": False,
            "top": [],
            "selected_id": None,
            "freshness": freshness,
            "stale": True,
        }
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "available": False,
            "top": [],
            "selected_id": None,
            "error": "parse_error",
            "freshness": freshness,
            "stale": True,
        }
    ranking = data.get("ranking") or []
    top = [
        {
            "id": c.get("id"),
            "roi": c.get("roi"),
            "title": c.get("title") or c.get("summary") or c.get("id"),
            "blocked": c.get("blocked"),
            "score": c.get("score"),
            "reasons": c.get("reasons") or c.get("why") or [],
        }
        for c in ranking[:10]
    ]
    return {
        "available": True,
        "generated_at": data.get("generated_at"),
        "selected_id": data.get("selected_id"),
        "top": top,
        "weights": data.get("weights"),
        "freshness": freshness,
        "stale": bool(freshness.get("stale")),
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


def _active_cto_cycles(root: Path) -> list[dict[str, Any]]:
    cdir = cycles_dir(root)
    if not cdir.is_dir():
        return []
    items = []
    for child in sorted(cdir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)[:15]:
        if not child.is_dir():
            continue
        entry: dict[str, Any] = {
            "cycle_id": child.name,
            "path": str(child.relative_to(root)) if child.is_relative_to(root) else str(child),
            "artifacts": sorted(p.name for p in child.iterdir() if p.is_file())[:20],
        }
        for name in ("decision.json", "execution.json", "verification.json", "review.json", "publication.json"):
            fp = child / name
            if fp.is_file():
                try:
                    data = json.loads(fp.read_text(encoding="utf-8"))
                    if name == "decision.json":
                        entry["decision"] = data.get("decision")
                        entry["work_id"] = data.get("work_id")
                    elif name == "execution.json":
                        entry["execution_status"] = data.get("status")
                    elif name == "verification.json":
                        entry["verify_result"] = data.get("result")
                    elif name == "review.json":
                        entry["review_verdict"] = data.get("verdict")
                    elif name == "publication.json":
                        entry["pr"] = (data.get("pr") or {}).get("url")
                except (OSError, json.JSONDecodeError):
                    entry[f"{name}_error"] = "parse_error"
        items.append(entry)
    return items


def _recent_tests(root: Path) -> dict[str, Any]:
    """Scan cycle artifacts and common pytest caches for recent test evidence."""
    evidence: list[dict[str, Any]] = []
    cdir = cycles_dir(root)
    if cdir.is_dir():
        for child in sorted(cdir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)[:10]:
            ver = child / "verification.json"
            if ver.is_file():
                try:
                    data = json.loads(ver.read_text(encoding="utf-8"))
                    for chk in data.get("checks") or []:
                        if chk.get("name") == "tests":
                            evidence.append(
                                {
                                    "cycle_id": child.name,
                                    "source": "verification.json",
                                    "results": [
                                        {
                                            "cmd": r.get("cmd"),
                                            "exit_code": r.get("exit_code"),
                                        }
                                        for r in (chk.get("results") or [])[:10]
                                    ],
                                    "overall": data.get("result"),
                                    "mtime_utc": datetime.fromtimestamp(
                                        ver.stat().st_mtime, tz=UTC
                                    ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                }
                            )
                except (OSError, json.JSONDecodeError):
                    continue
    # pytest cache lastfailed if present
    lastfailed = root / ".pytest_cache" / "v" / "cache" / "lastfailed"
    lastfailed_data = None
    if lastfailed.is_file():
        try:
            lastfailed_data = json.loads(lastfailed.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            lastfailed_data = {"error": "parse_error"}
    return {
        "cycle_test_evidence": evidence[:10],
        "pytest_lastfailed": lastfailed_data
        if isinstance(lastfailed_data, dict)
        else {"present": bool(lastfailed_data)},
    }


def _html_meta(root: Path) -> dict[str, Any]:
    path = executive_html_path(root)
    if not path.is_file():
        return {"exists": False}
    raw = path.read_bytes()
    h = hashlib.sha256(raw).hexdigest()
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
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


def _work_items_full(root: Path) -> dict[str, Any]:
    """Full work items for CTO decision context (not IDs/titles alone)."""
    registry = load_registry(root)
    items = []
    ready_ids = []
    blocked_ids = []
    for raw in registry.get("work_items") or []:
        view = work_item_public_view(raw)
        ready_info = readiness_for_item(raw, registry)
        view["readiness"] = ready_info
        if ready_info.get("ready"):
            ready_ids.append(view.get("work_id"))
        else:
            if (raw.get("state") or "").lower() in {"ready", "in_progress", "in-progress"}:
                blocked_ids.append(
                    {
                        "work_id": view.get("work_id"),
                        "reasons": ready_info.get("reasons"),
                    }
                )
        items.append(view)
    return {
        "exists": work_registry_path(root).is_file(),
        "count": len(items),
        "open": sum(
            1 for i in items if (i.get("state") or "").lower() not in {"done", "closed"}
        ),
        "ready_ids": ready_ids,
        "not_ready": blocked_ids[:30],
        "items": items[:40],
        "ids": [i.get("work_id") for i in items[:40]],
    }


def _work_registry_summary(root: Path) -> dict[str, Any]:
    full = _work_items_full(root)
    return {
        "exists": full.get("exists"),
        "count": full.get("count"),
        "open": full.get("open"),
        "ids": full.get("ids"),
        "ready_ids": full.get("ready_ids"),
        "not_ready_count": len(full.get("not_ready") or []),
    }


def _ops_freshness_evidence(root: Path) -> dict[str, Any]:
    paths = [
        root / "output" / "cto" / "current" / "observation.json",
        root / "squads" / "extra-dod-roi" / "state" / "rankings" / "latest.json",
        root / "output" / "cto" / "current" / "state.json",
        root / "output" / "cto" / "current" / "ledger.jsonl",
    ]
    files = []
    for p in paths:
        if p.is_file():
            files.append(
                {
                    "path": str(p.relative_to(root)) if p.is_relative_to(root) else str(p),
                    "mtime_utc": datetime.fromtimestamp(p.stat().st_mtime, tz=UTC).strftime(
                        "%Y-%m-%dT%H:%M:%SZ"
                    ),
                    "size_bytes": p.stat().st_size,
                    "sha256": hashlib.sha256(p.read_bytes()[:200_000]).hexdigest(),
                }
            )
        else:
            files.append({"path": str(p), "exists": False})
    return {"files": files}


def _divergences(
    root: Path,
    *,
    git: dict[str, Any],
    dod: dict[str, Any],
    prs: list[dict[str, Any]],
    issues: dict[str, Any],
    html: dict[str, Any],
) -> list[dict[str, Any]]:
    divs: list[dict[str, Any]] = []
    if git.get("behind_main") and int(git.get("behind_main") or 0) > 0:
        divs.append(
            {
                "kind": "branch_behind_main",
                "detail": f"HEAD behind origin/main by {git.get('behind_main')}",
                "branch": git.get("branch"),
                "commit": git.get("commit"),
            }
        )
    if git.get("dirty"):
        divs.append(
            {
                "kind": "dirty_worktree",
                "detail": f"{git.get('dirty_count')} dirty paths",
                "sample": (git.get("dirty_files") or [])[:10],
            }
        )
    for pr in prs:
        if pr.get("ci_status") == "FAILURE":
            divs.append(
                {
                    "kind": "pr_ci_failure",
                    "pr": pr.get("number"),
                    "branch": pr.get("branch"),
                    "commit": pr.get("commit"),
                    "failed_jobs": pr.get("failed_job_names"),
                    "url": pr.get("url"),
                }
            )
    # Issues labeled ready vs registry readiness later filled by work_items
    ready_issues = len((issues.get("by_state") or {}).get("state:ready") or [])
    if ready_issues and any(pr.get("ci_status") == "FAILURE" for pr in prs):
        divs.append(
            {
                "kind": "ready_queue_with_red_ci",
                "detail": f"{ready_issues} state:ready issues while open PR CI is red",
            }
        )
    if html.get("exists") and dod.get("percent_checked") is not None:
        # HTML is projection — flag if mtime much older than observation moment
        try:
            html_mtime = datetime.strptime(html["mtime_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=UTC
            )
            if datetime.now(UTC) - html_mtime > timedelta(days=7):
                divs.append(
                    {
                        "kind": "html_stale",
                        "detail": f"executive HTML mtime {html.get('mtime_utc')}",
                    }
                )
        except (KeyError, ValueError):
            pass
    return divs[:40]


def _gates_from_dod(text: str) -> dict[str, Any]:
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
            "claim_allowed": False,
        }
    return out


def observe(root: Path | None = None, *, write: bool = True) -> dict[str, Any]:
    """Collect deterministic observation snapshot with full decision context."""
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

    git = _git_snapshot(root)
    prs = _gh_prs(root)
    issues = _gh_issues_summary(root)
    html = _html_meta(root)
    ranking = _ranking(root)
    work_items = _work_items_full(root)
    dod_block = {
        **dod_counts,
        "sha256": hashlib.sha256(dod_text.encode("utf-8")).hexdigest() if dod_text else None,
        "gates": _gates_from_dod(dod_text),
    }

    observation: dict[str, Any] = {
        "schema_version": "1.1",
        "timestamp_utc": _utc_now(),
        "git": git,
        "dod": dod_block,
        "prs": prs,
        "issues": issues,
        "ranking": ranking,
        "roi_cycle": _cycle_roi(root),
        "html": html,
        "work_registry": _work_registry_summary(root),
        "work_items": work_items,
        "active_cycles": _active_cto_cycles(root),
        "recent_tests": _recent_tests(root),
        "ops_freshness": _ops_freshness_evidence(root),
        "divergences": _divergences(
            root, git=git, dod=dod_block, prs=prs, issues=issues, html=html
        ),
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
                "ranking_stale": (obs.get("ranking") or {}).get("stale"),
                "divergences": len(obs.get("divergences") or []),
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

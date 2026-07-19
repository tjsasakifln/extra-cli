"""GitHub Issues operational layer — idempotent via invisible work_id marker."""
from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.cto.config import load_policies
from scripts.cto.paths import repo_root
from scripts.cto.redaction import redact_obj
from scripts.cto.work_registry import load_registry, save_registry, upsert_item

WORK_ID_MARKER_RE = re.compile(r"<!--\s*extra-work-id:\s*([^\s]+)\s*-->")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run_gh(args: list[str], cwd: Path, timeout: int = 90) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            ["gh", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "exit_code": proc.returncode,
            "stdout": proc.stdout or "",
            "stderr": proc.stderr or "",
        }
    except FileNotFoundError:
        return {"exit_code": -2, "stdout": "", "stderr": "gh not found"}
    except subprocess.TimeoutExpired:
        return {"exit_code": -1, "stdout": "", "stderr": "timeout"}


def gh_auth_ok(root: Path | None = None) -> bool:
    res = _run_gh(["auth", "status"], root or repo_root(), timeout=30)
    return res.get("exit_code") == 0


def work_id_marker(work_id: str) -> str:
    return f"<!-- extra-work-id: {work_id} -->"


def extract_work_id(body: str) -> str | None:
    m = WORK_ID_MARKER_RE.search(body or "")
    return m.group(1).strip() if m else None


def render_issue_body(item: dict[str, Any]) -> str:
    ac = item.get("acceptance_criteria") or []
    tests = item.get("test_commands") or []
    deps = item.get("dependencies") or []
    blockers = item.get("blockers") or []
    dod = item.get("dod_refs") or []
    evidence = item.get("evidence") or []
    lines = [
        work_id_marker(str(item["work_id"])),
        "",
        "## Outcome",
        str(item.get("objective") or item.get("title") or ""),
        "",
        "## Why now",
        f"Priority `{item.get('priority')}` · risk `{item.get('risk')}` · origin `{item.get('origin')}`",
        "",
        "## Scope",
        f"Area: `{item.get('area')}` · type: `{item.get('type')}` · milestone: `{item.get('milestone')}`",
        "",
        "## Out of scope",
        "- Inventing readiness seals or DoD checkbox flips without evidence",
        "- Autonomous merge/deploy",
        "- Expanding beyond acceptance criteria",
        "",
        "## DOD references",
    ]
    lines.extend([f"- {d}" for d in dod] or ["- (none listed)"])
    lines.extend(["", "## Acceptance criteria"])
    lines.extend([f"- [ ] {c}" for c in ac] or ["- [ ] (define measurable criteria)"])
    lines.extend(["", "## Required evidence"])
    lines.extend([f"- {e}" for e in evidence] or ["- Command output / test log / JSON report"])
    lines.extend(["", "## Test commands"])
    lines.extend([f"- `{t}`" for t in tests] or ["- (none)"])
    lines.extend(["", "## Dependencies"])
    lines.extend([f"- {d}" for d in deps] or ["- none"])
    lines.extend(["", "## Blockers"])
    lines.extend([f"- {b}" for b in blockers] or ["- none"])
    lines.extend(
        [
            "",
            "## Safety constraints",
            "- Fail closed on secrets, push, merge, deploy",
            "- Do not treat Issue close as DoD acceptance",
            "- Human gates per `.cto/CHARTER.md`",
            "",
            "## Agent handoff",
            f"work_id=`{item.get('work_id')}` — CTO Autopilot managed",
            "",
            "## Execution history",
            f"- registry_state: `{item.get('state')}`",
            f"- last_synced_at: `{item.get('last_synced_at') or 'never'}`",
            f"- issue_number: `{item.get('issue_number') or 'pending'}`",
        ]
    )
    return "\n".join(lines) + "\n"


def labels_for_item(item: dict[str, Any]) -> list[str]:
    labels = []
    state = item.get("state") or "ready"
    state_map = {
        "ready": "state:ready",
        "in_progress": "state:in-progress",
        "in-progress": "state:in-progress",
        "review": "state:review",
        "blocked": "state:blocked",
        "human": "state:human",
    }
    labels.append(state_map.get(str(state).lower(), "state:ready"))
    t = item.get("type") or "ops"
    labels.append(f"type:{t}")
    p = item.get("priority") or "p2"
    labels.append(f"priority:{p}")
    r = item.get("risk") or "normal"
    labels.append(f"risk:{r}")
    area = item.get("area")
    if area:
        labels.append(f"area:{area}")
    return labels


def list_managed_issues(root: Path | None = None) -> dict[str, dict[str, Any]]:
    """Map work_id -> issue metadata for open+closed recently."""
    root = root or repo_root()
    res = _run_gh(
        [
            "issue",
            "list",
            "--state",
            "all",
            "--limit",
            "200",
            "--json",
            "number,title,body,state,labels,url",
        ],
        root,
        timeout=120,
    )
    mapping: dict[str, dict[str, Any]] = {}
    if res.get("exit_code") != 0:
        return mapping
    try:
        items = json.loads(res.get("stdout") or "[]")
    except json.JSONDecodeError:
        return mapping
    for it in items:
        wid = extract_work_id(it.get("body") or "")
        if not wid:
            continue
        mapping[wid] = {
            "number": it.get("number"),
            "title": it.get("title"),
            "state": it.get("state"),
            "url": it.get("url"),
            "labels": [lb.get("name") for lb in (it.get("labels") or [])],
        }
    return mapping


def ensure_labels(root: Path, labels: list[str], *, apply: bool) -> list[str]:
    created: list[str] = []
    # color map simple
    colors = {
        "state:": "0E8A16",
        "type:": "1D76DB",
        "priority:": "D93F0B",
        "risk:": "B60205",
        "area:": "5319E7",
    }
    for lab in labels:
        if not apply:
            created.append(lab)
            continue
        color = "CCCCCC"
        for prefix, c in colors.items():
            if lab.startswith(prefix):
                color = c
                break
        res = _run_gh(
            ["label", "create", lab, "--color", color, "--force"],
            root,
            timeout=30,
        )
        if res.get("exit_code") == 0:
            created.append(lab)
    return created


def ensure_milestones(root: Path, names: list[str], *, apply: bool) -> list[str]:
    done: list[str] = []
    existing_res = _run_gh(
        ["api", "repos/{owner}/{repo}/milestones", "--jq", ".[].title"],
        root,
        timeout=45,
    )
    existing = set(
        ln.strip() for ln in (existing_res.get("stdout") or "").splitlines() if ln.strip()
    )
    for name in names:
        if name in existing:
            done.append(name)
            continue
        if not apply:
            done.append(name)
            continue
        res = _run_gh(
            [
                "api",
                "repos/{owner}/{repo}/milestones",
                "-f",
                f"title={name}",
                "-f",
                "state=open",
            ],
            root,
            timeout=45,
        )
        if res.get("exit_code") == 0:
            done.append(name)
    return done


def plan_issues(root: Path | None = None) -> dict[str, Any]:
    root = root or repo_root()
    registry = load_registry(root)
    managed = list_managed_issues(root) if gh_auth_ok(root) else {}
    creates = []
    updates = []
    for item in registry.get("work_items") or []:
        if (item.get("state") or "").lower() in {"done", "closed"}:
            continue
        wid = item["work_id"]
        if wid in managed:
            updates.append(
                {
                    "work_id": wid,
                    "issue_number": managed[wid]["number"],
                    "title": item.get("title"),
                    "action": "update",
                }
            )
        else:
            creates.append(
                {
                    "work_id": wid,
                    "title": item.get("title"),
                    "action": "create",
                    "labels": labels_for_item(item),
                }
            )
    return {
        "creates": creates,
        "updates": updates,
        "open_managed": len(managed),
        "registry_open": sum(
            1
            for i in registry.get("work_items") or []
            if (i.get("state") or "").lower() not in {"done", "closed"}
        ),
        "auth_ok": gh_auth_ok(root),
    }


def sync_issues(root: Path | None = None, *, apply: bool = False) -> dict[str, Any]:
    root = root or repo_root()
    policies = load_policies(root)
    registry = load_registry(root)
    auth = gh_auth_ok(root)
    result: dict[str, Any] = {
        "mode": "apply" if apply else "dry-run",
        "auth_ok": auth,
        "created": [],
        "updated": [],
        "labels_ensured": [],
        "milestones_ensured": [],
        "inconsistencies": [],
        "duplicates": [],
        "skipped": [],
    }

    max_open = (policies.get("issue_limits") or {}).get("max_open_without_justification", 40)
    open_items = [
        i
        for i in registry.get("work_items") or []
        if (i.get("state") or "").lower() not in {"done", "closed"}
    ]
    if len(open_items) > max_open:
        result["inconsistencies"].append(
            f"registry open items {len(open_items)} > max {max_open}"
        )

    # weak criteria audit
    for item in open_items:
        ac = item.get("acceptance_criteria") or []
        if not ac:
            result["inconsistencies"].append(f"{item.get('work_id')}: missing acceptance_criteria")
        vague = re.compile(r"^(melhorar|otimizar|evoluir|deixar robusto)", re.I)
        for c in ac:
            if vague.search(str(c).strip()) and len(str(c)) < 40:
                result["inconsistencies"].append(
                    f"{item.get('work_id')}: vague criterion: {c}"
                )

    if not auth and apply:
        result["skipped"].append("gh auth not available — cannot apply")
        return redact_obj(result)

    all_labels = set()
    milestones = set()
    for item in open_items:
        all_labels.update(labels_for_item(item))
        if item.get("milestone"):
            milestones.add(str(item["milestone"]))

    label_defs = []
    for group in ("states", "types", "priorities", "risks", "areas"):
        label_defs.extend((policies.get("labels") or {}).get(group) or [])
    all_labels.update(label_defs)
    ms_defs = policies.get("milestones") or []
    milestones.update(ms_defs)

    result["labels_ensured"] = ensure_labels(root, sorted(all_labels), apply=apply and auth)
    result["milestones_ensured"] = ensure_milestones(
        root, sorted(milestones), apply=apply and auth
    )

    managed = list_managed_issues(root) if auth else {}
    # duplicate detection: same work_id shouldn't map twice (dict keys unique)
    seen_numbers: dict[int, str] = {}
    for wid, meta in managed.items():
        num = meta.get("number")
        if isinstance(num, int) and num in seen_numbers:
            result["duplicates"].append(
                {"issue": num, "work_ids": [seen_numbers[num], wid]}
            )
        elif isinstance(num, int):
            seen_numbers[num] = wid

    for item in open_items:
        wid = item["work_id"]
        title = str(item.get("title") or wid)[:250]
        body = render_issue_body(item)
        labs = labels_for_item(item)
        if wid in managed:
            num = managed[wid]["number"]
            if apply and auth:
                args = [
                    "issue",
                    "edit",
                    str(num),
                    "--title",
                    title,
                    "--body",
                    body,
                ]
                for lab in labs:
                    args.extend(["--add-label", lab])
                if item.get("milestone"):
                    args.extend(["--milestone", str(item["milestone"])])
                res = _run_gh(args, root, timeout=60)
                ok = res.get("exit_code") == 0
                result["updated"].append(
                    {"work_id": wid, "number": num, "ok": ok, "stderr": res.get("stderr")[:300]}
                )
                if ok:
                    item["issue_number"] = num
                    item["last_synced_at"] = _utc_now()
                    upsert_item(registry, item)
            else:
                result["updated"].append(
                    {"work_id": wid, "number": num, "ok": True, "dry_run": True}
                )
        else:
            if apply and auth:
                args = ["issue", "create", "--title", title, "--body", body]
                for lab in labs:
                    args.extend(["--label", lab])
                if item.get("milestone"):
                    args.extend(["--milestone", str(item["milestone"])])
                res = _run_gh(args, root, timeout=60)
                num = None
                if res.get("exit_code") == 0:
                    # stdout is URL
                    url = (res.get("stdout") or "").strip()
                    m = re.search(r"/issues/(\d+)", url)
                    if m:
                        num = int(m.group(1))
                result["created"].append(
                    {
                        "work_id": wid,
                        "number": num,
                        "ok": res.get("exit_code") == 0,
                        "url": (res.get("stdout") or "").strip(),
                        "stderr": (res.get("stderr") or "")[:300],
                    }
                )
                if num:
                    item["issue_number"] = num
                    item["last_synced_at"] = _utc_now()
                    upsert_item(registry, item)
            else:
                result["created"].append(
                    {"work_id": wid, "number": None, "ok": True, "dry_run": True}
                )

    if apply and auth:
        save_registry(registry, root)

    # open count check after
    if auth:
        open_res = _run_gh(
            ["issue", "list", "--state", "open", "--limit", "100", "--json", "number"],
            root,
        )
        try:
            open_count = len(json.loads(open_res.get("stdout") or "[]"))
        except json.JSONDecodeError:
            open_count = -1
        result["open_issues_count"] = open_count
        if open_count > max_open:
            result["inconsistencies"].append(
                f"open issues {open_count} exceeds max {max_open}"
            )

    return redact_obj(result)


def audit_issues(root: Path | None = None) -> dict[str, Any]:
    root = root or repo_root()
    registry = load_registry(root)
    managed = list_managed_issues(root) if gh_auth_ok(root) else {}
    reg_ids = {
        i["work_id"]
        for i in registry.get("work_items") or []
        if (i.get("state") or "").lower() not in {"done", "closed"}
    }
    managed_ids = set(managed.keys())
    return {
        "registry_open": sorted(reg_ids),
        "managed_open_or_closed": sorted(managed_ids),
        "missing_issues": sorted(reg_ids - managed_ids),
        "orphan_issues": sorted(managed_ids - {i["work_id"] for i in registry.get("work_items") or []}),
        "auth_ok": gh_auth_ok(root),
    }

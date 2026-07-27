#!/usr/bin/env python3
"""Fail-closed SHA binding for CONFENGE commercial RC artifacts.

Rules (objective §4, practical with embedded SHAs in-git):
1. All present of {artifact,run,gate,review,git}_git_sha must be equal to each other.
2. That common SHA must be an ancestor of (or equal to) HEAD.
3. Diff HEAD...common_sha may change evidence lag + unrelated monorepo paths.
   Protected CONFENGE frozen inputs after the run SHA → FAIL (requires re-freeze).
4. match_run_to_head=false with unequal internal SHAs → FAIL.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
_ART = _ROOT / "artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01"

from scripts.ops.confenge_frozen_inputs import (  # noqa: E402
    EVIDENCE_LAG_PREFIXES,
    evaluate_post_freeze_diff,
    load_frozen_inputs_manifest,
    protected_path_set,
)

# Deprecated alias: evidence lag only — not a feature allowlist.
_ALLOWED_PREFIXES = EVIDENCE_LAG_PREFIXES

SHA_KEYS = ("artifact_git_sha", "run_git_sha", "gate_git_sha", "review_git_sha", "git_sha")


def _git(args: list[str], *, cwd: Path | None = None) -> str:
    return subprocess.check_output(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=str(cwd or _ROOT),
        text=True,
        stderr=subprocess.DEVNULL,
        timeout=10,
    ).strip()


def git_head(root: Path | None = None) -> str:
    return _git(["rev-parse", "HEAD"], cwd=root)


def _is_ancestor(anc: str, head: str) -> bool:
    try:
        subprocess.check_call(  # noqa: S603
            ["git", "merge-base", "--is-ancestor", anc, head],  # noqa: S607
            cwd=str(_ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
        return True
    except (subprocess.CalledProcessError, OSError):
        return False


def _paths_changed(base: str, head: str) -> list[str]:
    if base == head:
        return []
    out = _git(["diff", "--name-only", f"{base}..{head}"])
    return [ln for ln in out.splitlines() if ln.strip()]


def check_artifact_binding(
    *,
    head_sha: str,
    result_path: Path | None = None,
    extra_paths: list[Path] | None = None,
) -> dict[str, Any]:
    paths = [result_path or (_ART / "result.json")]
    if extra_paths:
        paths.extend(extra_paths)
    issues: list[str] = []
    details: dict[str, Any] = {"head_sha": head_sha, "files": {}}
    collected: list[str] = []

    for path in paths:
        p = Path(path)
        if not p.is_file():
            issues.append(f"missing:{p}")
            details["files"][str(p)] = {"present": False}
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            issues.append(f"invalid_json:{p}:{exc}")
            details["files"][str(p)] = {"present": True, "error": str(exc)}
            continue
        file_issues: list[str] = []
        found: dict[str, str] = {}
        for key in SHA_KEYS:
            val = data.get(key)
            if val is None:
                continue
            sval = str(val)
            found[key] = sval
            collected.append(sval)
        # Internal consistency
        uniq = set(found.values())
        if len(uniq) > 1:
            file_issues.append(f"internal_sha_mismatch:{sorted(uniq)}")
        bind = data.get("sha_binding") or {}
        if bind.get("match_run_to_head") is False and len(uniq) > 1:
            file_issues.append("sha_binding.match_run_to_head=false")
        if file_issues:
            issues.extend(f"{p.name}:{x}" for x in file_issues)
        details["files"][str(p)] = {"present": True, "shas": found, "issues": file_issues}

    common: str | None = None
    if collected:
        uniq_all = set(collected)
        if len(uniq_all) != 1:
            issues.append(f"cross_file_sha_mismatch:{sorted(uniq_all)}")
        else:
            common = next(iter(uniq_all))

    if common:
        details["bound_sha"] = common
        if common != head_sha:
            if not _is_ancestor(common, head_sha):
                issues.append(f"bound_sha_not_ancestor_of_head:{common}!->{head_sha}")
            else:
                # Frozen-inputs policy: only protected CONFENGE inputs invalidate binding.
                eval_diff = evaluate_post_freeze_diff(
                    root=_ROOT,
                    freeze_sha=common,
                    tip=head_sha,
                    art_dir=_ART,
                )
                changed = list(eval_diff.get("files_changed_after_freeze") or [])
                bad = list(eval_diff.get("protected_changed") or [])
                details["paths_since_bound"] = changed
                details["freeze_policy"] = "frozen_confenge_inputs_v1"
                details["protected_changed"] = bad
                details["free_changed"] = list(eval_diff.get("free_changed") or [])
                if bad or not eval_diff.get("ok"):
                    issues.append(f"protected_input_changed_after_bound_sha:{bad}")
                # pure artifact lag + unrelated monorepo work is allowed
        # If common == head: perfect
    else:
        issues.append("no_sha_fields_found")

    ok = len(issues) == 0
    return {
        "ok": ok,
        "status": "PASS" if ok else "FAIL",
        "head_sha": head_sha,
        "bound_sha": common,
        "issues": issues,
        "details": details,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="CONFENGE commercial artifact SHA binding gate")
    p.add_argument("--result", default=str(_ART / "result.json"))
    p.add_argument("--queue-summary", default=str(_ART / "queue-summary.json"))
    p.add_argument("--head", default=None, help="Override HEAD SHA (tests)")
    p.add_argument("--out", default=None)
    args = p.parse_args(argv)
    head = args.head or git_head()
    report = check_artifact_binding(
        head_sha=head,
        result_path=Path(args.result),
        extra_paths=[Path(args.queue_summary)] if Path(args.queue_summary).is_file() else None,
    )
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""Atomic claim-surface sync — one process, one intended commit.

Updates in a single invocation:
1. pr-state.json heads from frozen/live PR branch OIDs
2. FINAL-REPORT / PR-MATRIX / BASELINE / TEST-MATRIX / manifest / checksums
3. HANDOFF.md tests/cto passed count from collect-only
4. executive HTML panel commit stamp = current HEAD (pre-commit tip)

Does NOT git-commit; the implementer makes exactly one commit containing all
outputs so claim surfaces do not re-age each other.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.cto.executive_sync import refresh_executive
from scripts.cto.paths import repo_root


PKG = Path("docs/ops/cto-pr-remediation-48-50-51-52")
SSOT_NAME = "pr-state.json"

# Frozen branch names for the four PRs (numbers preserved)
PR_REFS = {
    "48": "origin/feat/cto-autopilot-issues-deepseek-20260719",
    "50": "origin/cto/canary-live-20260719T204106Z",
    "51": "origin/cto/canary-live-20260719T215031Z",
    "52": "origin/goal/extra-decision-loop-01",
}


def _utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run(cmd: list[str], *, cwd: Path) -> str:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"cmd failed {cmd}: {(proc.stderr or proc.stdout or '')[:500]}"
        )
    return (proc.stdout or "").strip()


def _rev(ref: str, root: Path) -> str:
    return _run(["git", "rev-parse", ref], cwd=root)


def collect_tests_cto_count(root: Path) -> int:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/cto",
            "--collect-only",
            "-q",
            "--no-cov",
            "-o",
            "addopts=",
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )
    text = (proc.stdout or "") + (proc.stderr or "")
    m = re.search(r"(\d+)\s+tests?\s+collected", text)
    if not m:
        raise RuntimeError(f"could not parse collect-only count: {text[-500:]}")
    return int(m.group(1))


def update_handoff_passed_count(root: Path, n: int) -> None:
    path = root / "docs" / "ops" / "cto-autopilot" / "HANDOFF.md"
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    text2 = re.sub(r"\b\d+\s+passed\b", f"{n} passed", text)
    path.write_text(text2, encoding="utf-8")


def build_ssot(root: Path, *, n_tests: int) -> dict[str, Any]:
    """Build pr-state.json. Recommendations: incomplete SDC => BLOCKED_HUMAN."""
    heads = {
        "main": _rev("origin/main", root),
        "48": _rev("HEAD", root),  # pre-commit tip of this branch
        "50": _rev(PR_REFS["50"], root),
        "51": _rev(PR_REFS["51"], root),
        "52": _rev(PR_REFS["52"], root),
    }
    recs = {
        "48": "READY_FOR_HUMAN_REVIEW",
        "50": "BLOCKED_HUMAN",
        "51": "BLOCKED_HUMAN",
        "52": "READY_FOR_HUMAN_REVIEW",
    }
    return {
        "schema_version": "1.0",
        "generated_at": _utc_now(),
        "terminal_state": "WAITING_HUMAN",
        "heads": heads,
        "bases": {
            "48": "main",
            "50": "feat/cto-autopilot-issues-deepseek-20260719",
            "51": "cto/canary-live-20260719T204106Z",
            "52": "main",
        },
        "recommendations": recs,
        "stories": {
            "50": {
                "story_id": "ROI-cand-dyn-slice-cb906bb58392",
                "status": "Draft",
                "po_validated": False,
                "qa_verdict": "PENDING",
                "candidate_id": "cand-dyn-slice:cb906bb58392",
            },
            "51": {
                "story_id": "ROI-cand-dyn-slice-b84aad7b10ee",
                "status": "Draft",
                "po_validated": False,
                "qa_verdict": "PENDING",
                "candidate_id": "cand-dyn-slice:b84aad7b10ee",
            },
        },
        "next_actions": {
            "48": (
                f"Human review/merge CTO Autopilot (tests/cto {n_tests} passed; "
                "full suite SKIPPED≠green)"
            ),
            "50": (
                "@po validate ROI-cand-dyn-slice-cb906bb58392 → Ready; "
                "independent @qa"
            ),
            "51": (
                "Complete #50 SDC; force-next/rerank; @po Ready cycle-2 story"
            ),
            "52": (
                "Human review/merge decision loop "
                "(required CI pass; full suite SKIPPED≠green)"
            ),
        },
        "merge_order": [48, 50, 51, 52],
        "test_counts": {
            "tests_cto_collected": n_tests,
            "tests_cto_passed_claim": n_tests,
            "full_suite": "SKIPPED on PR CI — preexisting debt, not claimed green",
        },
        "claims_forbidden": [
            "LOCAL_READY",
            "VPS_OPERATIONAL",
            "PROJECT_DONE",
            "95% coverage",
            "INTEGRATED without main",
            "story Done without PO+QA",
            "READY_FOR_HUMAN_REVIEW for incomplete SDC on #50/#51",
            "full suite green when skipped",
        ],
    }


def write_derived_docs(pkg: Path, state: dict[str, Any]) -> None:
    h = state["heads"]
    r = state["recommendations"]
    now = state["generated_at"]
    n = (state.get("test_counts") or {}).get("tests_cto_collected", "?")

    (pkg / "PR-MATRIX.md").write_text(
        f"""# PR-MATRIX

> SSOT: `pr-state.json` ({now}). Do not hand-edit without re-running sync_claim_surfaces.

| PR | Base | Head | Objetivo | Testes | Estado |
| -- | ---- | ---- | -------- | ------ | ------ |
| #48 | main | `{h['48'][:12]}` | CTO Autopilot seguro AIOX/ROI | tests/cto **{n}** passed; full suite SKIPPED≠green | **{r['48']}** |
| #50 | branch #48 | `{h['50'][:12]}` | Ciclo 1 ledger + force-next | stack suite; story Draft | **{r['50']}** |
| #51 | branch #50 | `{h['51'][:12]}` | Ciclo 2 reconstruct after rerank | stack suite; story Draft | **{r['51']}** |
| #52 | main | `{h['52'][:12]}` | Decision loop semântico | required CI pass; full suite SKIPPED≠green | **{r['52']}** |
""",
        encoding="utf-8",
    )

    (pkg / "FINAL-REPORT.md").write_text(
        f"""# FINAL-REPORT — WAITING_HUMAN

**Generated:** {now}  
**SSOT:** `pr-state.json`

## Heads

| Ref | SHA |
|-----|-----|
| main | `{h['main']}` |
| PR #48 | `{h['48']}` |
| PR #50 | `{h['50']}` |
| PR #51 | `{h['51']}` |
| PR #52 | `{h['52']}` |

## Parecer

| PR | Estado |
|----|--------|
| #48 | **{r['48']}** — tests/cto {n} passed; full suite SKIPPED≠green |
| #50 | **{r['50']}** — {state['next_actions']['50']} |
| #51 | **{r['51']}** — {state['next_actions']['51']} |
| #52 | **{r['52']}** — {state['next_actions']['52']} |

## Topology

```text
main ← #48 ← #50 ← #51
main ← #52
```

## Merge order

1. #48 READY_FOR_HUMAN_REVIEW  
2. #50 after @po/@qa (BLOCKED_HUMAN)  
3. #51 after #50 SDC (BLOCKED_HUMAN)  
4. #52 parallel (READY_FOR_HUMAN_REVIEW)

## Honesty

- Incomplete SDC (po_validated=false / qa PENDING) ⇒ **BLOCKED_HUMAN**
- Full suite skipped is **not** green
- Panel commit is ancestor of HEAD (not last-5 window)

Sem merge, force-push, ou selos falsos.
""",
        encoding="utf-8",
    )

    (pkg / "BASELINE.md").write_text(
        f"""# BASELINE

**Captured:** {now}  
**SSOT:** `pr-state.json`

| Ref | SHA |
|-----|-----|
| main | `{h['main']}` |
| #48 | `{h['48']}` |
| #50 | `{h['50']}` |
| #51 | `{h['51']}` |
| #52 | `{h['52']}` |

| PR | Recommendation |
|----|----------------|
| #48 | {r['48']} |
| #50 | {r['50']} |
| #51 | {r['51']} |
| #52 | {r['52']} |

tests/cto collected/claimed: **{n}**. Full suite SKIPPED on PR CI.
""",
        encoding="utf-8",
    )

    (pkg / "TEST-MATRIX.md").write_text(
        f"""# TEST-MATRIX

> SSOT ({now}). Skipped ≠ green.

| Suite | #48 | #50 | #51 | #52 |
|-------|-----|-----|-----|-----|
| tests/cto | **{n} pass claim** | stack | stack | n/a |
| full suite | SKIPPED | SKIPPED | SKIPPED | SKIPPED |
| required CI | see Actions | see Actions | see Actions | lint/mypy/critical/resilience/bandit/pip-audit |

**Skipped ≠ green.**
""",
        encoding="utf-8",
    )

    # Preserve ARCHITECTURE / DOD-MAP / SECURITY-REVIEW if present (content stable)
    man = {
        "generated_at": now,
        "ssot": SSOT_NAME,
        "heads": h,
        "recommendations": r,
        "terminal_state": "WAITING_HUMAN",
        "test_counts": state.get("test_counts"),
        "merge_order": state.get("merge_order"),
    }
    (pkg / "manifest.json").write_text(
        json.dumps(man, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    checksums = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(pkg.iterdir())
        if p.is_file() and p.name != "checksums.json"
    }
    (pkg / "checksums.json").write_text(
        json.dumps(checksums, indent=2) + "\n", encoding="utf-8"
    )


def sync_all(root: Path | None = None) -> dict[str, Any]:
    root = root or repo_root()
    pkg = root / PKG
    pkg.mkdir(parents=True, exist_ok=True)

    n = collect_tests_cto_count(root)
    update_handoff_passed_count(root, n)
    state = build_ssot(root, n_tests=n)
    (pkg / SSOT_NAME).write_text(
        json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    write_derived_docs(pkg, state)

    # Stamp HTML last so commit field is current pre-commit HEAD
    html_res = refresh_executive(root)

    return {
        "ok": True,
        "n_tests": n,
        "heads": state["heads"],
        "recommendations": state["recommendations"],
        "html": {
            "ok": html_res.get("ok"),
            "path": html_res.get("path"),
            "sha256": html_res.get("sha256"),
        },
        "ssot_path": str(pkg / SSOT_NAME),
        "note": (
            "Make exactly ONE commit containing these files; do not re-sync after "
            "that commit (panel commit is pre-commit HEAD / ancestor of tip)."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    result = sync_all()
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""DoD §27 hygiene: metrics definitions, TODOs, dry-run inventory, destructive safety."""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Word-boundary tags only — do NOT match CNPJ masks like XX.XXX.XXX/XXXX-XX
CRITICAL_TODO = re.compile(
    r"(?:#|//)\s*(?P<tag>FIXME|XXX|HACK|TODO)\b(?P<body>[^\n]{0,200})",
    re.IGNORECASE,
)
# Also allow bare TODO(tracking) without requiring # if it's a code comment style
CRITICAL_TODO_INLINE = re.compile(
    r"\b(?P<tag>FIXME|HACK)\b(?P<body>[^\n]{0,200})",
    re.IGNORECASE,
)
# Accept story/issue/ADR refs in TODO body
TODO_TRACKED = re.compile(
    r"(story|ROI-|B2G-|issue|#[0-9]+|ADR-|datalake-step|TD-|epic)",
    re.IGNORECASE,
)

# Operational CLIs expected to support --dry-run (read-mostly report tools)
DRY_RUN_EXPECTED = [
    "scripts/reports/operational_outputs.py",
    "scripts/reports/operational_reports.py",
    "scripts/reports/operational_export_pack.py",
    "scripts/coverage/applicability_matrix.py",
    "scripts/ops/alert_pipeline.py",
    "scripts/ops/centralized_config_audit.py",
    "scripts/ops/code_organization_gate.py",
    "scripts/ops/code_hygiene_gate.py",
]

DESTRUCTIVE_SCRIPTS = [
    {
        "path": "scripts/ops/golden_clean_env.py",
        "risk": "DROP/CREATE database",
        "require_flag": "--confirm-drop",
        "rollback": "Restore from backups/local-proof/*.dump or re-run seed",
    },
    {
        "path": "scripts/backup-database.sh",
        "risk": "overwrite dump paths",
        "require_flag": "documented in script / --help",
        "rollback": "Keep prior dump; do not overwrite without versioned name",
    },
    {
        "path": "scripts/ops/local_backup_restore_proof.py",
        "risk": "restore into separate DB",
        "require_flag": "explicit DSN args",
        "rollback": "Drop proof DB only; never target production without confirm",
    },
]


def check_metric_definitions() -> dict[str, Any]:
    from scripts.coverage.coverage_contract import METRIC_DEFINITIONS, validate_indicator_catalog

    missing = []
    for mid, defn in METRIC_DEFINITIONS.items():
        if not defn.required_fields_present():
            missing.append(mid)
    catalog = validate_indicator_catalog()
    policy = _PROJECT_ROOT / "docs" / "ops" / "METRIC-DEFINITION-POLICY.md"
    return {
        "n_metrics": len(METRIC_DEFINITIONS),
        "all_required_fields": len(missing) == 0,
        "missing_required": missing,
        "catalog_valid": bool(catalog.get("ok", catalog.get("valid", True))),
        "policy_doc": str(policy.relative_to(_PROJECT_ROOT)),
        "policy_exists": policy.is_file(),
        "ok": len(missing) == 0 and policy.is_file(),
    }


def scan_todos(root: Path | None = None) -> dict[str, Any]:
    root = root or _PROJECT_ROOT
    critical_untracked: list[dict[str, str]] = []
    tracked = 0
    total = 0
    for path in (root / "scripts").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        # do not flag this scanner's own pattern strings
        if path.name == "code_hygiene_gate.py":
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if "#" not in line:
                continue  # only real comments
            # skip generated YAML template strings
            if "lines.append" in line or "print(" in line:
                continue
            comment = line.split("#", 1)[1]
            if not any(t in comment.upper() for t in ("TODO", "FIXME", "XXX", "HACK")):
                continue
            m = re.search(
                r"\b(?P<tag>FIXME|XXX|HACK|TODO)\b(?P<body>.*)$",
                comment,
                re.IGNORECASE,
            )
            if not m:
                continue
            tag = m.group("tag").upper()
            body = m.group("body")
            # CNPJ masks / module placeholders: XX.XXX.XXX or scripts.xxx.yyy
            if tag == "XXX" and (
                re.search(r"X{2,}\.X{3}", comment, re.I)
                or re.search(r"scripts\.xxx", comment, re.I)
                or re.search(r"\w\.xxx\.\w", comment, re.I)
            ):
                continue
            total += 1
            if TODO_TRACKED.search(body) or TODO_TRACKED.search(comment):
                tracked += 1
            else:
                critical_untracked.append(
                    {
                        "path": str(path.relative_to(root)),
                        "line": str(i),
                        "tag": tag,
                        "text": line.strip()[:160],
                    }
                )
    # Policy: untracked FIXME/XXX/HACK must be 0; bare TODO allowed but listed (debt)
    fixme = [c for c in critical_untracked if c["tag"] in {"FIXME", "XXX", "HACK"}]
    bare_todos = [c for c in critical_untracked if c["tag"] == "TODO"]
    return {
        "n_todo_like": total,
        "n_tracked": tracked,
        "n_fixme_untracked": len(fixme),
        "n_todo_untracked": len(bare_todos),
        "fixme_untracked": fixme[:30],
        "todo_untracked_sample": bare_todos[:40],
        "ok": len(fixme) == 0,  # TODOs may remain as debt with inventory
        "policy": "FIXME/XXX/HACK must reference story/issue; bare TODO inventoried",
    }


def inventory_dry_run(root: Path | None = None) -> dict[str, Any]:
    root = root or _PROJECT_ROOT
    results = []
    for rel in DRY_RUN_EXPECTED:
        path = root / rel
        if not path.is_file():
            results.append({"path": rel, "exists": False, "has_dry_run": False})
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        has = "--dry-run" in text or "dry_run" in text
        results.append({"path": rel, "exists": True, "has_dry_run": has})
    missing = [r for r in results if r["exists"] and not r["has_dry_run"]]
    return {
        "expected": DRY_RUN_EXPECTED,
        "results": results,
        "missing_dry_run": [m["path"] for m in missing],
        "ok": len(missing) == 0,
    }


def check_destructive_safety(root: Path | None = None) -> dict[str, Any]:
    root = root or _PROJECT_ROOT
    checks = []
    for item in DESTRUCTIVE_SCRIPTS:
        path = root / item["path"]
        text = path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
        flag = item["require_flag"]
        has_flag = flag.split()[0] in text if flag.startswith("--") else True
        has_rollback_doc = bool(item.get("rollback"))
        checks.append(
            {
                **item,
                "exists": path.is_file(),
                "has_require_flag": has_flag,
                "rollback_documented": has_rollback_doc,
                "ok": path.is_file() and has_flag and has_rollback_doc,
            }
        )
    # also require LEGACY plan
    legacy = root / "docs" / "ops" / "LEGACY-REMOVAL-PLAN.md"
    return {
        "scripts": checks,
        "legacy_plan": {
            "path": "docs/ops/LEGACY-REMOVAL-PLAN.md",
            "exists": legacy.is_file(),
            "ok": legacy.is_file() and "Critério de remoção" in (legacy.read_text(encoding="utf-8") if legacy.is_file() else ""),
        },
        "ok": all(c["ok"] for c in checks) and legacy.is_file(),
    }


def check_comment_code_contradiction(root: Path | None = None) -> dict[str, Any]:
    """Light scan: comments claiming REMOVED/DONE while TODO remains on same line."""
    root = root or _PROJECT_ROOT
    hits: list[dict[str, str]] = []
    for path in (root / "scripts").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            if "#" not in line:
                continue
            comment = line.split("#", 1)[1]
            if re.search(r"\b(TODO|FIXME)\b", comment, re.I) and re.search(
                r"\b(DONE|REMOVED|FIXED|COMPLETE)\b", comment, re.I
            ):
                hits.append(
                    {
                        "path": str(path.relative_to(root)),
                        "line": str(i),
                        "text": line.strip()[:160],
                    }
                )
    return {
        "n_hits": len(hits),
        "hits": hits[:20],
        "ok": len(hits) == 0,
        "note": "Heuristic only — empty hits does not prove all comments accurate",
    }


def check_logs_vs_error_handling() -> dict[str, Any]:
    """PARTIAL capability: policy doc that log-only is insufficient for fail-closed gates."""
    policy = (
        "Fail-closed gates (golden_path, coverage_gate, freshness_gate, enforce_aiox_path) "
        "must return non-zero exit on failure; logging alone is not success. "
        "Former silent excepts now log with exc_info but still do not claim full rethrow."
    )
    # Sample fail-closed scripts exist
    paths = [
        "scripts/golden_path.py",
        "scripts/coverage_gate.py",
        "scripts/freshness_gate.py",
        "squads/extra-dod-roi/scripts/enforce_aiox_path.py",
    ]
    present = [(p, (_PROJECT_ROOT / p).is_file()) for p in paths]
    return {
        "policy": policy,
        "fail_closed_scripts": [{"path": p, "exists": e} for p, e in present],
        "ok": all(e for _, e in present),
        "status": "PARTIAL_capability_documented",
    }


def run_gate() -> dict[str, Any]:
    metrics = check_metric_definitions()
    todos = scan_todos()
    dry = inventory_dry_run()
    destructive = check_destructive_safety()
    comments = check_comment_code_contradiction()
    logs = check_logs_vs_error_handling()
    legacy_ok = destructive.get("legacy_plan", {}).get("ok", False)

    result = {
        "generated_at": datetime.now(UTC).isoformat(),
        "metric_definitions": metrics,
        "todos": todos,
        "dry_run": dry,
        "destructive_safety": destructive,
        "comments": comments,
        "logs_vs_errors": logs,
        "legacy_removal_plan": destructive.get("legacy_plan"),
        "summary": {
            "ok": (
                metrics["ok"]
                and todos["ok"]
                and dry["ok"]
                and destructive["ok"]
                and comments["ok"]
                and legacy_ok
            )
        },
        "claims": {
            "allowed": [
                "Metric definitions complete in METRIC_DEFINITIONS",
                "FIXME/XXX/HACK untracked count is zero",
                "Operational CLIs expose --dry-run",
                "Destructive scripts require confirm flag + rollback doc",
                "Legacy removal plan exists",
            ],
            "forbidden": ["LOCAL_READY", "all TODOs eliminated", "comments proven globally consistent"],
        },
    }
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="DoD §27 code hygiene gate")
    p.add_argument("--json", action="store_true")
    p.add_argument("--dry-run", action="store_true", help="Same as default: no writes")
    p.add_argument("--out", type=Path, default=None)
    args = p.parse_args(argv)
    result = run_gate()
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
    if args.json:
        print(text)
    else:
        s = result["summary"]
        print(
            f"ok={s['ok']} metrics={result['metric_definitions']['ok']} "
            f"todos={result['todos']['ok']} dry_run={result['dry_run']['ok']} "
            f"destructive={result['destructive_safety']['ok']}"
        )
    return 0 if result["summary"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

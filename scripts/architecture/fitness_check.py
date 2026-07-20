#!/usr/bin/env python3
"""Architecture fitness checks (ARCH-RESET). Advisory by default; --strict fails closed.

Minimal automated subset of FITNESS-FUNCTIONS.md:
1. one canonical weekly product entrypoint (Makefile + yaml if present)
2. no LLM modules imported by coverage/freshness entrypoints
3. alternate product pipelines must be labeled or have ADR reference
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def check_canonical_weekly_entrypoint(root: Path = ROOT) -> dict[str, Any]:
    makefile = (root / "Makefile").read_text(encoding="utf-8", errors="replace")
    has_extra = bool(re.search(r"^extra-weekly:", makefile, flags=re.M))
    points_to_module = "scripts.ops.weekly_cycle" in makefile
    yaml_path = root / "docs" / "canonical-entry-points.yaml"
    yaml_ok = True
    product_cmd = None
    if yaml_path.is_file():
        text = yaml_path.read_text(encoding="utf-8", errors="replace")
        # v1.1 field or weekly command blob
        m = re.search(r"product_canonical_command:\s*(\S+)", text)
        product_cmd = m.group(1) if m else None
        yaml_ok = ("extra-weekly" in text) and ("weekly_cycle" in text)
        if product_cmd is not None:
            yaml_ok = yaml_ok and product_cmd.strip("\"'") == "extra-weekly"
    ok = has_extra and points_to_module and yaml_ok
    return {
        "id": "one_canonical_weekly_entrypoint",
        "ok": ok,
        "has_extra_weekly": has_extra,
        "points_to_weekly_cycle": points_to_module,
        "yaml_ok": yaml_ok,
        "product_canonical_command": product_cmd,
    }


def check_no_llm_in_coverage_freshness(root: Path = ROOT) -> dict[str, Any]:
    """Static denylist: coverage/freshness modules must not import openai/llm clients."""
    denylist = ("openai", "anthropic", "langchain", "litellm")
    paths = [
        root / "scripts" / "coverage",
        root / "scripts" / "freshness_gate.py",
        root / "scripts" / "coverage_gate.py",
        root / "scripts" / "coverage_truth.py",
    ]
    hits: list[str] = []
    files: list[Path] = []
    for p in paths:
        if p.is_file():
            files.append(p)
        elif p.is_dir():
            files.extend(p.rglob("*.py"))
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for token in denylist:
            # import openai / from openai
            if re.search(rf"(^|\s)(import|from)\s+{re.escape(token)}\b", text, flags=re.M):
                hits.append(f"{f.relative_to(root)}:{token}")
    return {
        "id": "no_llm_in_coverage_freshness",
        "ok": not hits,
        "hits": hits,
        "scanned_files": len(files),
    }


def check_alternate_pipelines_labeled(root: Path = ROOT) -> dict[str, Any]:
    """Competing Make targets must remain labeled diagnostic/legacy or documented in ADR.

    On main without PR #56 banners, require either class comment OR ARCH-RESET ADR presence.
    """
    makefile = (root / "Makefile").read_text(encoding="utf-8", errors="replace")
    targets = {
        "golden-path": "diagnostic",
        "run-pipeline": "legacy",
        "extra-weekly": "canonical",
    }
    issues: list[str] = []
    for t, kind in targets.items():
        if not re.search(rf"^{re.escape(t)}:", makefile, flags=re.M):
            if t == "extra-weekly":
                issues.append("missing_extra_weekly")
            continue
        if t == "extra-weekly":
            continue
        # Accept either explicit class banner or presence of ADR-023 campaign file
        banner = (
            "LEGACY" in makefile
            or "DIAGNOSTIC" in makefile
            or "legacy_composite" in makefile
            or "diagnostic" in makefile.lower()
        )
        adr = (root / "docs/architecture/adr/ADR-023-arch-reset-2026-07-20.md").is_file()
        if not banner and not adr:
            issues.append(f"unlabeled_competing_target:{t}:{kind}")
    return {
        "id": "alternate_pipelines_labeled_or_adr",
        "ok": not issues,
        "issues": issues,
    }


def run_all(root: Path = ROOT) -> dict[str, Any]:
    checks = [
        check_canonical_weekly_entrypoint(root),
        check_no_llm_in_coverage_freshness(root),
        check_alternate_pipelines_labeled(root),
    ]
    return {
        "generated_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "root": str(root),
        "ok": all(c["ok"] for c in checks),
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--strict", action="store_true", help="exit 2 if any check fails")
    p.add_argument("--json-out", type=Path, default=None)
    args = p.parse_args(argv)
    report = run_all()
    text = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    print(text, end="")
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text, encoding="utf-8")
    if args.strict and not report["ok"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""DoD §1 process integrity checks — evidence-only completion rules.

Enforces:
- completed items should carry evidence markers when possible
- code-without-execution is not treated as done (policy constant)
- unit tests alone are not E2E (policy constant)
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

EVIDENCE_MARKERS = (
    "evidência",
    "evidence",
    "pytest",
    "exit",
    "qa pass",
    "qa concerns",
    "cyc-",
    "session-",
    "scripts/",
    "docs/ops/",
)

POLICY = {
    "checkbox_requires_evidence": True,
    "code_without_execution_is_not_done": True,
    "unit_test_is_not_e2e": True,
}


def parse_completed_without_evidence(dod_text: str) -> list[dict[str, Any]]:
    """Return checked items whose text lacks an evidence marker (heuristic)."""
    issues: list[dict[str, Any]] = []
    for i, line in enumerate(dod_text.splitlines(), 1):
        m = re.match(r"^\s*-\s*\[[xX]\]\s*(.*)$", line)
        if not m:
            continue
        body = m.group(1).strip()
        if not body:
            continue
        lower = body.lower()
        if any(marker in lower for marker in EVIDENCE_MARKERS):
            continue
        # short process meta lines may be structural
        if len(body) < 40 and body.endswith("."):
            issues.append({"line": i, "text": body[:160], "severity": "low"})
        else:
            issues.append({"line": i, "text": body[:160], "severity": "medium"})
    return issues


def audit_dod_file(path: str | Path) -> dict[str, Any]:
    text = Path(path).read_text(encoding="utf-8")
    checked = len(re.findall(r"^\s*-\s*\[[xX]\]", text, re.M))
    open_n = len(re.findall(r"^\s*-\s*\[\s\]", text, re.M))
    weak = parse_completed_without_evidence(text)
    return {
        "ok": True,  # advisory scan — campaign uses QA gates for flips
        "policy": POLICY,
        "checked": checked,
        "open": open_n,
        "completed_without_evidence_marker": len(weak),
        "sample_weak": weak[:20],
        "rules": {
            "code_without_execution_is_not_done": POLICY["code_without_execution_is_not_done"],
            "unit_test_is_not_e2e": POLICY["unit_test_is_not_e2e"],
            "checkbox_requires_evidence": POLICY["checkbox_requires_evidence"],
        },
    }

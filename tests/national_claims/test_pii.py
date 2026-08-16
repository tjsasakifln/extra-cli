"""Fixtures and reports carry no PII."""

from __future__ import annotations

import json
import re
from pathlib import Path

PII = re.compile(
    r"("
    r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}"
    r"|\b\d{3}\.\d{3}\.\d{3}-\d{2}\b"
    r"|\b\d{11}\b"
    r"|\+55\d{10,11}"
    r"|\bpassword\b"
    r"|\bsecret\b"
    r")",
    re.IGNORECASE,
)


def test_fixtures_and_sample_reports_have_no_pii() -> None:
    roots = [
        Path("docs/contracts/national-claims"),
        Path("tests/fixtures/national_claims"),
        Path("reports/national_claims"),
    ]
    scanned = 0
    for root in roots:
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in {".json", ".md"}:
                continue
            text = path.read_text(encoding="utf-8")
            match = PII.search(text)
            assert match is None, f"PII-like token in {path}: {match.group(0)}"
            scanned += 1
            if path.suffix == ".json":
                json.loads(text)
    assert scanned >= 8

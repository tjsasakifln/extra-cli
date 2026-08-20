"""Fixtures and coverage docs carry no secrets or raw official payloads."""

from __future__ import annotations

import json
import re
from pathlib import Path

LEAK = re.compile(
    r"("
    r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}"
    r"|\bpassword\b"
    r"|\bsecret\b"
    r"|\bapi[_-]?key\b"
    r"|\bBEGIN (RSA )?PRIVATE KEY\b"
    r")",
    re.IGNORECASE,
)


def test_fixtures_have_no_secrets_or_raw_payloads() -> None:
    roots = [
        Path("docs/contracts/national-coverage"),
        Path("tests/national_coverage"),
        Path("exports/national-coverage"),
    ]
    scanned = 0
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in {".json", ".md"}:
                continue
            text = path.read_text(encoding="utf-8")
            match = LEAK.search(text)
            assert match is None, f"secret-like token in {path}: {match.group(0)}"
            scanned += 1
            if path.suffix == ".json":
                payload = json.loads(text)
                blob = json.dumps(payload)
                assert "raw_catalog_bytes" not in blob
                assert "Authorization" not in blob
    assert scanned >= 8

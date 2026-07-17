"""Identity: commercial numerator == entities_covered.jsonl line count."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SESSION = ROOT / "output" / "session-2026-07-17"


def test_commercial_list_identity_when_artifacts_present():
    cov_path = SESSION / "coverage_canonical.json"
    list_path = SESSION / "entities_covered.jsonl"
    if not cov_path.is_file() or not list_path.is_file():
        return  # artifacts optional in pure unit CI without session data
    cov = json.loads(cov_path.read_text(encoding="utf-8"))
    num = int(cov.get("commercial_numerator") or 0)
    ids = [int(x) for x in (cov.get("commercial_entity_ids") or [])]
    lines = [json.loads(line) for line in list_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    line_ids = {int(e["entity_id"]) for e in lines}
    assert num > 0
    assert len(lines) == num, f"covered lines {len(lines)} != commercial_numerator {num}"
    if ids:
        assert len(ids) == num
        assert set(ids) == line_ids
    assert cov.get("list_identity_ok") is True or len(lines) == num

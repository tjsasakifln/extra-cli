"""Shipped unit tests for golden_path ledger normalization.

Proves the fix for nested ledger corruption:
``{"version":1,"runs":{"version":1,"runs":[...]}}`` broke append.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.golden_path import _load_ledger, _normalize_ledger_runs, _save_ledger


def test_normalize_flat_list():
    assert _normalize_ledger_runs([{"run_id": "a"}]) == [{"run_id": "a"}]


def test_normalize_nested_once():
    nested = {"version": 1, "runs": [{"run_id": "b"}]}
    assert _normalize_ledger_runs(nested) == [{"run_id": "b"}]


def test_normalize_double_nested_corruption():
    # Real failure mode from campaign evidence gp-20260716-191038
    corrupted = {"version": 1, "runs": {"version": 1, "runs": [{"run_id": "old"}]}}
    assert _normalize_ledger_runs(corrupted) == [{"run_id": "old"}]


def test_normalize_garbage():
    assert _normalize_ledger_runs(None) == []
    assert _normalize_ledger_runs("x") == []
    assert _normalize_ledger_runs(42) == []
    assert _normalize_ledger_runs([{"ok": 1}, "skip", 3]) == [{"ok": 1}]


def test_save_ledger_after_corruption(tmp_path: Path, monkeypatch):
    ledger = tmp_path / "ledger.json"
    ledger.write_text(
        json.dumps({"version": 1, "runs": {"version": 1, "runs": [{"run_id": "old"}]}}),
        encoding="utf-8",
    )
    # Point module ledger path at temp file via load path used by _save_ledger
    import scripts.golden_path as gp

    monkeypatch.setattr(gp, "_LEDGER_PATH", ledger)
    fixed = _normalize_ledger_runs(json.loads(ledger.read_text())["runs"])
    _save_ledger(fixed + [{"run_id": "new"}], ledger)
    data = json.loads(ledger.read_text())
    assert isinstance(data["runs"], list)
    assert [r["run_id"] for r in data["runs"]] == ["old", "new"]
    # load_ledger also recovers
    loaded = _load_ledger()
    assert isinstance(loaded["runs"], list)
    assert len(loaded["runs"]) == 2

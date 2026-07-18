"""DoD §29 — manual overrides require motivo, data, autor."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.lib.manual_override_ledger import (
    append_override,
    load_overrides,
    new_override,
    validate_override_row,
)


def test_new_override_requires_motivo(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        new_override(target="entity:1", action="force_status", motivo=" ", autor="tiago")


def test_append_and_load(tmp_path: Path) -> None:
    path = tmp_path / "overrides.jsonl"
    ov = new_override(
        target="entity:1",
        action="force_coverage",
        motivo="fonte oficial offline; consulta manual",
        autor="tiago",
        before="unknown",
        after="verified",
        run_id="run-1",
    )
    append_override(path, ov)
    rows = load_overrides(path)
    assert len(rows) == 1
    assert rows[0]["motivo"]
    assert rows[0]["autor"] == "tiago"
    assert rows[0]["data"]
    assert validate_override_row(rows[0])["ok"] is True


def test_validate_row_missing_fields() -> None:
    r = validate_override_row({"target": "x", "action": "y"})
    assert r["ok"] is False

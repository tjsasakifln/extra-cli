"""DoD §29 — manual overrides require motivo, data, autor."""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts.lib.manual_override_ledger import (
    append_override,
    load_overrides,
    new_override,
    validate_override_row,
)


def test_new_override_requires_motivo(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="motivo"):
        new_override(target="entity:1", action="force_status", motivo=" ", autor="tiago")


def test_new_override_requires_autor() -> None:
    with pytest.raises(ValueError, match="autor"):
        new_override(
            target="entity:1",
            action="force_status",
            motivo="consulta manual portal",
            autor="",
        )


def test_new_override_requires_data() -> None:
    with pytest.raises(ValueError, match="data"):
        new_override(
            target="entity:1",
            action="force_status",
            motivo="consulta manual portal",
            autor="tiago",
            data="  ",
        )


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
    assert any("motivo" in i for i in r["issues"])
    assert any("data" in i for i in r["issues"])
    assert any("autor" in i for i in r["issues"])


def test_validate_row_missing_autor_only() -> None:
    r = validate_override_row(
        {
            "target": "x",
            "action": "y",
            "motivo": "ok",
            "data": "2026-07-20T00:00:00+00:00",
            "autor": "",
        }
    )
    assert r["ok"] is False
    assert "missing:autor" in r["issues"]

"""Fail-closed: missing/unreadable required inputs never produce shallow feed."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.warmbly_bridge.export import ExportConfig, export_outreach
from scripts.warmbly_bridge.io_jsonl import InputError


def test_missing_universe_fails(tmp_path: Path, intel_path: Path, contacts_path: Path) -> None:
    out = tmp_path / "out"
    with pytest.raises(InputError, match="--universe"):
        export_outreach(
            ExportConfig(
                universe=tmp_path / "missing_universe.jsonl",
                account_intelligence=intel_path,
                contacts=contacts_path,
                out_dir=out,
            )
        )
    assert not out.exists() or not list(out.glob("chunk_*.json"))


def test_missing_account_intelligence_fails(
    tmp_path: Path, universe_path: Path, contacts_path: Path
) -> None:
    out = tmp_path / "out"
    with pytest.raises(InputError, match="--account-intelligence"):
        export_outreach(
            ExportConfig(
                universe=universe_path,
                account_intelligence=tmp_path / "no_intel.jsonl",
                contacts=contacts_path,
                out_dir=out,
            )
        )
    assert not list(out.glob("chunk_*.json")) if out.exists() else True


def test_missing_contacts_fails(tmp_path: Path, universe_path: Path, intel_path: Path) -> None:
    out = tmp_path / "out"
    with pytest.raises(InputError, match="--contacts"):
        export_outreach(
            ExportConfig(
                universe=universe_path,
                account_intelligence=intel_path,
                contacts=tmp_path / "no_contacts.jsonl",
                out_dir=out,
            )
        )


def test_cli_missing_input_exit_code(
    tmp_path: Path, universe_path: Path, contacts_path: Path
) -> None:
    from scripts.warmbly_bridge.cli import main

    code = main(
        [
            "export-outreach",
            "--universe",
            str(universe_path),
            "--account-intelligence",
            str(tmp_path / "gone.jsonl"),
            "--contacts",
            str(contacts_path),
            "--out",
            str(tmp_path / "out"),
        ]
    )
    assert code == 2

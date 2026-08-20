"""Drive the shipped CLI entry (python3 -m / main) twice for hash identity."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.public_integrity.cli import main
from scripts.public_integrity.models import INTEGRITY_STATES, SCHEMA_VERSION
from tests.public_integrity.helpers import FIXTURES, REPO, VALID_CNPJ


def _run_module(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "scripts.public_integrity", *args],
        cwd=str(REPO),
        check=False,
        capture_output=True,
        text=True,
    )


def test_cli_matches_twice_same_hash(tmp_path: Path, capsys) -> None:
    out1 = tmp_path / "run-1.json"
    out2 = tmp_path / "run-2.json"
    fixture = str(FIXTURES / "matches.json")
    assert main(["replay", "--fixture", fixture, "--cnpj", VALID_CNPJ, "--out", str(out1)]) == 0
    first = json.loads(capsys.readouterr().out)
    assert main(["replay", "--fixture", fixture, "--cnpj", VALID_CNPJ, "--out", str(out2)]) == 0
    second = json.loads(capsys.readouterr().out)
    payload1 = json.loads(out1.read_text(encoding="utf-8"))
    payload2 = json.loads(out2.read_text(encoding="utf-8"))
    assert payload1["schema"] == payload1["schema_version"] == SCHEMA_VERSION
    assert payload1["aggregate_state"] == "MATCHES_FOUND"
    assert payload1["aggregate_state"] in INTEGRITY_STATES
    assert payload1["not_legal_conclusion"] is True
    assert payload1["records"]
    assert payload1["records"][0]["official_id"] == "9001"
    assert payload1["records"][0]["source_url"]
    for source_id in ("CEIS", "CNEP"):
        source = payload1["sources"][source_id]
        assert "status" in source
        assert "coverage_complete" in source
        assert "as_of" in source
        assert "pages_fetched" in source
        assert "pages_expected" in source
    assert payload1["content_hash"] == payload2["content_hash"] == first["content_hash"] == second["content_hash"]
    assert payload1["queried_cnpj"] == VALID_CNPJ


def test_cli_empty_complete_twice_same_hash(tmp_path: Path, capsys) -> None:
    out1 = tmp_path / "empty-1.json"
    out2 = tmp_path / "empty-2.json"
    fixture = str(FIXTURES / "empty-complete.json")
    assert main(["replay", "--fixture", fixture, "--cnpj", VALID_CNPJ, "--out", str(out1)]) == 0
    capsys.readouterr()
    assert main(["replay", "--fixture", fixture, "--cnpj", VALID_CNPJ, "--out", str(out2)]) == 0
    capsys.readouterr()
    payload1 = json.loads(out1.read_text(encoding="utf-8"))
    payload2 = json.loads(out2.read_text(encoding="utf-8"))
    assert payload1["schema_version"] == SCHEMA_VERSION
    assert payload1["aggregate_state"] == "NO_MATCH_CONFIRMED"
    assert payload1["not_legal_conclusion"] is True
    assert payload1["sources"]["CEIS"]["coverage_complete"] is True
    assert payload1["sources"]["CNEP"]["coverage_complete"] is True
    assert payload1["records"] == []
    assert payload1["content_hash"] == payload2["content_hash"]


def test_module_entry_matches_main(tmp_path: Path) -> None:
    out = tmp_path / "module.json"
    proc = _run_module(["replay", "--fixture", str(FIXTURES / "matches.json"), "--cnpj", VALID_CNPJ, "--out", str(out)])
    assert proc.returncode == 0, proc.stderr
    summary = json.loads(proc.stdout)
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert summary["schema"] == SCHEMA_VERSION
    assert summary["aggregate_state"] == payload["aggregate_state"] == "MATCHES_FOUND"
    assert summary["content_hash"] == payload["content_hash"]
    assert payload["not_legal_conclusion"] is True

"""CLI entry point: real decide() path, deterministic replay."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.national_claims.cli import main
from scripts.national_claims.models import AUTHORIZATION_STATES

FIXTURES = Path("docs/contracts/national-claims/fixtures")


def test_cli_incomplete_national_twice_matches(tmp_path: Path, capsys) -> None:
    out1 = tmp_path / "run-1.json"
    out2 = tmp_path / "run-2.json"
    fixture = FIXTURES / "needs-data.json"
    assert main(["evaluate", "--input", str(fixture), "--out", str(out1)]) == 0
    first = json.loads(capsys.readouterr().out)
    assert main(["evaluate", "--input", str(fixture), "--out", str(out2)]) == 0
    second = json.loads(capsys.readouterr().out)
    assert first["authorization_state"] == second["authorization_state"] == "NEEDS_DATA"
    assert first["reason_codes"] == second["reason_codes"]
    assert first["content_hash"] == second["content_hash"]
    payload = json.loads(out1.read_text(encoding="utf-8"))
    assert payload["authorization_state"] in AUTHORIZATION_STATES
    assert payload["authorization_state"] != "AUTHORIZED"
    assert payload["consumer_view"] == "blocked"
    assert payload["extra_1093_used_as_denominator"] is False
    assert payload["row_count_used_as_completeness"] is False
    assert "unknown_partitions" in payload["reason_codes"]
    assert json.loads(out2.read_text(encoding="utf-8"))["content_hash"] == payload["content_hash"]


def test_cli_geo_limited_and_source_wide(tmp_path: Path, capsys) -> None:
    limited_out = tmp_path / "limited.json"
    wide_out = tmp_path / "wide.json"
    assert (
        main(
            [
                "evaluate",
                "--input",
                str(FIXTURES / "authorized-limited.json"),
                "--out",
                str(limited_out),
            ]
        )
        == 0
    )
    limited = json.loads(limited_out.read_text(encoding="utf-8"))
    assert limited["authorization_state"] == "AUTHORIZED_WITH_LIMITATIONS"
    assert limited["nacional_completo"] is False
    assert limited["consumer_view"] == "current"
    assert (
        main(
            [
                "evaluate",
                "--input",
                str(FIXTURES / "source-wide-only.json"),
                "--out",
                str(wide_out),
            ]
        )
        == 0
    )
    wide = json.loads(wide_out.read_text(encoding="utf-8"))
    assert wide["authorization_state"] != "AUTHORIZED"
    assert wide["identity"]["proves_entity_coverage"] is False
    assert wide["consumer_view"] in {"current", "lkg", "blocked"}
    capsys.readouterr()

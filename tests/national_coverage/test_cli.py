"""Drive the shipped CLI entry point twice on the same fixture."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

FIXTURE = Path("docs/contracts/national-coverage/fixtures/official-partial.json")


def _run(tmp_path: Path, name: str) -> tuple[dict, dict]:
    out = tmp_path / name
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.national_coverage",
            "evaluate",
            "--input",
            str(FIXTURE),
            "--out",
            str(out),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    summary = json.loads(proc.stdout)
    payload = json.loads(out.read_text(encoding="utf-8"))
    return summary, payload


def test_cli_two_independent_runs_match(tmp_path: Path) -> None:
    summary_1, payload_1 = _run(tmp_path, "run-1.json")
    summary_2, payload_2 = _run(tmp_path, "run-2.json")
    keys = (
        "verdict",
        "national_claim_authorized",
        "national_universe_id",
        "catalog_hash",
        "expected_partitions",
        "closed_partitions",
        "content_hash",
    )
    for key in keys:
        assert summary_1[key] == summary_2[key]
    assert payload_1["partitions"]["expected"] == summary_1["expected_partitions"]
    assert payload_1["partitions"]["closed"] == summary_1["closed_partitions"]
    assert payload_1["national_universe_id"] == payload_2["national_universe_id"]
    assert payload_1["content_hash"] == payload_2["content_hash"]
    assert payload_1["consumer"]["content_hash"] == payload_2["consumer"]["content_hash"]
    assert summary_1["verdict"] in {
        "NATIONAL_CLAIM_AUTHORIZED",
        "PARTIAL",
        "NOT_MEASURED",
        "BLOCKED",
    }
    assert summary_1["national_claim_authorized"] is False
    assert isinstance(summary_1["reason_codes"], list)


def test_cli_closed_toy_and_blocked_paths(tmp_path: Path) -> None:
    closed = Path("docs/contracts/national-coverage/fixtures/official-closed-toy.json")
    blocked = Path("docs/contracts/national-coverage/fixtures/official-blocked-observed.json")
    national = tmp_path / "national.json"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.national_coverage",
            "evaluate",
            "--input",
            str(closed),
            "--out",
            str(national),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    summary = json.loads(proc.stdout)
    assert summary["verdict"] == "NATIONAL_CLAIM_AUTHORIZED"
    assert summary["national_claim_authorized"] is True
    proc_blocked = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.national_coverage",
            "evaluate",
            "--input",
            str(blocked),
            "--out",
            str(tmp_path / "blocked.json"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    blocked_summary = json.loads(proc_blocked.stdout)
    assert blocked_summary["verdict"] == "BLOCKED"
    assert blocked_summary["national_claim_authorized"] is False

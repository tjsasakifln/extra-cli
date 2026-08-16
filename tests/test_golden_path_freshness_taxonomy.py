"""#349 — golden path must not label freshness never as stale."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.golden_path import classify_freshness_summary, format_freshness_gate_failure_lines

_NEVER = {
    "critical_sources": [
        {
            "source": "contracts",
            "freshness_status": "never",
            "last_success_at": None,
            "last_ingested_at": None,
            "latest_business_date": None,
            "recent_records": 0,
            "total_records": 0,
            "successful_runs": 0,
            "failure_reason": "No successful ingestion run found for critical source",
        }
    ],
    "overall": {"failing_sources": ["contracts"], "all_critical_sources_fresh": False},
}

_STALE = {
    "critical_sources": [
        {
            "source": "contracts",
            "freshness_status": "stale",
            "last_success_at": "2026-08-01T00:00:00+00:00",
            "last_ingested_at": "2026-08-01T00:00:00+00:00",
            "recent_records": 0,
            "total_records": 12,
            "successful_runs": 3,
            "failure_reason": "Last successful run is 300.0h old, above SLA 24h",
        }
    ],
    "overall": {"failing_sources": ["contracts"], "all_critical_sources_fresh": False},
}

_FRESH = {
    "critical_sources": [
        {
            "source": "pncp",
            "freshness_status": "fresh",
            "last_success_at": "2026-08-15T10:00:00+00:00",
            "last_ingested_at": "2026-08-15T10:00:00+00:00",
            "recent_records": 8,
            "total_records": 8,
            "successful_runs": 1,
            "failure_reason": None,
        }
    ],
    "overall": {"failing_sources": [], "all_critical_sources_fresh": True},
}


def test_never_is_missing_evidence_not_stale() -> None:
    classes = classify_freshness_summary(_NEVER)
    assert classes["never"] == ["contracts"]
    assert classes["missing_evidence"] == ["contracts"]
    assert classes["stale"] == []
    text = "\n".join(format_freshness_gate_failure_lines(_NEVER, duration_ms=12))
    assert "never/missing_evidence" in text
    assert "Sources stale:" not in text
    assert "Sources never/missing_evidence: contracts" in text


def test_stale_kept_separate_from_never() -> None:
    classes = classify_freshness_summary(_STALE)
    assert classes["stale"] == ["contracts"]
    assert classes["never"] == []
    text = "\n".join(format_freshness_gate_failure_lines(_STALE, duration_ms=12))
    assert "Sources stale: contracts" in text
    assert "never/missing_evidence" not in text


def test_fresh_not_in_failure_buckets() -> None:
    classes = classify_freshness_summary(_FRESH)
    assert classes["fresh"] == ["pncp"]
    assert classes["stale"] == []
    assert classes["never"] == []


def test_cli_render_never_and_stale_twice(tmp_path: Path) -> None:
    never_path = tmp_path / "never.json"
    stale_path = tmp_path / "stale.json"
    never_path.write_text(json.dumps(_NEVER), encoding="utf-8")
    stale_path.write_text(json.dumps(_STALE), encoding="utf-8")
    cmd = [sys.executable, "-m", "scripts.golden_path", "--render-freshness-json"]
    first = subprocess.run([*cmd, str(never_path)], capture_output=True, text=True, check=False)
    second = subprocess.run([*cmd, str(never_path)], capture_output=True, text=True, check=False)
    stale = subprocess.run([*cmd, str(stale_path)], capture_output=True, text=True, check=False)
    assert first.returncode == 2
    assert first.stdout == second.stdout
    assert "Sources stale:" not in first.stdout
    assert "never/missing_evidence" in first.stdout
    assert "Sources stale: contracts" in stale.stdout
    assert "Sources never" not in stale.stdout

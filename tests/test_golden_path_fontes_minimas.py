"""DoD §12.1 — golden path executes minimum essential sources (not mere config)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.golden_path import (
    ESSENTIAL_SOURCE_NAMES,
    SourceDef,
    SourceRecord,
    assert_essential_sources_executed,
    crawl_source,
    essential_sources,
)


def test_essential_sources_are_pncp_pcp_compras_gov() -> None:
    names = set(ESSENTIAL_SOURCE_NAMES)
    assert names == {"pncp", "pcp", "compras_gov"}
    assert {s.name for s in essential_sources()} == names


def test_assert_essential_requires_execution_not_config_only() -> None:
    # Config presence alone is insufficient: empty records fail.
    ok, details = assert_essential_sources_executed([])
    assert ok is False
    assert set(details["missing"]) == set(ESSENTIAL_SOURCE_NAMES)

    # attempts=0 does not count as executed
    fake = [
        SourceRecord(name=n, status="success", duration_ms=1, attempts=0, metrics={}) for n in ESSENTIAL_SOURCE_NAMES
    ]
    ok, details = assert_essential_sources_executed(fake)
    assert ok is False
    assert set(details["not_executed"]) == set(ESSENTIAL_SOURCE_NAMES)


def test_assert_essential_accepts_fail_as_executed() -> None:
    """Adapter ran but failed: still proves execution (persist is separate item)."""
    recs = [
        SourceRecord(
            name=n,
            status="fail",
            duration_ms=10,
            attempts=1,
            metrics={"fetched": 5},
            error="upsert",
        )
        for n in ESSENTIAL_SOURCE_NAMES
    ]
    ok, details = assert_essential_sources_executed(recs)
    assert ok is True
    assert len(details["executed"]) == 3


def test_crawl_source_invokes_monitor_for_each_essential(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Prove crawl_source launches monitor.py per essential source (not SOURCES list)."""
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        out = Path(cmd[cmd.index("--output-json") + 1])
        source = cmd[cmd.index("--source") + 1]
        payload = {
            "summary": {
                "total_fetched": 3,
                "total_transformed": 3,
                "total_inserted": 1,
                "total_updated": 0,
                "total_matched": 0,
                "total_persisted_opportunities": 1,
                "total_external_failures": 0,
                "sources_failed": 0,
            },
            "results": [
                {
                    "source": source,
                    "status": "success",
                    "fetched": 3,
                    "metadata": {},
                }
            ],
        }
        out.write_text(json.dumps(payload), encoding="utf-8")

        class R:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return R()

    import scripts.golden_path as gp

    monkeypatch.setattr(gp.subprocess, "run", fake_run)
    records = []
    for src in essential_sources():
        out = tmp_path / f"{src.name}.json"
        rec = crawl_source(src, "postgresql://test@localhost/db", out)
        records.append(rec)
        assert rec.attempts >= 1
        assert rec.status in {"success", "success_zero", "fail"}

    ok, details = assert_essential_sources_executed(records)
    assert ok is True, details
    # monitor.py invoked 3 times with each source name
    invoked_sources = set()
    for cmd in calls:
        assert any("monitor.py" in str(c) for c in cmd)
        invoked_sources.add(cmd[cmd.index("--source") + 1])
    assert invoked_sources == set(ESSENTIAL_SOURCE_NAMES)


def test_crawl_source_honors_json_failed_status(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Exit 0 + JSON status failed must not be silent success."""
    import scripts.golden_path as gp

    def fake_run(cmd, **kwargs):
        out = Path(cmd[cmd.index("--output-json") + 1])
        source = cmd[cmd.index("--source") + 1]
        out.write_text(
            json.dumps(
                {
                    "summary": {
                        "total_fetched": 10,
                        "total_transformed": 10,
                        "total_inserted": 0,
                        "total_updated": 0,
                        "total_matched": 0,
                        "total_persisted_opportunities": 0,
                        "total_external_failures": 0,
                        "sources_failed": 1,
                    },
                    "results": [
                        {
                            "source": source,
                            "status": "failed",
                            "fetched": 10,
                            "error_message": "Upsert failed: ON CONFLICT",
                            "metadata": {},
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        return R()

    monkeypatch.setattr(gp.subprocess, "run", fake_run)
    src = SourceDef(name="pcp", essential=True, description="t")
    rec = crawl_source(src, "postgresql://x", tmp_path / "pcp.json")
    assert rec.status == "fail"
    assert rec.attempts >= 1
    assert rec.metrics and int(rec.metrics.get("fetched") or 0) == 10


def test_help_documents_execute_sources_only() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "scripts.golden_path", "--help"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert r.returncode == 0
    assert "execute-sources-only" in (r.stdout + r.stderr)

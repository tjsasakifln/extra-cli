"""DoD §12.1 — canonical golden path command + metadata + fail-closed."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.golden_path import (
    collect_run_metadata,
    evaluate_run_outcome,
    SourceRecord,
    FreshnessRecord,
    ReportRecord,
)


def test_canonical_module_help() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "scripts.golden_path", "--help"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert r.returncode == 0
    out = r.stdout + r.stderr
    assert "strict" in out
    assert "bootstrap" in out or "Golden Path" in out


def test_collect_run_metadata_fields() -> None:
    meta = collect_run_metadata(dsn="postgresql://x@localhost/db")
    assert meta["canonical_command"] == "python3 -m scripts.golden_path"
    assert "limitations" in meta and meta["limitations"]
    assert "reference_period" in meta
    assert "as_of" in meta["reference_period"]
    # git may be unknown in some envs but key present
    assert "git_sha" in meta
    assert "schema_version" in meta or meta.get("migration_files_count", 0) >= 0


def test_fail_closed_non_zero_on_freshness() -> None:
    overall, code = evaluate_run_outcome(
        [
            SourceRecord(
                name="pcp",
                status="success",
                duration_ms=1,
                attempts=1,
                metrics={"fetched": 3},
            )
        ],
        {"pcp"},
        FreshnessRecord(status="fail"),
        [ReportRecord(type="excel", status="generated")],
        strict=True,
    )
    assert code != 0
    assert overall  # non-empty


def test_script_path_help() -> None:
    root = Path(__file__).resolve().parents[1]
    r = subprocess.run(
        [sys.executable, str(root / "scripts" / "golden_path.py"), "--help"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert r.returncode == 0


def test_help_documents_skip_migrations() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "scripts.golden_path", "--help"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert r.returncode == 0
    assert "skip-migrations" in (r.stdout + r.stderr)


def test_apply_migrations_function_exists_and_uses_apply_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DoD: golden path applies migrations via scripts.ops.apply_migrations."""
    from scripts import golden_path as gp

    calls: list[tuple] = []

    def fake_apply_range(dsn, root, **kwargs):
        calls.append((dsn, Path(root), kwargs.get("mode"), kwargs.get("max_num")))
        return {"applied": ["001_x.sql"], "skipped": ["002_y.sql"], "repaired": []}

    monkeypatch.setattr(
        "scripts.ops.apply_migrations.apply_range",
        fake_apply_range,
    )
    ok, dur, summary = gp.apply_migrations("postgresql://test@localhost/db")
    assert ok is True
    assert dur >= 0
    assert summary["applied"] == ["001_x.sql"]
    assert len(calls) == 1
    assert calls[0][0] == "postgresql://test@localhost/db"
    assert calls[0][2] == "upgrade"
    assert calls[0][3] is None  # all migrations


def test_help_documents_skip_seeds() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "scripts.golden_path", "--help"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert r.returncode == 0
    assert "skip-seeds" in (r.stdout + r.stderr)


def test_apply_seeds_runs_seed_scripts(monkeypatch: pytest.MonkeyPatch) -> None:
    """DoD: golden path applies seed scripts under db/seed/."""
    from scripts import golden_path as gp

    ran: list[str] = []

    def fake_run(cmd, **kwargs):
        ran.append(str(cmd[1]) if len(cmd) > 1 else str(cmd))

        class R:
            returncode = 0
            stderr = ""
            stdout = "ok"

        return R()

    monkeypatch.setattr(gp.subprocess, "run", fake_run)
    ok, dur, summary = gp.apply_seeds("postgresql://test@localhost/db")
    assert ok is True
    assert dur >= 0
    assert len(summary["ran"]) == 2
    assert not summary["failed"]
    assert not summary["missing"]
    assert any("001_sc_entities" in p for p in summary["ran"])
    assert any("002_entity_aliases" in p for p in summary["ran"])
    assert len(ran) == 2

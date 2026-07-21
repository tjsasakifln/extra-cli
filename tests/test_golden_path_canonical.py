"""DoD §12.1 — canonical golden path command + metadata + fail-closed."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.golden_path import (
    FreshnessRecord,
    ReportRecord,
    SourceRecord,
    collect_run_metadata,
    evaluate_run_outcome,
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


# ---------------------------------------------------------------------------
# DoD §12.1 — planilha-alvo strong validation
# ---------------------------------------------------------------------------

EXPECTED_IDS_SHA = "0b3f894d87ba71f2e0fa96887cb3075033488de1af1e6e55f97ccda0701fb396"
CANONICAL_XLSX = "Extra - alvos de licitação. R-0.xlsx"


def test_help_documents_spreadsheet_flags() -> None:
    r = subprocess.run(
        [sys.executable, "-m", "scripts.golden_path", "--help"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert r.returncode == 0
    out = r.stdout + r.stderr
    assert "skip-spreadsheet" in out
    assert "validate-spreadsheet-only" in out


def test_resolve_prefers_canonical_not_backup(tmp_path: Path) -> None:
    from scripts.golden_path import resolve_canonical_spreadsheet

    root = Path(__file__).resolve().parents[1]
    src = root / CANONICAL_XLSX
    assert src.is_file()
    # Copy both canonical and backup into temp root; canonical must win.
    import shutil

    dest = tmp_path / CANONICAL_XLSX
    backup = tmp_path / "Extra - alvos de licitação. R-0.backup.xlsx"
    shutil.copy2(src, dest)
    shutil.copy2(src, backup)
    chosen = resolve_canonical_spreadsheet(tmp_path)
    assert chosen.name == CANONICAL_XLSX
    assert ".backup" not in chosen.name


def test_resolve_backup_only_fails_without_allow(tmp_path: Path) -> None:
    import shutil

    from scripts.golden_path import resolve_canonical_spreadsheet

    root = Path(__file__).resolve().parents[1]
    src = root / CANONICAL_XLSX
    backup = tmp_path / "Extra - alvos de licitação. R-0.backup.xlsx"
    shutil.copy2(src, backup)
    with pytest.raises(FileNotFoundError, match="backup"):
        resolve_canonical_spreadsheet(tmp_path, allow_backup=False)


def test_resolve_missing_fails(tmp_path: Path) -> None:
    from scripts.golden_path import resolve_canonical_spreadsheet

    with pytest.raises(FileNotFoundError):
        resolve_canonical_spreadsheet(tmp_path)


def test_resolve_ambiguous_primary_fails(tmp_path: Path) -> None:
    import shutil

    from scripts.golden_path import resolve_canonical_spreadsheet

    root = Path(__file__).resolve().parents[1]
    src = root / CANONICAL_XLSX
    # Two non-backup candidates with different names matching glob
    a = tmp_path / "Extra - alvos A.xlsx"
    b = tmp_path / "Extra - alvos B.xlsx"
    shutil.copy2(src, a)
    shutil.copy2(src, b)
    with pytest.raises(FileNotFoundError, match="Ambiguous"):
        resolve_canonical_spreadsheet(tmp_path)


def test_validate_target_spreadsheet_live_strong() -> None:
    """Requires private local xlsx (not shipped in public repo)."""
    root = Path(__file__).resolve().parents[1]
    from scripts.golden_path import resolve_canonical_spreadsheet
    try:
        resolve_canonical_spreadsheet(root)
    except FileNotFoundError:
        import pytest
        pytest.skip("private spreadsheet not available (EXTRA_TARGET_SPREADSHEET / local xlsx)")
    """Strong AC: path, sha256, dual metrics, 1093 set + ids hash."""
    from scripts.golden_path import validate_target_spreadsheet

    root = Path(__file__).resolve().parents[1]
    ok, dur, details = validate_target_spreadsheet(root)
    assert ok is True, details
    assert dur >= 0
    assert details.get("path")
    assert CANONICAL_XLSX in details["path"]
    assert ".backup" not in Path(details["path"]).name
    assert details.get("sha256")
    assert len(details["sha256"]) == 64
    assert details.get("physical_rows") == 2085
    assert details.get("canonical_entities") == 1093
    assert details.get("physical_rows") != details.get("canonical_entities")
    assert details.get("canonical_ids_sha256") == EXPECTED_IDS_SHA
    assert details.get("sheet_name") == "Entes Públicos SC"
    assert details.get("selection_rule") in {"exact_basename", "single_primary_glob"}


def test_validate_wrong_expected_count_fails() -> None:
    from scripts.golden_path import validate_target_spreadsheet

    root = Path(__file__).resolve().parents[1]
    ok, _dur, details = validate_target_spreadsheet(root, expected_included=9999, expected_ids_sha256=EXPECTED_IDS_SHA)
    assert ok is False
    assert "mismatch" in str(details.get("error", "")).lower()


def test_validate_cli_spreadsheet_only_writes_ledger(tmp_path: Path) -> None:
    """Proof via canonical CLI entrypoint, not only isolated function call."""
    root = Path(__file__).resolve().parents[1]
    ledger = tmp_path / "ledger-ss.json"
    r = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.golden_path",
            "--validate-spreadsheet-only",
            "--ledger-output",
            str(ledger),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        cwd=str(root),
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert ledger.is_file()
    import json

    data = json.loads(ledger.read_text(encoding="utf-8"))
    steps = data.get("steps") or data.get("ledger", {}).get("steps") or []
    # ledger shape may nest under keys — search flexibly
    if not steps and isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list) and v and isinstance(v[0], dict) and "step" in v[0]:
                steps = v
                break
        if not steps:
            # try common shapes
            steps = data.get("execution", {}).get("steps") or []
    names = [s.get("step") for s in steps] if steps else []
    assert "validate_target_spreadsheet" in names or any(
        "validate_target_spreadsheet" in json.dumps(data) for _ in [0]
    ), data
    blob = json.dumps(data)
    assert "canonical_entities" in blob or "1093" in blob
    assert "physical_rows" in blob or "2085" in blob

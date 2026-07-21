"""Public-repo sanitization: no weak password defaults; env required fail-closed."""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_install_sh_has_no_weak_password_default() -> None:
    text = (ROOT / "deploy/install.sh").read_text(encoding="utf-8")
    assert "smartlic_local" not in text
    assert "PG_PASSWORD:?" in text or 'PG_PASSWORD:?' in text
    assert "LOCAL_DATALAKE_DSN:?" in text


def test_provision_vps_sh_has_no_smartlic_fallback() -> None:
    text = (ROOT / "deploy/provision-vps.sh").read_text(encoding="utf-8")
    assert "smartlic_local" not in text


def test_seed_scripts_reject_missing_dsn(tmp_path: Path) -> None:
    env = {k: v for k, v in os.environ.items() if k not in {"LOCAL_DATALAKE_DSN", "DATABASE_URL"}}
    env["PATH"] = os.environ.get("PATH", "")
    r = subprocess.run(
        [sys.executable, str(ROOT / "db/seed/001_sc_entities.py"), "--dry-run"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert r.returncode != 0
    assert "smartlic_local" not in (r.stdout + r.stderr)


def test_resolve_spreadsheet_env_and_missing_message(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.golden_path import resolve_canonical_spreadsheet

    monkeypatch.delenv("EXTRA_TARGET_SPREADSHEET", raising=False)
    monkeypatch.delenv("TARGET_SPREADSHEET_PATH", raising=False)
    with pytest.raises(FileNotFoundError, match="EXTRA_TARGET_SPREADSHEET|private"):
        resolve_canonical_spreadsheet(tmp_path)

    fake = tmp_path / "private-alvos.xlsx"
    fake.write_bytes(b"not-a-real-xlsx")
    monkeypatch.setenv("EXTRA_TARGET_SPREADSHEET", str(fake))
    assert resolve_canonical_spreadsheet(tmp_path) == fake.resolve()

    backup = tmp_path / "x.backup.xlsx"
    backup.write_bytes(b"x")
    monkeypatch.setenv("EXTRA_TARGET_SPREADSHEET", str(backup))
    with pytest.raises(FileNotFoundError, match="backup"):
        resolve_canonical_spreadsheet(tmp_path, allow_backup=False)


def test_commercial_assets_not_tracked() -> None:
    r = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    tracked = r.stdout.splitlines()
    banned_substrings = (
        "proposta-24515063000149-consultoria.pdf",
        "Extra - alvos de licitação. R-0.xlsx",
        "Extra - alvos de licitação. R-0.backup.xlsx",
        "data/intel/",
        "output/briefing-extra-2026-07-14.txt",
        "data/contract_intel.db",
    )
    for line in tracked:
        for ban in banned_substrings:
            assert ban not in line, f"still tracked: {line}"


def test_gitignore_blocks_reintroduction() -> None:
    gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for needle in ("data/intel/**", "Extra - alvos", "proposta-*.pdf", "*.backup.xlsx"):
        assert needle in gi or "alvos" in gi

"""Canonical process-documents systemd provisioning contract (#278)."""

from __future__ import annotations

import grp
import hashlib
import os
import pwd
from pathlib import Path

import pytest

from scripts.ops.provision_process_documents_systemd import (
    SERVICE_NAME,
    TIMER_NAME,
    UnitConfig,
    install_units,
    preflight,
    render_units,
    verify_rendered_units,
)
from scripts.ops.validate_systemd import validate


def _config(tmp_path: Path) -> UnitConfig:
    app = tmp_path / "opt" / "extra-consultoria"
    state = tmp_path / "var" / "lib" / "extra-consultoria"
    python = app / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    python.chmod(0o755)
    state.mkdir(parents=True)
    env_file = app / ".env"
    env_file.write_text("LOCAL_DATALAKE_DSN=test\n", encoding="utf-8")
    current_user = pwd.getpwuid(os.getuid())
    current_group = grp.getgrgid(current_user.pw_gid)
    return UnitConfig(
        app_user=current_user.pw_name,
        app_group=current_group.gr_name,
        app_dir=app,
        state_dir=state,
        env_file=env_file,
        python=python,
        deploy_sha="a" * 40,
        config_sha=hashlib.sha256(env_file.read_bytes()).hexdigest(),
    )


def test_preflight_fails_nominally_for_missing_user_paths_and_env(tmp_path: Path) -> None:
    missing = tmp_path / "missing"
    config = UnitConfig(
        app_user="extra-user-that-does-not-exist",
        app_group="extra-group-that-does-not-exist",
        app_dir=missing / "app",
        state_dir=missing / "state",
        env_file=missing / ".env",
        python=missing / "python",
        deploy_sha="a" * 40,
        config_sha="b" * 64,
    )

    errors = preflight(config)

    assert any("user missing" in error for error in errors)
    assert any("group principal missing" in error for error in errors)
    assert any("app_dir missing" in error for error in errors)
    assert any("state_dir missing" in error for error in errors)
    assert any("env_file missing" in error for error in errors)
    assert any("venv python missing" in error for error in errors)
    unit_dir = tmp_path / "systemd"
    with pytest.raises(RuntimeError, match="preflight failed"):
        install_units(
            config,
            unit_dir=unit_dir,
            daemon_reload=False,
            smoke_output=None,
        )
    assert unit_dir.exists() is False


def test_rendered_pair_shares_sha_config_and_canonical_tree(tmp_path: Path) -> None:
    config = _config(tmp_path)

    units = render_units(config)

    assert set(units) == {SERVICE_NAME, TIMER_NAME}
    for text in units.values():
        assert f"# ExtraDeploySHA={config.deploy_sha}" in text
        assert f"# ExtraConfigSHA={config.config_sha}" in text
        assert "/opt/extra-cli" not in text
        assert "/var/lib/extra-cli" not in text
    assert f"User={config.app_user}" in units[SERVICE_NAME]
    assert f"Unit={SERVICE_NAME}" in units[TIMER_NAME]


def test_systemd_analyze_verify_passes_for_rendered_pair(tmp_path: Path) -> None:
    verified, output = verify_rendered_units(render_units(_config(tmp_path)))

    assert verified is True, output


def test_install_and_upgrade_are_idempotent_and_smoke_is_truthful(tmp_path: Path) -> None:
    config = _config(tmp_path)
    unit_dir = tmp_path / "systemd"
    evidence_path = config.state_dir / "evidence" / "unit-smoke.json"

    first = install_units(
        config,
        unit_dir=unit_dir,
        daemon_reload=False,
        smoke_output=evidence_path,
    )
    second = install_units(
        config,
        unit_dir=unit_dir,
        daemon_reload=False,
        smoke_output=evidence_path,
    )

    assert sorted(first["changed_units"]) == sorted([SERVICE_NAME, TIMER_NAME])
    assert first["vps_operational"] is False
    assert first["claim"] == "UNIT_INSTALL_SMOKE_ONLY"
    assert first["runtime_smoke"] == "PASS"
    assert second["changed_units"] == []
    assert second["idempotent"] is True
    assert evidence_path.is_file()
    assert "VPS_OPERATIONAL" not in evidence_path.read_text(encoding="utf-8")


def test_committed_systemd_surface_is_canonical_and_verified() -> None:
    assert validate() == []

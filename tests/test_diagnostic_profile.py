"""Tests for DoD diagnostic profile audit (Extra Construtora)."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts.ops.diagnostic_profile import (
    DEFAULT_PROFILE,
    audit_diagnostic_profile,
    load_raw_profile,
    profile_stamp,
)


def test_canonical_profile_exists() -> None:
    assert DEFAULT_PROFILE.is_file()
    raw = load_raw_profile()
    assert raw["profile_id"] == "extra_construtora"
    assert int(raw["version"]) >= 1


def test_audit_passes_on_repo_profile() -> None:
    report = audit_diagnostic_profile()
    assert report["ok"] is True
    assert report["summary"]["fail"] == 0
    assert report["summary"]["pass"] == 10
    ids = {c["item_id"] for c in report["checks"]}
    assert "canonical_profile" in ids
    assert "region_universe" in ids
    assert "work_types" in ids
    assert "value_bands" in ids
    assert "modalities" in ids
    assert "operational_constraints" in ids
    assert "priority_organs" in ids
    assert "known_competitors" in ids
    assert "yaml_centralized" in ids
    assert "report_profile_version" in ids


def test_stamp_includes_version() -> None:
    stamp = profile_stamp()
    assert stamp["profile_id"]
    assert stamp["version"] is not None
    assert "@v" in stamp["stamp"]


def test_missing_profile_fails(tmp_path: Path) -> None:
    missing = tmp_path / "nope.yaml"
    with pytest.raises(FileNotFoundError):
        load_raw_profile(missing)
    report = audit_diagnostic_profile(missing)
    assert report["ok"] is False


def test_broken_profile_fails_region(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        yaml.safe_dump(
            {
                "profile_id": "x",
                "version": 1,
                "display_name": "X",
                # no region
                "desired_object_types": [],
                "engineering_categories": [],
                "priority_modalities": [],
                "operational_constraints": [],
                "priority_organs": [],
                "known_competitors": [],
                "minimum_value": None,
                "maximum_value": None,
            }
        ),
        encoding="utf-8",
    )
    report = audit_diagnostic_profile(bad)
    assert report["ok"] is False
    by = {c["item_id"]: c for c in report["checks"]}
    assert by["region_universe"]["status"] == "FAIL"
    assert by["work_types"]["status"] == "FAIL"

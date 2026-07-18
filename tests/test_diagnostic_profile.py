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
    # Core structural checks must PASS; yaml_centralized / report_version may be PARTIAL
    by = {c["item_id"]: c for c in report["checks"]}
    for kid in (
        "canonical_profile",
        "region_universe",
        "work_types",
        "value_bands",
        "modalities",
        "operational_constraints",
        "priority_organs",
        "known_competitors",
    ):
        assert by[kid]["status"] == "PASS", kid
    assert by["yaml_centralized"]["status"] in {"PASS", "PARTIAL"}
    assert by["report_profile_version"]["status"] in {"PASS", "PARTIAL"}
    assert report["summary"]["pass"] + report["summary"].get("partial", 0) >= 8


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

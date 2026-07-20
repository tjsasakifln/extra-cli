"""Tests for evidence reconstruction — cycle-2 material DoD advance."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.ops.evidence_reconstruct import reconstruct_from_artifacts


def test_reconstruct_pass_when_artifacts_present(tmp_path: Path):
    snap = tmp_path / "snapshot.json"
    snap.write_text(json.dumps({"opportunities": [{"id": 1}]}, indent=2), encoding="utf-8")
    import hashlib

    h = hashlib.sha256(snap.read_bytes()).hexdigest()
    csums = tmp_path / "checksums.json"
    csums.write_text(json.dumps({"snapshot.json": h}), encoding="utf-8")
    out = reconstruct_from_artifacts(
        snapshot_path=snap,
        checksums_path=csums,
        root=tmp_path,
        out_dir=tmp_path / "out",
    )
    assert out["status"] in {"PASS", "PARTIAL"}
    assert (tmp_path / "out" / "reconstructed-evidence.json").is_file()
    assert any(a["name"] == "snapshot" for a in out["verified_artifacts"])


def test_reconstruct_unproven_when_missing(tmp_path: Path):
    out = reconstruct_from_artifacts(
        snapshot_path=tmp_path / "nope.json",
        root=tmp_path,
        out_dir=tmp_path / "out",
    )
    assert out["status"] in {"UNPROVEN", "PARTIAL", "FAIL"}
    assert "snapshot" in out["missing"] or out["status"] != "PASS"


def test_checksum_mismatch_detected(tmp_path: Path):
    snap = tmp_path / "snapshot.json"
    snap.write_text("{}", encoding="utf-8")
    csums = tmp_path / "checksums.json"
    csums.write_text(json.dumps({"snapshot.json": "0" * 64}), encoding="utf-8")
    out = reconstruct_from_artifacts(
        snapshot_path=snap,
        checksums_path=csums,
        root=tmp_path,
        out_dir=tmp_path / "out",
    )
    assert out["mismatches"] or out["status"] != "PASS"

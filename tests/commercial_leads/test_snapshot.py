"""Snapshot manifest validation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.commercial_leads.snapshot import validate_snapshot_manifest, write_default_manifest


def test_fixture_rejected(tmp_path):
    man = tmp_path / "m.json"
    man.write_text(
        json.dumps({"fixture": True, "sha256": "abc", "dump_path": "x.dump", "contracts_count": 1}),
        encoding="utf-8",
    )
    r = validate_snapshot_manifest(man, verify_file_hash=False)
    assert not r.ok
    assert "BLOCKED" in r.status


def test_hash_match(tmp_path):
    dump = tmp_path / "x.dump"
    dump.write_bytes(b"hello-contracts")
    h = hashlib.sha256(b"hello-contracts").hexdigest()
    man = write_default_manifest(
        tmp_path / "snap.json",
        dump_path=dump,
        sha256=h,
        contracts_count=10,
        package="test",
        exported_at_utc="20260725T000000Z",
    )
    r = validate_snapshot_manifest(man, verify_file_hash=True)
    assert r.ok
    assert r.snapshot_hash == h


def test_hash_mismatch(tmp_path):
    dump = tmp_path / "x.dump"
    dump.write_bytes(b"hello")
    man = tmp_path / "m.json"
    man.write_text(
        json.dumps(
            {
                "fixture": False,
                "sha256": "0" * 64,
                "dump_path": str(dump),
                "contracts_count": 1,
            }
        ),
        encoding="utf-8",
    )
    r = validate_snapshot_manifest(man, verify_file_hash=True)
    assert not r.ok
    assert r.status == "FAIL"

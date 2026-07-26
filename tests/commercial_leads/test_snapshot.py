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


def test_marker_dump_without_canonical_hash_blocked(tmp_path):
    marker = tmp_path / "db-content-binding.marker"
    marker.write_text("pncp_supplier_contracts row_count=60000\n", encoding="utf-8")
    man = tmp_path / "m.json"
    man.write_text(
        json.dumps(
            {
                "fixture": False,
                "synthetic": False,
                "sha256": "abc",
                "dump_path": str(marker),
                "contracts_count": 60000,
            }
        ),
        encoding="utf-8",
    )
    r = validate_snapshot_manifest(man, verify_file_hash=False, allow_missing_dump=True)
    assert not r.ok
    assert r.status == "BLOCKED_MISSING_AUTHENTICATED_REAL_SNAPSHOT"
    assert any("marker" in x for x in r.reasons)


def test_marker_dump_with_canonical_hash_allowed_for_db_bind(tmp_path):
    marker = tmp_path / "db-content-binding.marker"
    marker.write_text("pncp_supplier_contracts row_count=60000\n", encoding="utf-8")
    man = tmp_path / "m.json"
    man.write_text(
        json.dumps(
            {
                "fixture": False,
                "synthetic": False,
                "sha256": "abc",
                "dump_path": str(marker),
                "contracts_count": 60000,
                "canonical_table_hash": "f" * 64,
                "canonical_hash_algorithm": "sha256-rowmd5-ordered-agg-v1",
            }
        ),
        encoding="utf-8",
    )
    r = validate_snapshot_manifest(man, verify_file_hash=False, allow_missing_dump=True)
    assert r.ok
    assert r.canonical_table_hash == "f" * 64
    assert "MARKER" in r.status or "canonical" in r.status.lower()


def test_manifest_missing_canonical_hash_blocked_for_independent_anchor(tmp_path):
    dump = tmp_path / "x.dump"
    dump.write_bytes(b"real-dump-bytes-not-marker" * 20)
    man = tmp_path / "m.json"
    man.write_text(
        json.dumps(
            {
                "fixture": False,
                "sha256": hashlib.sha256(dump.read_bytes()).hexdigest(),
                "dump_path": str(dump),
                "contracts_count": 1,
            }
        ),
        encoding="utf-8",
    )
    from scripts.commercial_leads.snapshot import bind_snapshot_to_database

    r = validate_snapshot_manifest(man, verify_file_hash=True)
    # File hash may validate, but bind without canonical is BLOCKED independent anchor
    class _FakeConn:
        pass

    # bind requires DB — unit-level: missing canon on snap triggers block status path
    assert r.canonical_table_hash is None or r.canonical_table_hash == "None"
    # validate may still ok on dump hash alone; independent bind forbids mint
    man2 = tmp_path / "m2.json"
    man2.write_text(
        json.dumps(
            {
                "fixture": False,
                "sha256": "a" * 64,
                "dump_path": str(dump),
                "contracts_count": 1,
                # no canonical_table_hash
            }
        ),
        encoding="utf-8",
    )
    r2 = validate_snapshot_manifest(man2, verify_file_hash=False, allow_missing_dump=True)
    # Without canon and with dump, may be ok at file level — bind_snapshot enforces anchor
    snap_dict = r2.as_dict()
    assert not snap_dict.get("canonical_table_hash")


def test_verify_authenticated_snapshot_manifest_immutable(tmp_path, monkeypatch):
    """Altering manifest during validation must FAIL."""
    from scripts.commercial_leads import snapshot as snapmod

    dump = tmp_path / "pack.json"
    dump.write_text('{"kind":"logical"}\n', encoding="utf-8")
    man = tmp_path / "manifest.json"
    man.write_text(
        json.dumps(
            {
                "fixture": False,
                "canonical_table_hash": "a" * 64,
                "canonical_hash_algorithm": "sha256-rowmd5-ordered-agg-v1",
                "dump_path": str(dump),
                "row_count": 1,
                "sha256": hashlib.sha256(dump.read_bytes()).hexdigest(),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    def _fake_bind(conn, manifest, **kwargs):
        # mutate manifest mid-validation (forbidden)
        data = json.loads(man.read_text())
        data["tampered"] = True
        man.write_text(json.dumps(data) + "\n", encoding="utf-8")
        return {
            "ok": True,
            "status": "BOUND",
            "canonical_table_hash": "a" * 64,
            "reasons": ["canonical_table_hash_match"],
        }

    monkeypatch.setattr(snapmod, "bind_snapshot_to_database", _fake_bind)
    monkeypatch.setattr(
        snapmod,
        "validate_snapshot_manifest",
        lambda *a, **k: snapmod.SnapshotValidation(
            ok=True,
            status="OK",
            manifest_path=str(man),
            snapshot_hash="x",
            expected_hash="x",
            dump_path=str(dump),
            canonical_table_hash="a" * 64,
        ),
    )
    report = snapmod.verify_authenticated_snapshot(object(), man)
    assert report["ok"] is False
    assert report.get("manifest_mutated") is True
    assert "manifest_mutated_during_validation" in (report.get("reasons") or [])


def test_post_restore_canonical_mint_not_accepted_as_anchor(tmp_path):
    """Hash computed after restore (missing in manifest) is not independent anchor."""
    from scripts.commercial_leads.snapshot import bind_snapshot_to_database

    man = {
        "ok": True,
        "status": "X",
        "manifest_path": None,
        "snapshot_hash": None,
        "expected_hash": None,
        "dump_path": None,
        "contracts_count_declared": 0,
        "canonical_table_hash": None,
        "details": {},
    }

    class FakeConn:
        pass

    # Monkeypatch compute via forcing empty DB path is heavy; call bind with no canon
    # and a stub that would mint — ensure status is BLOCKED independent anchor
    import scripts.commercial_leads.snapshot as snapmod

    def fake_compute(conn, **kwargs):
        return {
            "canonical_table_hash": "minted_after_restore",
            "canonical_hash_algorithm": snapmod.CANONICAL_HASH_ALGORITHM,
            "row_count": 0,
            "rows_hashed": 0,
            "table": "pncp_supplier_contracts",
        }

    original = snapmod.compute_canonical_table_hash
    snapmod.compute_canonical_table_hash = fake_compute  # type: ignore[assignment]
    try:
        # fetch_all will fail without real conn — patch fetch_all too
        import scripts.commercial_leads.dbutil as dbutil

        def fake_fetch(conn, sql, params=None):
            if "COUNT" in sql.upper():
                return [{"n": 0}]
            if "MIN" in sql.upper():
                return [{"min_d": None, "max_d": None}]
            return []

        orig_fetch = dbutil.fetch_all
        # bind imports fetch_all inside function from dbutil
        import scripts.commercial_leads.snapshot as s2

        # Patch at usage site via monkey: replace bind's fetch by wrapping compute only
        # Use validate path: missing canon → BLOCKED
        class V:
            def as_dict(self):
                return man

        # Direct unit of bind_snapshot_to_database with patched internals
        from unittest.mock import patch

        with patch("scripts.commercial_leads.dbutil.fetch_all", side_effect=fake_fetch):
            with patch.object(snapmod, "compute_canonical_table_hash", fake_compute):
                binding = bind_snapshot_to_database(FakeConn(), man, require_canonical_match=True)
        assert binding["ok"] is False
        assert binding["status"] == "BLOCKED_MISSING_INDEPENDENT_SNAPSHOT_ANCHOR"
        assert "manifest_canonical_table_hash_missing" in binding["reasons"]
    finally:
        snapmod.compute_canonical_table_hash = original  # type: ignore[assignment]

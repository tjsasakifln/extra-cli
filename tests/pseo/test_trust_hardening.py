"""Trust-hardening gates for PR #187 pSEO export."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.pseo.approval import (
    approval_hash,
    verify_approval_for_publish,
    write_approval_template,
)
from scripts.pseo.atomic_io import write_snapshot_atomic
from scripts.pseo.jsonschema_export import build_json_schema
from scripts.pseo.models import ApprovalArtifact, validate_public_payload
from scripts.pseo.pipeline import build_export, load_from_fixture, write_export
from scripts.pseo.privacy import suppress_small_cells
from scripts.pseo.provenance import EXPORT_VERSION, compute_dataset_hash


def test_unexpected_field_fails_closed() -> None:
    with pytest.raises(ValueError, match="validation failed"):
        validate_public_payload(
            "markets",
            [
                {
                    "id": "m1",
                    "slug": "x",
                    "contract_count": 1,
                    "score_total": 99,  # forbidden commercial signal + extra
                }
            ],
        )


def test_forbid_extra_on_opportunity() -> None:
    with pytest.raises(ValueError, match="validation failed"):
        validate_public_payload(
            "opportunities",
            [
                {
                    "id": "o1",
                    "slug": "s",
                    "open_count": 0,
                    "commercial_state": "hot",
                }
            ],
        )


def test_json_schema_is_real_draft() -> None:
    schema = build_json_schema()
    assert schema["$schema"].startswith("https://json-schema.org/")
    assert "additionalProperties" in schema
    assert schema["additionalProperties"] is False
    assert "Archetype" in schema["$defs"]
    assert schema["$defs"]["Market"].get("additionalProperties") is False


def test_small_cell_suppression() -> None:
    cells = [
        {"name": "A", "contract_count": 1},
        {"name": "B", "contract_count": 10},
        {"name": "C", "contract_count": 2},
    ]
    public, meta = suppress_small_cells(cells, min_cell=5)
    assert meta["suppressed_cells"] == 2
    names = [c["name"] for c in public]
    assert "B" in names
    assert any("outros" in str(n).lower() for n in names)
    assert "A" not in names


def test_approval_gate_binds_dataset_hash() -> None:
    art = ApprovalArtifact(
        decision="APPROVED",
        dataset_hash="a" * 64,
        schema_version="1.1.0",
        exporter_version=EXPORT_VERSION,
        source_commit_sha="deadbeef",
        actor="qa@example.com",
        approved_at="2026-07-31T12:00:00Z",
    )
    ok = verify_approval_for_publish(
        art,
        dataset_hash="a" * 64,
        schema_version="1.1.0",
        exporter_version=EXPORT_VERSION,
        source_commit_sha="deadbeef",
    )
    assert ok["publish_ready"] is True
    assert ok["indexable"] is True

    bad = verify_approval_for_publish(
        art,
        dataset_hash="b" * 64,
        schema_version="1.1.0",
        exporter_version=EXPORT_VERSION,
        source_commit_sha="deadbeef",
    )
    assert bad["publish_ready"] is False
    assert bad["status"] == "INVALID_APPROVAL"

    missing = verify_approval_for_publish(
        None,
        dataset_hash="a" * 64,
        schema_version="1.1.0",
        exporter_version=EXPORT_VERSION,
        source_commit_sha="deadbeef",
    )
    assert missing["status"] == "REVIEW_REQUIRED"
    assert missing["indexable"] is False


def test_atomic_write_preserves_prior_on_failure(tmp_path: Path) -> None:
    out = tmp_path / "snap"
    out.mkdir()
    (out / "manifest.json").write_text('{"ok": true, "prior": true}\n', encoding="utf-8")

    def boom(_path: Path) -> dict:
        return {"ok": False, "errors": ["intentional"]}

    with pytest.raises(RuntimeError, match="validation failed"):
        write_snapshot_atomic(
            out,
            {"manifest.json": '{"ok": false}\n'},
            validate=boom,
            dataset_hash=None,
        )
    # prior preserved
    assert json.loads((out / "manifest.json").read_text(encoding="utf-8"))["prior"] is True


def test_fixture_export_candidate_not_indexable(tmp_path: Path) -> None:
    contracts, bids, counts = load_from_fixture(Path("tests/pseo/fixtures/sample_contracts.json"))
    bundle = build_export(contracts, bids, counts, top20_path=None, as_of="2026-07-31")
    out = tmp_path / "export"
    write_export(out, bundle, approval_path=None)
    man = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert man.get("indexable") is False
    assert man.get("snapshot_status") == "CANDIDATE"
    assert (out / "schema.json").is_file()
    schema = json.loads((out / "schema.json").read_text(encoding="utf-8"))
    assert "$schema" in schema
    assert (out / "CURRENT.json").is_file()


def test_approval_template_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "approval.json"
    write_approval_template(
        path,
        dataset_hash="c" * 64,
        source_commit_sha="abc123",
        actor="human@confenge",
        schema_version="1.1.0",
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["approval_hash"] == approval_hash(data)


def test_chunked_loader_exists_and_no_fetchall_in_source() -> None:
    src = Path("scripts/pseo/pipeline.py").read_text(encoding="utf-8")
    assert "fetchmany" in src
    assert "server_side_cursor" in src or "name=\"pseo_" in src or "name='pseo_" in src
    # fetchall should not remain on the large-table path
    assert "cur.fetchall()" not in src


def test_dataset_hash_stable_for_body() -> None:
    body = {
        "archetypes": [],
        "markets": [],
        "agencies": [],
        "prices": [],
        "competition": [],
        "opportunities": [],
        "problem_service": [],
        "icp_methodology": {"schema_version": "1.1.0"},
    }
    h1 = compute_dataset_hash(body)
    h2 = compute_dataset_hash(body)
    assert h1 == h2
    assert len(h1) == 64

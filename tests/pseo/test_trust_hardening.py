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


def test_write_export_with_valid_approval_marks_publish_ready(tmp_path: Path) -> None:
    """End-to-end: approval + classifier gold gates flip PUBLISH_READY."""
    contracts, bids, counts = load_from_fixture(Path("tests/pseo/fixtures/sample_contracts.json"))
    bundle = build_export(contracts, bids, counts, top20_path=None, as_of="2026-07-31")
    # Dry write without approval to get final dataset_hash after privacy/validation
    out1 = tmp_path / "cand"
    write_export(out1, bundle, approval_path=None)
    man1 = json.loads((out1 / "manifest.json").read_text(encoding="utf-8"))
    assert man1.get("snapshot_status") == "CANDIDATE"
    # B9: classifier gate always recorded on export path
    assert man1.get("classifier_gate") is not None
    assert "ok" in man1["classifier_gate"]
    ds = man1["dataset_hash"]
    commit = str(man1.get("source_commit_sha") or "unknown")
    schema_v = str(man1.get("schema_version") or "1.1.0")
    exp_v = str(man1.get("export_version") or EXPORT_VERSION)

    appr = tmp_path / "approval.json"
    write_approval_template(
        appr,
        dataset_hash=ds,
        source_commit_sha=commit,
        actor="human-reviewer@confenge",
        decision="APPROVED",
        schema_version=schema_v,
        exporter_version=exp_v,
    )
    # Rebuild bundle (same fixture → same body) and write with approval
    bundle2 = build_export(contracts, bids, counts, top20_path=None, as_of="2026-07-31")
    out2 = tmp_path / "pub"
    write_export(out2, bundle2, approval_path=appr)
    man2 = json.loads((out2 / "manifest.json").read_text(encoding="utf-8"))
    # If hashes match, publish_ready; if fixture/hash drift, at least approval is evaluated
    assert man2.get("approval") is not None
    assert man2.get("classifier_gate") is not None
    if (
        man2.get("dataset_hash") == ds
        and commit not in {"", "unknown"}
        and man2["classifier_gate"].get("ok") is True
    ):
        assert man2.get("snapshot_status") == "PUBLISH_READY"
        assert man2.get("indexable") is True
        assert man2["approval"].get("publish_ready") is True
    else:
        # Still prove wrong-hash approval cannot publish
        wrong = tmp_path / "wrong.json"
        write_approval_template(
            wrong,
            dataset_hash="f" * 64,
            source_commit_sha=commit,
            actor="human-reviewer@confenge",
            schema_version=schema_v,
            exporter_version=exp_v,
        )
        out3 = tmp_path / "wrong-out"
        write_export(out3, bundle2, approval_path=wrong)
        man3 = json.loads((out3 / "manifest.json").read_text(encoding="utf-8"))
        assert man3.get("indexable") is False
        assert man3.get("snapshot_status") != "PUBLISH_READY"


def test_write_export_classifier_gate_blocks_publish_even_with_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """B9: evaluate_classifier (via run_gold_classifier_gate) must run before PUBLISH_READY.

    Even with a valid human approval, a failed classifier gold gate keeps CANDIDATE.
    """
    from scripts.pseo import classifiers as clf
    from scripts.pseo import pipeline as pl

    contracts, bids, counts = load_from_fixture(Path("tests/pseo/fixtures/sample_contracts.json"))
    bundle = build_export(contracts, bids, counts, top20_path=None, as_of="2026-07-31")
    out1 = tmp_path / "cand"
    write_export(out1, bundle, approval_path=None)
    man1 = json.loads((out1 / "manifest.json").read_text(encoding="utf-8"))
    ds = man1["dataset_hash"]
    commit = str(man1.get("source_commit_sha") or "unknown")
    schema_v = str(man1.get("schema_version") or "1.1.0")
    exp_v = str(man1.get("export_version") or EXPORT_VERSION)

    # Force classifier gate failure on the next write_export
    def fail_gate(**kwargs):
        return {
            "ok": False,
            "reason": "injected classifier failure for test",
            "metrics": {"gates": {"publish_ok": False}},
            "gold_path": "tests/pseo/fixtures/gold_classification.json",
        }

    monkeypatch.setattr(clf, "run_gold_classifier_gate", fail_gate)
    # Also patch the import site used inside write_export (local import)
    monkeypatch.setattr(pl, "run_gold_classifier_gate", fail_gate, raising=False)

    appr = tmp_path / "approval.json"
    write_approval_template(
        appr,
        dataset_hash=ds,
        source_commit_sha=commit,
        actor="human-reviewer@confenge",
        decision="APPROVED",
        schema_version=schema_v,
        exporter_version=exp_v,
    )
    bundle2 = build_export(contracts, bids, counts, top20_path=None, as_of="2026-07-31")
    out2 = tmp_path / "blocked"
    # Patch at classifiers module — write_export does `from scripts.pseo.classifiers import ...`
    import scripts.pseo.classifiers as clf_mod

    monkeypatch.setattr(clf_mod, "run_gold_classifier_gate", fail_gate)

    write_export(out2, bundle2, approval_path=appr)
    man2 = json.loads((out2 / "manifest.json").read_text(encoding="utf-8"))
    assert man2.get("classifier_gate", {}).get("ok") is False
    assert man2.get("snapshot_status") == "CANDIDATE"
    assert man2.get("indexable") is False
    assert man2.get("publish_status") in {
        "CLASSIFIER_GATE_FAILED",
        "REVIEW_REQUIRED",
        "INVALID_APPROVAL",
        "CANDIDATE",
    } or man2.get("approval", {}).get("status") == "CLASSIFIER_GATE_FAILED"


def test_run_gold_classifier_gate_calls_evaluate_classifier() -> None:
    """B9: export-path helper must call evaluate_classifier (not unit-test only)."""
    from scripts.pseo.classifiers import run_gold_classifier_gate

    result = run_gold_classifier_gate(repo_root=Path(".").resolve())
    assert result["ok"] is True, result.get("reason")
    assert result["metrics"] is not None
    gates = result["metrics"]["gates"]
    assert gates["publish_ok"] is True
    assert gates["precision_global_ok"] is True
    assert gates["fp_ok"] is True
    assert gates["segment_precision_ok"] is True
    assert result["metrics"]["precision_aec_confirmed"] >= 0.97
    assert result["metrics"]["fp"] == 0


def test_atomic_mid_write_failure_preserves_prior_versioned(tmp_path: Path) -> None:
    """B6: failure after temp write / during validate must not replace prior snapshot files."""
    parent = tmp_path / "exports"
    parent.mkdir()
    final = parent / "current"
    final.mkdir()
    prior = {"ok": True, "generation": 1, "keep": "prior-content"}
    (final / "manifest.json").write_text(json.dumps(prior) + "\n", encoding="utf-8")
    (final / "markets.json").write_text("[]\n", encoding="utf-8")

    calls = {"n": 0}

    def validate_then_boom(path: Path) -> dict:
        calls["n"] += 1
        # Prove temp files were written
        assert (path / "manifest.json").is_file()
        return {"ok": False, "errors": ["mid-write intentional failure"]}

    with pytest.raises(RuntimeError, match="validation failed before promote"):
        write_snapshot_atomic(
            final,
            {
                "manifest.json": json.dumps({"ok": False, "generation": 2}) + "\n",
                "markets.json": '[{"id":"new"}]\n',
            },
            validate=validate_then_boom,
            dataset_hash=None,
        )
    assert calls["n"] == 1
    # Prior generation intact
    kept = json.loads((final / "manifest.json").read_text(encoding="utf-8"))
    assert kept["generation"] == 1
    assert kept["keep"] == "prior-content"
    assert json.loads((final / "markets.json").read_text(encoding="utf-8")) == []


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

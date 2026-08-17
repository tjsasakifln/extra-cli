"""Handoff export, replay hashes and consumer contract import."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.historical_contract_authority.adapters import to_public_read
from scripts.historical_contract_authority.cases import case_handoff_ready, fixture_corpus
from scripts.historical_contract_authority.cli import run_fixture
from scripts.historical_contract_authority.engine import process_cases
from scripts.historical_contract_authority.handoff import file_sha256sums, write_handoff
from scripts.historical_contract_authority.schema import CONSUMER_ID, CONSUMER_SCHEMA, FORBIDDEN_PUBLIC_STATES
from scripts.public_read_consumers.contract_analysis import PAYLOAD_FIELDS
from scripts.public_read_consumers.contract_analysis import SCHEMA as PUBLIC_SCHEMA


def test_public_read_adapter_matches_consumer_contract() -> None:
    dossiers = process_cases([case_handoff_ready()], as_of="2026-08-17T12:00:00Z", snapshot_hash="snap-pr")
    payload = to_public_read(dossiers[0])
    assert payload["schema"] == PUBLIC_SCHEMA == CONSUMER_SCHEMA
    for field in PAYLOAD_FIELDS:
        assert field in payload
    assert payload["data_state"] in {"DATA_READY", "DATA_HOLD", "DATA_REJECT"}
    blob = json.dumps(payload)
    for token in FORBIDDEN_PUBLIC_STATES:
        assert token not in blob
    assert "PUBLISHABLE" not in blob
    assert '"INDEX"' not in blob


def test_cli_fixture_two_launches_same_hashes(tmp_path: Path) -> None:
    first = tmp_path / "launch-1"
    second = tmp_path / "launch-2"
    run_fixture(output=first, as_of="2026-08-17T12:00:00Z")
    run_fixture(output=second, as_of="2026-08-17T12:00:00Z")
    left = file_sha256sums(first)
    right = file_sha256sums(second)
    assert left
    assert left == right
    for name, digest in left.items():
        raw = (first / name).read_bytes()
        import hashlib

        assert hashlib.sha256(raw).hexdigest() == digest
    manifest = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["consumer"] == CONSUMER_ID
    assert manifest["no_index_authorization"] is True
    assert manifest["no_publication_authorization"] is True
    assert manifest["dossier_schema"] == "historical-contract-authority-dossier/1.0"
    ready = sum(1 for flag in manifest["handoff_ready"].values() if flag)
    assert 0 <= ready <= 5
    status = json.loads((first / "status.json").read_text(encoding="utf-8"))
    assert status["no_index_authorization"] is True
    blob = (first / "manifest.json").read_text(encoding="utf-8") + (first / "status.json").read_text(encoding="utf-8")
    assert "PUBLISHABLE" not in blob
    assert "INDEX" not in blob


def test_write_handoff_exports_only_ready(tmp_path: Path) -> None:
    dossiers = process_cases(fixture_corpus(), as_of="2026-08-17T12:00:00Z", snapshot_hash="snap-all")
    write_handoff(
        dossiers,
        output_dir=tmp_path,
        as_of="2026-08-17T12:00:00Z",
        snapshot_hash="snap-all",
        replay_command="python3 -m scripts.historical_contract_authority --mode fixture",
        catalog_mode="fixture",
    )
    exported = list((tmp_path / "dossiers").glob("*.json")) if (tmp_path / "dossiers").exists() else []
    assert len(exported) <= 5
    for path in exported:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["state"] == "HANDOFF_READY"
        assert payload["score"]["score"] >= 88
        assert not payload["score"]["below_floor"]
        public = json.loads((tmp_path / "public-read" / path.name).read_text(encoding="utf-8"))
        assert public["data_state"] == "DATA_READY"
        assert public["safety_flags"]["no_index_authorization"] is True

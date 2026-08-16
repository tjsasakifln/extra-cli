"""Drive the shipped CLI entry point. Same snapshot → same hashes."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.contract_publication.cli import main
from scripts.contract_publication.schema import (
    COMPONENT_NAMES,
    OFFICIAL_DATA_UNAVAILABLE,
    manifest_contains_forbidden_token,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "contract_publication" / "golden_corpus.json"


def test_rank_cli_is_deterministic(tmp_path: Path) -> None:
    out1 = tmp_path / "rank-1"
    out2 = tmp_path / "rank-2"
    assert main(["rank", "--snapshot", str(FIXTURE), "--out", str(out1)]) == 0
    assert main(["rank", "--snapshot", str(FIXTURE), "--out", str(out2)]) == 0
    first = json.loads((out1 / "candidates.json").read_text(encoding="utf-8"))
    second = json.loads((out2 / "candidates.json").read_text(encoding="utf-8"))
    assert first["content_hash"] == second["content_hash"]
    assert first["input_hash"] == second["input_hash"]
    assert set(first["weights"]) == set(COMPONENT_NAMES)
    assert len(first["weights"]) == 10
    states = {item["candidate_state"] for item in first["candidates"]}
    assert states <= {"REJECT", "HOLD_FOR_DATA", "EDITORIAL_REVIEW"}
    manifest = json.loads((out1 / "manifest.json").read_text(encoding="utf-8"))
    assert manifest_contains_forbidden_token(manifest) == []
    assert "official_live" not in json.dumps(manifest)
    for pack_path in (out1 / "packs").glob("*.json"):
        other = out2 / "packs" / pack_path.name
        assert json.loads(pack_path.read_text())["content_hash"] == json.loads(other.read_text())["content_hash"]


def test_rebuild_pack_cli_same_hash(tmp_path: Path) -> None:
    pack1 = tmp_path / "pack-1.json"
    pack2 = tmp_path / "pack-2.json"
    assert main(["rebuild-pack", "--snapshot", str(FIXTURE), "--candidate-id", "CAND-BDI-01", "--out", str(pack1)]) == 0
    assert main(["rebuild-pack", "--snapshot", str(FIXTURE), "--candidate-id", "CAND-BDI-01", "--out", str(pack2)]) == 0
    first = json.loads(pack1.read_text(encoding="utf-8"))
    second = json.loads(pack2.read_text(encoding="utf-8"))
    assert first["content_hash"] == second["content_hash"]


def test_live_path_is_official_unavailable(tmp_path: Path) -> None:
    out = tmp_path / "live"
    assert main(["live", "--out", str(out)]) == 2
    document = json.loads((out / "candidates.json").read_text(encoding="utf-8"))
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert document["status"] == OFFICIAL_DATA_UNAVAILABLE
    assert manifest["status"] == OFFICIAL_DATA_UNAVAILABLE
    assert document["schema"] == "contract-publication-candidate/1.0"
    assert manifest_contains_forbidden_token(manifest) == []
    blob = json.dumps(manifest).lower()
    assert "live" not in blob
    assert "real" not in blob
    assert "publicável" not in blob and "publicavel" not in blob
    assert "official_live" not in blob


def test_export_400_cli(tmp_path: Path) -> None:
    out = tmp_path / "export-400"
    assert main(["export-400", "--snapshot", str(FIXTURE), "--out", str(out)]) == 0
    bundle = json.loads((out / "bundle.json").read_text(encoding="utf-8"))
    assert bundle["schema"] == "public-read-contract-analysis/1.0"
    assert all(item["data_state"].startswith("DATA_") for item in bundle["analyses"])
    assert all("INDEX" not in item["data_state"] for item in bundle["analyses"])

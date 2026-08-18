"""Exporters feed the existing #414/#415 CLIs without editing those packages."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.contract_comparables.cli import main as comparables_main
from scripts.contract_comparables.constants import STATUS_COMPARABLE, STATUS_HOLD, STATUS_NOT
from scripts.contract_publication.cli import main as publication_main
from scripts.official_contract_semantics.cli import main as semantics_main
from scripts.official_contract_semantics.constants import FORBIDDEN_PUBLIC_STATES
from tests.official_contract_semantics.conftest import FIXTURE_DIR


def _pipeline(inputs: list[Path], out: Path) -> dict:
    code = semantics_main(["pipeline", "--input", *[str(path) for path in inputs], "--out", str(out)])
    assert code == 0
    return json.loads((out / "pipeline-summary.json").read_text(encoding="utf-8"))


def test_incomplete_export_keeps_comparables_engine_refusing(tmp_path: Path) -> None:
    summary = _pipeline([FIXTURE_DIR / "14_export_incomplete.json"], tmp_path / "incomplete")
    corpus = tmp_path / "incomplete" / "export-comparables.json"
    out = tmp_path / "incomplete" / "peer.json"
    assert (
        comparables_main(["build", "--corpus", str(corpus), "--case", "official_semantics_export", "--out", str(out)])
        == 0
    )
    document = json.loads(out.read_text(encoding="utf-8"))
    assert document["status"] in {STATUS_HOLD, STATUS_NOT}
    assert document["status"] != STATUS_COMPARABLE
    publication = json.loads((tmp_path / "incomplete" / "export-publication-evidence.json").read_text(encoding="utf-8"))
    assert publication["hold_for_data_count"] >= 1
    assert publication["authorizes_publication"] is False
    assert set(FORBIDDEN_PUBLIC_STATES).issubset(set(publication["does_not_emit"]))
    assert summary["accepted"] >= 1


def test_complete_export_lets_comparables_engine_evaluate(tmp_path: Path) -> None:
    _pipeline([FIXTURE_DIR / "15_export_comparable.json"], tmp_path / "complete")
    corpus = tmp_path / "complete" / "export-comparables.json"
    out = tmp_path / "complete" / "peer.json"
    payload = json.loads(corpus.read_text(encoding="utf-8"))
    focal = payload["cases"]["official_semantics_export"]["focal_id"]
    assert (
        comparables_main(
            [
                "build",
                "--corpus",
                str(corpus),
                "--case",
                "official_semantics_export",
                "--focal",
                str(focal),
                "--out",
                str(out),
            ]
        )
        == 0
    )
    document = json.loads(out.read_text(encoding="utf-8"))
    assert document["status"] in {STATUS_COMPARABLE, STATUS_HOLD, STATUS_NOT}
    assert "reason_codes" in document
    assert document["unit"] == "BRL_TOTAL"
    assert document["value_semantic"] == "valor_integral_nominal"
    assert document["regime"] == "empreitada_global"


def test_publication_rank_consumes_export_without_promoting(tmp_path: Path) -> None:
    _pipeline([FIXTURE_DIR / "15_export_comparable.json"], tmp_path / "pub")
    snapshot = tmp_path / "pub" / "export-publication-evidence.json"
    out = tmp_path / "pub" / "rank"
    assert publication_main(["rank", "--snapshot", str(snapshot), "--out", str(out)]) == 0
    ranked = json.loads((out / "candidates.json").read_text(encoding="utf-8"))
    assert ranked["coverage"]["candidate_count"] >= 1
    assert ranked.get("authorizes_publication") is not True
    for candidate in ranked["candidates"]:
        assert candidate["authorizes_publication"] is False
        assert candidate["authorizes_indexation"] is False
        assert candidate["candidate_state"] in {"REJECT", "HOLD_FOR_DATA", "EDITORIAL_REVIEW"}
        assert candidate["candidate_state"] not in FORBIDDEN_PUBLIC_STATES


def test_pipeline_replay_same_hashes(tmp_path: Path) -> None:
    first = _pipeline([FIXTURE_DIR / "15_export_comparable.json"], tmp_path / "run-1")
    second = _pipeline([FIXTURE_DIR / "15_export_comparable.json"], tmp_path / "run-2")
    assert first["artifact_sha256"] == second["artifact_sha256"]
    obs1 = (tmp_path / "run-1" / "observations.jsonl").read_text(encoding="utf-8")
    obs2 = (tmp_path / "run-2" / "observations.jsonl").read_text(encoding="utf-8")
    assert obs1 == obs2

"""No brand, SEO, CTA or accusation leaks into shipped outputs."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.contract_publication.cli import main

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "contract_publication" / "golden_corpus.json"

BRAND = ("CONFENGE", "confenge")
FORBIDDEN_FIELDS = (
    "seo_title",
    "cta",
    "noindex",
    "has_right",
    "should_adjust",
    "irregular",
    "fraude",
)


def _keys(node: object) -> set[str]:
    found: set[str] = set()
    if isinstance(node, dict):
        found.update(str(key) for key in node)
        for value in node.values():
            found.update(_keys(value))
    elif isinstance(node, list):
        for item in node:
            found.update(_keys(item))
    return found


def test_rank_outputs_have_no_forbidden_fields(tmp_path: Path) -> None:
    out = tmp_path / "rank"
    assert main(["rank", "--snapshot", str(FIXTURE), "--out", str(out)]) == 0
    for path in out.rglob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        blob = json.dumps(payload)
        for token in BRAND:
            assert token not in blob
        keys = _keys(payload)
        for field in FORBIDDEN_FIELDS:
            assert field not in keys
        if "candidates" in payload:
            for item in payload["candidates"]:
                assert item["candidate_state"] not in {"INDEX", "PUBLISHABLE_INDEX", "PUBLISHABLE_NOINDEX"}
                assert item["authorizes_publication"] is False
                assert item["authorizes_indexation"] is False
        if "data_state" in payload:
            assert payload["data_state"] in {"DATA_READY", "DATA_HOLD", "DATA_REJECT"}
    candidates = json.loads((out / "candidates.json").read_text(encoding="utf-8"))
    report = json.loads((out / "status-report.json").read_text(encoding="utf-8"))
    assert report["recommendation"] in {"EXPAND", "ADJUST", "STOP", "NEEDS_DATA"}
    assert report["producer_sha"]
    assert report["policy"]
    assert report["snapshot_hash"]
    assert set(candidates["weights"]) >= set(
        [
            "commercial_relevance",
            "demand_fit",
            "insight_or_anomaly_strength",
            "documentary_richness",
            "comparability",
            "freshness",
            "defensibility",
            "citation_potential",
            "editorial_maintenance_cost",
            "reputational_sensitivity",
        ]
    )

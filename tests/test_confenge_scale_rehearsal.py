from __future__ import annotations

import json
from pathlib import Path

from scripts.ops.confenge_scale_rehearsal import run_rehearsal


def test_synthetic_scale_recipe_exercises_every_terminal_idempotently(tmp_path: Path) -> None:
    recipe = {
        "schema_version": "confenge.synthetic-scale-rehearsal.v1",
        "generator_version": "confenge-scale-corpus.v1",
        "seed": 468469155151,
        "account_count": 100,
        "refresh_membership_change_percent": 10,
        "max_leads_per_chunk": 17,
        "scenarios": [
            "supplier_confirmed",
            "buyer_conflict",
            "direct_person",
            "role_mailbox",
            "generic_mailbox",
            "company_freemail",
            "shared_mailbox_conflict",
            "no_public_email",
            "stale_evidence",
            "suppression",
        ],
    }
    recipe_path = tmp_path / "recipe.json"
    recipe_path.write_text(json.dumps(recipe), encoding="utf-8")

    report = run_rehearsal(recipe_path, tmp_path / "run", repeat=2)

    assert report["status"] == "PASS", report["failed_assertions"]
    assert report["provider_send_invocations"] == 0
    assert report["producer"]["scenario_counts"] == {scenario: 10 for scenario in recipe["scenarios"]}
    assert report["producer"]["discovery_terminal_counts"] == {
        "NOT_FOUND": 10,
        "RESOLVED": 80,
        "SUPPRESSED": 10,
    }
    assert report["producer"]["membership_removed"] == 10
    assert report["producer"]["membership_added"] == 10
    assert report["producer"]["run1"]["preferred_route_count"] > 0

    manifest = json.loads((tmp_path / "run" / "feed-v1" / "manifest.json").read_text(encoding="utf-8"))
    chunk = json.loads(
        (tmp_path / "run" / "feed-v1" / manifest["chunks"][0]["file"]).read_text(encoding="utf-8")
    )
    for lead in chunk["leads"]:
        assert not any(character.isdigit() for character in lead["company"]["nome_fantasia"])
        assert {evidence["type"] for evidence in lead["evidence"]} == {"CONTRACT"}

    refresh_manifest = json.loads((tmp_path / "run" / "feed-v2" / "manifest.json").read_text(encoding="utf-8"))
    assert {row["to_state"] for row in refresh_manifest["deactivations"]} == {"SUPPRESSED"}

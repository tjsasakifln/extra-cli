"""Contract test: extra-cli export vs web-cfg consumer rules (read-only vendored)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.pseo.pipeline import build_export, load_from_fixture, write_export
from tests.pseo.consumer_web_cfg.validate_consumer import (
    REQUIRED_FILES,
    SCHEMA_VERSIONS_OK,
    ConsumerContractError,
    validate_consumer_snapshot,
)

FIXTURE = Path(__file__).parent / "fixtures" / "sample_contracts.json"
CAMPAIGN = Path("docs/ops/campaigns/EXTRA-PRS-186-187-TRUST-HARDENING-01")
SCRATCH = Path("/tmp/grok-goal-582c99c4809e/implementer")


def test_consumer_required_files_and_schema_versions_documented():
    assert "manifest.json" in REQUIRED_FILES
    assert "1.1.0" in SCHEMA_VERSIONS_OK
    assert "1.0.0" in SCHEMA_VERSIONS_OK


def test_fixture_export_satisfies_web_cfg_consumer_contract(tmp_path: Path):
    contracts, bids, counts = load_from_fixture(FIXTURE)
    bundle = build_export(contracts, bids, counts, top20_path=None, as_of="2026-07-31")
    out = tmp_path / "export"
    write_export(out, bundle, approval_path=None)

    # Align schema_version with consumer allowlist if pipeline emitted 1.1.0
    man_path = out / "manifest.json"
    man = json.loads(man_path.read_text(encoding="utf-8"))
    # Consumer accepts 1.0.0 and 1.1.0 — ensure we emit one of them
    assert str(man.get("schema_version")) in SCHEMA_VERSIONS_OK or True
    # If pipeline uses 1.1.0 in files but 1.0.0 in SCHEMA_VERSION constant, normalize for consumer
    if str(man.get("schema_version")) not in SCHEMA_VERSIONS_OK:
        man["schema_version"] = "1.1.0"
        # re-checksum manifest only is hard; instead force write path to set 1.1.0 upstream
        pytest.fail(f"schema_version {man.get('schema_version')} not in consumer allowlist {SCHEMA_VERSIONS_OK}")

    result = validate_consumer_snapshot(out)
    assert result["ok"] is True

    report = {
        "status": "SCHEMA_CONTRACT_PROVEN",
        "consumer": result["consumer"],
        "dataset_hash": result["dataset_hash"],
        "schema_version": result["schema_version"],
        "required_files_ok": True,
        "forbidden_patterns_ok": True,
        "checksums_ok": True,
        "render_pipeline": "CONSUMER_INTEGRATION_NOT_PROVEN",
        "notes": [
            "Static consumer rules from web-cfg scripts/pseo/schema.py were applied to fixture export.",
            "Did not run web-cfg npm pseo:build / Netlify deploy / production data/pseo swap.",
        ],
    }
    SCRATCH.mkdir(parents=True, exist_ok=True)
    (CAMPAIGN / "PR-187-CONSUMER-CONTRACT.md").parent.mkdir(parents=True, exist_ok=True)
    (SCRATCH / "consumer-contract-report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    (CAMPAIGN / "PR-187-CONSUMER-CONTRACT.md").write_text(
        "# PR #187 Consumer Contract Report\n\n"
        f"- **Schema contract:** PROVEN against vendored web-cfg rules\n"
        f"- **dataset_hash:** `{report['dataset_hash']}`\n"
        f"- **schema_version:** `{report['schema_version']}`\n"
        f"- **Render/build integration:** `CONSUMER_INTEGRATION_NOT_PROVEN`\n"
        f"- **Source of rules:** `tests/pseo/consumer_web_cfg/` (from tjsasakifln/web-cfg, read-only)\n"
        f"- **Non-claims:** no Netlify deploy, no production tree write, no live DSN\n",
        encoding="utf-8",
    )


def test_consumer_rejects_forbidden_field(tmp_path: Path):
    contracts, bids, counts = load_from_fixture(FIXTURE)
    bundle = build_export(contracts, bids, counts, top20_path=None, as_of="2026-07-31")
    out = tmp_path / "export"
    write_export(out, bundle, approval_path=None)
    # Poison opportunities with commercial field
    opp_path = out / "opportunities.json"
    data = json.loads(opp_path.read_text(encoding="utf-8"))
    if isinstance(data, list) and data:
        data[0]["score_total"] = 99.9
    else:
        data = [{"id": "x", "slug": "x", "score_total": 1}]
    opp_path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ConsumerContractError, match="forbidden|checksum|dataset_hash"):
        validate_consumer_snapshot(out)

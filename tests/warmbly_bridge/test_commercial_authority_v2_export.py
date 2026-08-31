from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from scripts.confenge_activation.commercial_authority_v2 import RootQualification, evidence_hash
from scripts.confenge_activation.publish import (
    atomic_publish_directory,
    producer_identity,
    publication_semantic_hash,
)
from scripts.warmbly_bridge.export import ExportConfig, export_outreach

NOW = datetime(2026, 8, 31, 12, tzinfo=UTC)


def _corpus(universe: Path, out: Path) -> Path:
    rows = [json.loads(line) for line in universe.read_text(encoding="utf-8").splitlines() if line.strip()]
    with out.open("w", encoding="utf-8") as handle:
        for index, row in enumerate(rows):
            root = row["cnpj14"][:8]
            q = RootQualification(
                cnpj_root8=root,
                target_fit_class="TARGET_CONFIRMED",
                party_role="SUPPLIER",
                qualifying_contract_id=f"contract-{index:02d}",
                qualifying_contract_date="2026-01-10",
                qualifying_date_field="data_assinatura",
                qualifying_contract_count=1,
                qualified_until="2029-01-10",
                qualification_evidence_reference=f"extra-cli:v_contracts_canonical_v2:contract-{index:02d}",
                provenance="extra-cli:v_contracts_canonical_v2",
            )
            signed = RootQualification(**{**q.__dict__, "qualification_evidence_hash": evidence_hash(q)})
            handle.write(json.dumps(signed.as_dict(), sort_keys=True) + "\n")
    return out


def test_stale_or_missing_pncp_does_not_block_valid_v2_publication(
    tmp_path: Path,
    universe_path: Path,
    intel_path: Path,
    contacts_path: Path,
) -> None:
    corpus = _corpus(universe_path, tmp_path / "qualification.jsonl")
    built = tmp_path / "build"
    result = export_outreach(
        ExportConfig(
            universe=universe_path,
            account_intelligence=intel_path,
            contacts=contacts_path,
            out_dir=built,
            generated_at="2026-08-31T12:00:00Z",
            datalake_watermark="2026-08-31T12:00:00Z",
            expected_universe_count=5,
            commercial_qualification_corpus=corpus,
            require_commercial_authority_v2=True,
            authoritative_source_freshness={
                "contract_version": "PNCP_CONTRACT_FRESHNESS/1.0",
                "status": "STALE",
                "reason_codes": ["UPSTREAM_UNAVAILABLE"],
            },
        )
    )
    manifest = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
    assert manifest["commercial_authority_v2"]["state"] == "QUALIFIED"
    assert manifest["source_operational_health"]["status"] == "STALE"
    assert manifest["commercial_authority_v2"]["qualified_root_count"] == 5
    for chunk in manifest["chunks"]:
        payload = json.loads((built / chunk["file"]).read_text(encoding="utf-8"))
        assert all(lead["commercial_qualification"]["party_role"] == "SUPPLIER" for lead in payload["leads"])

    projection = manifest["authoritative_contact_projection"]
    membership = manifest["authoritative_target_membership"]
    ready = int(projection["output_preferred_account_count"])
    projection.update(
        {
            "schema_id": "confenge.contact_discovery.projection_report.v1",
            "report_sha256": "a" * 64,
            "cohort_id": "v2-test",
            "generated_at": "2026-08-31T12:00:00Z",
            "population_hash": "b" * 64,
            "population_as_of": "2026-08-31T12:00:00Z",
            "population_as_of_source": "target_fit_full_reconcile",
            "population_verified_at": "2026-08-31T12:00:00Z",
            "population_coverage_ratio": 1.0,
            "population_publication_ready": True,
            "projection_hash": "c" * 64,
            "controlled_email_policy_version": "controlled-email-policy.v3",
            "discovery_policy_version": "dui.policy.v1",
            "input_evidence_version": "commercial-authority-v2",
            "code_sha": "test-v2",
            "coverage_complete": True,
            "terminal_coverage_complete": True,
            "terminal_equation": {"holds": True},
            "population_count": 5,
            "membership_count": 5,
            "membership_hash": membership["membership_hash"],
            "membership_schema_version": membership["schema_version"],
            "membership_identity_key": membership["identity_key"],
            "membership_hash_algorithm": membership["hash_algorithm"],
            "enrichment_states": {"EMAIL_ROUTE_READY": ready, "NO_PUBLIC_EMAIL_FOUND": 5 - ready},
            "recipient_states": {
                "RECIPIENT_ATTRIBUTED": ready,
                "READY": ready,
                "NO_PUBLIC_EMAIL_FOUND": 5 - ready,
                "BLOCKED_WITH_REASON": 0,
            },
        }
    )
    identity = producer_identity(manifest)
    semantic = publication_semantic_hash(manifest)
    manifest["producer_identity"] = identity
    manifest["publication_semantic_hash"] = semantic
    manifest["commercial_authority_v2"].update(
        {"producer_identity": identity, "basis_publication_semantic_hash": semantic}
    )
    Path(result["manifest"]).write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")

    publication = atomic_publish_directory(
        built,
        tmp_path / "public",
        state_path=tmp_path / "state.json",
        alert_ledger=tmp_path / "alerts.jsonl",
        now=NOW,
    )
    assert publication["ok"] is True
    served = json.loads(Path(publication["current"]).joinpath("manifest.json").read_text(encoding="utf-8"))
    assert served["commercial_authority_v2"]["state"] == "QUALIFIED"
    assert "commercial_authority" not in served

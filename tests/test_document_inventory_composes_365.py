"""Cross-module proof: #366 consumes real #365 types."""

from __future__ import annotations

from scripts.process_documents.inventory_pipeline import InventoryRun, enqueue_from_inventory
from scripts.process_documents.pncp_document_versions import (
    CandidateInventory,
    apply_fanout,
    version_document,
)


def test_real_candidate_inventory_feeds_pipeline_states() -> None:
    inventory = CandidateInventory(
        candidate_id="live-1",
        official_page="https://pncp.gov.br/app/editais/9",
        official_reconfirmed=True,
        status="open",
    )
    apply_fanout(
        inventory,
        official_page="https://pncp.gov.br/app/editais/9",
        official_status="Revogado",
        documents=[
            version_document(
                kind="edital",
                url="https://pncp.gov.br/docs/edital",
                body=b"%PDF-1.4 e",
                mime="application/pdf",
            )
        ],
        items_fetched=True,
        history_fetched=True,
        results_fetched=True,
    )
    run = InventoryRun(process_id="cross")
    enqueue_from_inventory(run, inventory)
    job = run.jobs["live-1:edital:v1"]
    assert inventory.status == "revoked"
    assert job.state == "SUPERSEDED"
    assert job.reason_code == "official_status_revoked"
    assert inventory.shortlist_eligible is False

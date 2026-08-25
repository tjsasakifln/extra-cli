from __future__ import annotations

from scripts.decision_unit_intelligence.batch_projection import reconcile_prior_contact_rows

ACCOUNT = "11222333000181"
MAILBOX = "acmeengenharia@gmail.com"


def _prior_registry_contact() -> dict:
    return {
        "email": MAILBOX,
        "source": "company_registry",
        "source_type": "company_registry",
        "source_reference": "registry-evidence-1",
        "evidence_ids": ["registry-evidence-1"],
        "observed_at": "2026-08-24T12:00:00Z",
        "channel_epistemic_class": "OBSERVED",
        "route_freshness": "FRESH",
        "route_suppression": "NONE",
        "ownership_status": "COMPANY_OWNED",
        "company_associated": True,
        "mailbox_company_evidence": "OBSERVED",
        "official_match_status": "MATCHED",
        "official_authority": "RECEITA_FEDERAL",
        "official_release_id": "rfb-2026-08",
        "registry_cnpj14": ACCOUNT,
        "source_provenance": {"release_id": "rfb-2026-08"},
    }


def _current_blocked_contact(*, suppression: str = "NONE") -> dict:
    return {
        "email": MAILBOX,
        "source": "company_registry",
        "source_type": "company_registry",
        "source_reference": "replayed-seed-evidence",
        "observed_at": "2026-08-25T01:00:00Z",
        "channel_epistemic_class": "OBSERVED",
        "route_freshness": "FRESH",
        "route_suppression": suppression,
        "ownership_status": "COMPANY_OWNED",
        "company_associated": True,
        "mailbox_company_evidence": "OBSERVED",
        # These are stale derived values from a serializer that lost the exact
        # registry association. Reconciliation must derive them again.
        "route_class": "PROBABILISTIC_OR_RISKY",
        "controlled_email_eligible": False,
        "preferred_initial": False,
    }


def _row(contact: dict, *, state: str, reason: str) -> dict:
    return {
        "cnpj14": ACCOUNT,
        "canonical_account_id": ACCOUNT,
        "contacts": [contact],
        "preferred_email_route": None,
        "enrichment_state": state,
        "enrichment_reason": reason,
    }


def test_prior_exact_registry_proof_prevents_incremental_evidence_regression() -> None:
    prior = [_row(_prior_registry_contact(), state="EMAIL_ROUTE_READY", reason="selected")]
    current = [
        _row(
            _current_blocked_contact(),
            state="BLOCKED_WITH_REASON",
            reason="WATERFALL_PROVIDER_FAILURE",
        )
    ]

    rows, metrics = reconcile_prior_contact_rows(current, prior)

    assert metrics["preferred_before_reconciliation"] == 0
    assert metrics["preferred_after_reconciliation"] == 1
    assert metrics["preferred_recovered_from_prior"] == 1
    row = rows[0]
    assert row["latest_enrichment_state"] == "BLOCKED_WITH_REASON"
    assert row["enrichment_state"] == "EMAIL_ROUTE_READY"
    assert row["enrichment_reason"] == "DURABLE_EVIDENCE_ROUTE_SELECTED"
    preferred = row["preferred_email_route"]
    assert preferred["route_class"] == "PUBLIC_COMPANY_FREEMAIL"
    assert preferred["controlled_email_eligible"] is True
    assert preferred["company_associated"] is True
    assert preferred["official_authority"] == "RECEITA_FEDERAL"
    assert preferred["source_reference"] == "registry-evidence-1"


def test_current_hard_bounce_survives_prior_ready_route_and_blocks_selection() -> None:
    prior = [_row(_prior_registry_contact(), state="EMAIL_ROUTE_READY", reason="selected")]
    current = [
        _row(
            _current_blocked_contact(suppression="HARD_BOUNCE"),
            state="BLOCKED_WITH_REASON",
            reason="HARD_BOUNCE",
        )
    ]

    rows, metrics = reconcile_prior_contact_rows(current, prior)

    assert metrics["preferred_after_reconciliation"] == 0
    assert rows[0]["enrichment_state"] == "BLOCKED_WITH_REASON"
    assert rows[0]["enrichment_reason"] == "HARD_BOUNCE"
    assert rows[0].get("preferred_email_route") is None
    assert rows[0]["contacts"][0]["route_suppression"] == "HARD_BOUNCE"

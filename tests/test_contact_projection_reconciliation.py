from __future__ import annotations

from scripts.decision_unit_intelligence.batch_projection import reconcile_prior_contact_rows
from tests.recipient_attestation_fixtures import exact_page_attestation

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
        "source_provenance": {
            "release_id": "rfb-2026-08",
            "source_label": "rfb_public_cadastral",
        },
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
        # Reproduce the live serializer regression: the current attempt kept
        # the mailbox but lost the prior immutable registry tuple and therefore
        # emitted no association verdict of its own.
        "ownership_status": "UNKNOWN",
        "company_associated": False,
        "mailbox_company_evidence": "UNKNOWN",
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


def test_registry_match_for_another_cnpj_cannot_restore_company_association() -> None:
    prior_contact = _prior_registry_contact()
    prior_contact["registry_cnpj14"] = "99888777000166"
    prior = [_row(prior_contact, state="EMAIL_ROUTE_READY", reason="selected")]
    current = [
        _row(
            _current_blocked_contact(),
            state="BLOCKED_WITH_REASON",
            reason="WATERFALL_PROVIDER_FAILURE",
        )
    ]

    rows, metrics = reconcile_prior_contact_rows(current, prior)

    assert metrics["preferred_after_reconciliation"] == 0
    assert rows[0]["enrichment_state"] == "BLOCKED_WITH_REASON"
    assert rows[0].get("preferred_email_route") is None
    assert rows[0]["contacts"][0]["company_associated"] is False
    assert rows[0]["contacts"][0]["controlled_email_eligible"] is False


def test_unobserved_historical_route_remains_stored_but_cannot_be_preferred() -> None:
    unobserved = {
        "email": "info@ncsecu.org",
        "source": "contact_page",
        "source_type": "contact_page",
        "source_reference": "https://locations.ncsecu.org/search",
        "source_url": "https://locations.ncsecu.org/search",
        "channel_epistemic_class": "OBSERVED",
        "route_freshness": "UNKNOWN",
        "route_suppression": "NONE",
        "ownership_status": "COMPANY_OWNED",
        "company_associated": True,
        "mailbox_company_evidence": "OBSERVED",
    }
    current = [_row(unobserved, state="EMAIL_ROUTE_READY", reason="selected")]

    rows, metrics = reconcile_prior_contact_rows(current, [])

    assert metrics["routes_rejected_missing_observed_at"] == 1
    assert metrics["preferred_after_reconciliation"] == 0
    assert rows[0]["enrichment_state"] == "BLOCKED_WITH_REASON"
    assert rows[0]["enrichment_reason"] == "CONTACT_ROUTE_MISSING_OBSERVED_AT"
    assert rows[0].get("preferred_email_route") is None
    assert rows[0]["contacts"][0]["controlled_email_eligible"] is False
    assert rows[0]["contacts"][0]["risk_class"] == "RISKY"
    assert rows[0]["contacts"][0]["publication_block_reason"] == "MISSING_OBSERVED_AT"


def test_page_attestation_is_not_laundered_through_new_unbound_observation() -> None:
    old_url = "https://valid-a.example/contato"
    observed_at = "2024-01-01T00:00:00Z"
    attestation = exact_page_attestation(
        account=ACCOUNT,
        mailbox=MAILBOX,
        source_url=old_url,
        observed_at=observed_at,
        page_content=f"CNPJ {ACCOUNT} | Contato: {MAILBOX}",
    )
    prior_contact = {
        "email": MAILBOX,
        "source": "contact_page",
        "source_type": "contact_page",
        "source_reference": old_url,
        "source_url": old_url,
        "official_domain": "valid-a.example",
        "observed_at": observed_at,
        "channel_epistemic_class": "OBSERVED",
        "route_freshness": "STALE",
        "route_suppression": "NONE",
        "ownership_status": "COMPANY_OWNED",
        "company_associated": True,
        "mailbox_company_evidence": "OBSERVED",
        **attestation,
    }
    current_contact = {
        "email": MAILBOX,
        "source": "contact_page",
        "source_type": "contact_page",
        "source_reference": "https://wrong-b.example/contato",
        "source_url": "https://wrong-b.example/contato",
        "observed_at": "2026-08-26T12:00:00Z",
        "channel_epistemic_class": "OBSERVED",
        "route_freshness": "FRESH",
        "route_suppression": "NONE",
        "ownership_status": "UNKNOWN",
        "company_associated": False,
        "mailbox_company_evidence": "UNKNOWN",
    }

    rows, metrics = reconcile_prior_contact_rows(
        [_row(current_contact, state="BLOCKED_WITH_REASON", reason="NO_IDENTITY_PROOF")],
        [_row(prior_contact, state="EMAIL_ROUTE_READY", reason="selected")],
    )

    assert metrics["preferred_after_reconciliation"] == 0
    merged = rows[0]["contacts"][0]
    assert merged["source_url"] == old_url
    assert merged["observed_at"] == "2024-01-01T00:00:00Z"
    assert merged["route_freshness"] == "STALE"
    assert rows[0]["enrichment_state"] == "BLOCKED_WITH_REASON"

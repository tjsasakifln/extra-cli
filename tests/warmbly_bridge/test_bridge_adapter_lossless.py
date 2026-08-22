"""The bridge adapters must not turn dropped fields into negative assertions.

Two lossy projections in scripts/confenge_outreach_pipeline/adapt.py plus a
bool() coercion in mapping.py made a cohort ship `target_fit_fresh=false` and
`email_explicitly_published=false` for mailboxes read off the companies' own
contact pages. Downstream those read as evidence, not as absence.
"""

from scripts.confenge_contact_resolution.mailbox_purpose import (
    CONTROLLED_BLOCKED_PURPOSES,
    classify_mailbox_purpose,
)
from scripts.confenge_outreach_pipeline.adapt import (
    contact_resolution_to_bridge_row,
    universe_row_for_bridge,
)
from scripts.warmbly_bridge.mapping import _as_tribool


def test_universe_row_forwards_authoritative_target_fit_metadata():
    row = {
        "cnpj14": "10000000000191",
        "razao_social": "CONSTRUTORA X LTDA",
        "target_fit_class": "TARGET_CONFIRMED",
        "target_fit_version": "v3",
        "target_fit_computed_at": "2026-08-22T03:00:00Z",
        "target_fit_source_watermark": "2026-08-22T02:00:00Z",
        "operational_status": "ACTIVE",
    }
    out = universe_row_for_bridge(row, rank=1)
    # ADR-035 requires these on every emitted decision; without them the
    # sanctioned export path raises and cohorts get hand-rolled instead.
    assert out["target_fit_computed_at"] == "2026-08-22T03:00:00Z"
    assert out["target_fit_source_watermark"] == "2026-08-22T02:00:00Z"
    assert out["operational_status"] == "ACTIVE"


def test_universe_row_reads_target_fit_metadata_from_construction_evidence():
    row = {
        "cnpj14": "10000000000191",
        "construction_evidence": {
            "target_fit_class": "TARGET_CONFIRMED",
            "target_fit_computed_at": "2026-08-22T03:00:00Z",
            "target_fit_source_watermark": "2026-08-22T02:00:00Z",
        },
    }
    out = universe_row_for_bridge(row, rank=1)
    assert out["target_fit_computed_at"] == "2026-08-22T03:00:00Z"
    assert out["target_fit_source_watermark"] == "2026-08-22T02:00:00Z"


def test_contact_row_carries_identity_evidence():
    payload = {
        "cnpj14": "10000000000191",
        "candidates": [
            {
                "candidate_id": "c-1",
                "email": "contato@construtorax.com.br",
                "verification_status": "OFFICIAL_SOURCE",
                "email_explicitly_published": True,
                "name_explicitly_published": False,
                "role_explicitly_published": False,
                "human_identity_evidence_valid": False,
                "identity_evidence_urls": ["https://construtorax.com.br/contato"],
                "evidence_sha256": "a" * 64,
                "ownership_status": "COMPANY_OWNED",
                "source": {
                    "source_url": "https://construtorax.com.br/contato",
                    "source_type": "contact_page",
                },
            }
        ],
    }
    row = contact_resolution_to_bridge_row(payload)
    contact = row["contacts"][0]
    assert contact["email_explicitly_published"] is True
    assert contact["identity_evidence_urls"] == ["https://construtorax.com.br/contato"]
    assert contact["evidence_sha256"] == "a" * 64


def test_absent_identity_flag_is_unknown_not_false():
    # The whole defect: bool(None) is False, which asserts "we checked and it
    # was not published" about a field the producer simply dropped.
    assert _as_tribool(None) is None
    assert _as_tribool(True) is True
    assert _as_tribool(False) is False
    assert _as_tribool("true") is True
    assert _as_tribool("") is None


def test_controlled_mode_allows_the_departments_autorun_blocks():
    # send_blocked is the autorun rule and blocks every functional mailbox.
    # A controlled institutional cohort must be able to reach these.
    for email in (
        "comercial@construtorax.com.br",
        "licitacoes@construtorax.com.br",
        "contratos@construtorax.com.br",
        "contato@construtorax.com.br",
    ):
        mp = classify_mailbox_purpose(email)
        assert mp.send_blocked is True, email
        assert mp.purpose not in CONTROLLED_BLOCKED_PURPOSES, email


def test_controlled_mode_still_blocks_non_commercial_mailboxes():
    for email in ("vagas@construtorax.com.br", "noreply@construtorax.com.br"):
        mp = classify_mailbox_purpose(email)
        assert mp.purpose in CONTROLLED_BLOCKED_PURPOSES, email

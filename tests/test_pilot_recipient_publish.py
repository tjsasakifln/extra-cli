"""#370 publish only already-observed public human recipients."""

from __future__ import annotations

from scripts.confenge_contact_resolution.publish_pilot_recipients import (
    VALIDATED,
    publish_pilot_recipients,
)

# Already-observed public evidence (same chain used by the send-ready fixture).
# Nothing here is invented at publish time.
OBSERVED_HUMAN = {
    "account_id": "cnpj:11222333000181",
    "name": "Maria de Souza",
    "role": "Diretora Comercial",
    "email": "maria.souza@empresa-target.com.br",
    "source_url": "https://empresa-target.com.br/equipe",
    "observed_at": "2026-08-13T12:00:00Z",
    "email_explicitly_published": True,
    "name_explicitly_published": True,
    "role_explicitly_published": True,
    "ownership": "COMPANY_OWNED",
    "suitability": "CONFENGE_REAJUSTE",
}

GENERIC_MAILBOX = {
    "account_id": "cnpj:11222333000181",
    "name": "",
    "role": "",
    "email": "contato@empresa-target.com.br",
    "source_url": "https://empresa-target.com.br/contato",
    "observed_at": "2026-08-13T12:00:00Z",
    "email_explicitly_published": True,
}

INVENTED = {
    "account_id": "cnpj:000",
    "name": "placeholder",
    "role": "inferred",
    "email": "n/a",
    "invented": True,
}


def test_publish_validates_observed_human_and_rejects_generic() -> None:
    result = publish_pilot_recipients([OBSERVED_HUMAN, GENERIC_MAILBOX])
    assert result["ok"] is True
    assert result["validated_count"] == 1
    assert result["validated"][0]["status"] == VALIDATED
    assert result["validated"][0]["name"] == "Maria de Souza"
    assert result["validated"][0]["email"] == "maria.souza@empresa-target.com.br"
    assert result["validated"][0]["source_url"].startswith("https://")
    assert result["validated"][0]["observed_at"]
    assert any(
        "functional_mailbox_not_human_recipient" in item["reasons"]
        for item in result["rejected"]
    )


def test_publish_fails_closed_without_inventing_pii() -> None:
    result = publish_pilot_recipients([GENERIC_MAILBOX, INVENTED])
    assert result["ok"] is False
    assert result["warmbly_ready"] is False
    assert result["validated"] == []
    assert "insufficient_validated_humans" in result["reason_codes"]
    assert "generic_mailbox_not_promoted" in result["reason_codes"]
    assert "refused_to_invent_pii" in result["reason_codes"]

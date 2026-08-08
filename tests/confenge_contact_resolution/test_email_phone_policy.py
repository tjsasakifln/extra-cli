"""Unit tests for email layers, BR E.164, WhatsApp consent defaults."""

from __future__ import annotations

from scripts.confenge_contact_resolution.email_policy import (
    assess_email,
    is_functional_mailbox,
    looks_like_personal_pattern,
    syntactic_ok,
)
from scripts.confenge_contact_resolution.models import VerificationStatus, WhatsAppConsent
from scripts.confenge_contact_resolution.phone_policy import (
    assess_phone,
    classify_phone_type,
    default_whatsapp_block,
    normalize_br_e164,
)


def test_syntactic_and_functional_email() -> None:
    a = assess_email("contato@empresa.com.br")
    assert a.verification_status == VerificationStatus.OBSERVED.value
    assert a.is_functional is True
    assert a.enrollable is True
    assert a.email_display == "contato@empresa.com.br"
    assert is_functional_mailbox("comercial@foo.com.br")


def test_pattern_guessed_never_enrollable() -> None:
    a = assess_email("joao.silva@empresa.com.br", pattern_guessed=True)
    assert a.verification_status == VerificationStatus.CANDIDATE_UNVERIFIED.value
    assert a.enrollable is False
    assert a.layers.pattern_guessed is True


def test_observed_nominal_email_preserved_exact() -> None:
    raw = "Joao.Silva@Construtora-XYZ.com.br"
    a = assess_email(raw, pattern_guessed=False)
    assert a.verification_status == VerificationStatus.OBSERVED.value
    assert a.email_display == raw
    assert a.email == raw.lower()
    assert a.enrollable is True


def test_invalid_syntax() -> None:
    a = assess_email("not-an-email")
    assert a.verification_status == VerificationStatus.SYNTAX_INVALID.value
    assert a.enrollable is False
    assert not syntactic_ok("@@@")


def test_mx_layer_injected() -> None:
    a = assess_email(
        "contato@empresa.com.br",
        check_mx_flag=True,
        mx_resolver=lambda d: d == "empresa.com.br",
    )
    assert a.layers.mx_checked is True
    assert a.layers.mx_ok is True


def test_e164_mobile_and_landline() -> None:
    mobile = normalize_br_e164("(48) 99999-1234")
    assert mobile == "+5548999991234"
    assert classify_phone_type(mobile) == "mobile"

    land = normalize_br_e164("48 3333-4444")
    assert land == "+554833334444"
    assert classify_phone_type(land) == "landline"

    with_cc = normalize_br_e164("+55 11 98888-7777")
    assert with_cc == "+5511988887777"

    assert normalize_br_e164("123") is None
    assert normalize_br_e164("48988887777")  # 11 digits
    invalid = assess_phone("abc")
    assert invalid.valid is False
    assert invalid.phone_e164 is None


def test_landline_assessment() -> None:
    a = assess_phone("48 3222-1000")
    assert a.valid is True
    assert a.phone_type == "landline"
    assert a.phone_e164 == "+554832221000"


def test_whatsapp_consent_defaults() -> None:
    wa = default_whatsapp_block("+5548999991234")
    assert wa.consent_status in {
        WhatsAppConsent.UNKNOWN.value,
        WhatsAppConsent.NO_OPT_IN.value,
    }
    assert wa.consent_status != WhatsAppConsent.OPTED_IN.value

    # OPTED_IN without provenance fails closed
    wa2 = default_whatsapp_block("+5548999991234", consent_status="OPTED_IN")
    assert wa2.consent_status != WhatsAppConsent.OPTED_IN.value

    wa3 = default_whatsapp_block(
        "+5548999991234",
        consent_status="OPTED_IN",
        consent_provenance="form_submit:2026-01-01:landing-page-x",
    )
    assert wa3.consent_status == WhatsAppConsent.OPTED_IN.value
    assert wa3.consent_provenance is not None


def test_personal_pattern_detector() -> None:
    assert looks_like_personal_pattern("maria.souza@acme.com")
    assert not looks_like_personal_pattern("contato@acme.com")

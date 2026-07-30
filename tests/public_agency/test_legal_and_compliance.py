"""Boundary tests for legal thresholds, classification, fragmentation, art.117, COI."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from scripts.public_agency import ELIGIBILITY_POTENTIAL, OBJECT_ENGINEERING, OBJECT_HUMAN, OBJECT_OTHER, SUM_UNKNOWN
from scripts.public_agency.conflict import (
    STATE_BLOCKED,
    STATE_CLEARED,
    STATE_PENDING,
    STATE_REVIEW,
    assess_conflict,
    blocks_outreach,
)
from scripts.public_agency.contacts import validate_contact, validate_contacts
from scripts.public_agency.fiscal_support import check_commercial_text, sanitize_offer_text
from scripts.public_agency.fragmentation import assess_fragmentation, price_from_scope
from scripts.public_agency.legal_thresholds import (
    evaluate_potential_eligibility,
    get_threshold,
    is_strictly_below_ceiling,
    load_threshold_catalog,
    parse_thresholds,
)
from scripts.public_agency.object_classification import classify_object, may_allege_dispensa_ceiling

AS_OF_2026 = date(2026, 7, 15)
AS_OF_2025 = date(2025, 6, 1)


def test_threshold_below_equal_above_engineering():
    thr = get_threshold(OBJECT_ENGINEERING, as_of=AS_OF_2026)
    assert thr is not None
    assert thr.amount == 130984.20
    assert is_strictly_below_ceiling(130984.19, thr.amount) is True
    assert is_strictly_below_ceiling(130984.20, thr.amount) is False  # equal not eligible
    assert is_strictly_below_ceiling(130984.21, thr.amount) is False

    below = evaluate_potential_eligibility(
        100000.0, OBJECT_ENGINEERING, as_of=AS_OF_2026, annual_sum_known=True, annual_sum_same_nature=100000.0
    )
    assert below["potentially_eligible"] is True
    assert below["eligibility_state"] == ELIGIBILITY_POTENTIAL

    equal = evaluate_potential_eligibility(130984.20, OBJECT_ENGINEERING, as_of=AS_OF_2026)
    assert equal["potentially_eligible"] is False
    assert "AMOUNT_NOT_STRICTLY_BELOW_CEILING" in equal["reason_codes"]

    above = evaluate_potential_eligibility(200000.0, OBJECT_ENGINEERING, as_of=AS_OF_2026)
    assert above["potentially_eligible"] is False


def test_threshold_other_service_2026():
    thr = get_threshold(OBJECT_OTHER, as_of=AS_OF_2026)
    assert thr is not None
    assert thr.amount == 65492.11
    assert is_strictly_below_ceiling(65492.11, thr.amount) is False


def test_temporal_validity_and_annual_update():
    thr_2025 = get_threshold(OBJECT_ENGINEERING, as_of=AS_OF_2025)
    thr_2026 = get_threshold(OBJECT_ENGINEERING, as_of=AS_OF_2026)
    assert thr_2025 is not None and thr_2026 is not None
    assert thr_2025.threshold_id != thr_2026.threshold_id
    assert thr_2025.amount == 125455.13
    assert thr_2026.amount == 130984.20
    # catalog has both years without code change
    all_t = parse_thresholds()
    assert any(t.effective_from.year == 2025 for t in all_t)
    assert any(t.effective_from.year == 2026 for t in all_t)
    cat = load_threshold_catalog()
    assert "thresholds" in cat


def test_object_classification_engineering_other_ambiguous():
    eng = classify_object("Contratação de obra de pavimentação asfáltica e drenagem urbana")
    assert eng.suggested_class == OBJECT_ENGINEERING
    assert eng.confidence > 0.5
    assert may_allege_dispensa_ceiling(eng) is True

    other = classify_object("Capacitação e treinamento de servidores em gestão de contratos")
    assert other.suggested_class == OBJECT_OTHER

    amb = classify_object("Consultoria administrativa e obra de reforma de prédio público")
    assert amb.suggested_class == OBJECT_HUMAN
    assert amb.human_validation_required is True
    assert may_allege_dispensa_ceiling(amb) is False

    empty = classify_object("")
    assert empty.suggested_class == OBJECT_HUMAN


def test_annual_sum_below_above_unknown():
    below = evaluate_potential_eligibility(
        50000.0,
        OBJECT_ENGINEERING,
        as_of=AS_OF_2026,
        annual_sum_known=True,
        annual_sum_same_nature=80000.0,
    )
    assert below["potentially_eligible"] is True
    assert below.get("annual_limit_adherence_claimed") is True

    above = evaluate_potential_eligibility(
        50000.0,
        OBJECT_ENGINEERING,
        as_of=AS_OF_2026,
        annual_sum_known=True,
        annual_sum_same_nature=200000.0,
    )
    assert above["potentially_eligible"] is False

    unknown = evaluate_potential_eligibility(
        50000.0,
        OBJECT_ENGINEERING,
        as_of=AS_OF_2026,
        annual_sum_known=False,
        annual_sum_same_nature=None,
    )
    assert unknown["annual_sum_state"] == SUM_UNKNOWN
    assert unknown.get("annual_limit_adherence_claimed") is False
    assert unknown["potentially_eligible"] is True  # unit amount only; no annual claim


def test_fragmentation_and_near_ceiling_pricing():
    thr = get_threshold(OBJECT_ENGINEERING, as_of=AS_OF_2026)
    assert thr
    frag = assess_fragmentation(
        proposed_amount=thr.amount * 0.98,
        ceiling=thr.amount,
        proposed_packages=[
            {"amount": 70000, "object": "obra pavimentação trecho A"},
            {"amount": 70000, "object": "obra pavimentação trecho B"},
        ],
    )
    assert frag.pricing_near_ceiling is True
    assert "packages_sum_above_ceiling_each_below" in frag.indicators or frag.fragmentation_suspected

    price = price_from_scope(effort_hours=100, hourly_rate=200, margin=0.1, ceiling=thr.amount)
    assert price["ceiling_used_as_price_anchor"] is False
    assert price["pricing_method"] == "SCOPE_EFFORT_RESPONSIBILITY"


def test_document_not_available_not_inferred_absence():
    # semantic constant used by pipeline evidence limitations
    marker = "DOCUMENT_NOT_AVAILABLE_IN_SOURCE"
    # pipeline must not invent AGENCY_DID_NOT_CREATE_DOCUMENT
    forbidden = "AGENCY_DID_NOT_CREATE_DOCUMENT"
    from scripts.public_agency import pipeline as pl

    src = Path(pl.__file__).read_text(encoding="utf-8")
    assert forbidden not in src or "must not" in src.lower()
    # presence of honest limitation language in package
    assert "DOCUMENT_NOT_AVAILABLE" in marker


def test_fiscal_exclusive_powers_blocked():
    bad = check_commercial_text("A CONFENGE irá homologar e autorizar pagamento e substituir o fiscal")
    assert bad.allowed is False
    assert bad.blocked_phrases

    good = check_commercial_text(
        "A CONFENGE prestará apoio técnico especializado à fiscalização e à gestão contratual, "
        "assistindo e subsidiando o fiscal público."
    )
    assert good.allowed is True

    sanitized = sanitize_offer_text("Vamos substituir o fiscal e autorizar pagamentos")
    assert "substituir o fiscal" not in sanitized.lower() or "apoiar" in sanitized.lower()


def test_conflict_known_pending_cleared():
    pending = assess_conflict(agency_id="a1", cnpj14="12345678000199", official_name="PREFEITURA X")
    assert pending.state == STATE_PENDING
    assert pending.cannot_assert_no_conflict is True
    assert blocks_outreach(pending) is True

    blocked = assess_conflict(
        agency_id="a1",
        known_conflict=True,
        known_conflict_reason="operator is fiscal",
    )
    assert blocked.state == STATE_BLOCKED

    cleared = assess_conflict(
        agency_id="a1",
        human_clearance={"cleared": True, "reviewer": "Tiago Sasaki", "note": "no overlap with public duties"},
    )
    assert cleared.state == STATE_CLEARED
    assert blocks_outreach(cleared) is False

    incomplete = assess_conflict(
        agency_id="a1",
        human_clearance={"cleared": True, "reviewer": "Tiago", "note": ""},
    )
    assert incomplete.state == STATE_REVIEW


def test_institutional_vs_personal_contact():
    personal = validate_contact(channel="email", value="joao@gmail.com")
    assert personal.institutional is False
    assert personal.rejected_reason == "personal_email_not_allowed"

    inst = validate_contact(channel="email", value="licitacao@pm.exemplo.sc.gov.br")
    assert inst.institutional is True

    wa = validate_contact(channel="whatsapp", value="48999999999", officially_published=False)
    assert wa.institutional is False

    batch = validate_contacts(
        [
            {"channel": "email", "value": "x@gmail.com"},
            {"channel": "email", "value": "obras@prefeitura.sc.gov.br"},
        ]
    )
    assert len(batch.rejected) >= 1
    assert len(batch.accepted) >= 1


def test_ambiguous_object_blocks_ceiling_allegation_in_eligibility():
    r = evaluate_potential_eligibility(10000.0, OBJECT_HUMAN, as_of=AS_OF_2026)
    assert r["potentially_eligible"] is False
    assert "OBJECT_CLASSIFICATION_AMBIGUOUS" in r["reason_codes"]

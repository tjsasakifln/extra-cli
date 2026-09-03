"""AC6 / AC10 — contrato de schema, whitelist de PII e disciplina de hash."""

from __future__ import annotations

from dataclasses import fields
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from scripts.confenge_live_intelligence import schema as li_schema
from scripts.confenge_live_intelligence.verifier import (
    LiveIntelligenceVerificationError,
    assert_no_undeclared_keys,
)
from scripts.inference_runtime.jobs import sha256_payload

UTC_NOW = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)


def _opportunity(**overrides):
    base = dict(
        opportunity_id="LI-TEST-1",
        source="pncp",
        source_as_of=UTC_NOW,
        objeto="Reforma de unidade basica de saude com estrutura metalica",
        objeto_state=li_schema.OBSERVED,
        valor_estimado_brl=Decimal("250000.00"),
        valor_state=li_schema.OBSERVED,
        valor_band="100K_1M",
        modalidade="Pregao",
        modalidade_state=li_schema.OBSERVED,
        uf="SC",
        geo_state=li_schema.OBSERVED,
        orgao_cnpj="12345678000199",
        orgao_state=li_schema.OBSERVED,
        data_encerramento=date(2026, 10, 1),
        deadline_state=li_schema.DEADLINE_OPEN,
    )
    base.update(overrides)
    return li_schema.LiveOpportunity(**base)


def _company(**overrides):
    base = dict(
        company_root8="11222333",
        source_as_of=UTC_NOW,
        date_resolver_version="ca-v2-precedence/1.0",
        observed_objects=("Reforma de escola municipal com estrutura metalica",),
        observed_value_bands=("100K_1M",),
        observed_ufs=("SC",),
        observed_buyer_cnpjs=("12345678000199",),
        most_recent_contracting_date=date(2025, 5, 1),
        contracting_date_state=li_schema.OBSERVED,
    )
    base.update(overrides)
    return li_schema.LiveCompany(**base)


# --- hash ------------------------------------------------------------------


def test_live_hash_is_field_order_independent() -> None:
    a = {"z": 1, "a": {"n": 2, "m": 3}}
    b = {"a": {"m": 3, "n": 2}, "z": 1}
    assert li_schema.live_hash(a) == li_schema.live_hash(b)


def test_live_hash_matches_repo_canonical_discipline() -> None:
    """Equivalencia byte-a-byte com ``sha256_payload`` (jobs.py:39) sem acoplar."""
    payload = {"b": [1, 2], "a": "áç", "c": {"k": None}}
    assert li_schema.live_hash(payload) == sha256_payload(payload)


def test_live_hash_is_sensitive_to_content() -> None:
    assert li_schema.live_hash({"a": 1}) != li_schema.live_hash({"a": 2})


def test_decimal_is_hashed_as_normalized_string_not_float() -> None:
    assert li_schema.live_hash({"v": Decimal("1.10")}) == li_schema.live_hash({"v": Decimal("1.1")})
    assert li_schema.canonical_json({"v": Decimal("2500.00")}) == '{"v":"2500"}'


def test_schema_hash_is_stable_and_declares_keysets() -> None:
    assert li_schema.schema_hash() == li_schema.schema_hash()
    assert len(li_schema.schema_hash()) == 64


# --- AC6: zero score numerico ---------------------------------------------


NUMERIC_TERMS = ("score", "rank", "weight", "peso", "percent", "count", "nota")


def test_fit_dataclass_has_no_numeric_score_field() -> None:
    for f in fields(li_schema.LiveCompanyOpportunityFit):
        assert not any(term in f.name.lower() for term in NUMERIC_TERMS), f.name
        assert f.type not in (int, float, "int", "float"), f.name


def test_fit_payload_has_no_numeric_value() -> None:
    from scripts.confenge_live_intelligence.fit import evaluate_fit

    fit = evaluate_fit(_company(), _opportunity(), as_of=date(2026, 9, 2))

    def walk(node, path: str) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, f"{path}.{k}")
        elif isinstance(node, (list, tuple)):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")
        else:
            assert not isinstance(node, (int, float, Decimal)), (
                f"valor numerico proibido no payload do FIT: {path}={node!r}"
            )

    walk(fit.as_payload(), "fit")


def test_dimension_states_are_tri_state() -> None:
    assert li_schema.DIMENSION_STATES == ("MATCH", "NO_MATCH", "UNKNOWN")
    assert len(li_schema.DIMENSION_NAMES) == 5


# --- AC10: whitelist -------------------------------------------------------


def test_opportunity_payload_keyset_is_subset_of_schema() -> None:
    payload = _opportunity().as_payload()
    assert set(payload) <= li_schema.OPPORTUNITY_PAYLOAD_KEYS
    assert_no_undeclared_keys(payload, kind="opportunity")


def test_company_payload_keyset_is_subset_of_schema() -> None:
    assert_no_undeclared_keys(_company().as_payload(), kind="company")


def test_undeclared_key_is_rejected_even_without_blacklist_hit() -> None:
    """AC10 — ``responsavel_nome`` nao bate em regex de blacklist; cai no whitelist."""
    payload = _opportunity().as_payload()
    payload["responsavel_nome"] = "Fulano de Tal"
    with pytest.raises(LiveIntelligenceVerificationError) as exc:
        assert_no_undeclared_keys(payload, kind="opportunity")
    assert "responsavel_nome" in str(exc.value)


def test_arbitrary_unknown_key_is_rejected() -> None:
    payload = _company().as_payload()
    payload["campo_vazado_por_join_lateral"] = 1
    with pytest.raises(LiveIntelligenceVerificationError):
        assert_no_undeclared_keys(payload, kind="company")


def test_no_declared_key_is_a_contact_field() -> None:
    all_keys = li_schema.OPPORTUNITY_PAYLOAD_KEYS | li_schema.COMPANY_PAYLOAD_KEYS | li_schema.FIT_PAYLOAD_KEYS
    for key in all_keys:
        assert not any(term in key.lower() for term in li_schema.FORBIDDEN_PII_KEY_TERMS), key


# --- invariantes tipados ---------------------------------------------------


def test_unknown_without_reason_is_refused_by_company_contract() -> None:
    with pytest.raises(li_schema.LiveIntelligenceSchemaError):
        _company(contracting_date_state=li_schema.UNKNOWN, most_recent_contracting_date=None)


def test_excluded_row_without_reason_code_is_refused() -> None:
    with pytest.raises(li_schema.LiveIntelligenceSchemaError):
        _opportunity(row_completeness_state=li_schema.ROW_EXCLUDED_INCOMPLETE)


def test_value_band_is_ordinal_label_not_arithmetic() -> None:
    assert li_schema.value_band(Decimal("100000")) == "ATE_100K"
    assert li_schema.value_band(Decimal("100000.01")) == "100K_1M"
    assert li_schema.value_band(Decimal("10000000.01")) == "ACIMA_10M"
    assert li_schema.value_band(None) is None

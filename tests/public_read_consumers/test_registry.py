"""Registry declares exactly three named consumers."""

from __future__ import annotations

from scripts.public_read_consumers.registry import (
    REQUIRED_CONSUMER_KEYS,
    get_consumer,
    list_consumer_ids,
    load_registry,
    validate_registry,
)


def test_registry_has_exactly_three_named_consumers() -> None:
    ids = list_consumer_ids()
    assert ids == [
        "web-cfg/contract-analysis",
        "web-cfg/market-answer/valor-tipico-contratos-pavimentacao",
        "web-cfg/b2g-xray",
    ]
    assert load_registry().get("generic_query_endpoint") is False


def test_each_consumer_declares_required_contract_fields() -> None:
    for consumer_id in list_consumer_ids():
        record = get_consumer(consumer_id)
        missing = [key for key in REQUIRED_CONSUMER_KEYS if key not in record]
        assert missing == [], consumer_id


def test_validate_registry_passes() -> None:
    report = validate_registry()
    assert report["ok"] is True
    assert report["errors"] == []


def test_aliases_resolve() -> None:
    assert get_consumer("contract-analysis")["consumer_id"] == "web-cfg/contract-analysis"
    assert get_consumer("market-answer-pavimentacao")["schema"] == "public-read-market-answer-pavimentacao/1.0"
    assert get_consumer("b2g-xray")["grain"] == "normalized_cnpj_or_canonical_entity_id"

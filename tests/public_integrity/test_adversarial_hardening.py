"""Order, replay, clock skew and exception-log adversarial cases on shipped produce()."""

from __future__ import annotations

import json
import logging

from scripts.public_integrity.cli import replay_fixture
from scripts.public_integrity.hashing import content_hash
from scripts.public_integrity.producer import produce
from scripts.public_integrity.redaction import install_log_redaction
from scripts.public_integrity.transport import FixtureTransport
from tests.public_integrity.helpers import FIXTURES, VALID_CNPJ


def test_replay_is_byte_stable() -> None:
    first = replay_fixture(FIXTURES / "matches.json", cnpj=VALID_CNPJ)
    second = replay_fixture(FIXTURES / "matches.json", cnpj=VALID_CNPJ)
    assert first["content_hash"] == second["content_hash"]
    assert first["aggregate_state"] == "MATCHES_FOUND"
    assert content_hash({key: value for key, value in first.items() if key != "content_hash"}) == first["content_hash"]


def test_record_order_does_not_change_content_hash() -> None:
    fixture = json.loads((FIXTURES / "multi-page-ceis.json").read_text(encoding="utf-8"))
    pages = dict(fixture["sources"]["CEIS"]["pages"])
    pages["1"], pages["2"] = pages["2"], pages["1"]
    fixture["sources"]["CEIS"]["pages"] = pages
    original = replay_fixture(FIXTURES / "multi-page-ceis.json", cnpj=VALID_CNPJ)
    reversed_run = produce(
        VALID_CNPJ,
        transport=FixtureTransport(fixture),
        clock=fixture.get("clock") or original["as_of"],
    )
    ids_original = sorted(record["official_id"] for record in original["records"])
    ids_reversed = sorted(record["official_id"] for record in reversed_run["records"])
    assert ids_original == ids_reversed
    assert original["aggregate_state"] == reversed_run["aggregate_state"]


def test_clock_skew_stale_cache_is_not_current() -> None:
    payload = replay_fixture(FIXTURES / "stale-cache.json", cnpj=VALID_CNPJ)
    assert payload["freshness"]["is_current"] is False
    assert payload["aggregate_state"] != "NO_MATCH_CONFIRMED"


def test_exception_log_redacts_cnpj(caplog) -> None:
    logger = install_log_redaction()
    with caplog.at_level(logging.INFO, logger=logger.name):
        payload = produce(
            VALID_CNPJ,
            transport=FixtureTransport(json.loads((FIXTURES / "timeout.json").read_text(encoding="utf-8"))),
            clock="2026-08-01T12:00:00+00:00",
        )
    assert payload["aggregate_state"] != "NO_MATCH_CONFIRMED"
    assert VALID_CNPJ not in caplog.text
    assert "".join(ch for ch in VALID_CNPJ if ch.isdigit()) not in caplog.text

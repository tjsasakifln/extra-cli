"""Separate CEIS/CNEP adapters against the injectable transport."""

from __future__ import annotations

from scripts.public_integrity.ceis import run_ceis
from scripts.public_integrity.cnep import run_cnep
from scripts.public_integrity.transport import FixtureTransport, load_fixture
from tests.public_integrity.helpers import CLOCK, FIXTURES, VALID_CNPJ


def test_ceis_and_cnep_are_separate_complete_runs() -> None:
    fixture = load_fixture(FIXTURES / "matches.json")
    transport = FixtureTransport(fixture)
    ceis = run_ceis(VALID_CNPJ, transport, captured_at=CLOCK)
    cnep = run_cnep(VALID_CNPJ, transport, captured_at=CLOCK)
    assert ceis.source_id == "CEIS"
    assert cnep.source_id == "CNEP"
    assert ceis.coverage_complete is True
    assert cnep.coverage_complete is True
    assert ceis.status == "MATCHES_FOUND"
    assert cnep.status == "NO_MATCH_CONFIRMED"
    assert ceis.records[0].official_id == "9001"
    assert transport.calls[0]["source_id"] == "CEIS"
    assert any(call["source_id"] == "CNEP" for call in transport.calls)

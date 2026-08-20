"""Zero failure/degraded fixtures return NO_MATCH_CONFIRMED."""

from __future__ import annotations

from scripts.public_integrity.cli import replay_fixture
from tests.public_integrity.helpers import FAILURE_FIXTURES, FIXTURES, INVALID_CNPJ, VALID_CNPJ


def test_zero_failure_fixtures_return_no_match_confirmed() -> None:
    seen: list[str] = []
    for name in FAILURE_FIXTURES:
        payload = replay_fixture(FIXTURES / name, cnpj=VALID_CNPJ)
        state = payload["aggregate_state"]
        seen.append(f"{name}:{state}")
        assert state != "NO_MATCH_CONFIRMED", seen
        assert state in {"PARTIAL", "UNKNOWN"}, seen
    invalid = replay_fixture(FIXTURES / "empty-complete.json", cnpj=INVALID_CNPJ)
    assert invalid["aggregate_state"] != "NO_MATCH_CONFIRMED"
    seen.append(f"invalid_cnpj:{invalid['aggregate_state']}")
    assert seen

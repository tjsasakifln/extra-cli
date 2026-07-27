"""Tests for per-item CMI proof runner."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.ops import cmi_item_proofs as proofs
from scripts.ops import contract_market_intelligence as cmi

DSN = os.environ.get("LOCAL_DATALAKE_DSN", "postgresql://test:test@127.0.0.1:5433/extra_test")
REQUIRE = os.environ.get("REQUIRE_REAL_DB", "").lower() in {"1", "true", "yes"}
PKG = Path("artifacts/campaigns/CONTRACT-MARKET-INTELLIGENCE-ACCEPT-01/final-package")


def test_all_aliases_registered():
    assert len(proofs.CHECKERS) == 47
    assert "CMI-10.1-01" in proofs.CHECKERS
    assert "CMI-11.1-20" in proofs.CHECKERS


def test_unit_value_and_win_rate_gates():
    # pure unit paths used by several aliases
    assert cmi.win_rate(wins=1, proposals_presented=None)["status"] == "NOT_COMPUTABLE"
    assert cmi.VALUE_DEFINITIONS["valor_pago"]["enum"] == "valor_pago"


@pytest.mark.real_db
@pytest.mark.skipif(not REQUIRE, reason="REQUIRE_REAL_DB")
def test_all_item_proofs_against_package():
    # Always regenerate package so Excel and material rows exist in CI.
    cmi.run_package(DSN, PKG, seed_if_empty=True)
    try:
        out = proofs.run_all()
        assert out["ok"] is True, out.get("failed")
        assert len(out["passed"]) == 47
        assert (PKG / "executive-review.xlsx").is_file()
    finally:
        cmi.cleanup_cmi_fixture(DSN)

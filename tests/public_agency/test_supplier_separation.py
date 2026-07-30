"""Ensure public-agency modality does not break supplier path semantics."""

from __future__ import annotations

from pathlib import Path

from scripts.commercial_leads import CAMPAIGN_ID as SUPPLIER_CAMPAIGN
from scripts.public_agency import CAMPAIGN_ID as PAG_CAMPAIGN
from scripts.public_agency import ENTITY_TYPE


def test_campaign_ids_distinct():
    assert SUPPLIER_CAMPAIGN != PAG_CAMPAIGN
    assert ENTITY_TYPE == "PUBLIC_AGENCY_PROSPECT"


def test_supplier_profile_still_drops_public_organs():
    import yaml

    root = Path(__file__).resolve().parents[2]
    profile = yaml.safe_load(
        (root / "config/commercial_profiles/confenge.yaml").read_text(encoding="utf-8")
    )
    assert profile["exclusions"]["drop_public_organs"] is True


def test_cycle_entry_has_target_flag():
    src = (Path(__file__).resolve().parents[2] / "scripts/ops/confenge_commercial_cycle.py").read_text(
        encoding="utf-8"
    )
    assert "--target" in src
    assert "public-agencies" in src
    assert "suppliers" in src


def test_makefile_target_var():
    mk = (Path(__file__).resolve().parents[2] / "Makefile").read_text(encoding="utf-8")
    assert "CONFENGE_COMMERCIAL_TARGET" in mk
    assert "test-public-agency" in mk

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
    """TARGET multi-modal lives on the router (outside commercial-ready freeze).

    Frozen ``confenge_commercial_cycle`` remains suppliers-only; Makefile
    redefines ``confenge-commercial-cycle`` to call the router.
    """
    root = Path(__file__).resolve().parents[2]
    router = (root / "scripts/ops/confenge_commercial_target_router.py").read_text(encoding="utf-8")
    frozen = (root / "scripts/ops/confenge_commercial_cycle.py").read_text(encoding="utf-8")
    mk = (root / "Makefile").read_text(encoding="utf-8")
    assert "--target" in router
    assert "public-agencies" in router
    assert "suppliers" in router
    # Freeze surface must stay suppliers-only (no multi-target CLI).
    assert "--target" not in frozen
    assert "public-agencies" not in frozen
    assert "confenge_commercial_target_router" in mk
    assert "CONFENGE_COMMERCIAL_TARGET" in mk


def test_makefile_target_var():
    mk = (Path(__file__).resolve().parents[2] / "Makefile").read_text(encoding="utf-8")
    assert "CONFENGE_COMMERCIAL_TARGET" in mk
    assert "test-public-agency" in mk
    assert "confenge_commercial_target_router" in mk

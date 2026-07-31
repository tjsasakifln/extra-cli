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


def test_router_suppliers_uses_registry_wrapper_when_required():
    """TARGET=suppliers must not silently bypass official registry fail-closed."""
    root = Path(__file__).resolve().parents[2]
    router = (root / "scripts/ops/confenge_commercial_target_router.py").read_text(encoding="utf-8")
    assert "confenge_registry_commercial_cycle" in router
    assert "official_registry_required" in router
    assert "CONFENGE_REQUIRE_OFFICIAL_REGISTRY" in router


def test_router_all_preserves_independent_modality_status(monkeypatch, tmp_path):
    """TARGET=all keeps separate statuses; one modality must not approve the other."""
    from scripts.ops import confenge_commercial_target_router as router

    def fake_suppliers(argv_tail):
        return 2, {
            "status": "BLOCKED",
            "exit_code": 2,
            "modality": "suppliers",
            "entry": "confenge_registry_commercial_cycle",
            "official_registry_required": True,
        }

    def fake_pag(args):
        return 0, {
            "status": "PASS",
            "reason": "PASS",
            "run_id": "pag-test-run",
            "leads": [{"agency_id": "x"}],
            "ready_state": "READY_FOR_TIAGO_REVIEW_PUBLIC_AGENCY_VERTICAL",
        }

    monkeypatch.setattr(router, "_run_suppliers", fake_suppliers)
    monkeypatch.setattr(router, "_run_public_agencies", fake_pag)
    out = tmp_path / "suppliers-out"
    pag_out = tmp_path / "pag-out"
    code = router.main(
        [
            "--target",
            "all",
            "--dsn",
            "postgresql://x",
            "--out",
            str(out),
            "--public-agency-out",
            str(pag_out),
        ]
    )
    assert code == 2  # suppliers BLOCKED dominates; public-agencies PASS is not hidden
    man = out / "combined-cycle-manifest.json"
    assert man.is_file()
    import json

    combined = json.loads(man.read_text(encoding="utf-8"))
    assert combined["results"]["suppliers"]["status"] == "BLOCKED"
    assert combined["results"]["public-agencies"]["status"] == "PASS"
    assert combined["any_blocked"] is True
    assert combined["all_pass"] is False
    assert combined["results"]["suppliers"]["exit_code"] == 2
    assert combined["results"]["public-agencies"]["run_id"] == "pag-test-run"

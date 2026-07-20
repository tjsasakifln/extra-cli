"""OCDS spike validation tests — ARCH-RESET PR D."""
from __future__ import annotations

from scripts.ocds_bridge.export_sample import build_package
from scripts.ocds_bridge.validate import validate_release_package, validate_release_structure


def test_demo_package_structurally_valid() -> None:
    package = build_package()
    report = validate_release_package(package)
    assert report["structural_ok"] is True
    assert report["n_releases"] >= 3


def test_contract_not_marked_paid() -> None:
    package = build_package()
    contract_releases = [r for r in package["releases"] if "contract" in (r.get("tag") or [])]
    assert contract_releases
    for rel in contract_releases:
        issues = validate_release_structure(rel)
        assert "contract_marked_paid_without_payment_observation" not in issues
        assert (rel.get("extra:value_semantics") or {}).get("is_paid") is False


def test_missing_tag_flagged() -> None:
    issues = validate_release_structure({"id": "x", "extra:provenance": {"source": "t"}})
    assert "missing_tag" in issues

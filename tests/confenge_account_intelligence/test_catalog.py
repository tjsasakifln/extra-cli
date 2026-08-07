"""Catalog version stamp and required service families."""

from __future__ import annotations

from scripts.confenge_account_intelligence.catalog import (
    REQUIRED_SERVICE_IDS,
    catalog_version,
    load_catalog,
    service_index,
)


def test_catalog_loads_with_version_and_ten_families() -> None:
    cat = load_catalog()
    assert catalog_version(cat)
    assert cat.get("catalog_id") == "confenge_account_service_catalog"
    idx = service_index(cat)
    missing = REQUIRED_SERVICE_IDS - set(idx)
    assert not missing, f"missing services: {missing}"
    assert len(idx) >= 10


def test_discovery_service_present() -> None:
    idx = service_index()
    assert "diagnostico_contratual_b2g" in idx
    assert idx["diagnostico_contratual_b2g"].get("discovery_fallback") is True

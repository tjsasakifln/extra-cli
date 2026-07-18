"""DoD §7.1 canonical source registry tests."""
from __future__ import annotations

from scripts.crawl.registry import (
    export_registry,
    iter_sources,
    lookup,
    validate_registry,
)


def test_registry_nonempty_stable_ids():
    sources = iter_sources(active_only=False)
    assert len(sources) >= 5
    ids = [s.name for s in sources]
    assert len(ids) == len(set(ids))
    assert "pncp" in ids


def test_each_source_has_url_capabilities_geo_credentials_flag():
    for s in iter_sources(active_only=False):
        rec = s.to_dod_record()
        assert rec["id"]
        assert rec["canonical_url"], s.name
        assert isinstance(rec["capabilities"], list) and rec["capabilities"], s.name
        assert rec["geo_coverage"], s.name
        assert isinstance(rec["needs_credentials"], bool)
        assert rec["pagination_limits"]
        assert rec["rate_limits"]
        assert rec["retry_strategy"]
        assert rec["backoff_strategy"]
        assert rec["operational_status"] in {
            "active",
            "implemented_not_proven",
            "blocked",
            "not_applicable",
        }
        assert rec["role"] in {"primary", "complementary", "gap_fill"}


def test_pncp_is_primary_active():
    pncp = lookup("pncp")
    assert pncp is not None
    assert pncp.role == "primary"
    assert pncp.operational_status == "active"
    assert "pncp.gov.br" in pncp.canonical_url


def test_validate_registry_ok_for_primaries():
    result = validate_registry()
    assert result["n_sources"] >= 5
    # primaries must not appear in missing
    primary_gaps = [m for m in result["missing_required"] if m["id"] in {"pncp", "ciga_ckan", "sc_compras"}]
    assert primary_gaps == [], primary_gaps
    assert result["ok"] is True or all(
        m["id"] not in {"pncp", "ciga_ckan", "sc_compras"} for m in result["missing_required"]
    )


def test_export_registry_json_serializable():
    import json

    data = export_registry()
    text = json.dumps(data, default=str)
    assert "pncp" in text
    assert "canonical_url" in text

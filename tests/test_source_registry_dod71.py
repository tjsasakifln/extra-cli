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


def test_operational_status_machine():
    from scripts.crawl.registry import SourceInfo

    active = SourceInfo(
        name="x_active",
        module="m",
        capabilities=["open_tenders"],
        operational_validated=True,
        canonical_url="https://example.com",
        is_active=True,
    )
    assert active.operational_status == "active"

    unproven = SourceInfo(
        name="x_unproven",
        module="m",
        capabilities=["open_tenders"],
        operational_validated=False,
        canonical_url="https://example.com",
        is_active=True,
    )
    assert unproven.operational_status == "implemented_not_proven"

    blocked = SourceInfo(
        name="x_blocked",
        module="m",
        capabilities=["open_tenders"],
        is_active=True,
        known_blockers=["blocked:no_access"],
        canonical_url="https://example.com",
    )
    assert blocked.operational_status == "blocked"

    na = SourceInfo(
        name="x_na",
        module="m",
        capabilities=["open_tenders"],
        is_active=False,
    )
    assert na.operational_status == "not_applicable"


def test_crawler_exists_not_auto_active():
    """Fonte com module/crawler NÃO é active só por existir."""
    from scripts.crawl.registry import SourceInfo

    s = SourceInfo(
        name="only_crawler",
        module="some_crawler",
        capabilities=["open_tenders"],
        operational_validated=False,
        canonical_url="https://example.com",
        is_active=True,
    )
    assert s.operational_status != "active"
    assert s.operational_status == "implemented_not_proven"


def test_all_sources_have_retry_backoff_role_status():
    for s in iter_sources(active_only=False):
        rec = s.to_dod_record()
        assert rec["retry_strategy"]
        assert rec["backoff_strategy"]
        assert rec["role"] in {"primary", "complementary", "gap_fill"}
        assert rec["operational_status"]
        # last_validation may be None — field still present
        assert "last_validation_at" in rec
        assert isinstance(rec["known_blockers"], list)

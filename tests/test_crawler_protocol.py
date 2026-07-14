"""Protocol conformance tests for all crawler modules.

Verifies that every crawler in monitor.py's module_map implements the
required ``crawl(mode) -> list[dict]`` and ``transform(records) -> list[dict]``
interface.

These are fast unit tests — no network, no database.
"""

from __future__ import annotations

import importlib

import pytest

# ---------------------------------------------------------------------------
# Crawler registry — mirrors monitor.py module_map
# ---------------------------------------------------------------------------

CRAWLER_MODULES: dict[str, str] = {}
COVERAGE_ONLY_SOURCES: set[str] = set()
CREDENTIAL_SOURCES: set[str] = set()


def _init_from_registry():
    """Populate module maps from the central source registry (called once)."""
    global CRAWLER_MODULES, COVERAGE_ONLY_SOURCES, CREDENTIAL_SOURCES
    if CRAWLER_MODULES:
        return
    from scripts.crawl.registry import get_coverage_only_sources, get_credential_sources, iter_sources

    for info in iter_sources():
        CRAWLER_MODULES[info.name] = f"scripts.crawl.{info.module}"
    CREDENTIAL_SOURCES = get_credential_sources()
    COVERAGE_ONLY_SOURCES = get_coverage_only_sources()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _load_module(source: str):
    """Import a crawler module by source key."""
    _init_from_registry()
    mod_path = CRAWLER_MODULES.get(source)
    if not mod_path:
        pytest.skip(f"Unknown source: {source}")
    return importlib.import_module(mod_path)


# Populate from registry at import time so parametrize works
_init_from_registry()


# ---------------------------------------------------------------------------
# Tests — interface conformance
# ---------------------------------------------------------------------------


class TestCrawlerInterface:
    """Every crawler module must expose crawl() and transform()."""

    @pytest.mark.unit
    @pytest.mark.parametrize("source", sorted(CRAWLER_MODULES))
    def test_has_crawl_function(self, source: str):
        mod = _load_module(source)
        assert hasattr(mod, "crawl"), f"{source}: missing crawl() function"
        assert callable(mod.crawl), f"{source}: crawl is not callable"

    @pytest.mark.unit
    @pytest.mark.parametrize("source", sorted(CRAWLER_MODULES))
    def test_has_transform_function(self, source: str):
        mod = _load_module(source)
        assert hasattr(mod, "transform"), f"{source}: missing transform() function"
        assert callable(mod.transform), f"{source}: transform is not callable"


class TestCrawlerSignatures:
    """crawl() and transform() must accept and return the right types."""

    @pytest.mark.unit
    @pytest.mark.parametrize("source", sorted(CRAWLER_MODULES))
    def test_transform_empty_list_returns_list(self, source: str):
        """transform([]) must always return a list (never None or exception)."""
        mod = _load_module(source)
        result = mod.transform([])
        assert isinstance(result, list), f"{source}: transform([]) returned {type(result).__name__}, expected list"

    @pytest.mark.unit
    @pytest.mark.parametrize("source", sorted(CRAWLER_MODULES))
    def test_crawl_accepts_mode_kwarg(self, source: str):
        """crawl() must accept a mode keyword argument (signature check only)."""
        import inspect

        mod = _load_module(source)
        sig = inspect.signature(mod.crawl)
        params = list(sig.parameters.keys())
        # Must have at least a 'mode' parameter
        assert "mode" in params, f"{source}: crawl() signature missing 'mode' parameter: {params}"


class TestCrawlerProtocol:
    """Verify Protocol conformance at runtime."""

    @pytest.mark.unit
    @pytest.mark.parametrize("source", sorted(CRAWLER_MODULES))
    def test_matches_protocol(self, source: str):
        """Module should structurally match CrawlerProtocol."""
        mod = _load_module(source)
        # Check that the module has both required methods
        assert hasattr(mod, "crawl"), f"{source}: missing crawl"
        assert hasattr(mod, "transform"), f"{source}: missing transform"


# ---------------------------------------------------------------------------
# Tests — source purpose markers
# ---------------------------------------------------------------------------


class TestSourcePurpose:
    """Coverage-only sources must declare SOURCE_PURPOSE."""

    @pytest.mark.unit
    @pytest.mark.parametrize("source", sorted(COVERAGE_ONLY_SOURCES))
    def test_coverage_only_has_purpose_marker(self, source: str):
        mod = _load_module(source)
        purpose = getattr(mod, "SOURCE_PURPOSE", None)
        assert purpose is not None, f"{source}: coverage-only source must set SOURCE_PURPOSE = 'coverage_only'"


# ---------------------------------------------------------------------------
# Tests — credential awareness
# ---------------------------------------------------------------------------


class TestCredentialAwareness:
    """Sources that require credentials must detect their absence gracefully."""

    @pytest.mark.unit
    @pytest.mark.parametrize("source", sorted(CREDENTIAL_SOURCES))
    def test_credential_source_importable_without_credentials(self, source: str):
        """Module must be importable even when credentials are missing."""
        mod = _load_module(source)
        assert mod is not None, f"{source}: failed to import module"

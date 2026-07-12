"""Smoke tests for all active data sources.

Verifies connectivity and basic functionality for each source.
Uses ``crawl("dry-run")`` or ``crawl("incremental")`` where possible
to avoid excessive API calls.

Classification:
    PASS_REAL                 — connected, received valid data
    SKIPPED_MISSING_CREDENTIALS — credentials required but not available
    FAIL_CONNECTIVITY         — could not reach the source
    FAIL_TRANSFORM            — data received but transform produced nothing
"""

from __future__ import annotations

import importlib
import os

import pytest


# ---------------------------------------------------------------------------
# Registry — mirrors monitor.py module_map
# ---------------------------------------------------------------------------

CRAWLER_MODULES: dict[str, str] = {}
CREDENTIAL_SOURCES: set[str] = set()
COVERAGE_ONLY_SOURCES: set[str] = set()

def _init_from_registry():
    """Populate module maps from the central source registry (called once)."""
    global CRAWLER_MODULES, CREDENTIAL_SOURCES, COVERAGE_ONLY_SOURCES
    if CRAWLER_MODULES:
        return
    from scripts.crawl.registry import iter_sources, get_credential_sources, get_coverage_only_sources
    for info in iter_sources():
        CRAWLER_MODULES[info.name] = f"scripts.crawl.{info.module}"
    CREDENTIAL_SOURCES = get_credential_sources()
    COVERAGE_ONLY_SOURCES = get_coverage_only_sources()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_module(source: str):
    _init_from_registry()
    mod_path = CRAWLER_MODULES.get(source)
    if not mod_path:
        pytest.skip(f"Unknown source: {source}")
    return importlib.import_module(mod_path)


def _check_credentials(source: str) -> tuple[bool, list[str]]:
    """Check if required credentials are set for *source*."""
    from scripts.crawl.credential_validator import validate_source_credentials

    return validate_source_credentials(source)


# Populate from registry at import time so parametrize works
_init_from_registry()


# ---------------------------------------------------------------------------
# Smoke tests — connectivity
# ---------------------------------------------------------------------------


class TestSourceConnectivity:
    """Verify that each source can be imported and has basic functionality."""

    @pytest.mark.smoke
    @pytest.mark.parametrize("source", sorted(CRAWLER_MODULES))
    def test_module_imports(self, source: str):
        """Module must be importable."""
        mod = _get_module(source)
        assert mod is not None
        assert hasattr(mod, "crawl")
        assert hasattr(mod, "transform")

    @pytest.mark.smoke
    @pytest.mark.parametrize("source", sorted(CREDENTIAL_SOURCES))
    def test_credential_source_detected(self, source: str):
        """Credential-requiring sources must be detected as such."""
        ok, missing = _check_credentials(source)
        if not ok:
            # Expected: credentials are missing in test env
            assert len(missing) > 0
            print(f"  [SKIP] {source}: missing credentials: {missing}")
        else:
            print(f"  [OK] {source}: credentials present")


class TestSourceDryRun:
    """Verify that sources support dry-run or handle it gracefully."""

    @pytest.mark.smoke
    @pytest.mark.parametrize("source", sorted(set(CRAWLER_MODULES) - CREDENTIAL_SOURCES))
    def test_crawl_accepts_mode(self, source: str):
        """Public sources should accept a mode kwarg without error."""
        import inspect

        mod = _get_module(source)
        sig = inspect.signature(mod.crawl)
        params = list(sig.parameters.keys())
        assert "mode" in params, f"{source}: crawl() has no 'mode' parameter"


class TestTransformEmptyList:
    """transform([]) must work without errors for all sources."""

    @pytest.mark.smoke
    @pytest.mark.parametrize("source", sorted(CRAWLER_MODULES))
    def test_transform_empty_returns_list(self, source: str):
        mod = _get_module(source)
        result = mod.transform([])
        assert isinstance(result, list), (
            f"{source}: transform([]) returned {type(result).__name__}"
        )


# ---------------------------------------------------------------------------
# Smoke tests — real data (public sources only)
# ---------------------------------------------------------------------------


@pytest.mark.smoke
@pytest.mark.slow
class TestPublicSourcesRealData:
    """Test public sources against their real APIs (small requests)."""

    @pytest.mark.parametrize("source", ["pncp", "compras_gov", "tce_sc"])
    def test_crawl_incremental_returns_data(self, source: str):
        """Crawl incremental mode should return records or empty list gracefully.

        Hard rule: fetched > 0 AND transformed == 0 → FAIL (not warning).
        Applies only to non-coverage-only sources.
        """
        _init_from_registry()
        mod = _get_module(source)
        try:
            records = mod.crawl("incremental")
        except Exception as e:
            pytest.fail(f"{source}: crawl('incremental') raised: {e}")

        assert isinstance(records, list), (
            f"{source}: crawl('incremental') returned {type(records).__name__}"
        )

        if len(records) == 0:
            print(f"  [EMPTY] {source}: no records in incremental window (may be normal)")
        else:
            print(f"  [DATA] {source}: {len(records)} record(s)")

            # Verify transform works — hard fail if transform discards all data
            transformed = mod.transform(records[:5])  # Test first 5
            assert isinstance(transformed, list)

            if len(transformed) == 0 and source not in COVERAGE_ONLY_SOURCES:
                pytest.fail(
                    f"{source}: fetched {len(records)} records but transform produced 0. "
                    f"This is a hard failure for non-coverage sources."
                )


# ---------------------------------------------------------------------------
# Report generator
# ---------------------------------------------------------------------------


def generate_smoke_report() -> dict:
    """Run smoke checks programmatically and return a structured report.

    State machine (each step gates the next):
        1. Module importable? YES → 2, else FAIL_IMPORT
        2. Has crawl()+transform()? YES → 3, else FAIL_MISSING_API
        3. Credentials required? If missing → SKIPPED_MISSING_CREDENTIALS
        4. crawl("incremental") succeeds? YES → 5, else FAIL_CONNECTIVITY
        5. fetched > 0? YES → 6, else EMPTY_VALIDATED
        6. transformed > 0? YES → PASS_REAL, else (coverage_only? PASS_REAL : FAIL_TRANSFORM)

    PASS_REAL requires: external source access + valid response + at least
    one record crawled AND transformed (or coverage_only with evidence).
    """
    _init_from_registry()

    report: dict[str, dict] = {}

    for source, mod_path in sorted(CRAWLER_MODULES.items()):
        entry: dict = {
            "source": source,
            "module": mod_path,
            "importable": False,
            "has_crawl": False,
            "has_transform": False,
            "credentials_ok": None,
            "credentials_missing": [],
            "smoke_result": None,
            "error": None,
            "fetched": 0,
            "transformed": 0,
        }

        # ── Step 1: Import ──────────────────────────────────────────
        try:
            mod = importlib.import_module(mod_path)
            entry["importable"] = True
        except Exception as e:
            entry["error"] = str(e)
            entry["smoke_result"] = "FAIL_IMPORT"
            report[source] = entry
            continue

        # ── Step 2: API surface check ───────────────────────────────
        entry["has_crawl"] = hasattr(mod, "crawl") and callable(mod.crawl)
        entry["has_transform"] = hasattr(mod, "transform") and callable(mod.transform)
        if not entry["has_crawl"] or not entry["has_transform"]:
            entry["smoke_result"] = "FAIL_MISSING_API"
            entry["error"] = "Missing crawl() or transform()"
            report[source] = entry
            continue

        # ── Step 3: Credential check ────────────────────────────────
        if source in CREDENTIAL_SOURCES:
            ok, missing = _check_credentials(source)
            entry["credentials_ok"] = ok
            entry["credentials_missing"] = missing
            if not ok:
                entry["smoke_result"] = "SKIPPED_MISSING_CREDENTIALS"
                report[source] = entry
                continue

        # ── Step 4: Real external access ────────────────────────────
        try:
            raw_records = mod.crawl("incremental")
        except Exception as e:
            entry["smoke_result"] = "FAIL_CONNECTIVITY"
            entry["error"] = str(e)
            report[source] = entry
            continue

        entry["fetched"] = len(raw_records)

        # ── Step 5: Empty check ─────────────────────────────────────
        if len(raw_records) == 0:
            entry["smoke_result"] = "EMPTY_VALIDATED"
            report[source] = entry
            continue

        # ── Step 6: Transform check ─────────────────────────────────
        try:
            sample = raw_records[:min(len(raw_records), 10)]
            transformed = mod.transform(sample)
            entry["transformed"] = len(transformed)
        except Exception as e:
            entry["smoke_result"] = "FAIL_TRANSFORM"
            entry["error"] = str(e)
            report[source] = entry
            continue

        # ── Step 7: Final classification ────────────────────────────
        if len(transformed) > 0:
            entry["smoke_result"] = "PASS_REAL"
        elif source in COVERAGE_ONLY_SOURCES:
            # coverage_only: empty transform is expected behavior
            entry["smoke_result"] = "PASS_REAL"
            entry["note"] = "coverage_only source: transform returns empty by design"
        else:
            entry["smoke_result"] = "FAIL_TRANSFORM"
            entry["error"] = (
                f"crawl() returned {len(raw_records)} records but "
                f"transform() produced 0 — degraded source"
            )

        report[source] = entry

    return report


if __name__ == "__main__":
    import json

    report = generate_smoke_report()
    print(json.dumps(report, indent=2, ensure_ascii=False))

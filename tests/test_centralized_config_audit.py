"""Tests for centralized config audit (DoD §27)."""
from __future__ import annotations

from scripts.ops.centralized_config_audit import audit


def test_audit_ok():
    r = audit()
    assert r["source_urls_centralized"]["ok"] is True
    assert r["domain_constants_centralized"]["ok"] is True
    assert r["configuration_centralized"]["ok"] is True
    assert r["summary"]["ok"] is True


def test_every_source_has_url():
    r = audit()
    assert r["source_urls_centralized"]["missing_url"] == []
    assert r["source_urls_centralized"]["n_sources"] >= 5

"""Refs #235 — versioned public-surface discovery for the canonical 1.093 IDs."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from scripts.factory_spine.contracts import (
    CANONICAL_UNIVERSE_SIZE,
    DISCOVERY_TERMINALS,
    apply_surface_revalidation,
    canonical_entity_ids,
    classify_discovery_surface,
    seal_discovery_run,
)
from scripts.source_registry.continuous_inventory import SURFACE_KINDS, SurfaceObservation


def test_issue_235_new_domain_is_unclassified_never_ignored() -> None:
    status, url, domain = classify_discovery_surface(
        SurfaceObservation(
            kind="institutional",
            canonical_url="https://prefeitura.novo-dominio.test/",
            platform=None,
            anchor_url="https://example.test/",
            method="anchor",
            http_status=200,
        ),
        known_domains={"pncp.gov.br"},
    )
    assert status == "UNCLASSIFIED"
    assert status in DISCOVERY_TERMINALS
    assert domain == "prefeitura.novo-dominio.test"
    assert url is not None


def test_issue_235_login_captcha_403_are_blocked() -> None:
    blocked_403, _, _ = classify_discovery_surface(
        SurfaceObservation(
            kind="procurement",
            canonical_url="https://compras.example.test/",
            platform="portal",
            anchor_url=None,
            method="probe",
            http_status=403,
        ),
        known_domains=set(),
    )
    blocked_captcha, _, _ = classify_discovery_surface(
        SurfaceObservation(
            kind="transparency",
            canonical_url="https://transparencia.example.test/",
            platform="portal",
            anchor_url=None,
            method="probe",
            http_status=200,
            response_hint="recaptcha challenge",
        ),
        known_domains={"transparencia.example.test"},
    )
    exhausted, url, _ = classify_discovery_surface(
        SurfaceObservation(
            kind="gazette",
            canonical_url=None,
            platform=None,
            anchor_url=None,
            method="exhausted_seed",
        ),
        known_domains=set(),
    )
    assert blocked_403 == "BLOCKED"
    assert blocked_captcha == "BLOCKED"
    assert exhausted == "DISCOVERY_EXHAUSTED_NO_SURFACE"
    assert url is None


def test_issue_235_revalidation_keeps_history() -> None:
    first, history = apply_surface_revalidation(
        None,
        status="FOUND",
        canonical_url="https://old.example.test/",
        domain="old.example.test",
        platform="betha",
    )
    current, versions = apply_surface_revalidation(
        first,
        status="UNCLASSIFIED",
        canonical_url="https://new.example.test/",
        domain="new.example.test",
        platform="egov",
    )
    assert current.version_no == 2
    assert versions[0].invalidated is True
    assert versions[0].canonical_url == "https://old.example.test/"
    assert versions[0].invalidation_reason == "binding_changed"
    assert current.domain == "new.example.test"
    assert len(history) == 1


def test_issue_235_seals_exactly_1093_versioned_ids() -> None:
    universe = canonical_entity_ids()
    assert len(universe) == CANONICAL_UNIVERSE_SIZE
    checked = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
    results = {}
    for entity_id in universe:
        current, versions = apply_surface_revalidation(
            None,
            status="DISCOVERY_EXHAUSTED_NO_SURFACE",
            canonical_url=None,
            domain=None,
            platform=None,
        )
        results[entity_id] = {
            "status": current.status,
            "history": [version.version_no for version in versions],
            "surfaces": [{"kind": kind} for kind in SURFACE_KINDS],
            "checked_at": checked.isoformat(),
            "next_check_at": checked.isoformat(),
        }
    sealed = seal_discovery_run(universe, results)
    assert sealed["entity_count"] == 1093
    assert sealed["outcome"] == "complete"
    with pytest.raises(ValueError, match="missing_discovery_results"):
        seal_discovery_run(universe, {universe[0]: results[universe[0]]})

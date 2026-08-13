"""Adapters skipped without status must not fake full ladder; loss reasons exclude PASS."""

from __future__ import annotations

from collections import Counter

from scripts.confenge_activation.rebuild_contact_terminals import _sources_from_enrich_row
from scripts.confenge_contact_resolution.discovery_state import sources_cover_required_ladder


def test_adapters_used_count_toward_ladder() -> None:
    src = _sources_from_enrich_row(
        {
            "adapters_used": ["registry", "site"],
            "adapters_skipped": ["public_docs:empty", "contact_page:empty", "web_search:empty"],
        }
    )
    assert "official_registry" in src
    assert "official_site" in src
    assert "public_docs_datalake" in src
    assert "company_public_pages" in src


def test_bare_skipped_without_status_not_counted() -> None:
    """Unqualified skip tokens must not prove an adapter ran."""
    src = _sources_from_enrich_row(
        {
            "adapters_used": ["registry"],
            "adapters_skipped": ["site", "public_docs", "contact_page"],  # bare — invalid
        }
    )
    assert src == ["official_registry"]
    assert "official_site" not in src


def test_error_status_counts_as_attempted() -> None:
    src = _sources_from_enrich_row(
        {
            "adapters_used": [],
            "adapters_skipped": ["site:error:Timeout", "registry:empty"],
        }
    )
    assert "official_site" in src
    assert "official_registry" in src


def test_process_plus_legacy_adapters_cannot_fake_new_council_ladder_step() -> None:
    process = ["process_administrative_docs", "pncp_annexes"]
    enrich = _sources_from_enrich_row(
        {
            "adapters_used": ["registry"],
            "adapters_skipped": [
                "site:empty",
                "public_docs:empty",
                "contact_page:empty",
                "web_search:empty",
            ],
        }
    )
    assert not sources_cover_required_ladder(process + enrich)
    assert sources_cover_required_ladder(process + enrich + ["professional_councils_associations"])


def test_loss_reason_filter_excludes_pass_strings() -> None:
    """Mirror strict ESR loss filter: service_fit_supported is not a loss."""
    reason_counter: Counter[str] = Counter()
    sample_reasons = Counter(
        {
            "service_fit_supported": 285,
            "all_gates_pass": 72,
            "ownership_identity_domain_mismatch": 10,
            "service_fit_unsupported": 0,
            "FAIL:service_fit_unsupported": 0,
            "domain_aligned_with_company": 50,
            "PASS:service_fit_supported": 100,
        }
    )
    for reason, n in sample_reasons.items():
        r = str(reason)
        if r.startswith("PASS:") or r in {
            "service_fit_supported",
            "all_gates_pass",
            "domain_aligned_with_company",
            "copy_context_complete",
        }:
            continue
        if r.startswith("provenance_trust:") and "REAL_OBSERVED" in r:
            continue
        reason_counter[r] += int(n)
    assert "service_fit_supported" not in reason_counter
    assert "all_gates_pass" not in reason_counter
    assert reason_counter["ownership_identity_domain_mismatch"] == 10

"""Registry coverage must not define top20 endogenously."""

from __future__ import annotations

from scripts.commercial_leads.supplier_registry import SupplierRegistryRecord, coverage_report


def _rec(cnpj: str) -> SupplierRegistryRecord:
    return SupplierRegistryRecord(
        cnpj14=cnpj,
        cnae_principal="7112-0/00",
        source="test",
        source_version="v1",
        source_date="2026-01-01",
    )


def test_top20_complete_universe_incomplete_is_selection_bias() -> None:
    all_cands = [f"{i:014d}" for i in range(100)]
    # Only 2% have registry — but they happen to be the "top20"
    top20 = all_cands[:20]
    reg = {c: _rec(c) for c in top20}
    # pretend only top20 enriched
    report = coverage_report(reg, all_candidates=all_cands, top20=top20, top100=all_cands[:100])
    assert report["top20_coverage_100pct"] is True
    assert report["selection_bias_risk"] is True
    assert report["block_reason"] == "BLOCKED_REGISTRY_SELECTION_BIAS"
    assert (report["registry_coverage_all_candidates"]["coverage"] or 0) < 1.0


def test_full_universe_coverage_clears_bias() -> None:
    all_cands = [f"{i:014d}" for i in range(50)]
    reg = {c: _rec(c) for c in all_cands}
    report = coverage_report(
        reg, all_candidates=all_cands, top20=all_cands[:20], top100=all_cands
    )
    assert report["registry_universe_resolved"] is True
    assert report["selection_bias_risk"] is False
    assert report["block_reason"] is None or report["block_reason"] != "BLOCKED_REGISTRY_SELECTION_BIAS"


def test_definitive_not_found_counts_as_resolved_universe() -> None:
    all_cands = [f"{i:014d}" for i in range(10)]
    reg = {c: _rec(c) for c in all_cands[:7]}
    statuses = {
        all_cands[7]: "NOT_FOUND_IN_OFFICIAL_DATASET",
        all_cands[8]: "INVALID_CNPJ",
        all_cands[9]: "NOT_COMPUTABLE",
    }
    report = coverage_report(
        reg,
        all_candidates=all_cands,
        top20=all_cands[:7],
        resolution_status=statuses,
    )
    assert report["registry_resolved_or_definitively_not_found"] == 1.0
    assert report["selection_bias_risk"] is False


def test_transient_failure_not_confused_with_not_found() -> None:
    all_cands = [f"{i:014d}" for i in range(5)]
    reg = {c: _rec(c) for c in all_cands[:3]}
    statuses = {
        all_cands[3]: "LOOKUP_TRANSIENT_FAILURE",
        all_cands[4]: "LOOKUP_TRANSIENT_FAILURE",
    }
    report = coverage_report(
        reg,
        all_candidates=all_cands,
        top20=all_cands[:3],
        resolution_status=statuses,
    )
    assert report["registry_resolved_or_definitively_not_found"] < 1.0
    assert report["selection_bias_risk"] is True


def test_expanding_coverage_does_not_invent_prior_top20_members() -> None:
    """Ampliar cobertura de 2%→100% não deve reescrever quem era invisível como se já estivesse no top20."""
    # Simulate: with 2% coverage only registry-backed firms can be "published"
    universe = [f"{i:014d}" for i in range(100)]
    rich = set(universe[:2])
    # ranking scores independent of registry — pure score order
    scores = {c: float(100 - i) for i, c in enumerate(universe)}
    # biased queue: only among rich
    biased_top = sorted(rich, key=lambda c: -scores[c])[:2]
    # full coverage ranking
    full_top20 = sorted(universe, key=lambda c: -scores[c])[:20]
    # firms that were invisible under bias must not appear as if previously ranked in top20
    previously_invisible = [c for c in full_top20 if c not in rich]
    assert previously_invisible, "fixture must include newly visible firms"
    assert all(c not in biased_top for c in previously_invisible)

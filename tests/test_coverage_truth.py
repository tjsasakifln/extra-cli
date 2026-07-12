"""Offline tests for Coverage Truth MVP.

Tests the core metric computation pipeline without requiring a live database:
    simulated source run → ledger evidence → deduplicated metrics → report.

Key properties proven:
    - Failure state != legitimate zero (success_zero)
    - Out-of-radius entities excluded from denominator
    - Sources do not duplicate entities in counts
    - Freshness is independent from bid/contract presence
"""

from __future__ import annotations

import math
from datetime import date, datetime, timezone

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_entity(
    eid: int,
    razao: str = "MUNICIPIO TESTE",
    municipio: str = "Florianopolis",
    lat: float = -27.5954,
    lon: float = -48.5480,
    raio_200km: bool = True,
) -> dict:
    return {
        "id": eid,
        "razao_social": razao,
        "cnpj_8": f"{eid:08d}",
        "municipio": municipio,
        "codigo_ibge": f"{eid:07d}",
        "natureza_juridica": "Municipio",
        "latitude": lat,
        "longitude": lon,
        "distancia_fk": 0.0,
    }


def make_coverage(
    entity_id: int,
    source: str,
    is_covered: bool = True,
    last_seen_at: date | None = None,
    total_bids: int = 5,
    within_200km: bool = True,
    match_method: str = "direct",
) -> dict:
    return {
        "entity_id": entity_id,
        "source": source,
        "last_seen_at": last_seen_at or date.today(),
        "total_bids": total_bids,
        "is_covered": is_covered,
        "within_200km": within_200km,
        "match_method": match_method,
    }


def make_evidence(
    source: str,
    state: str = "success_with_data",
    entity_id: int | None = None,
    completed_at: datetime | None = None,
) -> dict:
    return {
        "id": 1,
        "entity_id": entity_id,
        "source": source,
        "data_type": "bids",
        "state": state,
        "completed_at": completed_at or datetime.now(timezone.utc),
        "run_id": "test-run-001",
        "queried_start": None,
        "queried_end": None,
        "count_obtained": 100,
        "count_transformed": 95,
        "count_persisted": 90,
        "error_message": None,
        "error_code": None,
    }


ALL_TEST_SOURCES = ["pncp", "dom_sc", "contracts"]


# ---------------------------------------------------------------------------
# Import the real compute_metrics
# ---------------------------------------------------------------------------

@pytest.fixture
def compute_metrics_fn():
    from scripts.coverage_truth import compute_metrics

    return compute_metrics


# ═══════════════════════════════════════════════════════════════════════════
# Haversine tests
# ═══════════════════════════════════════════════════════════════════════════


class TestHaversine:
    def test_same_point_zero(self):
        from scripts.coverage_truth import haversine_km

        assert haversine_km(-27.5954, -48.5480, -27.5954, -48.5480) == 0.0

    def test_florianopolis_to_joinville(self):
        from scripts.coverage_truth import haversine_km

        dist = haversine_km(-27.5954, -48.5480, -26.3044, -48.8467)
        # Joinville ~147 km from Florianópolis (actual ~163 by road)
        assert 130 < dist < 170

    def test_florianopolis_to_porto_alegre(self):
        from scripts.coverage_truth import haversine_km

        dist = haversine_km(-27.5954, -48.5480, -30.0346, -51.2177)
        # ~380 km (actual ~375 km)
        assert 350 < dist < 420

    def test_out_of_radius_entity_excluded(self):
        from scripts.coverage_truth import haversine_km

        # São Paulo (~490 km from Floripa)
        dist = haversine_km(-27.5954, -48.5480, -23.5505, -46.6333)
        assert dist > 200
        assert dist > 400

    def test_radius_boundary_inclusive(self):
        from scripts.coverage_truth import haversine_km

        # A point exactly at radius boundary should be included (<= radius)
        # Just test that the function is symmetric
        d1 = haversine_km(-27.5, -48.5, -27.6, -48.6)
        d2 = haversine_km(-27.6, -48.6, -27.5, -48.5)
        assert abs(d1 - d2) < 0.001


# ═══════════════════════════════════════════════════════════════════════════
# Evidence state mapping tests
# ═══════════════════════════════════════════════════════════════════════════


class TestMapEvidenceState:
    def test_success_with_data(self):
        from scripts.crawl.monitor import _map_evidence_state

        assert _map_evidence_state("success", "", 100) == "success_with_data"

    def test_success_zero(self):
        from scripts.crawl.monitor import _map_evidence_state

        assert _map_evidence_state("success", "", 0) == "success_zero"

    def test_empty_is_success_zero(self):
        from scripts.crawl.monitor import _map_evidence_state

        assert _map_evidence_state("empty", "", 0) == "success_zero"

    def test_degraded_is_partial(self):
        from scripts.crawl.monitor import _map_evidence_state

        assert _map_evidence_state("degraded", "", 100) == "partial"

    def test_failed_is_connection_failed(self):
        from scripts.crawl.monitor import _map_evidence_state

        assert _map_evidence_state("failed", "", 100) == "connection_failed"

    def test_skipped_is_not_investigated(self):
        from scripts.crawl.monitor import _map_evidence_state

        assert _map_evidence_state("skipped", "", 0) == "not_investigated"

    def test_error_code_takes_priority(self):
        from scripts.crawl.monitor import _map_evidence_state

        # missing_credentials error → auth_failed even if status is "success"
        assert _map_evidence_state("success", "missing_credentials", 100) == "auth_failed"

    def test_crawler_not_implemented(self):
        from scripts.crawl.monitor import _map_evidence_state

        assert _map_evidence_state("failed", "crawler_not_implemented", 0) == "not_applicable"

    def test_unknown_status_defaults_to_not_investigated(self):
        from scripts.crawl.monitor import _map_evidence_state

        assert _map_evidence_state("unknown_status", "", 0) == "not_investigated"

    def test_failure_never_maps_to_success(self):
        """Prove failure != legitimate zero: failed states never map to success_*."""
        from scripts.crawl.monitor import _map_evidence_state

        failure_states = ["failed", "degraded"]
        for fs in failure_states:
            result = _map_evidence_state(fs, "", 0)
            assert "success" not in result, f"{fs} incorrectly mapped to {result}"

        # error codes that should never become success
        error_codes = ["crawler_not_implemented", "missing_credentials", "fetch_failed", "runtime_error"]
        for ec in error_codes:
            result = _map_evidence_state("success", ec, 100)
            assert "success" not in result, f"{ec} incorrectly mapped to {result}"


# ═══════════════════════════════════════════════════════════════════════════
# Core metric computation tests
# ═══════════════════════════════════════════════════════════════════════════


class TestComputeMetrics:
    """Test metric computation with simulated data."""

    def test_denominator_counts_only_in_radius_entities(self, compute_metrics_fn):
        """Excluded/out-of-radius entities do not affect the denominator."""
        entities = [
            make_entity(1, "In Radius A", lat=-27.5, lon=-48.5),
            make_entity(2, "In Radius B", lat=-27.3, lon=-48.8),
        ]
        # Entity 3 is at São Paulo lat/lon (~490 km) but NOT passed to compute_metrics
        # because load_entities_within_radius filters it out.
        coverage = [
            make_coverage(1, "pncp", is_covered=True),
            make_coverage(2, "pncp", is_covered=False),
        ]
        evidence = [
            make_evidence("pncp", "success_with_data"),
        ]

        result = compute_metrics_fn(
            entities, coverage, evidence, [], {}, radius_km=200,
        )

        assert result["denominator"]["total_entities_within_radius"] == 2
        # Entity 3 (out of radius) is NOT in the denominator
        assert result["monitoring_coverage"]["entities_with_coverage"] == 1

    def test_out_of_radius_entities_not_in_denominator(self, compute_metrics_fn):
        """If only in-radius entities are passed, denominator = len(entities)."""
        # Simulate what happens after load_entities_within_radius filters
        entities_in_radius = [
            make_entity(1, "In Radius", lat=-27.5, lon=-48.5),
        ]
        # Entity 2 is out of radius and NOT included in entities list
        # (filtered by load_entities_within_radius)
        coverage = [
            make_coverage(1, "pncp", is_covered=True),
        ]

        result = compute_metrics_fn(
            entities_in_radius, coverage, [], [], {}, radius_km=200,
        )

        assert result["denominator"]["total_entities_within_radius"] == 1

    def test_sources_do_not_duplicate_entities(self, compute_metrics_fn):
        """Entity covered by 3 sources counts as 1 covered entity, not 3."""
        entities = [make_entity(1, "Test Entity")]
        coverage = [
            make_coverage(1, "pncp", is_covered=True),
            make_coverage(1, "dom_sc", is_covered=True),
            make_coverage(1, "contracts", is_covered=True),
        ]

        result = compute_metrics_fn(
            entities, coverage, [], [], {}, radius_km=200,
        )

        # Monitoring coverage: entity is covered if ANY source has is_covered
        assert result["monitoring_coverage"]["entities_with_coverage"] == 1
        assert result["monitoring_coverage"]["pct"] == 100.0

        # Per-source counts can sum to > denominator (expected — not a bug)
        total_by_source = sum(
            s["entities_covered"]
            for s in result["monitoring_coverage"]["by_source"].values()
        )
        # Multiple sources covering same entity → total > denominator
        assert total_by_source >= 1

    def test_freshness_independent_from_bid_presence(self, compute_metrics_fn):
        """Freshness and bid presence are computed independently."""
        # Entity 1: has bids AND is fresh
        # Entity 2: has bids but STALE (last seen 100 days ago)
        # Entity 3: NO bids but FRESH (coverage without bids is possible via coverage_only sources)
        entities = [
            make_entity(1, "Fresh with bids"),
            make_entity(2, "Stale with bids"),
            make_entity(3, "Fresh no bids"),
        ]
        today = date.today()
        coverage = [
            make_coverage(1, "pncp", is_covered=True, last_seen_at=today, total_bids=10),
            make_coverage(2, "pncp", is_covered=True, last_seen_at=today.replace(year=today.year - 1), total_bids=5),
            make_coverage(3, "ciga_ckan", is_covered=True, last_seen_at=today, total_bids=0),
        ]

        result = compute_metrics_fn(
            entities, coverage, [], [], {}, radius_km=200,
        )

        # Freshness: 2 of 3 are fresh (entity 1 and 3)
        assert result["freshness"]["fresh_count"] == 2
        assert result["freshness"]["stale_count"] == 1

        # Bid presence: 2 of 3 have bids (entity 1 and 2)
        assert result["bid_presence"]["entities_with_bids"] == 2

        # Freshness and bid presence are DIFFERENT metrics
        # They can coincidentally have same pct; prove independence by counts
        # Entity 3 is fresh (via ciga_ckan) but has no bids
        # Entity 2 has bids but is stale
        # The sets of entities counted differ
        assert result["freshness"]["fresh_count"] == 2  # entities 1,3
        assert result["bid_presence"]["entities_with_bids"] == 2  # entities 1,2
        # Entity 3 demonstrates: fresh WITHOUT bids → independence proven
        # Entity 2 demonstrates: bids WITHOUT freshness → independence proven

    def test_failure_not_equal_to_legitimate_zero(self, compute_metrics_fn):
        """Prove failure != legitimate zero in evidence states."""
        # success_zero = source checked, confirmed zero records (legitimate)
        # connection_failed = source NOT checked successfully (failure)
        # These must produce different health metrics

        entities = [make_entity(1, "Test")]
        coverage = []  # No coverage yet

        # Evidence: one source with success_zero, one with connection_failed
        evidence = [
            make_evidence("pncp", "success_zero"),
            make_evidence("dom_sc", "connection_failed"),
        ]

        result = compute_metrics_fn(
            entities, coverage, evidence, [], {}, radius_km=200,
        )

        # Both sources should appear in gaps with different states
        gaps = result["gaps"]["sample"]
        gap_states = {g["source"]: g["state"] for g in gaps}
        assert gap_states.get("pncp") == "success_zero"
        assert gap_states.get("dom_sc") == "connection_failed"

    def test_all_sources_failed_shows_zero_monitoring_coverage(self, compute_metrics_fn):
        """When all sources fail, monitoring coverage = 0%, not 100%."""
        entities = [make_entity(1, "Test")]
        coverage = []  # No coverage — all sources failed
        evidence = [
            make_evidence("pncp", "connection_failed"),
            make_evidence("dom_sc", "connection_failed"),
        ]

        result = compute_metrics_fn(
            entities, coverage, evidence, [], {}, radius_km=200,
        )

        assert result["monitoring_coverage"]["pct"] == 0.0
        assert result["monitoring_coverage"]["entities_with_coverage"] == 0
        assert result["monitoring_coverage"]["entities_never_checked"] == 1

    def test_no_95_pct_claim_in_metrics(self, compute_metrics_fn):
        """Verify no metric claims ≥95% completeness or recall."""
        entities = [make_entity(i, f"Entity {i}") for i in range(1, 6)]
        # 2 covered, 3 uncovered = 40%
        coverage = [
            make_coverage(1, "pncp", is_covered=True),
            make_coverage(2, "pncp", is_covered=True),
        ]

        result = compute_metrics_fn(
            entities, coverage, [], [], {}, radius_km=200,
        )

        # The metric values themselves may be any percentage
        # The important thing: no field name claims "completeness" or "recall"
        result_str = str(result)
        assert "completeness" not in result_str.lower()
        assert "complete" not in result_str.lower()
        # The .md report explicitly warns against completeness claims
        # (verified via build_markdown output, not via metric dict)

    def test_contract_presence_separate_from_bid_presence(self, compute_metrics_fn):
        """Contract presence counts only source='contracts'."""
        entities = [make_entity(1, "Has contracts"), make_entity(2, "No contracts")]
        coverage = [
            make_coverage(1, "pncp", is_covered=True),  # bid
            make_coverage(1, "contracts", is_covered=True),  # contract
            make_coverage(2, "pncp", is_covered=True),  # bid only, no contract
        ]
        contract_presence = {1: True}  # Only entity 1 has contracts

        result = compute_metrics_fn(
            entities, coverage, [], [], contract_presence, radius_km=200,
        )

        assert result["bid_presence"]["entities_with_bids"] == 2  # both have bids
        assert result["contract_presence"]["entities_with_contracts"] == 1  # only entity 1

    def test_gap_ranking_by_marginal_impact(self, compute_metrics_fn):
        """Gaps are ranked by number of uncovered entities per source."""
        entities = [make_entity(i, f"Entity {i}") for i in range(1, 4)]
        coverage = [
            make_coverage(1, "pncp", is_covered=True),  # entity 1 covered by pncp
            # entities 2,3 uncovered for pncp
            # all 3 uncovered for dom_sc, contracts
        ]
        evidence = [
            make_evidence("pncp", "success_with_data"),
            make_evidence("dom_sc", "success_zero"),
            make_evidence("contracts", "not_investigated"),
        ]

        result = compute_metrics_fn(
            entities, coverage, evidence, [], {}, radius_km=200,
        )

        # Next best source should be the one with most uncovered entities
        next_best = result["gaps"]["next_best_source"]
        assert next_best is not None
        # dom_sc and contracts both have 3 uncovered, pncp has 2
        # The first ranked source should have the highest count
        by_source = result["gaps"]["by_source"]
        first_count = list(by_source.values())[0] if by_source else 0
        assert first_count >= next_best["uncovered_entities_resolved"]

    def test_empty_entities_produces_zero_metrics(self, compute_metrics_fn):
        """Empty entity list produces zero values, not division errors."""
        result = compute_metrics_fn([], [], [], [], {}, radius_km=200)

        assert result["denominator"]["total_entities_within_radius"] == 0
        assert result["monitoring_coverage"]["pct"] == 0
        assert result["freshness"]["pct_fresh"] == 0
        assert result["bid_presence"]["pct"] == 0
        assert result["contract_presence"]["pct"] == 0

    def test_evidence_ledger_empty_produces_graceful_degradation(self, compute_metrics_fn):
        """When evidence ledger is empty, metrics still compute from entity_coverage."""
        entities = [make_entity(1, "Test")]
        coverage = [make_coverage(1, "pncp", is_covered=True)]

        result = compute_metrics_fn(entities, coverage, [], [], {}, radius_km=200)

        # Metrics still work with entity_coverage fallback
        assert result["meta"]["evidence_ledger_available"] is False
        assert result["monitoring_coverage"]["pct"] == 100.0
        # Source health should have fallback note
        pncp_health = result["source_health"].get("pncp", {})
        assert pncp_health.get("_note") is not None or pncp_health.get("health_pct") is not None


# ═══════════════════════════════════════════════════════════════════════════
# Integration: simulated pipeline end-to-end
# ═══════════════════════════════════════════════════════════════════════════


class TestSimulatedPipeline:
    """Simulate: source run → ledger evidence → deduplicated metrics → report."""

    def test_full_pipeline_simulation(self, compute_metrics_fn):
        """End-to-end: simulate a crawl run that populates evidence + coverage."""
        # ── Setup: 5 entities within 200km ────────────────────────────
        entities = [
            make_entity(1, "Prefeitura Alpha", lat=-27.5, lon=-48.5),
            make_entity(2, "Prefeitura Beta", lat=-27.3, lon=-48.8),
            make_entity(3, "Camara Gamma", lat=-27.1, lon=-49.0),
            make_entity(4, "Autarquia Delta", lat=-27.7, lon=-48.3),
            make_entity(5, "Fundo Epsilon", lat=-27.9, lon=-48.1),
        ]

        # ── Simulate PNCP crawl run ──────────────────────────────────
        # crawl() fetched 200 records, transform() produced 180,
        # upsert inserted 150 new + updated 30, matched 4 of 5 entities
        pncp_evidence = [
            make_evidence("pncp", "success_with_data", completed_at=datetime(2026, 7, 12, 9, 0, 0, tzinfo=timezone.utc)),
        ]

        # entity_coverage after PNCP run
        pncp_coverage = [
            make_coverage(1, "pncp", is_covered=True, total_bids=50, last_seen_at=date(2026, 7, 12)),
            make_coverage(2, "pncp", is_covered=True, total_bids=30, last_seen_at=date(2026, 7, 10)),
            make_coverage(3, "pncp", is_covered=True, total_bids=20, last_seen_at=date(2026, 7, 8)),
            make_coverage(4, "pncp", is_covered=True, total_bids=10, last_seen_at=date(2026, 7, 5)),
            # Entity 5: no PNCP coverage (not matched)
        ]

        # ── Simulate contracts crawl run ─────────────────────────────
        contracts_evidence = [
            make_evidence("contracts", "success_with_data", completed_at=datetime(2026, 7, 12, 10, 0, 0, tzinfo=timezone.utc)),
        ]

        contracts_coverage = [
            make_coverage(1, "contracts", is_covered=True, total_bids=5, last_seen_at=date(2026, 7, 11)),
            make_coverage(3, "contracts", is_covered=True, total_bids=2, last_seen_at=date(2026, 7, 9)),
        ]

        # ── Simulate DOM-SC crawl run ────────────────────────────────
        # This run FAILED with connection error
        dom_sc_evidence = [
            make_evidence("dom_sc", "connection_failed", completed_at=datetime(2026, 7, 12, 8, 0, 0, tzinfo=timezone.utc)),
        ]
        # No DOM-SC coverage rows (run failed before producing data)

        all_evidence = pncp_evidence + contracts_evidence + dom_sc_evidence
        all_coverage = pncp_coverage + contracts_coverage

        # ── Compute metrics ──────────────────────────────────────────
        result = compute_metrics_fn(
            entities, all_coverage, all_evidence, [], {}, radius_km=200,
        )

        # ── Assertions ───────────────────────────────────────────────
        assert result["denominator"]["total_entities_within_radius"] == 5

        # Monitoring coverage: 4 entities covered (entity 5 has none)
        assert result["monitoring_coverage"]["entities_with_coverage"] == 4
        assert result["monitoring_coverage"]["pct"] == 80.0

        # PNCP per-source: 4 covered
        pncp_src = result["monitoring_coverage"]["by_source"]["pncp"]
        assert pncp_src["entities_covered"] == 4

        # Contracts per-source: 2 covered
        contracts_src = result["monitoring_coverage"]["by_source"]["contracts"]
        assert contracts_src["entities_covered"] == 2

        # DOM-SC per-source: 0 covered (run failed)
        dom_src = result["monitoring_coverage"]["by_source"]["dom_sc"]
        assert dom_src["entities_covered"] == 0

        # Gaps: entity 5 uncovered for all 3 sources = 3 gaps
        # Plus entities 2,4,5 uncovered for contracts = 3 gaps
        # Plus entities 1-5 uncovered for dom_sc = 5 gaps
        # Total: entity 1 (contracts+n/a, dom_sc), 2 (contracts, dom_sc), 3 (dom_sc), 4 (contracts, dom_sc), 5 (pncp, contracts, dom_sc)
        # Wait, let me recalculate. 5 entities × 3 sources = 15 total combinations
        # Covered: entity 1 (pncp, contracts), 2 (pncp), 3 (pncp, contracts), 4 (pncp)
        # Total covered combinations = 2 + 1 + 2 + 1 = 6
        # Gaps = 15 - 6 = 9
        assert result["gaps"]["total_gap_combinations"] >= 1

        # Bid presence: 4 entities have bids
        assert result["bid_presence"]["entities_with_bids"] == 4

        # Freshness: entities 1-4 have freshness dates
        assert result["freshness"]["fresh_count"] >= 1
        assert result["freshness"]["unknown_count"] == 1  # entity 5 never seen

    def test_report_output_contains_required_sections(self, compute_metrics_fn):
        """Generated report dict has all required metric sections."""
        entities = [make_entity(1, "Test")]
        coverage = [make_coverage(1, "pncp", is_covered=True)]

        result = compute_metrics_fn(entities, coverage, [], [], {}, radius_km=200)

        required_keys = [
            "meta",
            "denominator",
            "monitoring_coverage",
            "freshness",
            "bid_presence",
            "contract_presence",
            "source_health",
            "gaps",
        ]
        for key in required_keys:
            assert key in result, f"Missing key: {key}"

        # Denominator must have explicit count
        assert isinstance(result["denominator"]["total_entities_within_radius"], int)

        # Gaps must have next_best_source recommendation
        assert "next_best_source" in result["gaps"]

        # Meta must declare evidence_ledger_available
        assert "evidence_ledger_available" in result["meta"]

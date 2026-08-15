"""Tests for #315 national contracts storage-workload contract."""

from __future__ import annotations

from scripts.national_contract_truth.storage_workload import (
    MIN_REPRESENTATIVE_FACTS,
    WORKLOAD_QUERIES,
    DesignCandidate,
    WorkloadEvidence,
    evaluate_pk_headroom,
    seal_workload,
)


def test_serial_does_not_support_national_growth() -> None:
    serial = evaluate_pk_headroom("SERIAL", current_rows=4_000_000)
    assert serial["supports_national_growth"] is False
    assert serial["blocker"] == "SERIAL_EXHAUSTION_RISK"
    big = evaluate_pk_headroom("BIGSERIAL", current_rows=4_000_000)
    assert big["supports_national_growth"] is True


def test_unrun_corpus_stays_unproven() -> None:
    candidate = DesignCandidate(
        name="unpartitioned_brin",
        partitioning="none",
        pk_type="BIGSERIAL",
        notes="candidate only; not selected",
    )
    report = seal_workload(
        corpus_facts=1_000,
        incremental_churn=50,
        evidence=(),
        candidate=candidate,
        current_rows=1_000,
    )
    assert report["seal"] == "UNPROVEN"
    assert report["claim_nacional_physical_design_proven"] is False
    assert report["corpus_facts"] < MIN_REPRESENTATIVE_FACTS
    assert any(b.startswith("corpus_below_representative") for b in report["blockers"])
    assert {q["id"] for q in report["workload"]} == {q["id"] for q in WORKLOAD_QUERIES}


def test_full_evidence_seals_proven() -> None:
    candidate = DesignCandidate(
        name="range_partition_month",
        partitioning="range(source_event_date)",
        pk_type="BIGSERIAL",
        notes="decision pending cost comparison",
    )
    evidence = tuple(
        WorkloadEvidence(
            query_id=q["id"],
            explain_analyze="Index Scan",
            p50_ms=5.0,
            p95_ms=12.0,
            p99_ms=20.0,
            wal_bytes=100,
            buffers={"hits": 10},
        )
        for q in WORKLOAD_QUERIES
    )
    report = seal_workload(
        corpus_facts=MIN_REPRESENTATIVE_FACTS,
        incremental_churn=10_000,
        evidence=evidence,
        candidate=candidate,
        current_rows=MIN_REPRESENTATIVE_FACTS,
        disk_wal_budget={"disk_gb": 200, "wal_gb": 20},
        rollback_rehearsed=True,
    )
    assert report["seal"] == "PROVEN"
    assert report["claim_nacional_physical_design_proven"] is True
    replay = seal_workload(
        corpus_facts=MIN_REPRESENTATIVE_FACTS,
        incremental_churn=10_000,
        evidence=evidence,
        candidate=candidate,
        current_rows=MIN_REPRESENTATIVE_FACTS,
        disk_wal_budget={"disk_gb": 200, "wal_gb": 20},
        rollback_rehearsed=True,
    )
    assert replay["contract_hash"] == report["contract_hash"]
    assert report["rollback_rehearsed"] is True
    assert report["disk_wal_budget"] == {"disk_gb": 200, "wal_gb": 20}
    assert {row["query_id"] for row in report["evidence"]} == {q["id"] for q in WORKLOAD_QUERIES}


def test_wal_required_and_evidence_binds_contract_hash() -> None:
    candidate = DesignCandidate(
        name="range_partition_month",
        partitioning="range(source_event_date)",
        pk_type="BIGSERIAL",
        notes="decision pending cost comparison",
    )
    missing_wal = tuple(
        WorkloadEvidence(
            query_id=q["id"],
            explain_analyze="Index Scan",
            p50_ms=5.0,
            p95_ms=12.0,
            p99_ms=20.0,
            wal_bytes=None,
        )
        for q in WORKLOAD_QUERIES
    )
    unproven = seal_workload(
        corpus_facts=MIN_REPRESENTATIVE_FACTS,
        incremental_churn=10_000,
        evidence=missing_wal,
        candidate=candidate,
        current_rows=MIN_REPRESENTATIVE_FACTS,
        disk_wal_budget={"disk_gb": 200, "wal_gb": 20},
        rollback_rehearsed=True,
    )
    assert unproven["seal"] == "UNPROVEN"
    assert any(b.startswith("incomplete_metrics") for b in unproven["blockers"])

    empty_budget = seal_workload(
        corpus_facts=MIN_REPRESENTATIVE_FACTS,
        incremental_churn=10_000,
        evidence=tuple(
            WorkloadEvidence(
                query_id=q["id"],
                explain_analyze="Index Scan",
                p50_ms=5.0,
                p95_ms=12.0,
                p99_ms=20.0,
                wal_bytes=100,
            )
            for q in WORKLOAD_QUERIES
        ),
        candidate=candidate,
        current_rows=MIN_REPRESENTATIVE_FACTS,
        disk_wal_budget={},
        rollback_rehearsed=True,
    )
    assert empty_budget["seal"] == "UNPROVEN"
    assert "disk_wal_budget_unrecorded" in empty_budget["blockers"]

    def _full(explain: str, p50: float) -> tuple[WorkloadEvidence, ...]:
        return tuple(
            WorkloadEvidence(
                query_id=q["id"],
                explain_analyze=explain,
                p50_ms=p50,
                p95_ms=12.0,
                p99_ms=20.0,
                wal_bytes=100,
            )
            for q in WORKLOAD_QUERIES
        )

    index_scan = seal_workload(
        corpus_facts=MIN_REPRESENTATIVE_FACTS,
        incremental_churn=10_000,
        evidence=_full("Index Scan", 5.0),
        candidate=candidate,
        current_rows=MIN_REPRESENTATIVE_FACTS,
        disk_wal_budget={"disk_gb": 200, "wal_gb": 20},
        rollback_rehearsed=True,
    )
    seq_scan = seal_workload(
        corpus_facts=MIN_REPRESENTATIVE_FACTS,
        incremental_churn=10_000,
        evidence=_full("Seq Scan", 30_000.0),
        candidate=candidate,
        current_rows=MIN_REPRESENTATIVE_FACTS,
        disk_wal_budget={"disk_gb": 200, "wal_gb": 20},
        rollback_rehearsed=True,
    )
    assert index_scan["seal"] == seq_scan["seal"] == "PROVEN"
    assert index_scan["contract_hash"] != seq_scan["contract_hash"]

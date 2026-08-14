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

"""Fail-closed and operational tests for the resumable #302 census."""

from __future__ import annotations

import json
import urllib.error
from email.message import Message
from pathlib import Path

import pytest

from scripts.crawl.resilience.circuit_breaker import PersistentCircuitBreaker
from scripts.crawl.resilience.http_policy import HttpResiliencePolicy
from scripts.national_coverage.census import (
    CATALOG_SCHEMA,
    CensusOperationError,
    _CheckpointLock,
    _corpus_publishers_from_rows,
    build_catalog_inventory,
    build_corpus_snapshot,
    build_window_evidence,
    fetch_catalog_bytes,
    load_catalog_bundle,
    publish_catalog_bundle,
    run_census,
    sha256_bytes,
)


def _raw_catalog() -> bytes:
    return json.dumps(
        [
            {"cnpj": "33333333000191", "razaoSocial": "C", "statusAtivo": True},
            {"cnpj": "11111111000191", "razaoSocial": "A", "statusAtivo": True},
            {"cnpj": "22222222000191", "razaoSocial": "B", "statusAtivo": False},
        ]
    ).encode()


def _checkpoint(path: Path, completed: list[str], **extra: object) -> Path:
    supplied_meta = extra.pop("meta", {})
    assert isinstance(supplied_meta, dict)
    path.write_text(
        json.dumps(
            {
                "source": "pncp_contracts",
                "mode": "full",
                "completed_windows": completed,
                "updated_at": "2026-08-29T00:00:00Z",
                "meta": {
                    "capability": "historical_contracts",
                    "query_kind": "publication",
                    **supplied_meta,
                },
                **extra,
            }
        ),
        encoding="utf-8",
    )
    return path


def _corpus() -> dict:
    return build_corpus_snapshot(
        [
            {
                "org_id": "11111111000191",
                "contract_count": 4,
                "first_seen": "2026-01-01T01:00:00Z",
                "last_seen": "2026-01-02T23:00:00Z",
            }
        ],
        period_start="2026-01-01",
        period_end_exclusive="2026-01-03",
        retrieved_at="2026-01-03T00:00:00Z",
    )


def test_catalog_inventory_is_canonical_and_refuses_partial_json() -> None:
    inventory, orgs = build_catalog_inventory(
        _raw_catalog(),
        competence="contracts-2026-01",
        cutoff="2026-01-02",
        retrieved_at="2026-01-03T00:00:00Z",
    )
    assert inventory["schema_version"] == CATALOG_SCHEMA
    assert inventory["org_count"] == 3
    assert inventory["unique_org_count"] == 3
    assert inventory["active_org_count"] == 2
    assert inventory["unit_count"] is None
    assert inventory["transport_body_complete"] is True
    assert inventory["catalog_completeness_proven"] is False
    assert [item["org_id"] for item in orgs] == sorted(item["org_id"] for item in orgs)
    with pytest.raises(CensusOperationError, match="catalog_invalid_or_truncated"):
        build_catalog_inventory(
            _raw_catalog()[:-1],
            competence="contracts-2026-01",
            cutoff="2026-01-02",
            retrieved_at="2026-01-03T00:00:00Z",
        )


def test_catalog_duplicate_and_invalid_cnpj_fail_closed() -> None:
    duplicate = json.dumps(
        [
            {"cnpj": "11.111.111/0001-91", "razaoSocial": "A"},
            {"cnpj": "11111111000191", "razaoSocial": "A2"},
        ]
    ).encode()
    with pytest.raises(CensusOperationError, match="catalog_duplicate_cnpj"):
        build_catalog_inventory(
            duplicate,
            competence="x",
            cutoff="2026-01-01",
            retrieved_at="2026-01-02T00:00:00Z",
        )
    invalid = json.dumps([{"cnpj": "123", "razaoSocial": "X"}]).encode()
    with pytest.raises(CensusOperationError, match="catalog_invalid_cnpj"):
        build_catalog_inventory(
            invalid,
            competence="x",
            cutoff="2026-01-01",
            retrieved_at="2026-01-02T00:00:00Z",
        )


def test_catalog_hash_is_deterministic_across_source_order() -> None:
    raw = json.loads(_raw_catalog())
    first, _ = build_catalog_inventory(
        json.dumps(raw).encode(),
        competence="x",
        cutoff="2026-01-01",
        retrieved_at="2026-01-02T00:00:00Z",
    )
    second, _ = build_catalog_inventory(
        json.dumps(list(reversed(raw))).encode(),
        competence="x",
        cutoff="2026-01-01",
        retrieved_at="2026-01-02T00:00:00Z",
    )
    assert first["catalog_hash"] == second["catalog_hash"]
    assert first["national_universe_id"] == second["national_universe_id"]
    assert first["raw_sha256"] != second["raw_sha256"]


def test_catalog_bundle_is_content_addressed_and_manifest_bound(tmp_path: Path) -> None:
    raw = _raw_catalog()
    inventory, _ = build_catalog_inventory(
        raw,
        competence="contracts-2026-01",
        cutoff="2026-01-02",
        retrieved_at="2026-01-03T00:00:00Z",
        raw_artifact=f"catalog.{sha256_bytes(raw)[:16]}.json",
    )
    manifest = tmp_path / "catalog.manifest.json"
    versioned = publish_catalog_bundle(
        out_raw=tmp_path / "catalog.json",
        out_manifest=manifest,
        raw=raw,
        inventory=inventory,
    )
    loaded_raw, loaded_manifest = load_catalog_bundle(manifest)
    assert loaded_raw == raw
    assert loaded_manifest["raw_artifact"] == versioned.name
    assert versioned.name.startswith("catalog.")

    lkg = manifest.read_bytes()
    with pytest.raises(CensusOperationError, match="catalog_bundle_inventory_mismatch"):
        publish_catalog_bundle(
            out_raw=tmp_path / "catalog.json",
            out_manifest=manifest,
            raw=raw,
            inventory={**inventory, "retrieved_at": "2026-08-29T00:00:00Z"},
        )
    assert manifest.read_bytes() == lkg

    tampered = {**loaded_manifest, "retrieved_at": "2026-08-29T00:00:00Z"}
    manifest.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(CensusOperationError, match="catalog_manifest_reconciliation_mismatch"):
        load_catalog_bundle(manifest)

    with pytest.raises(CensusOperationError, match="catalog_bundle_paths_must_share_directory"):
        publish_catalog_bundle(
            out_raw=tmp_path / "raw" / "catalog.json",
            out_manifest=tmp_path / "manifest" / "catalog.manifest.json",
            raw=raw,
            inventory=inventory,
        )


def test_corpus_snapshot_hash_binds_retrieval_time() -> None:
    first = _corpus()
    later = build_corpus_snapshot(
        first["publishers"],
        period_start=first["period_start"],
        period_end_exclusive=first["period_end_exclusive"],
        retrieved_at="2026-01-04T00:00:00Z",
    )
    assert first["snapshot_hash"] != later["snapshot_hash"]


def test_corpus_snapshot_refuses_unmappable_identity_rows() -> None:
    with pytest.raises(CensusOperationError, match="corpus_unmappable_identity_rows:groups=1:contracts=7"):
        _corpus_publishers_from_rows([("", 7, None, None)])


def test_window_union_is_day_exact_and_completed_overrides_old_failure(tmp_path: Path) -> None:
    first = _checkpoint(
        tmp_path / "first.json",
        ["20260101_20260101"],
        failed_windows=["20260102_20260102"],
    )
    second = _checkpoint(tmp_path / "second.json", ["20260102_20260102"])
    evidence = build_window_evidence(
        [first, second],
        period_start="2026-01-01",
        period_end_exclusive="2026-01-03",
    )
    assert evidence["complete"] is True
    assert evidence["covered_days"] == 2
    assert evidence["failed_dates"] == []
    assert evidence["not_consulted_dates"] == []


def test_window_evidence_reports_failed_blocked_and_never_ran(tmp_path: Path) -> None:
    checkpoint = _checkpoint(
        tmp_path / "checkpoint.json",
        ["20260101_20260101"],
        failed_windows=["20260102_20260102"],
        blocked_windows=["20260103_20260103"],
    )
    evidence = build_window_evidence(
        [checkpoint],
        period_start="2026-01-01",
        period_end_exclusive="2026-01-05",
    )
    assert evidence["complete"] is False
    assert evidence["failed_dates"] == ["2026-01-02"]
    assert evidence["blocked_dates"] == ["2026-01-03"]
    assert evidence["not_consulted_dates"] == ["2026-01-04"]


def test_resume_is_idempotent_and_source_wide_windows_never_prove_entity_zero(tmp_path: Path) -> None:
    source_checkpoint = _checkpoint(tmp_path / "source.json", ["20260101_20260102"])
    windows = build_window_evidence(
        [source_checkpoint],
        period_start="2026-01-01",
        period_end_exclusive="2026-01-03",
    )
    operation_checkpoint = tmp_path / "census.json"
    first = run_census(
        catalog_raw=_raw_catalog(),
        catalog_retrieved_at="2026-01-03T00:00:00Z",
        corpus=_corpus(),
        window_evidence=windows,
        competence="contracts-2026-01",
        checkpoint_path=operation_checkpoint,
        batch_size=1,
        max_partitions=2,
    )
    assert first["partitions"]["by_status"] == {
        "FOUND": 1,
        "ZERO_CONFIRMED": 0,
        "BLOCKED": 2,
        "FAILED": 0,
        "NOT_APPLICABLE": 0,
    }
    assert first["national_claim_authorized"] is False
    assert first["census_operation"]["queue"]["remaining"] == 1
    assert first["universe"]["expected_units"] is None
    assert "publishing_unit_denominator_not_enumerated" in first["consumer"]["limitations"]

    resumed = run_census(
        catalog_raw=_raw_catalog(),
        catalog_retrieved_at="2026-01-03T00:00:00Z",
        corpus=_corpus(),
        window_evidence=windows,
        competence="contracts-2026-01",
        checkpoint_path=operation_checkpoint,
        batch_size=2,
    )
    assert resumed["partitions"]["by_status"]["FOUND"] == 1
    assert resumed["partitions"]["by_status"]["ZERO_CONFIRMED"] == 0
    assert resumed["partitions"]["by_status"]["BLOCKED"] == 2
    assert resumed["national_claim_authorized"] is False
    assert resumed["consumer"]["national_claim_allowed"] is False
    assert "source_wide_aggregate_without_identity" in resumed["reason_codes"]
    assert resumed["reconciliation_hash"] == resumed["consumer"]["provenance"]["reconciliation_hash"]

    replay = run_census(
        catalog_raw=_raw_catalog(),
        catalog_retrieved_at="2026-01-03T00:00:00Z",
        corpus=_corpus(),
        window_evidence=windows,
        competence="contracts-2026-01",
        checkpoint_path=operation_checkpoint,
    )
    assert replay["census_operation"]["processed_this_run"] == 0
    assert replay["reconciliation_hash"] == resumed["reconciliation_hash"]
    assert replay["consumer"]["content_hash"] == resumed["consumer"]["content_hash"]


def test_incomplete_source_never_infers_zero_or_entity_query_failure(tmp_path: Path) -> None:
    incomplete = _checkpoint(tmp_path / "incomplete.json", ["20260101_20260101"])
    incomplete_windows = build_window_evidence(
        [incomplete],
        period_start="2026-01-01",
        period_end_exclusive="2026-01-03",
    )
    report = run_census(
        catalog_raw=_raw_catalog(),
        catalog_retrieved_at="2026-01-03T00:00:00Z",
        corpus=_corpus(),
        window_evidence=incomplete_windows,
        competence="contracts-2026-01",
        checkpoint_path=tmp_path / "blocked-census.json",
    )
    assert report["partitions"]["by_status"]["FOUND"] == 1
    assert report["partitions"]["by_status"]["ZERO_CONFIRMED"] == 0
    assert report["partitions"]["by_status"]["BLOCKED"] == 2
    assert report["national_claim_authorized"] is False

    failed = _checkpoint(
        tmp_path / "failed.json",
        ["20260101_20260101"],
        failed_windows=["20260102_20260102"],
    )
    failed_windows = build_window_evidence(
        [failed],
        period_start="2026-01-01",
        period_end_exclusive="2026-01-03",
    )
    failed_report = run_census(
        catalog_raw=_raw_catalog(),
        catalog_retrieved_at="2026-01-03T00:00:00Z",
        corpus=_corpus(),
        window_evidence=failed_windows,
        competence="contracts-2026-01",
        checkpoint_path=tmp_path / "failed-census.json",
    )
    assert failed_report["partitions"]["by_status"]["ZERO_CONFIRMED"] == 0
    assert failed_report["partitions"]["by_status"]["FAILED"] == 0
    assert failed_report["partitions"]["by_status"]["BLOCKED"] == 2
    assert "source_windows_failed" in failed_report["reason_codes"]


def test_direct_forged_window_or_corpus_input_cannot_authorize(tmp_path: Path) -> None:
    source = _checkpoint(tmp_path / "source.json", ["20260101_20260102"])
    windows = build_window_evidence([source], period_start="2026-01-01", period_end_exclusive="2026-01-03")
    forged_windows = {**windows, "complete": False}
    with pytest.raises(CensusOperationError, match="window_evidence_hash_mismatch"):
        run_census(
            catalog_raw=_raw_catalog(),
            catalog_retrieved_at="2026-01-03T00:00:00Z",
            corpus=_corpus(),
            window_evidence=forged_windows,
            competence="contracts-2026-01",
            checkpoint_path=tmp_path / "forged-window.json",
        )
    forged_corpus = {**_corpus(), "contract_count": 999}
    with pytest.raises(CensusOperationError, match="corpus_snapshot_reconciliation_mismatch"):
        run_census(
            catalog_raw=_raw_catalog(),
            catalog_retrieved_at="2026-01-03T00:00:00Z",
            corpus=forged_corpus,
            window_evidence=windows,
            competence="contracts-2026-01",
            checkpoint_path=tmp_path / "forged-corpus.json",
        )
    noncanonical_corpus = {**_corpus(), "source": "parallel_datalake"}
    with pytest.raises(CensusOperationError, match="corpus_source_not_canonical"):
        run_census(
            catalog_raw=_raw_catalog(),
            catalog_retrieved_at="2026-01-03T00:00:00Z",
            corpus=noncanonical_corpus,
            window_evidence=windows,
            competence="contracts-2026-01",
            checkpoint_path=tmp_path / "wrong-source.json",
        )


def test_checkpoint_input_change_and_corruption_fail_closed(tmp_path: Path) -> None:
    source = _checkpoint(tmp_path / "source.json", ["20260101_20260102"])
    windows = build_window_evidence([source], period_start="2026-01-01", period_end_exclusive="2026-01-03")
    checkpoint = tmp_path / "operation.json"
    run_census(
        catalog_raw=_raw_catalog(),
        catalog_retrieved_at="2026-01-03T00:00:00Z",
        corpus=_corpus(),
        window_evidence=windows,
        competence="contracts-2026-01",
        checkpoint_path=checkpoint,
        max_partitions=1,
    )
    changed_corpus = build_corpus_snapshot(
        [{"org_id": "11111111000191", "contract_count": 5, "last_seen": "2026-01-02T23:00:00Z"}],
        period_start="2026-01-01",
        period_end_exclusive="2026-01-03",
        retrieved_at="2026-01-03T00:00:00Z",
    )
    with pytest.raises(CensusOperationError, match="checkpoint_input_hash_mismatch"):
        run_census(
            catalog_raw=_raw_catalog(),
            catalog_retrieved_at="2026-01-03T00:00:00Z",
            corpus=changed_corpus,
            window_evidence=windows,
            competence="contracts-2026-01",
            checkpoint_path=checkpoint,
        )
    checkpoint.write_text("{", encoding="utf-8")
    with pytest.raises(CensusOperationError, match="invalid_json"):
        run_census(
            catalog_raw=_raw_catalog(),
            catalog_retrieved_at="2026-01-03T00:00:00Z",
            corpus=_corpus(),
            window_evidence=windows,
            competence="contracts-2026-01",
            checkpoint_path=checkpoint,
        )


def test_checkpoint_terminal_status_is_rederived_from_bound_inputs(tmp_path: Path) -> None:
    source = _checkpoint(tmp_path / "source.json", ["20260101_20260102"])
    windows = build_window_evidence([source], period_start="2026-01-01", period_end_exclusive="2026-01-03")
    checkpoint = tmp_path / "operation.json"
    run_census(
        catalog_raw=_raw_catalog(),
        catalog_retrieved_at="2026-01-03T00:00:00Z",
        corpus=_corpus(),
        window_evidence=windows,
        competence="contracts-2026-01",
        checkpoint_path=checkpoint,
        max_partitions=1,
    )
    forged = json.loads(checkpoint.read_text(encoding="utf-8"))
    forged["terminal_by_status"]["FOUND"] = []
    forged["terminal_by_status"]["ZERO_CONFIRMED"] = ["11111111000191"]
    checkpoint.write_text(json.dumps(forged), encoding="utf-8")

    with pytest.raises(CensusOperationError, match="checkpoint_partition_status_mismatch"):
        run_census(
            catalog_raw=_raw_catalog(),
            catalog_retrieved_at="2026-01-03T00:00:00Z",
            corpus=_corpus(),
            window_evidence=windows,
            competence="contracts-2026-01",
            checkpoint_path=checkpoint,
        )


def test_update_date_checkpoint_cannot_prove_publication_date_window(tmp_path: Path) -> None:
    checkpoint = _checkpoint(
        tmp_path / "update.json",
        ["20260101_20260102"],
        meta={
            "logical_job_id": "pncp-contracts-incremental",
            "capability": "historical_contracts",
            "query_kind": "update",
        },
    )
    with pytest.raises(CensusOperationError, match="checkpoint_query_kind_mismatch"):
        build_window_evidence(
            [checkpoint],
            period_start="2026-01-01",
            period_end_exclusive="2026-01-03",
        )


def test_checkpoint_without_explicit_query_semantics_is_rejected(tmp_path: Path) -> None:
    checkpoint = tmp_path / "legacy.json"
    checkpoint.write_text(
        json.dumps(
            {
                "source": "pncp_contracts",
                "mode": "full",
                "completed_windows": ["20260101_20260102"],
                "meta": {"capability": "historical_contracts"},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(CensusOperationError, match="checkpoint_query_kind_mismatch"):
        build_window_evidence(
            [checkpoint],
            period_start="2026-01-01",
            period_end_exclusive="2026-01-03",
        )


def test_checkpoint_claim_refuses_parallel_worker(tmp_path: Path) -> None:
    checkpoint = tmp_path / "operation.json"
    with _CheckpointLock(checkpoint):
        with pytest.raises(CensusOperationError, match="already_claimed"):
            with _CheckpointLock(checkpoint):
                pass


class _Response:
    def __init__(self, raw: bytes):
        self.raw = raw
        self.status = 200
        self.headers = {"Date": "Sat, 29 Aug 2026 21:12:05 GMT"}
        self.offset = 0

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, size: int) -> bytes:
        chunk = self.raw[self.offset : self.offset + size]
        self.offset += len(chunk)
        return chunk


def _breaker(tmp_path: Path) -> PersistentCircuitBreaker:
    return PersistentCircuitBreaker(
        tmp_path,
        environment="test",
        source="pncp",
        route="catalog",
        threshold=5,
        cooldown_seconds=1,
    )


def test_fetch_retries_429_5xx_and_timeout_with_bounded_budget(tmp_path: Path) -> None:
    policy = HttpResiliencePolicy(max_retries=3, base_delay=0, max_delay=0, jitter=0)
    headers = Message()
    headers["Retry-After"] = "0"
    outcomes: list[object] = [
        urllib.error.HTTPError("https://pncp.gov.br", 429, "rate", headers, None),
        urllib.error.HTTPError("https://pncp.gov.br", 503, "down", Message(), None),
        TimeoutError("slow"),
        _Response(_raw_catalog()),
    ]
    sleeps: list[float] = []

    def opener(*_args: object, **_kwargs: object) -> object:
        outcome = outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    raw, metadata = fetch_catalog_bytes(
        policy=policy,
        breaker=_breaker(tmp_path),
        opener=opener,
        sleeper=sleeps.append,
    )
    assert raw == _raw_catalog()
    assert metadata["request_count"] == 4
    assert metadata["concurrency"] == 1
    assert [item["classification"] for item in metadata["attempts"]] == [
        "rate_limited",
        "server_error",
        "timeout",
        "success",
    ]
    assert len(sleeps) == 3


def test_fetch_does_not_retry_permanent_4xx(tmp_path: Path) -> None:
    policy = HttpResiliencePolicy(max_retries=5, base_delay=0, max_delay=0, jitter=0)

    def opener(*_args: object, **_kwargs: object) -> object:
        raise urllib.error.HTTPError("https://pncp.gov.br", 404, "missing", Message(), None)

    with pytest.raises(CensusOperationError, match="http_404:client_error"):
        fetch_catalog_bytes(policy=policy, breaker=_breaker(tmp_path), opener=opener)

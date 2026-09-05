"""PNCP live health is acquisition telemetry; the datalake is the authority.

These are the end-to-end assertions for the decoupling: a degraded source must
not suppress commercial operation over data already persisted and proven, while
every datalake, membership and accountability gate stays fail-closed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.confenge_activation.commercial_authority import source_health_attestation_present
from scripts.confenge_outreach_pipeline.pipeline import _published_target_fit_snapshot

DEGRADED_STATUSES = ("STALE", "UNKNOWN", "DEGRADED")


class _FakeConnection:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _healthy_coverage() -> dict[str, object]:
    return {
        "coverage_ratio": 1.0,
        "pagination_exhausted_normally": True,
        "last_full_reconcile_unexplained_missing": 0,
        "last_full_reconcile_completed_at": "2026-08-25T02:45:00Z",
    }


def _wire(
    monkeypatch,
    *,
    coverage: dict[str, object],
    queue: dict[str, int],
    cdc_watermark: str | None = "2026-08-24T03:26:43Z",
) -> _FakeConnection:
    import scripts.confenge_outreach_pipeline.pipeline as pipeline
    import scripts.confenge_target_fit.db as target_fit_db

    conn = _FakeConnection()
    monkeypatch.setattr(target_fit_db, "connect", lambda dsn, readonly: conn)
    monkeypatch.setattr(
        pipeline,
        "load_published_index",
        lambda connection, cnpj14s: {
            "11222333": {
                "cnpj_raiz": "11222333",
                "company_key": "cnpj_root:11222333",
                "target_fit_class": "TARGET_CONFIRMED",
                "source_watermark": "2026-08-16T08:30:23Z",
            }
        },
    )
    monkeypatch.setattr(
        pipeline,
        "get_control",
        lambda connection, key: ({"watermark": cdc_watermark} if key == "cdc_watermark" else coverage),
    )
    monkeypatch.setattr(pipeline, "queue_counts", lambda connection: queue)
    return conn


@pytest.mark.parametrize("status", DEGRADED_STATUSES)
def test_a_degraded_source_still_yields_the_persisted_population(status: str, monkeypatch) -> None:
    conn = _wire(monkeypatch, coverage=_healthy_coverage(), queue={"done": 407_513})

    snapshot, authority, watermark = _published_target_fit_snapshot(
        [{"cnpj14": "11222333000181"}],
        dsn="postgresql://unused",
        authoritative_source_freshness={
            "contract_version": "PNCP_CONTRACT_FRESHNESS/1.0",
            "status": status,
            "reason_codes": ["SOURCE_WINDOW_NOT_CLOSED"],
        },
    )

    assert conn.closed is True
    assert authority == "published_target_fit_store"
    assert [row["cnpj_raiz"] for row in snapshot] == ["11222333"]
    # No live observation to project: the decision keeps its own evidence
    # watermark and the datalake CDC watermark stands. Nothing is fabricated.
    assert watermark == "2026-08-24T03:26:43Z"
    assert snapshot[0]["source_watermark"] == "2026-08-16T08:30:23Z"
    assert "target_fit_observation_run_id" not in snapshot[0]


def test_an_unreachable_source_is_indistinguishable_from_a_degraded_one(monkeypatch) -> None:
    """No freshness envelope at all must behave exactly like a degraded source."""
    _wire(monkeypatch, coverage=_healthy_coverage(), queue={"done": 407_513})

    snapshot, authority, _ = _published_target_fit_snapshot(
        [{"cnpj14": "11222333000181"}],
        dsn="postgresql://unused",
    )

    assert authority == "published_target_fit_store"
    assert [row["cnpj_raiz"] for row in snapshot] == ["11222333"]


@pytest.mark.parametrize(
    "source_observed_at",
    [
        "2026-08-25T02:42:00Z",  # before the persisted full reconcile
        "2026-08-25T02:45:00Z",  # equal to the persisted full reconcile
        "2026-08-25T02:50:00Z",  # after the persisted full reconcile
        "2026-08-25T02:42:00",  # timezone-naive telemetry must not gate it
        "",  # absent telemetry must not gate the persisted snapshot
        "not-a-timestamp",  # malformed telemetry must not gate it either
    ],
)
def test_source_telemetry_never_rewrites_persisted_binding(
    source_observed_at: str,
    monkeypatch,
) -> None:
    """PNCP freshness is telemetry, never persisted binding provenance."""
    _wire(monkeypatch, coverage=_healthy_coverage(), queue={"done": 407_513})

    snapshot, _, watermark = _published_target_fit_snapshot(
        [{"cnpj14": "11222333000181"}],
        dsn="postgresql://unused",
        authoritative_source_freshness={
            "contract_version": "PNCP_CONTRACT_FRESHNESS/1.0",
            "status": "FRESH",
            "source_observed_at": source_observed_at,
            "run_id": "contracts-live-1",
        },
    )

    assert watermark == "2026-08-24T03:26:43Z"
    assert snapshot[0]["source_watermark"] == "2026-08-16T08:30:23Z"
    assert "target_fit_evidence_watermark" not in snapshot[0]
    assert "target_fit_observation_run_id" not in snapshot[0]


@pytest.mark.parametrize("cdc_watermark", [None, "", "   "])
def test_a_missing_persisted_cdc_watermark_fails_closed(cdc_watermark: str | None, monkeypatch) -> None:
    _wire(
        monkeypatch,
        coverage=_healthy_coverage(),
        queue={"done": 407_513},
        cdc_watermark=cdc_watermark,
    )

    with pytest.raises(ValueError, match="persisted CDC watermark is missing"):
        _published_target_fit_snapshot(
            [{"cnpj14": "11222333000181"}],
            dsn="postgresql://unused",
            authoritative_source_freshness={
                "contract_version": "PNCP_CONTRACT_FRESHNESS/1.0",
                "status": "FRESH",
                "source_observed_at": "2026-08-25T02:42:00Z",
            },
        )


@pytest.mark.parametrize("status", [*DEGRADED_STATUSES, "FRESH"])
@pytest.mark.parametrize(
    ("coverage_patch", "queue", "expected"),
    [
        ({"coverage_ratio": 0.97}, {"done": 1}, "national coverage is incomplete"),
        ({"last_full_reconcile_unexplained_missing": 3}, {"done": 1}, "national coverage is incomplete"),
        ({"pagination_exhausted_normally": False}, {"done": 1}, "national coverage is incomplete"),
        ({}, {"pending": 1}, "unresolved queue items"),
        ({"last_full_reconcile_completed_at": ""}, {"done": 1}, "full-reconcile observation is missing"),
    ],
)
def test_an_invalid_datalake_fails_closed_whatever_the_source_is_doing(
    status: str,
    coverage_patch: dict[str, object],
    queue: dict[str, int],
    expected: str,
    monkeypatch,
) -> None:
    """Datalake integrity is the real gate and it never depends on PNCP health."""
    _wire(monkeypatch, coverage={**_healthy_coverage(), **coverage_patch}, queue=queue)
    freshness: dict[str, object] = {
        "contract_version": "PNCP_CONTRACT_FRESHNESS/1.0",
        "status": status,
    }
    if status == "FRESH":
        freshness["source_observed_at"] = "2026-08-25T02:42:00Z"

    with pytest.raises(ValueError, match=expected):
        _published_target_fit_snapshot(
            [{"cnpj14": "11222333000181"}],
            dsn="postgresql://unused",
            authoritative_source_freshness=freshness,
        )


def test_a_naive_full_reconcile_timestamp_fails_closed(monkeypatch) -> None:
    """An unanchored reconcile timestamp cannot be compared, so it cannot pass."""
    _wire(
        monkeypatch,
        coverage={**_healthy_coverage(), "last_full_reconcile_completed_at": "2026-08-25T02:45:00"},
        queue={"done": 407_513},
    )

    with pytest.raises(ValueError, match="must be timezone-aware"):
        _published_target_fit_snapshot(
            [{"cnpj14": "11222333000181"}],
            dsn="postgresql://unused",
            authoritative_source_freshness={
                "contract_version": "PNCP_CONTRACT_FRESHNESS/1.0",
                "status": "STALE",
            },
        )


@pytest.mark.parametrize("status", DEGRADED_STATUSES)
def test_a_degraded_attestation_is_accountable_but_not_authorising(status: str) -> None:
    source_health_attestation_present({"contract_version": "PNCP_CONTRACT_FRESHNESS/1.0", "status": status})


@pytest.mark.parametrize(
    "envelope",
    [None, {}, {"status": "FRESH"}, {"contract_version": "BOGUS/9", "status": "FRESH"}],
)
def test_an_unaccountable_attestation_is_still_refused(envelope: dict[str, object] | None) -> None:
    with pytest.raises(ValueError):
        source_health_attestation_present(envelope)


def test_the_cli_reports_an_unreachable_probe_as_unknown_and_keeps_going(monkeypatch, tmp_path: Path) -> None:
    """A 503/exception from the probe must degrade telemetry, never the run."""
    import scripts.ops.pncp_contract_freshness as freshness_module
    from scripts.confenge_outreach_pipeline import cli

    def explode(*args, **kwargs):
        raise ConnectionError("PNCP returned 503")

    monkeypatch.setattr(freshness_module, "collect_snapshot", explode)
    monkeypatch.setenv("LOCAL_DATALAKE_DSN", "postgresql://unused")

    captured: dict[str, object] = {}

    def fake_run_pipeline(cfg):
        captured["freshness"] = cfg.authoritative_source_freshness
        raise SystemExit(0)

    monkeypatch.setattr(cli, "run_pipeline", fake_run_pipeline)
    with pytest.raises(SystemExit):
        cli.main(["run", "--out", str(tmp_path / "out"), "--skip-universe"])

    observed = captured["freshness"]
    assert isinstance(observed, dict)
    assert observed["status"] == "UNKNOWN"
    assert observed["reason_codes"] == ["PNCP_TELEMETRY_UNAVAILABLE"]
    assert observed["contract_version"] == "PNCP_CONTRACT_FRESHNESS/1.0"

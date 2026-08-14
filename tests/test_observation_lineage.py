"""Tests for #305 persist-time contract observation lineage."""

from __future__ import annotations

import pytest

from scripts.contracts_truth import annotate_transformed_contract
from scripts.crawl.observation_lineage import (
    Lineage,
    LineageError,
    Observation,
    persist_observations,
    reconcile_page_window,
    sha256_bytes,
    sha256_payload,
)


def _lineage(**overrides: object) -> Lineage:
    base: dict[str, object] = {
        "run_id": "run-1",
        "attempt_id": "att-1",
        "window_start": "2026-01-01",
        "window_end": "2026-01-07",
        "page": 2,
        "official_url": "https://pncp.gov.br/api/consulta/v1/contratos?pagina=2",
        "raw_uri": "cas://raw/abc",
        "raw_sha256": sha256_bytes(b"page-2-body"),
    }
    base.update(overrides)
    return Lineage(**base)  # type: ignore[arg-type]


def test_annotate_attaches_non_null_lineage_from_envelope() -> None:
    raw_body = b'{"numeroControlePNCP":"x","pagina":2}'
    raw = {
        "situacaoContrato": "Vigente",
        "numeroControlePNCP": "SC-1",
        "run_id": "run-9",
        "attempt_id": "att-3",
        "query_window_start": "2026-02-01",
        "query_window_end": "2026-02-02",
        "page": 4,
        "official_url": "https://pncp.gov.br/api/consulta/v1/contratos?pagina=4",
        "raw_uri": "cas://raw/page4",
        "raw_sha256": sha256_bytes(raw_body),
        "_raw_bytes": raw_body,
    }
    record = annotate_transformed_contract(
        {
            "contrato_id": "SC-1",
            "data_inicio": "2026-01-01",
            "data_fim": "2026-12-31",
            "source": "pncp",
        },
        raw=raw,
    )
    assert record["run_id"] == "run-9"
    assert record["attempt_id"] == "att-3"
    assert record["window_start"] == "2026-02-01"
    assert record["window_end"] == "2026-02-02"
    assert record["page"] == 4
    assert record["official_url"].endswith("pagina=4")
    assert record["raw_uri"] == "cas://raw/page4"
    assert record["raw_sha256"] == sha256_bytes(raw_body)
    # Window/page coincide with the immutable HTTP envelope.
    assert record["window_start"] == raw["query_window_start"]
    assert record["page"] == raw["page"]


def test_missing_lineage_blocks_when_envelope_present() -> None:
    with pytest.raises(LineageError, match="missing_lineage"):
        annotate_transformed_contract(
            {"contrato_id": "SC-2", "source": "pncp"},
            raw={"run_id": "run-1", "page": 1},
        )


def test_upsert_preserves_every_occurrence() -> None:
    first = Observation("C1", _lineage(page=1), sha256_payload({"n": 1}))
    second = Observation("C1", _lineage(page=2, attempt_id="att-2"), sha256_payload({"n": 2}))
    stored = persist_observations((), (first,))
    stored = persist_observations(stored, (second,))
    assert len(stored) == 2
    assert [o.occurrence for o in stored] == [1, 2]
    assert stored[0].lineage.page == 1
    assert stored[1].lineage.page == 2
    assert stored[0].lineage.attempt_id == "att-1"
    assert stored[1].lineage.attempt_id == "att-2"


def test_page_window_fetched_equals_persisted_plus_rejected() -> None:
    closed = reconcile_page_window(
        fetched=10,
        persisted=7,
        rejected=3,
        window_start="2026-01-01",
        window_end="2026-01-07",
        page=3,
    )
    assert closed["closed"] is True
    assert closed["fetched"] == closed["persisted"] + closed["rejected"]
    with pytest.raises(LineageError, match="do_not_close"):
        reconcile_page_window(
            fetched=10,
            persisted=7,
            rejected=2,
            window_start="2026-01-01",
            window_end="2026-01-07",
            page=3,
        )

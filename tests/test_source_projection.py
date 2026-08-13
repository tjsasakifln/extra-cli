"""Tests for source-agnostic opportunity projection (#238)."""

from __future__ import annotations

from scripts.opportunity_intel.source_projection import (
    REASON_SOURCE_RENAMED_PNCP,
    Observation,
    Rejection,
    counts_by_source,
    project_raw,
    project_source_batch,
)


def _sc_raw(**overrides):
    row = {
        "source_id": "sc-2025/00001",
        "objeto": "Servico de limpeza predial",
        "orgao_cnpj": "12345678000199",
        "orgao_razao_social": "Secretaria de Estado da Saude",
        "municipio": "Florianopolis",
        "uf": "SC",
        "status": "aberto",
    }
    row.update(overrides)
    return row


def test_non_pncp_raw_becomes_observation_keeping_source_identity() -> None:
    obs = project_raw(_sc_raw(), source="sc_compras")
    assert isinstance(obs, Observation)
    assert obs.source == "sc_compras"
    assert obs.source_id == "sc-2025/00001"
    assert obs.identity == "sc_compras:sc-2025/00001"
    assert obs.source != "pncp"


def test_never_renames_source_as_pncp() -> None:
    rejected = project_raw(_sc_raw(rewrite_as_pncp=True), source="sc_compras")
    assert isinstance(rejected, Rejection)
    assert rejected.reason == REASON_SOURCE_RENAMED_PNCP
    ok = project_raw(_sc_raw(), source="compras_gov")
    assert isinstance(ok, Observation)
    assert ok.source == "compras_gov"


def test_fetched_equals_persisted_plus_rejected_with_reason() -> None:
    records = [
        _sc_raw(source_id="ok-1"),
        _sc_raw(source_id="ok-2"),
        _sc_raw(source_id="bad", objeto=""),
        {"municipio": "X"},
    ]
    batch = project_source_batch(records, source="sc_compras")
    assert batch.fetched == 4
    assert batch.balanced
    assert batch.fetched == len(batch.persisted) + len(batch.rejected)
    assert len(batch.rejected) == 2
    reasons = {r.reason for r in batch.rejected}
    assert "empty_object" in reasons
    assert "missing_identity" in reasons


def test_upsert_is_idempotent_and_terminal_updates_state() -> None:
    store: dict[tuple[str, str], Observation] = {}
    first = project_source_batch([_sc_raw(status="aberto")], source="sc_compras", store=store)
    second = project_source_batch([_sc_raw(status="revogado")], source="sc_compras", store=store)
    assert first.persisted[0].status == "aberto"
    assert second.persisted[0].status == "revogado"
    assert len(store) == 1
    assert store[("sc_compras", "sc-2025/00001")].status == "revogado"


def test_counts_by_source_keep_original_names() -> None:
    batches = [
        project_source_batch([_sc_raw()], source="sc_compras"),
        project_source_batch(
            [{"source_id": "p-1", "objeto": "obra", "orgao_cnpj": "1"}],
            source="pcp",
        ),
        project_source_batch([{"source_id": "x", "objeto": ""}], source="tce_sc"),
    ]
    counts = counts_by_source(batches)
    assert set(counts) == {"sc_compras", "pcp", "tce_sc"}
    assert "pncp" not in counts
    assert counts["sc_compras"]["persisted"] == 1
    assert counts["tce_sc"]["rejected"] == 1


def test_unsupported_source_is_rejected() -> None:
    result = project_raw(_sc_raw(), source="invented")
    assert isinstance(result, Rejection)
    assert result.reason == "unsupported_source"


def test_persistence_hook_projects_non_pncp() -> None:
    from types import SimpleNamespace

    from scripts.opportunity_intel.source_projection import attach_projection

    result = SimpleNamespace(opportunities_persisted=0, provenance={})
    attach_projection(result, [_sc_raw(), _sc_raw(source_id="bad", objeto="")], "sc_compras")
    assert result.opportunities_persisted == 1
    assert result.provenance["source_projection"]["source"] == "sc_compras"
    assert result.provenance["source_projection"]["rejected"] == 1


def test_transformer_normalizers_keep_declared_source() -> None:
    from scripts.opportunity_intel.transformer import normalize_record

    record = normalize_record(_sc_raw(), "sc_compras")
    assert record.source == "sc_compras"
    assert record.source_id == "sc-2025/00001"
    gov = normalize_record({"id": "cg-1", "objeto": "obra federal", "uf": "SC"}, "compras_gov")
    assert gov.source == "compras_gov"
    assert gov.source != "pncp"


def test_projection_invariant_holds_for_mixed_batch() -> None:
    batch = project_source_batch([_sc_raw(), _sc_raw(source_id="b", objeto="")], source="doe_sc")
    assert batch.balanced
    assert batch.fetched == 2
    assert len(batch.persisted) == 1
    assert len(batch.rejected) == 1

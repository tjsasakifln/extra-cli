"""Tests for #346 AlertaLicitação import + conservative reconcile + miss ranking.

Drives the shipped functions from a real start state (bytes → import → reconcile).
No hardcoded dump of the unit under test and no mocked SUT.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.coverage.alerta_miss_ranking import (
    PROVENANCE,
    AlertaImportError,
    ExtraRow,
    compute_import_id,
    import_alerta,
    reconcile,
    sha256_bytes,
)

FIXTURES = Path(__file__).parent / "fixtures" / "alerta_miss"
SNAPSHOT = FIXTURES / "snapshot-197.jsonl"


def _extra(*rows: dict) -> tuple[ExtraRow, ...]:
    return tuple(ExtraRow(**row) for row in rows)


def test_reimport_same_bytes_same_import_id_counts_and_hashes() -> None:
    raw = SNAPSHOT.read_bytes()
    first = import_alerta(raw, filename=SNAPSHOT.name, imported_at="2026-08-12T21:34:00Z")
    second = import_alerta(raw, filename=SNAPSHOT.name, imported_at="2026-08-14T00:00:00Z")
    assert first.import_id == second.import_id
    assert first.import_id == compute_import_id(file_sha256=sha256_bytes(raw))
    assert first.row_count == second.row_count == 10
    assert first.file_sha256 == second.file_sha256 == sha256_bytes(raw)
    assert first.content_hash == second.content_hash
    assert first.row_hashes == second.row_hashes
    assert first.imported_at != second.imported_at


def test_every_imported_row_keeps_identifier_url_and_provenance() -> None:
    imported = import_alerta(SNAPSHOT.read_bytes(), filename=SNAPSHOT.name)
    assert imported.row_count == len(imported.rows)
    for row in imported.rows:
        assert row.original_id
        assert row.provenance == PROVENANCE
        assert row.url  # fixture rows all carry a URL
        dumped = row.as_dict()
        assert dumped["original_id"] == row.original_id
        assert dumped["url"] == row.url
        assert dumped["provenance"] == PROVENANCE


def test_unknown_xls_layout_blocks_measurement() -> None:
    with pytest.raises(AlertaImportError, match="unknown or unsupported Excel layout"):
        import_alerta(b"not-a-real-xls", filename="alertaLicitacao-12082026-213400.xls")


def test_non_equivalent_window_is_fail_closed() -> None:
    imported = import_alerta(SNAPSHOT.read_bytes(), filename=SNAPSHOT.name)
    with pytest.raises(AlertaImportError, match="window"):
        reconcile(
            imported,
            (),
            window_start="2026-08-31",
            window_end="2026-08-01",
        )


def test_reconcile_states_cover_every_identity_and_totals_close() -> None:
    imported = import_alerta(SNAPSHOT.read_bytes(), filename=SNAPSHOT.name)
    extra = _extra(
        {
            "identity": "BOTH-001",
            "url": "https://pncp.gov.br/app/editais/001",
            "objeto": "Servico de limpeza",
            "ente": "Municipio de Florianopolis",
            "modalidade": "pregao",
            "published_at": "2026-08-06",
            "source_platform": "pncp",
        },
        {
            "identity": "DIFF-002",
            "url": "https://pncp.gov.br/app/editais/002",
            "objeto": "Objeto extra diferente",
            "ente": "Municipio de Sao Jose",
            "modalidade": "pregao",
            "published_at": "2026-08-07",
            "source_platform": "pncp",
        },
        {
            "identity": "EXTRA-009",
            "url": "https://pncp.gov.br/app/editais/009",
            "objeto": "Somente extra-cli",
            "ente": "Municipio de Itajai",
            "modalidade": "pregao",
            "published_at": "2026-08-10",
            "source_platform": "pncp",
        },
    )
    report = reconcile(
        imported,
        extra,
        window_start="2026-08-01",
        window_end="2026-08-12",
        filters={"uf": "SC", "profile": "confenge"},
        registered_sources=frozenset({"pncp", "ciga"}),
    )
    by_state = {d.identity: d.state for d in report.decisions}
    assert by_state["BOTH-001"] == "found_both"
    assert by_state["DIFF-002"] == "matched_with_difference"
    assert by_state["EXTRA-009"] == "extra_only"
    assert by_state["DUP-004"] == "unresolved"
    assert by_state["BNC-331"] == "alerta_only"
    assert by_state["DOU-332"] == "alerta_only"
    assert by_state["MUN-333"] == "alerta_only"
    assert by_state["JOI-334"] == "alerta_only"
    assert by_state["EPUB-335"] == "alerta_only"
    assert by_state["OUT-003"] == "alerta_only"
    assert report.closed is True
    assert not report.blockers
    counted = sum(report.counts.values())
    assert counted == len(report.decisions)
    unique_alerta = {row.original_id for row in imported.rows}
    unique_extra = {row.identity for row in extra}
    assert counted == len(unique_alerta | unique_extra)


def test_ambiguous_match_stays_unresolved_and_never_auto_merges() -> None:
    imported = import_alerta(SNAPSHOT.read_bytes(), filename=SNAPSHOT.name)
    extra = _extra(
        {"identity": "DUP-004", "url": "https://dup.example/a", "objeto": "Duplicata A"},
        {"identity": "DUP-004", "url": "https://dup.example/c", "objeto": "Outra leitura"},
    )
    report = reconcile(
        imported,
        extra,
        window_start="2026-08-01",
        window_end="2026-08-12",
    )
    dup = next(d for d in report.decisions if d.identity == "DUP-004")
    assert dup.state == "unresolved"
    assert dup.reason == "ambiguous_identity_multiple_rows"


def test_alerta_only_gaps_have_resolution_and_ranking_is_versioned() -> None:
    imported = import_alerta(SNAPSHOT.read_bytes(), filename=SNAPSHOT.name)
    extra = _extra(
        {
            "identity": "BOTH-001",
            "url": "https://pncp.gov.br/app/editais/001",
            "objeto": "Servico de limpeza",
            "ente": "Municipio de Florianopolis",
            "modalidade": "pregao",
            "published_at": "2026-08-06",
        },
        {
            "identity": "DIFF-002",
            "url": "https://pncp.gov.br/app/editais/002",
            "objeto": "Objeto extra diferente",
            "ente": "Municipio de Sao Jose",
            "modalidade": "pregao",
            "published_at": "2026-08-07",
        },
    )
    report = reconcile(
        imported,
        extra,
        window_start="2026-08-01",
        window_end="2026-08-12",
        registered_sources=frozenset({"pncp"}),
    )
    gaps = {g.identity: g for g in report.gaps}
    assert set(gaps) == {"BNC-331", "DOU-332", "MUN-333", "JOI-334", "EPUB-335", "OUT-003"}
    assert gaps["BNC-331"].gap_type == "fonte_nao_cadastrada"
    assert gaps["DOU-332"].gap_type == "diario_oficial"
    assert gaps["MUN-333"].gap_type == "portal_proprio"
    assert gaps["OUT-003"].gap_type == "fora_do_universo"
    for gap in report.gaps:
        assert gap.public_source_attempted is True
        assert gap.gap_type
        assert gap.probable_cause
        assert gap.evidence
        assert gap.next_action
    assert all(r.snapshot_ref.startswith("snapshot-197.jsonl:") for r in report.ranking)
    assert all("expected_unique_recall_gain" in r.components for r in report.ranking)
    # Out-of-universe misses do not promote an adapter.
    assert all(r.adapter_key != "OUT-003" for r in report.ranking)
    dumped = json.dumps(report.as_dict(), sort_keys=True)
    assert "alerta_is_absolute_truth" in dumped
    assert report.as_dict()["alerta_is_absolute_truth"] is False
    # Re-running the same inputs reproduces the versioned report hash.
    again = reconcile(
        imported,
        extra,
        window_start="2026-08-01",
        window_end="2026-08-12",
        registered_sources=frozenset({"pncp"}),
    )
    assert again.report_hash == report.report_hash
    assert again.import_id == imported.import_id

"""Tests for #346 AlertaLicitação import + conservative reconcile + miss ranking.

Drives the shipped functions from a real start state (bytes → import → reconcile).
No hardcoded dump of the unit under test and no mocked SUT.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.coverage.alerta_miss_ranking import (
    HISTORICAL_SEEDS,
    PROVENANCE,
    AlertaImportError,
    ExtraRow,
    compute_import_id,
    import_alerta,
    main,
    parse_extra_rows,
    reconcile,
    resolve_public_source,
    run_measurement,
    sha256_bytes,
)

FIXTURES = Path(__file__).parent / "fixtures" / "alerta_miss"
SNAPSHOT = FIXTURES / "snapshot-197.jsonl"
EXTRA_WINDOW = FIXTURES / "extra-window.jsonl"
CORPUS_ROW_COUNT = 11
HISTORICAL_IDS = {str(seed["identity"]) for seed in HISTORICAL_SEEDS}


def _extra(*rows: dict) -> tuple[ExtraRow, ...]:
    return tuple(ExtraRow(**row) for row in rows)


def test_reimport_same_bytes_same_import_id_counts_and_hashes() -> None:
    raw = SNAPSHOT.read_bytes()
    first = import_alerta(raw, filename=SNAPSHOT.name, imported_at="2026-08-12T21:34:00Z")
    second = import_alerta(raw, filename=SNAPSHOT.name, imported_at="2026-08-14T00:00:00Z")
    assert first.import_id == second.import_id
    assert first.import_id == compute_import_id(file_sha256=sha256_bytes(raw))
    assert first.row_count == second.row_count == CORPUS_ROW_COUNT
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
    assert by_state["BLL-261"] == "alerta_only"
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
    assert set(gaps) == {
        "BNC-331",
        "DOU-332",
        "MUN-333",
        "JOI-334",
        "EPUB-335",
        "OUT-003",
        "BLL-261",
    }
    assert gaps["BNC-331"].gap_type == "fonte_nao_cadastrada"
    assert gaps["DOU-332"].gap_type == "diario_oficial"
    assert gaps["MUN-333"].gap_type == "portal_proprio"
    assert gaps["JOI-334"].gap_type == "portal_proprio"
    assert gaps["BLL-261"].gap_type == "fonte_nao_cadastrada"
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


def test_public_source_resolution_is_a_real_deterministic_attempt() -> None:
    imported = import_alerta(SNAPSHOT.read_bytes(), filename=SNAPSHOT.name)
    bnc = next(row for row in imported.rows if row.original_id == "BNC-331")
    resolution = resolve_public_source(bnc, registered_sources=frozenset({"pncp"}))
    assert resolution.attempted is True
    assert resolution.method == "url_host"
    assert resolution.host == "bnc.org.br"
    assert resolution.resolved_platform == "bnc"
    assert resolution.registered is False
    assert "bnc.org.br" in resolution.evidence


def test_window_excludes_out_of_range_rows_and_keeps_dateless() -> None:
    alerta = (
        b'{"original_id": "IN-WIN", "url": "https://pncp.gov.br/in", '
        b'"published_at": "2026-08-05", "in_universe": true}\n'
        b'{"original_id": "OUT-WIN", "url": "https://pncp.gov.br/out", '
        b'"published_at": "2026-07-01", "in_universe": true}\n'
        b'{"original_id": "NO-DATE", "url": "https://pncp.gov.br/nodate", '
        b'"in_universe": true}\n'
    )
    extra = (
        b'{"identity": "IN-WIN", "url": "https://pncp.gov.br/in", '
        b'"published_at": "2026-08-05"}\n'
        b'{"identity": "OLD-EXTRA", "url": "https://pncp.gov.br/old", '
        b'"published_at": "2026-06-01"}\n'
    )
    report = run_measurement(
        alerta,
        extra,
        alerta_filename="window.jsonl",
        extra_filename="extra.jsonl",
        window_start="2026-08-01",
        window_end="2026-08-12",
        registered_sources=frozenset({"pncp"}),
    )
    identities = {d.identity for d in report.decisions}
    assert identities == {"IN-WIN", "NO-DATE"}
    assert "OUT-WIN" not in identities
    assert "OLD-EXTRA" not in identities
    by_state = {d.identity: d.state for d in report.decisions}
    assert by_state["IN-WIN"] == "found_both"
    assert by_state["NO-DATE"] == "alerta_only"


def test_false_positive_marker_does_not_promote_adapter() -> None:
    alerta = (
        b'{"original_id": "FP-1", "url": "https://spam.example/1", '
        b'"source_platform": "spam", "in_universe": true, "false_positive": true}\n'
    )
    report = run_measurement(
        alerta,
        b"",
        alerta_filename="fp.jsonl",
        extra_filename="empty.jsonl",
        window_start="2026-08-01",
        window_end="2026-08-12",
    )
    assert report.gaps[0].gap_type == "falso_positivo"
    assert report.ranking == ()
    dumped = report.as_dict()
    assert dumped["false_positives"] == 1
    assert dumped["alerta_only_relevant"] == 0
    assert dumped["next_source"] is None


def test_empty_extra_jsonl_is_valid_zero_side() -> None:
    extra = parse_extra_rows(b"", "empty.jsonl")
    assert extra == ()


def test_historical_seeds_are_not_silently_dropped() -> None:
    report = run_measurement(
        SNAPSHOT.read_bytes(),
        EXTRA_WINDOW.read_bytes(),
        alerta_filename=SNAPSHOT.name,
        extra_filename=EXTRA_WINDOW.name,
        window_start="2026-08-01",
        window_end="2026-08-12",
        registered_sources=frozenset({"pncp", "ciga"}),
    )
    present = {d.identity for d in report.decisions}
    assert HISTORICAL_IDS <= present
    seeds = {item["identity"]: item for item in report.as_dict()["historical_seeds"]}
    assert set(seeds) == HISTORICAL_IDS
    assert seeds["BNC-331"]["relevance"] == "still-relevant"
    assert seeds["BNC-331"]["state"] == "alerta_only"
    assert seeds["BNC-331"]["gap_type"] == "fonte_nao_cadastrada"
    assert seeds["DOU-332"]["relevance"] == "still-relevant"
    assert seeds["DOU-332"]["gap_type"] == "diario_oficial"
    assert seeds["MUN-333"]["relevance"] == "still-relevant"
    assert seeds["JOI-334"]["relevance"] == "still-relevant"
    assert seeds["EPUB-335"]["relevance"] == "still-relevant"
    assert seeds["BLL-261"]["relevance"] == "still-relevant"
    assert seeds["BLL-261"]["gap_type"] == "fonte_nao_cadastrada"
    assert all(item["relevance"] != "silently_dropped" for item in seeds.values())
    # Issue prose counts are recorded, never treated as the measured denominator.
    assert seeds["BNC-331"]["claimed_count"] == 34
    assert seeds["BNC-331"]["corpus_count"] == 1


def test_executive_report_fields_and_reproducible_measurement() -> None:
    first = run_measurement(
        SNAPSHOT.read_bytes(),
        EXTRA_WINDOW.read_bytes(),
        alerta_filename=SNAPSHOT.name,
        extra_filename=EXTRA_WINDOW.name,
        window_start="2026-08-01",
        window_end="2026-08-12",
        filters={"uf": "SC", "profile": "confenge"},
        registered_sources=frozenset({"pncp", "ciga"}),
        imported_at="2026-08-12T21:34:00Z",
    )
    second = run_measurement(
        SNAPSHOT.read_bytes(),
        EXTRA_WINDOW.read_bytes(),
        alerta_filename=SNAPSHOT.name,
        extra_filename=EXTRA_WINDOW.name,
        window_start="2026-08-01",
        window_end="2026-08-12",
        filters={"uf": "SC", "profile": "confenge"},
        registered_sources=frozenset({"pncp", "ciga"}),
        imported_at="2026-08-15T00:00:00Z",
    )
    dumped = first.as_dict()
    assert dumped["alerta_is_absolute_truth"] is False
    assert dumped["xls_197_status"] == "UNKNOWN"
    assert dumped["denominator"] == 10  # unique alerta identities in window (DUP-004 collapsed)
    assert dumped["matched"] == 2  # BOTH-001 + DIFF-002
    assert dumped["alerta_only_relevant"] == 6  # BNC DOU MUN JOI EPUB BLL; OUT excluded
    assert dumped["false_positives"] == 0
    assert dumped["unknown"] == 1  # DUP-004 unresolved
    assert dumped["affected_value"] == "UNKNOWN"
    assert dumped["affected_accounts"] != "UNKNOWN"
    assert dumped["expected_marginal_gain"] > 0
    assert dumped["next_source"]
    assert first.import_id == second.import_id
    assert first.report_hash == second.report_hash
    assert first.counts == second.counts


def test_cli_entry_point_twice_reproduces_hashes(tmp_path: Path) -> None:
    out1 = tmp_path / "run1.json"
    out2 = tmp_path / "run2.json"
    csv1 = tmp_path / "rank1.csv"
    argv_common = [
        "--alerta",
        str(SNAPSHOT),
        "--extra",
        str(EXTRA_WINDOW),
        "--window-start",
        "2026-08-01",
        "--window-end",
        "2026-08-12",
        "--registered-sources",
        "pncp,ciga",
        "--filter",
        "uf=SC",
        "--filter",
        "profile=confenge",
        "--imported-at",
        "2026-08-12T21:34:00Z",
    ]
    rc1 = main([*argv_common, "--output", str(out1), "--csv", str(csv1)])
    rc2 = main([*argv_common, "--output", str(out2)])
    assert rc1 == 0
    assert rc2 == 0
    payload1 = json.loads(out1.read_text(encoding="utf-8"))
    payload2 = json.loads(out2.read_text(encoding="utf-8"))
    assert payload1["import_id"] == payload2["import_id"]
    assert payload1["report_hash"] == payload2["report_hash"]
    assert payload1["denominator"] == payload2["denominator"]
    assert payload1["alerta_is_absolute_truth"] is False
    for key in (
        "denominator",
        "matched",
        "alerta_only_relevant",
        "false_positives",
        "unknown",
        "affected_value",
        "affected_accounts",
        "expected_marginal_gain",
        "next_source",
    ):
        assert key in payload1
    assert csv1.exists()
    header = csv1.read_text(encoding="utf-8").splitlines()[0]
    assert "adapter_key" in header
    assert "score" in header
    # No adapter implementation leaked into this module's ranking output.
    assert all(row["adapter_key"] not in {"implement", "adapter.py"} for row in payload1["ranking"])

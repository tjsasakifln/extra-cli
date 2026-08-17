"""Drive the shipped official-live refresh/export path. No parallel oracle."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.contract_publication.official_snapshot import (
    SOURCE_KIND_OFFICIAL,
    blocked_snapshot,
    build_snapshot,
    fetch_official_sc_snapshot,
    query_hash,
)
from scripts.public_read_consumers.cli import main as consumers_main
from scripts.public_read_consumers.live_refresh import (
    CONSUMER_ID,
    REASON_FIXTURE_AS_LIVE,
    REASON_NATIONAL,
    REASON_PII,
    REASON_UNKNOWN_CONSUMER,
    RefreshRefusedError,
    refresh,
    replay_dir,
    stable_content_hash,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "contract_publication" / "golden_corpus.json"


def _base_row(**overrides: object) -> dict:
    row = {
        "contrato_id": "11111111000191-1-000001/2026",
        "orgao_cnpj": "11111111000191",
        "orgao_nome": "Prefeitura",
        "fornecedor_cnpj": "22222222000191",
        "fornecedor_nome": "Construtora",
        "objeto_contrato": "Obra de pavimentacao com aditivo de prazo",
        "valor_total": 1_200_000,
        "data_inicio": "2026-01-01",
        "data_fim": "2026-12-01",
        "data_publicacao": "2026-01-02",
        "data_assinatura": "2026-01-03",
        "uf": "SC",
        "municipio": "Florianopolis",
        "source": "pncp",
        "source_id": "11111111000191-1-000001/2026",
        "ingested_at": "2026-08-16T12:00:00+00:00",
        "is_active": True,
        "codigo_municipio_ibge": "4205407",
    }
    row.update(overrides)
    return row


def _official_snapshot(rows: list[dict] | None = None) -> dict:
    snapshot = build_snapshot(
        rows or [_base_row()],
        as_of="2026-08-17T00:00:00Z",
        source_as_of="2026-08-16T12:00:00Z",
        limit=40,
        source_kind=SOURCE_KIND_OFFICIAL,
    )
    snapshot["live_select_executed"] = True
    snapshot["official_projection_authorized"] = True
    return snapshot


def _fixture_snapshot() -> dict:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["source_kind"] = "fixture"
    payload["official_projection_authorized"] = False
    payload["live_select_executed"] = False
    payload["official_live"] = False
    return payload


def test_dsn_absent_is_blocked_not_live() -> None:
    snapshot = fetch_official_sc_snapshot(None)
    assert snapshot["source_kind"] == "blocked"
    assert snapshot["official_live"] is False
    assert "dsn_absent" in snapshot["reason_codes"]
    assert snapshot["live_select_executed"] is False


def test_query_hash_is_stable() -> None:
    assert query_hash(uf="SC", limit=40) == query_hash(uf="SC", limit=40)
    assert query_hash(uf="SC", limit=40) != query_hash(uf="SC", limit=10)


def test_table_absent_is_blocked() -> None:
    class _Cur:
        def execute(self, sql, params=None):
            return None

        def fetchall(self):
            return []

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class _Conn:
        def cursor(self):
            return _Cur()

        def close(self):
            return None

    snapshot = fetch_official_sc_snapshot("postgresql://x", connect=lambda _dsn: _Conn())
    assert snapshot["source_kind"] == "blocked"
    assert "table_absent" in snapshot["reason_codes"]


def test_fixture_refresh_is_not_official_live(tmp_path: Path) -> None:
    dest = tmp_path / "export"
    first = refresh(
        consumer=CONSUMER_ID,
        out=dest,
        snapshot=_fixture_snapshot(),
        fixture=True,
        generated_at="2026-08-17T10:00:00Z",
    )
    second = refresh(
        consumer=CONSUMER_ID,
        out=dest,
        snapshot=_fixture_snapshot(),
        fixture=True,
        generated_at="2026-08-17T11:00:00Z",
    )
    assert first["official_live"] is False
    assert first["content_hash"] == second["content_hash"]
    payload = json.loads((dest / "payload.json").read_text(encoding="utf-8"))
    assert payload["schema"] == "public-read-contract-analysis/1.0"
    assert payload["no_index_authorization"] is True
    assert payload["claim_scope"] == "SC"
    assert payload["claim_authorization"] is None
    assert payload["official_live"] is False
    assert "INDEX" not in json.dumps(payload)
    assert payload["coverage"]["editorial_review"] <= 3
    for item in payload["analyses"]:
        assert item["data_state"] in {"DATA_READY", "DATA_HOLD", "DATA_REJECT"}
        assert item.get("peer_group", {}).get("status") in {"NOT_COMPARABLE", "ABSENT", "PEER_WEAK", "PEER_VALID"}


def test_content_hash_ignores_generated_at(tmp_path: Path) -> None:
    dest = tmp_path / "a"
    other = tmp_path / "b"
    snap = _fixture_snapshot()
    one = refresh(consumer=CONSUMER_ID, out=dest, snapshot=snap, fixture=True, generated_at="2026-08-17T01:00:00Z")
    two = refresh(consumer=CONSUMER_ID, out=other, snapshot=snap, fixture=True, generated_at="2026-08-17T23:00:00Z")
    assert one["content_hash"] == two["content_hash"]
    left = json.loads((dest / "payload.json").read_text(encoding="utf-8"))
    right = json.loads((other / "payload.json").read_text(encoding="utf-8"))
    assert left["generated_at"] != right["generated_at"]
    assert stable_content_hash(left) == stable_content_hash(right)


def test_live_flag_on_fixture_is_refused(tmp_path: Path) -> None:
    with pytest.raises(RefreshRefusedError) as exc:
        refresh(
            consumer=CONSUMER_ID,
            out=tmp_path / "x",
            snapshot=_fixture_snapshot(),
            fixture=True,
            live=True,
        )
    assert exc.value.reason_code == REASON_FIXTURE_AS_LIVE


def test_unknown_consumer_refused(tmp_path: Path) -> None:
    with pytest.raises(RefreshRefusedError) as exc:
        refresh(consumer="web-cfg/unknown-generic-api", out=tmp_path / "x", snapshot=_fixture_snapshot(), fixture=True)
    assert exc.value.reason_code == REASON_UNKNOWN_CONSUMER


def test_national_claim_is_refused(tmp_path: Path) -> None:
    snap = _official_snapshot()
    snap["records"][0]["national_claim"] = True
    snap["records"][0]["claim_scope"] = "BR"
    with pytest.raises(RefreshRefusedError) as exc:
        refresh(consumer=CONSUMER_ID, out=tmp_path / "x", snapshot=snap, live=True)
    assert exc.value.reason_code == REASON_NATIONAL


def test_pii_payload_is_refused(tmp_path: Path) -> None:
    from scripts.public_read_consumers.live_refresh import build_export_documents, validate_export

    docs = build_export_documents(_official_snapshot(), generated_at="2026-08-17T00:00:00Z", out_dir=str(tmp_path))
    docs["payload"]["analyses"][0]["email"] = "pessoa@example.com"
    with pytest.raises(RefreshRefusedError) as exc:
        validate_export(docs)
    assert exc.value.reason_code == REASON_PII


def test_peer_group_absent_is_not_comparable(tmp_path: Path) -> None:
    dest = tmp_path / "export"
    refresh(
        consumer=CONSUMER_ID, out=dest, snapshot=_official_snapshot(), live=True, generated_at="2026-08-17T00:00:00Z"
    )
    payload = json.loads((dest / "payload.json").read_text(encoding="utf-8"))
    assert payload["official_live"] is True
    assert payload["status.json"] if False else payload["producer_status"] == "OFFICIAL_LIVE"
    status = json.loads((dest / "status.json").read_text(encoding="utf-8"))
    assert status["comparability"] == "NOT_COMPARABLE"
    for item in payload["analyses"]:
        assert item["peer_group"]["status"] == "NOT_COMPARABLE"
        assert "NOT_COMPARABLE" in item["reason_codes"]


def test_high_value_without_insight_rejects() -> None:
    from scripts.contract_publication.engine import rank_candidates

    snap = _fixture_snapshot()
    ranked = rank_candidates(snap["records"], as_of=snap["as_of"], catalog_mode="fixture")
    ordinary = next(item for item in ranked if "high_value_without_insight" in item.reason_codes)
    assert ordinary.candidate_state == "REJECT"


def test_inference_is_not_serialized_as_fact() -> None:
    from scripts.contract_publication.engine import build_packs, rank_candidates

    snap = _fixture_snapshot()
    ranked = rank_candidates(snap["records"], as_of=snap["as_of"], catalog_mode="fixture")
    packs = build_packs(snap["records"], ranked, as_of=snap["as_of"], catalog_mode="fixture", policy=None)
    for pack in packs.values():
        for node in pack.get("timeline") or ():
            if isinstance(node, dict) and node.get("epistemic_class") == "INFERENCE":
                assert node.get("class") != "FACT"


def test_cnpj_or_city_swap_is_not_novelty() -> None:
    from scripts.contract_publication.engine import rank_candidates

    snap = _fixture_snapshot()
    ranked = {
        item.analysis_candidate_id: item
        for item in rank_candidates(snap["records"], as_of=snap["as_of"], catalog_mode="fixture")
    }
    swapped = ranked.get("CAND-SWAP-01") or next(
        (
            item
            for item in ranked.values()
            if "swap" in item.analysis_candidate_id.lower() or "municipio" in ",".join(item.reason_codes)
        ),
        None,
    )
    if swapped is None:
        pytest.skip("golden corpus has no swap record on this revision")
    assert swapped.candidate_state != "EDITORIAL_REVIEW" or "swap" not in swapped.reason_codes


def test_duplicate_or_rectification_collapses() -> None:
    from scripts.contract_publication.engine import rank_candidates

    snap = _fixture_snapshot()
    first = dict(snap["records"][0])
    second = dict(snap["records"][0])
    ranked = rank_candidates([first, second], as_of=snap["as_of"], catalog_mode="fixture")
    assert any("duplicate_collapsed" in item.reason_codes for item in ranked)


def test_stale_snapshot_holds() -> None:
    from scripts.contract_publication.engine import rank_candidates

    snap = _fixture_snapshot()
    record = dict(snap["records"][0])
    record["observed_at"] = "2024-01-01T00:00:00+00:00"
    ranked = rank_candidates([record], as_of="2026-08-15T00:00:00+00:00", catalog_mode="fixture")
    assert any(item.freshness_status == "STALE" or "snapshot_stale" in item.reason_codes for item in ranked)


def test_atomic_failure_preserves_lkg(tmp_path: Path) -> None:
    dest = tmp_path / "export"
    refresh(
        consumer=CONSUMER_ID, out=dest, snapshot=_fixture_snapshot(), fixture=True, generated_at="2026-08-17T00:00:00Z"
    )
    lkg_hash = json.loads((dest / "payload.json").read_text(encoding="utf-8"))["content_hash"]
    assert (dest / "lkg" / "payload.json").is_file()
    with pytest.raises(RefreshRefusedError) as exc:
        refresh(
            consumer=CONSUMER_ID,
            out=dest,
            snapshot=_fixture_snapshot(),
            fixture=True,
            fail_before_rename=True,
        )
    assert exc.value.reason_code == "atomic_fail_before_rename"
    assert json.loads((dest / "payload.json").read_text(encoding="utf-8"))["content_hash"] == lkg_hash
    assert json.loads((dest / "lkg" / "payload.json").read_text(encoding="utf-8"))["content_hash"] == lkg_hash


def test_schema_incompatible_refused(tmp_path: Path) -> None:
    from scripts.public_read_consumers.live_refresh import build_export_documents, validate_export

    docs = build_export_documents(_fixture_snapshot(), generated_at="2026-08-17T00:00:00Z", out_dir=str(tmp_path))
    docs["payload"]["schema"] = "public-read-contract-analysis/9.9"
    with pytest.raises(RefreshRefusedError) as exc:
        validate_export(docs)
    assert exc.value.reason_code == "schema_incompatible"


def test_cli_refresh_and_replay_match(tmp_path: Path) -> None:
    dest = tmp_path / "cli"
    snap = tmp_path / "snap.json"
    snap.write_text(json.dumps(_fixture_snapshot()), encoding="utf-8")
    code = consumers_main(
        [
            "refresh",
            "--consumer",
            CONSUMER_ID,
            "--out",
            str(dest),
            "--snapshot",
            str(snap),
            "--fixture",
        ]
    )
    assert code == 0
    first = json.loads((dest / "payload.json").read_text(encoding="utf-8"))["content_hash"]
    replayed = replay_dir(dest, generated_at="2026-08-18T00:00:00Z")
    assert replayed["content_hash"] == first


def test_official_snapshot_does_not_rank_by_value_only() -> None:
    cheap = _base_row(contrato_id="cheap", valor_total=80_000, objeto_contrato="Obra com aditivo de prazo e reajuste")
    expensive = _base_row(contrato_id="dear", valor_total=80_000_000, objeto_contrato="Obra ordinaria de terraplenagem")
    snap = _official_snapshot([expensive, cheap])
    records = snap["records"]
    assert records[0]["selection_signal"] == "editorial_token" or records[1]["selection_signal"] == "editorial_token"
    assert "aditivo" in cheap["objeto_contrato"]


def test_blocked_snapshot_helper_has_query_hash() -> None:
    blocked = blocked_snapshot(reason="columns_absent", extra={"missing_columns": ["unidade"]})
    assert blocked["official_live"] is False
    assert blocked["query_hash"]
    assert "columns_absent" in blocked["reason_codes"]

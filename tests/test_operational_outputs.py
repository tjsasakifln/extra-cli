"""Tests for scripts.reports.operational_outputs (DoD §12.2 first 8 lists)."""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.reports.operational_outputs import (
    LIST_FILES,
    OperationalQueryError,
    _motivo_from_ranking,
    _q,
    _write_csv,
    classify_bids,
    main,
    run,
    write_lists,
)
from scripts.reports.run_metadata import (
    OPERATIONAL_METADATA_REQUIRED_FIELDS,
    build_run_metadata,
    validate_operational_metadata,
)


def test_classify_bids_partitions_active_rows():
    now = datetime(2026, 7, 18, tzinfo=UTC)
    rows = [
        {
            "pncp_id": "A",
            "objeto_compra": "Pavimentação asfáltica de vias urbanas",
            "orgao_cnpj": "12345678000199",
            "orgao_razao_social": "Pref Teste",
            "uf": "SC",
            "municipio": "Florianópolis",
            "valor_total_estimado": 500_000,
            "modalidade_nome": "Pregão Eletrônico",
            "data_encerramento": now + timedelta(days=10),
            "data_publicacao": now - timedelta(days=1),
            "link_pncp": "https://pncp.gov.br/x",
            "is_active": True,
            "matched_entity_id": 1,
        },
        {
            "pncp_id": "B",
            "objeto_compra": "",
            "orgao_cnpj": None,
            "is_active": True,
            "data_encerramento": now - timedelta(days=1),
        },
    ]
    out = classify_bids(rows, now=now)
    assert set(out.keys()) >= {"GO", "REVIEW", "NO_GO"}
    total = sum(len(v) for v in out.values())
    assert total == 2
    # B must be NO_GO (no objeto / no orgao / past deadline)
    ids_nogo = {r["source_id"] for r in out["NO_GO"]}
    assert "B" in ids_nogo
    for r in out["NO_GO"]:
        if r["source_id"] == "B":
            assert r["motivo"]
            break


def test_motivo_from_ranking_uses_blockers():
    m = _motivo_from_ranking(
        {
            "ranking_score": 0,
            "ranking_fatores": {"bloqueadores": ["Sem objeto"], "negativos": []},
            "ranking_regras": ["BLOQUEIO:sem_objeto"],
        }
    )
    assert "Sem objeto" in m


def test_write_lists_creates_eight_files(tmp_path: Path):
    payload = {
        "editais_acionaveis": [{"source_id": "1", "ranking": "GO"}],
        "editais_revisao": [],
        "editais_descartados": [{"source_id": "2", "ranking": "NO_GO", "motivo": "x"}],
        "oportunidades_removidas_snapshot": [],
        "entes_sem_cobertura_editais": [],
        "entes_sem_cobertura_contratos": [],
        "blockers_por_fonte": [{"source": "pncp", "blocker_type": "ingestion_failed", "n": 1}],
        "runs_stale": [],
        "meta": {
            "ranking_source": "test",
            "limitations": ["fixture"],
            "counts": {
                "GO": 1,
                "REVIEW": 0,
                "NO_GO": 1,
                "removed": 0,
                "gap_editais": 0,
                "gap_contratos": 0,
                "blockers": 1,
                "stale_runs": 0,
            },
        },
    }
    man = write_lists(tmp_path, payload, run_id="ops-lists-test")
    assert man["run_id"] == "ops-lists-test"
    assert "reliability" in man
    for key, filename in LIST_FILES.items():
        p = tmp_path / filename
        assert p.is_file(), f"missing {filename}"
        assert p.stat().st_size >= 0
    mpath = tmp_path / "manifest.json"
    assert mpath.is_file()
    data = json.loads(mpath.read_text(encoding="utf-8"))
    assert data["section"] == "12.2"
    assert "LOCAL_READY" in data["claims"]["forbidden"]
    assert data.get("code_sha")
    assert "artifact_hashes" in data
    assert data.get("capability") == "operational_lists_12_2"


def test_write_lists_empty_payload_still_writes_headers(tmp_path: Path):
    payload = {k: [] for k in LIST_FILES}
    payload["meta"] = {
        "ranking_source": "empty",
        "limitations": ["no data"],
        "counts": {},
        "status": "SUCCESS_ZERO",
        "reliability": "NOT_READY",
    }
    man = write_lists(tmp_path, payload)
    assert man["reliability"] in {"NOT_READY", "UNTRUSTED", "DEGRADED", "PARTIAL"}
    assert man.get("status") == "SUCCESS_ZERO"
    assert len(list(tmp_path.glob("*.csv"))) == 8
    for field in OPERATIONAL_METADATA_REQUIRED_FIELDS:
        assert field in man, f"missing operational metadata field {field}"
    assert man.get("duration_seconds") is None or isinstance(man.get("duration_seconds"), (int, float))
    assert isinstance(man.get("artifact_hashes"), dict)
    assert man.get("errors") == [] or isinstance(man.get("errors"), list)


def test_write_csv_refuses_error_rows(tmp_path: Path):
    with pytest.raises(OperationalQueryError, match="fail-closed"):
        _write_csv(tmp_path / "bad.csv", [{"_error": "boom", "x": 1}], fieldnames=["x"])


def test_q_fail_closed_raises_on_sql_error():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    conn.cursor.return_value.__exit__.return_value = False
    cur.execute.side_effect = RuntimeError("relation does not exist")
    with pytest.raises(OperationalQueryError, match="relation does not exist"):
        _q(conn, "SELECT * FROM definitely_missing_table_xyz")
    conn.rollback.assert_called()


def test_classify_bids_refuses_error_rows():
    with pytest.raises(OperationalQueryError, match="_error"):
        classify_bids([{"_error": "sql failed"}])


def test_build_run_metadata_has_operational_fields():
    meta = build_run_metadata(
        run_id="ops-test-1",
        artifact_kind="operational_lists",
        dataset_hash="abc",
        reliability="NOT_READY",
        limitations=["empty"],
        errors=[],
        duration_seconds=0.12,
        artifact_hashes={"a.csv": "deadbeef"},
    )
    missing = validate_operational_metadata(meta)
    assert missing == [], missing
    assert meta["code_sha"]
    assert meta["run_id"] == "ops-test-1"
    assert meta["reliability"] == "NOT_READY"


def test_main_sql_error_nonzero_exit(monkeypatch, tmp_path: Path):
    def _boom(*_a, **_k):
        raise OperationalQueryError("injected SQL failure")

    monkeypatch.setattr(
        "scripts.reports.operational_outputs.run",
        _boom,
    )
    code = main(["--dsn", "postgresql://x", "--out", str(tmp_path)])
    assert code == 1


def test_main_missing_dsn_exit_2(monkeypatch):
    monkeypatch.delenv("LOCAL_DATALAKE_DSN", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    code = main(["--out", "/tmp/orpt-no-dsn"])
    assert code == 2


def _require_real_db_dsn() -> str:
    dsn = os.environ.get("LOCAL_DATALAKE_DSN") or os.environ.get("DATABASE_URL")
    if os.environ.get("REQUIRE_REAL_DB") == "1":
        if not dsn:
            pytest.fail("REQUIRE_REAL_DB=1 but LOCAL_DATALAKE_DSN/DATABASE_URL unset")
        try:
            import psycopg2

            conn = psycopg2.connect(dsn)
            conn.close()
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"REQUIRE_REAL_DB=1 but PostgreSQL unavailable: {exc}")
        return dsn
    if not dsn:
        pytest.skip("no DSN")
    try:
        import psycopg2

        conn = psycopg2.connect(dsn)
        conn.close()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"pg unavailable: {exc}")
    return dsn


@pytest.mark.integration
def test_live_run_against_local_pg(tmp_path: Path):
    dsn = _require_real_db_dsn()
    man = run(dsn, tmp_path)
    assert man["run_id"]
    assert (tmp_path / "manifest.json").is_file()
    assert len(list(tmp_path.glob("*.csv"))) == 8
    counts = man.get("counts") or {}
    total = (
        int(counts.get("GO") or 0)
        + int(counts.get("REVIEW") or 0)
        + int(counts.get("NO_GO") or 0)
    )
    assert total >= 0
    if total == 0:
        assert man.get("status") == "SUCCESS_ZERO"
        assert man.get("reliability") in {"NOT_READY", "UNTRUSTED", "PARTIAL"}
        assert man.get("limitations"), "zero rows must document limitations"
    for field in OPERATIONAL_METADATA_REQUIRED_FIELDS:
        assert field in man, f"live missing field {field}"
    assert man.get("dataset_hash")
    assert isinstance(man.get("artifact_hashes"), dict)
    assert "editais_acionaveis.csv" in man["artifact_hashes"]


@pytest.mark.integration
def test_live_sql_error_propagates_nonzero(tmp_path: Path, monkeypatch):
    """Inject bad SQL path: broken table name via monkeypatch of fetch."""
    dsn = _require_real_db_dsn()

    def _bad_fetch(conn):  # noqa: ARG001
        raise OperationalQueryError("injected relation missing for campaign gate")

    monkeypatch.setattr(
        "scripts.reports.operational_outputs.fetch_active_bids",
        _bad_fetch,
    )
    monkeypatch.setattr(
        "scripts.reports.operational_outputs.fetch_from_opportunity_intel",
        lambda conn: None,  # noqa: ARG005
    )
    with pytest.raises(OperationalQueryError, match="injected"):
        run(dsn, tmp_path)
    code = main(["--dsn", dsn, "--out", str(tmp_path / "fail")])
    assert code == 1

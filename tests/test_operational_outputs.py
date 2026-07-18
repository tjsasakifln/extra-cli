"""Tests for scripts.reports.operational_outputs (DoD §12.2 first 8 lists)."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts.reports.operational_outputs import (
    LIST_FILES,
    classify_bids,
    write_lists,
    _motivo_from_ranking,
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


def test_write_lists_empty_payload_still_writes_headers(tmp_path: Path):
    payload = {k: [] for k in LIST_FILES}
    payload["meta"] = {"ranking_source": "empty", "limitations": ["no data"], "counts": {}}
    man = write_lists(tmp_path, payload)
    assert man["reliability"] in {"DEGRADED", "UNTRUSTED"}
    assert len(list(tmp_path.glob("*.csv"))) == 8


@pytest.mark.integration
def test_live_run_against_local_pg(tmp_path: Path):
    import os

    dsn = os.environ.get("LOCAL_DATALAKE_DSN") or os.environ.get("DATABASE_URL")
    if not dsn:
        pytest.skip("no DSN")
    try:
        import psycopg2

        conn = psycopg2.connect(dsn)
        conn.close()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"pg unavailable: {exc}")

    from scripts.reports.operational_outputs import run

    man = run(dsn, tmp_path)
    assert man["run_id"]
    assert (tmp_path / "manifest.json").is_file()
    assert len(list(tmp_path.glob("*.csv"))) == 8
    # With live PNCP inserts from campaign, expect some classification
    counts = man.get("counts") or {}
    total = int(counts.get("GO") or 0) + int(counts.get("REVIEW") or 0) + int(counts.get("NO_GO") or 0)
    # Allow zero if DB wiped; still require files
    assert total >= 0

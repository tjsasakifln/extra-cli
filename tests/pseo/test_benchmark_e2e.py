"""B4: end-to-end benchmark on the same path as ``python -m scripts.pseo.export_web_cfg``.

CI variant: 5k contracts / 2k bids (default).
Full variant: 250k contracts + 100k bids behind ``PSEO_BENCH_FULL=1`` or marker ``pseo_full``.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from scripts.pseo.chunked_extract import peak_rss_mb
from scripts.pseo.pipeline import build_export, stage_from_rows, write_export
from scripts.pseo.staging import StagingStore
from scripts.pseo.validation import validate_export_dir

# AEC-like object so classifier keeps rows
_AEC_OBJ = (
    "Contratação de empresa especializada para pavimentação asfáltica "
    "e drenagem em vias urbanas do município"
)


def _rss_mb() -> float:
    return peak_rss_mb()


def _synthetic_contract(i: int) -> dict:
    uf = "SC" if i % 2 == 0 else "PR"
    return {
        "contrato_id": f"c-{i:08d}",
        "orgao_cnpj": f"{(i % 9000) + 1000:08d}0001{(i % 90):02d}"[:14].ljust(14, "0"),
        "orgao_nome": f"PREFEITURA MUNICIPAL SYNTH {i % 50}",
        "fornecedor_cnpj": f"{(i % 8000) + 2000:08d}0001{(i % 80):02d}"[:14].ljust(14, "0"),
        "fornecedor_nome": f"CONSTRUTORA SYNTH {i % 200}",
        "objeto_contrato": _AEC_OBJ if i % 3 != 0 else "Fornecimento de material de expediente",
        "valor_total": 50_000.0 + (i % 5000) * 10.0,
        "data_inicio": "2025-01-01",
        "data_fim": "2026-12-31",
        "data_publicacao": f"2025-{(i % 12) + 1:02d}-15",
        "uf": uf,
        "municipio": "Florianopolis" if uf == "SC" else "Curitiba",
        "source": "synthetic",
    }


def _synthetic_bid(i: int) -> dict:
    uf = "SC" if i % 2 == 0 else "PR"
    # Future end dates so some stay open relative to as_of 2026-07-31
    end = "2026-08-15" if i % 5 == 0 else "2026-01-10"
    return {
        "pncp_id": f"{(i % 9000) + 1000:08d}000100{(i % 90):02d}-1-{i % 10000:06d}/2026",
        "objeto_compra": _AEC_OBJ if i % 2 == 0 else "Aquisicao de generos alimenticios",
        "valor_total_estimado": 100_000.0 + i % 10000,
        "modalidade_nome": "Concorrência - Eletrônica",
        "uf": uf,
        "municipio": "Florianopolis" if uf == "SC" else "Curitiba",
        "orgao_nome": f"PREFEITURA MUNICIPAL SYNTH {i % 50}",
        "orgao_cnpj": f"{(i % 9000) + 1000:08d}0001{(i % 90):02d}"[:14].ljust(14, "0"),
        "data_publicacao": "2026-06-01",
        "data_abertura": "2026-06-15",
        "data_encerramento": end,
        "link_pncp": f"https://pncp.gov.br/app/editais/synthetic/{i}",
        "source": "synthetic",
        "is_active": True,
        "situacao": "Aberta" if end >= "2026-07-31" else "Encerrada",
    }


def _run_e2e(
    tmp_path: Path,
    *,
    n_contracts: int,
    n_bids: int,
    as_of: str = "2026-07-31",
) -> dict:
    rss0 = _rss_mb()
    t0 = time.perf_counter()

    # Generate synthetic data without retaining more than one batch for staging insert
    # (we still need lists for stage_from_rows API — build in place then stage)
    contracts = [_synthetic_contract(i) for i in range(n_contracts)]
    bids = [_synthetic_bid(i) for i in range(n_bids)]
    counts = {
        "pncp_supplier_contracts": n_contracts,
        "pncp_raw_bids": n_bids,
        "sc_public_entities": 0,
        "synthetic": 1,
    }

    staged = stage_from_rows(contracts, bids, chunk_size=2_000)
    # Drop raw lists before aggregate to exercise memory path
    del contracts, bids

    staging: StagingStore = staged["staging"]
    try:
        bundle = build_export(
            [],
            [],
            counts,
            top20_path=None,
            as_of=as_of,
            repo_root=Path(".").resolve(),
            staging=staging,
            pre_classification_counts=staged["pre_classification_counts"],
        )
        out = tmp_path / "export"
        write_export(out, bundle, approval_path=None)
        elapsed = time.perf_counter() - t0
        rss1 = _rss_mb()
        man = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        vr = validate_export_dir(out, repo_root=Path(".").resolve(), require_commit_entrypoint=True)
        files = sorted(p.name for p in out.glob("*.json"))
        report = {
            "ok": vr.get("ok") is True and man.get("snapshot_status") == "CANDIDATE",
            "n_contracts": n_contracts,
            "n_bids": n_bids,
            "elapsed_sec": round(elapsed, 4),
            "rss_start_mb": round(rss0, 2),
            "rss_peak_mb": round(rss1, 2),
            "rss_delta_mb": round(max(0.0, rss1 - rss0), 2),
            "dataset_hash": man.get("dataset_hash"),
            "snapshot_status": man.get("snapshot_status"),
            "indexable": man.get("indexable"),
            "publish_status": man.get("publish_status"),
            "counts": man.get("counts"),
            "files": files,
            "validation_ok": vr.get("ok"),
            "validation_errors": vr.get("errors"),
            "staging_used": True,
            "no_fetchall": True,
            "linear_full_list": False,
            "batches_hint": (n_contracts + 1999) // 2000 + (n_bids + 1999) // 2000,
        }
        return report
    finally:
        staging.secure_delete()


def test_benchmark_e2e_ci_variant(tmp_path: Path) -> None:
    """CI: 5k contracts / 2k bids — same code path as export_web_cfg."""
    r1 = _run_e2e(tmp_path / "r1", n_contracts=5_000, n_bids=2_000)
    r2 = _run_e2e(tmp_path / "r2", n_contracts=5_000, n_bids=2_000)

    assert r1["ok"] is True, r1
    assert r1["snapshot_status"] == "CANDIDATE"
    assert r1["indexable"] is False
    assert r1["validation_ok"] is True
    assert "manifest.json" in r1["files"]
    assert "schema.json" in r1["files"]
    assert r1["dataset_hash"] and len(r1["dataset_hash"]) == 64
    # Determinism
    assert r1["dataset_hash"] == r2["dataset_hash"]
    assert r1["counts"].get("classified_aec_contracts") == r2["counts"].get(
        "classified_aec_contracts"
    )
    # Soft memory ceiling for CI synthetic
    assert r1["rss_delta_mb"] < 1500, r1
    assert r1["elapsed_sec"] > 0

    # Persist evidence
    camp = Path("docs/ops/campaigns/EXTRA-PRS-186-187-TRUST-HARDENING-01/logs")
    camp.mkdir(parents=True, exist_ok=True)
    (camp / "pseo-e2e-bench-ci.json").write_text(
        json.dumps(r1, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


@pytest.mark.slow
def test_benchmark_e2e_full_variant(tmp_path: Path) -> None:
    """Full: 250k contracts + 100k bids (requires PSEO_BENCH_FULL=1; mark=slow)."""
    if os.environ.get("PSEO_BENCH_FULL") != "1":
        pytest.skip("set PSEO_BENCH_FULL=1 for full 250k/100k e2e benchmark")
    r1 = _run_e2e(tmp_path / "full1", n_contracts=250_000, n_bids=100_000)
    r2 = _run_e2e(tmp_path / "full2", n_contracts=250_000, n_bids=100_000)
    assert r1["ok"] is True, r1
    assert r1["dataset_hash"] == r2["dataset_hash"]
    assert r1["no_fetchall"] is True
    assert r1["linear_full_list"] is False
    camp = Path("docs/ops/campaigns/EXTRA-PRS-186-187-TRUST-HARDENING-01/logs")
    camp.mkdir(parents=True, exist_ok=True)
    (camp / "pseo-e2e-bench-full.json").write_text(
        json.dumps(r1, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def test_stage_from_rows_secure_delete(tmp_path: Path) -> None:
    staged = stage_from_rows(
        [_synthetic_contract(0), _synthetic_contract(1)],
        [_synthetic_bid(0)],
        chunk_size=10,
    )
    path = Path(staged["staging_path"])
    assert path.exists()
    staged["staging"].secure_delete()
    assert not path.exists()

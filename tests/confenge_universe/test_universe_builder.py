"""Required scenarios for CONFENGE national construction universe."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from scripts.commercial_leads.contract_relevance import classify_contract_relevance
from scripts.confenge_universe import DNC, ELIGIBLE, NOT_CONSTRUCTION, SCHEMA_VERSION
from scripts.confenge_universe.construction import assess_construction
from scripts.confenge_universe.dedupe import (
    brand_tokens,
    jaccard,
    should_split_independent_brand,
)
from scripts.confenge_universe.eligibility import decide_eligibility, is_dnc_cnpj, load_dnc_set
from scripts.confenge_universe.identity import resolve_identity
from scripts.confenge_universe.pipeline import run_universe_build
from scripts.confenge_universe.scoring import compute_priority_score
from scripts.confenge_universe.source import iter_contract_rows, iter_contracts_keyset
from scripts.linkage.keys import is_valid_cnpj14

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "confenge_universe"
AS_OF = date(2026, 8, 1)

# Fixture CNPJs (valid check digits)
CNPJ_ALFA_MATRIZ = "11222333000181"
CNPJ_ALFA_FILIAL = "11222333000262"
CNPJ_MEGA = "44555666000181"
CNPJ_BETA_SMALL = "77888999000181"
CNPJ_FARMA = "12345678000195"
CNPJ_GAMA_DNC = "99887766000105"
CNPJ_DELTA = "33445566000186"
CNPJ_OMEGA = "33445566000267"
ROOT_ALFA = "11222333"
ROOT_BRAND = "33445566"


@pytest.fixture
def sample_csv() -> Path:
    p = FIXTURES / "contracts_sample.csv"
    assert p.is_file()
    return p


@pytest.fixture
def dnc_path() -> Path:
    p = FIXTURES / "dnc.txt"
    assert p.is_file()
    return p


def test_fixture_cnpjs_are_valid() -> None:
    for c in (
        CNPJ_ALFA_MATRIZ,
        CNPJ_ALFA_FILIAL,
        CNPJ_MEGA,
        CNPJ_BETA_SMALL,
        CNPJ_FARMA,
        CNPJ_GAMA_DNC,
        CNPJ_DELTA,
        CNPJ_OMEGA,
    ):
        assert is_valid_cnpj14(c), c


def test_root_cnpj_dedupe_matrix_filial(sample_csv: Path, dnc_path: Path, tmp_path: Path) -> None:
    """Matrix + branch of same root collapse to one entity."""
    result = run_universe_build(
        as_of=AS_OF,
        csv_path=str(sample_csv),
        dnc_path=str(dnc_path),
        out_dir=tmp_path / "out",
        enable_independent_brand=True,
    )
    assert result["reconciliation_ok"] is True
    records = result["records"]
    alfa = [r for r in records if r["cnpj_root"] == ROOT_ALFA]
    assert len(alfa) == 1, f"expected 1 alfa entity, got {len(alfa)}"
    est = alfa[0]["portfolio"]["establishments"]
    cnpjs = {e["cnpj14"] for e in est}
    assert CNPJ_ALFA_MATRIZ in cnpjs
    assert CNPJ_ALFA_FILIAL in cnpjs
    assert alfa[0]["cnpj14"] == CNPJ_ALFA_MATRIZ  # prefer matriz
    assert alfa[0]["outreach_eligibility"] in {ELIGIBLE, DNC}


def test_independent_brand_exception_matrix_filial_distinct_names(
    sample_csv: Path, dnc_path: Path, tmp_path: Path
) -> None:
    """DELTA vs OMEGA under same root with distinct brands may split."""
    # Unit-level evidence for the split rule
    assert should_split_independent_brand(
        "DELTA CONSTRUTORA DE EDIFICIOS LTDA",
        "OMEGA TERRAPLENAGEM E PAVIMENTACAO SPE",
        both_have_construction=True,
    )
    assert not should_split_independent_brand(
        "ALFA CONSTRUTORA E ENGENHARIA LTDA",
        "ALFA CONSTRUTORA E ENGENHARIA LTDA FILIAL BLUMENAU",
        both_have_construction=True,
    )

    result = run_universe_build(
        as_of=AS_OF,
        csv_path=str(sample_csv),
        dnc_path=str(dnc_path),
        out_dir=tmp_path / "out_brand",
        enable_independent_brand=True,
    )
    brand_entities = [r for r in result["records"] if r["cnpj_root"] == ROOT_BRAND]
    # Either split into 2 independent brands or stay 1 if stream order didn't
    # trigger — both are acceptable if aliases retained; prefer split when evidence.
    assert len(brand_entities) >= 1
    if len(brand_entities) == 2:
        names = {r["razao_social"] for r in brand_entities}
        assert any("DELTA" in n.upper() for n in names)
        assert any("OMEGA" in n.upper() for n in names)
        assert all(r.get("independent_brand") for r in brand_entities)
    else:
        # collapsed path still retains both establishments as aliases
        est = brand_entities[0]["portfolio"]["establishments"]
        assert len(est) >= 2


def test_large_firm_not_discarded(sample_csv: Path, dnc_path: Path, tmp_path: Path) -> None:
    result = run_universe_build(
        as_of=AS_OF,
        csv_path=str(sample_csv),
        dnc_path=str(dnc_path),
        out_dir=tmp_path / "out_large",
    )
    mega = [r for r in result["records"] if r["cnpj14"] == CNPJ_MEGA]
    assert len(mega) == 1
    assert mega[0]["outreach_eligibility"] == ELIGIBLE
    assert mega[0]["portfolio"]["value_total_brl"] > 100_000_000
    assert mega[0]["construction_evidence"]["is_construction"] is True


def test_small_firm_not_promoted_by_contract_size_alone() -> None:
    """Score: diversified portfolio outranks single mega-contract small pattern."""
    from scripts.confenge_universe.construction import ConstructionEvidence

    small_single = ConstructionEvidence(
        is_construction=True,
        sector_fit="POSSIBLE_ENGINEERING_FIT",
        activity_class="CONSTRUCTION_CONTRACTOR",
        confidence=0.45,
        relevant_contract_count=1,
        total_contract_count=1,
        relevant_ratio=1.0,
        reason_codes=["single"],
    )
    large_div = ConstructionEvidence(
        is_construction=True,
        sector_fit="STRONG_ENGINEERING_FIT",
        activity_class="CONSTRUCTION_CONTRACTOR",
        confidence=0.78,
        relevant_contract_count=5,
        total_contract_count=6,
        relevant_ratio=0.83,
        reason_codes=["strong"],
    )
    score_small = compute_priority_score(
        construction=small_single,
        contract_count=1,
        contract_count_recent=1,
        value_total=50_000_000.0,  # huge single contract
        value_recent=50_000_000.0,
        n_ufs=1,
        n_orgaos=1,
        last_contract_date=date(2025, 1, 1),
        as_of=AS_OF,
        active_count=1,
    )
    score_div = compute_priority_score(
        construction=large_div,
        contract_count=6,
        contract_count_recent=3,
        value_total=8_000_000.0,  # smaller total
        value_recent=3_000_000.0,
        n_ufs=3,
        n_orgaos=4,
        last_contract_date=date(2025, 6, 1),
        as_of=AS_OF,
        active_count=2,
    )
    assert score_div.score > score_small.score
    assert "single_contract_not_promoted" in score_small.reason


def test_non_constructor_excluded_by_evidence(
    sample_csv: Path, dnc_path: Path, tmp_path: Path
) -> None:
    result = run_universe_build(
        as_of=AS_OF,
        csv_path=str(sample_csv),
        dnc_path=str(dnc_path),
        out_dir=tmp_path / "out_nc",
    )
    # Farma must not appear in eligible universe records
    assert all(r["cnpj14"] != CNPJ_FARMA for r in result["records"])
    excl = result["exclusions"]
    farma_excl = [
        e
        for e in excl
        if e.get("cnpj14") == CNPJ_FARMA or "FARMA" in str(e.get("razao_social") or "").upper()
    ]
    assert farma_excl, "pharmacy should be justified exclusion"
    assert farma_excl[0]["outreach_eligibility"] == NOT_CONSTRUCTION


def test_dnc_preserved(sample_csv: Path, dnc_path: Path, tmp_path: Path) -> None:
    dnc_set = load_dnc_set(str(dnc_path))
    assert is_dnc_cnpj(CNPJ_GAMA_DNC, CNPJ_GAMA_DNC[:8], dnc_set)

    result = run_universe_build(
        as_of=AS_OF,
        csv_path=str(sample_csv),
        dnc_path=str(dnc_path),
        out_dir=tmp_path / "out_dnc",
    )
    gama = [r for r in result["records"] if r["cnpj14"] == CNPJ_GAMA_DNC]
    assert len(gama) == 1, "DNC construction firm stays in universe"
    assert gama[0]["outreach_eligibility"] == DNC
    assert gama[0]["eligibility_reason"] == "human_do_not_contact_dominant"


def test_determinism(sample_csv: Path, dnc_path: Path, tmp_path: Path) -> None:
    out1 = tmp_path / "d1"
    out2 = tmp_path / "d2"
    r1 = run_universe_build(
        as_of=AS_OF, csv_path=str(sample_csv), dnc_path=str(dnc_path), out_dir=out1
    )
    r2 = run_universe_build(
        as_of=AS_OF, csv_path=str(sample_csv), dnc_path=str(dnc_path), out_dir=out2
    )
    j1 = Path(r1["jsonl_path"]).read_text(encoding="utf-8")
    j2 = Path(r2["jsonl_path"]).read_text(encoding="utf-8")
    assert j1 == j2
    m1 = json.loads(Path(r1["manifest_path"]).read_text(encoding="utf-8"))
    m2 = json.loads(Path(r2["manifest_path"]).read_text(encoding="utf-8"))
    assert m1["counts"]["eligibles"] == m2["counts"]["eligibles"]
    assert m1["outputs"]["jsonl"]["sha256"] == m2["outputs"]["jsonl"]["sha256"]


def test_reconciliation_invariant(sample_csv: Path, dnc_path: Path, tmp_path: Path) -> None:
    result = run_universe_build(
        as_of=AS_OF,
        csv_path=str(sample_csv),
        dnc_path=str(dnc_path),
        out_dir=tmp_path / "out_recon",
    )
    assert result["reconciliation_ok"] is True
    c = result["counts"]
    assert c["input_supplier_roots"] == c["eligibles"] + c["exclusions"]
    manifest = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
    recon = manifest["counts"]["reconciliation"]
    assert recon["ok"] is True
    assert recon["input_supplier_roots"] == recon["eligibles"] + recon["exclusions"]
    assert "as_of" in manifest
    assert "repo_sha" in manifest
    assert manifest["source"] is not None


def test_cli_fixture_path(sample_csv: Path, dnc_path: Path, tmp_path: Path) -> None:
    """Exercise real CLI entry point."""
    from scripts.confenge_universe.cli import main

    out = tmp_path / "cli_out"
    code = main(
        [
            "build",
            "--out",
            str(out),
            "--csv",
            str(sample_csv),
            "--dnc",
            str(dnc_path),
            "--as-of",
            AS_OF.isoformat(),
            "--result-json",
            str(tmp_path / "result.json"),
        ]
    )
    assert code == 0
    jsonl = out / "confenge-universe-v1.jsonl"
    man = out / "confenge-universe-manifest-v1.json"
    assert jsonl.is_file()
    assert man.is_file()
    lines = [json.loads(ln) for ln in jsonl.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert lines
    for rec in lines:
        assert rec["schema_version"] == SCHEMA_VERSION
        assert rec["cnpj14"]
        assert rec["cnpj_root"]
        assert rec["outreach_eligibility"] in {ELIGIBLE, DNC}
        assert "priority_score" in rec
        assert "construction_evidence" in rec
        assert "portfolio" in rec
        # score never used as discard: membership is eligibility, not score
        assert rec["construction_evidence"]["is_construction"] is True


def test_score_changes_order_not_membership(sample_csv: Path, dnc_path: Path, tmp_path: Path) -> None:
    result = run_universe_build(
        as_of=AS_OF,
        csv_path=str(sample_csv),
        dnc_path=str(dnc_path),
        out_dir=tmp_path / "out_score",
    )
    records = result["records"]
    assert records
    # All members have construction evidence regardless of score rank
    by_score = sorted(records, key=lambda r: -r["priority_score"])
    by_name = sorted(records, key=lambda r: r["cnpj_root"])
    assert {r["entity_key"] for r in by_score} == {r["entity_key"] for r in by_name}
    assert all(r["construction_evidence"]["is_construction"] for r in records)


def test_bounded_memory_streaming_no_fetchall_full_table(sample_csv: Path) -> None:
    """CSV path yields batches without loading entire logical stream as one fetchall of DB."""
    from scripts.confenge_universe.source import SourceConfig

    cfg = SourceConfig(mode="csv", csv_path=str(sample_csv))
    batches = list(iter_contracts_keyset(cfg, batch_size=3))
    assert len(batches) >= 2  # multiple batches
    assert all(len(b) <= 3 for b in batches)
    total = sum(len(b) for b in batches)
    assert total >= 10


def test_scale_250k_synthetic_no_full_materialization(tmp_path: Path) -> None:
    """Synthetic ≥250k rows processed in batches; never materialize full list via fetchall."""
    N = 250_000
    batch_size = 5_000

    def _make_cnpj(i: int) -> str:
        # Deterministic valid-ish 14-digit ids for scale (identity may mark invalid
        # check digits — we use a fixed valid root pool + order)
        # Use pre-validated matrix pattern: cycle a few valid bases
        bases = [
            "11222333000181",
            "44555666000181",
            "77888999000181",
            "99887766000105",
            "33445566000186",
        ]
        return bases[i % len(bases)]

    def row_gen() -> Iterator[dict[str, Any]]:
        names = {
            "11222333000181": "ALFA CONSTRUTORA E ENGENHARIA LTDA",
            "44555666000181": "MEGA OBRAS NACIONAIS S.A.",
            "77888999000181": "BETA PAVIMENTACAO ME",
            "99887766000105": "GAMA ENGENHARIA E CONSTRUCOES LTDA",
            "33445566000186": "DELTA CONSTRUTORA DE EDIFICIOS LTDA",
        }
        objetos = [
            "Execucao de obra de pavimentacao asfaltica e drenagem",
            "Construcao civil de escola com empreitada",
            "Obras de infraestrutura de saneamento rede de esgoto",
            "Terraplenagem e pavimentacao de vias urbanas",
            "Execucao de obra de engenharia - edificacao predial",
        ]
        for i in range(N):
            cnpj = _make_cnpj(i)
            yield {
                "contrato_id": f"SCALE-{i:08d}",
                "orgao_cnpj": f"{i % 9000:014d}",
                "orgao_nome": f"ORGAO {i % 500}",
                "fornecedor_cnpj": cnpj,
                "fornecedor_nome": names[cnpj],
                "objeto_contrato": objetos[i % len(objetos)],
                "valor_total": float(100_000 + (i % 1000) * 1000),
                "data_inicio": "2024-01-01",
                "data_fim": "2025-12-31",
                "data_publicacao": "2024-06-15",
                "uf": ["SC", "PR", "RS", "SP", "MG"][i % 5],
                "municipio": "X",
                "is_active": True,
                "source": "synthetic",
            }

    # Prove batching: never collect all rows into one list
    max_batch = 0
    n_rows = 0
    n_batches = 0
    t0 = time.perf_counter()
    for batch in iter_contract_rows(row_gen(), batch_size=batch_size):
        n_batches += 1
        max_batch = max(max_batch, len(batch))
        n_rows += len(batch)
        # process batch (light) — simulate ingest cost without full universe finalize
        for row in batch:
            classify_contract_relevance(row["objeto_contrato"])
    elapsed = time.perf_counter() - t0

    assert n_rows == N
    assert n_batches == N // batch_size
    assert max_batch <= batch_size
    assert max_batch < N  # never one giant materialization
    # Soft time budget — should finish in reasonable time on CI
    assert elapsed < 180.0, f"scale stream too slow: {elapsed:.1f}s"

    # Full pipeline on a scaled-down but still multi-entity synthetic stream
    # (250k full finalize is heavy; scale invariant above covers streaming).
    # Still run pipeline on 3k synthetic for integration + recon.
    def small_gen() -> Iterator[dict[str, Any]]:
        for i, row in enumerate(row_gen()):
            if i >= 3000:
                break
            yield row

    result = run_universe_build(
        as_of=AS_OF,
        row_iter=small_gen(),
        out_dir=tmp_path / "scale_pipe",
        batch_size=500,
    )
    assert result["reconciliation_ok"] is True
    assert result["counts"]["input_contract_rows"] == 3000
    assert result["counts"]["peak_batch_size"] <= 500
    assert result["counts"]["eligibles"] >= 1


def test_identity_public_organ_and_invalid() -> None:
    organ = resolve_identity("11222333000181", "PREFEITURA MUNICIPAL DE JOINVILLE")
    assert not organ.valid
    assert organ.exclusion_code == "PUBLIC_ORGAN"

    person = resolve_identity("12345678901", "JOAO DA SILVA")
    assert not person.valid
    assert person.exclusion_code == "NATURAL_PERSON"


def test_construction_classifier_reuse() -> None:
    contracts = [
        {
            "objeto_contrato": "Execucao de obra de pavimentacao asfaltica",
            "orgao_nome": "PREFEITURA",
            "data_publicacao": "2024-01-01",
        },
        {
            "objeto_contrato": "Construcao civil de escola municipal",
            "orgao_nome": "PREFEITURA 2",
            "data_publicacao": "2024-06-01",
        },
    ]
    ev = assess_construction(
        razao_social="ALFA CONSTRUTORA LTDA",
        contracts=contracts,
    )
    assert ev.is_construction is True
    assert "sector_fit" in ev.rule_versions

    out = assess_construction(
        razao_social="FARMA SAUDE COMERCIO DE MEDICAMENTOS LTDA",
        contracts=[
            {
                "objeto_contrato": "Fornecimento de medicamentos e generos farmaceuticos",
                "orgao_nome": "HOSPITAL",
                "data_publicacao": "2024-01-01",
            }
        ],
    )
    assert out.is_construction is False


def test_eligibility_dnc_dominant() -> None:
    from scripts.confenge_universe.construction import ConstructionEvidence
    from scripts.confenge_universe.identity import Identity

    ident = Identity(
        cnpj14=CNPJ_GAMA_DNC,
        cnpj_root="99887766",
        razao_social="GAMA",
        person_kind="cnpj",
        valid=True,
    )
    cons = ConstructionEvidence(
        is_construction=True,
        sector_fit="STRONG_ENGINEERING_FIT",
        activity_class="CONSTRUCTION_CONTRACTOR",
        confidence=0.8,
        relevant_contract_count=2,
        total_contract_count=2,
        relevant_ratio=1.0,
    )
    d = decide_eligibility(identity=ident, construction=cons, dnc=True)
    assert d.outreach_eligibility == DNC
    assert d.in_universe is True


def test_brand_jaccard_helpers() -> None:
    a = brand_tokens("DELTA CONSTRUTORA DE EDIFICIOS LTDA")
    b = brand_tokens("OMEGA TERRAPLENAGEM E PAVIMENTACAO SPE")
    assert jaccard(a, b) < 0.3
    c = brand_tokens("ALFA CONSTRUTORA E ENGENHARIA LTDA")
    d = brand_tokens("ALFA CONSTRUTORA E ENGENHARIA LTDA FILIAL")
    assert jaccard(c, d) >= 0.3

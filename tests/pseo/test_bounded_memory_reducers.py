"""Adversarial tests: streaming reducers must not grow O(N) Python value/date lists."""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from scripts.pseo.aggregate import _pct
from scripts.pseo.archetypes import ClassifiedContract
from scripts.pseo.staging import StagingStore
from scripts.pseo.stream_aggregate import (
    build_agencies_streaming,
    build_archetypes_streaming,
    build_competition_streaming,
    build_markets_streaming,
    build_prices_streaming,
    freshness_bounds_streaming,
    freshness_dates_streaming,
    get_last_reducer_mem_profile,
)
from scripts.pseo.value_spill import METHOD_ID, ValueSpillStore


def _make_contract(i: int, *, uf: str = "SC", arch: str = "pavimentacao-infraestrutura-viaria") -> ClassifiedContract:
    # Objects that hit known archetype patterns when possible; archetypes forced.
    return ClassifiedContract(
        contrato_id=f"c-{i}",
        orgao_cnpj=f"{10000000 + (i % 50):08d}",
        orgao_nome=f"Prefeitura Teste {i % 50}",
        fornecedor_cnpj=f"{20000000 + (i % 30):08d}",
        fornecedor_nome=f"Fornecedor {i % 30}",
        objeto=f"Servicos de pavimentacao asfaltica trecho {i}",
        valor=float(50_000 + (i % 1000) * 137.5),
        data_inicio="2024-01-01",
        data_fim="2024-12-31",
        data_publicacao=f"2024-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}",
        uf=uf,
        municipio="Florianopolis",
        source="pncp",
        archetypes=[arch],
    )


def _fill_store(n: int) -> StagingStore:
    st = StagingStore()
    batch: list[ClassifiedContract] = []
    for i in range(n):
        batch.append(_make_contract(i))
        if len(batch) >= 500:
            st.insert_classified_batch(batch)
            batch.clear()
    if batch:
        st.insert_classified_batch(batch)
    st.commit()
    return st


def test_value_spill_percentile_matches_pct_index_rule():
    spill = ValueSpillStore()
    vals = [float(x) for x in range(1, 101)]
    for v in vals:
        spill.add("t", "b", v)
    spill.commit()
    assert spill.percentile("t", "b", 50) == _pct(vals, 50)
    assert spill.percentile("t", "b", 25) == _pct(vals, 25)
    assert spill.percentile("t", "b", 75) == _pct(vals, 75)
    assert spill.methodology()["method_id"] == METHOD_ID
    assert spill.methodology()["exact"] is True
    assert spill.methodology()["approximate"] is False
    spill.secure_delete()


def test_reducers_no_linear_value_or_date_vectors():
    """Scale N and assert instrumented value/date list cells stay 0."""
    profiles = []
    for n in (200, 800, 1600):
        st = _fill_store(n)
        try:
            build_markets_streaming(st, open_bids=[], min_contracts=1, min_buyers=1)
            build_agencies_streaming(st, open_bids=[], min_contracts=1)
            build_prices_streaming(st, min_obs=1)
            build_competition_streaming(st, min_contracts=1)
            build_archetypes_streaming(st)
            freshness_bounds_streaming(st)
            prof = get_last_reducer_mem_profile()
            profiles.append((n, prof))
            for name in ("markets", "agencies", "prices", "competition", "archetypes", "freshness"):
                assert name in prof, prof.keys()
                assert prof[name].get("python_value_vector_cells", 0) == 0, (name, prof[name])
                assert prof[name].get("python_date_list_cells", 0) == 0, (name, prof[name])
                if name == "competition":
                    assert prof[name].get("python_band_value_list_cells", 0) == 0
        finally:
            st.secure_delete()
    # Buckets must not grow linearly with N when key space is fixed (~1 arch × 1 UF)
    market_buckets = [p["markets"]["buckets"] for _, p in profiles]
    assert market_buckets[0] == market_buckets[-1] or market_buckets[-1] <= market_buckets[0] + 5


def test_freshness_shim_not_on():
    st = _fill_store(300)
    try:
        bounds = freshness_bounds_streaming(st)
        assert bounds["contract_min"] is not None
        assert bounds["contract_max"] is not None
        assert bounds["contract_n_dates"] == 300
        c_dates, b_dates = freshness_dates_streaming(st)
        # shim returns at most min/max (≤2), never N
        assert len(c_dates) <= 2
        assert len(b_dates) <= 2
        assert get_last_reducer_mem_profile()["freshness"]["python_date_list_cells"] == 0
    finally:
        st.secure_delete()


def test_source_has_no_defaultdict_list_for_vals_or_dates():
    """Static guard: stream_aggregate must not reintroduce vals/dates list reducers."""
    src = Path("scripts/pseo/stream_aggregate.py").read_text(encoding="utf-8")
    # Forbidden O(N) reducer patterns (value vectors / full date lists / band value lists)
    assert "vals: dict" not in src
    assert "dates: dict" not in src
    assert "band_vals" not in src
    assert "per_arch_vals" not in src
    assert "contract_dates: list[str] = []" not in src
    assert "bid_dates: list[str] = []" not in src
    assert "ValueSpillStore" in src
    assert "_ScalarPeriod" in src
    assert "_BandHist" in src
    assert "sqlite_order_offset_v1" in Path("scripts/pseo/value_spill.py").read_text(
        encoding="utf-8"
    )
    # Bounded sample lists remain OK (examples capped by _MAX_EXAMPLES)
    assert "examples:" in src


def test_load_all_still_forbidden():
    st = StagingStore()
    try:
        with pytest.raises(RuntimeError, match="load_all_classified"):
            st.load_all_classified()
        with pytest.raises(RuntimeError, match="load_all_bids"):
            st.load_all_bids()
    finally:
        st.secure_delete()


def test_stream_aggregate_source_forbids_load_all_calls():
    src = inspect.getsource(
        __import__("scripts.pseo.stream_aggregate", fromlist=["*"])
    )
    assert "load_all_classified(" not in src
    assert "load_all_bids(" not in src

"""Chunked, memory-bounded extraction helpers for pSEO (no fetchall on large paths).

Used by pipeline.load_from_db and by scale benchmarks / unit tests.
"""

from __future__ import annotations

import resource
import time
from collections.abc import Callable, Iterable, Iterator
from typing import Any


def peak_rss_mb() -> float:
    """Peak resident set size in MiB (Linux ru_maxrss is KiB)."""
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # Linux: KiB; macOS: bytes — normalize heuristically
    if usage > 10_000_000:  # likely bytes
        return usage / (1024 * 1024)
    return usage / 1024.0


def fetch_chunked(
    cur: Any,
    sql: str,
    *,
    chunk_size: int = 5_000,
) -> list[dict[str, Any]]:
    """Read all rows via fetchmany only (never fetchall).

    Materializes the full list — prefer ``iter_fetch_chunked`` + incremental
    aggregation when memory must stay bounded.
    """
    if chunk_size < 1:
        raise ValueError("chunk_size must be >= 1")
    cur.execute(sql)
    rows: list[dict[str, Any]] = []
    while True:
        if not hasattr(cur, "fetchmany"):
            raise RuntimeError("cursor must support fetchmany (fetchall forbidden on this path)")
        batch = cur.fetchmany(chunk_size)
        if not batch:
            break
        rows.extend(dict(r) for r in batch)
    return rows


def iter_fetch_chunked(
    cur: Any,
    sql: str,
    *,
    chunk_size: int = 5_000,
) -> Iterator[list[dict[str, Any]]]:
    """Yield batches from a server-side / synthetic cursor via fetchmany only."""
    if chunk_size < 1:
        raise ValueError("chunk_size must be >= 1")
    cur.execute(sql)
    while True:
        batch = cur.fetchmany(chunk_size)
        if not batch:
            break
        yield [dict(r) for r in batch]


def reduce_rows_chunked(
    batches: Iterable[list[dict[str, Any]]],
    *,
    reducer: Callable[[dict[str, Any], dict[str, Any]], None],
    initial: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply reducer to each row across batches without retaining all rows."""
    state: dict[str, Any] = dict(initial or {})
    state.setdefault("n_rows", 0)
    state.setdefault("n_batches", 0)
    for batch in batches:
        state["n_batches"] = int(state["n_batches"]) + 1
        for row in batch:
            state["n_rows"] = int(state["n_rows"]) + 1
            reducer(state, row)
    return state


def benchmark_synthetic_extraction(
    n_rows: int = 250_000,
    *,
    chunk_size: int = 5_000,
) -> dict[str, Any]:
    """Run a synthetic ≥n_rows extraction using fetchmany-only cursor.

    Proves structural scale path: no fetchall, timed, peak RSS recorded,
    deterministic row count.
    """
    if n_rows < 1:
        raise ValueError("n_rows must be >= 1")

    class _SyntheticCursor:
        """Minimal DB-API style cursor with fetchmany only (no fetchall)."""

        def __init__(self, total: int) -> None:
            self._total = total
            self._i = 0
            self._executed = False
            self.fetchall_calls = 0
            self.fetchmany_calls = 0

        def execute(self, sql: str, params: Any = None) -> None:  # noqa: ARG002
            self._executed = True
            self._i = 0

        def fetchmany(self, size: int = 1) -> list[dict[str, Any]]:
            if not self._executed:
                raise RuntimeError("execute() required before fetchmany")
            self.fetchmany_calls += 1
            if self._i >= self._total:
                return []
            end = min(self._i + size, self._total)
            batch = [
                {
                    "contrato_id": f"c-{i}",
                    "orgao_cnpj": f"{i % 10_000:08d}",
                    "objeto_contrato": "Pavimentação asfáltica em vias urbanas do município",
                    "valor_total": 1000.0 + (i % 500),
                    "uf": "SC" if i % 2 == 0 else "PR",
                    "source": "synthetic",
                }
                for i in range(self._i, end)
            ]
            self._i = end
            return batch

        def fetchall(self) -> list[dict[str, Any]]:
            self.fetchall_calls += 1
            raise AssertionError("fetchall is forbidden on the large-table path")

    def _reduce(state: dict[str, Any], row: dict[str, Any]) -> None:
        uf = str(row.get("uf") or "?")
        by_uf = state.setdefault("by_uf", {})
        by_uf[uf] = int(by_uf.get(uf, 0)) + 1
        state["sum_valor"] = float(state.get("sum_valor") or 0.0) + float(row.get("valor_total") or 0)

    cur = _SyntheticCursor(n_rows)
    t0 = time.perf_counter()
    rss0 = peak_rss_mb()
    batches = iter_fetch_chunked(cur, "SELECT * FROM synthetic", chunk_size=chunk_size)
    result = reduce_rows_chunked(batches, reducer=_reduce, initial={"sum_valor": 0.0, "by_uf": {}})
    elapsed = time.perf_counter() - t0
    rss1 = peak_rss_mb()

    out = {
        "ok": True,
        "n_rows": int(result["n_rows"]),
        "n_batches": int(result["n_batches"]),
        "expected_rows": n_rows,
        "chunk_size": chunk_size,
        "elapsed_sec": round(elapsed, 4),
        "rss_start_mb": round(rss0, 2),
        "rss_peak_mb": round(rss1, 2),
        "rss_delta_mb": round(max(0.0, rss1 - rss0), 2),
        "fetchmany_calls": cur.fetchmany_calls,
        "fetchall_calls": cur.fetchall_calls,
        "by_uf": result.get("by_uf"),
        "sum_valor": round(float(result.get("sum_valor") or 0.0), 2),
        "fetch_mode": "synthetic_fetchmany_only",
        "no_fetchall": cur.fetchall_calls == 0,
    }
    if out["n_rows"] != n_rows:
        out["ok"] = False
    if out["fetchall_calls"] != 0:
        out["ok"] = False
    # Expected batch count: ceil(n/chunk) + final empty fetchmany
    min_batches = (n_rows + chunk_size - 1) // chunk_size
    if out["n_batches"] != min_batches:
        out["ok"] = False
        out["batch_mismatch"] = {"got": out["n_batches"], "expected": min_batches}
    return out

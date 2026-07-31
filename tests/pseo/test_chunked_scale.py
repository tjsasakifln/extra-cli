"""Scale proof: ≥250k synthetic rows via fetchmany-only path (no fetchall)."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.pseo.chunked_extract import benchmark_synthetic_extraction, fetch_chunked
from scripts.pseo.pipeline import _fetch_chunked

SCRATCH = Path("/tmp/grok-goal-582c99c4809e/implementer")
CAMPAIGN_LOG = Path("docs/ops/campaigns/EXTRA-PRS-186-187-TRUST-HARDENING-01/logs")


def test_fetch_chunked_never_calls_fetchall():
    class Cur:
        def __init__(self):
            self.i = 0
            self.fetchall_calls = 0
            self.fetchmany_calls = 0

        def execute(self, sql, params=None):  # noqa: ARG002
            self.i = 0

        def fetchmany(self, size=1):
            self.fetchmany_calls += 1
            if self.i >= 12:
                return []
            batch = [{"id": j} for j in range(self.i, min(self.i + size, 12))]
            self.i += len(batch)
            return batch

        def fetchall(self):
            self.fetchall_calls += 1
            raise AssertionError("fetchall forbidden")

    cur = Cur()
    rows = fetch_chunked(cur, "SELECT 1", chunk_size=5)
    assert len(rows) == 12
    assert cur.fetchall_calls == 0
    assert cur.fetchmany_calls >= 3
    # pipeline alias uses same helper
    cur2 = Cur()
    rows2 = _fetch_chunked(cur2, "SELECT 1", chunk_size=5)
    assert len(rows2) == 12
    assert cur2.fetchall_calls == 0


def test_synthetic_250k_chunked_benchmark_deterministic():
    report = benchmark_synthetic_extraction(250_000, chunk_size=5_000)
    # Persist evidence for campaign
    SCRATCH.mkdir(parents=True, exist_ok=True)
    CAMPAIGN_LOG.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    (SCRATCH / "pseo-250k-benchmark.json").write_text(payload, encoding="utf-8")
    (CAMPAIGN_LOG / "pseo-250k-benchmark.json").write_text(payload, encoding="utf-8")

    assert report["ok"] is True, report
    assert report["n_rows"] == 250_000
    assert report["n_batches"] == 50  # 250000/5000
    assert report["fetchall_calls"] == 0
    assert report["no_fetchall"] is True
    assert report["fetchmany_calls"] >= 50
    assert report["elapsed_sec"] > 0
    assert report["rss_peak_mb"] >= 0
    # Determinism: second run same aggregates
    report2 = benchmark_synthetic_extraction(250_000, chunk_size=5_000)
    assert report2["n_rows"] == report["n_rows"]
    assert report2["sum_valor"] == report["sum_valor"]
    assert report2["by_uf"] == report["by_uf"]
    # Memory: incremental reduce should not explode — soft ceiling (CI machines vary)
    # 250k small dicts if fully retained would be much larger; we only keep aggregates.
    assert report["rss_delta_mb"] < 800, f"unexpected memory growth: {report}"

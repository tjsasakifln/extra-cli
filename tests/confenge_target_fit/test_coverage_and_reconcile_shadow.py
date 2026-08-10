"""Coverage watermark + SHADOW-aware reconcile materialization authority."""

from __future__ import annotations

from scripts.confenge_target_fit.coverage import (
    TARGET_FIT_COVERAGE_THRESHOLD,
    build_coverage_snapshot,
    classify_coverage_mode,
    coverage_ratio,
)
from scripts.confenge_target_fit.reconcile import _load_materialized_index, iter_universe_roots


class _Cur:
    def __init__(self, responses: list):
        self._responses = list(responses)
        self._last = None

    def execute(self, sql, params=None):  # noqa: ANN001
        if not self._responses:
            self._last = []
            return
        self._last = self._responses.pop(0)

    def fetchall(self):
        if isinstance(self._last, list):
            return self._last
        return []

    def fetchone(self):
        if isinstance(self._last, list):
            return self._last[0] if self._last else None
        return self._last


class _Ctx:
    def __init__(self, cur):
        self._cur = cur

    def __enter__(self):
        return self._cur

    def __exit__(self, *a):  # noqa: ANN002
        return False


class _Conn:
    def __init__(self, responses: list):
        self._cur = _Cur(responses)

    def cursor(self):
        return _Ctx(self._cur)

    def rollback(self):
        return None


def test_coverage_ratio_and_threshold() -> None:
    assert coverage_ratio(materialized_company_count=995, canonical_company_count=1000) == 0.995
    assert coverage_ratio(materialized_company_count=0, canonical_company_count=0) is None
    snap = build_coverage_snapshot(
        canonical_company_count=1000,
        materialized_company_count=1000,
        expected_company_roots=1000,
        visited_company_roots=1000,
        unexplained_missing=0,
        pagination_exhausted_normally=True,
        last_full_reconcile_completed_at="2026-08-10T00:00:00+00:00",
    )
    assert snap["coverage_ratio"] == 1.0
    assert snap["FULL_NATIONAL_READY"] is True
    assert snap["coverage_mode"] == "FULLY_RECONCILED"
    assert TARGET_FIT_COVERAGE_THRESHOLD == 0.995


def test_coverage_mode_bootstrapping_and_partial() -> None:
    assert (
        classify_coverage_mode(
            coverage=0.02,
            last_full_reconcile_completed_at=None,
            unexplained_missing=0,
            pagination_exhausted_normally=False,
        )
        == "BOOTSTRAPPING"
    )
    assert (
        classify_coverage_mode(
            coverage=0.02,
            last_full_reconcile_completed_at="2026-08-10T00:00:00+00:00",
            unexplained_missing=0,
            pagination_exhausted_normally=True,
        )
        == "PARTIAL"
    )
    assert (
        classify_coverage_mode(
            coverage=0.999,
            last_full_reconcile_completed_at="2026-08-10T00:00:00+00:00",
            unexplained_missing=5,
            pagination_exhausted_normally=True,
        )
        == "PARTIAL"
    )


def test_load_materialized_index_prefers_shadow_in_shadow_mode() -> None:
    shadow_rows = [
        {
            "company_key": "cnpj_root:11111111",
            "cnpj_raiz": "11111111",
            "target_fit_version": "confenge-target-fit-v1",
            "input_fingerprint": "a",
            "shadow_class": "TARGET_CONFIRMED",
        }
    ]
    conn = _Conn([shadow_rows])
    idx = _load_materialized_index(conn, mode="SHADOW")
    assert "cnpj_root:11111111" in idx
    assert idx["cnpj_root:11111111"]["target_fit_class"] == "TARGET_CONFIRMED"


def test_iter_universe_roots_multi_page_no_early_exit() -> None:
    page1 = [{"raiz": f"{i:08d}"} for i in range(1, 501)]
    page2 = [{"raiz": f"{i:08d}"} for i in range(501, 510)]
    # responses: columns, page1, page2
    conn = _Conn(
        [
            [{"column_name": "fornecedor_cnpj"}],
            page1,
            page2,
        ]
    )
    roots = iter_universe_roots(conn, page_size=500)
    assert len(roots) == 509
    assert roots[0] == "00000001"
    assert roots[-1] == "00000509"

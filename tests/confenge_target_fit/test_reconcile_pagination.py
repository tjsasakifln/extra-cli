"""Regression: reconcile universe root pagination must not stop after first page."""

from __future__ import annotations

from scripts.confenge_target_fit.reconcile import iter_universe_roots


class _FakeCursor:
    def __init__(self, pages: list[list[dict]]):
        self._pages = list(pages)
        self._last: list[dict] = []
        self.queries: list[tuple] = []

    def execute(self, sql: str, params=None) -> None:  # noqa: ANN001
        self.queries.append((sql, params))
        if "information_schema.columns" in sql:
            self._last = [{"column_name": "fornecedor_cnpj"}]
            return
        # page query
        if not self._pages:
            self._last = []
            return
        self._last = self._pages.pop(0)

    def fetchall(self):
        return list(self._last)


class _FakeConn:
    def __init__(self, pages: list[list[dict]]):
        self._cur = _FakeCursor(pages)

    def cursor(self):
        return _FakeCursorContext(self._cur)


class _FakeCursorContext:
    def __init__(self, cur: _FakeCursor):
        self._cur = cur

    def __enter__(self):
        return self._cur

    def __exit__(self, *args):  # noqa: ANN002
        return False


def test_iter_universe_roots_continues_after_filtered_invalid_root() -> None:
    """If page_size=500 and one invalid root is filtered, must still fetch page 2.

    Production bug: comparing *filtered* batch length to page_size stopped at
    universe_roots≈499 and left continuous CONFIRMED stuck at 3.
    """
    page1 = [{"raiz": f"{i:08d}"} for i in range(1, 500)]
    page1.append({"raiz": "00000000"})  # invalid → filtered
    assert len(page1) == 500
    page2 = [{"raiz": f"{i:08d}"} for i in range(500, 520)]
    conn = _FakeConn([page1, page2])
    roots = iter_universe_roots(conn, page_size=500)
    assert "00000000" not in roots
    assert "00000001" in roots
    assert "00000500" in roots
    assert "00000519" in roots
    assert len(roots) == 499 + 20  # page1 filtered + full page2

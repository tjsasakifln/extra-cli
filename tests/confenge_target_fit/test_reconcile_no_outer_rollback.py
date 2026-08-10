"""Regression: optional-table probe must not wipe dirty enqueues."""

from __future__ import annotations

from scripts.confenge_target_fit.reconcile import count_canonical_eligible_roots


class _Cur:
    def __init__(self):
        self.ops: list[str] = []
        self._fail_next_select = True

    def execute(self, sql, params=None):  # noqa: ANN001
        s = " ".join(str(sql).split())
        self.ops.append(s)
        if s.startswith("SELECT COUNT") and self._fail_next_select:
            self._fail_next_select = False
            raise RuntimeError("relation does not exist")

    def fetchone(self):
        return {"n": 42}


class _Ctx:
    def __init__(self, cur):
        self._cur = cur

    def __enter__(self):
        return self._cur

    def __exit__(self, *a):  # noqa: ANN002
        return False


class _Conn:
    def __init__(self):
        self.cur = _Cur()
        self.rollbacks = 0

    def cursor(self):
        return _Ctx(self.cur)

    def rollback(self):
        self.rollbacks += 1


def test_count_canonical_uses_savepoint_not_outer_rollback() -> None:
    conn = _Conn()
    # First SQL fails, second would succeed if reached with fail flag off
    n = count_canonical_eligible_roots(conn)
    assert conn.rollbacks == 0
    assert any("SAVEPOINT" in o for o in conn.cur.ops)
    assert any("ROLLBACK TO SAVEPOINT" in o for o in conn.cur.ops)
    # may return None or 42 depending on second query path
    assert n is None or n == 42

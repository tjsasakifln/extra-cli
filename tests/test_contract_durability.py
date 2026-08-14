"""#314 fence, #319 checkpoint location, #306 identity, #304 pagination."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.contracts_truth import (
    CheckpointLocationError,
    PaginationReconcile,
    PostgresWriterFence,
    WriterFenceBusyError,
    WriterFenceBypassError,
    canonical_contract_identity,
    refuse_writer_bypass,
    replay_adapters_to_canonical,
    resolve_checkpoint_dir,
)


class _FakeAdvisoryConn:
    """Minimal connection that implements pg_try_advisory_lock / unlock."""

    held: set[int] = set()

    def __init__(self) -> None:
        self.mutations = 0
        self.statements: list[str] = []

    def cursor(self):
        return _FakeCursor(self)


class _FakeCursor:
    def __init__(self, conn: _FakeAdvisoryConn) -> None:
        self.conn = conn
        self._result: tuple[bool, ...] | None = None

    def execute(self, sql: str, params=None) -> None:
        self.conn.statements.append(sql)
        key = int(params[0]) if params else 0
        if "pg_try_advisory_lock" in sql:
            if key in _FakeAdvisoryConn.held:
                self._result = (False,)
            else:
                _FakeAdvisoryConn.held.add(key)
                self._result = (True,)
        elif "pg_advisory_unlock" in sql:
            _FakeAdvisoryConn.held.discard(key)
            self._result = (True,)
        else:
            self.conn.mutations += 1
            self._result = (True,)

    def fetchone(self):
        return self._result

    def close(self) -> None:
        return None


def test_second_writer_is_refused_before_mutation() -> None:
    _FakeAdvisoryConn.held.clear()
    fence_a = PostgresWriterFence()
    fence_b = PostgresWriterFence()
    conn_a = _FakeAdvisoryConn()
    conn_b = _FakeAdvisoryConn()
    mutated: list[str] = []
    assert fence_a.acquire(conn_a) is True

    def _mutate() -> None:
        mutated.append("wrote")
        conn_b.cursor().execute("INSERT INTO pncp_supplier_contracts VALUES (1)")

    with pytest.raises(WriterFenceBusyError):
        fence_b.run_exclusive(conn_b, _mutate)
    assert mutated == []
    assert conn_b.mutations == 0
    fence_a.release()
    fence_b.run_exclusive(conn_b, _mutate)
    assert mutated == ["wrote"]


def test_production_bypass_is_refused_outside_isolated_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("EXTRA_ISOLATED_TEST", raising=False)
    with pytest.raises(WriterFenceBypassError):
        refuse_writer_bypass(skip_lock=True)
    monkeypatch.setenv("EXTRA_ISOLATED_TEST", "1")
    refuse_writer_bypass(skip_lock=True)


def test_production_checkpoint_path_is_outside_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    durable = tmp_path / "var" / "lib" / "extra-consultoria"
    (durable / "checkpoints").mkdir(parents=True)
    inside = resolve_checkpoint_dir(
        "data/contracts_checkpoints/incremental",
        production=False,
        repo_root=repo,
        state_root=durable,
    )
    assert inside == (repo / "data/contracts_checkpoints/incremental")
    with pytest.raises(CheckpointLocationError, match="worktree"):
        resolve_checkpoint_dir(
            repo / "data" / "contracts_checkpoints",
            production=True,
            repo_root=repo,
            state_root=durable,
        )
    with pytest.raises(CheckpointLocationError, match="release tree"):
        resolve_checkpoint_dir(
            "/opt/extra-consultoria/data/contracts_checkpoints",
            production=True,
            repo_root=repo,
            state_root=durable,
        )
    ok = resolve_checkpoint_dir(
        durable / "checkpoints" / "contracts",
        production=True,
        repo_root=repo,
        state_root=durable,
    )
    assert str(ok).startswith(str(durable))
    assert "opt/extra-consultoria" not in str(ok)


def test_two_adapters_replay_to_one_canonical_and_two_observations() -> None:
    official = "12345678000199-1-000010/2026"
    crawler = canonical_contract_identity(source="pncp", official_id=official)
    adapter = canonical_contract_identity(
        source="pncp",
        official_id=official,
        parent_procurement_id="compra-1",
        fallback_parts=["12345678000199", "2026", "10"],
    )
    assert crawler.canonical_contract_id == adapter.canonical_contract_id
    assert crawler.canonical_contract_id == f"pncp:{official}"
    replayed = replay_adapters_to_canonical(
        [
            {"adapter": "contracts_crawler", "source": "pncp", "official_id": official},
            {
                "adapter": "pncp_crawler_adapter",
                "source": "pncp",
                "official_id": official,
                "fallback_parts": ["12345678000199", "2026", "10"],
            },
        ]
    )
    assert replayed["canonical_count"] == 1
    assert replayed["observation_count"] == 2
    other_source = canonical_contract_identity(source="compras_gov", official_id=official)
    assert other_source.canonical_contract_id != crawler.canonical_contract_id


def test_pagination_reconciles_and_drift_is_not_success() -> None:
    ok = PaginationReconcile()
    ok.observe_page(
        total_registros=2,
        total_paginas=1,
        items=[
            {"numeroControlePNCP": "a"},
            {"numeroControlePNCP": "b"},
        ],
    )
    ok.record_persisted(2)
    report = ok.finish()
    assert report.ok is True
    assert report.fetched == report.persisted + report.rejected

    drift = PaginationReconcile()
    drift.observe_page(total_registros=80, total_paginas=8, items=[{"numeroControlePNCP": "1"}])
    drift.observe_page(total_registros=95, total_paginas=10, items=[{"numeroControlePNCP": "2"}])
    drift.record_persisted(2)
    drifted = drift.finish()
    assert drifted.ok is False
    assert drifted.status == "source_population_drift"
    assert drifted.fetched == drifted.persisted + drifted.rejected

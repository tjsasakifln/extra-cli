"""#314 fence, #319 checkpoint location, #306 identity, #304 pagination."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.contracts_truth import (
    PG_FENCE_KEY,
    CheckpointLocationError,
    PaginationReconcile,
    PostgresWriterFence,
    WriterFenceBusyError,
    WriterFenceBypassError,
    acquire_national_writer_fence,
    canonical_contract_identity,
    refuse_writer_bypass,
    replay_adapters_to_canonical,
    resolve_checkpoint_dir,
)
from scripts.crawl.contracts_writer_lock import EXIT_LOCK_BUSY


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


def test_incremental_writer_uses_pg_fence_before_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.crawl import run_contracts_incremental as inc

    monkeypatch.delenv("CONTRACTS_SKIP_WRITER_LOCK", raising=False)
    ran: list[str] = []
    monkeypatch.setattr(inc, "_run_incremental", lambda args: ran.append("ran") or 0)

    def _connect(_dsn: str) -> _FakeAdvisoryConn:
        return _FakeAdvisoryConn()

    monkeypatch.setattr("psycopg2.connect", _connect)
    _FakeAdvisoryConn.held.clear()
    out = tmp_path / "out.json"
    rc = inc.main(
        [
            "--dsn",
            "postgresql://fence/test",
            "--days",
            "7",
            "--checkpoint-dir",
            str(tmp_path / "ckpt"),
            "--output-json",
            str(out),
        ]
    )
    assert rc == 0
    assert ran == ["ran"]
    assert PG_FENCE_KEY not in _FakeAdvisoryConn.held

    ran.clear()
    _FakeAdvisoryConn.held.add(PG_FENCE_KEY)
    rc_busy = inc.main(
        [
            "--dsn",
            "postgresql://fence/test",
            "--days",
            "7",
            "--checkpoint-dir",
            str(tmp_path / "ckpt"),
            "--output-json",
            str(out),
        ]
    )
    assert rc_busy == EXIT_LOCK_BUSY
    assert ran == []


def test_acquire_national_writer_fence_is_the_shipped_lock() -> None:
    _FakeAdvisoryConn.held.clear()
    fence = acquire_national_writer_fence("postgresql://x", connect=lambda _dsn: _FakeAdvisoryConn())
    assert fence is not None
    assert fence.owned is True
    fence.release()


def test_production_default_checkpoint_refuses_worktree_and_release_tree(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "data" / "contracts_checkpoints").mkdir(parents=True)
    with pytest.raises(CheckpointLocationError, match="worktree"):
        resolve_checkpoint_dir(
            repo / "data" / "contracts_checkpoints",
            production=True,
            repo_root=repo,
        )
    with pytest.raises(CheckpointLocationError, match="release tree"):
        resolve_checkpoint_dir(
            "/opt/extra-consultoria/data/contracts_checkpoints",
            production=True,
            repo_root=repo,
        )
    production_default = resolve_checkpoint_dir(None, production=True, repo_root=repo)
    assert str(production_default).startswith("/var/lib/extra-consultoria")
    from scripts.crawl import contracts_crawler as crawler

    assert "resolve_checkpoint_dir" in Path(crawler.__file__).read_text(encoding="utf-8")


def test_stamp_contract_truth_labels_writes_quality_not_null_valid() -> None:
    from scripts.contracts_truth import stamp_contract_truth_labels

    statements: list[str] = []

    class _Conn:
        def cursor(self):
            return self

        def execute(self, sql, params=None):
            statements.append(sql)
            self.rowcount = 1
            assert "quality_state = stamp.quality_state" in sql
            assert "COALESCE(quality_state, 'VALID')" not in sql
            payload = __import__("json").loads(params[0])
            assert payload[0]["quality_state"] == "QUARANTINED"
            assert payload[0]["status_normalized"] == "UNKNOWN"

        def close(self) -> None:
            return None

    stamped = stamp_contract_truth_labels(
        _Conn(),
        [
            {
                "contrato_id": "11111111000191-1-000001/2026",
                "status_normalized": "UNKNOWN",
                "quality_state": "QUARANTINED",
                "canonical_contract_id": "pncp:11111111000191-1-000001/2026",
            }
        ],
    )
    assert stamped == 1
    assert statements


def test_purchase_id_is_not_official_contract_id() -> None:
    ident = canonical_contract_identity(
        source="pncp",
        official_id=None,
        parent_procurement_id="12345678000199-1-000010/2026",
        fallback_parts=["12345678000199", "2026", "10"],
    )
    assert ident.method == "fallback"
    assert not ident.canonical_contract_id.endswith("12345678000199-1-000010/2026")
    assert ident.parent_procurement_id == "12345678000199-1-000010/2026"


def test_pilot_window_drift_is_not_complete() -> None:
    from scripts.crawl.run_contracts_90d_pilot import evaluate_window_completion

    fully_ok, errors = evaluate_window_completion(
        [],
        pages_exhausted=True,
        last_total_pages=2,
        page=2,
        max_pages=10,
        first_total_registros=80,
        last_total_registros=95,
    )
    assert fully_ok is False
    assert any("source_population_drift" in err for err in errors)


def test_report_ready_view_does_not_treat_null_quality_as_valid() -> None:
    sql = Path("db/migrations/091_contract_truth_durability.sql").read_text(encoding="utf-8")
    assert "COALESCE(quality_state, 'VALID')" not in sql
    assert "quality_state IS NOT NULL" in sql
    assert "status_normalized IS NOT NULL" in sql


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

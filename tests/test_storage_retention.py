from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from scripts.ops.storage_retention import (
    DEFAULT_RETENTION_LOCK_PATH,
    FilePolicy,
    RetentionError,
    RetentionLockBusyError,
    _assert_canonical_purge_safe,
    _canonical_batch,
    _parser,
    database_advisory_lock,
    delete_file_plan,
    discover_file_candidates,
    exclusive_lock,
    package_size,
    run_retention,
    select_file_plan,
)

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)


@contextmanager
def _noop_lock(_path: Path):
    yield


def _old_file(path: Path, size: int, age_days: int) -> Path:
    path.write_bytes(b"x" * size)
    timestamp = (NOW - timedelta(days=age_days)).timestamp()
    os.utime(path, (timestamp, timestamp))
    return path


def test_package_size_rejects_symlink(tmp_path: Path) -> None:
    target = tmp_path / "package.dump"
    target.write_bytes(b"123")
    link = tmp_path / "link.dump"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(RetentionError, match="regular file"):
        package_size(link)


def test_discovery_is_oldest_first_and_protects_newest(tmp_path: Path) -> None:
    _old_file(tmp_path / "old.dump", 5, 4)
    _old_file(tmp_path / "middle.dump.gz", 7, 3)
    _old_file(tmp_path / "new.dump", 11, 2)
    policy = FilePolicy(roots=(tmp_path,), min_age=timedelta(days=1), protect_newest=1)

    candidates = discover_file_candidates(policy, now=NOW)

    assert [Path(item.path).name for item in candidates] == ["old.dump"]


def test_plan_reclaims_at_least_target_with_whole_files(tmp_path: Path) -> None:
    old = _old_file(tmp_path / "old.dump", 6, 4)
    middle = _old_file(tmp_path / "middle.dump", 7, 3)
    candidates = discover_file_candidates(
        FilePolicy(roots=(tmp_path,), min_age=timedelta(), protect_newest=0), now=NOW
    )

    plan = select_file_plan(candidates, 10)
    deleted = delete_file_plan(plan, (tmp_path,))

    assert deleted == plan[0].allocated_bytes
    assert not old.exists()
    assert middle.exists()


def test_dry_run_never_deletes_and_reports_shortfall(tmp_path: Path) -> None:
    old = _old_file(tmp_path / "old.dump", 5, 4)

    report = run_retention(
        target_bytes=10_000,
        policy=FilePolicy(roots=(tmp_path,), min_age=timedelta(), protect_newest=0),
        apply=False,
        now=NOW,
    )

    assert old.exists()
    assert report.status == "PLAN_INSUFFICIENT"
    assert report.shortfall_bytes > 0
    assert report.planned_file_bytes > 0


def test_apply_protects_incoming_and_newest_old_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    old = _old_file(tmp_path / "old.dump", 10, 4)
    newest = _old_file(tmp_path / "newest.dump", 10, 3)
    incoming = _old_file(tmp_path / "incoming.dump", 8, 2)

    free_values = iter((10_000, 20_000))
    monkeypatch.setattr("scripts.ops.storage_retention.filesystem_free_bytes", lambda _path: next(free_values))
    monkeypatch.setattr("scripts.ops.storage_retention.exclusive_lock", _noop_lock)
    report = run_retention(
        target_bytes=8,
        policy=FilePolicy(roots=(tmp_path,), min_age=timedelta(), protect_newest=1),
        apply=True,
        protected_paths=(incoming,),
        lock_dir=tmp_path / "retention.lock",
        space_path=tmp_path,
        writer_fence_already_held=True,
        now=NOW,
    )

    assert report.status == "SATISFIED"
    assert report.deleted_file_bytes == report.file_candidates[0].allocated_bytes
    assert not old.exists()
    assert newest.exists()
    assert incoming.exists()


def test_changed_candidate_fails_closed_before_unlink(tmp_path: Path) -> None:
    path = _old_file(tmp_path / "old.dump", 5, 3)
    candidates = discover_file_candidates(
        FilePolicy(roots=(tmp_path,), min_age=timedelta(), protect_newest=0), now=NOW
    )
    path.write_bytes(b"changed-size")

    with pytest.raises(RetentionError, match="size changed"):
        delete_file_plan(candidates, (tmp_path,))
    assert path.exists()


def test_root_path_is_refused() -> None:
    with pytest.raises(RetentionError, match="filesystem root"):
        discover_file_candidates(FilePolicy(roots=(Path(Path.cwd().anchor),), protect_newest=0), now=NOW)


def test_exclusive_lock_fails_closed_when_busy(tmp_path: Path) -> None:
    lock = tmp_path / "retention.lock"
    try:
        with exclusive_lock(lock):
            with pytest.raises(RetentionLockBusyError, match="already held"):
                with exclusive_lock(lock):
                    pass
    except ModuleNotFoundError as exc:
        if exc.name == "fcntl":
            pytest.skip("kernel flock is only available on the Linux deployment target")
        raise


def test_cli_and_ingest_hook_share_persistent_retention_lock() -> None:
    args = _parser().parse_args(["--incoming-bytes", "1"])
    pilot_source = (
        Path(__file__).parents[1] / "scripts" / "crawl" / "run_contracts_90d_pilot.py"
    ).read_text(encoding="utf-8")
    assert args.lock_dir == DEFAULT_RETENTION_LOCK_PATH
    assert DEFAULT_RETENTION_LOCK_PATH == Path(
        "/var/lib/extra-consultoria/locks/storage-retention.lock"
    )
    assert 'os.getenv("STORAGE_RETENTION_LOCK_PATH", str(DEFAULT_RETENTION_LOCK_PATH))' in pilot_source


class FakeCursor:
    def __init__(self, rows: list[tuple[int, int]]) -> None:
        self.rows = rows
        self.sql: list[str] = []

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, sql: str, _params: object = None) -> None:
        self.sql.append(sql)

    def fetchone(self) -> tuple[int, int]:
        return self.rows.pop(0)


class FakeConnection:
    def __init__(self, rows: list[tuple[int, int]]) -> None:
        self.cursor_value = FakeCursor(rows)
        self.commit_count = 0
        self.autocommit = False

    def cursor(self) -> FakeCursor:
        return self.cursor_value

    def commit(self) -> None:
        self.commit_count += 1


class SafetyCursor:
    def __init__(self, triggers, foreign_keys) -> None:
        self.triggers = triggers
        self.foreign_keys = foreign_keys
        self.result = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, sql: str, _params=None) -> None:
        if "FROM pg_trigger" in sql:
            self.result = self.triggers
        elif "current_setting" in sql:
            self.result = [(None,)]
        elif "FROM pg_constraint" in sql:
            self.result = self.foreign_keys

    def fetchall(self):
        return list(self.result)

    def fetchone(self):
        return self.result[0]


class SafetyConnection:
    def __init__(self, triggers, foreign_keys) -> None:
        self.cursor_value = SafetyCursor(triggers, foreign_keys)

    def cursor(self):
        return self.cursor_value


def _normal_role_trigger():
    return (
        "trg_contract_role_link",
        "O",
        21,
        "trg_refresh_contract_role_link()",
        "CREATE TRIGGER trg_contract_role_link AFTER INSERT OR UPDATE OF orgao_cnpj "
        "ON public.pncp_supplier_contracts FOR EACH ROW EXECUTE FUNCTION "
        "public.trg_refresh_contract_role_link()",
    )


def test_canonical_safety_requires_exact_role_cascade_fk() -> None:
    connection = SafetyConnection([_normal_role_trigger()], [])
    with pytest.raises(RetentionError, match="expected exactly contract_role_links"):
        _assert_canonical_purge_safe(connection)


def test_canonical_safety_accepts_normal_role_trigger_and_exact_fk() -> None:
    connection = SafetyConnection(
        [_normal_role_trigger()],
        [
            (
                "contract_role_links_contract_id_fkey",
                "contract_role_links",
                "c",
                ["contract_id"],
                ["contrato_id"],
            )
        ],
    )
    _assert_canonical_purge_safe(connection)


def test_canonical_safety_rejects_unexpected_trigger() -> None:
    unexpected = ("surprise_delete", "O", 11, "surprise()", "CREATE TRIGGER surprise_delete")
    connection = SafetyConnection([_normal_role_trigger(), unexpected], [])
    with pytest.raises(RetentionError, match="unexpected user triggers"):
        _assert_canonical_purge_safe(connection)


class CanonicalBatchCursor:
    def __init__(self, connection) -> None:
        self.connection = connection
        self.result = (1, 10)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, sql: str, _params=None) -> None:
        self.connection.sql.append(sql)

    def fetchone(self):
        return self.result


class CanonicalBatchConnection:
    def __init__(self) -> None:
        self.sql = []
        self.commit_count = 0

    def cursor(self):
        return CanonicalBatchCursor(self)

    def commit(self) -> None:
        self.commit_count += 1


def test_each_canonical_apply_batch_locks_then_revalidates_before_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = CanonicalBatchConnection()
    validation_lock_counts = []

    def validate_locked(conn) -> None:
        lock_offsets = [index for index, sql in enumerate(conn.sql) if sql.startswith("LOCK TABLE")]
        assert len(lock_offsets) == len(validation_lock_counts) + 1
        validation_lock_counts.append(len(lock_offsets))

    monkeypatch.setattr("scripts.ops.storage_retention._assert_canonical_purge_safe", validate_locked)
    for _ in range(2):
        _canonical_batch(
            connection,
            cutoff=NOW,
            batch_rows=1,
            target_bytes=1,
            apply=True,
        )

    assert validation_lock_counts == [1, 2]
    assert sum(sql.startswith("LOCK TABLE") for sql in connection.sql) == 2
    assert connection.commit_count == 2


def test_history_apply_only_deletes_superseded_history_and_vacuums(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = _old_file(tmp_path / "old.dump", 4, 5)
    connection = FakeConnection([(2, 700), (1, 500), (0, 0)])
    free_values = iter((10_000, 14_096))
    monkeypatch.setattr("scripts.ops.storage_retention.filesystem_free_bytes", lambda _path: next(free_values))
    monkeypatch.setattr("scripts.ops.storage_retention.exclusive_lock", _noop_lock)

    report = run_retention(
        target_bytes=5_000,
        policy=FilePolicy(roots=(tmp_path,), min_age=timedelta(), protect_newest=0),
        apply=True,
        history_connection=connection,
        history_min_age=timedelta(days=30),
        history_batch_rows=2,
        history_max_rows=10,
        lock_dir=tmp_path / "retention.lock",
        space_path=tmp_path,
        writer_fence_already_held=True,
        now=NOW,
    )

    sql = "\n".join(connection.cursor_value.sql)
    assert report.status == "INSUFFICIENT"
    assert not old.exists()
    assert report.relation_reusable_bytes == 1_200
    assert report.deleted_history_rows == 3
    assert report.vacuum_completed is True
    assert "DELETE FROM public.contract_version_history" in sql
    assert "newer.version > h.version" in sql
    assert "pncp_supplier_contracts" not in sql
    assert "VACUUM (ANALYZE) public.contract_version_history" in sql
    assert report.filesystem_freed_bytes == 4_096


def test_missing_roots_and_no_history_are_insufficient_not_success(tmp_path: Path) -> None:
    report = run_retention(
        target_bytes=1024,
        policy=FilePolicy(roots=(tmp_path / "missing",), protect_newest=1),
        apply=False,
        now=NOW,
    )
    assert report.status == "PLAN_INSUFFICIENT"
    assert report.shortfall_bytes == report.target_bytes == 1280
    assert report.protected_current_snapshot is True


def test_minimum_free_watermark_increases_reclaim_target(tmp_path: Path) -> None:
    old = _old_file(tmp_path / "old.dump", 10, 4)
    free_before = tmp_path.stat().st_size  # only a small positive reference value
    # The actual free-space value is captured by the report; make the requested
    # watermark exactly eight bytes above it to prove target selection.
    from scripts.ops.storage_retention import filesystem_free_bytes

    free_before = filesystem_free_bytes(tmp_path)
    report = run_retention(
        target_bytes=3,
        policy=FilePolicy(roots=(tmp_path,), min_age=timedelta(), protect_newest=0),
        apply=False,
        space_path=tmp_path,
        minimum_free_bytes=free_before + 8,
        now=NOW,
    )
    assert old.exists()
    assert report.package_bytes == 3
    assert report.target_bytes == 8
    assert report.filesystem_free_before is not None
    assert report.filesystem_free_after is not None


def test_database_advisory_lock_refuses_busy_owner() -> None:
    connection = FakeConnection([(False, 0)])
    with pytest.raises(RetentionLockBusyError, match="advisory lock"):
        with database_advisory_lock(connection):
            pass


def test_backup_pipeline_has_opt_in_byte_balanced_rotation() -> None:
    script = (Path(__file__).parents[1] / "scripts" / "backup-database.sh").read_text(
        encoding="utf-8"
    )
    assert 'BACKUP_BYTE_BALANCED_RETENTION:-0' in script
    assert 'BACKUP_BYTE_BALANCED_MINIMUM:-2' in script
    assert "BACKUP_BYTE_BALANCED_INCOMING_PATH" in script
    assert 'stat --printf=\'%b\'' in script
    assert 'stat --printf=\'%h\'' in script
    assert 'stat --printf=\'%d\'' in script
    assert '"${backup_base}/daily" "$dump_path" "$net_growth" "$incoming_allocated"' in script
    assert script.index("do_byte_balanced_retention \\") < script.index('cp -f "$staging_path"')
    assert "net_growth=$(( incoming_allocated > replaced_allocated" in script
    assert 'do_retention "$BACKUP_BASE" "" 0' in script
    assert 'rm -f -- "$CURRENT_STAGING_GZIP"' in script
    assert 'rm -f -- "$CURRENT_STAGING_CUSTOM"' in script


def test_backup_same_day_retry_charges_net_growth_before_copy() -> None:
    script = (Path(__file__).parents[1] / "scripts" / "backup-database.sh").read_text(
        encoding="utf-8"
    )
    net_growth = "net_growth=$(( incoming_allocated > replaced_allocated"
    preflight = '"${backup_base}/daily" "$dump_path" "$net_growth" "$incoming_allocated"'
    assert net_growth in script
    assert preflight in script
    assert script.index(preflight) < script.index('cp -f "$staging_path"')
    assert 'do_retention "$BACKUP_BASE" "" 0' in script


def test_canonical_purge_is_opt_in_and_can_satisfy_reusable_capacity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    free_values = iter((10_000, 10_000))
    monkeypatch.setattr("scripts.ops.storage_retention.filesystem_free_bytes", lambda _path: next(free_values))
    monkeypatch.setattr("scripts.ops.storage_retention.exclusive_lock", _noop_lock)
    monkeypatch.setattr(
        "scripts.ops.storage_retention.reclaim_canonical_contracts",
        lambda *_args, **_kwargs: (2, 125, True),
    )

    report = run_retention(
        target_bytes=100,
        policy=FilePolicy(roots=(tmp_path,), protect_newest=0),
        apply=True,
        history_connection=object(),
        allow_canonical_purge=True,
        canonical_hot_horizon=timedelta(days=730),
        minimum_free_bytes=1,
        lock_dir=tmp_path / "retention.lock",
        space_path=tmp_path,
        writer_fence_already_held=True,
        now=NOW,
    )

    assert report.status == "SATISFIED_REUSABLE"
    assert report.deleted_canonical_rows == 2
    assert report.canonical_reusable_bytes == report.target_bytes == 125
    assert report.filesystem_freed_bytes == 0


def test_history_reuse_cannot_pay_canonical_growth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    free_values = iter((10_000, 10_000))
    monkeypatch.setattr("scripts.ops.storage_retention.filesystem_free_bytes", lambda _path: next(free_values))
    monkeypatch.setattr("scripts.ops.storage_retention.exclusive_lock", _noop_lock)
    monkeypatch.setattr(
        "scripts.ops.storage_retention.reclaim_history",
        lambda *_args, **_kwargs: (5, 125, True),
    )

    report = run_retention(
        target_bytes=100,
        policy=FilePolicy(roots=(tmp_path,), protect_newest=0),
        apply=True,
        history_connection=object(),
        canonical_required_bytes=125,
        history_required_bytes=125,
        lock_dir=tmp_path / "retention.lock",
        space_path=tmp_path,
        writer_fence_already_held=True,
        now=NOW,
    )

    assert report.status == "INSUFFICIENT"
    assert report.relation_reusable_bytes == 125
    assert report.matched_relation_reusable_bytes == 125
    assert report.target_bytes == 250
    assert report.shortfall_bytes == 125


def test_file_and_canonical_reuse_jointly_satisfy_only_canonical_growth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _old_file(tmp_path / "old.dump", 1, 5)
    free_values = iter((10_000, 14_096))
    monkeypatch.setattr("scripts.ops.storage_retention.filesystem_free_bytes", lambda _path: next(free_values))
    monkeypatch.setattr("scripts.ops.storage_retention.exclusive_lock", _noop_lock)

    def fake_canonical(*_args, **kwargs):
        return 2, kwargs["target_bytes"], True

    monkeypatch.setattr("scripts.ops.storage_retention.reclaim_canonical_contracts", fake_canonical)
    report = run_retention(
        target_bytes=5_000,
        policy=FilePolicy(roots=(tmp_path,), min_age=timedelta(), protect_newest=0),
        apply=True,
        history_connection=object(),
        allow_canonical_purge=True,
        canonical_required_bytes=6_250,
        history_required_bytes=0,
        minimum_free_bytes=1,
        lock_dir=tmp_path / "retention.lock",
        space_path=tmp_path,
        writer_fence_already_held=True,
        now=NOW,
    )

    assert report.status == "SATISFIED_REUSABLE"
    assert report.filesystem_freed_bytes == 4_096
    assert report.canonical_reusable_bytes == 2_154
    assert report.matched_relation_reusable_bytes == 2_154
    assert report.shortfall_bytes == 0


def test_canonical_purge_refuses_hot_horizon_below_30_days(tmp_path: Path) -> None:
    with pytest.raises(RetentionError, match="at least 30 days"):
        run_retention(
            target_bytes=100,
            policy=FilePolicy(roots=(tmp_path,), protect_newest=0),
            apply=False,
            allow_canonical_purge=True,
            canonical_hot_horizon=timedelta(days=29),
            now=NOW,
        )


def test_canonical_apply_requires_positive_physical_watermark(tmp_path: Path) -> None:
    with pytest.raises(RetentionError, match="positive physical"):
        run_retention(
            target_bytes=100,
            policy=FilePolicy(roots=(tmp_path,), protect_newest=0),
            apply=True,
            allow_canonical_purge=True,
            lock_dir=tmp_path / "retention.lock",
            space_path=tmp_path,
            now=NOW,
        )


def test_canonical_sql_protects_hot_or_active_contracts() -> None:
    source = (
        Path(__file__).parents[1] / "scripts" / "ops" / "storage_retention.py"
    ).read_text(encoding="utf-8")
    assert "STORAGE_RETENTION_ALLOW_CANONICAL_PURGE" not in source
    assert "c.data_fim IS NOT NULL" in source
    assert "c.data_fim < %s::date" in source
    assert "trg_contract_versioning is not disabled" in source
    assert "expected exactly contract_role_links(contract_id)" in source
    assert "trg_contract_role_link definition is unexpected" in source

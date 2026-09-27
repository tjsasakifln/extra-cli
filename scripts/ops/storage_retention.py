#!/usr/bin/env python3
"""Bounded, fail-closed storage retention for PNCP packages.

The canonical ``pncp_supplier_contracts`` table is outside the deletion
surface unless the operator explicitly opts in. Reclamation is restricted to
old files under explicit roots, superseded history rows, and (only with that
opt-in) completed canonical contracts older than a configured hot horizon.

The command is a dry-run unless ``--apply`` is supplied.  A successful apply
means that at least the requested logical byte budget was reclaimed; a
shortfall exits non-zero and is never reported as success.
"""

# The only composed SQL fragment is a fixed internal FOR UPDATE clause selected
# by a boolean; all values remain bound parameters.
# ruff: noqa: S608

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from math import ceil
from pathlib import Path
from typing import Any

DEFAULT_FILE_ROOTS = (
    Path("/var/lib/extra-consultoria/backups/tmp"),
    Path("/tmp/pg-backup"),  # noqa: S108 -- production backup staging contract
)
DEFAULT_PATTERNS = ("*.dump", "*.dump.gz", "*.partial.*", "*.tmp")
LOCK_NAME = "extra-storage-retention.lock"
DEFAULT_RETENTION_LOCK_PATH = Path("/var/lib/extra-consultoria/locks") / "storage-retention.lock"
HISTORY_TABLE = "public.contract_version_history"
# Same PostgreSQL fence as scripts.contracts_truth.PG_FENCE_KEY.  Retention
# mutates contract history and therefore belongs to the one-writer domain.
CONTRACTS_WRITER_FENCE_KEY = 0x45585452
LOCK_BUSY_EXIT = 75
INSUFFICIENT_EXIT = 2


class RetentionError(RuntimeError):
    """Base error for a retention run that must fail closed."""


class RetentionLockBusyError(RetentionError):
    """Another retention process owns the filesystem lock."""


@dataclass(frozen=True)
class FileCandidate:
    path: str
    size_bytes: int
    allocated_bytes: int
    device: int
    modified_at: str


@dataclass(frozen=True)
class FilePolicy:
    roots: tuple[Path, ...]
    patterns: tuple[str, ...] = DEFAULT_PATTERNS
    min_age: timedelta = timedelta(hours=24)
    protect_newest: int = 1


@dataclass
class RetentionReport:
    contract: str = "EXTRA_STORAGE_RETENTION/1.0"
    dry_run: bool = True
    status: str = "INSUFFICIENT"
    package_bytes: int = 0
    target_bytes: int = 0
    minimum_free_bytes: int = 0
    filesystem_free_before: int | None = None
    filesystem_free_after: int | None = None
    filesystem_freed_bytes: int = 0
    planned_file_bytes: int = 0
    deleted_file_bytes: int = 0
    planned_history_bytes: int = 0
    relation_reusable_bytes: int = 0
    deleted_history_rows: int = 0
    planned_canonical_bytes: int = 0
    canonical_reusable_bytes: int = 0
    deleted_canonical_rows: int = 0
    canonical_required_bytes: int = 0
    history_required_bytes: int = 0
    matched_relation_reusable_bytes: int = 0
    vacuum_completed: bool = False
    protected_current_snapshot: bool = True
    protected_newest_history_per_contract: bool = True
    shortfall_bytes: int = 0
    file_candidates: list[FileCandidate] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def reclaimed_bytes(self) -> int:
        if self.dry_run:
            return self.planned_file_bytes
        return self.filesystem_freed_bytes

    def finalize(self) -> None:
        self.shortfall_bytes = max(0, self.target_bytes - self.reclaimed_bytes)
        if self.dry_run:
            planned_matched = min(self.planned_canonical_bytes, self.canonical_required_bytes)
            planned_matched += min(self.planned_history_bytes, self.history_required_bytes)
            planned_capacity = self.planned_file_bytes + planned_matched
            self.shortfall_bytes = max(0, self.target_bytes - planned_capacity)
            self.status = "PLAN_SUFFICIENT" if self.shortfall_bytes == 0 else "PLAN_INSUFFICIENT"
            return
        free_watermark_met = self.filesystem_free_after is not None and (
            self.minimum_free_bytes == 0 or self.filesystem_free_after >= self.minimum_free_bytes
        )
        self.matched_relation_reusable_bytes = min(
            self.canonical_reusable_bytes, self.canonical_required_bytes
        ) + min(self.relation_reusable_bytes, self.history_required_bytes)
        capacity_bytes = self.filesystem_freed_bytes + self.matched_relation_reusable_bytes
        capacity_shortfall = max(0, self.target_bytes - capacity_bytes)
        if self.shortfall_bytes == 0 and free_watermark_met and not self.errors:
            self.status = "SATISFIED"
        elif capacity_shortfall == 0 and free_watermark_met and not self.errors:
            self.status = "SATISFIED_REUSABLE"
            self.shortfall_bytes = 0
        else:
            self.status = "INSUFFICIENT"
            self.shortfall_bytes = capacity_shortfall

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reclaimed_bytes"] = self.reclaimed_bytes
        return payload


def _validate_target_bytes(value: int) -> int:
    if value <= 0:
        raise RetentionError("incoming byte budget must be greater than zero")
    return value


def package_size(path: Path) -> int:
    """Return a stable regular-file size without following symlinks."""

    if path.is_symlink() or not path.is_file():
        raise RetentionError(f"incoming package is not a regular file: {path}")
    before = path.stat()
    after = path.stat()
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise RetentionError(f"incoming package changed while measured: {path}")
    return _validate_target_bytes(before.st_size)


def _safe_root(root: Path) -> Path:
    resolved = root.resolve(strict=True)
    if not resolved.is_dir() or root.is_symlink():
        raise RetentionError(f"retention root is not a real directory: {root}")
    if resolved == Path(resolved.anchor):
        raise RetentionError("filesystem root may not be a retention root")
    return resolved


def _is_within(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def filesystem_free_bytes(path: Path) -> int:
    """Measure free bytes on the filesystem containing ``path``."""

    resolved = path.resolve(strict=True)
    return int(shutil.disk_usage(resolved).free)


def allocated_bytes(stat_result: os.stat_result) -> int:
    """Return allocated disk bytes, not sparse-file logical length."""

    blocks = getattr(stat_result, "st_blocks", None)
    if blocks is not None:
        return int(blocks) * 512
    # Windows does not expose st_blocks. Round up to a conservative 4 KiB
    # allocation unit for planning; apply still verifies disk_usage delta.
    return ceil(stat_result.st_size / 4096) * 4096


def discover_file_candidates(
    policy: FilePolicy,
    *,
    now: datetime | None = None,
    protected_paths: Iterable[Path] = (),
) -> list[FileCandidate]:
    """List eligible files oldest-first, with path/symlink escape protection."""

    if policy.protect_newest < 0:
        raise RetentionError("protect_newest cannot be negative")
    if policy.min_age < timedelta(0):
        raise RetentionError("min_age cannot be negative")
    current = now or datetime.now(UTC)
    cutoff = current - policy.min_age
    protected = {path.resolve(strict=False) for path in protected_paths}
    unique: dict[Path, FileCandidate] = {}

    for configured_root in policy.roots:
        if not configured_root.exists():
            continue
        root = _safe_root(configured_root)
        for pattern in policy.patterns:
            class_candidates: dict[Path, FileCandidate] = {}
            for path in root.glob(pattern):
                if path.is_symlink() or not path.is_file():
                    continue
                resolved = path.resolve(strict=True)
                if not _is_within(resolved, root) or resolved in protected:
                    continue
                stat_result = path.stat()
                if stat_result.st_nlink != 1:
                    continue
                modified = datetime.fromtimestamp(stat_result.st_mtime, tz=UTC)
                if modified > cutoff:
                    continue
                class_candidates[resolved] = FileCandidate(
                    path=str(resolved),
                    size_bytes=stat_result.st_size,
                    allocated_bytes=allocated_bytes(stat_result),
                    device=int(stat_result.st_dev),
                    modified_at=modified.isoformat(),
                )
            class_ordered = sorted(class_candidates.values(), key=lambda item: (item.modified_at, item.path))
            eligible = (
                class_ordered[: max(0, len(class_ordered) - policy.protect_newest)]
                if policy.protect_newest
                else class_ordered
            )
            for candidate in eligible:
                unique[Path(candidate.path)] = candidate

    return sorted(unique.values(), key=lambda item: (item.modified_at, item.path))


def select_file_plan(candidates: Sequence[FileCandidate], target_bytes: int) -> list[FileCandidate]:
    """Select whole files, oldest first, until the target is met."""

    _validate_target_bytes(target_bytes)
    selected: list[FileCandidate] = []
    selected_bytes = 0
    for candidate in candidates:
        if selected_bytes >= target_bytes:
            break
        selected.append(candidate)
        selected_bytes += candidate.allocated_bytes
    return selected


def delete_file_plan(
    plan: Sequence[FileCandidate], roots: Sequence[Path], *, monitored_device: int | None = None
) -> int:
    """Delete a previously-built plan after revalidating every path and size."""

    safe_roots = tuple(_safe_root(root) for root in roots if root.exists())
    deleted_bytes = 0
    for candidate in plan:
        path = Path(candidate.path)
        if path.is_symlink() or not path.is_file():
            raise RetentionError(f"candidate changed type before deletion: {path}")
        resolved = path.resolve(strict=True)
        if not any(_is_within(resolved, root) for root in safe_roots):
            raise RetentionError(f"candidate escaped retention roots: {path}")
        current_size = path.stat().st_size
        if current_size != candidate.size_bytes:
            raise RetentionError(f"candidate size changed before deletion: {path}")
        current_stat = path.stat()
        if current_stat.st_nlink != 1:
            raise RetentionError(f"candidate has multiple hard links: {path}")
        if monitored_device is not None and current_stat.st_dev != monitored_device:
            raise RetentionError(f"candidate is not on monitored filesystem: {path}")
        current_allocated = allocated_bytes(current_stat)
        if current_allocated != candidate.allocated_bytes:
            raise RetentionError(f"candidate allocation changed before deletion: {path}")
        path.unlink()
        deleted_bytes += current_allocated
    return deleted_bytes


@contextmanager
def exclusive_lock(lock_path: Path) -> Iterator[None]:
    """Acquire a kernel flock; a process crash cannot leave a stale owner."""

    from scripts.crawl.contracts_writer_lock import ContractsWriterLock

    lock = ContractsWriterLock(path=lock_path, blocking=False)
    if not lock.acquire():
        raise RetentionLockBusyError(f"retention lock is already held: {lock_path}")
    try:
        yield
    finally:
        lock.release()


@contextmanager
def database_advisory_lock(connection: Any) -> Iterator[None]:
    """Hold the PostgreSQL session lock for the whole mutating retention run."""

    acquired = False
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", (CONTRACTS_WRITER_FENCE_KEY,))
        row = cursor.fetchone()
        acquired = bool(row and row[0])
    if not acquired:
        raise RetentionLockBusyError("database retention advisory lock is already held")
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_unlock(%s)", (CONTRACTS_WRITER_FENCE_KEY,))


def _history_plan(connection: Any, cutoff: datetime, target_bytes: int, max_rows: int) -> tuple[int, int]:
    """Estimate oldest superseded history rows without mutating the database."""

    with connection.cursor() as cursor:
        cursor.execute(
            """
            WITH eligible AS (
                SELECT h.id, h.changed_at, pg_column_size(h.*)::bigint AS row_bytes
                FROM public.contract_version_history AS h
                WHERE h.changed_at < %s
                  AND EXISTS (
                      SELECT 1
                      FROM public.contract_version_history AS newer
                      WHERE newer.contrato_id = h.contrato_id
                        AND newer.version > h.version
                  )
                ORDER BY h.changed_at ASC, h.id ASC
                LIMIT %s
            ), bounded AS (
                SELECT id, row_bytes,
                       SUM(row_bytes) OVER (ORDER BY changed_at, id) AS running_bytes
                FROM eligible
            )
            SELECT COUNT(*)::bigint, COALESCE(SUM(row_bytes), 0)::bigint
            FROM bounded
            WHERE running_bytes - row_bytes < %s
            """,
            (cutoff, max_rows, target_bytes),
        )
        row = cursor.fetchone()
    return int(row[0]), int(row[1])


def _delete_history_batch(connection: Any, cutoff: datetime, batch_rows: int) -> tuple[int, int]:
    """Delete one locked batch of superseded rows; never touch canonical rows."""

    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL lock_timeout = '5s'")
        cursor.execute("SET LOCAL statement_timeout = '2min'")
        cursor.execute(
            """
            WITH candidates AS (
                SELECT h.id, pg_column_size(h.*)::bigint AS row_bytes
                FROM public.contract_version_history AS h
                WHERE h.changed_at < %s
                  AND EXISTS (
                      SELECT 1
                      FROM public.contract_version_history AS newer
                      WHERE newer.contrato_id = h.contrato_id
                        AND newer.version > h.version
                  )
                ORDER BY h.changed_at ASC, h.id ASC
                LIMIT %s
                FOR UPDATE OF h SKIP LOCKED
            ), deleted AS (
                DELETE FROM public.contract_version_history AS history
                USING candidates
                WHERE history.id = candidates.id
                RETURNING candidates.row_bytes
            )
            SELECT COUNT(*)::bigint, COALESCE(SUM(row_bytes), 0)::bigint
            FROM deleted
            """,
            (cutoff, batch_rows),
        )
        row = cursor.fetchone()
    connection.commit()
    return int(row[0]), int(row[1])


def reclaim_history(
    connection: Any,
    *,
    target_bytes: int,
    cutoff: datetime,
    batch_rows: int,
    max_rows: int,
    apply: bool,
) -> tuple[int, int, bool]:
    """Plan or reclaim history bytes, preserving one latest row per contract."""

    if batch_rows <= 0 or max_rows <= 0:
        raise RetentionError("history row limits must be greater than zero")
    if cutoff > datetime.now(UTC):
        raise RetentionError("history cutoff may not be in the future")
    if not apply:
        rows, planned_bytes = _history_plan(connection, cutoff, target_bytes, max_rows)
        return rows, planned_bytes, False

    deleted_rows = 0
    deleted_bytes = 0
    while deleted_bytes < target_bytes and deleted_rows < max_rows:
        limit = min(batch_rows, max_rows - deleted_rows)
        rows, size = _delete_history_batch(connection, cutoff, limit)
        deleted_rows += rows
        deleted_bytes += size
        if rows == 0:
            break

    vacuum_completed = False
    if deleted_rows:
        previous_autocommit = bool(connection.autocommit)
        try:
            connection.autocommit = True
            with connection.cursor() as cursor:
                cursor.execute("SET statement_timeout = '15min'")
                cursor.execute("VACUUM (ANALYZE) public.contract_version_history")
            vacuum_completed = True
        finally:
            connection.autocommit = previous_autocommit
    return deleted_rows, deleted_bytes, vacuum_completed


def _assert_canonical_purge_safe(connection: Any) -> None:
    """Refuse canonical deletion when triggers/FKs are outside the allowlist."""

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT tgname, tgenabled, tgtype, tgfoid::regprocedure::text,
                   pg_get_triggerdef(oid)
            FROM pg_trigger
            WHERE tgrelid = 'public.pncp_supplier_contracts'::regclass
              AND NOT tgisinternal
            ORDER BY tgname
            """
        )
        triggers = {
            str(row[0]): (
                str(row[1]),
                int(row[2]),
                str(row[3]),
                " ".join(str(row[4]).split()),
            )
            for row in cursor.fetchall()
        }
        unexpected_triggers = set(triggers) - {
            "trg_contract_versioning",
            "trg_prevent_pncp_snapshot_mutation",
            "trg_contract_role_link",
        }
        if unexpected_triggers:
            raise RetentionError(
                f"canonical purge refused: unexpected user triggers {sorted(unexpected_triggers)}"
            )
        versioning = triggers.get("trg_contract_versioning")
        if versioning is not None and versioning[0] != "D":
            raise RetentionError("canonical purge refused: trg_contract_versioning is not disabled")
        role_trigger = triggers.get("trg_contract_role_link")
        if role_trigger is None:
            raise RetentionError("canonical purge refused: trg_contract_role_link is missing")
        role_definition = role_trigger[3].upper()
        if (
            role_trigger[0] not in {"O", "A"}
            or role_trigger[1] != 21  # ROW + INSERT + UPDATE, AFTER
            or not role_trigger[2].endswith("trg_refresh_contract_role_link()")
            or "AFTER INSERT OR UPDATE OF" not in role_definition
            or " DELETE " in f" {role_definition} "
        ):
            raise RetentionError("canonical purge refused: trg_contract_role_link definition is unexpected")
        snapshot_trigger = triggers.get("trg_prevent_pncp_snapshot_mutation")
        if snapshot_trigger is not None:
            if (
                snapshot_trigger[0] not in {"O", "A"}
                or snapshot_trigger[1] != 31  # ROW + BEFORE + INSERT + DELETE + UPDATE
                or not snapshot_trigger[2].endswith("prevent_pncp_snapshot_mutation()")
            ):
                raise RetentionError("canonical purge refused: snapshot guard trigger definition is unexpected")
        cursor.execute("SELECT current_setting('app.confenge_snapshot_guard', true)")
        snapshot_guard = cursor.fetchone()
        if snapshot_guard and snapshot_guard[0] == "on":
            raise RetentionError("canonical purge refused: CONFENGE snapshot guard is active")
        cursor.execute(
            """
            SELECT conname,
                   conrelid::regclass::text,
                   confdeltype,
                   ARRAY(
                       SELECT attr.attname
                       FROM unnest(constraint_row.conkey) WITH ORDINALITY AS key_column(attnum, ord)
                       JOIN pg_attribute AS attr
                         ON attr.attrelid = constraint_row.conrelid
                        AND attr.attnum = key_column.attnum
                       ORDER BY key_column.ord
                   ),
                   ARRAY(
                       SELECT attr.attname
                       FROM unnest(constraint_row.confkey) WITH ORDINALITY AS key_column(attnum, ord)
                       JOIN pg_attribute AS attr
                         ON attr.attrelid = constraint_row.confrelid
                        AND attr.attnum = key_column.attnum
                       ORDER BY key_column.ord
                   )
            FROM pg_constraint AS constraint_row
            WHERE contype = 'f'
              AND confrelid = 'public.pncp_supplier_contracts'::regclass
            ORDER BY 1
            """
        )
        inbound = [
            (str(row[0]), str(row[1]), str(row[2]), tuple(row[3]), tuple(row[4]))
            for row in cursor.fetchall()
        ]
    expected = [
        row
        for row in inbound
        if row[1] in {"contract_role_links", "public.contract_role_links"}
        and row[2] == "c"
        and row[3] == ("contract_id",)
        and row[4] == ("contrato_id",)
    ]
    if len(expected) != 1 or len(inbound) != 1:
        raise RetentionError(
            "canonical purge refused: expected exactly contract_role_links(contract_id) "
            "-> pncp_supplier_contracts(contrato_id) ON DELETE CASCADE; "
            f"found {inbound!r}"
        )


def _canonical_batch(
    connection: Any,
    *,
    cutoff: datetime,
    batch_rows: int,
    target_bytes: int,
    apply: bool,
) -> tuple[int, int]:
    if apply:
        # The lock is transaction-scoped and conflicts with ALTER TABLE and
        # other DDL that could change triggers/FKs. Validate only after it is
        # held, then delete and commit in the same transaction.
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout = '5s'")
            cursor.execute("SET LOCAL statement_timeout = '2min'")
            cursor.execute(
                "LOCK TABLE public.pncp_supplier_contracts, "
                "public.contract_role_links IN SHARE ROW EXCLUSIVE MODE"
            )
        _assert_canonical_purge_safe(connection)
    lock_clause = " FOR UPDATE OF c SKIP LOCKED" if apply else ""
    query = (
        """
        WITH eligible AS (
            SELECT c.id,
                   observed.recency,
                   (pg_column_size(c.*) + COALESCE(pg_column_size(roles.*), 0))::bigint AS row_bytes
            FROM public.pncp_supplier_contracts AS c
            LEFT JOIN public.contract_role_links AS roles
              ON roles.contract_id = c.contrato_id
            CROSS JOIN LATERAL (
                SELECT GREATEST(
                    c.data_fim::timestamp AT TIME ZONE 'UTC',
                    COALESCE(c.source_updated_at, '-infinity'::timestamptz),
                    COALESCE(
                        c.data_atualizacao_fonte::timestamp AT TIME ZONE 'UTC',
                        '-infinity'::timestamptz
                    ),
                    COALESCE(
                        c.data_publicacao_fonte::timestamp AT TIME ZONE 'UTC',
                        '-infinity'::timestamptz
                    ),
                    COALESCE(
                        c.data_publicacao::timestamp AT TIME ZONE 'UTC',
                        '-infinity'::timestamptz
                    ),
                    COALESCE(
                        c.data_assinatura::timestamp AT TIME ZONE 'UTC',
                        '-infinity'::timestamptz
                    )
                ) AS recency
            ) AS observed
            WHERE observed.recency < %s
              AND c.status_normalized = 'COMPLETED'
              AND c.quality_state = 'VALID'
              AND c.data_fim IS NOT NULL
              AND c.data_fim < %s::date
            ORDER BY observed.recency ASC, c.id ASC
            LIMIT %s
        """
        + lock_clause
        + """
        ), candidates AS (
            SELECT id, row_bytes
            FROM (
                SELECT id, recency, row_bytes,
                       SUM(row_bytes) OVER (ORDER BY recency, id) AS running_bytes
                FROM eligible
            ) bounded
            WHERE running_bytes - row_bytes < %s
        )
        """
    )
    if apply:
        query += """
        , deleted AS (
            DELETE FROM public.pncp_supplier_contracts AS contracts
            USING candidates
            WHERE contracts.id = candidates.id
            RETURNING candidates.row_bytes
        )
        SELECT COUNT(*)::bigint, COALESCE(SUM(row_bytes), 0)::bigint FROM deleted
        """
    else:
        query += "SELECT COUNT(*)::bigint, COALESCE(SUM(row_bytes), 0)::bigint FROM candidates"
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL lock_timeout = '5s'")
        cursor.execute("SET LOCAL statement_timeout = '2min'")
        cursor.execute(query, (cutoff, cutoff, batch_rows, target_bytes))
        row = cursor.fetchone()
    if apply:
        connection.commit()
    return int(row[0]), int(row[1])


def reclaim_canonical_contracts(
    connection: Any,
    *,
    target_bytes: int,
    cutoff: datetime,
    batch_rows: int,
    max_rows: int,
    apply: bool,
) -> tuple[int, int, bool]:
    """Prune completed cold contracts oldest-first for same-relation reuse."""

    if batch_rows <= 0 or max_rows <= 0:
        raise RetentionError("canonical row limits must be greater than zero")
    if not apply:
        _assert_canonical_purge_safe(connection)
    rows_total = 0
    bytes_total = 0
    while bytes_total < target_bytes and rows_total < max_rows:
        rows, reusable = _canonical_batch(
            connection,
            cutoff=cutoff,
            batch_rows=(max_rows if not apply else min(batch_rows, max_rows - rows_total)),
            target_bytes=max(1, target_bytes - bytes_total),
            apply=apply,
        )
        rows_total += rows
        bytes_total += reusable
        if rows == 0 or not apply:
            break
    vacuumed = False
    if apply and rows_total:
        previous_autocommit = bool(connection.autocommit)
        try:
            connection.autocommit = True
            with connection.cursor() as cursor:
                cursor.execute("SET statement_timeout = '15min'")
                cursor.execute("VACUUM (ANALYZE) public.pncp_supplier_contracts")
                cursor.execute("VACUUM (ANALYZE) public.contract_role_links")
            vacuumed = True
        finally:
            connection.autocommit = previous_autocommit
    return rows_total, bytes_total, vacuumed


def run_retention(
    *,
    target_bytes: int,
    policy: FilePolicy,
    apply: bool,
    protected_paths: Iterable[Path] = (),
    history_connection: Any | None = None,
    history_min_age: timedelta = timedelta(days=30),
    history_batch_rows: int = 1_000,
    history_max_rows: int = 1_000_000,
    allow_canonical_purge: bool = False,
    canonical_hot_horizon: timedelta = timedelta(days=730),
    canonical_batch_rows: int = 1_000,
    canonical_max_rows: int = 100_000,
    canonical_required_bytes: int | None = None,
    history_required_bytes: int | None = None,
    lock_dir: Path | None = None,
    space_path: Path | None = None,
    minimum_free_bytes: int = 0,
    safety_factor: float = 1.25,
    max_reclaim_bytes: int = 20 * 1024**3,
    writer_fence_already_held: bool = False,
    now: datetime | None = None,
) -> RetentionReport:
    """Reclaim at least ``target_bytes`` from allowlisted old data."""

    package_bytes = _validate_target_bytes(target_bytes)
    if safety_factor < 1.0:
        raise RetentionError("safety_factor must be at least 1.0")
    if canonical_hot_horizon < timedelta(days=30):
        raise RetentionError("canonical hot horizon must be at least 30 days")
    if minimum_free_bytes < 0:
        raise RetentionError("minimum_free_bytes cannot be negative")
    if apply and allow_canonical_purge and minimum_free_bytes == 0:
        raise RetentionError(
            "canonical purge apply requires a positive physical minimum_free_bytes watermark"
        )
    if max_reclaim_bytes <= 0:
        raise RetentionError("max_reclaim_bytes must be greater than zero")
    free_before = filesystem_free_bytes(space_path) if space_path is not None else None
    free_deficit = max(0, minimum_free_bytes - free_before) if free_before is not None else 0
    target = max(ceil(package_bytes * safety_factor), free_deficit)
    if target > max_reclaim_bytes:
        raise RetentionError(
            f"reclaim target {target} exceeds configured maximum {max_reclaim_bytes}"
        )
    report = RetentionReport(
        dry_run=not apply,
        package_bytes=package_bytes,
        target_bytes=target,
        minimum_free_bytes=minimum_free_bytes,
        filesystem_free_before=free_before,
    )
    if canonical_required_bytes is None:
        canonical_required_bytes = target if allow_canonical_purge else 0
    if history_required_bytes is None:
        history_required_bytes = target if history_connection is not None and not allow_canonical_purge else 0
    if canonical_required_bytes < 0 or history_required_bytes < 0:
        raise RetentionError("relation-specific required bytes cannot be negative")
    report.canonical_required_bytes = canonical_required_bytes
    report.history_required_bytes = history_required_bytes
    # Reusable pages are relation-local. The required capacity is therefore
    # the sum of each relation's requirement, not a fungible aggregate.
    target = max(target, canonical_required_bytes + history_required_bytes)
    if target > max_reclaim_bytes:
        raise RetentionError(
            f"relation-specific reclaim target {target} exceeds configured maximum {max_reclaim_bytes}"
        )
    report.target_bytes = target
    candidates = discover_file_candidates(policy, now=now, protected_paths=protected_paths)
    if space_path is not None:
        monitored_device = space_path.resolve(strict=True).stat().st_dev
        candidates = [candidate for candidate in candidates if candidate.device == monitored_device]
    file_plan = select_file_plan(candidates, target)
    report.file_candidates = list(file_plan)
    report.planned_file_bytes = sum(item.allocated_bytes for item in file_plan)

    def execute() -> None:
        if apply:
            if space_path is None:
                raise RetentionError("apply mode requires space_path for physical free-space verification")
            monitored_device = space_path.resolve(strict=True).stat().st_dev
            report.deleted_file_bytes = delete_file_plan(
                file_plan, policy.roots, monitored_device=monitored_device
            )
        file_bytes = report.deleted_file_bytes if apply else report.planned_file_bytes
        canonical_need = max(0, canonical_required_bytes - file_bytes)
        if canonical_need and allow_canonical_purge:
            if history_connection is None:
                raise RetentionError("canonical purge requires a PostgreSQL connection")
            current = now or datetime.now(UTC)
            rows, canonical_bytes, canonical_vacuumed = reclaim_canonical_contracts(
                history_connection,
                target_bytes=canonical_need,
                cutoff=current - canonical_hot_horizon,
                batch_rows=canonical_batch_rows,
                max_rows=canonical_max_rows,
                apply=apply,
            )
            if apply:
                report.deleted_canonical_rows = rows
                report.canonical_reusable_bytes = canonical_bytes
                report.vacuum_completed = report.vacuum_completed or canonical_vacuumed
            else:
                report.planned_canonical_bytes = canonical_bytes
        physical_after_canonical = max(0, file_bytes - canonical_required_bytes)
        history_need = max(0, history_required_bytes - physical_after_canonical)
        if history_need and history_connection is not None:
            current = now or datetime.now(UTC)
            rows, history_bytes, vacuumed = reclaim_history(
                history_connection,
                target_bytes=history_need,
                cutoff=current - history_min_age,
                batch_rows=history_batch_rows,
                max_rows=history_max_rows,
                apply=apply,
            )
            if apply:
                report.deleted_history_rows = rows
                report.relation_reusable_bytes = history_bytes
                report.vacuum_completed = report.vacuum_completed or vacuumed
            else:
                report.planned_history_bytes = history_bytes
                report.deleted_history_rows = 0

    if apply:
        if lock_dir is None:
            raise RetentionError("apply mode requires an exclusive lock path")
        if writer_fence_already_held:
            # Global order: outer PostgreSQL writer fence, then filesystem
            # retention flock. The outer fence is held by incremental ingest.
            with exclusive_lock(lock_dir):
                execute()
        else:
            if history_connection is not None:
                # Global order: PostgreSQL writer fence -> filesystem flock.
                with database_advisory_lock(history_connection):
                    with exclusive_lock(lock_dir):
                        execute()
            else:
                with exclusive_lock(lock_dir):
                    execute()
    else:
        execute()
    report.filesystem_free_after = filesystem_free_bytes(space_path) if space_path is not None else None
    if report.filesystem_free_before is not None and report.filesystem_free_after is not None:
        observed_delta = max(0, report.filesystem_free_after - report.filesystem_free_before)
        report.filesystem_freed_bytes = min(report.deleted_file_bytes, observed_delta)
    report.finalize()
    return report


def _connect_history(dsn: str) -> Any:
    try:
        import psycopg2
    except ImportError as exc:  # pragma: no cover - deployment preflight
        raise RetentionError("psycopg2 is required for history retention") from exc
    return psycopg2.connect(dsn, connect_timeout=10, application_name="extra_storage_retention")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    incoming = parser.add_mutually_exclusive_group(required=True)
    incoming.add_argument("--incoming-path", type=Path, help="completed package whose size is the reclaim target")
    incoming.add_argument("--incoming-bytes", type=int, help="explicit package byte size")
    parser.add_argument("--file-root", type=Path, action="append", help="allowlisted old-file root")
    parser.add_argument("--pattern", action="append", help="eligible filename glob (repeatable)")
    parser.add_argument("--min-age-hours", type=float, default=24.0)
    parser.add_argument("--protect-newest", type=int, default=1)
    parser.add_argument("--prune-contract-history", action="store_true")
    parser.add_argument("--dsn-env", default="LOCAL_DATALAKE_DSN")
    parser.add_argument("--history-min-age-days", type=float, default=30.0)
    parser.add_argument("--history-batch-rows", type=int, default=1_000)
    parser.add_argument("--history-max-rows", type=int, default=1_000_000)
    parser.add_argument(
        "--allow-canonical-purge",
        action="store_true",
        help="explicitly allow oldest-first deletion of completed cold canonical contracts",
    )
    parser.add_argument("--canonical-hot-horizon-days", type=float, default=730.0)
    parser.add_argument("--canonical-batch-rows", type=int, default=1_000)
    parser.add_argument("--canonical-max-rows", type=int, default=100_000)
    parser.add_argument("--lock-dir", type=Path, default=DEFAULT_RETENTION_LOCK_PATH)
    parser.add_argument("--space-path", type=Path, help="path whose filesystem free bytes are reported")
    parser.add_argument("--minimum-free-bytes", type=int, default=0)
    parser.add_argument("--safety-factor", type=float, default=1.25)
    parser.add_argument("--max-reclaim-bytes", type=int, default=20 * 1024**3)
    parser.add_argument("--apply", action="store_true", help="perform deletion; default is dry-run")
    parser.add_argument("--output", type=Path, help="optional JSON report path")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    connection = None
    try:
        target = package_size(args.incoming_path) if args.incoming_path else _validate_target_bytes(args.incoming_bytes)
        configured_roots = os.getenv("STORAGE_RETENTION_FILE_ROOTS", "")
        roots = tuple(
            args.file_root
            or ([Path(item) for item in configured_roots.split(os.pathsep) if item] if configured_roots else DEFAULT_FILE_ROOTS)
        )
        patterns = tuple(args.pattern or DEFAULT_PATTERNS)
        policy = FilePolicy(
            roots=roots,
            patterns=patterns,
            min_age=timedelta(hours=args.min_age_hours),
            protect_newest=args.protect_newest,
        )
        if args.prune_contract_history or args.allow_canonical_purge:
            dsn = os.getenv(args.dsn_env, "")
            if not dsn:
                raise RetentionError(f"{args.dsn_env} is required for contract history retention")
            connection = _connect_history(dsn)
        report = run_retention(
            target_bytes=target,
            policy=policy,
            apply=args.apply,
            protected_paths=([args.incoming_path] if args.incoming_path else []),
            history_connection=connection,
            history_min_age=timedelta(days=args.history_min_age_days),
            history_batch_rows=args.history_batch_rows,
            history_max_rows=args.history_max_rows,
            allow_canonical_purge=args.allow_canonical_purge,
            canonical_hot_horizon=timedelta(days=args.canonical_hot_horizon_days),
            canonical_batch_rows=args.canonical_batch_rows,
            canonical_max_rows=args.canonical_max_rows,
            lock_dir=args.lock_dir,
            space_path=args.space_path,
            minimum_free_bytes=args.minimum_free_bytes,
            safety_factor=args.safety_factor,
            max_reclaim_bytes=args.max_reclaim_bytes,
        )
        payload = json.dumps(report.to_dict(), ensure_ascii=False, indent=2)
        print(payload)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(payload + "\n", encoding="utf-8")
        successful = {"SATISFIED", "SATISFIED_REUSABLE"} if args.apply else {"PLAN_SUFFICIENT"}
        return 0 if report.status in successful else INSUFFICIENT_EXIT
    except RetentionLockBusyError as exc:
        print(json.dumps({"status": "LOCK_BUSY", "error": str(exc)}), file=sys.stderr)
        return LOCK_BUSY_EXIT
    except (OSError, RetentionError) as exc:
        print(json.dumps({"status": "ERROR", "error": str(exc)}), file=sys.stderr)
        return 1
    finally:
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    raise SystemExit(main())

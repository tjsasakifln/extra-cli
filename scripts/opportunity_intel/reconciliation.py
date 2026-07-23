"""Snapshot reconciliation algorithm for opportunity_intel.

Reconciles opportunity_intel records against the latest completed source
snapshot to ensure the radar only displays opportunities actually present
in the most recent validated run.

Core logic (7 rules from Story 1.4, Secao 8):
    1. Persist all IDs seen in the snapshot
    2. Confirm all 19 modalidades completed pagination
    3. Mark source_active=FALSE for previously active records not seen
    4. Use source_inactive_reason='absent_from_complete_open_snapshot'
    5. NEVER inactivate on partial/failed/limited runs
    6. Preserve history (source_active_changes JSONB)
    7. Re-activate records that reappear in a later snapshot

Usage:
    # After a completed PNCP crawl:
    reconciler = SourceSnapshotReconciler(dsn)
    result = reconciler.reconcile(run_id=123, source='pncp')

Design:
    - Fail-closed: partial/failed runs never trigger inactivation
    - Idempotent: re-reconciling the same snapshot does nothing new
    - Self-auditing: writes reconciliation_summary to the run's metadata
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import psycopg2
import psycopg2.extras

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReconciliationSummary:
    """Summary of a single reconciliation run."""

    run_id: int
    source: str
    reconciled_at: str
    run_status: str
    scope_complete: bool
    active_before: int
    inactivated: int
    reactivated: int
    skipped: bool
    skip_reason: str | None
    memberships_recorded: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "source": self.source,
            "reconciled_at": self.reconciled_at,
            "run_status": self.run_status,
            "scope_complete": self.scope_complete,
            "active_before": self.active_before,
            "inactivated": self.inactivated,
            "reactivated": self.reactivated,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
            "memberships_recorded": self.memberships_recorded,
            "active_after": self.active_before - self.inactivated + self.reactivated,
        }


class SourceSnapshotReconciler:
    """Reconciles opportunity_intel records against completed source runs.

    Implements the 7 reconciliation rules from Story 1.4.
    Fail-closed: never inactivates records when run status is not completed.
    """

    def __init__(self, dsn: str):
        if not dsn.startswith(("postgresql://", "postgres://")):
            raise ValueError("Reconciliation requires a PostgreSQL DSN")
        self.dsn = dsn
        self._conn: Any = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reconcile(
        self,
        run_id: int,
        source: str = "pncp",
        records: list[dict[str, Any]] | None = None,
    ) -> ReconciliationSummary:
        """Execute full reconciliation cycle for one source run.

        Args:
            run_id: opportunity_runs.id of the completed run.
            source: Source name (default: 'pncp').
            records: Optional list of records from this run. If provided,
                     memberships are saved first. If None, assumes
                     memberships are already recorded.

        Returns:
            ReconciliationSummary with counts.

        Raises:
            ValueError: If run not found.
        """
        conn = self._get_conn()
        try:
            # Step 1: Load run and validate
            run = self._load_run(conn, run_id)
            if run is None:
                raise ValueError(f"Run {run_id} not found in opportunity_runs")

            run_status = str(run["status"])
            scope_complete = bool(run["scope_complete"])

            # Step 5 (protection): Never reconcile partial/failed/limited
            skip_reason = self._check_run_gate(run)
            if skip_reason:
                _logger.warning("Reconciliation SKIPPED for run %d: %s", run_id, skip_reason)
                return ReconciliationSummary(
                    run_id=run_id,
                    source=source,
                    reconciled_at=datetime.now(UTC).isoformat(),
                    run_status=run_status,
                    scope_complete=scope_complete,
                    active_before=0,
                    inactivated=0,
                    reactivated=0,
                    skipped=True,
                    skip_reason=skip_reason,
                    memberships_recorded=0,
                )

            # Step 1: Persist IDs seen (if records provided)
            memberships_recorded = 0
            if records:
                memberships_recorded = self._record_memberships(conn, run_id, source, records)
                _logger.info("Recorded %d memberships for run %d", memberships_recorded, run_id)

            # Count active before
            active_before = self._count_active(conn, source)

            # Step 3: Inactivate records not seen in this run
            inactivated = self._inactivate_absent(conn, run_id, source)

            # Step 7: Reactivate records that reappeared
            reactivated = self._reactivate_present(conn, run_id, source)

            # Step 6: Update last_seen/verified for active records that were seen
            self._update_verified(conn, run_id, source)

            # Write reconciliation summary to run metadata
            summary_payload = {
                "reconciliation": {
                    "reconciled_at": datetime.now(UTC).isoformat(),
                    "active_before": active_before,
                    "inactivated": inactivated,
                    "reactivated": reactivated,
                    "active_after": active_before - inactivated + reactivated,
                    "memberships_recorded": memberships_recorded,
                    "source": source,
                }
            }
            self._append_run_metadata(conn, run_id, summary_payload)

            _logger.info(
                "Reconciliation for run %d: active_before=%d, inactivated=%d, reactivated=%d",
                run_id,
                active_before,
                inactivated,
                reactivated,
            )

            return ReconciliationSummary(
                run_id=run_id,
                source=source,
                reconciled_at=datetime.now(UTC).isoformat(),
                run_status=run_status,
                scope_complete=scope_complete,
                active_before=active_before,
                inactivated=inactivated,
                reactivated=reactivated,
                skipped=False,
                skip_reason=None,
                memberships_recorded=memberships_recorded,
            )
        finally:
            conn.close()

    def record_memberships(
        self,
        run_id: int,
        source: str,
        records: list[dict[str, Any]],
    ) -> int:
        """Record membership IDs for a run without running full reconciliation.

        Useful in the crawl pipeline: record memberships during crawl,
        then call reconcile() later after all modalidades complete.

        Args:
            run_id: opportunity_runs.id
            source: Source name
            records: List of record dicts from this run

        Returns:
            Number of memberships recorded.
        """
        conn = self._get_conn()
        try:
            return self._record_memberships(conn, run_id, source, records)
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Internal — Run gate
    # ------------------------------------------------------------------

    @staticmethod
    def _check_run_gate(run: dict[str, Any]) -> str | None:
        """Check if reconciliation should be skipped. Fail-closed.

        Rule 5: NEVER reconcile when:
        - Run status is partial, failed, or running
        - scope_complete is FALSE
        - Run was limited by record or page cap
        """
        status = str(run.get("status", "unknown"))
        scope_complete = bool(run.get("scope_complete"))

        if status not in ("completed", "completed_zero"):
            return (
                f"Run status is '{status}' — "
                f"reconciliation requires 'completed' or 'completed_zero'. "
                f"Protection: partial/failed runs never inactivate records."
            )

        if not scope_complete:
            return (
                "Run scope_complete is FALSE — "
                "not all 19 modalidades completed pagination. "
                "Protection: incomplete scopes never trigger inactivation."
            )

        metadata = run.get("metadata") or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except (json.JSONDecodeError, TypeError):
                metadata = {}

        if metadata.get("stopped_by_record_limit") is True:
            return "Run was stopped by record limit — snapshot is incomplete. Reconciliation blocked."

        if metadata.get("stopped_by_max_pages") is True:
            return "Run was stopped by page cap — snapshot is incomplete. Reconciliation blocked."

        return None

    # ------------------------------------------------------------------
    # Internal — Database operations
    # ------------------------------------------------------------------

    def _record_memberships(
        self,
        conn: Any,
        run_id: int,
        source: str,
        records: list[dict[str, Any]],
    ) -> int:
        """Record all IDs from records into source_snapshot_membership.

        Step 1: Persist every ID seen in the snapshot.
        Idempotent: ON CONFLICT DO NOTHING.
        """
        if not records:
            return 0

        # Build JSONB payload.
        # Accept both normalized opportunity_intel fields and raw PNCP API keys
        # (numeroControlePNCP) — pncp_audit passes raw records into reconcile().
        payload = []
        for rec in records:
            source_record_id = (
                rec.get("numero_controle_pncp")
                or rec.get("numeroControlePNCP")
                or rec.get("source_id")
                or rec.get("id")
                or ""
            )
            # Prefer official control number as canonical key for membership match
            # against opportunity_intel.numero_controle_pncp (inactivate_absent).
            # content_hash alone does not match that column and caused false
            # absent_from_complete_open_snapshot inactivation of every row.
            canonical_key = (
                rec.get("numero_controle_pncp")
                or rec.get("numeroControlePNCP")
                or rec.get("content_hash")
                or str(source_record_id)
                or ""
            )
            if not source_record_id and not canonical_key:
                continue
            payload.append(
                {
                    "source_record_id": str(source_record_id),
                    "canonical_opportunity_key": str(canonical_key),
                }
            )

        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT fn_record_snapshot_membership(%s, %s, %s::jsonb)",
                (run_id, source, json.dumps(payload, default=str)),
            )
            return int(cursor.fetchone()[0])

    def _count_active(self, conn: Any, source: str) -> int:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM opportunity_intel WHERE source = %s AND source_active = TRUE",
                (source,),
            )
            return int(cursor.fetchone()[0])

    def _inactivate_absent(self, conn: Any, run_id: int, source: str) -> int:
        """Mark source_active=FALSE for records not seen in this run.

        Rules 3+4: Only inactivate if not seen via content_hash OR source_id.
        Rule 6: Preserve history via source_active_changes JSONB.
        """
        with conn.cursor() as cursor:
            cursor.execute(
                """
                WITH inactivated AS (
                    UPDATE opportunity_intel oi
                    SET source_active = FALSE,
                        source_inactive_at = NOW(),
                        source_inactive_reason = 'absent_from_complete_open_snapshot',
                        source_active_changes = COALESCE(oi.source_active_changes, '[]'::jsonb)
                            || jsonb_build_array(
                                jsonb_build_object(
                                    'changed_at', NOW(),
                                    'from', TRUE,
                                    'to', FALSE,
                                    'reason', 'absent_from_complete_open_snapshot',
                                    'source_run_id', %s
                                )
                            )
                    WHERE oi.source = %s
                      AND oi.source_active = TRUE
                      AND oi.is_active = TRUE
                      AND NOT EXISTS (
                          SELECT 1 FROM source_snapshot_membership ssm
                          WHERE ssm.source_run_id = %s
                            AND ssm.canonical_opportunity_key = oi.numero_controle_pncp
                      )
                      AND NOT EXISTS (
                          SELECT 1 FROM source_snapshot_membership ssm2
                          WHERE ssm2.source_run_id = %s
                            AND ssm2.source_record_id = oi.source_id
                      )
                    RETURNING 1
                )
                SELECT COUNT(*) FROM inactivated
                """,
                (run_id, source, run_id, run_id),
            )
            return int(cursor.fetchone()[0])

    def _reactivate_present(self, conn: Any, run_id: int, source: str) -> int:
        """Re-activate records that were seen again in this snapshot.

        Rule 7: If a previously inactive record reappears, restore it.
        """
        with conn.cursor() as cursor:
            cursor.execute(
                """
                WITH reactivated AS (
                    UPDATE opportunity_intel oi
                    SET source_active = TRUE,
                        source_inactive_at = NULL,
                        source_inactive_reason = NULL,
                        last_seen_source_run_id = %s,
                        last_status_verified_at = NOW(),
                        last_status_verified_by = 'reconciliation_algorithm',
                        source_active_changes = COALESCE(oi.source_active_changes, '[]'::jsonb)
                            || jsonb_build_array(
                                jsonb_build_object(
                                    'changed_at', NOW(),
                                    'from', FALSE,
                                    'to', TRUE,
                                    'reason', 'reappeared_in_snapshot',
                                    'source_run_id', %s
                                )
                            )
                    WHERE oi.source = %s
                      AND oi.source_active = FALSE
                      AND oi.is_active = TRUE
                      AND (
                          EXISTS (
                              SELECT 1 FROM source_snapshot_membership ssm
                              WHERE ssm.source_run_id = %s
                                AND ssm.canonical_opportunity_key = oi.numero_controle_pncp
                          )
                          OR
                          EXISTS (
                              SELECT 1 FROM source_snapshot_membership ssm2
                              WHERE ssm2.source_run_id = %s
                                AND ssm2.source_record_id = oi.source_id
                          )
                      )
                    RETURNING 1
                )
                SELECT COUNT(*) FROM reactivated
                """,
                (run_id, run_id, source, run_id, run_id),
            )
            return int(cursor.fetchone()[0])

    def _update_verified(self, conn: Any, run_id: int, source: str) -> None:
        """Update last_seen and verification for records that are active and seen.

        Marks last_status_verified_at for records that are already active
        and were confirmed by this run.
        """
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE opportunity_intel oi
                SET last_seen_source_run_id = %s,
                    last_status_verified_at = NOW(),
                    last_status_verified_by = 'reconciliation_algorithm'
                WHERE oi.source = %s
                  AND oi.source_active = TRUE
                  AND oi.is_active = TRUE
                  AND (
                      EXISTS (
                          SELECT 1 FROM source_snapshot_membership ssm
                          WHERE ssm.source_run_id = %s
                            AND ssm.canonical_opportunity_key = oi.numero_controle_pncp
                      )
                      OR
                      EXISTS (
                          SELECT 1 FROM source_snapshot_membership ssm2
                          WHERE ssm2.source_run_id = %s
                            AND ssm2.source_record_id = oi.source_id
                      )
                  )
                """,
                (run_id, source, run_id, run_id),
            )

    def _append_run_metadata(self, conn: Any, run_id: int, payload: dict[str, Any]) -> None:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE opportunity_runs SET metadata = metadata || %s::jsonb WHERE id = %s",
                (json.dumps(payload, default=str), run_id),
            )

    # ------------------------------------------------------------------
    # Internal — DB helpers
    # ------------------------------------------------------------------

    def _get_conn(self) -> Any:
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(self.dsn)
            self._conn.autocommit = True
        return self._conn

    @staticmethod
    def _load_run(conn: Any, run_id: int) -> dict[str, Any] | None:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT id, source, status, scope_complete, finished_at, metadata
                FROM opportunity_runs
                WHERE id = %s
                """,
                (run_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

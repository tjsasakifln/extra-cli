#!/usr/bin/env python3
"""Fail-closed PostgreSQL authority for truth-plane SLI/SLO state (#275)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any


def _connect(dsn: str | None = None):
    import psycopg2
    from psycopg2.extras import RealDictCursor

    resolved = dsn or os.getenv("LOCAL_DATALAKE_DSN") or os.getenv("DATABASE_URL")
    if not resolved:
        raise RuntimeError("LOCAL_DATALAKE_DSN or DATABASE_URL is required")
    return psycopg2.connect(resolved, cursor_factory=RealDictCursor, connect_timeout=10)


def _one(cursor: Any, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any]:
    cursor.execute(sql, params)
    return dict(cursor.fetchone() or {})


def _relation_exists(cursor: Any, relation: str) -> bool:
    return bool(_one(cursor, "SELECT to_regclass(%s) IS NOT NULL AS exists", (relation,))["exists"])


def _metric_state(definition: dict[str, Any], value: float | None, denominator: float | None, reason: str) -> dict:
    objective = float(definition["objective_value"])
    warning_at = objective * float(definition["alert_before_ratio"])
    state = "UNKNOWN"
    if value is not None and denominator is not None and denominator > 0:
        if definition["objective_operator"] == "lte":
            state = "BREACH" if value > objective else ("WARNING" if value >= warning_at else "OK")
        else:
            state = "BREACH" if value < objective else ("WARNING" if value <= warning_at else "OK")
    return {
        "metric_name": definition["metric_name"],
        "stage": definition["stage"],
        "state": state,
        "value": value,
        "unit": definition["unit"],
        "objective_operator": definition["objective_operator"],
        "objective_value": objective,
        "window_seconds": int(definition["window_seconds"]),
        "denominator": denominator,
        "denominator_contract": definition["denominator_contract"],
        "reason": reason if state == "UNKNOWN" else None,
    }


def _observe_metric(cursor: Any, definition: dict[str, Any], now: datetime) -> dict:
    name = definition["metric_name"]
    window_start = now - timedelta(seconds=int(definition["window_seconds"]))
    value: float | None = None
    denominator: float | None = None
    reason = "metric source unavailable"

    if name == "queue_oldest_age_seconds":
        row = _one(
            cursor,
            """
            SELECT count(*)::BIGINT AS denominator,
                   extract(EPOCH FROM (%s - min(created_at))) AS value
            FROM crawl_jobs WHERE status IN ('queued', 'running')
            """,
            (now,),
        )
        denominator, value = float(row["denominator"]), float(row["value"]) if row["value"] is not None else None
        reason = "no queued/running jobs"
    elif name == "queue_terminal_failure_ratio":
        row = _one(
            cursor,
            """
            SELECT count(*)::BIGINT AS denominator,
                   count(*) FILTER (WHERE status IN ('failed', 'blocked', 'lease_expired'))::BIGINT AS failures
            FROM crawl_job_attempts
            WHERE finished_at >= %s AND finished_at <= %s
            """,
            (window_start, now),
        )
        denominator = float(row["denominator"])
        value = float(row["failures"]) / denominator if denominator else None
        reason = "no terminal attempts in window"
    elif name == "dlq_open_count":
        row = _one(
            cursor,
            """
            SELECT count(*)::BIGINT AS denominator,
                   (
                       SELECT count(*) FROM dlq_entries
                       WHERE status IN ('pending', 'dead')
                   )::BIGINT AS value
            FROM dlq_entries
            WHERE terminal_at >= %s AND terminal_at <= %s
            """,
            (window_start, now),
        )
        denominator = float(row["denominator"])
        value = float(row["value"]) if denominator else None
        reason = "no jobs reached a terminal threshold in window"
    elif name == "document_failure_ratio":
        if _relation_exists(cursor, "public.process_document_runs"):
            row = _one(
                cursor,
                """
                SELECT COALESCE(sum(documents_downloaded + documents_failed), 0)::BIGINT AS denominator,
                       COALESCE(sum(documents_failed), 0)::BIGINT AS failures
                FROM process_document_runs WHERE finished_at >= %s AND finished_at <= %s
                """,
                (window_start, now),
            )
            denominator = float(row["denominator"])
            value = float(row["failures"]) / denominator if denominator else None
            reason = "no terminal document units in window"
    elif name == "canonical_lag_seconds":
        if _relation_exists(cursor, "public.canonical_public_observations"):
            row = _one(
                cursor,
                """
                SELECT count(*)::BIGINT AS denominator,
                       max(extract(EPOCH FROM (received_at - observed_at))) AS value
                FROM canonical_public_observations
                WHERE received_at >= %s AND received_at <= %s
                """,
                (window_start, now),
            )
            denominator = float(row["denominator"])
            value = float(row["value"]) if row["value"] is not None else None
            reason = "no canonical observations in window"
        else:
            reason = "canonical_public_observations not installed"
    elif name.startswith("public_read_"):
        if _relation_exists(cursor, "public_read_v1.surface_health"):
            if name == "public_read_freshness_seconds":
                row = _one(
                    cursor,
                    """
                    SELECT count(*) FILTER (WHERE query_count > 0)::BIGINT AS denominator,
                           max(extract(EPOCH FROM (%s - refreshed_at)))
                               FILTER (WHERE query_count > 0) AS value
                    FROM public_read_v1.surface_health WHERE enabled
                    """,
                    (now,),
                )
            elif name == "public_read_query_p95_ms":
                row = _one(
                    cursor,
                    "SELECT COALESCE(sum(query_count), 0)::BIGINT AS denominator, max(query_p95_ms) AS value FROM public_read_v1.surface_health WHERE enabled",
                )
            else:
                row = _one(
                    cursor,
                    """
                    SELECT COALESCE(sum(query_count), 0)::BIGINT AS denominator,
                           CASE WHEN sum(query_count) > 0 THEN sum(error_count)::NUMERIC / sum(query_count) END AS value
                    FROM public_read_v1.surface_health WHERE enabled
                    """,
                )
            denominator = float(row["denominator"])
            value = float(row["value"]) if row["value"] is not None else None
            reason = "public_read_v1 has no measured denominator"
        else:
            reason = "public_read_v1.surface_health not installed"
    elif name == "public_reader_connection_ratio":
        row = _one(
            cursor,
            """
            SELECT count(*)::BIGINT AS denominator,
                   count(*) FILTER (
                       WHERE usename = 'smartlic_public_reader'
                          OR application_name LIKE 'smartlic%%'
                   )::BIGINT AS public_count
            FROM pg_stat_activity
            """,
        )
        denominator = float(row["denominator"])
        value = float(row["public_count"]) / denominator if denominator else None
        reason = "pg_stat_activity has no connection denominator"
    elif name == "public_reader_blocking_locks":
        row = _one(
            cursor,
            """
            SELECT (SELECT count(*) FROM pg_stat_activity)::BIGINT AS denominator,
                   count(*)::BIGINT AS value
            FROM pg_locks waiting
            JOIN pg_locks holding
              ON waiting.locktype = holding.locktype
             AND waiting.database IS NOT DISTINCT FROM holding.database
             AND waiting.relation IS NOT DISTINCT FROM holding.relation
             AND waiting.page IS NOT DISTINCT FROM holding.page
             AND waiting.tuple IS NOT DISTINCT FROM holding.tuple
             AND waiting.virtualxid IS NOT DISTINCT FROM holding.virtualxid
             AND waiting.transactionid IS NOT DISTINCT FROM holding.transactionid
             AND waiting.classid IS NOT DISTINCT FROM holding.classid
             AND waiting.objid IS NOT DISTINCT FROM holding.objid
             AND waiting.objsubid IS NOT DISTINCT FROM holding.objsubid
             AND waiting.pid <> holding.pid
            JOIN pg_stat_activity activity ON activity.pid = waiting.pid
            WHERE NOT waiting.granted AND holding.granted
              AND (activity.usename = 'smartlic_public_reader' OR activity.application_name LIKE 'smartlic%%')
            """,
        )
        denominator, value = float(row["denominator"]), float(row["value"])
        reason = "pg_stat_activity has no connection denominator"
    elif name == "public_reader_cpu_io_share":
        if _relation_exists(cursor, "public.pg_stat_statements"):
            row = _one(
                cursor,
                """
                SELECT count(*)::BIGINT AS denominator,
                       CASE WHEN sum(total_exec_time) > 0 THEN
                           sum(total_exec_time) FILTER (WHERE userid = (SELECT oid FROM pg_roles WHERE rolname = 'smartlic_public_reader'))
                           / sum(total_exec_time)
                       END AS value
                FROM pg_stat_statements
                """,
            )
            denominator = float(row["denominator"])
            value = float(row["value"]) if denominator and row["value"] is not None else None
            reason = "pg_stat_statements has no statement denominator"
        else:
            reason = "pg_stat_statements not installed"
    elif name == "operational_cost_per_public_unit":
        row = _one(
            cursor,
            """
            SELECT COALESCE(sum(unit_count), 0)::NUMERIC AS denominator,
                   CASE WHEN sum(unit_count) > 0 THEN sum(cost_brl) / sum(unit_count) END AS value
            FROM truth_plane_cost_observations
            WHERE observed_at >= %s AND observed_at <= %s
            """,
            (window_start, now),
        )
        denominator = float(row["denominator"])
        value = float(row["value"]) if row["value"] is not None else None
        reason = "no cost/unit observations in window"

    return _metric_state(definition, value, denominator, reason)


def _record_alerts(cursor: Any, metrics: list[dict[str, Any]], definition_hash: str) -> int:
    route = _one(
        cursor,
        "SELECT route_name FROM truth_plane_alert_routes WHERE enabled ORDER BY route_name LIMIT 1",
    ).get("route_name")
    written = 0
    for metric in metrics:
        if metric["state"] == "OK":
            continue
        fingerprint = hashlib.sha256(
            f"{definition_hash}|{metric['metric_name']}|{metric['state']}".encode()
        ).hexdigest()
        cursor.execute(
            """
            INSERT INTO truth_plane_alert_events (
                fingerprint, metric_name, state, route_name, payload, delivery_status
            ) VALUES (%s, %s, %s, %s, %s::JSONB, %s)
            ON CONFLICT (fingerprint) DO UPDATE
            SET last_seen_at = NOW(), occurrence_count = truth_plane_alert_events.occurrence_count + 1,
                payload = EXCLUDED.payload
            """,
            (
                fingerprint,
                metric["metric_name"],
                metric["state"],
                route,
                json.dumps(metric, sort_keys=True),
                "PENDING" if route else "NO_ROUTE",
            ),
        )
        written += 1
    return written


def observe(connection: Any, *, actor: str, now: datetime | None = None) -> dict[str, Any]:
    clock = (now or datetime.now(UTC)).astimezone(UTC)
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM truth_plane_slo_definitions WHERE enabled ORDER BY metric_name")
        definitions = [dict(row) for row in cursor.fetchall() or []]
        definition_hash = hashlib.sha256(
            json.dumps(definitions, sort_keys=True, default=str).encode()
        ).hexdigest()
        metrics = [_observe_metric(cursor, definition, clock) for definition in definitions]
        kill_switch = _one(cursor, "SELECT * FROM truth_plane_kill_switch WHERE singleton")
        unknown_count = sum(metric["state"] == "UNKNOWN" for metric in metrics)
        breach_count = sum(metric["state"] == "BREACH" for metric in metrics)
        denominator_sum = sum(float(metric["denominator"] or 0) for metric in metrics)
        blocked = bool(kill_switch.get("enabled")) or unknown_count > 0 or breach_count > 0 or denominator_sum <= 0
        status = "BLOCKED" if blocked else "VALID"
        cursor.execute(
            """
            INSERT INTO truth_plane_sli_reviews (
                window_start, window_end, status, metrics, metric_count,
                unknown_count, breach_count, denominator_sum, definition_hash, actor
            ) VALUES (%s, %s, %s, %s::JSONB, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                min(
                    (clock - timedelta(seconds=int(d["window_seconds"])) for d in definitions),
                    default=clock,
                ),
                clock,
                status,
                json.dumps(metrics, sort_keys=True),
                len(metrics),
                unknown_count,
                breach_count,
                denominator_sum,
                definition_hash,
                actor,
            ),
        )
        review_id = int(cursor.fetchone()["id"])
        last_valid = _one(
            cursor,
            """
            SELECT id, observed_at
            FROM truth_plane_sli_reviews
            WHERE status = 'VALID' AND id <> %s
            ORDER BY observed_at DESC, id DESC
            LIMIT 1
            """,
            (review_id,),
        )
        alert_count = _record_alerts(cursor, metrics, definition_hash)
    connection.commit()
    return {
        "status": status,
        "review_id": review_id,
        "last_valid_review": last_valid or None,
        "observed_at": clock.isoformat(),
        "definition_hash": definition_hash,
        "metric_count": len(metrics),
        "unknown_count": unknown_count,
        "breach_count": breach_count,
        "denominator_sum": denominator_sum,
        "kill_switch": dict(kill_switch),
        "alerts_recorded": alert_count,
        "metrics": metrics,
        "claim": "local truth-plane telemetry; not production soak or VPS evidence",
    }


def set_kill_switch(connection: Any, *, enabled: bool, reason: str, actor: str) -> dict[str, Any]:
    if not reason.strip() or not actor.strip():
        raise ValueError("kill switch reason and actor are required")
    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE truth_plane_kill_switch
            SET enabled = %s, reason = %s, changed_at = NOW(), changed_by = %s
            WHERE singleton
            RETURNING *
            """,
            (enabled, reason.strip(), actor.strip()),
        )
        state = dict(cursor.fetchone())
        cursor.execute(
            "INSERT INTO truth_plane_kill_switch_history (enabled, reason, changed_by) VALUES (%s, %s, %s)",
            (enabled, reason.strip(), actor.strip()),
        )
    connection.commit()
    return state


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, Decimal)):
        return value.isoformat() if isinstance(value, datetime) else float(value)
    return str(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Truth-plane SLI/SLO fail-closed authority")
    parser.add_argument("--dsn")
    sub = parser.add_subparsers(dest="command", required=True)
    observe_cmd = sub.add_parser("observe")
    observe_cmd.add_argument("--actor", required=True)
    switch_cmd = sub.add_parser("kill-switch")
    switch_cmd.add_argument("--enable", action=argparse.BooleanOptionalAction, required=True)
    switch_cmd.add_argument("--reason", required=True)
    switch_cmd.add_argument("--actor", required=True)
    cost_cmd = sub.add_parser("record-cost")
    cost_cmd.add_argument("--source", required=True)
    cost_cmd.add_argument("--unit-type", choices=["source", "document", "event", "dossier", "public_read"], required=True)
    cost_cmd.add_argument("--unit-count", type=int, required=True)
    cost_cmd.add_argument("--cost-brl", type=Decimal, required=True)
    cost_cmd.add_argument("--provenance", required=True, help="JSON object with billing evidence")
    args = parser.parse_args(argv)

    connection = _connect(args.dsn)
    try:
        if args.command == "observe":
            output = observe(connection, actor=args.actor)
            code = 0 if output["status"] == "VALID" else 2
        elif args.command == "kill-switch":
            output = set_kill_switch(connection, enabled=args.enable, reason=args.reason, actor=args.actor)
            code = 0
        else:
            provenance = json.loads(args.provenance)
            if not isinstance(provenance, dict) or not provenance:
                raise ValueError("--provenance must be a non-empty JSON object")
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO truth_plane_cost_observations
                        (source, unit_type, unit_count, cost_brl, provenance)
                    VALUES (%s, %s, %s, %s, %s::JSONB) RETURNING id
                    """,
                    (args.source, args.unit_type, args.unit_count, args.cost_brl, json.dumps(provenance)),
                )
                output = {"cost_observation_id": int(cursor.fetchone()["id"])}
            connection.commit()
            code = 0
    finally:
        connection.close()
    print(json.dumps(output, ensure_ascii=False, indent=2, default=_json_default))
    return code


if __name__ == "__main__":
    sys.exit(main())

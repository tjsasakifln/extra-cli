"""No-HTTP scheduler for recurring entity x applicable-source crawl jobs."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from scripts.crawl.runtime_queue import CrawlQueue, connect

POLICY_PATH = Path(__file__).resolve().parents[2] / "config" / "crawl-schedule-policies.json"
VALID_APPLICABILITY = frozenset({"APPLICABLE", "NOT_APPLICABLE", "BLOCKED", "FAILED"})


@dataclass(frozen=True)
class SchedulePair:
    entity_id: int
    source: str
    canonical_entity_key: str | None = None
    capability: str = "open_tenders"
    applicability: str = "APPLICABLE"
    reason: str = "applicable_by_current_rule"
    binding_version: str = "unbound-v1"
    canonical_url: str | None = None


class SchedulePolicyRegistry:
    def __init__(self, payload: dict[str, Any]):
        if payload.get("schema_version") != "crawl-schedule-policy/v1":
            raise ValueError("unsupported crawl schedule policy schema")
        self.version = str(payload.get("policy_version") or "").strip()
        default = payload.get("default")
        sources = payload.get("sources")
        if not self.version or not isinstance(default, dict) or not isinstance(sources, dict):
            raise ValueError("schedule policy requires version, default and sources")
        self.default = self._validate(default)
        self.sources = {
            str(source): self._validate({**self.default, **values})
            for source, values in sources.items()
            if isinstance(values, dict)
        }

    @classmethod
    def load(cls, path: Path | None = None) -> SchedulePolicyRegistry:
        payload = json.loads((path or POLICY_PATH).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("schedule policy root must be an object")
        return cls(payload)

    @staticmethod
    def _validate(values: dict[str, Any]) -> dict[str, Any]:
        required = (
            "sla_hours",
            "recheck_not_applicable_hours",
            "recheck_blocked_hours",
            "recheck_failed_hours",
            "jitter_seconds",
            "max_attempts",
            "domain_concurrency_limit",
        )
        for key in required:
            value = values.get(key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                raise ValueError(f"invalid schedule policy value: {key}")
        if values["max_attempts"] < 1 or values["domain_concurrency_limit"] < 1:
            raise ValueError("attempt and concurrency limits must be positive")
        out = dict(values)
        out["domain"] = str(values.get("domain") or "unknown")
        return out

    def for_source(self, source: str) -> dict[str, Any]:
        return dict(self.sources.get(source, self.default))


def _stable_jitter(pair: SchedulePair, policy_version: str, maximum: int) -> int:
    if maximum <= 0:
        return 0
    canonical_key = pair.canonical_entity_key or f"db:{pair.entity_id}"
    digest = hashlib.sha256(f"{canonical_key}|{pair.source}|{pair.capability}|{policy_version}".encode()).digest()
    return int.from_bytes(digest[:8], "big") % (maximum + 1)


def _domain(pair: SchedulePair, policy: dict[str, Any]) -> str:
    if pair.canonical_url:
        host = urlsplit(pair.canonical_url).hostname
        if host:
            return host.lower()
    return str(policy.get("domain") or pair.source)


def _recheck_hours(applicability: str, policy: dict[str, Any]) -> float:
    if applicability == "NOT_APPLICABLE":
        return float(policy["recheck_not_applicable_hours"])
    if applicability == "BLOCKED":
        return float(policy["recheck_blocked_hours"])
    if applicability == "FAILED":
        return float(policy["recheck_failed_hours"])
    return float(policy["sla_hours"])


def load_pairs_from_database(connection: Any) -> list[SchedulePair]:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT canonical_entity_key, entity_id, source, capability, status, applicability,
                   applicability_reason, canonical_url, latest_attempt_id
            FROM entity_source_coverage_current
            WHERE universe_run_id = (SELECT MAX(id) FROM target_universe_runs)
            ORDER BY canonical_entity_key, source, capability
            """
        )
        current_rows = list(cursor.fetchall() or [])
        if current_rows:
            pairs: list[SchedulePair] = []
            for row in current_rows:
                state = str(row["status"])
                applicability = (
                    "NOT_APPLICABLE"
                    if not row["applicability"] or state == "NOT_APPLICABLE"
                    else "BLOCKED"
                    if state == "BLOCKED"
                    else "FAILED"
                    if state in {"FAILED", "DISCOVERY_EXHAUSTED_NO_SURFACE"}
                    else "APPLICABLE"
                )
                binding = hashlib.sha256(
                    (
                        f"{row['source']}|{row['capability']}|{row['canonical_url'] or ''}|{row['latest_attempt_id']}"
                    ).encode()
                ).hexdigest()[:24]
                pairs.append(
                    SchedulePair(
                        entity_id=int(row["entity_id"]),
                        source=str(row["source"]),
                        canonical_entity_key=str(row["canonical_entity_key"]),
                        capability=str(row["capability"]),
                        applicability=applicability,
                        reason=str(row["applicability_reason"]),
                        binding_version=binding,
                        canonical_url=row["canonical_url"],
                    )
                )
            return pairs
        cursor.execute(
            """
            WITH sources(source) AS (
                VALUES ('pncp'::text), ('ciga_dom'::text),
                       ('sc_compras'::text), ('transparencia'::text)
            )
            SELECT active.canonical_entity_key, entity.id AS entity_id, sources.source,
                   'APPLICABLE'::text AS applicability,
                   'bootstrap_pending_continuous_coverage'::text AS reason
            FROM v_target_universe_active active
            JOIN sc_public_entities entity ON entity.cnpj_8 = active.cnpj8
            CROSS JOIN sources
            ORDER BY active.canonical_entity_key, sources.source
            """
        )
        return [
            SchedulePair(
                entity_id=int(row["entity_id"]),
                source=str(row["source"]),
                canonical_entity_key=str(row["canonical_entity_key"]),
                applicability=str(row["applicability"]),
                reason=str(row["reason"]),
                binding_version="applicability-v1",
            )
            for row in cursor.fetchall() or []
        ]


def load_pairs_json(path: Path) -> list[SchedulePair]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload if isinstance(payload, list) else payload.get("pairs", [])
    if not isinstance(rows, list):
        raise ValueError("pairs input must be a list or pairs list")
    return [SchedulePair(**row) for row in rows]


def reconcile_schedule(
    connection: Any,
    pairs: Iterable[SchedulePair],
    *,
    expected_entities: int,
    now: datetime | None = None,
    dry_run: bool = False,
    policy_registry: SchedulePolicyRegistry | None = None,
) -> dict[str, Any]:
    clock = (now or datetime.now(UTC)).astimezone(UTC)
    registry = policy_registry or SchedulePolicyRegistry.load()
    ordered = sorted(
        pairs,
        key=lambda row: (
            row.canonical_entity_key or f"db:{row.entity_id}",
            row.source,
            row.capability,
        ),
    )
    keys = [(row.canonical_entity_key or f"db:{row.entity_id}", row.source, row.capability) for row in ordered]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate entity/source/capability pair")
    entities = {row.canonical_entity_key or f"db:{row.entity_id}" for row in ordered}
    if len(entities) != expected_entities:
        raise ValueError(f"active universe mismatch: expected {expected_entities}, observed {len(entities)}")
    for pair in ordered:
        if pair.applicability not in VALID_APPLICABILITY:
            raise ValueError(f"invalid applicability: {pair.applicability}")
        if not pair.reason.strip():
            raise ValueError("every schedule pair requires an explicit reason")

    open_route_entities = {
        pair.canonical_entity_key or f"db:{pair.entity_id}"
        for pair in ordered
        if pair.capability == "open_tenders" and pair.applicability in VALID_APPLICABILITY and pair.reason.strip()
    }
    missing_routes = sorted(entities - open_route_entities)
    if missing_routes:
        raise ValueError(f"entities without open-tender route or blocker: {missing_routes[:10]}")

    result: dict[str, Any] = {
        "policy_version": registry.version,
        "dry_run": dry_run,
        "entity_count": len(entities),
        "pair_count": len(ordered),
        "queued": 0,
        "existing": 0,
        "deferred": 0,
        "invalidated": 0,
        "states": {state: 0 for state in sorted(VALID_APPLICABILITY)},
    }
    queue = CrawlQueue(connection)
    for pair in ordered:
        policy = registry.for_source(pair.source)
        result["states"][pair.applicability] += 1
        jitter = _stable_jitter(pair, registry.version, int(policy["jitter_seconds"]))
        next_run = clock + timedelta(seconds=jitter)
        if pair.applicability != "APPLICABLE":
            next_run = clock + timedelta(hours=_recheck_hours(pair.applicability, policy), seconds=jitter)
        freshness_deadline = clock + timedelta(hours=float(policy["sla_hours"]))
        domain = _domain(pair, policy)
        if dry_run:
            result["queued" if pair.applicability == "APPLICABLE" else "deferred"] += 1
            continue

        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE crawl_jobs
                SET status = 'queued', attempt_count = 0,
                    last_outcome = 'scheduled_recheck', updated_at = %s
                WHERE canonical_entity_key = %s AND source = %s AND capability = %s
                  AND binding_version = %s AND status IN ('blocked', 'failed')
                  AND next_run_at <= %s
                """,
                (
                    clock,
                    pair.canonical_entity_key or f"db:{pair.entity_id}",
                    pair.source,
                    pair.capability,
                    pair.binding_version,
                    clock,
                ),
            )
            cursor.execute(
                """
                UPDATE crawl_jobs
                SET status = 'cancelled', last_outcome = 'binding_changed', updated_at = %s
                WHERE canonical_entity_key = %s AND source = %s AND capability = %s
                  AND binding_version <> %s AND status = 'queued'
                """,
                (
                    clock,
                    pair.canonical_entity_key or f"db:{pair.entity_id}",
                    pair.source,
                    pair.capability,
                    pair.binding_version,
                ),
            )
            result["invalidated"] += cursor.rowcount or 0
            cursor.execute(
                """
                INSERT INTO crawl_entity_source_schedule AS schedule (
                    canonical_entity_key, entity_id, source, capability, applicability,
                    applicability_reason, policy_version, binding_version,
                    canonical_url, domain_key, next_run_at, freshness_deadline
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (canonical_entity_key, source, capability) DO UPDATE
                SET applicability = EXCLUDED.applicability,
                    applicability_reason = EXCLUDED.applicability_reason,
                    policy_version = EXCLUDED.policy_version,
                    binding_version = EXCLUDED.binding_version,
                    canonical_url = EXCLUDED.canonical_url,
                    domain_key = EXCLUDED.domain_key,
                    next_run_at = CASE
                        WHEN schedule.binding_version IS DISTINCT FROM EXCLUDED.binding_version
                          OR schedule.policy_version IS DISTINCT FROM EXCLUDED.policy_version
                          OR schedule.applicability IS DISTINCT FROM EXCLUDED.applicability
                        THEN EXCLUDED.next_run_at
                        ELSE schedule.next_run_at
                    END,
                    freshness_deadline = CASE
                        WHEN schedule.binding_version IS DISTINCT FROM EXCLUDED.binding_version
                          OR schedule.policy_version IS DISTINCT FROM EXCLUDED.policy_version
                          OR schedule.applicability IS DISTINCT FROM EXCLUDED.applicability
                        THEN EXCLUDED.freshness_deadline
                        ELSE schedule.freshness_deadline
                    END,
                    updated_at = now()
                RETURNING next_run_at
                """,
                (
                    pair.canonical_entity_key or f"db:{pair.entity_id}",
                    pair.entity_id,
                    pair.source,
                    pair.capability,
                    pair.applicability,
                    pair.reason,
                    registry.version,
                    pair.binding_version,
                    pair.canonical_url,
                    domain,
                    next_run,
                    freshness_deadline,
                ),
            )
            scheduled_next_run = cursor.fetchone()["next_run_at"]
        if pair.applicability != "APPLICABLE":
            result["deferred"] += 1
            continue
        if scheduled_next_run > clock:
            result["deferred"] += 1
            continue
        window_start = clock.replace(minute=0, second=0, microsecond=0)
        window_end = window_start + timedelta(hours=float(policy["sla_hours"]))
        _, inserted = queue.enqueue(
            entity_id=pair.entity_id,
            canonical_entity_key=pair.canonical_entity_key,
            source=pair.source,
            capability=pair.capability,
            domain_key=domain,
            binding_version=pair.binding_version,
            window_start=window_start,
            window_end=window_end,
            freshness_deadline=freshness_deadline,
            next_run_at=scheduled_next_run,
            max_attempts=int(policy["max_attempts"]),
            domain_concurrency_limit=int(policy["domain_concurrency_limit"]),
        )
        result["queued" if inserted else "existing"] += 1

    result["fully_reconciled"] = result["pair_count"] == (
        result["queued"] + result["existing"] + result["deferred"]
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reconcile recurring entity/source crawl jobs; performs no HTTP")
    parser.add_argument("--dsn")
    parser.add_argument("--pairs-json", type=Path)
    parser.add_argument("--expected-entities", type=int, default=1093)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    with connect(args.dsn) as connection:
        pairs = load_pairs_json(args.pairs_json) if args.pairs_json else load_pairs_from_database(connection)
        result = reconcile_schedule(
            connection,
            pairs,
            expected_entities=args.expected_entities,
            dry_run=args.dry_run,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Explicit legacy import for human-decisions.jsonl and related run artifacts.

Default mode is dry-run. Zero outcome inference. Zero invention of actor/owner/dates.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from scripts.decision_memory.db import require_client_id
from scripts.decision_memory.identity import extract_source_identifiers, resolve_opportunity_key
from scripts.decision_memory.mapping import MappingAmbiguousError, map_legacy_decision, map_system_recommendation
from scripts.decision_memory.models import (
    DecisionRecordInput,
    EventOrigin,
    TemporalIntegrity,
)
from scripts.decision_memory.repository import DecisionMemoryRepository


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _sha256_text(text: str) -> str:
    return _sha256_bytes(text.encode())


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"corrupted jsonl {path} line {i}: {exc}") from exc
        if not isinstance(obj, dict):
            raise ValueError(f"jsonl line {i} is not an object")
        rows.append(obj)
    return rows


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def import_run(
    repo: DecisionMemoryRepository,
    *,
    client_id: str,
    actor: str,
    paths: list[Path],
    apply: bool = False,
    cycle_id: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Import explicit file paths. dry-run unless apply=True."""
    client_id = require_client_id(client_id)
    if not actor or not str(actor).strip():
        raise ValueError("actor is required for import")
    if not paths:
        raise ValueError("at least one explicit path is required")

    manifest: list[dict[str, Any]] = []
    human_rows: list[dict[str, Any]] = []
    shortlist_recs: dict[str, str] = {}
    profile_stamp: dict[str, Any] = {}
    errors: list[dict[str, Any]] = []

    for raw in paths:
        path = Path(raw)
        if not path.is_file():
            errors.append({"path": str(path), "error": "file_not_found"})
            continue
        try:
            content_hash = _sha256_file(path)
        except OSError as exc:
            errors.append({"path": str(path), "error": str(exc)})
            continue
        entry = {
            "path": str(path.resolve()),
            "name": path.name,
            "sha256": content_hash,
            "bytes": path.stat().st_size,
        }
        manifest.append(entry)
        name = path.name.lower()
        try:
            if name.endswith(".jsonl") or name == "human-decisions.jsonl":
                human_rows.extend(_load_jsonl(path))
            elif name.endswith(".json"):
                data = _load_json(path)
                if name in {"shortlist.json", "03-shortlist.json", "actionable-summary.json"}:
                    for s in data.get("shortlist") or []:
                        if not isinstance(s, dict):
                            continue
                        oid = str(
                            s.get("opportunity_id") or s.get("numero_controle") or s.get("numero_controle_pncp") or ""
                        )
                        if oid:
                            rec = s.get("state") or s.get("recommendation") or s.get("actionable")
                            shortlist_recs[oid] = str(rec)
                    if isinstance(data.get("profile_stamp"), dict):
                        profile_stamp = data["profile_stamp"]
                elif name == "decision-loop-state.json":
                    # Do not invent package outcomes as tender outcomes
                    pass
                else:
                    # metadata only
                    if isinstance(data.get("profile_stamp"), dict) and not profile_stamp:
                        profile_stamp = data["profile_stamp"]
            else:
                errors.append({"path": str(path), "error": "unsupported_extension"})
        except (ValueError, json.JSONDecodeError, OSError) as exc:
            errors.append({"path": str(path), "error": str(exc)})

    counts = {
        "new": 0,
        "duplicate": 0,
        "blocked": 0,
        "invalid": 0,
        "skipped_outcome_inference": 0,
    }
    planned: list[dict[str, Any]] = []
    applied_events: list[dict[str, Any]] = []

    for row in human_rows:
        entry_hash = _sha256_text(json.dumps(row, sort_keys=True, ensure_ascii=False, default=str))
        try:
            legacy_raw = row.get("decision")
            human, legacy = map_legacy_decision(str(legacy_raw) if legacy_raw is not None else None)
        except MappingAmbiguousError as exc:
            counts["blocked"] += 1
            planned.append(
                {
                    "status": "blocked",
                    "reason": str(exc),
                    "entry_hash": entry_hash,
                    "row_keys": sorted(row.keys()),
                }
            )
            continue

        actor_row = row.get("actor")
        reason = row.get("reason") or row.get("justification")
        if not actor_row or not str(actor_row).strip():
            counts["invalid"] += 1
            planned.append(
                {
                    "status": "invalid",
                    "reason": "actor_missing",
                    "entry_hash": entry_hash,
                }
            )
            continue
        if not reason or not str(reason).strip():
            counts["invalid"] += 1
            planned.append(
                {
                    "status": "invalid",
                    "reason": "justification_missing",
                    "entry_hash": entry_hash,
                }
            )
            continue

        ids = extract_source_identifiers(row)
        oid_raw = row.get("opportunity_id") or row.get("opportunity_key")
        entry_oid: str | None = str(oid_raw) if oid_raw is not None else None
        try:
            opp_key = resolve_opportunity_key(
                client_id=client_id,
                identifiers=ids,
                explicit_key=entry_oid,
            )
        except ValueError as exc:
            counts["invalid"] += 1
            planned.append({"status": "invalid", "reason": str(exc), "entry_hash": entry_hash})
            continue

        rec_raw = shortlist_recs.get(str(entry_oid or opp_key))
        system_rec = map_system_recommendation(rec_raw)

        decided_at = _parse_dt(row.get("recorded_at") or row.get("decided_at"))
        # Backfill: historical unverified unless we can prove order (we cannot invent)
        temporal = TemporalIntegrity.HISTORICAL_UNVERIFIED

        inp = DecisionRecordInput(
            client_id=client_id,
            opportunity_key=opp_key,
            actor=str(actor_row).strip(),
            justification=str(reason).strip(),
            human_decision=human,
            legacy_decision=legacy,
            system_recommendation=system_rec,
            source_identifiers=ids,
            cycle_id=cycle_id or row.get("cycle_id"),
            run_id=run_id or row.get("run_id") or row.get("run_dir"),
            decided_at=decided_at,
            profile_id=profile_stamp.get("profile_id") or row.get("profile_id"),
            profile_version=str(profile_stamp.get("version") or row.get("profile_version") or "") or None,
            profile_hash=profile_stamp.get("profile_hash") or row.get("profile_hash"),
            evidence_hash=row.get("evidence_hash"),
            evidence_locators=[str(row.get("run_dir"))] if row.get("run_dir") else [],
            temporal_integrity=temporal,
            origin=EventOrigin.IMPORT,
            payload={
                "import_entry_hash": entry_hash,
                "legacy_schema": row.get("schema"),
                "next_action": row.get("next_action") or "NOT_PROVIDED",
                "next_action_due": row.get("next_action_due") or "NOT_PROVIDED",
                "source": "legacy_import",
            },
        )
        planned.append(
            {
                "status": "new_candidate",
                "entry_hash": entry_hash,
                "opportunity_key": opp_key,
                "human_decision": human.value,
                "legacy_decision": legacy.value,
                "temporal_integrity": temporal.value,
                "idempotency_preview": inp.idempotency_key,
            }
        )

        if apply:
            result = repo.record_decision(inp)
            if result.get("created"):
                counts["new"] += 1
                applied_events.append(result["event"])
                planned[-1]["status"] = "created"
                planned[-1]["event_id"] = result["event"]["event_id"]
            else:
                counts["duplicate"] += 1
                planned[-1]["status"] = "duplicate"
                planned[-1]["event_id"] = (result.get("event") or {}).get("event_id")
        else:
            # Dry-run: probe duplicates without insert by computing idem key via a dry probe
            # Use repository get if we can compute key the same way
            from scripts.decision_memory.idempotency import decision_idempotency_key

            decided_s = decided_at.isoformat().replace("+00:00", "Z") if decided_at else None
            idem = decision_idempotency_key(
                client_id=client_id,
                opportunity_key=opp_key,
                human_decision=human.value,
                actor=str(actor_row).strip(),
                justification=str(reason).strip(),
                decided_at=decided_s,
                evidence_hash=row.get("evidence_hash"),
                legacy_decision=legacy.value,
            )
            existing = repo.get_decision_by_idempotency(client_id, idem)
            if existing:
                counts["duplicate"] += 1
                planned[-1]["status"] = "duplicate"
                planned[-1]["event_id"] = existing.get("event_id")
            else:
                counts["new"] += 1
                planned[-1]["status"] = "would_create"
                planned[-1]["idempotency_key"] = idem

    # Never infer outcomes from package state
    counts["skipped_outcome_inference"] = 1  # policy marker

    import_id = str(uuid4())
    mode = "apply" if apply else "dry_run"
    report = {
        "ok": len(errors) == 0 or (counts["new"] + counts["duplicate"] > 0),
        "import_id": import_id,
        "client_id": client_id,
        "mode": mode,
        "actor": actor,
        "manifest": manifest,
        "counts": counts,
        "planned": planned,
        "errors": errors,
        "applied_event_ids": [e.get("event_id") for e in applied_events],
        "policies": [
            "dry_run_default",
            "zero_outcome_inference",
            "zero_invention_of_actor_owner_dates",
            "missing_fields_as_NOT_PROVIDED_or_invalid",
            "backfill_HISTORICAL_UNVERIFIED",
            "re-run fully idempotent",
        ],
        "non_claims": [
            "Import does not create outcomes",
            "Import does not finalize human package acceptance",
            "Historical rows are not prospective",
        ],
    }

    if apply:
        with repo.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO public.dm_import_runs (import_id, client_id, mode, manifest, counts, actor)
                VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s)
                """,
                (
                    import_id,
                    client_id,
                    mode,
                    json.dumps(manifest),
                    json.dumps(counts),
                    actor,
                ),
            )
        repo.conn.commit()

    return report

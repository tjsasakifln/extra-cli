"""Atomic local state: checkpoints, raw, evidence, watermark, DLQ and run history."""

from __future__ import annotations

import hashlib
import json
import os
import re
import traceback
from collections.abc import Callable
from contextlib import closing
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from scripts.crawl.ingestion._base.crawler import FetchResult
from scripts.crawl.resilience.stages import (
    CheckpointStatus,
    InvalidCheckpointTransition,
    parse_checkpoint_status,
    validate_transition,
)
from scripts.crawl.run_evidence import get_git_meta, sha256_json

_SAFE = re.compile(r"[^a-zA-Z0-9_.-]+")
_SENSITIVE = {"authorization", "proxy-authorization", "cookie", "set-cookie", "x-api-key"}

# Canonical checkpoint payload schema (FetchResult.checkpoint).
CHECKPOINT_REQUIRED_KEYS = frozenset({"source", "run_id", "request_scope", "status"})


def _slug(value: str) -> str:
    return _SAFE.sub("_", value.strip())[:180] or "default"


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def sanitize_headers(headers: dict[str, Any] | None) -> dict[str, str]:
    return {str(k).lower(): str(v) for k, v in (headers or {}).items() if str(k).lower() not in _SENSITIVE}


def _optional_positive_int(value: str | None) -> int | None:
    if not value:
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed > 0 else None


def coerce_canonical_checkpoint(payload: dict[str, Any]) -> CanonicalCheckpoint:
    """Strict schema for FetchResult.checkpoint — invalid shapes raise."""
    missing = CHECKPOINT_REQUIRED_KEYS - set(payload)
    if missing:
        raise TypeError(f"checkpoint schema invalido, faltam campos: {sorted(missing)}")
    known = {f.name for f in CanonicalCheckpoint.__dataclass_fields__.values()}
    filtered = {k: v for k, v in payload.items() if k in known}
    return CanonicalCheckpoint(**filtered)


@dataclass
class CanonicalCheckpoint:
    source: str
    run_id: str
    request_scope: str
    target: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    window: str | None = None
    page: int | None = None
    cursor: str | None = None
    status: str = "pending"
    attempt_count: int = 0
    last_http_status: int | None = None
    last_error: str | None = None
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    content_hash: str | None = None
    raw_reference: str | None = None
    scope_level: str = "page"
    pages_fetched: int = 0
    pages_expected: int | None = None
    stage: str | None = None
    snapshot_hash: str | None = None
    environment: str | None = None
    execution_mode: str | None = None

    @property
    def completed(self) -> bool:
        try:
            status = parse_checkpoint_status(self.status)
        except InvalidCheckpointTransition:
            return False
        return status.operational_complete or status == CheckpointStatus.WATERMARK_COMMITTED

    def transition_to(self, new_status: str) -> None:
        validate_transition(self.status, new_status)
        self.status = parse_checkpoint_status(new_status).value
        self.stage = self.status


class CheckpointStore:
    """Filesystem is the local source of truth; one atomic JSON per scope."""

    def __init__(self, root: Path):
        self.root = root

    def path_for(self, source: str, request_scope: str) -> Path:
        digest = hashlib.sha256(request_scope.encode()).hexdigest()[:16]
        return self.root / _slug(source) / f"{digest}-{_slug(request_scope)[:80]}.json"

    def load(self, source: str, request_scope: str) -> CanonicalCheckpoint | None:
        path = self.path_for(source, request_scope)
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        known = {f.name for f in CanonicalCheckpoint.__dataclass_fields__.values()}
        return CanonicalCheckpoint(**{k: v for k, v in data.items() if k in known})

    def save(self, checkpoint: CanonicalCheckpoint, *, previous_status: str | None = None) -> Path:
        if previous_status is not None and previous_status != checkpoint.status:
            validate_transition(previous_status, checkpoint.status)
        checkpoint.updated_at = datetime.now(UTC).isoformat()
        checkpoint.stage = checkpoint.status
        # Validate status is known.
        parse_checkpoint_status(checkpoint.status)
        path = self.path_for(checkpoint.source, checkpoint.request_scope)
        _atomic_json(path, asdict(checkpoint))
        return path

    def promote(self, checkpoint: CanonicalCheckpoint, new_status: str) -> Path:
        previous = checkpoint.status
        checkpoint.transition_to(new_status)
        return self.save(checkpoint, previous_status=previous)

    def pending(self, source: str | None = None) -> list[CanonicalCheckpoint]:
        roots = [self.root / _slug(source)] if source else list(self.root.glob("*"))
        result: list[CanonicalCheckpoint] = []
        for root in roots:
            for path in root.glob("*.json") if root.is_dir() else []:
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    known = {f.name for f in CanonicalCheckpoint.__dataclass_fields__.values()}
                    cp = CanonicalCheckpoint(**{k: v for k, v in data.items() if k in known})
                except (OSError, TypeError, ValueError, json.JSONDecodeError, InvalidCheckpointTransition):
                    continue
                if not cp.completed:
                    # Snapshot root is infrastructure for bulk resume; chunks/pages are the
                    # operational pending units. A raw_persisted snapshot alone is not a blocker.
                    if cp.scope_level == "snapshot" and cp.status == "raw_persisted" and cp.raw_reference:
                        continue
                    result.append(cp)
        return result


class RawStore:
    """Immutable HTTP envelope + globally deduplicated content-addressed body."""

    def __init__(self, root: Path, *, dsn: str | None = None, require_db: bool = False):
        self.root = root
        self.dsn = dsn
        self.require_db = require_db

    def persist(
        self,
        *,
        source: str,
        run_id: str,
        request_scope: str,
        payload: Any,
        provenance: dict[str, Any],
        http_status: int | None = None,
        request_succeeded: bool = True,
        page: int | None = None,
        crawl_job_attempt_id: int | None = None,
    ) -> tuple[Path, str]:
        from scripts.crawl.resilience.diagnostics import sanitize_mapping, sanitize_url

        if isinstance(payload, bytes):
            body = payload
        elif isinstance(payload, bytearray):
            body = bytes(payload)
        elif isinstance(payload, str):
            body = payload.encode()
        else:
            body = json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode()
        digest = hashlib.sha256(body).hexdigest()
        body_path = self.root / "cas" / digest[:2] / digest[2:4] / f"{digest}.body"
        if not body_path.exists():
            body_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = body_path.with_suffix(f".body.{os.getpid()}.tmp")
            with tmp.open("wb") as handle:
                handle.write(body)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, body_path)
        elif body_path.read_bytes() != body:
            raise RuntimeError(f"raw CAS collision for sha256={digest}")

        safe_provenance = sanitize_mapping(dict(provenance))
        raw_headers = safe_provenance.get("response_headers")
        safe_provenance["response_headers"] = sanitize_headers(raw_headers if isinstance(raw_headers, dict) else {})
        endpoint = sanitize_url(str(safe_provenance.get("endpoint") or "")) or None
        if endpoint:
            safe_provenance["endpoint"] = endpoint
        envelope = {
            "schema_version": "raw-http-envelope/v1",
            "source": source,
            "run_id": run_id,
            "crawl_job_attempt_id": crawl_job_attempt_id or _optional_positive_int(os.getenv("CRAWL_JOB_ATTEMPT_ID")),
            "request_scope": request_scope,
            "page": page,
            "sanitized_url": endpoint,
            "http_status": http_status,
            "request_succeeded": request_succeeded,
            "body_sha256": digest,
            "body_size_bytes": len(body),
            "body_uri": f"cas://raw-http/{digest}",
            "provenance": safe_provenance,
        }
        stable_identity = {key: value for key, value in envelope.items() if key != "provenance"}
        envelope_hash = sha256_json(stable_identity)
        envelope["observed_at"] = datetime.now(UTC).isoformat()
        envelope["envelope_sha256"] = envelope_hash
        scope_hash = hashlib.sha256(request_scope.encode()).hexdigest()[:16]
        page_token = f"page-{page}" if page is not None else "page-none"
        path = (
            self.root / "envelopes" / _slug(source) / _slug(run_id) / f"{scope_hash}-{page_token}-{envelope_hash}.json"
        )
        if not path.exists():
            _atomic_json(path, envelope)
        if self.dsn:
            self._record_postgres(envelope, path)
        elif self.require_db:
            raise RuntimeError("raw_http_archive_database_required_but_dsn_missing")
        return path, digest

    def load_reference(self, envelope_path: Path | str) -> dict[str, Any]:
        path = Path(envelope_path)
        envelope = json.loads(path.read_text(encoding="utf-8"))
        digest = str(envelope.get("body_sha256") or "")
        # Raw envelopes written before the CAS migration stored the canonical
        # payload inline. Production checkpoints are durable across releases,
        # so replay must verify and consume that historical shape instead of
        # resolving an empty digest as ``raw/cas/.body``.
        if not digest:
            if "payload" not in envelope:
                raise ValueError("raw envelope has neither CAS digest nor legacy payload")
            payload = envelope["payload"]
            canonical = json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode()
            expected = str(envelope.get("content_hash") or "")
            actual = hashlib.sha256(canonical).hexdigest()
            if not expected or actual != expected:
                raise ValueError("legacy raw body hash mismatch")
            provenance = envelope.get("provenance")
            return {
                "envelope": envelope,
                "payload": payload,
                "provenance": provenance if isinstance(provenance, dict) else {},
            }
        body_path = self.root / "cas" / digest[:2] / digest[2:4] / f"{digest}.body"
        body = body_path.read_bytes()
        if hashlib.sha256(body).hexdigest() != digest:
            raise ValueError(f"raw body hash mismatch: {digest}")
        try:
            payload: Any = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = body
        return {"envelope": envelope, "payload": payload, "provenance": envelope["provenance"]}

    def _record_postgres(self, envelope: dict[str, Any], path: Path) -> None:
        import psycopg2

        with (
            closing(psycopg2.connect(self.dsn, connect_timeout=10)) as connection,
            connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                """
                INSERT INTO raw_http_fetches (
                    run_id, crawl_job_attempt_id, source, request_scope, page,
                    sanitized_url, http_status, request_succeeded,
                    body_sha256, body_size_bytes, body_uri,
                    envelope_uri, envelope_sha256, observed_at
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s
                )
                ON CONFLICT (envelope_sha256) DO NOTHING
                """,
                (
                    envelope["run_id"],
                    envelope["crawl_job_attempt_id"],
                    envelope["source"],
                    envelope["request_scope"],
                    envelope["page"],
                    envelope["sanitized_url"],
                    envelope["http_status"],
                    envelope["request_succeeded"],
                    envelope["body_sha256"],
                    envelope["body_size_bytes"],
                    envelope["body_uri"],
                    str(path),
                    envelope["envelope_sha256"],
                    envelope["observed_at"],
                ),
            )


class StageLedger:
    """Per-run recoverable stage progress (append-only + latest pointer)."""

    def __init__(self, root: Path):
        self.root = root

    def path_for(self, source: str, run_id: str, request_scope: str) -> Path:
        digest = hashlib.sha256(request_scope.encode()).hexdigest()[:16]
        return self.root / _slug(source) / _slug(run_id) / f"{digest}.json"

    def load(self, source: str, run_id: str, request_scope: str) -> dict[str, Any] | None:
        path = self.path_for(source, run_id, request_scope)
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None

    def advance(
        self,
        *,
        source: str,
        run_id: str,
        request_scope: str,
        stage: str,
        meta: dict[str, Any] | None = None,
    ) -> Path:
        path = self.path_for(source, run_id, request_scope)
        current = self.load(source, run_id, request_scope) or {
            "source": source,
            "run_id": run_id,
            "request_scope": request_scope,
            "stages": [],
            "last_stage": None,
        }
        entry = {"stage": stage, "at": datetime.now(UTC).isoformat(), "meta": meta or {}}
        current["stages"].append(entry)
        current["last_stage"] = stage
        current["updated_at"] = entry["at"]
        _atomic_json(path, current)
        return path

    def last_stage(self, source: str, run_id: str, request_scope: str) -> str | None:
        data = self.load(source, run_id, request_scope)
        return None if not data else data.get("last_stage")


class RunHistory:
    """Append-only history of attempts so last_success is never overwritten."""

    def __init__(self, root: Path):
        self.root = root

    def append(self, record: dict[str, Any]) -> Path:
        source = str(record.get("source") or "unknown")
        day = datetime.now(UTC).strftime("%Y%m%d")
        path = self.root / _slug(source) / f"{day}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        return path

    def load_all(self, source: str | None = None) -> list[dict[str, Any]]:
        roots = [self.root / _slug(source)] if source else list(self.root.glob("*"))
        rows: list[dict[str, Any]] = []
        for root in roots:
            if not root.is_dir():
                continue
            for path in sorted(root.glob("*.jsonl")):
                for line in path.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        try:
                            rows.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        return rows


class EvidenceLedger:
    """Evidence predicate and atomic local ledger used before/with DB projection."""

    def __init__(self, root: Path):
        self.root = root

    def write(
        self,
        *,
        source: str,
        run_id: str,
        request_scope: str,
        result: FetchResult,
        window: dict[str, Any],
        target: str | None = None,
        environment: str = "development",
        execution_mode: str = "live",
        db_committed: bool = False,
        db_records_committed: int = 0,
        content_max_timestamp: str | None = None,
        artifact_meta: dict[str, Any] | None = None,
    ) -> tuple[Path, dict[str, Any]]:
        mechanics_satisfactory = bool(result.coverage_satisfactory and request_scope and window and result.provenance)
        # Operational requires DB commit for live modes.
        operational_satisfactory = bool(
            mechanics_satisfactory
            and db_committed
            and execution_mode in {"live", "canary"}
            and environment not in {"fixture", "test"}
        )
        # For fixture/test, "satisfactory" means mechanics only (never operational).
        if execution_mode == "fixture" or environment in {"fixture", "test"}:
            satisfactory = mechanics_satisfactory
            claim = "TEST_HEALTHY" if mechanics_satisfactory else "fixture_unsatisfactory"
        else:
            satisfactory = operational_satisfactory
            claim = "operational_satisfactory" if operational_satisfactory else "not_operational"

        evidence = {
            "source": source,
            "run_id": run_id,
            "request_scope": request_scope,
            "target": target,
            "window": window,
            "status": result.status,
            "satisfactory": satisfactory,
            "mechanics_satisfactory": mechanics_satisfactory,
            "operational_satisfactory": operational_satisfactory,
            "db_committed": db_committed,
            "db_records_committed": db_records_committed,
            "claim": claim,
            "environment": environment,
            "execution_mode": execution_mode,
            "request_completed": result.request_completed,
            "empty_confirmed": result.empty_confirmed,
            "pages_fetched": result.pages_fetched,
            "pages_expected": result.pages_expected,
            "records": len(result.records),
            "http_status": result.http_status,
            "http_statuses": result.http_statuses,
            "errors": result.errors,
            "warnings": result.warnings,
            "provenance": result.provenance,
            "source_content_max_timestamp": content_max_timestamp,
            "created_at": datetime.now(UTC).isoformat(),
            **(artifact_meta or {}),
            **get_git_meta(),
        }
        evidence["evidence_hash"] = sha256_json(evidence)
        path = self.root / _slug(source) / _slug(run_id) / f"{_slug(request_scope)}.json"
        _atomic_json(path, evidence)
        return path, evidence


class WatermarkStore:
    """Confirmed progress only; evidence is committed before watermark."""

    def __init__(self, root: Path):
        self.root = root

    def commit(self, checkpoint: CanonicalCheckpoint, evidence_path: Path, evidence: dict[str, Any]) -> Path:
        if not checkpoint.completed and checkpoint.status not in {
            "success",
            "empty_confirmed",
            "evidence_committed",
            "watermark_committed",
            "db_committed",
        }:
            # Allow commit after evidence_committed transition path.
            if not evidence.get("satisfactory"):
                raise ValueError("watermark exige checkpoint completo e evidence satisfatoria")
        if not evidence.get("satisfactory"):
            raise ValueError("watermark exige checkpoint completo e evidence satisfatoria")
        # Live operational watermark requires operational_satisfactory.
        if evidence.get("execution_mode") in {"live", "canary"} and evidence.get("environment") not in {
            "fixture",
            "test",
        }:
            if not evidence.get("operational_satisfactory") or not evidence.get("db_committed"):
                raise ValueError("watermark operacional exige db_committed e operational_satisfactory")
        transaction = {
            "source": checkpoint.source,
            "request_scope": checkpoint.request_scope,
            "run_id": checkpoint.run_id,
            "status": "committed",
            "environment": evidence.get("environment"),
            "execution_mode": evidence.get("execution_mode"),
            "checkpoint": asdict(checkpoint),
            "evidence_path": str(evidence_path),
            "evidence_hash": evidence["evidence_hash"],
            "db_committed": evidence.get("db_committed"),
            "committed_at": datetime.now(UTC).isoformat(),
        }
        path = self.root / _slug(checkpoint.source) / f"{_slug(checkpoint.request_scope)}.json"
        _atomic_json(path, transaction)
        return path

    def load(self, source: str, request_scope: str) -> dict[str, Any] | None:
        path = self.root / _slug(source) / f"{_slug(request_scope)}.json"
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None


class RequestBudget:
    def __init__(self, path: Path, limit: int):
        self.path = path
        self.limit = limit

    def consume(self, amount: int = 1) -> bool:
        today = date.today().isoformat()
        state: dict[str, Any] = {"date": today, "used": 0, "limit": self.limit}
        if self.path.is_file():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if loaded.get("date") == today:
                    state.update(loaded)
            except (OSError, json.JSONDecodeError):
                pass
        used = int(str(state.get("used", 0)))
        if used + amount > self.limit:
            return False
        state["used"] = used + amount
        _atomic_json(self.path, state)
        return True

    def snapshot(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {"used": 0, "limit": self.limit}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {"used": 0, "limit": self.limit}
        except (OSError, json.JSONDecodeError):
            return {"used": 0, "limit": self.limit}


class FileDLQ:
    """Local durable DLQ with content-hash dedup and manual replay."""

    def __init__(self, root: Path):
        self.root = root

    def push(
        self,
        *,
        source: str,
        run_id: str,
        payload: Any,
        error: BaseException | str,
        attempts: int = 0,
        raw_reference: str | None = None,
        error_kind: str = "record",
    ) -> Path:
        message = str(error)
        digest = sha256_json({"source": source, "payload": payload, "error_kind": error_kind, "message": message})
        path = self.root / "pending" / _slug(source) / f"{digest}.json"
        existing: dict[str, Any] = {}
        if path.is_file():
            existing = json.loads(path.read_text(encoding="utf-8"))
        summary = (
            ""
            if isinstance(error, str)
            else "".join(traceback.format_exception(type(error), error, error.__traceback__, limit=5))
        )
        record = {
            "source": source,
            "run_id": run_id,
            "payload": payload,
            "raw_reference": raw_reference,
            "error": message,
            "error_kind": error_kind,
            "stack_summary": summary[-4000:],
            "timestamp": existing.get("timestamp") or datetime.now(UTC).isoformat(),
            "hash": digest,
            "attempts": max(attempts, int(existing.get("attempts", 0))) + 1,
        }
        _atomic_json(path, record)
        return path

    def pending(self, source: str | None = None) -> list[Path]:
        root = self.root / "pending"
        return sorted((root / _slug(source)).glob("*.json")) if source else sorted(root.glob("*/*.json"))

    def resolve_scope(self, *, source: str, request_scope: str) -> int:
        """Move systemic failures aside only after that exact scope succeeds."""

        def equivalent_scope(candidate: str) -> bool:
            if candidate == request_scope:
                return True
            # Legacy all-target scopes omitted ``:same-day|target=all``.
            if "target=all" not in request_scope or "target=" in candidate:
                return False
            try:
                expected = request_scope.split("date=", 1)[1].split("|", 1)[0]
                observed = candidate.split("date=", 1)[1].split("|", 1)[0]
            except IndexError:
                return False
            if ":" not in observed:
                observed = f"{observed}:{observed}"
            return observed == expected

        resolved = 0
        for path in self.pending(source):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            payload = record.get("payload")
            if not isinstance(payload, dict) or not equivalent_scope(str(payload.get("request_scope") or "")):
                continue
            destination = self.root / "resolved" / path.parent.name / path.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(path, destination)
            resolved += 1
        return resolved

    def replay(self, handler: Callable[[dict[str, Any]], None], *, source: str | None = None) -> tuple[int, int]:
        ok = failed = 0
        for path in self.pending(source):
            record = json.loads(path.read_text(encoding="utf-8"))
            try:
                handler(record)
            except Exception as exc:  # record remains pending
                failed += 1
                record["attempts"] = int(record.get("attempts", 0)) + 1
                record["error"] = str(exc)
                _atomic_json(path, record)
            else:
                destination = self.root / "replayed" / path.parent.name / path.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                os.replace(path, destination)
                ok += 1
        return ok, failed

"""Atomic local state: checkpoints, raw, evidence, watermark and DLQ."""

from __future__ import annotations

import hashlib
import json
import os
import re
import traceback
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from scripts.crawl.ingestion._base.crawler import FetchResult
from scripts.crawl.run_evidence import get_git_meta, sha256_json

_SAFE = re.compile(r"[^a-zA-Z0-9_.-]+")
_SENSITIVE = {"authorization", "proxy-authorization", "cookie", "set-cookie", "x-api-key"}


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
    return {
        str(k).lower(): str(v)
        for k, v in (headers or {}).items()
        if str(k).lower() not in _SENSITIVE
    }


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

    @property
    def completed(self) -> bool:
        return self.status in {"success", "empty_confirmed"}


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
        return CanonicalCheckpoint(**json.loads(path.read_text(encoding="utf-8")))

    def save(self, checkpoint: CanonicalCheckpoint) -> Path:
        checkpoint.updated_at = datetime.now(UTC).isoformat()
        path = self.path_for(checkpoint.source, checkpoint.request_scope)
        _atomic_json(path, asdict(checkpoint))
        return path

    def pending(self, source: str | None = None) -> list[CanonicalCheckpoint]:
        roots = [self.root / _slug(source)] if source else list(self.root.glob("*"))
        result: list[CanonicalCheckpoint] = []
        for root in roots:
            for path in root.glob("*.json") if root.is_dir() else []:
                try:
                    cp = CanonicalCheckpoint(**json.loads(path.read_text(encoding="utf-8")))
                except (OSError, TypeError, ValueError, json.JSONDecodeError):
                    continue
                if not cp.completed:
                    result.append(cp)
        return result


class RawStore:
    """Immutable deterministic raw-zone storage using canonical JSON SHA-256."""

    def __init__(self, root: Path):
        self.root = root

    def persist(self, *, source: str, run_id: str, request_scope: str, payload: Any, provenance: dict[str, Any]) -> tuple[Path, str]:
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()
        digest = hashlib.sha256(canonical).hexdigest()
        directory = self.root / _slug(source) / _slug(request_scope)
        path = directory / f"{digest}.json"
        if not path.exists():
            safe_provenance = dict(provenance)
            safe_provenance["response_headers"] = sanitize_headers(safe_provenance.get("response_headers"))
            _atomic_json(path, {"source": source, "run_id": run_id, "request_scope": request_scope, "content_hash": digest, "provenance": safe_provenance, "payload": payload})
        return path, digest


class EvidenceLedger:
    """Evidence predicate and atomic local ledger used before DB projection."""

    def __init__(self, root: Path):
        self.root = root

    def write(self, *, source: str, run_id: str, request_scope: str, result: FetchResult, window: dict[str, Any], target: str | None = None) -> tuple[Path, dict[str, Any]]:
        satisfactory = bool(result.coverage_satisfactory and request_scope and window and result.provenance)
        evidence = {
            "source": source,
            "run_id": run_id,
            "request_scope": request_scope,
            "target": target,
            "window": window,
            "status": result.status,
            "satisfactory": satisfactory,
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
            "created_at": datetime.now(UTC).isoformat(),
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
        if not checkpoint.completed or not evidence.get("satisfactory"):
            raise ValueError("watermark exige checkpoint completo e evidence satisfatoria")
        transaction = {
            "source": checkpoint.source,
            "request_scope": checkpoint.request_scope,
            "run_id": checkpoint.run_id,
            "status": "committed",
            "checkpoint": asdict(checkpoint),
            "evidence_path": str(evidence_path),
            "evidence_hash": evidence["evidence_hash"],
            "committed_at": datetime.now(UTC).isoformat(),
        }
        path = self.root / _slug(checkpoint.source) / f"{_slug(checkpoint.request_scope)}.json"
        _atomic_json(path, transaction)
        return path


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


class FileDLQ:
    """Local durable DLQ with content-hash dedup and manual replay."""

    def __init__(self, root: Path):
        self.root = root

    def push(self, *, source: str, run_id: str, payload: Any, error: BaseException | str, attempts: int = 0, raw_reference: str | None = None, error_kind: str = "record") -> Path:
        message = str(error)
        digest = sha256_json({"source": source, "payload": payload, "error_kind": error_kind, "message": message})
        path = self.root / "pending" / _slug(source) / f"{digest}.json"
        existing: dict[str, Any] = {}
        if path.is_file():
            existing = json.loads(path.read_text(encoding="utf-8"))
        summary = "" if isinstance(error, str) else "".join(traceback.format_exception(type(error), error, error.__traceback__, limit=5))
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

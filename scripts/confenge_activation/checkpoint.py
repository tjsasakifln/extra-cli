"""Stage checkpoints so a national pipeline run can resume without restart-from-zero."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


CHECKPOINT_NAME = "pipeline-checkpoint.json"

STAGES = (
    "universe",
    "activation",
    "intelligence",
    "contacts",
    "feed",
    "done",
)


@dataclass
class StageCheckpoint:
    stage: str
    status: str  # pending | running | completed | failed
    started_at: str | None = None
    finished_at: str | None = None
    cursor: str | None = None  # opaque resume token (e.g. keyset id, cnpj)
    counts: dict[str, Any] = field(default_factory=dict)
    artifact_paths: dict[str, str] = field(default_factory=dict)
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PipelineCheckpoint:
    run_id: str
    as_of: str
    updated_at: str
    current_stage: str
    stages: dict[str, dict[str, Any]] = field(default_factory=dict)
    full_datalake_scanned: bool = False
    universe_total: int = 0
    hot_set_cursor: str | None = None  # last cnpj selected
    processed_cnpjs: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "as_of": self.as_of,
            "updated_at": self.updated_at,
            "current_stage": self.current_stage,
            "stages": dict(self.stages),
            "full_datalake_scanned": self.full_datalake_scanned,
            "universe_total": self.universe_total,
            "hot_set_cursor": self.hot_set_cursor,
            "processed_cnpjs": list(self.processed_cnpjs),
            "meta": dict(self.meta),
            "resume_safe": True,
        }

    def stage_completed(self, name: str) -> bool:
        st = self.stages.get(name) or {}
        return str(st.get("status") or "") == "completed"

    def mark_running(self, name: str, **counts: Any) -> None:
        prev = self.stages.get(name) or {}
        self.stages[name] = {
            **prev,
            "stage": name,
            "status": "running",
            "started_at": prev.get("started_at") or _utcnow(),
            "counts": {**(prev.get("counts") or {}), **counts},
        }
        self.current_stage = name
        self.updated_at = _utcnow()

    def mark_completed(
        self,
        name: str,
        *,
        cursor: str | None = None,
        counts: dict[str, Any] | None = None,
        artifact_paths: dict[str, str] | None = None,
    ) -> None:
        prev = self.stages.get(name) or {}
        self.stages[name] = {
            **prev,
            "stage": name,
            "status": "completed",
            "started_at": prev.get("started_at") or _utcnow(),
            "finished_at": _utcnow(),
            "cursor": cursor if cursor is not None else prev.get("cursor"),
            "counts": {**(prev.get("counts") or {}), **(counts or {})},
            "artifact_paths": {
                **(prev.get("artifact_paths") or {}),
                **(artifact_paths or {}),
            },
            "error": None,
        }
        self.current_stage = name
        self.updated_at = _utcnow()

    def mark_failed(self, name: str, error: str) -> None:
        prev = self.stages.get(name) or {}
        self.stages[name] = {
            **prev,
            "stage": name,
            "status": "failed",
            "finished_at": _utcnow(),
            "error": error[:1000],
        }
        self.current_stage = name
        self.updated_at = _utcnow()

    def add_processed(self, cnpjs: list[str], *, cursor: str | None = None) -> None:
        seen = set(self.processed_cnpjs)
        for c in cnpjs:
            if c and c not in seen:
                self.processed_cnpjs.append(c)
                seen.add(c)
        if cursor:
            self.hot_set_cursor = cursor
        self.updated_at = _utcnow()


def checkpoint_path(out_dir: Path | str) -> Path:
    return Path(out_dir) / CHECKPOINT_NAME


def load_checkpoint(out_dir: Path | str) -> PipelineCheckpoint | None:
    path = checkpoint_path(out_dir)
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return PipelineCheckpoint(
        run_id=str(data.get("run_id") or ""),
        as_of=str(data.get("as_of") or ""),
        updated_at=str(data.get("updated_at") or ""),
        current_stage=str(data.get("current_stage") or "universe"),
        stages=dict(data.get("stages") or {}),
        full_datalake_scanned=bool(data.get("full_datalake_scanned")),
        universe_total=int(data.get("universe_total") or 0),
        hot_set_cursor=data.get("hot_set_cursor"),
        processed_cnpjs=list(data.get("processed_cnpjs") or []),
        meta=dict(data.get("meta") or {}),
    )


def new_checkpoint(*, run_id: str, as_of: str) -> PipelineCheckpoint:
    return PipelineCheckpoint(
        run_id=run_id,
        as_of=as_of,
        updated_at=_utcnow(),
        current_stage="universe",
        stages={s: {"stage": s, "status": "pending"} for s in STAGES if s != "done"},
    )


def save_checkpoint(out_dir: Path | str, ckpt: PipelineCheckpoint) -> Path:
    """Atomic write of checkpoint JSON."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = checkpoint_path(out)
    payload = json.dumps(ckpt.as_dict(), indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    fd, tmp = tempfile.mkstemp(prefix=".ckpt-", suffix=".json", dir=str(out))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return path

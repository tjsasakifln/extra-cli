"""Canonical run-manifest contract for Command Center jobs.

The manifest (not stdout) is the primary source for artifact discovery.
Stdout path parsing remains a marked fallback only.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0.0"

# Paths printed in logs — fallback only when marked as such.
_PATH_RE = re.compile(
    r"(?P<path>(?:/|\./)?(?:[\w.-]+/)*[\w.-]+\.(?:json|jsonl|csv|md|pdf|xlsx|xls|zip|html|txt))",
    re.IGNORECASE,
)


class ArtifactRole(StrEnum):
    PRIMARY_DELIVERABLE = "primary_deliverable"
    WORKBOOK = "workbook"
    EXECUTIVE_REPORT = "executive_report"
    EVIDENCE = "evidence"
    SOURCE_DATA = "source_data"
    MANIFEST = "manifest"
    LOG = "log"
    ATTACHMENT = "attachment"
    REVIEW_PACKAGE = "review_package"


class OutputProfile(StrEnum):
    INTERNAL_ANALYSIS = "INTERNAL_ANALYSIS"
    CLIENT_READY = "CLIENT_READY"
    AUDIT_EVIDENCE = "AUDIT_EVIDENCE"


class StageState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    WAITING_REVIEW = "waiting_review"


HUMAN_STAGES = (
    ("preparing", "Preparando"),
    ("collecting", "Coletando"),
    ("processing", "Processando"),
    ("validating", "Validando"),
    ("generating_report", "Gerando relatório"),
    ("awaiting_review", "Aguardando revisão"),
    ("completed", "Concluído"),
)


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class ArtifactDecl:
    path: str
    logical_name: str
    role: str
    media_type: str
    title: str
    description: str = ""
    schema: str | None = None
    primary: bool = False
    previewable: bool = False
    downloadable: bool = True
    review_required: bool = False
    generated_from: list[str] = field(default_factory=list)
    sha256: str | None = None
    size_bytes: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class StageDecl:
    stage_id: str
    stage_label: str
    state: str = StageState.PENDING.value
    current: int | None = None
    total: int | None = None
    percentage: float | None = None
    message: str | None = None
    warning: str | None = None
    started_at: str | None = None
    finished_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProgressEvent:
    stage_id: str
    stage_label: str
    state: str
    message: str | None = None
    current: int | None = None
    total: int | None = None
    percentage: float | None = None
    warning: str | None = None
    artifact_created: str | None = None
    review_created: str | None = None
    timestamp: str = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RunManifest:
    schema_version: str = SCHEMA_VERSION
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    job_id: str | None = None
    capability_id: str | None = None
    workflow_id: str | None = None
    workspace_id: str | None = None
    project_id: str | None = None
    client_id: str | None = None
    started_at: str = field(default_factory=_utcnow)
    finished_at: str | None = None
    status: str = "running"
    stages: list[dict[str, Any]] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    code_sha: str | None = None
    data_as_of: str | None = None
    source_snapshots: list[dict[str, Any]] = field(default_factory=list)
    coverage: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    reviews_required: list[dict[str, Any]] = field(default_factory=list)
    terminal_claim: str | None = None
    checksums: dict[str, str] = field(default_factory=dict)
    output_profile: str | None = None
    discovery_source: str = "manifest"  # manifest | stdout_fallback
    progress_events: list[dict[str, Any]] = field(default_factory=list)
    data_mode: str | None = None  # REAL | FIXTURE
    canonical_command: list[str] = field(default_factory=list)
    exit_code: int | None = None
    preflight: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def add_artifact(self, art: ArtifactDecl, *, root: Path | None = None) -> None:
        d = art.to_dict()
        path = Path(art.path)
        if path.is_file():
            d["sha256"] = sha256_file(path)
            d["size_bytes"] = path.stat().st_size
            self.checksums[art.logical_name] = d["sha256"]
        self.artifacts.append(d)

    def primary_artifacts(self) -> list[dict[str, Any]]:
        return [a for a in self.artifacts if a.get("primary") or a.get("role") == ArtifactRole.PRIMARY_DELIVERABLE.value]

    def write(self, directory: Path, filename: str = "run-manifest.json") -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / filename
        payload = self.to_dict()
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        # self-checksum of manifest body without nested mutation races
        self.checksums["run-manifest.json"] = sha256_file(path)
        payload["checksums"] = self.checksums
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return path


def load_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("run-manifest must be a JSON object")
    if "schema_version" not in data or "run_id" not in data:
        raise ValueError("run-manifest missing required fields schema_version/run_id")
    return data


def validate_manifest(data: dict[str, Any]) -> list[str]:
    """Return list of validation errors (empty = valid)."""
    errors: list[str] = []
    for key in ("schema_version", "run_id", "status", "artifacts"):
        if key not in data:
            errors.append(f"missing field: {key}")
    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"unsupported schema_version: {data.get('schema_version')}")
    arts = data.get("artifacts")
    if arts is not None and not isinstance(arts, list):
        errors.append("artifacts must be a list")
    elif isinstance(arts, list):
        for i, a in enumerate(arts):
            if not isinstance(a, dict):
                errors.append(f"artifacts[{i}] not an object")
                continue
            for k in ("path", "logical_name", "role", "media_type", "title"):
                if k not in a:
                    errors.append(f"artifacts[{i}] missing {k}")
    return errors


def media_type_for(path: Path) -> str:
    ext = path.suffix.lower()
    return {
        ".pdf": "application/pdf",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xls": "application/vnd.ms-excel",
        ".csv": "text/csv",
        ".json": "application/json",
        ".jsonl": "application/x-ndjson",
        ".md": "text/markdown",
        ".html": "text/html",
        ".zip": "application/zip",
        ".txt": "text/plain",
        ".log": "text/plain",
    }.get(ext, "application/octet-stream")


def role_for_path(path: Path, *, primary_hint: bool = False) -> str:
    name = path.name.lower()
    ext = path.suffix.lower()
    if name in {"run-manifest.json", "manifest.json"} or "manifest" in name:
        return ArtifactRole.MANIFEST.value
    if ext == ".pdf":
        return ArtifactRole.EXECUTIVE_REPORT.value if primary_hint or "executiv" in name or "relatorio" in name or "report" in name else ArtifactRole.ATTACHMENT.value
    if ext in {".xlsx", ".xls"}:
        return ArtifactRole.WORKBOOK.value
    if "review" in name:
        return ArtifactRole.REVIEW_PACKAGE.value
    if ext in {".log"}:
        return ArtifactRole.LOG.value
    if ext in {".json", ".jsonl", ".csv"}:
        return ArtifactRole.SOURCE_DATA.value
    if "evidence" in name or "evidencia" in name:
        return ArtifactRole.EVIDENCE.value
    return ArtifactRole.ATTACHMENT.value


def declare_file(
    path: Path,
    *,
    role: str | None = None,
    title: str | None = None,
    primary: bool = False,
    review_required: bool = False,
    description: str = "",
    generated_from: list[str] | None = None,
) -> ArtifactDecl:
    path = path.resolve()
    r = role or role_for_path(path, primary_hint=primary)
    previewable = path.suffix.lower() in {".pdf", ".xlsx", ".xls", ".csv", ".json", ".jsonl", ".md", ".html", ".txt"}
    return ArtifactDecl(
        path=str(path),
        logical_name=path.name,
        role=r,
        media_type=media_type_for(path),
        title=title or path.stem.replace("_", " ").replace("-", " ").title(),
        description=description,
        primary=primary or r in {ArtifactRole.PRIMARY_DELIVERABLE.value, ArtifactRole.EXECUTIVE_REPORT.value, ArtifactRole.WORKBOOK.value},
        previewable=previewable,
        downloadable=True,
        review_required=review_required,
        generated_from=list(generated_from or []),
        sha256=sha256_file(path) if path.is_file() else None,
        size_bytes=path.stat().st_size if path.is_file() else None,
    )


def discover_paths_from_stdout(stdout: str) -> list[str]:
    """Legacy fallback: extract file-like paths from stdout. Clearly secondary."""
    found: list[str] = []
    seen: set[str] = set()
    for m in _PATH_RE.finditer(stdout or ""):
        p = m.group("path")
        if p not in seen:
            seen.add(p)
            found.append(p)
    return found


def finalize_manifest_from_job_dir(
    job_dir: Path,
    *,
    job_id: str,
    capability_id: str,
    status: str,
    parameters: dict[str, Any],
    code_sha: str | None,
    stdout: str = "",
    known_artifacts: list[str] | None = None,
    workflow_id: str | None = None,
    limitations: list[str] | None = None,
    coverage: dict[str, Any] | None = None,
    output_profile: str | None = None,
) -> tuple[RunManifest, Path]:
    """Build and write run-manifest for a finished job directory."""
    mf = RunManifest(
        job_id=job_id,
        capability_id=capability_id,
        workflow_id=workflow_id,
        status=status,
        parameters=parameters,
        code_sha=code_sha,
        finished_at=_utcnow(),
        limitations=list(limitations or []),
        coverage=dict(coverage or {}),
        output_profile=output_profile,
        discovery_source="manifest",
    )
    paths: list[Path] = []
    for p in known_artifacts or []:
        paths.append(Path(p))
    # Prefer files already under job_dir
    if job_dir.is_dir():
        for child in sorted(job_dir.rglob("*")):
            if child.is_file() and child.name != "run-manifest.json":
                paths.append(child)
    # Fallback stdout paths
    fallback_used = False
    for raw in discover_paths_from_stdout(stdout):
        candidate = Path(raw)
        if not candidate.is_absolute():
            # resolve relative to repo-ish cwd later; keep as-is if exists
            pass
        if candidate.is_file():
            paths.append(candidate)
            fallback_used = True
    if fallback_used and not (known_artifacts or []):
        mf.discovery_source = "stdout_fallback"
        mf.warnings.append(
            "Alguns artefatos foram descobertos via parsing de stdout (fallback legado). "
            "Prefira run-manifest declarado."
        )

    seen: set[str] = set()
    for p in paths:
        try:
            resolved = p.resolve()
        except OSError:
            continue
        key = str(resolved)
        if key in seen or not resolved.is_file():
            continue
        seen.add(key)
        primary = resolved.suffix.lower() in {".pdf", ".xlsx"} and (
            "executiv" in resolved.name.lower()
            or "relatorio" in resolved.name.lower()
            or "workbook" in resolved.name.lower()
            or "comercial" in resolved.name.lower()
            or "indice" in resolved.name.lower()
            or "cobertura" in resolved.name.lower()
        )
        mf.add_artifact(declare_file(resolved, primary=primary))

    # Always register log files if present
    for log_name in ("stdout.log", "stderr.log"):
        lp = job_dir / log_name
        if lp.is_file():
            key = str(lp.resolve())
            if key not in seen:
                mf.add_artifact(
                    declare_file(lp, role=ArtifactRole.LOG.value, title=log_name, primary=False)
                )

    out = mf.write(job_dir)
    mf.add_artifact(
        declare_file(out, role=ArtifactRole.MANIFEST.value, title="Run manifest", primary=False)
    )
    # rewrite with manifest self-entry
    out = mf.write(job_dir)
    return mf, out


def human_stage_timeline(events: list[dict[str, Any]] | None, status: str) -> list[dict[str, Any]]:
    """Map progress events into the fixed human timeline labels."""
    by_id = {e.get("stage_id"): e for e in (events or []) if e.get("stage_id")}
    out: list[dict[str, Any]] = []
    terminal_done = status in {"SUCCEEDED", "PARTIAL", "EMPTY_OK"}
    terminal_fail = status in {"FAILED", "CANCELLED", "BLOCKED_TECHNICAL", "BLOCKED_EXTERNAL"}
    reached = False
    for stage_id, label in HUMAN_STAGES:
        ev = by_id.get(stage_id)
        if ev:
            out.append(
                {
                    "stage_id": stage_id,
                    "stage_label": label,
                    "state": ev.get("state") or StageState.SUCCEEDED.value,
                    "message": ev.get("message"),
                }
            )
            if ev.get("state") == StageState.RUNNING.value:
                reached = True
            continue
        # heuristic fill
        if stage_id == "completed" and terminal_done:
            state = StageState.SUCCEEDED.value
        elif stage_id == "completed" and terminal_fail:
            state = StageState.FAILED.value
        elif not reached and terminal_done:
            state = StageState.SUCCEEDED.value
        else:
            state = StageState.PENDING.value
        out.append({"stage_id": stage_id, "stage_label": label, "state": state, "message": None})
    return out

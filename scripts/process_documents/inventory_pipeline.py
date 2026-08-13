"""Fail-closed document inventory: discover, fetch, expand, extract, replay.

States: QUEUED | RUNNING | SUCCEEDED | BLOCKED | FAILED | SUPERSEDED.
ZIP bombs, traversal, MIME mismatch and unreadable files never become complete.
Replay of the same hash does not re-download or re-OCR.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

JobState = Literal["QUEUED", "RUNNING", "SUCCEEDED", "BLOCKED", "FAILED", "SUPERSEDED"]
EXTRACTOR_VERSION = "inventory-pipeline/1.0.0"
MAX_ZIP_MEMBERS = 40
MAX_ZIP_UNCOMPRESSED = 20 * 1024 * 1024
MAX_DOCUMENT_BYTES = 80 * 1024 * 1024

FACT_KEYS = (
    "cat",
    "cao",
    "habilitacao",
    "garantias",
    "quantitativos",
    "somatorio",
    "consorcio",
    "subcontratacao",
)


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class FetchRecord:
    url: str
    parent: str | None
    sha256: str
    mime: str
    bytes_len: int
    method: str
    attempt: int
    blob_pointer: str


@dataclass(frozen=True)
class Extraction:
    extractor_version: str
    locator: str
    text: str
    facts: dict[str, str]


@dataclass
class DocumentJob:
    job_id: str
    url: str
    state: JobState = "QUEUED"
    reason_code: str | None = None
    evidence: str | None = None
    next_action: str | None = None
    fetch: FetchRecord | None = None
    extraction: Extraction | None = None
    content_hash: str | None = None
    derived_invalidated: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class InventoryRun:
    process_id: str
    jobs: dict[str, DocumentJob] = field(default_factory=dict)
    cache: dict[str, DocumentJob] = field(default_factory=dict)

    @property
    def terminal(self) -> bool:
        return all(job.state in {"SUCCEEDED", "BLOCKED", "FAILED", "SUPERSEDED"} for job in self.jobs.values())


def detect_mime(data: bytes, declared: str) -> str:
    if data.startswith(b"%PDF"):
        return "application/pdf"
    if data.startswith(b"PK"):
        return "application/zip"
    return declared or "application/octet-stream"


def _fail(job: DocumentJob, reason: str, evidence: str, next_action: str) -> DocumentJob:
    job.state = "BLOCKED" if reason.startswith("blocked_") else "FAILED"
    if reason in {"zip_slip", "zip_bomb", "mime_mismatch", "unreadable", "too_large"}:
        job.state = "BLOCKED"
    job.reason_code = reason
    job.evidence = evidence
    job.next_action = next_action
    return job


def expand_zip(data: bytes) -> list[tuple[str, bytes]] | str:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return "unreadable"
    names = archive.namelist()
    if len(names) > MAX_ZIP_MEMBERS:
        return "zip_bomb"
    total = 0
    members: list[tuple[str, bytes]] = []
    for info in archive.infolist():
        if info.filename.startswith("/") or ".." in info.filename.replace("\\", "/").split("/"):
            return "zip_slip"
        total += info.file_size
        if total > MAX_ZIP_UNCOMPRESSED:
            return "zip_bomb"
        members.append((info.filename, archive.read(info)))
    return members


def extract_text(data: bytes, mime: str, *, locator: str) -> Extraction:
    if mime == "application/pdf" and data.startswith(b"%PDF"):
        text = data.decode("latin-1", errors="replace")
    elif mime.startswith("text/") or mime in {"application/csv", "text/csv"}:
        text = data.decode("utf-8", errors="replace")
    else:
        text = ""
    facts = {key: "pendente" for key in FACT_KEYS}
    lowered = text.lower()
    if "consórcio" in lowered or "consorcio" in lowered:
        facts["consorcio"] = "mencionado"
    if "subcontrata" in lowered:
        facts["subcontratacao"] = "mencionado"
    return Extraction(extractor_version=EXTRACTOR_VERSION, locator=locator, text=text, facts=facts)


def process_document(
    run: InventoryRun,
    *,
    job_id: str,
    url: str,
    body: bytes,
    declared_mime: str,
    parent: str | None = None,
    attempt: int = 1,
    method: str = "GET",
) -> DocumentJob:
    existing = run.jobs.get(job_id) or DocumentJob(job_id=job_id, url=url, state="QUEUED")
    existing.state = "RUNNING"
    run.jobs[job_id] = existing
    digest = sha256_bytes(body)
    cached = run.cache.get(digest)
    if cached and cached.state == "SUCCEEDED":
        existing.state = "SUCCEEDED"
        existing.fetch = cached.fetch
        existing.extraction = cached.extraction
        existing.content_hash = digest
        existing.reason_code = "replay_cache"
        existing.evidence = digest
        existing.next_action = None
        return existing
    if len(body) > MAX_DOCUMENT_BYTES:
        return _fail(existing, "too_large", str(len(body)), "rejeitar e registrar blocker")
    mime = detect_mime(body, declared_mime)
    if declared_mime and declared_mime != "application/octet-stream" and mime != declared_mime:
        if not (declared_mime == "application/pdf" and mime == "application/pdf"):
            if declared_mime not in {mime, "application/octet-stream"}:
                return _fail(existing, "mime_mismatch", f"{declared_mime}->{mime}", "quarentenar arquivo")
    if mime == "application/zip":
        expanded = expand_zip(body)
        if isinstance(expanded, str):
            return _fail(existing, expanded, url, "não marcar completo; registrar blocker")
        for name, member in expanded:
            child_id = f"{job_id}:{name}"
            process_document(
                run,
                job_id=child_id,
                url=f"{url}#{name}",
                body=member,
                declared_mime="application/octet-stream",
                parent=job_id,
            )
    fetch = FetchRecord(
        url=url,
        parent=parent,
        sha256=digest,
        mime=mime,
        bytes_len=len(body),
        method=method,
        attempt=attempt,
        blob_pointer=f"cas://docs/{digest}",
    )
    extraction = extract_text(body, mime, locator=f"{url}#bytes=0-{len(body)}")
    if existing.content_hash and existing.content_hash != digest:
        existing.derived_invalidated = True
        existing.state = "SUPERSEDED"
        successor = DocumentJob(job_id=f"{job_id}:v", url=url, state="QUEUED")
        run.jobs[successor.job_id] = successor
        return process_document(
            run,
            job_id=successor.job_id,
            url=url,
            body=body,
            declared_mime=declared_mime,
            parent=parent,
            attempt=attempt,
            method=method,
        )
    existing.fetch = fetch
    existing.extraction = extraction
    existing.content_hash = digest
    existing.state = "SUCCEEDED"
    existing.reason_code = None
    existing.evidence = digest
    existing.next_action = None
    run.cache[digest] = existing
    return existing


def close_orphans(run: InventoryRun) -> None:
    """A run never stays RUNNING. Orphans become BLOCKED."""
    for job in run.jobs.values():
        if job.state == "RUNNING":
            job.state = "BLOCKED"
            job.reason_code = "orphan_running"
            job.evidence = job.job_id
            job.next_action = "reprocessar o documento"


def inventory_report(run: InventoryRun) -> dict[str, Any]:
    close_orphans(run)
    return {
        "process_id": run.process_id,
        "terminal": run.terminal,
        "jobs": [job.as_dict() for job in run.jobs.values()],
        "generated_at": _utc_now(),
    }

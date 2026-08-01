"""Quarantine for corrupt / empty / MIME-mismatched process documents.

Never promotes quarantined blobs to success inventory. OCR is only suggested
when native text extraction is unusable (caller decides to run OCR).
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.process_documents.storage import ensure_roots, sha256_bytes, write_json

QUARANTINE_REL = Path("quarantine")


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class QuarantineVerdict:
    quarantined: bool
    reasons: list[str]
    sha256: str | None
    size_bytes: int
    declared_mime: str | None
    detected_mime: str | None
    native_text_usable: bool | None
    ocr_recommended: bool
    extraction_quality: str  # high | low | none | unknown
    text_origin: str  # native | ocr | none | unknown

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _looks_like_html(data: bytes) -> bool:
    head = data[:256].lstrip().lower()
    return head.startswith(b"<!doctype html") or head.startswith(b"<html") or b"<html" in head[:64]


def _looks_like_pdf(data: bytes) -> bool:
    return data[:5] == b"%PDF-"


def assess_blob(
    data: bytes,
    *,
    declared_mime: str | None = None,
    detected_mime: str | None = None,
    native_text: str | None = None,
    min_native_text_chars: int = 40,
) -> QuarantineVerdict:
    reasons: list[str] = []
    size = len(data)
    digest = sha256_bytes(data) if data else None
    if size == 0:
        reasons.append("empty_file")
    declared = (declared_mime or "").lower()
    detected = (detected_mime or "").lower()

    if "pdf" in declared or (declared.endswith("/pdf")):
        if data and not _looks_like_pdf(data):
            reasons.append("declared_pdf_but_not_pdf")
            if _looks_like_html(data):
                reasons.append("html_disguised_as_pdf")
    if detected and declared:
        # coarse family mismatch
        def family(m: str) -> str:
            if "pdf" in m:
                return "pdf"
            if "html" in m:
                return "html"
            if "zip" in m or "officedocument" in m or "spreadsheet" in m:
                return "office"
            if "image" in m:
                return "image"
            if "json" in m:
                return "json"
            return m.split(";")[0].strip()

        if family(declared) != family(detected) and family(declared) and family(detected):
            reasons.append("mime_inconsistent")
    if data and _looks_like_html(data) and "pdf" in (declared + detected):
        if "html_disguised_as_pdf" not in reasons:
            reasons.append("html_disguised_as_pdf")

    native_usable: bool | None
    quality = "unknown"
    text_origin = "unknown"
    ocr_rec = False
    if native_text is None:
        native_usable = None
        # PDF without extractable text often needs OCR — recommend only when PDF magic
        if data and _looks_like_pdf(data) and not reasons:
            ocr_rec = False  # unknown until extraction attempted
            text_origin = "unknown"
    else:
        stripped = native_text.strip()
        native_usable = len(stripped) >= min_native_text_chars
        if native_usable:
            quality = "high"
            text_origin = "native"
            ocr_rec = False
        else:
            quality = "low" if stripped else "none"
            text_origin = "native"
            ocr_rec = bool(data and _looks_like_pdf(data) and not reasons)
            if not native_usable and data and _looks_like_pdf(data):
                reasons.append("native_text_unusable")

    # quarantine when hard failures; native_text_unusable alone is soft (OCR path)
    hard = [r for r in reasons if r != "native_text_unusable"]
    return QuarantineVerdict(
        quarantined=bool(hard),
        reasons=reasons,
        sha256=digest,
        size_bytes=size,
        declared_mime=declared_mime,
        detected_mime=detected_mime,
        native_text_usable=native_usable,
        ocr_recommended=ocr_rec,
        extraction_quality=quality,
        text_origin=text_origin,
    )


def quarantine_blob(
    data: bytes,
    *,
    verdict: QuarantineVerdict | None = None,
    meta: dict[str, Any] | None = None,
    raw_root: Path | None = None,
    meta_root: Path | None = None,
) -> dict[str, Any]:
    """Persist quarantined blob under raw/quarantine and meta ledger. Never CAS-success."""
    v = verdict or assess_blob(data)
    if not v.quarantined:
        return {"quarantined": False, "verdict": v.to_dict()}
    raw, meta_dir = ensure_roots(raw_root=raw_root, meta_root=meta_root)
    digest = v.sha256 or sha256_bytes(data or b"")
    qdir = raw / QUARANTINE_REL / digest[:2] / digest[2:4]
    qdir.mkdir(parents=True, exist_ok=True)
    blob_path = qdir / digest
    if not blob_path.is_file():
        tmp = blob_path.with_suffix(".partial")
        tmp.write_bytes(data)
        os.replace(tmp, blob_path)
    record = {
        "recorded_at": _now(),
        "sha256": digest,
        "verdict": v.to_dict(),
        "meta": meta or {},
        "raw_uri": f"quarantine://{digest}",
        "path": str(blob_path),
    }
    ledger = meta_dir / QUARANTINE_REL / "ledger.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    write_json(meta_dir / QUARANTINE_REL / f"{digest}.json", record)
    return {"quarantined": True, "record": record}

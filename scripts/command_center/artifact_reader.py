"""Safe artifact reading within allowed roots."""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from fastapi import HTTPException

from scripts.command_center.config import Settings
from scripts.command_center.redaction import redact_text
from scripts.command_center.security import resolve_under_roots


def read_artifact(path: str, settings: Settings, *, max_bytes: int | None = None) -> dict[str, Any]:
    resolved = resolve_under_roots(path, settings.allowed_artifact_roots)
    if not resolved.is_file():
        raise HTTPException(status_code=404, detail="Não é um arquivo.")
    size = resolved.stat().st_size
    limit = max_bytes or settings.max_artifact_read_bytes
    suffix = resolved.suffix.lower()
    meta = {
        "path": str(resolved),
        "name": resolved.name,
        "size_bytes": size,
        "suffix": suffix,
        "truncated": size > limit,
    }
    if suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".xlsx", ".xls"}:
        return {
            **meta,
            "kind": "binary",
            "message": "Arquivo binário. Use download local; conteúdo não é embutido na API.",
            "downloadable": True,
        }
    raw = resolved.read_bytes()[:limit]
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("utf-8", errors="replace")
    text = redact_text(text)
    if suffix == ".json":
        try:
            data = json.loads(text)
            return {**meta, "kind": "json", "data": data}
        except json.JSONDecodeError:
            return {**meta, "kind": "text", "text": text, "parse_error": "JSON inválido"}
    if suffix == ".jsonl":
        rows = []
        for i, line in enumerate(text.splitlines()):
            if i >= settings.artifact_sample_lines:
                break
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                rows.append({"_raw": line})
        return {**meta, "kind": "jsonl", "rows": rows, "sample_lines": len(rows)}
    if suffix == ".csv":
        reader = csv.DictReader(io.StringIO(text))
        rows = []
        for i, row in enumerate(reader):
            if i >= settings.artifact_sample_lines:
                break
            rows.append(row)
        return {**meta, "kind": "csv", "rows": rows, "fieldnames": reader.fieldnames}
    if suffix in {".md", ".markdown"}:
        # Do not execute HTML; return as markdown text for sanitized client render
        return {**meta, "kind": "markdown", "text": text}
    return {**meta, "kind": "text", "text": text}


def list_recent_artifacts(settings: Settings, limit: int = 30) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for root in settings.allowed_artifact_roots:
        if not root.exists():
            continue
        try:
            for p in root.rglob("*"):
                if not p.is_file():
                    continue
                if any(part.startswith(".") for part in p.parts):
                    continue
                if p.suffix.lower() not in {".json", ".jsonl", ".md", ".csv", ".xlsx", ".pdf", ".txt", ".log"}:
                    continue
                try:
                    st = p.stat()
                except OSError:
                    continue
                items.append(
                    {
                        "path": str(p),
                        "name": p.name,
                        "size_bytes": st.st_size,
                        "mtime": st.st_mtime,
                        "suffix": p.suffix.lower(),
                    }
                )
        except OSError:
            continue
    items.sort(key=lambda x: x["mtime"], reverse=True)
    return items[:limit]

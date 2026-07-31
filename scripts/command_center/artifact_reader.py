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
    if suffix in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
        return {
            **meta,
            "kind": "binary",
            "message": "Arquivo de imagem. Use download local.",
            "downloadable": True,
        }
    if suffix == ".pdf":
        return {
            **meta,
            "kind": "pdf",
            "message": "PDF disponível para visualização embutida no navegador.",
            "downloadable": True,
            "previewable": True,
            "embed_url": f"/api/artifacts/download?path={resolved}",
        }
    if suffix in {".xlsx", ".xls"}:
        return {
            **meta,
            "kind": "xlsx",
            "message": "Planilha disponível para pré-visualização no navegador.",
            "downloadable": True,
            "previewable": True,
            "preview_url": f"/api/artifacts/preview-xlsx?path={resolved}",
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
            table = _json_as_table(data, max_rows=settings.artifact_sample_lines)
            out: dict[str, Any] = {**meta, "kind": "json", "data": data}
            if table:
                out["table"] = table
            # Prefer summary keys engineers care about
            if isinstance(data, dict):
                out["summary"] = _json_summary(data)
            return out
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


def _json_as_table(data: Any, *, max_rows: int = 200) -> dict[str, Any] | None:
    """If JSON is a list of objects (or dict with common list keys), expose as table."""
    rows: list[Any] | None = None
    source_key: str | None = None
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        for key in (
            "leads",
            "rows",
            "items",
            "results",
            "records",
            "data",
            "top20",
            "ranking",
            "opportunities",
            "entities",
            "recent",
        ):
            val = data.get(key)
            if isinstance(val, list) and val and isinstance(val[0], dict):
                rows = val
                source_key = key
                break
    if not rows or not isinstance(rows[0], dict):
        return None
    sample = rows[:max_rows]
    # Stable column order from first row keys, then union of next rows
    cols: list[str] = list(sample[0].keys())
    seen = set(cols)
    for r in sample[1:]:
        for k in r.keys():
            if k not in seen:
                cols.append(k)
                seen.add(k)
    # Prefer business-facing columns first when present
    preferred = [
        "cnpj",
        "cnpj14",
        "razao_social",
        "name",
        "orgao",
        "orgao_nome",
        "uf",
        "municipio",
        "valor",
        "score",
        "status",
        "title",
        "path",
    ]
    ordered = [c for c in preferred if c in seen] + [c for c in cols if c not in preferred]
    return {
        "columns": ordered[:40],
        "rows": [{k: _cell(r.get(k)) for k in ordered[:40]} for r in sample],
        "total_rows": len(rows),
        "sampled": len(sample),
        "source_key": source_key,
    }


def _cell(v: Any) -> Any:
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)[:200]
    return v


def _json_summary(data: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "status",
        "reason",
        "run_id",
        "target",
        "leads",
        "count",
        "total",
        "coverage",
        "message",
        "git_sha",
        "modality",
        "all_pass",
        "any_blocked",
        "any_fail",
    )
    out: dict[str, Any] = {}
    for k in keys:
        if k in data:
            val = data[k]
            if isinstance(val, list):
                out[k] = f"{len(val)} itens"
            elif isinstance(val, dict):
                out[k] = f"objeto ({len(val)} chaves)"
            else:
                out[k] = val
    return out


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

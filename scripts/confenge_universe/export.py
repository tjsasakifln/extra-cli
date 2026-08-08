"""Deterministic streamable JSONL + manifest export."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator
from datetime import date
from pathlib import Path
from typing import Any

from scripts.confenge_universe import (
    DEFAULT_JSONL_NAME,
    DEFAULT_MANIFEST_NAME,
    MANIFEST_VERSION,
    MODULE_VERSION,
    RULE_VERSION,
    SCHEMA_VERSION,
)


def _stable_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def write_jsonl_stream(
    records: Iterable[dict[str, Any]],
    path: Path,
) -> dict[str, Any]:
    """Write records sorted by entity key for determinism. Streams line-by-line."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # Materialize keys only for sort — records may be large but entity count
    # is << contract count. For true streaming of already-sorted input, use
    # write_jsonl_presorted.
    items = list(records)
    items.sort(
        key=lambda r: (
            str(r.get("cnpj_root") or ""),
            str(r.get("entity_key") or ""),
            str(r.get("cnpj14") or ""),
        )
    )
    n = 0
    h = hashlib.sha256()
    with path.open("w", encoding="utf-8") as f:
        for rec in items:
            line = _stable_dumps(rec) + "\n"
            f.write(line)
            h.update(line.encode("utf-8"))
            n += 1
    return {"lines": n, "sha256": h.hexdigest(), "path": str(path)}


def write_jsonl_presorted(
    records: Iterator[dict[str, Any]],
    path: Path,
) -> dict[str, Any]:
    """Write pre-sorted stream without buffering all records."""
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    h = hashlib.sha256()
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            line = _stable_dumps(rec) + "\n"
            f.write(line)
            h.update(line.encode("utf-8"))
            n += 1
    return {"lines": n, "sha256": h.hexdigest(), "path": str(path)}


def build_manifest(
    *,
    as_of: date,
    repo_sha: str,
    source_meta: dict[str, Any],
    counts: dict[str, Any],
    jsonl_meta: dict[str, Any],
    rule_version: str = RULE_VERSION,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    input_roots = int(counts.get("input_supplier_roots") or 0)
    eligibles = int(counts.get("eligibles") or 0)
    exclusions = int(counts.get("exclusions") or 0)
    recon_ok = input_roots == eligibles + exclusions
    manifest: dict[str, Any] = {
        "schema_version": MANIFEST_VERSION,
        "module_version": MODULE_VERSION,
        "rule_version": rule_version,
        "universe_schema_version": SCHEMA_VERSION,
        "as_of": as_of.isoformat(),
        "repo_sha": repo_sha,
        "source": source_meta,
        "outputs": {
            "jsonl": {
                "filename": Path(jsonl_meta.get("path") or DEFAULT_JSONL_NAME).name,
                "lines": jsonl_meta.get("lines"),
                "sha256": jsonl_meta.get("sha256"),
            }
        },
        "counts": {
            **counts,
            "reconciliation": {
                "formula": "input_supplier_roots = eligibles + exclusions",
                "input_supplier_roots": input_roots,
                "eligibles": eligibles,
                "exclusions": exclusions,
                "ok": recon_ok,
            },
        },
        "invariants": {
            "score_is_order_only": True,
            "commercial_tier_never_discard": True,
            "dnc_dominant_for_outreach": True,
            "no_silent_top_n_subset": True,
            "no_invented_legal_regime_or_delay": True,
        },
    }
    if extra:
        manifest["extra"] = extra
    return manifest


def write_manifest(manifest: dict[str, Any], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True, default=str) + "\n"
    path.write_text(text, encoding="utf-8")
    return path


def default_output_paths(out_dir: Path) -> tuple[Path, Path]:
    return out_dir / DEFAULT_JSONL_NAME, out_dir / DEFAULT_MANIFEST_NAME

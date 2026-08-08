"""Write versioned JSONL + run manifesto."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.confenge_contact_resolution import SCHEMA_ID
from scripts.confenge_contact_resolution.models import AccountContactResolution, empty_manifest

CANDIDATES_FILENAME = "confenge-contact-candidates-v1.jsonl"
MANIFEST_FILENAME = "run_manifest.json"


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_resolution_artifacts(
    resolutions: list[AccountContactResolution],
    output_dir: Path | str,
    *,
    mode: str = "batch",
    service_context: str = "generic",
    run_id: str | None = None,
) -> dict[str, Any]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    rid = run_id or f"confenge-contact-{datetime.now(UTC).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"
    started = _now()
    manifest = empty_manifest(
        run_id=rid,
        mode=mode,
        service_context=service_context,
        output_dir=str(out),
        input_count=len(resolutions),
    )
    manifest["started_at"] = started

    jsonl_path = out / CANDIDATES_FILENAME
    lines: list[str] = []
    with_cand = 0
    with_rec = 0
    absence = 0
    cache_hits = 0
    adapters: set[str] = set()

    for r in resolutions:
        d = r.as_dict()
        # ensure schema identity
        d["schema_id"] = SCHEMA_ID
        line = json.dumps(d, ensure_ascii=False, default=str, sort_keys=True)
        lines.append(line)
        if r.candidates:
            with_cand += 1
        else:
            absence += 1
        if r.recommended_candidate_id:
            with_rec += 1
        if r.cache_hit:
            cache_hits += 1
        adapters.update(r.adapters_used)

    # Idempotent: rewrite full file deterministically for this run
    body = "\n".join(lines) + ("\n" if lines else "")
    jsonl_path.write_text(body, encoding="utf-8")
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()

    manifest["finished_at"] = _now()
    manifest["resolved_count"] = len(resolutions)
    manifest["with_candidates"] = with_cand
    manifest["with_recommended"] = with_rec
    manifest["absence_count"] = absence
    manifest["cache_hits"] = cache_hits
    manifest["adapters"] = sorted(adapters)
    manifest["checksum_sha256"] = digest
    manifest["ok"] = True
    manifest_path = out / MANIFEST_FILENAME
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {
        "ok": True,
        "run_id": rid,
        "jsonl": str(jsonl_path),
        "manifest": str(manifest_path),
        "checksum_sha256": digest,
        "counts": {
            "resolved": len(resolutions),
            "with_candidates": with_cand,
            "with_recommended": with_rec,
            "absence": absence,
        },
    }

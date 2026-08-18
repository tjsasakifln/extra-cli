"""Write authority-handoff artifacts for web-cfg#83. Never emits PUBLISHABLE or INDEX."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from scripts.historical_contract_authority.adapters import to_public_read
from scripts.historical_contract_authority.schema import (
    CONSUMER_ID,
    FORBIDDEN_PUBLIC_STATES,
    HANDOFF_DIR,
    HANDOFF_SCHEMA,
    MAX_HANDOFF_READY,
    SCHEMA,
    canonical_dumps,
    hash_without_content_hash,
    producer_sha,
    sha256_bytes,
)

_HANDOFF_LEAVES = (
    "dossiers",
    "public-read",
    "source-claim-matrix",
    "editorial-briefs",
    "manifest.json",
    "status.json",
    "lineage.json",
    "SHA256SUMS",
)


def refuse_catalog_mode_collision(root: Path, catalog_mode: str) -> None:
    manifest = root / "manifest.json"
    if not manifest.is_file():
        return
    try:
        existing = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    previous = existing.get("catalog_mode")
    if previous and previous != catalog_mode:
        raise ValueError(f"handoff_catalog_mode_collision:{previous}->{catalog_mode}")


def reset_handoff_root(root: Path) -> None:
    for name in _HANDOFF_LEAVES:
        path = root / name
        if path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = payload if isinstance(payload, str) else canonical_dumps(payload) + "\n"
    path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")


def _scan_forbidden(node: Any) -> list[str]:
    blob = node if isinstance(node, str) else canonical_dumps(node)
    hits = [token for token in FORBIDDEN_PUBLIC_STATES if token in blob]
    return hits


def build_manifest(
    dossiers: list[dict[str, Any]],
    *,
    as_of: str,
    snapshot_hash: str,
    replay_command: str,
    catalog_mode: str,
) -> dict[str, Any]:
    ready = select_for_handoff(dossiers)
    selected = {item["dossier_id"] for item in ready}
    document = {
        "schema": HANDOFF_SCHEMA,
        "version": "1.0",
        "producer_commit": producer_sha(),
        "source_snapshot": snapshot_hash,
        "as_of": as_of,
        "catalog_mode": catalog_mode,
        "selected_ids": [item["dossier_id"] for item in ready],
        "states": {item["dossier_id"]: item.get("state") for item in dossiers},
        "score_decomposition": {
            item["dossier_id"]: (item.get("score") or {}) for item in dossiers if item.get("state") == "HANDOFF_READY"
        },
        "content_hashes": {item["dossier_id"]: item.get("content_hash") for item in dossiers},
        "source_coverage": {
            "dossier_count": len(dossiers),
            "handoff_ready": len(ready),
            "hold_for_data": sum(1 for item in dossiers if item.get("state") == "HOLD_FOR_DATA"),
            "reject": sum(1 for item in dossiers if item.get("state") == "REJECT"),
            "claim_scope": "SC",
            "claim_authorization": None,
        },
        "handoff_ready": {item["dossier_id"]: item["dossier_id"] in selected for item in dossiers},
        "no_index_authorization": True,
        "no_publication_authorization": True,
        "consumer": CONSUMER_ID,
        "replay_command": replay_command,
        "dossier_schema": SCHEMA,
    }
    hits = _scan_forbidden(document)
    if hits:
        raise ValueError(f"forbidden_manifest_token:{hits}")
    document["content_hash"] = hash_without_content_hash(document)
    return document


def select_for_handoff(dossiers: list[dict[str, Any]], *, limit: int = MAX_HANDOFF_READY) -> list[dict[str, Any]]:
    ready = [item for item in dossiers if item.get("state") == "HANDOFF_READY"]
    ready.sort(key=lambda item: (-float((item.get("score") or {}).get("score") or 0.0), item.get("dossier_id") or ""))
    chosen: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in ready:
        question = str((item.get("editorial") or {}).get("central_question") or item.get("dossier_id"))
        if question in seen:
            continue
        seen.add(question)
        chosen.append(item)
        if len(chosen) >= limit:
            break
    return chosen


def write_handoff(
    dossiers: list[dict[str, Any]],
    *,
    output_dir: Path | None = None,
    as_of: str,
    snapshot_hash: str,
    replay_command: str,
    catalog_mode: str = "fixture",
    live_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = output_dir or HANDOFF_DIR
    root.mkdir(parents=True, exist_ok=True)
    refuse_catalog_mode_collision(root, catalog_mode)
    reset_handoff_root(root)
    exported = select_for_handoff(dossiers)
    for dossier in exported:
        dossier_id = str(dossier["dossier_id"])
        analysis_id = dossier_id
        payload = dossier
        hits = _scan_forbidden(payload)
        if hits:
            raise ValueError(f"forbidden_dossier_token:{hits}")
        dossier_path = root / "dossiers" / f"{dossier_id}.json"
        _write(dossier_path, payload)
        public = to_public_read(payload)
        if public["data_state"] not in {"DATA_READY", "DATA_HOLD", "DATA_REJECT"}:
            raise ValueError("forbidden_data_state")
        _write(root / "public-read" / f"{analysis_id}.json", public)
        _write(
            root / "source-claim-matrix" / f"{analysis_id}.json",
            {"schema": "source-claim-matrix/1.0", "analysis_id": analysis_id, "claims": payload.get("claims") or []},
        )
        _write(
            root / "editorial-briefs" / f"{analysis_id}.json",
            {"schema": "editorial-brief/1.0", "analysis_id": analysis_id, "brief": payload.get("editorial") or {}},
        )
    manifest = build_manifest(
        dossiers, as_of=as_of, snapshot_hash=snapshot_hash, replay_command=replay_command, catalog_mode=catalog_mode
    )
    lineage = {
        "schema": "authority-handoff-lineage/1.0",
        "producer_commit": producer_sha(),
        "source_snapshot": snapshot_hash,
        "imports": [
            "scripts.contract_publication.engine.rank_candidates",
            "scripts.contract_comparables.engine.build_peer_group",
            "scripts.public_read_consumers.contract_analysis",
            "scripts.process_documents.inventory_pipeline",
        ],
        "does_not_rewrite": ["#414", "#415", "#400"],
        "consumer": CONSUMER_ID,
    }
    lineage["content_hash"] = hash_without_content_hash(lineage)
    status = {
        "schema": "authority-handoff-status/1.0",
        "as_of": as_of,
        "catalog_mode": catalog_mode,
        "handoff_ready_count": len(select_for_handoff(dossiers)),
        "states": {
            "HANDOFF_READY": sum(1 for item in dossiers if item.get("state") == "HANDOFF_READY"),
            "HOLD_FOR_DATA": sum(1 for item in dossiers if item.get("state") == "HOLD_FOR_DATA"),
            "REJECT": sum(1 for item in dossiers if item.get("state") == "REJECT"),
        },
        "no_index_authorization": True,
        "no_publication_authorization": True,
        "consumer": CONSUMER_ID,
        "live": live_meta or {},
        "reason_codes": sorted({code for item in dossiers for code in item.get("reason_codes") or []}),
    }
    status["content_hash"] = hash_without_content_hash(status)
    _write(root / "manifest.json", manifest)
    _write(root / "lineage.json", lineage)
    _write(root / "status.json", status)
    sums: list[str] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file() and p.name != "SHA256SUMS"):
        digest = sha256_bytes(path.read_bytes())
        rel = path.relative_to(root).as_posix()
        sums.append(f"{digest}  {rel}")
    _write(root / "SHA256SUMS", "\n".join(sums) + "\n")
    return {"root": str(root), "manifest": manifest, "status": status, "lineage": lineage}


def file_sha256sums(root: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    sums = (root / "SHA256SUMS").read_text(encoding="utf-8")
    for line in sums.splitlines():
        if not line.strip():
            continue
        digest, name = line.split("  ", 1)
        mapping[name] = digest
    return mapping

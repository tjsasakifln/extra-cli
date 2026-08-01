"""Human approval gate for indexable / PUBLISH_READY snapshots."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.pseo.models import ApprovalArtifact
from scripts.pseo.provenance import EXPORT_VERSION, canonical_json, sha256_text


def approval_hash(payload: dict[str, Any]) -> str:
    body = {k: payload[k] for k in sorted(payload) if k != "approval_hash"}
    return sha256_text(canonical_json(body))


def load_approval(path: Path | None) -> ApprovalArtifact | None:
    if path is None or not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    art = ApprovalArtifact.model_validate(data)
    expected = approval_hash(art.model_dump(mode="json"))
    if art.approval_hash and art.approval_hash != expected:
        raise ValueError("approval_hash does not match payload")
    return art


def verify_approval_for_publish(
    approval: ApprovalArtifact | None,
    *,
    dataset_hash: str,
    schema_version: str,
    exporter_version: str,
    source_commit_sha: str,
) -> dict[str, Any]:
    """Return status dict. Never auto-approves."""
    if approval is None:
        return {
            "status": "REVIEW_REQUIRED",
            "indexable": False,
            "publish_ready": False,
            "reason": "human approval artifact missing",
        }
    if approval.decision == "REJECTED":
        return {
            "status": "REJECTED",
            "indexable": False,
            "publish_ready": False,
            "reason": "human rejected",
        }
    if approval.dataset_hash != dataset_hash:
        return {
            "status": "INVALID_APPROVAL",
            "indexable": False,
            "publish_ready": False,
            "reason": "approval dataset_hash mismatch",
        }
    if approval.schema_version != schema_version:
        return {
            "status": "INVALID_APPROVAL",
            "indexable": False,
            "publish_ready": False,
            "reason": "approval schema_version mismatch",
        }
    if approval.exporter_version != exporter_version:
        return {
            "status": "INVALID_APPROVAL",
            "indexable": False,
            "publish_ready": False,
            "reason": "approval exporter_version mismatch",
        }
    if approval.source_commit_sha != source_commit_sha:
        return {
            "status": "INVALID_APPROVAL",
            "indexable": False,
            "publish_ready": False,
            "reason": "approval source_commit_sha mismatch (stale after change)",
        }
    if approval.decision not in {"APPROVED", "APPROVED_WITH_NOTES"}:
        return {
            "status": "INVALID_APPROVAL",
            "indexable": False,
            "publish_ready": False,
            "reason": f"unsupported decision {approval.decision}",
        }
    return {
        "status": "PUBLISH_READY",
        "indexable": True,
        "publish_ready": True,
        "reason": "human approval bound to dataset_hash/versions/commit",
        "actor": approval.actor,
        "decision": approval.decision,
    }


def write_approval_template(
    path: Path,
    *,
    dataset_hash: str,
    source_commit_sha: str,
    actor: str = "REPLACE_ME",
    decision: str = "APPROVED",
    notes: str = "",
    schema_version: str = "1.1.0",
    exporter_version: str = EXPORT_VERSION,
) -> Path:
    from datetime import UTC, datetime

    payload = {
        "decision": decision,
        "dataset_hash": dataset_hash,
        "schema_version": schema_version,
        "exporter_version": exporter_version,
        "source_commit_sha": source_commit_sha,
        "actor": actor,
        "approved_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "notes": notes or None,
    }
    payload["approval_hash"] = approval_hash(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path

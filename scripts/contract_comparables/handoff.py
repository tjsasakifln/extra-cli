"""Consumer-bound comparables handoff for web-cfg#83|#84. No editorial copy."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from scripts.contract_comparables.constants import (
    CONSUMER_WEB_CFG,
    LIVE_PAVING_CANARY_ID,
    LIVE_PAVING_HANDOFF_SCHEMA,
    PRODUCER_EXTRA_CLI,
    STATUS_BLOCKED,
    STATUS_COMPARABLE,
    STATUS_HOLD,
    STATUS_NOT,
)

HANDOFF_VOLATILE = frozenset(
    {"generated_at", "refresh_latency_ms", "per_group_ms", "retrieved_at", "verified_at", "unavailabilities"}
)


def _dump(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _write(path: Path, payload: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = payload if isinstance(payload, str) else _dump(payload)
    path.write_text(text, encoding="utf-8")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def ready_or_blocked(status: str) -> str:
    if status in {STATUS_COMPARABLE, STATUS_HOLD, STATUS_NOT}:
        return "READY"
    return "BLOCKED"


def consumer_instructions(envelope: dict[str, Any]) -> dict[str, Any]:
    return {
        "consumer": CONSUMER_WEB_CFG,
        "producer": PRODUCER_EXTRA_CLI,
        "publication_authorization": False,
        "index_authorization": False,
        "no_cross_repo_write": True,
        "official_live": bool(envelope.get("official_live")),
        "claim_scope": envelope.get("claim_scope"),
        "national_claim_authorized": False,
        "do_not_write": [
            "narrative",
            "title",
            "meta",
            "cta",
            "html",
            "sitemap",
            "INDEX",
            "publication",
        ],
        "next_consumer_action": (
            "Read payload.json and state.json. Do not INDEX or publish. "
            "Do not treat HOLD_FOR_DATA or NOT_COMPARABLE as a ranking."
        ),
    }


def write_comparables_handoff(envelope: dict[str, Any], output_dir: Path) -> dict[str, Any]:
    root = Path(output_dir)
    if root.exists():
        for path in sorted(root.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir() and path != root:
                path.rmdir()
    root.mkdir(parents=True, exist_ok=True)

    status = str(envelope.get("status") or STATUS_BLOCKED)
    decision = ready_or_blocked(status)
    payload = {
        "schema": LIVE_PAVING_HANDOFF_SCHEMA,
        "canary_id": envelope.get("canary_id") or LIVE_PAVING_CANARY_ID,
        "peer_group_id": envelope.get("peer_group_id"),
        "status": status,
        "reason_codes": list(envelope.get("reason_codes") or []),
        "official_live": bool(envelope.get("official_live")),
        "source_kind": envelope.get("source_kind"),
        "catalog_mode": envelope.get("catalog_mode"),
        "as_of": envelope.get("as_of"),
        "target_contract_id": envelope.get("target_contract_id") or envelope.get("focal_contract_id"),
        "question": envelope.get("question"),
        "question_id": envelope.get("question_id"),
        "metric": envelope.get("metric"),
        "grain": envelope.get("grain"),
        "value_semantic": envelope.get("value_semantic"),
        "unit": envelope.get("unit"),
        "regime": envelope.get("regime"),
        "modality": envelope.get("modality"),
        "geography": envelope.get("geography"),
        "period": envelope.get("period"),
        "porte": envelope.get("porte"),
        "typology": envelope.get("typology"),
        "inclusion_rules": envelope.get("inclusion_rules"),
        "exclusion_rules": envelope.get("exclusion_rules"),
        "universe": envelope.get("universe"),
        "coverage": envelope.get("coverage"),
        "missingness": envelope.get("missingness"),
        "suppression": envelope.get("suppression"),
        "total_found": envelope.get("total_found"),
        "total_eligible": envelope.get("total_eligible"),
        "total_used": envelope.get("total_used"),
        "match_quality": envelope.get("match_quality"),
        "metrics_produced": envelope.get("metrics_produced") or [],
        "unit_metrics": envelope.get("unit_metrics"),
        "document": envelope.get("document"),
        "content_hash": envelope.get("content_hash"),
        "consumer": CONSUMER_WEB_CFG,
        "producer": PRODUCER_EXTRA_CLI,
        "publication_authorization": False,
        "index_authorization": False,
        "no_cross_repo_write": True,
        "national_claim_authorized": False,
        "claim_scope": envelope.get("claim_scope"),
        "method": envelope.get("method"),
        "method_version": envelope.get("method_version"),
        "policy_version": envelope.get("policy_version"),
        "invalidation_keys": envelope.get("invalidation_keys"),
        "outlier_treatment": envelope.get("outlier_treatment"),
        "monetary_normalization": envelope.get("monetary_normalization"),
        "evidence_refs": list(envelope.get("evidence_refs") or []),
        "live": {
            key: value
            for key, value in dict(envelope.get("live") or {}).items()
            if key not in HANDOFF_VOLATILE | {"unavailabilities"}
        },
    }
    peers = list(envelope.get("peers") or [])
    peer_artifact: dict[str, Any]
    if peers:
        peer_artifact = {"kind": "peer_list", "n": len(peers), "peers": peers}
    else:
        peer_artifact = {
            "kind": "protected_aggregate",
            "n": int(envelope.get("total_used") or 0),
            "note": "No usable peer ids. Aggregate withheld because the group is not COMPARABLE.",
        }
    lineage = {
        "schema": "authority-handoff-lineage/1.0",
        "producer": PRODUCER_EXTRA_CLI,
        "consumer": CONSUMER_WEB_CFG,
        "imports": [
            "scripts.contract_comparables.engine.build_peer_group",
            "scripts.official_contract_semantics.export_comparables.observation_to_contract_record",
            "scripts.official_contract_semantics.extract.extract_record",
            "scripts.official_contract_semantics.live.records_from_consulta_listing",
        ],
        "does_not_rewrite": ["#400", "#414", "#302", "web-cfg"],
        "source_kind": envelope.get("source_kind"),
        "official_live": bool(envelope.get("official_live")),
        "live": {
            key: value
            for key, value in dict(envelope.get("live") or {}).items()
            if key not in HANDOFF_VOLATILE
        },
        "replay_command": envelope.get("replay_command"),
    }
    manifest = {
        "schema": LIVE_PAVING_HANDOFF_SCHEMA,
        "canary_id": payload["canary_id"],
        "status": status,
        "handoff_decision": decision,
        "content_hash": envelope.get("content_hash"),
        "peer_group_id": envelope.get("peer_group_id"),
        "target_contract_id": payload["target_contract_id"],
        "official_live": bool(envelope.get("official_live")),
        "source_kind": envelope.get("source_kind"),
        "consumer": CONSUMER_WEB_CFG,
        "producer": PRODUCER_EXTRA_CLI,
        "publication_authorization": False,
        "index_authorization": False,
        "no_cross_repo_write": True,
        "national_claim_authorized": False,
        "claim_scope": envelope.get("claim_scope"),
        "replay_command": envelope.get("replay_command"),
        "files": [
            "payload.json",
            "manifest.json",
            "lineage.json",
            "evidence_refs.json",
            "peer_list.json",
            "limitations.json",
            "state.json",
            "reason_codes.json",
            "replay.txt",
            "consumer_instructions.json",
            "READY.json" if decision == "READY" else "BLOCKED.json",
            "SHA256SUMS",
        ],
    }
    state = {
        "status": status,
        "handoff_decision": decision,
        "reason_codes": list(envelope.get("reason_codes") or []),
        "official_live": bool(envelope.get("official_live")),
        "catalog_mode": envelope.get("catalog_mode"),
        "total_found": envelope.get("total_found"),
        "total_eligible": envelope.get("total_eligible"),
        "total_used": envelope.get("total_used"),
        "metrics_produced": envelope.get("metrics_produced") or [],
        "publication_authorization": False,
        "index_authorization": False,
    }
    _write(root / "payload.json", payload)
    _write(root / "manifest.json", manifest)
    _write(root / "lineage.json", lineage)
    _write(root / "evidence_refs.json", {"refs": list(envelope.get("evidence_refs") or [])})
    _write(root / "peer_list.json", peer_artifact)
    _write(root / "limitations.json", {"limitations": list(envelope.get("limitations") or [])})
    _write(root / "state.json", state)
    _write(root / "reason_codes.json", {"reason_codes": list(envelope.get("reason_codes") or [])})
    (root / "replay.txt").write_text(str(envelope.get("replay_command") or "") + "\n", encoding="utf-8")
    _write(root / "consumer_instructions.json", consumer_instructions(envelope))
    marker = {
        "schema": LIVE_PAVING_HANDOFF_SCHEMA,
        "status": decision,
        "peer_status": status,
        "content_hash": envelope.get("content_hash"),
        "canary_id": payload["canary_id"],
        "publication_authorization": False,
        "index_authorization": False,
        "official_live": bool(envelope.get("official_live")),
    }
    if decision == "READY":
        _write(root / "READY.json", marker)
        blocked = root / "BLOCKED.json"
        if blocked.exists():
            blocked.unlink()
    else:
        _write(root / "BLOCKED.json", {**marker, "prerequisite": (envelope.get("document") or {}).get("prerequisite") or envelope.get("prerequisite")})
        ready = root / "READY.json"
        if ready.exists():
            ready.unlink()
    sums: list[str] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file() and p.name != "SHA256SUMS"):
        digest = _sha256_bytes(path.read_bytes())
        sums.append(f"{digest}  {path.relative_to(root).as_posix()}")
    (root / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
    if (root / "READY.json").exists() and (root / "BLOCKED.json").exists():
        raise RuntimeError("READY.json and BLOCKED.json are mutually exclusive")
    return {"root": str(root), "decision": decision, "status": status, "content_hash": envelope.get("content_hash")}


def sha256sums_map(root: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for line in (root / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, name = line.split("  ", 1)
        mapping[name] = digest
    return mapping


def verify_sha256sums(root: Path) -> list[str]:
    errors: list[str] = []
    listed = sha256sums_map(root)
    files = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and p.name != "SHA256SUMS"}
    if set(listed) != files:
        errors.append(f"sha256sums_mismatch:{sorted(set(listed) ^ files)}")
    for name, digest in listed.items():
        actual = _sha256_bytes((root / name).read_bytes())
        if actual != digest:
            errors.append(f"digest:{name}")
    ready = (root / "READY.json").exists()
    blocked = (root / "BLOCKED.json").exists()
    if ready == blocked:
        errors.append("ready_xor_blocked")
    return errors

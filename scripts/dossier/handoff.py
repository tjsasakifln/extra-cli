"""Consumer-bound handoff for `public-read-confenge-dossier/1.0`.

Only the de-identified projection crosses this boundary. The private dossier
never leaves extra-cli: web-cfg publishes public bodies and public contracts,
never the prospect.

Layout mirrors the contract-comparables rendezvous so the consumer side stays
one fail-closed pattern: ``READY.json`` xor ``BLOCKED.json`` plus
``SHA256SUMS.txt`` over every other file.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from scripts.dossier.constants import (
    CATALOG_OFFICIAL_LIVE,
    CONSUMER_WEB_CFG,
    CONTRACT_VERSION,
    DATA_READY,
    METHOD_VERSION,
    POLICY_VERSION,
    PRODUCER_EXTRA_CLI,
    PUBLIC_SCHEMA,
)

HANDOFF_SCHEMA = "authority-handoff-confenge-dossier/1.0"
FAMILY = "confenge-dossier"
CHANNEL = "official-live-01"
SUMS_NAME = "SHA256SUMS.txt"

DECISION_READY = "READY"
DECISION_BLOCKED = "BLOCKED"

REASON_NOT_OFFICIAL_LIVE = "handoff_requires_official_live"
REASON_NOT_DATA_READY = "handoff_requires_data_ready"
REASON_NOT_PUBLISHABLE = "handoff_requires_publication_readiness"


def rendezvous_dir() -> Path:
    """Where the consumer looks. Overridable with ``CONFENGE_HANDOFF_DIR``."""
    base = os.environ.get("CONFENGE_HANDOFF_DIR")
    root = Path(base) if base else Path.home() / ".local" / "share" / "confenge" / "handoffs"
    return root / FAMILY / CHANNEL


def _dump(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload if isinstance(payload, str) else _dump(payload), encoding="utf-8")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def decide(public: dict[str, Any]) -> tuple[str, list[str]]:
    """READY only when the projection is official, ready and publishable."""
    reasons: list[str] = []
    if public.get("catalog_mode") != CATALOG_OFFICIAL_LIVE:
        reasons.append(REASON_NOT_OFFICIAL_LIVE)
    if public.get("data_state") != DATA_READY:
        reasons.append(REASON_NOT_DATA_READY)
    if public.get("publication_readiness") != DATA_READY:
        reasons.append(REASON_NOT_PUBLISHABLE)
    return (DECISION_BLOCKED if reasons else DECISION_READY), reasons


def write_handoff(public: dict[str, Any], manifest: dict[str, Any], root: Path) -> dict[str, Any]:
    decision, reasons = decide(public)
    root.mkdir(parents=True, exist_ok=True)
    for stale in root.iterdir():
        if stale.is_file():
            stale.unlink()

    handoff_manifest = {
        "schema": HANDOFF_SCHEMA,
        "payload_schema": PUBLIC_SCHEMA,
        "contract_version": CONTRACT_VERSION,
        "method_version": METHOD_VERSION,
        "policy_version": POLICY_VERSION,
        "producer": PRODUCER_EXTRA_CLI,
        "consumer": CONSUMER_WEB_CFG,
        "producer_commit": manifest.get("producer_sha"),
        "dossier_id": manifest.get("dossier_id"),
        "source_dossier_hash": public.get("source_dossier_hash"),
        "content_hash": public.get("content_hash"),
        "as_of": public.get("as_of"),
        "catalog_mode": public.get("catalog_mode"),
        "data_state": public.get("data_state"),
        "publication_readiness": public.get("publication_readiness"),
        # The consumer owns editorial INDEX. The producer never grants it.
        "publication_authorization": False,
        "index_authorization": False,
        "no_cross_repo_write": True,
        "carries_prospect_identity": False,
        "files": ["payload.json", "manifest.json", "state.json", f"{decision}.json", SUMS_NAME],
    }
    state = {
        "handoff_decision": decision,
        "reason_codes": reasons + list(public.get("reason_codes") or []),
        "data_state": public.get("data_state"),
        "catalog_mode": public.get("catalog_mode"),
        "publication_authorization": False,
        "index_authorization": False,
    }
    marker = {
        "schema": HANDOFF_SCHEMA,
        "status": decision,
        "content_hash": public.get("content_hash"),
        "dossier_id": manifest.get("dossier_id"),
        "publication_authorization": False,
        "index_authorization": False,
        "reason_codes": reasons,
    }

    _write(root / "payload.json", public)
    _write(root / "manifest.json", handoff_manifest)
    _write(root / "state.json", state)
    _write(root / f"{decision}.json", marker)

    sums = [
        f"{_sha256(path.read_bytes())}  {path.relative_to(root).as_posix()}"
        for path in sorted(p for p in root.rglob("*") if p.is_file() and p.name != SUMS_NAME)
    ]
    (root / SUMS_NAME).write_text("\n".join(sums) + "\n", encoding="utf-8")

    if (root / f"{DECISION_READY}.json").exists() and (root / f"{DECISION_BLOCKED}.json").exists():
        raise RuntimeError("READY.json and BLOCKED.json are mutually exclusive")

    return {
        "root": str(root),
        "decision": decision,
        "reason_codes": reasons,
        "content_hash": public.get("content_hash"),
    }


def verify_handoff(root: Path) -> list[str]:
    errors: list[str] = []
    sums_file = root / SUMS_NAME
    if not sums_file.exists():
        return [f"missing:{SUMS_NAME}"]
    listed: dict[str, str] = {}
    for line in sums_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, name = line.split("  ", 1)
        listed[name] = digest
    present = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and p.name != SUMS_NAME}
    if set(listed) != present:
        errors.append(f"sha256sums_mismatch:{sorted(set(listed) ^ present)}")
    for name, digest in listed.items():
        path = root / name
        if not path.exists() or _sha256(path.read_bytes()) != digest:
            errors.append(f"digest:{name}")
    ready = (root / f"{DECISION_READY}.json").exists()
    blocked = (root / f"{DECISION_BLOCKED}.json").exists()
    if ready == blocked:
        errors.append("ready_xor_blocked")
    if ready:
        payload = json.loads((root / "payload.json").read_text(encoding="utf-8"))
        if payload.get("catalog_mode") != CATALOG_OFFICIAL_LIVE:
            errors.append("ready_on_non_official_live")
        if payload.get("publication_readiness") != DATA_READY:
            errors.append("ready_without_publication_readiness")
    return errors

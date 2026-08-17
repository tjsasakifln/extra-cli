"""Deterministic export, manifest, compare and hash verify."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.public_read_consumers.allowlist import unauthorized_fields
from scripts.public_read_consumers.contract_analysis import (
    SCHEMA as ANALYSIS_SCHEMA,
)
from scripts.public_read_consumers.contract_analysis import (
    hashed_analysis,
    project_catalog,
    render_status_markdown,
    select_canary,
    status_report,
    validate_analysis_payload,
)
from scripts.public_read_consumers.gates import (
    DATA_REJECT,
    NEEDS_DATA,
    REASON_FIXTURE_AS_LIVE,
    REASON_GATE_FAILED,
    REASON_LIVE_ABSENT,
    is_fixture_catalog,
)
from scripts.public_read_consumers.hashutil import (
    assert_public_clean,
    attach_hash,
    canonical_dumps,
    content_hash,
    scan_forbidden_tokens,
)
from scripts.public_read_consumers.market_answer import (
    CONSUMER_ID as MARKET_ID,
)
from scripts.public_read_consumers.market_answer import (
    project_market_answer,
    validate_market_answer,
)
from scripts.public_read_consumers.registry import get_consumer
from scripts.public_read_consumers.snapshot import (
    current_dir,
    diff_manifests,
    label_lkg,
    lkg_dir,
    load_manifest,
    preserve_or_fail,
    retain_previous,
    write_bytes,
)
from scripts.public_read_consumers.xray import CONSUMER_ID as XRAY_ID
from scripts.public_read_consumers.xray import project_xray, validate_xray

ANALYSES_DIR = "analyses"
MANIFEST_NAME = "manifest.json"
STATUS_JSON = "status-report.json"
STATUS_MD = "status-report.md"
PAYLOAD_NAME = "payload.json"


class ExportRefusedError(ValueError):
    def __init__(self, reason_code: str, message: str | None = None):
        self.reason_code = reason_code
        super().__init__(message or reason_code)


def load_json(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    return payload


def _analysis_filename(candidate_id: str) -> str:
    safe = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in candidate_id)
    return f"{safe}.json"


def _fixture_mode(raw: dict[str, Any], *, fixture: bool) -> dict[str, Any]:
    payload = dict(raw)
    if fixture:
        payload["catalog_mode"] = "fixture"
        payload["official_live"] = False
        payload["producer_status"] = "CONTRACT_FIXTURE"
        if payload.get("claimed_live"):
            payload.setdefault("reason_codes", [])
    return payload


def build_contract_analysis_bundle(raw: dict[str, Any]) -> dict[str, Any]:
    catalog_mode = str(raw.get("catalog_mode") or "fixture")
    claimed_live = bool(raw.get("claimed_live", False))
    generated_at = str(raw.get("generated_at") or "")
    analyses = [hashed_analysis(item) for item in project_catalog(raw)]
    for item in analyses:
        validate_analysis_payload(item)
        leaks = unauthorized_fields(item, consumer_id="web-cfg/contract-analysis")
        if leaks:
            raise ValueError(f"unauthorized_field:{leaks[0]}")
    canary = select_canary(analyses)
    report = status_report(canary, catalog_mode=catalog_mode, claimed_live=claimed_live, generated_at=generated_at)
    entries = [
        {
            "analysis_candidate_id": item["analysis_candidate_id"],
            "path": f"{ANALYSES_DIR}/{_analysis_filename(str(item['analysis_candidate_id'] or 'unknown'))}",
            "content_hash": item["content_hash"],
            "data_state": item["data_state"],
            "publication_readiness": item.get("publication_readiness") or item["data_state"],
            "angle": item.get("angle"),
        }
        for item in analyses
    ]
    as_of_values = sorted(
        {
            item.get("as_of") or (item.get("freshness") or {}).get("source_as_of")
            for item in analyses
            if item.get("as_of") or (item.get("freshness") or {}).get("source_as_of")
        }
    )
    as_of = as_of_values[0] if len(as_of_values) == 1 else as_of_values or None
    official_live = catalog_mode == "official_live" and claimed_live
    if catalog_mode == "fixture":
        official_live = False
    manifest_body = {
        "schema": ANALYSIS_SCHEMA,
        "contract_version": "v1.0.0",
        "consumer": {"id": "web-cfg/contract-analysis", "family": "web-cfg / contract-analysis family"},
        "consumer_id": "web-cfg/contract-analysis",
        "grain": "analysis_candidate_id",
        "generated_at": generated_at,
        "as_of": as_of,
        "source_as_of": as_of,
        "catalog_mode": catalog_mode,
        "claimed_live": claimed_live,
        "producer_status": "CONTRACT_FIXTURE" if catalog_mode == "fixture" else "OFFICIAL_LIVE",
        "official_live": official_live,
        "data_ready_is_not_index_permission": True,
        "canary": {
            "selected_ids": list(canary.selected_ids),
            "selected_candidate_ids": list(canary.selected_ids),
            "size": len(canary.selected_ids),
            "angles": list(canary.angles),
            "shortfall": canary.shortfall,
            "reason_codes": list(canary.reason_codes),
        },
        "analyses": entries,
        "status_report": report,
    }
    if catalog_mode == "fixture" and claimed_live:
        manifest_body["official_live"] = False
        manifest_body["producer_status"] = "CONTRACT_FIXTURE"
    assert_public_clean(manifest_body)
    manifest = attach_hash(manifest_body)
    return {
        "manifest": manifest,
        "analyses": analyses,
        "status_report": report,
        "status_markdown": render_status_markdown(report),
        "schema": ANALYSIS_SCHEMA,
        "content_hash": manifest["content_hash"],
        "catalog_mode": catalog_mode,
        "official_live": official_live,
        "producer_status": manifest["producer_status"],
        "reason_codes": list(canary.reason_codes),
    }


def build_single_payload(consumer_id: str, raw: dict[str, Any]) -> dict[str, Any]:
    if consumer_id == MARKET_ID:
        payload = project_market_answer(raw)
        validate_market_answer(payload)
    elif consumer_id == XRAY_ID:
        payload = project_xray(raw)
        validate_xray(payload)
    else:
        raise KeyError(f"unknown_single_consumer:{consumer_id}")
    leaks = unauthorized_fields(payload, consumer_id=consumer_id)
    if leaks:
        raise ValueError(f"unauthorized_field:{leaks[0]}")
    return payload


def gate_ok_for_export(consumer_id: str, document: dict[str, Any], *, live: bool) -> tuple[bool, str | None]:
    if live and is_fixture_catalog(document):
        return False, REASON_FIXTURE_AS_LIVE
    if live and not document.get("official_live"):
        return False, REASON_LIVE_ABSENT
    if document.get("catalog_mode") == "fixture" and document.get("claimed_live"):
        reasons = document.get("reason_codes") or ()
        if consumer_id == "web-cfg/contract-analysis":
            analyses = document.get("analyses") if isinstance(document.get("analyses"), list) else []
            if any(
                REASON_FIXTURE_AS_LIVE in (item.get("reason_codes") or ())
                for item in analyses
                if isinstance(item, dict)
            ):
                return True, None
        if REASON_FIXTURE_AS_LIVE not in reasons and document.get("official_live"):
            return False, REASON_FIXTURE_AS_LIVE
    state = document.get("answer_state") or document.get("data_state")
    if state == DATA_REJECT and REASON_FIXTURE_AS_LIVE in (document.get("reason_codes") or ()):
        if live:
            return False, REASON_FIXTURE_AS_LIVE
    if live and state in {DATA_REJECT, NEEDS_DATA}:
        return False, REASON_GATE_FAILED
    return True, None


def write_contract_analysis_export(raw: dict[str, Any], output_dir: str | Path) -> Path:
    bundle = build_contract_analysis_bundle(raw)
    root = Path(output_dir)
    analyses_dir = root / ANALYSES_DIR
    analyses_dir.mkdir(parents=True, exist_ok=True)
    for item in bundle["analyses"]:
        dest = analyses_dir / _analysis_filename(str(item.get("analysis_candidate_id") or "unknown"))
        retain_previous(dest, item)
        write_bytes(dest, canonical_dumps(item).encode("utf-8"))
    write_bytes(root / STATUS_JSON, canonical_dumps(bundle["status_report"]).encode("utf-8"))
    write_bytes(root / STATUS_MD, bundle["status_markdown"].encode("utf-8"))
    write_bytes(root / MANIFEST_NAME, canonical_dumps(bundle["manifest"]).encode("utf-8"))
    return root / MANIFEST_NAME


def write_single_export(consumer_id: str, raw: dict[str, Any], output_dir: str | Path) -> Path:
    payload = build_single_payload(consumer_id, raw)
    root = Path(output_dir)
    dest = root / PAYLOAD_NAME
    retain_previous(dest, payload)
    write_bytes(dest, canonical_dumps(payload).encode("utf-8"))
    manifest = attach_hash(
        {
            "schema": payload.get("schema"),
            "consumer_id": consumer_id,
            "catalog_mode": payload.get("catalog_mode"),
            "claimed_live": payload.get("claimed_live"),
            "producer_status": payload.get("producer_status"),
            "official_live": payload.get("official_live"),
            "as_of": payload.get("as_of"),
            "generated_at": payload.get("generated_at"),
            "payload_path": PAYLOAD_NAME,
            "payload_content_hash": payload.get("content_hash"),
            "answer_state": payload.get("answer_state"),
            "reason_codes": payload.get("reason_codes"),
        }
    )
    write_bytes(root / MANIFEST_NAME, canonical_dumps(manifest).encode("utf-8"))
    return root / MANIFEST_NAME


def export_consumer(
    consumer_id: str,
    raw: dict[str, Any],
    output_dir: str | Path,
    *,
    fixture: bool,
    live: bool,
    now: str,
) -> dict[str, Any]:
    record = get_consumer(consumer_id)
    resolved = record["consumer_id"]
    payload = _fixture_mode(raw, fixture=fixture)
    if live and fixture:
        raise ExportRefusedError(REASON_FIXTURE_AS_LIVE)
    if live and is_fixture_catalog(payload):
        raise ExportRefusedError(REASON_FIXTURE_AS_LIVE)
    if live and payload.get("catalog_mode") != "official_live":
        raise ExportRefusedError(REASON_LIVE_ABSENT)

    if resolved == "web-cfg/contract-analysis":
        bundle = build_contract_analysis_bundle(payload)
        document = bundle["manifest"]
        gate_ok, reason = gate_ok_for_export(resolved, {**document, "analyses": bundle["analyses"]}, live=live)
    else:
        document = build_single_payload(resolved, payload)
        gate_ok, reason = gate_ok_for_export(resolved, document, live=live)
        bundle = None

    decision = preserve_or_fail(
        output_dir=output_dir,
        now=now,
        gate_ok=gate_ok,
        live=live,
        official_live_present=bool(document.get("official_live")),
    )
    if live and not gate_ok:
        raise ExportRefusedError(reason or REASON_GATE_FAILED)
    if not gate_ok and decision["action"] == "fail":
        raise ExportRefusedError(decision["reason_code"] or reason or REASON_GATE_FAILED)
    if not gate_ok and decision["action"] == "preserve_lkg":
        raise ExportRefusedError(decision["reason_code"] or REASON_GATE_FAILED)

    if resolved == "web-cfg/contract-analysis":
        path = write_contract_analysis_export(payload, output_dir)
        manifest = bundle["manifest"]
    else:
        path = write_single_export(resolved, payload, output_dir)
        manifest = load_manifest(Path(output_dir)) or {}

    if gate_ok and manifest.get("catalog_mode") != "fixture":
        lkg_manifest = label_lkg(
            manifest, source_as_of=str(manifest.get("source_as_of") or manifest.get("as_of") or "")
        )
        write_bytes(lkg_dir(output_dir) / MANIFEST_NAME, canonical_dumps(lkg_manifest).encode("utf-8"))
    current = current_dir(output_dir)
    current.mkdir(parents=True, exist_ok=True)
    write_bytes(current / MANIFEST_NAME, canonical_dumps(manifest).encode("utf-8"))
    return {
        "ok": True,
        "path": str(path),
        "schema": manifest.get("schema"),
        "content_hash": manifest.get("content_hash"),
        "catalog_mode": manifest.get("catalog_mode"),
        "producer_status": manifest.get("producer_status"),
        "official_live": manifest.get("official_live"),
        "consumer_id": resolved,
    }


def compare_dirs(left: str | Path, right: str | Path) -> dict[str, Any]:
    return diff_manifests(load_manifest(Path(left)), load_manifest(Path(right)))


def verify_dir(path: str | Path) -> dict[str, Any]:
    root = Path(path)
    manifest = load_manifest(root)
    if not manifest:
        raise ValueError("manifest_missing")
    body = {key: value for key, value in manifest.items() if key != "content_hash"}
    expected = content_hash(body)
    if expected != manifest.get("content_hash"):
        raise ValueError("manifest_hash_mismatch")
    payload_path = root / PAYLOAD_NAME
    if payload_path.is_file():
        payload = load_json(payload_path)
        payload_body = {key: value for key, value in payload.items() if key != "content_hash"}
        if content_hash(payload_body) != payload.get("content_hash"):
            raise ValueError("payload_hash_mismatch")
    analyses_dir = root / ANALYSES_DIR
    if analyses_dir.is_dir():
        for entry in manifest.get("analyses") or []:
            rel = entry.get("path")
            if not rel:
                continue
            document = load_json(root / rel)
            body = {key: value for key, value in document.items() if key != "content_hash"}
            if content_hash(body) != document.get("content_hash"):
                raise ValueError(f"analysis_hash_mismatch:{entry.get('analysis_candidate_id')}")
            if document.get("content_hash") != entry.get("content_hash"):
                raise ValueError(f"analysis_manifest_hash_mismatch:{entry.get('analysis_candidate_id')}")
    if manifest.get("catalog_mode") == "fixture" and manifest.get("official_live"):
        raise ValueError(REASON_FIXTURE_AS_LIVE)
    if scan_forbidden_tokens(manifest):
        raise ValueError("forbidden_token")
    return {"ok": True, "content_hash": manifest.get("content_hash"), "schema": manifest.get("schema")}

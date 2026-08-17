"""Single refresh/replay command for official-live contract-analysis export.

Reuses #414 ranking/packs and #415 only when a valid peer group exists.
Never emits INDEX, revenue, lead, or a national claim.
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.contract_comparables.constants import LIVE_MISSING_SEMANTIC_COLUMNS
from scripts.contract_publication.engine import build_packs, rank_candidates
from scripts.contract_publication.export_400 import export_analysis
from scripts.contract_publication.official_snapshot import (
    SOURCE_KIND_BLOCKED,
    SOURCE_KIND_FIXTURE,
    SOURCE_KIND_OFFICIAL,
    UF_SC,
    fetch_official_sc_snapshot,
    query_hash,
)
from scripts.contract_publication.schema import CONSUMER_SCHEMA, CONTRACT_VERSION, producer_sha
from scripts.public_read_consumers.atomic_export import copy_lkg, write_tree_atomic
from scripts.public_read_consumers.gates import DATA_HOLD, DATA_READY, DATA_REJECT, freshness_block
from scripts.public_read_consumers.hashutil import (
    PII_FIELD_NAMES,
    assert_public_clean,
    canonical_dumps,
    collect_keys,
    content_hash,
    scan_forbidden_tokens,
)
from scripts.public_read_consumers.registry import get_consumer

CONSUMER_ID = "web-cfg/contract-analysis"
SCHEMA = CONSUMER_SCHEMA
SCHEMA_VERSION = "1.0"
MAX_EDITORIAL_REVIEW = 3
EXPORT_RELATIVE = "exports/public-read-live/contract-analysis/1.0"
VOLATILE_HASH_KEYS = frozenset({"generated_at", "expires_at", "producer_sha", "elapsed_ms"})

REASON_UNKNOWN_CONSUMER = "unknown_consumer"
REASON_FIXTURE_AS_LIVE = "fixture_as_live"
REASON_NATIONAL = "national_claim_blocked"
REASON_SCHEMA = "schema_incompatible"
REASON_PII = "pii_or_sensitive_field"
REASON_INDEX = "index_forbidden"
REASON_HIGH_VALUE = "high_value_without_insight"
REASON_NOT_COMPARABLE = "NOT_COMPARABLE"
REASON_NO_DOCUMENT = "document_absent"


class RefreshRefusedError(ValueError):
    def __init__(self, reason_code: str, message: str | None = None):
        self.reason_code = reason_code
        super().__init__(message or reason_code)


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_content_hash(payload: Any) -> str:
    def strip(node: Any) -> Any:
        if isinstance(node, dict):
            return {key: strip(value) for key, value in node.items() if key not in VOLATILE_HASH_KEYS}
        if isinstance(node, list):
            return [strip(item) for item in node]
        return node

    return content_hash(strip(payload))


def _not_comparable_peer() -> dict[str, Any]:
    return {
        "status": "NOT_COMPARABLE",
        "schema": "comparable-contracts/1.0",
        "version": "1.0",
        "metrics": {},
        "reason_codes": ["live_columns_unavailable", "fields_unavailable", *LIVE_MISSING_SEMANTIC_COLUMNS],
        "content_hash": None,
    }


def _claims_national(record: dict[str, Any]) -> bool:
    blob = json.dumps(record, ensure_ascii=False).casefold()
    if "nacional_completo" in blob or "national_claim_allowed" in blob and "true" in blob:
        return True
    geography = str(record.get("claim_scope") or record.get("geography") or record.get("uf") or "")
    if geography.upper() in {"BR", "BRASIL", "NATIONAL"} and record.get("national_claim"):
        return True
    return bool(record.get("national_claim") or record.get("claim_brasil"))


def _pii_hits(payload: Any) -> list[str]:
    tokens = tuple(PII_FIELD_NAMES)
    hits: list[str] = []
    for key in collect_keys(payload):
        leaf = key.split(".")[-1].lower()
        if leaf in tokens or any(token in leaf for token in ("cpf", "e_mail", "email", "telefone", "whatsapp")):
            hits.append(key)
    return hits


def _cap_editorial(candidates: list[Any]) -> list[Any]:
    kept_review = 0
    out: list[Any] = []
    for item in candidates:
        if item.candidate_state == "EDITORIAL_REVIEW":
            if kept_review >= MAX_EDITORIAL_REVIEW:
                out.append(
                    replace(
                        item,
                        candidate_state="HOLD_FOR_DATA",
                        reason_codes=tuple(dict.fromkeys((*item.reason_codes, "editorial_review_cap"))),
                    )
                )
                continue
            kept_review += 1
        out.append(item)
    return out


def load_input_snapshot(
    *,
    dsn: str | None,
    snapshot: dict[str, Any] | None,
    fixture: bool,
    live: bool,
) -> dict[str, Any]:
    if live and fixture:
        raise RefreshRefusedError(REASON_FIXTURE_AS_LIVE)
    if snapshot is not None:
        payload = dict(snapshot)
        source_kind = str(payload.get("source_kind") or SOURCE_KIND_FIXTURE)
        if live and source_kind != SOURCE_KIND_OFFICIAL:
            raise RefreshRefusedError(REASON_FIXTURE_AS_LIVE)
        if fixture:
            payload["source_kind"] = SOURCE_KIND_FIXTURE
            payload["official_projection_authorized"] = False
            payload["official_live"] = False
            payload["catalog_mode"] = payload.get("catalog_mode") or "fixture"
        return payload
    if fixture:
        raise RefreshRefusedError("fixture_snapshot_required")
    return fetch_official_sc_snapshot(dsn)


def _replay_command(out_dir: str) -> dict[str, Any]:
    del out_dir
    return {
        "module": "public_read_consumers",
        "argv": [
            "refresh",
            "--consumer",
            CONSUMER_ID,
            "--out",
            EXPORT_RELATIVE,
            "--replay-snapshot",
            "snapshot.json",
        ],
    }


def build_export_documents(
    snapshot: dict[str, Any],
    *,
    generated_at: str,
    out_dir: str,
) -> dict[str, Any]:
    source_kind = str(snapshot.get("source_kind") or SOURCE_KIND_FIXTURE)
    official = (
        source_kind == SOURCE_KIND_OFFICIAL
        and bool(snapshot.get("official_projection_authorized"))
        and bool(snapshot.get("live_select_executed"))
    )
    if snapshot.get("catalog_mode") == "fixture" and official:
        raise RefreshRefusedError(REASON_FIXTURE_AS_LIVE)
    if source_kind == SOURCE_KIND_BLOCKED:
        official = False
    as_of = str(snapshot.get("as_of") or generated_at)
    source_as_of = snapshot.get("source_as_of")
    records = list(snapshot.get("records") or [])
    for record in records:
        if _claims_national(record):
            raise RefreshRefusedError(REASON_NATIONAL)
    rank_mode = "official_projection" if official else "fixture"
    ranked = rank_candidates(records, as_of=as_of, catalog_mode=rank_mode)
    ranked = _cap_editorial(ranked)
    packs = build_packs(records, ranked, as_of=as_of, catalog_mode=rank_mode, policy=None)
    analyses: list[dict[str, Any]] = []
    for candidate in ranked:
        pack = dict(packs.get(candidate.analysis_candidate_id) or {})
        existing_peer = pack.get("peer_group") or {}
        if existing_peer.get("status") not in {"COMPARABLE", "PEER_VALID"}:
            pack["peer_group"] = _not_comparable_peer()
        analysis = export_analysis(candidate, pack, claimed_live=False)
        if not (pack.get("documents") or pack.get("official_refs") or analysis.get("official_refs")):
            if REASON_NO_DOCUMENT not in analysis["reason_codes"] and analysis["data_state"] != DATA_REJECT:
                analysis["reason_codes"] = [*analysis["reason_codes"], REASON_NO_DOCUMENT]
                if analysis["data_state"] == DATA_READY:
                    analysis["data_state"] = DATA_HOLD
                    analysis["publication_readiness"] = DATA_HOLD
        analysis["catalog_mode"] = "official_live" if official else "fixture"
        analysis["official_live"] = official
        analysis["producer_status"] = "OFFICIAL_LIVE" if official else "CONTRACT_FIXTURE"
        analysis["geography"] = {"uf": UF_SC, "claim_scope": "SC", "claim_authorization": None}
        analysis["no_index_authorization"] = True
        analysis["claim_scope"] = "SC"
        analysis["claim_authorization"] = None
        analysis["publication_readiness"] = analysis["data_state"]
        if analysis["peer_group"].get("status") in {"NOT_COMPARABLE", "ABSENT"}:
            if REASON_NOT_COMPARABLE not in analysis["reason_codes"]:
                analysis["reason_codes"] = [*analysis["reason_codes"], REASON_NOT_COMPARABLE]
        if analysis["data_state"] not in {DATA_READY, DATA_HOLD, DATA_REJECT}:
            raise RefreshRefusedError("forbidden_data_state")
        if "INDEX" in analysis["data_state"] or "PUBLISHABLE" in analysis["data_state"]:
            raise RefreshRefusedError(REASON_INDEX)
        pii = _pii_hits(analysis)
        if pii:
            raise RefreshRefusedError(REASON_PII)
        analysis["content_hash"] = stable_content_hash(analysis)
        analyses.append(analysis)

    freshness = freshness_block(generated_at=generated_at, source_as_of=str(source_as_of) if source_as_of else None)
    states = [item["data_state"] for item in analyses]
    editorial = sum(1 for item in ranked if item.candidate_state == "EDITORIAL_REVIEW")
    payload = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "consumer_id": CONSUMER_ID,
        "official_live": official,
        "producer_status": "OFFICIAL_LIVE"
        if official
        else ("OFFICIAL_DATA_UNAVAILABLE" if source_kind == SOURCE_KIND_BLOCKED else "CONTRACT_FIXTURE"),
        "generated_at": generated_at,
        "source_as_of": source_as_of,
        "as_of": as_of,
        "freshness_policy": freshness,
        "expires_at": freshness.get("expires_at"),
        "geography": {"uf": UF_SC, "claim_scope": "SC", "claim_authorization": None},
        "no_index_authorization": True,
        "claim_scope": "SC",
        "claim_authorization": None,
        "analyses": analyses,
        "facts": [item for item in analyses if item["data_state"] == DATA_READY],
        "unknowns": [item["analysis_candidate_id"] for item in analyses if item["data_state"] == DATA_HOLD],
        "limitations": [
            "Peer groups stay NOT_COMPARABLE until official unidade/quantidade/regime/modalidade/valor_semantic exist.",
            "Absence of a document is HOLD_FOR_DATA, never invented text.",
            "DATA_READY is not permission to index.",
        ],
        "reason_codes": sorted(
            {
                *(snapshot.get("reason_codes") or []),
                *(code for item in analyses for code in item.get("reason_codes") or ()),
            }
        ),
        "coverage": {
            "candidate_count": len(analyses),
            "editorial_review": editorial,
            "data_ready": states.count(DATA_READY),
            "data_hold": states.count(DATA_HOLD),
            "data_reject": states.count(DATA_REJECT),
        },
    }
    assert_public_clean(payload)
    if scan_forbidden_tokens(payload):
        raise RefreshRefusedError("forbidden_public_token")
    payload["content_hash"] = stable_content_hash(payload)

    sha = producer_sha()
    lineage = {
        "schema": "public-read-live-lineage/1.0",
        "consumer_id": CONSUMER_ID,
        "upstream_snapshot_hash": snapshot.get("content_hash"),
        "query_hash": snapshot.get("query_hash") or query_hash(uf=UF_SC, limit=len(records) or 40),
        "source_kind": source_kind,
        "producer_sha": sha,
        "replay_command": _replay_command(out_dir),
        "source_as_of": source_as_of,
        "record_ids": [item.get("analysis_candidate_id") for item in analyses],
        "evidence_packs": {
            item["analysis_candidate_id"]: {
                "version": item.get("evidence_pack_version"),
                "hash": item.get("evidence_pack_hash"),
                "schema": item.get("evidence_pack_schema"),
            }
            for item in analyses
        },
    }
    lineage["content_hash"] = stable_content_hash(lineage)

    status = {
        "schema": "public-read-live-status/1.0",
        "official_live": official,
        "producer_status": payload["producer_status"],
        "source_kind": source_kind,
        "coverage": payload["coverage"],
        "reason_codes": payload["reason_codes"],
        "comparability": "NOT_COMPARABLE",
        "no_index_authorization": True,
        "claim_scope": "SC",
        "claim_authorization": None,
        "freshness": freshness,
        "content_hash": payload["content_hash"],
    }
    manifest = {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "consumer_id": CONSUMER_ID,
        "official_live": official,
        "producer_status": payload["producer_status"],
        "generated_at": generated_at,
        "source_as_of": source_as_of,
        "freshness_policy": freshness.get("policy"),
        "expires_at": freshness.get("expires_at"),
        "content_hash": payload["content_hash"],
        "payload_path": "payload.json",
        "lineage_path": "lineage.json",
        "status_path": "status.json",
        "geography": payload["geography"],
        "no_index_authorization": True,
        "claim_scope": "SC",
        "claim_authorization": None,
        "upstream_snapshot_hash": snapshot.get("content_hash"),
        "producer_sha": sha,
        "replay_command": lineage["replay_command"],
    }
    manifest["content_hash"] = stable_content_hash(manifest)
    return {
        "payload": payload,
        "manifest": manifest,
        "lineage": lineage,
        "status": status,
        "snapshot": snapshot,
        "official_live": official,
    }


def validate_export(documents: dict[str, Any]) -> None:
    payload = documents["payload"]
    if payload.get("schema") != SCHEMA:
        raise RefreshRefusedError(REASON_SCHEMA)
    if payload.get("no_index_authorization") is not True:
        raise RefreshRefusedError(REASON_INDEX)
    if payload.get("claim_authorization"):
        raise RefreshRefusedError(REASON_NATIONAL)
    if payload.get("claim_scope") not in {"SC", "uf:SC"}:
        raise RefreshRefusedError(REASON_NATIONAL)
    pii = _pii_hits(payload)
    if pii:
        raise RefreshRefusedError(REASON_PII)
    editorial = int((payload.get("coverage") or {}).get("editorial_review") or 0)
    if editorial > MAX_EDITORIAL_REVIEW:
        raise RefreshRefusedError("editorial_review_cap")
    for item in payload.get("analyses") or ():
        if item.get("data_state") not in {DATA_READY, DATA_HOLD, DATA_REJECT}:
            raise RefreshRefusedError("forbidden_data_state")


def write_export(
    documents: dict[str, Any],
    output_dir: str | Path,
    *,
    replace_lkg: bool,
) -> dict[str, Any]:
    dest = Path(output_dir)
    files = {
        "payload.json": (canonical_dumps(documents["payload"]) + "\n").encode("utf-8"),
        "manifest.json": (canonical_dumps(documents["manifest"]) + "\n").encode("utf-8"),
        "lineage.json": (canonical_dumps(documents["lineage"]) + "\n").encode("utf-8"),
        "status.json": (canonical_dumps(documents["status"]) + "\n").encode("utf-8"),
        "snapshot.json": (canonical_dumps(documents["snapshot"]) + "\n").encode("utf-8"),
    }
    write_tree_atomic(dest, files)
    if replace_lkg:
        copy_lkg(dest)
    return {
        "ok": True,
        "path": str(dest),
        "content_hash": documents["payload"]["content_hash"],
        "official_live": documents["official_live"],
        "producer_status": documents["payload"]["producer_status"],
        "lkg": replace_lkg,
    }


def refresh(
    *,
    consumer: str,
    out: str | Path,
    dsn: str | None = None,
    snapshot: dict[str, Any] | None = None,
    fixture: bool = False,
    live: bool = False,
    generated_at: str | None = None,
    fail_before_rename: bool = False,
) -> dict[str, Any]:
    try:
        record = get_consumer(consumer)
    except KeyError as exc:
        raise RefreshRefusedError(REASON_UNKNOWN_CONSUMER) from exc
    if record["consumer_id"] != CONSUMER_ID:
        raise RefreshRefusedError(REASON_UNKNOWN_CONSUMER)
    loaded = load_input_snapshot(dsn=dsn, snapshot=snapshot, fixture=fixture, live=live)
    stamp = generated_at or _now()
    documents = build_export_documents(loaded, generated_at=stamp, out_dir=str(out))
    validate_export(documents)
    dest = Path(out)
    lkg_dir = dest / "lkg"
    previous_lkg = lkg_dir.is_dir()
    if fail_before_rename:
        raise RefreshRefusedError("atomic_fail_before_rename")
    replace_lkg = bool(documents["official_live"] or documents["payload"]["analyses"])
    if documents["payload"]["schema"] != SCHEMA:
        replace_lkg = False
    try:
        result = write_export(documents, dest, replace_lkg=replace_lkg)
    except Exception:
        if previous_lkg and not lkg_dir.is_dir():
            raise RuntimeError("lkg_lost")
        raise
    result["source_kind"] = loaded.get("source_kind")
    result["coverage"] = documents["payload"]["coverage"]
    result["reason_codes"] = documents["payload"]["reason_codes"]
    return result


def replay_dir(path: str | Path, *, generated_at: str | None = None) -> dict[str, Any]:
    snapshot = json.loads((Path(path) / "snapshot.json").read_text(encoding="utf-8"))
    return refresh(
        consumer=CONSUMER_ID,
        out=path,
        snapshot=snapshot,
        fixture=snapshot.get("source_kind") != SOURCE_KIND_OFFICIAL,
        live=snapshot.get("source_kind") == SOURCE_KIND_OFFICIAL,
        generated_at=generated_at,
    )

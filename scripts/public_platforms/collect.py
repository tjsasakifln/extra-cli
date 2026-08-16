"""Fixture-driven collector for public platform adapters.

Live HTTP is opt-in. Default path reads local fixtures so ZERO/BLOCKED
decisions stay deterministic.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from scripts.public_platforms.contract import (
    PLATFORMS,
    PageResult,
    RunResult,
    classify_http_block,
    pagination_terminal,
    sha256_bytes,
    sha256_json,
)

DEFAULT_FIXTURE_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "public_platforms"
SURFACES = ("listing", "detail", "documents", "status")


def default_fixture_path(source: str) -> Path:
    return DEFAULT_FIXTURE_DIR / f"{source}_pages.json"


def load_payload(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _page_from_mapping(source: str, raw: dict[str, Any], surface: str) -> PageResult:
    records = list(raw.get("records") or [])
    body = str(raw.get("body") or "")
    blob = json.dumps(raw, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return PageResult(
        page=int(raw.get("page") or 1),
        records=records,
        raw_uri=str(raw.get("raw_uri") or f"fixture://{source}/{surface}/{raw.get('page', 1)}"),
        raw_hash=str(raw.get("raw_hash") or sha256_bytes(blob)),
        content_hash=str(raw.get("content_hash") or sha256_json(records)),
        complete=bool(raw.get("complete", False)),
        surface=surface,
        status=int(raw.get("status") or 200),
        body=body,
    )


def collect_from_payload(source: str, payload: dict[str, Any]) -> RunResult:
    if source not in PLATFORMS:
        raise ValueError(f"unknown public platform: {source}")
    entity = payload.get("entity") or {}
    entity_key = str(entity.get("ibge") or entity.get("cnpj") or entity.get("name") or "")
    pages_out: list[PageResult] = []
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    id_field = str(PLATFORMS[source]["id_field"])
    blocked = False
    failed = False
    last_complete = True

    for surface in SURFACES:
        if surface == "listing":
            raw_pages = payload.get("listing") or payload.get("pages") or []
        else:
            raw_pages = payload.get(surface) or []
        for raw in raw_pages:
            if not isinstance(raw, dict):
                continue
            page = _page_from_mapping(source, raw, surface)
            reason = classify_http_block(status=page.status, body=page.body, headers=raw.get("headers") or {})
            pages_out.append(page)
            if reason == "BLOCKED":
                blocked = True
                continue
            if reason == "FAILED":
                failed = True
                continue
            if surface == "listing":
                last_complete = page.complete
            for record in page.records:
                key = str(record.get(id_field) or record.get("id") or sha256_json(record))
                if key in seen:
                    continue
                seen.add(key)
                enriched = dict(record)
                enriched.setdefault("source", source)
                enriched.setdefault("entity_key", entity_key)
                enriched.setdefault("surface", surface)
                records.append(enriched)

    # Dedicated blocked probe (login/CAPTCHA fixture without listing rows)
    probe = payload.get("blocked")
    if isinstance(probe, dict):
        reason = classify_http_block(
            status=probe.get("status"),
            body=str(probe.get("body") or ""),
            headers=probe.get("headers") or {},
        )
        if reason == "BLOCKED":
            blocked = True
        elif reason == "FAILED":
            failed = True

    fetched = sum(len(page.records) for page in pages_out)
    persisted = len(records)
    deduplicated = max(0, fetched - persisted)
    terminal = pagination_terminal(
        last_complete=last_complete and not blocked and not failed,
        record_count=persisted,
        blocked=blocked,
        failed=failed,
    )
    reason = None
    if terminal == "BLOCKED":
        reason = "login_captcha_or_forbidden"
    elif terminal == "ZERO":
        reason = "complete_scope_empty"
    elif terminal == "partial":
        reason = "pagination_incomplete"
    return RunResult(
        source=source,
        terminal=terminal,
        fetched=fetched,
        persisted=persisted,
        deduplicated=deduplicated,
        failed=1 if failed else 0,
        entity_key=entity_key or None,
        reason=reason,
        records=records,
        pages=pages_out,
    )


def collect_from_fixture(source: str, fixture: Path | None = None) -> RunResult:
    path = fixture or default_fixture_path(source)
    return collect_from_payload(source, load_payload(path))


def _blocked_observation(source: str, reason: str) -> dict[str, Any]:
    return {
        "source": source,
        "terminal": "BLOCKED",
        "reason": reason,
        "fetched": 0,
        "silent_zero": False,
    }


def transform_records(source: str, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    id_field = str(PLATFORMS[source]["id_field"])
    out: list[dict[str, Any]] = []
    for raw in records:
        if not isinstance(raw, dict):
            continue
        if raw.get("source") == source and raw.get("terminal"):
            out.append(raw)
            continue
        identity = raw.get(id_field) or raw.get("id") or raw.get("source_id")
        if not identity:
            continue
        if raw.get("source") == source and raw.get("source_id") == str(identity):
            out.append(raw)
            continue
        out.append(
            {
                "source": source,
                "source_id": str(identity),
                "entity_key": raw.get("entity_key"),
                "objeto": raw.get("objeto") or raw.get("object"),
                "status": raw.get("status") or raw.get("situacao"),
                "documents": list(raw.get("documents") or []),
                "raw_hash": raw.get("raw_hash"),
            }
        )
    return out


def crawl_source(source: str, mode: str = "incremental", fixture: str | None = None) -> list[dict[str, Any]]:
    del mode
    if os.environ.get("PUBLIC_PLATFORM_LIVE", "").strip() in {"1", "true", "yes"}:
        raise RuntimeError(f"{source}: live smoke is opt-in and must supply a transport; refusing bare live crawl")
    fixture_path = fixture or os.environ.get("PUBLIC_PLATFORM_FIXTURE")
    if not fixture_path:
        return [_blocked_observation(source, "missing_fixture_or_tenant_binding")]
    result = collect_from_fixture(source, Path(fixture_path))
    if result.terminal == "BLOCKED":
        return [_blocked_observation(source, result.reason or "login_captcha_or_forbidden")]
    return result.records

"""Bounded official-document acquisition. Never commits binaries."""

from __future__ import annotations

import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from scripts.historical_contract_authority.models import DocumentRecord, Locator
from scripts.historical_contract_authority.schema import (
    FETCH_RETRIES,
    FETCH_TIMEOUT_S,
    MAX_BYTES_PER_DOC,
    MAX_DOCS_PER_CONTRACT,
    MAX_REQUESTS,
    RATE_LIMIT_S,
    USER_AGENT,
    sha256_bytes,
    sha256_text,
)
from scripts.process_documents.inventory_pipeline import detect_mime, extract_text
from scripts.process_documents.inventory_pipeline import sha256_bytes as inventory_sha256


def locator_from(raw: dict[str, Any]) -> Locator:
    loc = raw.get("locator") or {}
    if isinstance(loc, str):
        return Locator(section=loc)
    return Locator(
        page=loc.get("page"),
        section=loc.get("section"),
        table=loc.get("table"),
        span=loc.get("span"),
    )


def document_from_mapping(raw: dict[str, Any]) -> DocumentRecord:
    text = str(raw.get("text") or "")
    binary = raw.get("binary")
    if isinstance(binary, str):
        payload = binary.encode("utf-8")
    elif isinstance(binary, (bytes, bytearray)):
        payload = bytes(binary)
    else:
        payload = text.encode("utf-8")
    binary_hash = str(raw.get("binary_sha256") or sha256_bytes(payload))
    text_hash = str(raw.get("text_sha256") or sha256_text(text))
    mime = str(raw.get("mime") or detect_mime(payload, raw.get("mime") or "text/plain"))
    return DocumentRecord(
        document_id=str(raw.get("document_id") or binary_hash[:16]),
        title=str(raw.get("title") or raw.get("document_id") or "untitled"),
        klass=str(raw.get("class") or raw.get("klass") or "unknown"),
        family=str(raw.get("family") or raw.get("class") or "unknown"),
        url=str(raw.get("url") or ""),
        locator=locator_from(raw),
        published_at=raw.get("published_at"),
        effective_at=raw.get("effective_at"),
        binary_sha256=binary_hash,
        text_sha256=text_hash,
        mime=mime,
        bytes_len=int(raw.get("bytes_len") or len(payload)),
        extract_status=str(raw.get("extract_status") or ("ok" if text else "empty")),
        relation=str(raw.get("relation") or "associated"),
        ocr_used=bool(raw.get("ocr_used")),
        ocr_tool=raw.get("ocr_tool"),
        ocr_confidence=float(raw["ocr_confidence"]) if raw.get("ocr_confidence") is not None else None,
        ocr_pages=tuple(raw.get("ocr_pages") or ()),
        superseded_by=raw.get("superseded_by"),
        http_status=raw.get("http_status"),
        redirect_chain=tuple(raw.get("redirect_chain") or ()),
        text=text,
    )


def extract_native(payload: bytes, mime: str, *, locator: str) -> tuple[str, bool]:
    extraction = extract_text(payload, mime, locator=locator)
    text = extraction.text or ""
    usable = len(text.strip()) >= 40 and not text.startswith("%PDF")
    return text, usable


def bounded_fetch(
    url: str,
    *,
    cache: dict[str, dict[str, Any]],
    budget: dict[str, Any],
) -> dict[str, Any]:
    if budget["requests"] >= MAX_REQUESTS:
        return {"ok": False, "reason": "request_budget_exceeded", "url": url}
    cached = cache.get(url)
    if cached:
        return {**cached, "cache_hit": True}
    last_error = "fetch_failed"
    for attempt in range(1, FETCH_RETRIES + 1):
        budget["requests"] += 1
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310
            with urlopen(request, timeout=FETCH_TIMEOUT_S) as response:  # noqa: S310
                status = int(getattr(response, "status", 200) or 200)
                data = response.read(MAX_BYTES_PER_DOC + 1)
                if len(data) > MAX_BYTES_PER_DOC:
                    record = {"ok": False, "reason": "too_large", "url": url, "http_status": status}
                    cache[url] = record
                    return record
                mime = detect_mime(
                    data, response.headers.get_content_type() if response.headers else "application/octet-stream"
                )
                text, usable = extract_native(data, mime, locator=url)
                record = {
                    "ok": True,
                    "url": url,
                    "http_status": status,
                    "mime": mime,
                    "bytes_len": len(data),
                    "binary_sha256": inventory_sha256(data),
                    "text": text if usable else "",
                    "extract_status": "ok" if usable else "no_native_text",
                    "ocr_used": False,
                    "redirect_chain": tuple(getattr(response, "url", url) for _ in (0,)),
                }
                cache[url] = record
                time.sleep(RATE_LIMIT_S)
                return record
        except HTTPError as exc:
            last_error = f"http_{exc.code}"
        except (URLError, TimeoutError, OSError) as exc:
            last_error = type(exc).__name__
        time.sleep(min(RATE_LIMIT_S * attempt, 3.0))
    record = {"ok": False, "reason": last_error, "url": url}
    cache[url] = record
    return record


def collect_documents(
    case: dict[str, Any], *, cache: dict[str, dict[str, Any]] | None = None, fetch: bool = False
) -> tuple[tuple[DocumentRecord, ...], list[dict[str, Any]]]:
    store = cache if cache is not None else {}
    budget = {"requests": 0}
    failed: list[dict[str, Any]] = []
    collected: list[DocumentRecord] = []
    raw_docs = list(case.get("documents") or [])
    fetched_count = 0
    for raw in raw_docs:
        needs_fetch = fetch and raw.get("url") and not raw.get("text") and not raw.get("binary_sha256")
        if needs_fetch:
            if fetched_count >= MAX_DOCS_PER_CONTRACT:
                failed.append({"ok": False, "reason": "doc_budget_exceeded", "url": raw.get("url")})
                continue
            fetched = bounded_fetch(str(raw["url"]), cache=store, budget=budget)
            fetched_count += 1
            if not fetched.get("ok"):
                failed.append(fetched)
                continue
            raw = {**raw, **fetched}
        collected.append(document_from_mapping(raw))
    return tuple(collected), failed

"""Canonical priority adapters: PNCP, public CIGA/DOM-SC and SC Compras."""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast

from scripts.crawl.ingestion._base.crawler import (
    CanonicalRecord,
    CrawlRequest,
    FetchResult,
    FetchStatus,
    SourceHealth,
)
from scripts.crawl.resilience.circuit_breaker import PersistentCircuitBreaker
from scripts.crawl.resilience.config import ResilienceConfig
from scripts.crawl.resilience.state import CanonicalCheckpoint, CheckpointStore, RawStore, RequestBudget
from scripts.crawl.run_evidence import get_git_meta, new_run_id


def _status_from_failure(result: FetchResult) -> FetchStatus:
    if result.status in {"rate_limited", "auth_blocked"}:
        return result.status
    return "partial" if result.records else "error"


def _snapshot_hash(payload: Any) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(canonical).hexdigest()


class _AdapterBase:
    source_id = "unknown"
    supports_pagination = True
    supports_empty_confirmed = False
    adapter_version = "adr-021-v2"

    def __init__(self, config: ResilienceConfig | None = None):
        self.config = config or ResilienceConfig.from_env()
        self.checkpoints = CheckpointStore(self.config.checkpoint_path)
        self.raw = RawStore(self.config.raw_path)
        self.budget = RequestBudget(
            self.config.ops_path / "budgets" / f"{self.source_id}.json",
            self.config.daily_request_budget,
        )
        self.breaker = PersistentCircuitBreaker(
            self.config.breaker_path,
            environment=self.config.environment,
            source=self.source_id,
            route="default",
            threshold=self.config.circuit_breaker_threshold,
            cooldown_seconds=self.config.circuit_breaker_cooldown,
        )

    def health(self) -> SourceHealth:
        pending = self.checkpoints.pending(self.source_id)
        br = self.breaker.snapshot()
        return SourceHealth(
            source=self.source_id,
            status="degraded" if pending or br.get("state") == "open" else "healthy",
            message=f"{len(pending)} checkpoint(s) pendente(s); breaker={br.get('state')}",
            metadata={
                "supports_pagination": self.supports_pagination,
                "supports_empty_confirmed": self.supports_empty_confirmed,
                "adapter_version": self.adapter_version,
                "environment": self.config.environment,
                "circuit_breaker": br,
            },
        )

    def _provenance(self, request: CrawlRequest, run_id: str) -> dict[str, Any]:
        return {
            "source": self.source_id,
            "run_id": run_id,
            "environment": self.config.environment,
            "execution_mode": self.config.execution_mode,
            "request_params": {
                "mode": request.mode,
                "target": request.target,
                "date_from": request.date_from.isoformat() if request.date_from else None,
                "date_to": request.date_to.isoformat() if request.date_to else None,
                "limit": request.limit,
            },
            "fetched_at": datetime.now(UTC).isoformat(),
            "adapter_version": self.adapter_version,
            **get_git_meta(),
        }


class PNCPAdapter(_AdapterBase):
    source_id = "pncp"
    supports_empty_confirmed = True

    def __init__(self, config: ResilienceConfig | None = None, page_fetcher: Callable[..., FetchResult] | None = None):
        super().__init__(config)
        from scripts.crawl import pncp_crawler_adapter as legacy

        self.legacy = legacy
        # Inject HTTP policy at call time when using real fetcher.
        if page_fetcher is not None:
            self.page_fetcher = page_fetcher
        else:
            policy = self.config.http_policy

            def _bound_fetch(request: CrawlRequest, modalidade: int, page: int) -> FetchResult:
                result = legacy._fetch_publication_page(request, modalidade, page, http_policy=policy)
                return cast(FetchResult, result)

            self.page_fetcher = _bound_fetch

    def fetch(self, request: CrawlRequest) -> FetchResult:
        run_id = request.run_id or new_run_id("pncp")
        start = request.date_from or date.today()
        end = request.date_to or start
        records: list[dict[str, Any]] = []
        statuses: list[int] = []
        errors: list[str] = []
        warnings: list[str] = []
        raw_refs: list[dict[str, str]] = []
        page_scopes: list[str] = []
        pages_complete = pages_expected = pages_reused = 0
        terminal_status: FetchStatus = "success"

        for window_start, window_end in self.legacy._windowed_dates(start, end):
            for modalidade in self.legacy.INGESTION_MODALIDADES or self.legacy.DEFAULT_MODALIDADES:
                page = 1
                modality_expected: int | None = None
                while page <= self.config.max_pages:
                    scope = f"window={window_start}:{window_end}|modalidade={modalidade}|page={page}"
                    page_scopes.append(scope)
                    prior = self.checkpoints.load(self.source_id, scope)
                    if prior and prior.pages_expected is not None and modality_expected is None:
                        modality_expected = max(0, int(prior.pages_expected))
                    # Reuse any stage that already has immutable raw — never re-HTTP.
                    _reuse_statuses = {
                        "raw_persisted",
                        "normalized",
                        "db_committed",
                        "evidence_committed",
                        "watermark_committed",
                        "success",
                        "empty_confirmed",
                    }
                    if prior and prior.status in _reuse_statuses and prior.raw_reference and Path(prior.raw_reference).is_file():
                        raw_doc = json.loads(Path(prior.raw_reference).read_text(encoding="utf-8"))
                        page_records = raw_doc.get("payload", {}).get("data", [])
                        records.extend(page_records)
                        raw_refs.append(
                            {
                                "path": str(prior.raw_reference),
                                "content_hash": prior.content_hash or "",
                                "request_scope": scope,
                            }
                        )
                        pages_complete += 1
                        pages_reused += 1
                        page += 1
                        if modality_expected is not None and page > modality_expected:
                            break
                        continue
                    if prior and prior.completed:
                        pages_complete += 1
                        pages_reused += 1
                        page += 1
                        if modality_expected is not None and page > modality_expected:
                            break
                        continue
                    if not self.breaker.allow_request():
                        terminal_status = "rate_limited"
                        errors.append("circuit_breaker_open")
                        break
                    if not self.budget.consume():
                        terminal_status = "rate_limited"
                        errors.append("daily_request_budget_exhausted")
                        break

                    page_request = CrawlRequest(
                        mode=request.mode,
                        date_from=window_start,
                        date_to=window_end,
                        target=request.target,
                        limit=request.limit,
                        source=self.source_id,
                        request_scope=scope,
                        page=page,
                        run_id=run_id,
                    )
                    fetched = self.page_fetcher(page_request, modalidade, page)
                    statuses.extend(fetched.http_statuses)
                    pagination = fetched.metadata.get("pagination") or {}
                    total_pages = pagination.get("totalPaginas")
                    if isinstance(total_pages, int):
                        modality_expected = max(0, total_pages)
                    cp = CanonicalCheckpoint(
                        source=self.source_id,
                        run_id=run_id,
                        request_scope=scope,
                        target=request.target,
                        date_from=window_start.isoformat(),
                        date_to=window_end.isoformat(),
                        window=f"{window_start}:{window_end}",
                        page=page,
                        status=fetched.status or "error",
                        attempt_count=int(fetched.metadata.get("retries", 0)) + 1,
                        last_http_status=fetched.http_status,
                        last_error="; ".join(fetched.errors) or None,
                        pages_fetched=1 if fetched.request_completed else 0,
                        pages_expected=modality_expected,
                        environment=self.config.environment,
                        execution_mode=self.config.execution_mode,
                    )
                    if fetched.status not in {"success", "empty_confirmed"}:
                        self.breaker.record_failure(http_status=fetched.http_status, error=str(fetched.status))
                        # Failure terminals: keep pending-compatible status for resume.
                        if fetched.status in {"rate_limited", "auth_blocked", "error", "partial"}:
                            cp.status = fetched.status
                        self.checkpoints.save(cp)
                        errors.extend(fetched.errors or [str(fetched.status)])
                        terminal_status = _status_from_failure(fetched)
                        break

                    self.breaker.record_success()
                    payload = {"data": fetched.records, "pagination": pagination}
                    provenance = self._provenance(page_request, run_id)
                    provenance.update(
                        {
                            "endpoint": fetched.metadata.get("url"),
                            "page": page,
                            "http_status": fetched.http_status,
                            "response_headers": fetched.metadata.get("response_headers", {}),
                        }
                    )
                    raw_path, digest = self.raw.persist(
                        source=self.source_id,
                        run_id=run_id,
                        request_scope=scope,
                        payload=payload,
                        provenance=provenance,
                    )
                    cp.status = "raw_persisted"
                    cp.content_hash = digest
                    cp.raw_reference = str(raw_path)
                    self.checkpoints.save(cp)
                    raw_refs.append({"path": str(raw_path), "content_hash": digest, "request_scope": scope})
                    records.extend(fetched.records)
                    pages_complete += 1
                    if (
                        fetched.empty_confirmed
                        or not isinstance(pagination.get("paginasRestantes"), int)
                        or pagination["paginasRestantes"] <= 0
                    ):
                        break
                    page += 1
                    if request.limit and len(records) >= request.limit:
                        records = records[: request.limit]
                        warnings.append("request_limit_applied_no_completeness_claim")
                        terminal_status = "partial"
                        break
                    time.sleep(self.config.request_delay)
                if modality_expected is None:
                    if terminal_status == "success" and pages_complete > 0:
                        pages_expected += pages_complete
                    elif terminal_status != "success":
                        pages_expected += pages_complete + 1
                else:
                    pages_expected += modality_expected
                if terminal_status != "success":
                    break
            if terminal_status != "success":
                break

        if terminal_status == "success" and pages_expected > 0 and pages_complete < pages_expected:
            terminal_status = "partial"
        if terminal_status == "success" and pages_complete > 0 and pages_expected == 0:
            pages_expected = pages_complete
        empty = terminal_status == "success" and not records and pages_complete >= max(pages_expected, 1)
        status: FetchStatus = "empty_confirmed" if empty else terminal_status
        provenance = self._provenance(request, run_id)
        provenance.update(
            {
                "endpoint": f"{self.legacy.PNCP_CONSULTA_BASE}/contratacoes/publicacao",
                "raw": raw_refs,
                "http_statuses": statuses,
            }
        )
        # Canonical checkpoint schema for orchestrator (not ad-hoc page_scopes only).
        run_scope = request.request_scope or f"window={start}:{end}"
        checkpoint_payload = {
            "source": self.source_id,
            "run_id": run_id,
            "request_scope": run_scope,
            "status": "raw_persisted" if raw_refs else (status if status not in {"success", "empty_confirmed"} else "pending"),
            "pages_fetched": pages_complete,
            "pages_expected": pages_expected,
            "environment": self.config.environment,
            "execution_mode": self.config.execution_mode,
        }
        return FetchResult(
            status=status,
            records=records,
            request_completed=status in {"success", "empty_confirmed"},
            http_status=statuses[-1] if statuses else None,
            http_statuses=statuses,
            empty_confirmed=empty,
            pages_fetched=pages_complete,
            pages_expected=pages_expected,
            resume_token=page_scopes[-1] if page_scopes else None,
            checkpoint=checkpoint_payload,
            errors=errors,
            warnings=warnings,
            provenance=provenance,
            metadata={"run_id": run_id, "raw": raw_refs, "pages_reused": pages_reused, "page_scopes": page_scopes},
        )

    def normalize(self, raw: list[dict[str, Any]]) -> list[CanonicalRecord]:
        return cast(list[CanonicalRecord], self.legacy.transform(raw))


class CigaDomAdapter(_AdapterBase):
    """Explicit bridge over the existing raw-first CIGA publication collector."""

    source_id = "ciga_dom"
    supports_empty_confirmed = False

    def __init__(self, config: ResilienceConfig | None = None, runner: Callable[..., dict[str, Any]] | None = None):
        super().__init__(config)
        from scripts.crawl import ciga_dom_publications as legacy

        self.legacy = legacy
        self.runner = runner or legacy.run_ingestion

    def fetch(self, request: CrawlRequest) -> FetchResult:
        run_id = request.run_id or new_run_id("ciga-dom")
        scope = request.request_scope or f"mode={request.mode}|target={request.target or 'latest'}"
        artifact = self.runner(
            mode=request.mode if request.mode in {"smoke", "incremental", "full"} else "incremental",
            package_id=request.target,
            max_zips=request.limit,
            request_delay=self.config.request_delay,
        )
        path = Path(artifact.get("jsonl_path", ""))
        records: list[dict[str, Any]] = []
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    records.append(json.loads(line))
        legacy_status = artifact.get("status")
        counts = artifact.get("counts") or {}
        expected = int(counts.get("selected", 0))
        fetched = int(counts.get("resources_processed_ok", 0)) + int(counts.get("resources_skipped_checkpoint", 0))
        status: FetchStatus = "success" if legacy_status == "success" and expected > 0 and fetched >= expected else "partial"
        if legacy_status == "failed":
            status = "error"
        if not records and status == "success":
            status = "partial"
        provenance = self._provenance(request, artifact.get("run_id") or run_id)
        provenance.update(
            {
                "endpoint": self.legacy.CKAN_API,
                "legacy_evidence": artifact.get("evidence_path"),
                "raw_output": str(path) if path else None,
            }
        )
        # NEVER mark success here — only raw_persisted / failure terminals.
        adapter_status = "raw_persisted" if status in {"success", "partial"} and path.is_file() else (
            status if status in {"error", "rate_limited", "auth_blocked", "partial"} else "pending"
        )
        if status == "success" and path.is_file():
            adapter_status = "raw_persisted"
        cp = CanonicalCheckpoint(
            source=self.source_id,
            run_id=artifact.get("run_id") or run_id,
            request_scope=scope,
            target=request.target,
            status=adapter_status,
            attempt_count=1,
            last_error="; ".join(artifact.get("errors") or []) or None,
            pages_fetched=fetched,
            pages_expected=expected,
            raw_reference=str(path) if path else None,
            environment=self.config.environment,
            execution_mode=self.config.execution_mode,
        )
        self.checkpoints.save(cp)
        return FetchResult(
            status=status,
            records=records,
            request_completed=status == "success",
            http_status=200 if legacy_status != "failed" else None,
            empty_confirmed=False,
            pages_fetched=fetched,
            pages_expected=expected,
            resume_token=scope,
            checkpoint=asdict(cp),
            errors=list(artifact.get("errors") or []),
            provenance=provenance,
            metadata={"run_id": cp.run_id, "legacy_bridge": True, "raw": [{"path": str(path), "request_scope": scope}] if path else []},
        )

    def normalize(self, raw: list[dict[str, Any]]) -> list[CanonicalRecord]:
        return [dict(record) for record in raw]


class ScComprasAdapter(_AdapterBase):
    """SC Compras uses bulk snapshot + internal chunks bound by snapshot_hash."""

    source_id = "sc_compras"
    supports_empty_confirmed = False

    def __init__(
        self,
        config: ResilienceConfig | None = None,
        list_fetcher: Callable[[int], tuple[list[dict[str, Any]], dict[str, Any]]] | None = None,
    ):
        super().__init__(config)
        from scripts.crawl import sc_compras_crawler as legacy

        self.legacy = legacy
        self.list_fetcher = list_fetcher or legacy._fetch_api_list_meta

    def fetch(self, request: CrawlRequest) -> FetchResult:
        run_id = request.run_id or new_run_id("sc-compras")
        year = (request.date_to or date.today()).year
        snapshot_scope = f"year={year}|snapshot"
        prior_snapshot = self.checkpoints.load(self.source_id, snapshot_scope)

        items: list[dict[str, Any]]
        meta: dict[str, Any]
        snapshot_hash: str
        raw_snapshot_path: str | None = None

        # Resume from immutable bulk snapshot without new HTTP when present.
        if (
            prior_snapshot
            and prior_snapshot.status in {"raw_persisted", "normalized", "db_committed", "success", "partial"}
            and prior_snapshot.raw_reference
            and prior_snapshot.snapshot_hash
            and Path(prior_snapshot.raw_reference).is_file()
        ):
            raw_doc = json.loads(Path(prior_snapshot.raw_reference).read_text(encoding="utf-8"))
            payload = raw_doc.get("payload") or {}
            items = list(payload.get("items") or [])
            meta = dict(payload.get("meta") or {})
            snapshot_hash = prior_snapshot.snapshot_hash
            raw_snapshot_path = prior_snapshot.raw_reference
            meta["resumed_snapshot"] = True
        else:
            if not self.breaker.allow_request():
                return FetchResult(
                    status="rate_limited",
                    request_completed=False,
                    errors=["circuit_breaker_open"],
                    provenance=self._provenance(request, run_id),
                    metadata={"run_id": run_id},
                )
            if not self.budget.consume():
                return FetchResult(
                    status="rate_limited",
                    request_completed=False,
                    errors=["daily_request_budget_exhausted"],
                    provenance=self._provenance(request, run_id),
                    metadata={"run_id": run_id},
                )
            items, meta = self.list_fetcher(year)
            if not meta.get("ok", True) and not items:
                status: FetchStatus = (
                    "rate_limited"
                    if meta.get("http_status") == 429
                    else ("auth_blocked" if meta.get("http_status") in {401, 403} else "error")
                )
                self.breaker.record_failure(http_status=meta.get("http_status"), error=str(meta.get("error")))
                return FetchResult(
                    status=status,
                    request_completed=False,
                    http_status=meta.get("http_status"),
                    empty_confirmed=False,
                    errors=[str(meta.get("error") or "list_fetch_failed")],
                    provenance=self._provenance(request, run_id),
                    metadata={"run_id": run_id},
                )
            self.breaker.record_success()
            snapshot_hash = _snapshot_hash({"items": items, "total": meta.get("total_elementos"), "year": year})
            # If a different snapshot exists, invalidate incompatible chunk resume.
            if prior_snapshot and prior_snapshot.snapshot_hash and prior_snapshot.snapshot_hash != snapshot_hash:
                meta = dict(meta)
                meta["snapshot_invalidated"] = True
                meta["previous_snapshot_hash"] = prior_snapshot.snapshot_hash
            snapshot_payload = {
                "items": items,
                "meta": meta,
                "year": year,
                "total_informed": meta.get("total_elementos"),
                "total_received": len(items),
                "snapshot_hash": snapshot_hash,
            }
            provenance = self._provenance(request, run_id)
            provenance.update({"endpoint": meta.get("url") or self.legacy.BASE_URL, "http_status": 200, "snapshot": True})
            raw_path, digest = self.raw.persist(
                source=self.source_id,
                run_id=run_id,
                request_scope=snapshot_scope,
                payload=snapshot_payload,
                provenance=provenance,
            )
            raw_snapshot_path = str(raw_path)
            self.checkpoints.save(
                CanonicalCheckpoint(
                    source=self.source_id,
                    run_id=run_id,
                    request_scope=snapshot_scope,
                    target=request.target,
                    date_from=request.date_from.isoformat() if request.date_from else None,
                    date_to=request.date_to.isoformat() if request.date_to else None,
                    window=str(year),
                    status="raw_persisted",
                    attempt_count=1,
                    last_http_status=200,
                    content_hash=digest,
                    raw_reference=str(raw_path),
                    snapshot_hash=snapshot_hash,
                    pages_fetched=0,
                    pages_expected=None,
                    scope_level="snapshot",
                    environment=self.config.environment,
                    execution_mode=self.config.execution_mode,
                )
            )

        total = meta.get("total_elementos")
        bulk_count = len(items)
        # Process internal chunks bound to the same snapshot_hash (not remote pages).
        chunk_size = self.config.page_size
        chunks_expected = math.ceil(bulk_count / chunk_size) if bulk_count > 0 else 0
        max_chunks = min(request.limit or self.config.max_pages, self.config.max_pages)
        chunks_to_process = min(chunks_expected, max_chunks) if chunks_expected else 0
        records: list[dict[str, Any]] = []
        raw_refs: list[dict[str, str]] = []
        warnings: list[str] = []
        chunks_complete = 0

        for index in range(chunks_to_process):
            scope = f"year={year}|snapshot={snapshot_hash[:12]}|chunk={index + 1}"
            cp = self.checkpoints.load(self.source_id, scope)
            if cp and cp.snapshot_hash and cp.snapshot_hash != snapshot_hash:
                warnings.append(f"incompatible_snapshot_chunk_{index + 1}")
                # Invalidate: do not mix chunks across snapshots.
                return FetchResult(
                    status="partial",
                    records=[],
                    request_completed=False,
                    errors=["snapshot_hash_mismatch_resume_incompatible"],
                    warnings=warnings,
                    provenance=self._provenance(request, run_id),
                    metadata={"run_id": run_id, "snapshot_hash": snapshot_hash},
                )
            if cp and (cp.completed or (cp.status == "raw_persisted" and cp.raw_reference)):
                if cp.raw_reference and Path(cp.raw_reference).is_file():
                    raw_doc = json.loads(Path(cp.raw_reference).read_text(encoding="utf-8"))
                    payload = raw_doc.get("payload", {})
                    chunk_items = payload.get("items") if isinstance(payload, dict) else payload
                    if isinstance(chunk_items, list) and chunk_items:
                        records.extend(chunk_items)
                        raw_refs.append(
                            {
                                "path": str(cp.raw_reference),
                                "content_hash": cp.content_hash or "",
                                "request_scope": scope,
                            }
                        )
                        chunks_complete += 1
                    else:
                        warnings.append(f"empty_checkpoint_chunk_{index + 1}")
                        break
                continue

            chunk_items = items[index * chunk_size : (index + 1) * chunk_size]
            if not chunk_items:
                warnings.append(f"empty_chunk_{index + 1}_bulk_count_{bulk_count}_total_{total}")
                break
            chunk_payload = {
                "items": chunk_items,
                "snapshot_hash": snapshot_hash,
                "chunk": index + 1,
                "year": year,
            }
            provenance = self._provenance(request, run_id)
            provenance.update(
                {
                    "endpoint": meta.get("url") or self.legacy.BASE_URL,
                    "chunk": index + 1,
                    "snapshot_hash": snapshot_hash,
                    "http_status": 200,
                }
            )
            raw_path, digest = self.raw.persist(
                source=self.source_id,
                run_id=run_id,
                request_scope=scope,
                payload=chunk_payload,
                provenance=provenance,
            )
            raw_refs.append({"path": str(raw_path), "content_hash": digest, "request_scope": scope})
            records.extend(chunk_items)
            chunks_complete += 1
            self.checkpoints.save(
                CanonicalCheckpoint(
                    source=self.source_id,
                    run_id=run_id,
                    request_scope=scope,
                    target=request.target,
                    date_from=request.date_from.isoformat() if request.date_from else None,
                    date_to=request.date_to.isoformat() if request.date_to else None,
                    window=str(year),
                    page=index + 1,
                    status="raw_persisted",
                    attempt_count=1,
                    last_http_status=200,
                    content_hash=digest,
                    raw_reference=str(raw_path),
                    snapshot_hash=snapshot_hash,
                    pages_fetched=1,
                    pages_expected=chunks_expected,
                    environment=self.config.environment,
                    execution_mode=self.config.execution_mode,
                )
            )

        records_match_total = (
            isinstance(total, int) and total > 0 and len(records) >= total and bulk_count >= total
        )
        chunks_complete_ok = chunks_expected > 0 and chunks_complete >= chunks_expected
        if chunks_expected > max_chunks:
            warnings.append("chunk_limit_prevents_completeness")
        if isinstance(total, int) and total > 0 and len(records) < total:
            warnings.append(f"records_lt_reported_total:{len(records)}<{total}")
        if bulk_count > 0 and isinstance(total, int) and total > bulk_count:
            warnings.append(f"bulk_incomplete_received_{bulk_count}_of_{total}")

        if records_match_total and chunks_complete_ok and records:
            status = "success"
        else:
            status = "partial"

        provenance = self._provenance(request, run_id)
        provenance.update(
            {
                "endpoint": meta.get("url") or self.legacy.BASE_URL,
                "raw": raw_refs,
                "reported_total": total,
                "bulk_count": bulk_count,
                "snapshot_hash": snapshot_hash,
                "total_informed": total,
                "total_received": bulk_count,
                "raw_snapshot": raw_snapshot_path,
            }
        )
        checkpoint_payload = {
            "source": self.source_id,
            "run_id": run_id,
            "request_scope": snapshot_scope,
            "status": "raw_persisted",
            "snapshot_hash": snapshot_hash,
            "raw_reference": raw_snapshot_path,
            "scope_level": "snapshot",
            "pages_fetched": chunks_complete,
            "pages_expected": chunks_expected,
            "environment": self.config.environment,
            "execution_mode": self.config.execution_mode,
        }
        return FetchResult(
            status=status,
            records=records,
            request_completed=status == "success",
            http_status=200,
            http_statuses=[200],
            empty_confirmed=False,
            pages_fetched=chunks_complete,
            pages_expected=chunks_expected if chunks_expected else (1 if isinstance(total, int) and total > 0 else 0),
            resume_token=f"year={year}|chunk={chunks_complete + 1}",
            checkpoint=checkpoint_payload,
            warnings=warnings,
            provenance=provenance,
            metadata={
                "run_id": run_id,
                "raw": raw_refs,
                "bulk_count": bulk_count,
                "snapshot_hash": snapshot_hash,
                "total_informed": total,
                "total_received": bulk_count,
            },
        )

    def normalize(self, raw: list[dict[str, Any]]) -> list[CanonicalRecord]:
        canonical = [self.legacy._api_item_to_canonical(item) for item in raw]
        return cast(list[CanonicalRecord], self.legacy.transform(canonical))


PRIORITY_ADAPTERS = {
    "pncp": PNCPAdapter,
    "ciga_dom": CigaDomAdapter,
    "ciga_ckan": CigaDomAdapter,
    "sc_compras": ScComprasAdapter,
}

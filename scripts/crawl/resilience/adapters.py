"""Canonical priority adapters: PNCP, public CIGA/DOM-SC and SC Compras."""

from __future__ import annotations

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
from scripts.crawl.run_evidence import get_git_meta, new_run_id

from .config import ResilienceConfig
from .state import CanonicalCheckpoint, CheckpointStore, RawStore, RequestBudget


def _status_from_failure(result: FetchResult) -> FetchStatus:
    if result.status in {"rate_limited", "auth_blocked"}:
        return result.status
    return "partial" if result.records else "error"


class _AdapterBase:
    source_id = "unknown"
    supports_pagination = True
    supports_empty_confirmed = False
    adapter_version = "adr-021-v1"

    def __init__(self, config: ResilienceConfig | None = None):
        self.config = config or ResilienceConfig.from_env()
        self.checkpoints = CheckpointStore(self.config.checkpoint_path)
        self.raw = RawStore(self.config.raw_path)
        self.budget = RequestBudget(
            self.config.ops_path / "budgets" / f"{self.source_id}.json",
            self.config.daily_request_budget,
        )

    def health(self) -> SourceHealth:
        pending = self.checkpoints.pending(self.source_id)
        return SourceHealth(
            source=self.source_id,
            status="degraded" if pending else "healthy",
            message=f"{len(pending)} checkpoint(s) pendente(s)" if pending else "sem checkpoint pendente",
            metadata={
                "supports_pagination": self.supports_pagination,
                "supports_empty_confirmed": self.supports_empty_confirmed,
                "adapter_version": self.adapter_version,
            },
        )

    def _provenance(self, request: CrawlRequest, run_id: str) -> dict[str, Any]:
        return {
            "source": self.source_id,
            "run_id": run_id,
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
        self.page_fetcher = page_fetcher or legacy._fetch_publication_page
        self._consecutive_failures = 0
        self._circuit_opened_at: float | None = None

    def _circuit_open(self) -> bool:
        if self._consecutive_failures < self.config.circuit_breaker_threshold:
            return False
        if self._circuit_opened_at is None:
            self._circuit_opened_at = time.monotonic()
        if time.monotonic() - self._circuit_opened_at >= self.config.circuit_breaker_cooldown:
            self._consecutive_failures = 0
            self._circuit_opened_at = None
            return False
        return True

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
                    if prior and prior.completed:
                        if prior.raw_reference and Path(prior.raw_reference).is_file():
                            raw_doc = json.loads(Path(prior.raw_reference).read_text(encoding="utf-8"))
                            records.extend(raw_doc.get("payload", {}).get("data", []))
                        pages_complete += 1
                        pages_reused += 1
                        page += 1
                        if modality_expected is not None and page > modality_expected:
                            break
                        continue
                    if prior and prior.status == "raw_persisted" and prior.raw_reference:
                        raw_doc = json.loads(Path(prior.raw_reference).read_text(encoding="utf-8"))
                        page_records = raw_doc.get("payload", {}).get("data", [])
                        records.extend(page_records)
                        pages_complete += 1
                        pages_reused += 1
                        page += 1
                        if modality_expected is not None and page > modality_expected:
                            break
                        continue
                    if self._circuit_open():
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
                    )
                    if fetched.status not in {"success", "empty_confirmed"}:
                        self._consecutive_failures += 1
                        if fetched.status == "rate_limited":
                            self._circuit_opened_at = self._circuit_opened_at or time.monotonic()
                        self.checkpoints.save(cp)
                        errors.extend(fetched.errors or [str(fetched.status)])
                        terminal_status = _status_from_failure(fetched)
                        break

                    self._consecutive_failures = 0
                    payload = {"data": fetched.records, "pagination": pagination}
                    provenance = self._provenance(page_request, run_id)
                    provenance.update({"endpoint": fetched.metadata.get("url"), "page": page, "http_status": fetched.http_status, "response_headers": fetched.metadata.get("response_headers", {})})
                    raw_path, digest = self.raw.persist(source=self.source_id, run_id=run_id, request_scope=scope, payload=payload, provenance=provenance)
                    cp.status = "raw_persisted"
                    cp.content_hash = digest
                    cp.raw_reference = str(raw_path)
                    self.checkpoints.save(cp)
                    raw_refs.append({"path": str(raw_path), "content_hash": digest, "request_scope": scope})
                    records.extend(fetched.records)
                    pages_complete += 1
                    if fetched.empty_confirmed or not isinstance(pagination.get("paginasRestantes"), int) or pagination["paginasRestantes"] <= 0:
                        break
                    page += 1
                    if request.limit and len(records) >= request.limit:
                        records = records[: request.limit]
                        warnings.append("request_limit_applied_no_completeness_claim")
                        terminal_status = "partial"
                        break
                    time.sleep(self.config.request_delay)
                if modality_expected is None:
                    # Resume-only path without pagination metadata still needs a
                    # conservative expected count so pages_expected is never zero
                    # while pages_fetched > 0 after a successful slice.
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
            # Prefer explicit pagination; fall back only when the source never
            # reported totals (resume of already-persisted slices).
            pages_expected = pages_complete
        empty = terminal_status == "success" and not records and pages_complete >= max(pages_expected, 1)
        status: FetchStatus = "empty_confirmed" if empty else terminal_status
        provenance = self._provenance(request, run_id)
        provenance.update({"endpoint": f"{self.legacy.PNCP_CONSULTA_BASE}/contratacoes/publicacao", "raw": raw_refs, "http_statuses": statuses})
        return FetchResult(
            status=status, records=records, request_completed=status in {"success", "empty_confirmed"},
            http_status=statuses[-1] if statuses else None, http_statuses=statuses,
            empty_confirmed=empty, pages_fetched=pages_complete, pages_expected=pages_expected,
            resume_token=page_scopes[-1] if page_scopes else None,
            checkpoint={"page_scopes": page_scopes, "pages_reused": pages_reused},
            errors=errors, warnings=warnings, provenance=provenance,
            metadata={"run_id": run_id, "raw": raw_refs, "pages_reused": pages_reused},
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
        artifact = self.runner(mode=request.mode if request.mode in {"smoke", "incremental", "full"} else "incremental", package_id=request.target, max_zips=request.limit, request_delay=self.config.request_delay)
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
        # CIGA cannot prove a zero publication result for a target entity.
        if not records and status == "success":
            status = "partial"
        provenance = self._provenance(request, artifact.get("run_id") or run_id)
        provenance.update({"endpoint": self.legacy.CKAN_API, "legacy_evidence": artifact.get("evidence_path"), "raw_output": str(path) if path else None})
        cp = CanonicalCheckpoint(source=self.source_id, run_id=artifact.get("run_id") or run_id, request_scope=scope, target=request.target, status=status, attempt_count=1, last_error="; ".join(artifact.get("errors") or []) or None, pages_fetched=fetched, pages_expected=expected, raw_reference=str(path) if path else None)
        self.checkpoints.save(cp)
        return FetchResult(status=status, records=records, request_completed=status == "success", http_status=200 if legacy_status != "failed" else None, empty_confirmed=False, pages_fetched=fetched, pages_expected=expected, resume_token=scope, checkpoint=asdict(cp), errors=list(artifact.get("errors") or []), provenance=provenance, metadata={"run_id": cp.run_id, "legacy_bridge": True})

    def normalize(self, raw: list[dict[str, Any]]) -> list[CanonicalRecord]:
        # Existing collector already parses archive members after persisting raw.
        # This bridge is pure and performs no network I/O.
        return [dict(record) for record in raw]


class ScComprasAdapter(_AdapterBase):
    source_id = "sc_compras"
    supports_empty_confirmed = False

    def __init__(self, config: ResilienceConfig | None = None, list_fetcher: Callable[[int], tuple[list[dict[str, Any]], dict[str, Any]]] | None = None):
        super().__init__(config)
        from scripts.crawl import sc_compras_crawler as legacy

        self.legacy = legacy
        self.list_fetcher = list_fetcher or legacy._fetch_api_list_meta

    def fetch(self, request: CrawlRequest) -> FetchResult:
        run_id = request.run_id or new_run_id("sc-compras")
        year = (request.date_to or date.today()).year
        items, meta = self.list_fetcher(year)
        total = meta.get("total_elementos")
        if not meta.get("ok", True) and not items:
            status: FetchStatus = "rate_limited" if meta.get("http_status") == 429 else ("auth_blocked" if meta.get("http_status") in {401, 403} else "error")
            return FetchResult(status=status, request_completed=False, http_status=meta.get("http_status"), empty_confirmed=False, errors=[str(meta.get("error") or "list_fetch_failed")], provenance=self._provenance(request, run_id), metadata={"run_id": run_id})
        pages_expected = math.ceil(total / self.config.page_size) if isinstance(total, int) and total else 0
        max_pages = min(request.limit or self.config.max_pages, self.config.max_pages)
        pages_to_process = min(pages_expected, max_pages) if pages_expected else 0
        records: list[dict[str, Any]] = []
        raw_refs: list[dict[str, str]] = []
        pages_complete = 0
        for index in range(pages_to_process):
            scope = f"year={year}|page={index + 1}"
            cp = self.checkpoints.load(self.source_id, scope)
            # success/empty_confirmed or raw already persisted: do not re-fetch.
            if cp and (cp.completed or (cp.status == "raw_persisted" and cp.raw_reference)):
                if cp.raw_reference and Path(cp.raw_reference).is_file():
                    raw_doc = json.loads(Path(cp.raw_reference).read_text(encoding="utf-8"))
                    payload = raw_doc.get("payload", [])
                    if isinstance(payload, list):
                        records.extend(payload)
                        raw_refs.append(
                            {
                                "path": str(cp.raw_reference),
                                "content_hash": cp.content_hash or "",
                                "request_scope": scope,
                            }
                        )
                pages_complete += 1
                continue
            page_items = items[index * self.config.page_size : (index + 1) * self.config.page_size]
            provenance = self._provenance(request, run_id)
            provenance.update({"endpoint": meta.get("url") or self.legacy.BASE_URL, "page": index + 1, "http_status": 200})
            raw_path, digest = self.raw.persist(source=self.source_id, run_id=run_id, request_scope=scope, payload=page_items, provenance=provenance)
            raw_refs.append({"path": str(raw_path), "content_hash": digest, "request_scope": scope})
            records.extend(page_items)
            pages_complete += 1
            self.checkpoints.save(CanonicalCheckpoint(source=self.source_id, run_id=run_id, request_scope=scope, target=request.target, date_from=request.date_from.isoformat() if request.date_from else None, date_to=request.date_to.isoformat() if request.date_to else None, window=str(year), page=index + 1, status="raw_persisted", attempt_count=1, last_http_status=200, content_hash=digest, raw_reference=str(raw_path), pages_fetched=1, pages_expected=pages_expected))
        status = "success" if pages_expected > 0 and pages_complete >= pages_expected else "partial"
        # Public endpoint does not provide a target-scoped zero proof.
        if not records and status == "success":
            status = "partial"
        provenance = self._provenance(request, run_id)
        provenance.update({"endpoint": meta.get("url") or self.legacy.BASE_URL, "raw": raw_refs, "reported_total": total})
        return FetchResult(status=status, records=records, request_completed=status == "success", http_status=200, http_statuses=[200], empty_confirmed=False, pages_fetched=pages_complete, pages_expected=pages_expected, resume_token=f"year={year}|page={pages_complete + 1}", checkpoint={"year": year}, warnings=["page_limit_prevents_completeness"] if status == "partial" and pages_expected > max_pages else [], provenance=provenance, metadata={"run_id": run_id, "raw": raw_refs})

    def normalize(self, raw: list[dict[str, Any]]) -> list[CanonicalRecord]:
        canonical = [self.legacy._api_item_to_canonical(item) for item in raw]
        return cast(list[CanonicalRecord], self.legacy.transform(canonical))


PRIORITY_ADAPTERS = {
    "pncp": PNCPAdapter,
    "ciga_dom": CigaDomAdapter,
    "ciga_ckan": CigaDomAdapter,
    "sc_compras": ScComprasAdapter,
}

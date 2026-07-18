"""Single operational pipeline: fetch → raw → normalize → DB → evidence → watermark."""
from __future__ import annotations
import logging

import json
import os
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.crawl.ingestion._base.crawler import CrawlRequest, FetchResult, SourceAdapter
from scripts.crawl.resilience.config import ResilienceConfig
from scripts.crawl.resilience.persistence import (
    PersistenceBackend,
    PersistResult,
    build_persistence_backend,
    extract_content_max_timestamp,
)
from scripts.crawl.resilience.state import (
    CanonicalCheckpoint,
    CheckpointStore,
    EvidenceLedger,
    FileDLQ,
    RunHistory,
    StageLedger,
    WatermarkStore,
    coerce_canonical_checkpoint,
)
from scripts.crawl.run_evidence import sha256_json


def _atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str), encoding="utf-8")
    os.replace(tmp, path)


class OperationalPipeline:
    """Canonical path shared by resilient_cycle (and future monitor facade)."""

    def __init__(
        self,
        config: ResilienceConfig,
        *,
        persistence: PersistenceBackend | None = None,
        crash_after: str | None = None,
    ):
        self.config = config
        self.checkpoints = CheckpointStore(config.checkpoint_path)
        self.evidence = EvidenceLedger(config.evidence_path)
        self.watermarks = WatermarkStore(config.ops_path / "watermarks")
        self.stages = StageLedger(config.ops_path / "stages")
        self.history = RunHistory(config.ops_path / "run_history")
        self.dlq = FileDLQ(config.dlq_path)
        self.persistence = persistence or build_persistence_backend(require_db=config.require_db)
        self.crash_after = crash_after  # test hook: raise after named stage

    def _maybe_crash(self, stage: str) -> None:
        if self.crash_after and self.crash_after == stage:
            raise RuntimeError(f"injected_crash_after:{stage}")

    def run_source(
        self,
        adapter: SourceAdapter,
        request: CrawlRequest,
        *,
        run_id: str,
    ) -> dict[str, Any]:
        source = adapter.source_id
        scope = request.request_scope or f"mode={request.mode}|date={request.date_from}"
        artifact_meta = self.config.artifact_metadata(source=source, run_id=run_id)
        started_at = datetime.now(UTC).isoformat()

        # Resume: if previous run already watermarked this scope, short-circuit.
        existing_wm = self.watermarks.load(source, scope)
        if existing_wm and existing_wm.get("status") == "committed":
            return {
                "status": "success",
                "satisfactory": True,
                "operational_satisfactory": bool(
                    existing_wm.get("db_committed") and self.config.execution_mode != "fixture"
                ),
                "resumed": True,
                "watermark": existing_wm,
                "records_fetched": 0,
                "records_persisted": 0,
                "db_records_committed": 0,
                "errors": [],
            }

        stage_doc = self.stages.load(source, run_id, scope) or {}
        last = stage_doc.get("last_stage")
        prior_db_committed = bool(stage_doc.get("db_committed"))
        for entry in reversed(stage_doc.get("stages") or []):
            meta = entry.get("meta") or {}
            if "db_committed" in meta:
                prior_db_committed = bool(meta["db_committed"])
                break
        fetched: FetchResult | None = None
        normalized: list[dict[str, Any]] = []
        canonical_path: Path | None = None
        canonical_hash: str | None = None
        persist_result = PersistResult()
        evidence_path: Path | None = None
        evidence: dict[str, Any] = {}

        try:
            # Stage: fetch + raw (adapter owns raw_persisted page checkpoints)
            if last not in {"normalized", "db_committed", "evidence_committed", "watermark_committed"}:
                fetched = adapter.fetch(request)
                self.stages.advance(source=source, run_id=run_id, request_scope=scope, stage="raw_persisted", meta={"status": fetched.status})
                self._maybe_crash("raw_persisted")
            else:
                # Re-fetch is skipped only when we have canonical artifact from this run.
                canonical_path = self.config.ops_path / "canonical" / source / f"{run_id}.json"
                if canonical_path.is_file():
                    normalized = json.loads(canonical_path.read_text(encoding="utf-8"))
                    fetched = FetchResult(
                        status="success",
                        records=normalized,
                        request_completed=True,
                        pages_fetched=1,
                        pages_expected=1,
                        provenance={"resumed_from": "canonical", **artifact_meta},
                    )
                else:
                    fetched = adapter.fetch(request)

            if fetched is None:
                raise RuntimeError("pipeline_missing_fetch_result")

            # Promote page-level checkpoints only after full operational path.
            # Do not mark success inside adapter for CIGA; cycle owns completion.

            # Stage: normalize
            if last not in {"db_committed", "evidence_committed", "watermark_committed"}:
                if not normalized:
                    normalized = list(adapter.normalize(fetched.records))
                canonical_path = self.config.ops_path / "canonical" / source / f"{run_id}.json"
                _atomic(canonical_path, normalized)
                canonical_hash = sha256_json(normalized)
                self.stages.advance(
                    source=source,
                    run_id=run_id,
                    request_scope=scope,
                    stage="normalized",
                    meta={"canonical_hash": canonical_hash, "count": len(normalized)},
                )
                self._promote_page_checkpoints(adapter, fetched, to_status="normalized")
                self._maybe_crash("normalized")
            else:
                if canonical_path is None:
                    canonical_path = self.config.ops_path / "canonical" / source / f"{run_id}.json"
                if canonical_path.is_file() and not normalized:
                    normalized = json.loads(canonical_path.read_text(encoding="utf-8"))
                canonical_hash = sha256_json(normalized) if normalized else None

            content_max = extract_content_max_timestamp(source, normalized)

            # Stage: persist canonical to PostgreSQL (or null/memory backend)
            db_committed = False
            if last not in {"evidence_committed", "watermark_committed", "db_committed"}:
                if fetched.status in {"success", "empty_confirmed"}:
                    if self.config.require_db or self.config.execution_mode in {"live", "canary"}:
                        persist_result = self.persistence.persist_canonical(
                            source=source,
                            records=normalized,
                            run_id=run_id,
                            request_scope=scope,
                            date_from=str(request.date_from) if request.date_from else None,
                            date_to=str(request.date_to) if request.date_to else None,
                            provenance=dict(fetched.provenance or {}),
                            fetch_status=str(fetched.status),
                            pages_fetched=fetched.pages_fetched,
                            pages_expected=fetched.pages_expected,
                        )
                        if persist_result.errors:
                            raise RuntimeError(";".join(persist_result.errors))
                        db_committed = True
                    else:
                        # Fixture/test mechanics: no operational DB claim.
                        persist_result = self.persistence.persist_canonical(
                            source=source,
                            records=normalized,
                            run_id=run_id,
                            request_scope=scope,
                            date_from=str(request.date_from) if request.date_from else None,
                            date_to=str(request.date_to) if request.date_to else None,
                            provenance=dict(fetched.provenance or {}),
                            fetch_status=str(fetched.status),
                            pages_fetched=fetched.pages_fetched,
                            pages_expected=fetched.pages_expected,
                        )
                        db_committed = False  # never operational without require_db
                    next_stage = "db_committed" if db_committed else "normalized"
                    # Never regress stage machine (db_committed -> normalized is illegal).
                    if last == "db_committed" and next_stage == "normalized":
                        next_stage = "db_committed"
                        db_committed = True
                    self.stages.advance(
                        source=source,
                        run_id=run_id,
                        request_scope=scope,
                        stage=next_stage,
                        meta={
                            "db_records_committed": persist_result.db_records_committed,
                            "backend": persist_result.backend,
                            "db_committed": db_committed,
                        },
                    )
                    if db_committed:
                        self._promote_page_checkpoints(adapter, fetched, to_status="db_committed")
                    self._maybe_crash("db_committed")
                else:
                    persist_result = PersistResult(errors=[f"skip_db_due_to_status:{fetched.status}"])
            else:
                # Resume after DB commit: do not re-persist or regress stage.
                db_committed = True if last == "db_committed" else prior_db_committed

            # Stage: evidence
            if fetched is None:
                raise RuntimeError("pipeline_missing_fetch_result_before_evidence")
            fetched.provenance = dict(fetched.provenance or {})
            if canonical_path:
                fetched.provenance["canonical_path"] = str(canonical_path)
            if canonical_hash:
                fetched.provenance["canonical_hash"] = canonical_hash
            fetched.provenance.update(artifact_meta)

            window = {
                "date_from": str(request.date_from) if request.date_from else None,
                "date_to": str(request.date_to) if request.date_to else None,
            }
            evidence_path, evidence = self.evidence.write(
                source=source,
                run_id=run_id,
                request_scope=scope,
                result=fetched,
                window=window,
                target=request.target,
                environment=self.config.environment,
                execution_mode=self.config.execution_mode,
                db_committed=db_committed,
                db_records_committed=persist_result.db_records_committed,
                content_max_timestamp=content_max or persist_result.content_max_timestamp,
                artifact_meta=artifact_meta,
            )
            self.stages.advance(
                source=source,
                run_id=run_id,
                request_scope=scope,
                stage="evidence_committed",
                meta={"evidence_hash": evidence.get("evidence_hash"), "satisfactory": evidence.get("satisfactory")},
            )
            self._maybe_crash("evidence_committed")

            # Run-level checkpoint
            fetched_status = fetched.status or "error"
            run_status: str = fetched_status
            if evidence.get("satisfactory") and db_committed and run_status in {"success", "empty_confirmed"}:
                run_status = fetched_status
            elif evidence.get("satisfactory") and not db_committed and self.config.execution_mode == "fixture":
                run_status = fetched_status
            elif not evidence.get("satisfactory"):
                run_status = fetched_status if fetched_status not in {"success", "empty_confirmed"} else "partial"

            run_cp = CanonicalCheckpoint(
                source=source,
                run_id=run_id,
                request_scope=scope,
                target=request.target,
                date_from=str(request.date_from) if request.date_from else None,
                date_to=str(request.date_to) if request.date_to else None,
                window=str(request.date_from) if request.date_from else None,
                status=run_status if run_status not in {"success", "empty_confirmed"} else "evidence_committed",
                attempt_count=1,
                last_http_status=fetched.http_status,
                last_error="; ".join(fetched.errors) or None,
                pages_fetched=fetched.pages_fetched,
                pages_expected=fetched.pages_expected,
                content_hash=canonical_hash,
                scope_level="run",
                environment=self.config.environment,
                execution_mode=self.config.execution_mode,
            )
            # Apply strict checkpoint from adapter if present (schema enforced).
            if isinstance(fetched.checkpoint, dict) and fetched.checkpoint:
                if "request_scope" in fetched.checkpoint and "source" in fetched.checkpoint:
                    page_cp = coerce_canonical_checkpoint(fetched.checkpoint)
                    # Never accept adapter success before pipeline completion for CIGA.
                    if page_cp.status in {"success", "empty_confirmed"} and not evidence.get("satisfactory"):
                        page_cp.status = "raw_persisted" if page_cp.raw_reference else "partial"
                    # Do not clobber a richer existing checkpoint (e.g. snapshot raw_reference).
                    existing = self.checkpoints.load(page_cp.source, page_cp.request_scope)
                    if existing and existing.raw_reference and not page_cp.raw_reference:
                        page_cp.raw_reference = existing.raw_reference
                    if existing and existing.scope_level == "snapshot":
                        page_cp.scope_level = "snapshot"
                    if existing and existing.snapshot_hash and not page_cp.snapshot_hash:
                        page_cp.snapshot_hash = existing.snapshot_hash
                    self.checkpoints.save(page_cp)

            self.checkpoints.save(run_cp)

            watermark_path = None
            if evidence.get("satisfactory"):
                # Promote only via validated state machine — never silent swallow.
                terminal = fetched.status if fetched.status in {"success", "empty_confirmed"} else "success"
                if run_cp.status == "evidence_committed":
                    self.checkpoints.promote(run_cp, terminal)
                self._promote_page_checkpoints(adapter, fetched, to_status=terminal)
                watermark_path = self.watermarks.commit(run_cp, evidence_path, evidence)
                if run_cp.status != "watermark_committed":
                    self.checkpoints.promote(run_cp, "watermark_committed")
                self.stages.advance(
                    source=source,
                    run_id=run_id,
                    request_scope=scope,
                    stage="watermark_committed",
                    meta={"watermark": str(watermark_path)},
                )
                self._maybe_crash("watermark_committed")

            out = {
                "status": fetched.status,
                "satisfactory": evidence.get("satisfactory"),
                "mechanics_satisfactory": evidence.get("mechanics_satisfactory"),
                "operational_satisfactory": evidence.get("operational_satisfactory"),
                "pages_fetched": fetched.pages_fetched,
                "pages_expected": fetched.pages_expected,
                "records_fetched": len(fetched.records),
                "records_persisted": persist_result.db_records_committed if db_committed else len(normalized),
                "db_records_committed": persist_result.db_records_committed if db_committed else 0,
                "db_committed": db_committed,
                "checkpoint": asdict(run_cp),
                "evidence": str(evidence_path),
                "evidence_hash": evidence.get("evidence_hash"),
                "canonical": str(canonical_path) if canonical_path else None,
                "watermark": str(watermark_path) if watermark_path else None,
                "errors": fetched.errors + persist_result.errors,
                "content_max_timestamp": content_max or persist_result.content_max_timestamp,
                "environment": self.config.environment,
                "execution_mode": self.config.execution_mode,
                "started_at": started_at,
            }
            self.history.append(
                {
                    "source": source,
                    "run_id": run_id,
                    "request_scope": scope,
                    "started_at": started_at,
                    "finished_at": datetime.now(UTC).isoformat(),
                    "status": out["status"],
                    "satisfactory": out["satisfactory"],
                    "operational_satisfactory": out["operational_satisfactory"],
                    "db_committed": db_committed,
                    "http_status": fetched.http_status,
                    "environment": self.config.environment,
                    "execution_mode": self.config.execution_mode,
                    "content_max_timestamp": out["content_max_timestamp"],
                    "evidence_hash": out["evidence_hash"],
                }
            )
            return out
        except Exception as exc:
            self.dlq.push(source=source, run_id=run_id, payload={"request_scope": scope}, error=exc, error_kind="systemic")
            self.history.append(
                {
                    "source": source,
                    "run_id": run_id,
                    "request_scope": scope,
                    "started_at": started_at,
                    "finished_at": datetime.now(UTC).isoformat(),
                    "status": "error",
                    "satisfactory": False,
                    "operational_satisfactory": False,
                    "db_committed": False,
                    "error": str(exc),
                    "environment": self.config.environment,
                    "execution_mode": self.config.execution_mode,
                }
            )
            return {
                "status": "error",
                "satisfactory": False,
                "mechanics_satisfactory": False,
                "operational_satisfactory": False,
                "errors": [str(exc)],
                "db_committed": False,
                "db_records_committed": 0,
                "records_fetched": 0,
                "records_persisted": 0,
                "environment": self.config.environment,
                "execution_mode": self.config.execution_mode,
                "started_at": started_at,
            }

    def _promote_page_checkpoints(self, adapter: SourceAdapter, fetched: FetchResult, *, to_status: str) -> None:
        """Include reused pages in the promoted set when concluding a window."""
        raw_refs = (fetched.metadata or {}).get("raw") or (fetched.provenance or {}).get("raw") or []
        if not isinstance(raw_refs, list):
            return
        for raw_ref in raw_refs:
            if not isinstance(raw_ref, dict):
                continue
            scope = raw_ref.get("request_scope")
            if not scope:
                continue
            cp = self.checkpoints.load(adapter.source_id, str(scope))
            if not cp:
                continue
            if cp.status in {"success", "empty_confirmed", "watermark_committed"}:
                continue
            from scripts.crawl.resilience.stages import InvalidCheckpointTransitionError, validate_transition

            target = to_status
            if to_status in {"success", "empty_confirmed"} and fetched.status in {"success", "empty_confirmed"}:
                target = fetched.status
            elif to_status == "evidence_committed":
                target = "db_committed" if cp.status in {"raw_persisted", "normalized", "pending"} else to_status
            try:
                validate_transition(cp.status, target)
            except InvalidCheckpointTransitionError:
                # Already at/after target is fine; other illegal jumps surface.
                if cp.status == target or cp.completed:
                    continue
                # Never regress page checkpoints (e.g. db_committed -> normalized).
                try:
                    from scripts.crawl.resilience.stages import stage_rank

                    if stage_rank(cp.status) >= stage_rank(target):
                        continue
                except Exception:
                    logging.getLogger(__name__).warning(
                        "swallowed exception in %s", __name__, exc_info=True
                    )
                raise
            if cp.status != target:
                self.checkpoints.promote(cp, target)

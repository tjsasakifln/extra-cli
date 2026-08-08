"""Mass contact enrichment: batch orchestration, metrics, checkpoint, artifacts.

Produces ``artifacts/confenge/contact-enrichment/<run_id>/`` with ownership-aware
exports and Warmbly feed subset (enrollable only for auto review queue).
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.confenge_contact_resolution.models import (
    AccountContactResolution,
    CompanyProcessingState,
    OwnershipStatus,
    VerificationStatus,
)
from scripts.confenge_contact_resolution.rate_limit import (
    RetryPolicy,
    RetryStats,
    call_with_retry,
    limiter_for,
)
from scripts.confenge_contact_resolution.resolver import ContactResolver, ResolverConfig
from scripts.confenge_contact_resolution.reuse_graph import ContactReuseGraph
from scripts.confenge_contact_resolution.third_party_registry import ThirdPartyRegistry

CHECKPOINT_FILENAME = "checkpoint.json"
METRICS_FILENAME = "metrics.json"
MANIFEST_FILENAME = "manifest.json"
CONTACTS_VERIFIED = "contacts_verified.jsonl"
CONTACTS_REVIEW = "contacts_review_required.jsonl"
CONTACTS_REJECTED = "contacts_rejected.jsonl"
ACCOUNTING_REJECTIONS = "accounting-contact-rejections.jsonl"
NO_CONTACT = "no-contact.jsonl"
FULL_RESOLUTIONS = "confenge-contact-candidates-v1.jsonl"
WARMBLY_FEED_DIR = "warmbly_feed"
REGISTRY_FILENAME = "third_party_registry.json"
REUSE_GRAPH_FILENAME = "reuse_graph.json"


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _digits(s: str) -> str:
    return "".join(ch for ch in (s or "") if ch.isdigit())[:14]


@dataclass
class CompanyJob:
    cnpj14: str
    razao_social: str | None = None
    priority_tier: str = "universe"  # PRIORITARIO_AGORA | A1 | A2 | strategic | universe
    priority_rank: int = 10_000_000
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class EnrichmentMetrics:
    companies_processed: int = 0
    companies_with_any_candidate: int = 0
    companies_with_enrollable_email: int = 0
    companies_with_enrollable_phone: int = 0
    companies_with_both: int = 0
    companies_without_contact: int = 0
    emails_found: int = 0
    emails_verified: int = 0
    generic_company_emails: int = 0
    nominal_company_emails: int = 0
    phones_found: int = 0
    mobile_phones: int = 0
    landlines: int = 0
    third_party_contacts_rejected: int = 0
    accounting_contacts_rejected: int = 0
    legal_contacts_rejected: int = 0
    shared_external_contacts_rejected: int = 0
    pattern_guesses_rejected: int = 0
    stale_contacts: int = 0
    review_required: int = 0
    # rates filled at end
    verified_email_rate: float = 0.0
    verified_phone_rate: float = 0.0
    any_company_contact_rate: float = 0.0
    third_party_rejection_rate: float = 0.0
    # perf
    companies_per_hour: float = 0.0
    cache_hits: int = 0
    retries: int = 0
    duration_seconds: float = 0.0
    coverage_spike_warning: bool | None = None
    coverage_spike_notes: list[str] = field(default_factory=list)

    def finalize(self, *, duration_s: float, baseline: dict[str, Any] | None = None) -> None:
        n = max(1, self.companies_processed)
        self.verified_email_rate = round(self.companies_with_enrollable_email / n, 4)
        self.verified_phone_rate = round(self.companies_with_enrollable_phone / n, 4)
        self.any_company_contact_rate = round(
            (self.companies_with_enrollable_email + self.companies_with_enrollable_phone - self.companies_with_both)
            / n,
            4,
        )
        # simpler: any enrollable channel
        with_enrollable = (
            self.companies_with_enrollable_email + self.companies_with_enrollable_phone - self.companies_with_both
        )
        self.any_company_contact_rate = round(with_enrollable / n, 4)
        total_rej = (
            self.third_party_contacts_rejected + self.shared_external_contacts_rejected + self.pattern_guesses_rejected
        )
        denom = max(1, self.emails_found + self.phones_found + total_rej)
        self.third_party_rejection_rate = round(
            (self.third_party_contacts_rejected + self.accounting_contacts_rejected) / denom, 4
        )
        self.duration_seconds = round(duration_s, 3)
        if duration_s > 0:
            self.companies_per_hour = round(self.companies_processed / duration_s * 3600, 2)

        if baseline:
            prev_rate = float(baseline.get("verified_email_rate") or 0)
            if self.verified_email_rate - prev_rate >= 0.5 and self.verified_email_rate >= 0.5:
                self.coverage_spike_warning = True
                self.coverage_spike_notes.append(
                    f"verified_email_rate jumped {prev_rate} → {self.verified_email_rate}; "
                    "inspect pattern_guesses / third_party / shared before celebrating"
                )
            if self.pattern_guesses_rejected == 0 and self.emails_verified > 0:
                # not necessarily bad; only flag with spike
                pass

    def as_dict(self) -> dict[str, Any]:
        return {
            "companies_processed": self.companies_processed,
            "companies_with_any_candidate": self.companies_with_any_candidate,
            "companies_with_enrollable_email": self.companies_with_enrollable_email,
            "companies_with_enrollable_phone": self.companies_with_enrollable_phone,
            "companies_with_both": self.companies_with_both,
            "companies_without_contact": self.companies_without_contact,
            "emails_found": self.emails_found,
            "emails_verified": self.emails_verified,
            "generic_company_emails": self.generic_company_emails,
            "nominal_company_emails": self.nominal_company_emails,
            "phones_found": self.phones_found,
            "mobile_phones": self.mobile_phones,
            "landlines": self.landlines,
            "third_party_contacts_rejected": self.third_party_contacts_rejected,
            "accounting_contacts_rejected": self.accounting_contacts_rejected,
            "legal_contacts_rejected": self.legal_contacts_rejected,
            "shared_external_contacts_rejected": self.shared_external_contacts_rejected,
            "pattern_guesses_rejected": self.pattern_guesses_rejected,
            "stale_contacts": self.stale_contacts,
            "review_required": self.review_required,
            "verified_email_rate": self.verified_email_rate,
            "verified_phone_rate": self.verified_phone_rate,
            "any_company_contact_rate": self.any_company_contact_rate,
            "third_party_rejection_rate": self.third_party_rejection_rate,
            "companies_per_hour": self.companies_per_hour,
            "cache_hits": self.cache_hits,
            "retries": self.retries,
            "duration_seconds": self.duration_seconds,
            "coverage_spike_warning": self.coverage_spike_warning,
            "coverage_spike_notes": list(self.coverage_spike_notes),
        }


def priority_sort_key(job: CompanyJob) -> tuple[int, int, str]:
    tier_order = {
        "PRIORITARIO_AGORA": 0,
        "A1": 1,
        "A2": 2,
        "strategic": 3,
        "universe": 4,
    }
    return (tier_order.get(job.priority_tier, 9), job.priority_rank, job.cnpj14)


def accumulate_metrics(
    metrics: EnrichmentMetrics,
    resolution: AccountContactResolution,
) -> None:
    metrics.companies_processed += 1
    if resolution.cache_hit:
        metrics.cache_hits += 1

    cands = resolution.candidates or []
    rejected = resolution.rejected_contacts or []
    if cands:
        metrics.companies_with_any_candidate += 1

    has_enroll_email = False
    has_enroll_phone = False
    for c in cands:
        if c.email:
            metrics.emails_found += 1
            if c.enrollable:
                metrics.emails_verified += 1
                has_enroll_email = True
            if c.name:
                metrics.nominal_company_emails += 1
            elif c.email:
                metrics.generic_company_emails += 1
            if c.email_layers and c.email_layers.pattern_guessed:
                metrics.pattern_guesses_rejected += 1
            if c.verification_status in {
                VerificationStatus.PATTERN_GUESS.value,
                VerificationStatus.CANDIDATE_UNVERIFIED.value,
            }:
                metrics.pattern_guesses_rejected += 1
        if c.phone_e164:
            metrics.phones_found += 1
            if c.phone_type == "mobile":
                metrics.mobile_phones += 1
            elif c.phone_type == "landline":
                metrics.landlines += 1
            if c.enrollable:
                has_enroll_phone = True
        if c.ownership_status == OwnershipStatus.LIKELY_COMPANY_OWNED.value:
            metrics.review_required += 1
        if c.freshness_class == "STALE" or (c.freshness_days is not None and c.freshness_days > 365):
            metrics.stale_contacts += 1

    for r in rejected:
        metrics.third_party_contacts_rejected += 1
        tp = (r.get("third_party_type") or "").upper()
        own = (r.get("ownership_status") or "").upper()
        if tp == "ACCOUNTING" or "ACCOUNTING" in (r.get("reason") or "").upper():
            metrics.accounting_contacts_rejected += 1
        if tp == "LEGAL":
            metrics.legal_contacts_rejected += 1
        if own == OwnershipStatus.SHARED_EXTERNAL_CONTACT.value:
            metrics.shared_external_contacts_rejected += 1

    if has_enroll_email:
        metrics.companies_with_enrollable_email += 1
    if has_enroll_phone:
        metrics.companies_with_enrollable_phone += 1
    if has_enroll_email and has_enroll_phone:
        metrics.companies_with_both += 1
    if not cands and not rejected:
        metrics.companies_without_contact += 1
    elif not has_enroll_email and not has_enroll_phone and not cands:
        metrics.companies_without_contact += 1


def company_export_row(resolution: AccountContactResolution) -> dict[str, Any]:
    """Per-company output shape from OBJECTIVE §22."""
    contacts = []
    for c in resolution.candidates:
        if not c.enrollable and c.ownership_status not in {
            OwnershipStatus.LIKELY_COMPANY_OWNED.value,
            OwnershipStatus.COMPANY_OWNED.value,
            OwnershipStatus.HUMAN_CONFIRMED.value,
        }:
            # still include LIKELY for review; skip pure unresolved noise in verified feed
            if c.ownership_status == OwnershipStatus.UNRESOLVED.value and not c.enrollable:
                continue
        contacts.append(
            {
                "type": c.contact_type if c.contact_type != "UNKNOWN" else ("EMAIL" if c.email else "PHONE"),
                "value": c.email or c.phone_e164,
                "role_class": c.role_class,
                "ownership_status": c.ownership_status,
                "verification_status": c.verification_status,
                "confidence": c.confidence,
                "enrollable": c.enrollable,
                "ownership_reason": c.ownership_reason,
                "verification_reason": c.verification_reason,
                "provenance": {
                    "source_type": c.source.source_type if c.source else None,
                    "source_url": c.source.source_url if c.source else None,
                    "source_document": c.source.source_document if c.source else None,
                    "source_date": c.source.source_date if c.source else None,
                    "source_urls": list(c.source_urls or []),
                    "source_types": list(c.source_types or []),
                },
                "name": c.name,
                "phone_e164": c.phone_e164,
                "email": c.email,
                "whatsapp_consent_status": c.whatsapp.consent_status if c.whatsapp else "UNKNOWN",
            }
        )
    return {
        "cnpj14": resolution.cnpj14,
        "company_name": resolution.razao_social,
        "official_domain": resolution.official_domain,
        "processing_state": resolution.processing_state,
        "commercial_contact_state": resolution.commercial_contact_state,
        "contacts": contacts,
        "rejected_contacts": list(resolution.rejected_contacts or []),
    }


def warmbly_contact_payload(resolution: AccountContactResolution) -> dict[str, Any]:
    """Bridge-ready contacts row preserving ownership fields."""
    contacts = []
    for i, c in enumerate(resolution.candidates):
        contacts.append(
            {
                "source_contact_id": c.candidate_id or f"ct-{resolution.cnpj14}-{i}",
                "name": c.name or "",
                "role": c.cargo or c.role_class or "",
                "role_class": c.role_class,
                "email": c.email or "",
                "phone": c.phone_e164 or c.phone_raw or "",
                "linkedin_url": c.linkedin_public or "",
                "source_url": (c.source.source_url if c.source else "") or "",
                "source_document": (c.source.source_document if c.source else "") or "",
                "source_date": (c.source.source_date if c.source else "") or "",
                "verification_status": c.verification_status,
                "ownership_status": c.ownership_status,
                "ownership_reason": c.ownership_reason or "",
                "verification_reason": c.verification_reason or "",
                "third_party_type": c.third_party_type or "",
                "confidence": str(c.confidence),
                "enrollable": bool(c.enrollable),
                "recommended": bool(c.recommended),
                "provenance": {
                    "source_type": c.source.source_type if c.source else None,
                    "source_url": c.source.source_url if c.source else None,
                    "source_urls": list(c.source_urls or []),
                    "source_types": list(c.source_types or []),
                },
            }
        )
    return {
        "cnpj14": resolution.cnpj14,
        "razao_social": resolution.razao_social,
        "commercial_contact_state": resolution.commercial_contact_state,
        "processing_state": resolution.processing_state,
        "contacts": contacts,
        "rejected_contacts": list(resolution.rejected_contacts or []),
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r, ensure_ascii=False, default=str, sort_keys=True) for r in rows]
    body = "\n".join(lines) + ("\n" if lines else "")
    path.write_text(body, encoding="utf-8")
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def accounting_rejection_row(
    resolution: AccountContactResolution,
    rejected: dict[str, Any],
) -> dict[str, Any] | None:
    tp = (rejected.get("third_party_type") or "").upper()
    reason = (rejected.get("reason") or "").lower()
    if tp != "ACCOUNTING" and "contabil" not in reason and "account" not in reason:
        return None
    return {
        "company_cnpj": resolution.cnpj14,
        "company_name": resolution.razao_social,
        "candidate_contact": rejected.get("value"),
        "candidate_domain": None,
        "detected_accounting_entity": rejected.get("third_party_type"),
        "reason": rejected.get("reason"),
        "number_of_unrelated_companies_using_contact": rejected.get("associated_company_count") or 0,
        "evidence": rejected.get("sources") or [],
    }


class EnrichmentBatchRunner:
    """Progressive national enrichment with checkpoint/resume."""

    def __init__(
        self,
        *,
        output_dir: Path | str,
        resolver: ContactResolver | None = None,
        resolver_config: ResolverConfig | None = None,
        run_id: str | None = None,
        baseline_metrics: dict[str, Any] | None = None,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id or (
            f"contact-enrichment-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
        )
        self.baseline_metrics = baseline_metrics
        reuse = ContactReuseGraph.load(self.output_dir / REUSE_GRAPH_FILENAME)
        registry = ThirdPartyRegistry.load(self.output_dir / REGISTRY_FILENAME)
        if resolver is not None:
            self.resolver = resolver
            self.resolver.reuse_graph = reuse
            self.resolver.third_party_registry = registry
        else:
            cfg = resolver_config or ResolverConfig()
            cfg.reuse_graph = reuse
            cfg.third_party_registry = registry
            cfg.apply_ownership = True
            self.resolver = ContactResolver(cfg)
        self.metrics = EnrichmentMetrics()
        self._checkpoint: dict[str, Any] = self._load_checkpoint()
        self.retry_policy = RetryPolicy(max_attempts=3, base_delay_seconds=0.25, max_delay_seconds=8.0)
        self.retry_stats = RetryStats()
        self._source_limiters = {
            "registry": limiter_for("registry"),
            "web_search": limiter_for("web_search"),
            "site": limiter_for("site"),
            "default": limiter_for("default"),
        }

    def _load_checkpoint(self) -> dict[str, Any]:
        p = self.output_dir / CHECKPOINT_FILENAME
        if p.is_file():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        return {"completed_cnpjs": [], "failed_cnpjs": {}, "updated_at": None}

    def _save_checkpoint(self) -> None:
        self._checkpoint["updated_at"] = _now()
        (self.output_dir / CHECKPOINT_FILENAME).write_text(
            json.dumps(self._checkpoint, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _resolve_with_retry(self, cnpj14: str) -> AccountContactResolution:
        """Resolve one CNPJ with rate-limit wait + exponential backoff on transport errors."""

        def _once() -> AccountContactResolution:
            self.retry_stats.attempts += 1
            # Network path: wait on registry limiter before each attempt
            if self.resolver.config.allow_network:
                waited = self._source_limiters["registry"].wait_if_needed()
                if waited > 0:
                    self.retry_stats.rate_limit_waits += 1
            return self.resolver.resolve_one(cnpj14, account_key=cnpj14)

        def _on_retry(attempt: int, exc: BaseException, delay: float) -> None:
            self.retry_stats.retries += 1
            self.metrics.retries += 1
            self.retry_stats.last_error = f"{type(exc).__name__}:{exc}"

        # Offline fixture path: single attempt is enough; still go through policy
        # so retry wiring is exercised and unit-testable.
        return call_with_retry(
            _once,
            policy=self.retry_policy,
            rate_limiter=None,  # per-source wait handled inside _once when network on
            on_retry=_on_retry,
        )

    def run(
        self,
        jobs: list[CompanyJob],
        *,
        resume: bool = True,
        max_companies: int | None = None,
    ) -> dict[str, Any]:
        ordered = sorted(jobs, key=priority_sort_key)
        done = set(self._checkpoint.get("completed_cnpjs") or []) if resume else set()
        todo = [j for j in ordered if j.cnpj14 not in done]
        if max_companies is not None:
            todo = todo[: max(0, int(max_companies))]

        t0 = time.time()
        resolutions: list[AccountContactResolution] = []
        verified_rows: list[dict[str, Any]] = []
        review_rows: list[dict[str, Any]] = []
        rejected_rows: list[dict[str, Any]] = []
        accounting_rows: list[dict[str, Any]] = []
        no_contact_rows: list[dict[str, Any]] = []
        warmbly_rows: list[dict[str, Any]] = []
        warmbly_enrollable: list[dict[str, Any]] = []

        # Two-pass enrichment:
        # 1) discover channels with ownership off → seed reverse reuse graph
        # 2) re-resolve with ownership on so SHARED_EXTERNAL sees the full cohort
        prev_ownership = self.resolver.config.apply_ownership
        self.resolver.config.apply_ownership = False
        pass1: list[AccountContactResolution] = []
        for job in todo:
            try:
                res = self._resolve_with_retry(job.cnpj14)
                if not res.razao_social and job.razao_social:
                    res.razao_social = job.razao_social
                pass1.append(res)
                for c in res.candidates:
                    self.resolver.reuse_graph.observe_candidate(
                        res.cnpj14,
                        email=c.email,
                        phone=c.phone_e164 or c.phone_raw,
                        razao_social=res.razao_social,
                    )
            except Exception as exc:  # noqa: BLE001
                self.metrics.retries += 1
                self.retry_stats.retries += 1
                self.retry_stats.last_error = str(exc)
                self._checkpoint.setdefault("failed_cnpjs", {})[job.cnpj14] = f"pass1:{exc}"

        self.resolver.config.apply_ownership = True
        # Drop pass1 cache entries so pass2 recomputes ownership with full graph
        if self.resolver.config.cache is not None:
            # ResolutionCache has no clear(); overwrite via fresh resolves with no-cache keys
            # by temporarily disabling cache for pass2 when present.
            cached = self.resolver.config.cache
            self.resolver.config.cache = None
        else:
            cached = None

        for job in todo:
            try:
                res = self._resolve_with_retry(job.cnpj14)
                if not res.razao_social and job.razao_social:
                    res.razao_social = job.razao_social
            except Exception as exc:  # noqa: BLE001 — per-company fail soft
                self.metrics.retries += 1
                self.retry_stats.retries += 1
                self.retry_stats.last_error = str(exc)
                failed = AccountContactResolution(
                    cnpj14=job.cnpj14,
                    account_key=job.cnpj14,
                    razao_social=job.razao_social,
                    processing_state=CompanyProcessingState.FAILED.value,
                    absence_reason=f"resolver_error:{type(exc).__name__}",
                    limitations=[str(exc)],
                )
                # Soft: still emit FAILED row so batch continues
                resolutions.append(failed)
                accumulate_metrics(self.metrics, failed)
                self._checkpoint.setdefault("failed_cnpjs", {})[job.cnpj14] = str(exc)
                self._checkpoint.setdefault("completed_cnpjs", []).append(job.cnpj14)
                self._save_checkpoint()
                continue

            resolutions.append(res)
            accumulate_metrics(self.metrics, res)
            row = company_export_row(res)
            wb = warmbly_contact_payload(res)

            enrollable_contacts = [c for c in res.candidates if c.enrollable]
            likely = [c for c in res.candidates if c.ownership_status == OwnershipStatus.LIKELY_COMPANY_OWNED.value]

            if enrollable_contacts:
                verified_rows.append(row)
                warmbly_enrollable.append(
                    {
                        **wb,
                        "contacts": [c for c in wb["contacts"] if c.get("enrollable")],
                    }
                )
            if likely or res.commercial_contact_state == "CONTACT_REVIEW_REQUIRED":
                review_rows.append(row)
            if res.rejected_contacts:
                rejected_rows.append(
                    {
                        "cnpj14": res.cnpj14,
                        "company_name": res.razao_social,
                        "rejected_contacts": res.rejected_contacts,
                    }
                )
                for r in res.rejected_contacts:
                    ar = accounting_rejection_row(res, r)
                    if ar:
                        # fill domain
                        val = str(r.get("value") or "")
                        if "@" in val:
                            ar["candidate_domain"] = val.split("@", 1)[-1].lower()
                        accounting_rows.append(ar)
            if not res.candidates and not res.rejected_contacts:
                no_contact_rows.append(
                    {
                        "cnpj14": res.cnpj14,
                        "company_name": res.razao_social,
                        "commercial_contact_state": res.commercial_contact_state,
                        "absence_reason": res.absence_reason,
                        "next_contact_resolution_at": res.next_contact_resolution_at,
                    }
                )

            warmbly_rows.append(wb)
            self._checkpoint.setdefault("completed_cnpjs", []).append(job.cnpj14)
            # periodic checkpoint every 25
            if len(resolutions) % 25 == 0:
                self._save_checkpoint()

        if cached is not None:
            self.resolver.config.cache = cached
        self.resolver.config.apply_ownership = prev_ownership

        self._save_checkpoint()
        duration = time.time() - t0
        self.metrics.finalize(duration_s=duration, baseline=self.baseline_metrics)

        # Persist graph + registry
        self.resolver.reuse_graph.save(self.output_dir / REUSE_GRAPH_FILENAME)
        self.resolver.third_party_registry.save(self.output_dir / REGISTRY_FILENAME)

        # Artifacts
        write_jsonl(self.output_dir / FULL_RESOLUTIONS, [r.as_dict() for r in resolutions])
        write_jsonl(self.output_dir / CONTACTS_VERIFIED, verified_rows)
        write_jsonl(self.output_dir / CONTACTS_REVIEW, review_rows)
        write_jsonl(self.output_dir / CONTACTS_REJECTED, rejected_rows)
        write_jsonl(self.output_dir / ACCOUNTING_REJECTIONS, accounting_rows)
        write_jsonl(self.output_dir / NO_CONTACT, no_contact_rows)

        feed_dir = self.output_dir / WARMBLY_FEED_DIR
        feed_dir.mkdir(parents=True, exist_ok=True)
        write_jsonl(feed_dir / "contacts.jsonl", warmbly_rows)
        write_jsonl(feed_dir / "contacts_enrollable.jsonl", warmbly_enrollable)

        metrics_path = self.output_dir / METRICS_FILENAME
        metrics_path.write_text(
            json.dumps(self.metrics.as_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        metrics_dict = self.metrics.as_dict()
        metrics_dict["retry_stats"] = self.retry_stats.as_dict()
        manifest = {
            "schema_id": "confenge-contact-enrichment-manifest-v1",
            "run_id": self.run_id,
            "output_dir": str(self.output_dir),
            "started_jobs": len(todo),
            "resolved": len(resolutions),
            "metrics": metrics_dict,
            "retry_stats": self.retry_stats.as_dict(),
            "artifacts": {
                "candidates": FULL_RESOLUTIONS,
                "verified": CONTACTS_VERIFIED,
                "review_required": CONTACTS_REVIEW,
                "rejected": CONTACTS_REJECTED,
                "accounting_rejections": ACCOUNTING_REJECTIONS,
                "no_contact": NO_CONTACT,
                "warmbly_feed": WARMBLY_FEED_DIR,
                "checkpoint": CHECKPOINT_FILENAME,
                "third_party_registry": REGISTRY_FILENAME,
                "reuse_graph": REUSE_GRAPH_FILENAME,
            },
            "finished_at": _now(),
            "ok": True,
        }
        (self.output_dir / MANIFEST_FILENAME).write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return manifest

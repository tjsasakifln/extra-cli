"""Mass contact enrichment: batch orchestration, metrics, checkpoint, artifacts.

Produces ``artifacts/confenge/contact-enrichment/<run_id>/`` with ownership-aware
exports and Warmbly feed subset (enrollable only for auto review queue).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.confenge_contact_resolution.discovery_state import (
    classify_contact_terminal,
    sources_cover_required_ladder,
)
from scripts.confenge_contact_resolution.mailbox_purpose import classify_mailbox_purpose
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

logger = logging.getLogger(__name__)

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
SOURCE_ATTEMPTS_FILENAME = "contact-source-attempts.jsonl"
TERMINALS_FILENAME = "contact-discovery-terminals.jsonl"


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _digits(s: str) -> str:
    return "".join(ch for ch in (s or "") if ch.isdigit())[:14]


def is_publishable_human_contact(candidate: Any) -> bool:
    """Strict pre-feed contact gate independent of target/service/copy context."""
    source = candidate.source
    layers = candidate.email_layers
    evidence_hash = str(candidate.evidence_sha256 or (source.evidence_sha256 if source else "") or "")
    return bool(
        candidate.email
        and candidate.enrollable
        and candidate.ownership_status in {OwnershipStatus.COMPANY_OWNED.value, OwnershipStatus.HUMAN_CONFIRMED.value}
        and candidate.human_identity_evidence_valid
        and candidate.email_explicitly_published
        and candidate.name_explicitly_published
        and candidate.role_explicitly_published
        and candidate.name
        and candidate.cargo
        and candidate.identity_evidence_urls
        and re.fullmatch(r"[0-9a-fA-F]{64}", evidence_hash)
        and source
        and (source.source_url or source.source_document)
        and (source.source_published_at or source.observed_at or source.verified_at)
        and layers.syntactic_ok is True
        and layers.domain_ok is True
        and layers.pattern_guessed is False
        and layers.mx_checked is True
        and layers.mx_ok is True
        and not candidate.dnc
        and not candidate.bounce
        and candidate.freshness_class != "STALE"
        and not classify_mailbox_purpose(candidate.email).send_blocked
    )


def principal_publishable_human_contacts(resolution: AccountContactResolution) -> list[Any]:
    """Return exactly one deterministic principal when the account is publishable."""
    ready = [candidate for candidate in resolution.candidates if is_publishable_human_contact(candidate)]
    if not ready:
        return []
    ready.sort(
        key=lambda candidate: (
            candidate.candidate_id != resolution.recommended_candidate_id,
            -float(candidate.confidence or 0),
            str(candidate.evidence_sha256 or ""),
            str(candidate.candidate_id or ""),
            str(candidate.email or "").lower(),
        )
    )
    return [ready[0]]


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
    emails_review_required: int = 0
    generic_company_emails: int = 0
    nominal_company_emails: int = 0
    phones_found: int = 0
    phones_enrollable: int = 0
    mobile_phones: int = 0
    landlines: int = 0
    # Partitioned rejections (each contact counted once via primary reason)
    rejected_total: int = 0
    rejected_by_primary_reason: dict[str, int] = field(
        default_factory=lambda: {
            "ACCOUNTING": 0,
            "LEGAL": 0,
            "SHARED_EXTERNAL": 0,
            "PATTERN_GUESS": 0,
            "OTHER_THIRD_PARTY": 0,
            "INVALID": 0,
        }
    )
    # Legacy aliases (equal to partition buckets — no double-count)
    third_party_contacts_rejected: int = 0
    accounting_contacts_rejected: int = 0
    legal_contacts_rejected: int = 0
    shared_external_contacts_rejected: int = 0
    pattern_guesses_rejected: int = 0
    stale_contacts: int = 0
    review_required: int = 0
    # discovery / budget outcomes
    investigation_outcomes: dict[str, int] = field(default_factory=dict)
    web_queries_total: int = 0
    pages_fetched_total: int = 0
    http_429: int = 0
    timeouts: int = 0
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
    # reuse graph summary (filled at end of batch)
    reuse_graph_metrics: dict[str, Any] = field(default_factory=dict)
    fixtures_dir: str | None = None
    synthetic_contacts: int = 0
    manually_injected_contacts: int = 0

    def finalize(self, *, duration_s: float, baseline: dict[str, Any] | None = None) -> None:
        n = max(1, self.companies_processed)
        self.verified_email_rate = round(self.companies_with_enrollable_email / n, 4)
        self.verified_phone_rate = round(self.companies_with_enrollable_phone / n, 4)
        with_enrollable = (
            self.companies_with_enrollable_email + self.companies_with_enrollable_phone - self.companies_with_both
        )
        self.any_company_contact_rate = round(with_enrollable / n, 4)
        # Sync legacy counters from partition (single source of truth)
        self.pattern_guesses_rejected = int(self.rejected_by_primary_reason.get("PATTERN_GUESS", 0))
        self.accounting_contacts_rejected = int(self.rejected_by_primary_reason.get("ACCOUNTING", 0))
        self.legal_contacts_rejected = int(self.rejected_by_primary_reason.get("LEGAL", 0))
        self.shared_external_contacts_rejected = int(self.rejected_by_primary_reason.get("SHARED_EXTERNAL", 0))
        self.third_party_contacts_rejected = int(
            self.rejected_by_primary_reason.get("OTHER_THIRD_PARTY", 0)
            + self.accounting_contacts_rejected
            + self.legal_contacts_rejected
        )
        denom = max(1, self.emails_found + self.phones_found + self.rejected_total)
        self.third_party_rejection_rate = round(self.third_party_contacts_rejected / denom, 4)
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

    def as_dict(self) -> dict[str, Any]:
        return {
            "companies_processed": self.companies_processed,
            "companies_with_any_candidate": self.companies_with_any_candidate,
            "companies_with_enrollable_email": self.companies_with_enrollable_email,
            "companies_with_enrollable_phone": self.companies_with_enrollable_phone,
            "companies_with_both": self.companies_with_both,
            "companies_without_contact": self.companies_without_contact,
            "companies_no_contact": self.companies_without_contact,
            "emails_found": self.emails_found,
            "emails_enrollable": self.emails_verified,
            "emails_verified": self.emails_verified,
            "emails_review_required": self.emails_review_required,
            "generic_company_emails": self.generic_company_emails,
            "nominal_company_emails": self.nominal_company_emails,
            "phones_found": self.phones_found,
            "phones_enrollable": self.phones_enrollable,
            "mobile_phones": self.mobile_phones,
            "landlines": self.landlines,
            "rejected_total": self.rejected_total,
            "rejected_by_primary_reason": dict(self.rejected_by_primary_reason),
            "third_party_contacts_rejected": self.third_party_contacts_rejected,
            "third_party_rejected": self.third_party_contacts_rejected,
            "accounting_contacts_rejected": self.accounting_contacts_rejected,
            "accounting_rejected": self.accounting_contacts_rejected,
            "legal_contacts_rejected": self.legal_contacts_rejected,
            "legal_rejected": self.legal_contacts_rejected,
            "shared_external_contacts_rejected": self.shared_external_contacts_rejected,
            "shared_external_rejected": self.shared_external_contacts_rejected,
            "pattern_guesses_rejected": self.pattern_guesses_rejected,
            "pattern_guess_rejected": self.pattern_guesses_rejected,
            "stale_contacts": self.stale_contacts,
            "review_required": self.review_required,
            "investigation_outcomes": dict(self.investigation_outcomes),
            "web_queries_total": self.web_queries_total,
            "pages_fetched_total": self.pages_fetched_total,
            "http_429": self.http_429,
            "timeouts": self.timeouts,
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
            "reuse_graph_metrics": dict(self.reuse_graph_metrics),
            "fixtures_dir": self.fixtures_dir,
            "synthetic_contacts": self.synthetic_contacts,
            "manually_injected_contacts": self.manually_injected_contacts,
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


def _record_primary_rejection(metrics: EnrichmentMetrics, primary: str) -> None:
    """Count one rejected contact under exactly one primary reason."""
    key = (primary or "INVALID").upper()
    if key not in metrics.rejected_by_primary_reason:
        key = "INVALID"
    metrics.rejected_total += 1
    metrics.rejected_by_primary_reason[key] = int(metrics.rejected_by_primary_reason.get(key, 0)) + 1


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
    counted_values: set[str] = set()

    for c in cands:
        if c.email:
            metrics.emails_found += 1
            if is_publishable_human_contact(c):
                metrics.emails_verified += 1
                has_enroll_email = True
            elif c.ownership_status == OwnershipStatus.LIKELY_COMPANY_OWNED.value:
                metrics.emails_review_required += 1
            if c.name:
                metrics.nominal_company_emails += 1
            else:
                metrics.generic_company_emails += 1
            # Non-enrollable candidate: count pattern-guess once (not twice)
            if not c.enrollable:
                is_guess = bool(c.email_layers and c.email_layers.pattern_guessed)
                vreason = (c.verification_reason or "").upper()
                if (
                    is_guess
                    or vreason == "PATTERN_GUESS"
                    or c.verification_status == VerificationStatus.PATTERN_GUESS.value
                ):
                    val = (c.email or "").lower()
                    if val and val not in counted_values:
                        counted_values.add(val)
                        _record_primary_rejection(metrics, "PATTERN_GUESS")
        if c.phone_e164:
            metrics.phones_found += 1
            if c.phone_type == "mobile":
                metrics.mobile_phones += 1
            elif c.phone_type == "landline":
                metrics.landlines += 1
            if c.enrollable:
                metrics.phones_enrollable += 1
                has_enroll_phone = True
        if c.ownership_status == OwnershipStatus.LIKELY_COMPANY_OWNED.value:
            metrics.review_required += 1
        if c.freshness_class == "STALE" or (c.freshness_days is not None and c.freshness_days > 365):
            metrics.stale_contacts += 1

    for r in rejected:
        val = str(r.get("value") or "").lower()
        if val and val in counted_values:
            continue  # already counted as pattern guess on candidate list
        if val:
            counted_values.add(val)
        primary = (r.get("primary_rejection_reason") or "").upper()
        if not primary:
            tp = (r.get("third_party_type") or "").upper()
            own = (r.get("ownership_status") or "").upper()
            reason = (r.get("reason") or "").upper()
            if "PATTERN" in reason:
                primary = "PATTERN_GUESS"
            elif tp == "ACCOUNTING" or "ACCOUNTING" in reason or "CONTAB" in reason:
                primary = "ACCOUNTING"
            elif tp == "LEGAL":
                primary = "LEGAL"
            elif own == OwnershipStatus.SHARED_EXTERNAL_CONTACT.value:
                primary = "SHARED_EXTERNAL"
            elif own == OwnershipStatus.THIRD_PARTY_SERVICE_PROVIDER.value or tp:
                primary = "OTHER_THIRD_PARTY"
            else:
                primary = "INVALID"
        _record_primary_rejection(metrics, primary)

    inv = getattr(resolution, "investigation_outcome", None)
    if inv:
        metrics.investigation_outcomes[str(inv)] = metrics.investigation_outcomes.get(str(inv), 0) + 1
    disc = getattr(resolution, "discovery_stats", None) or {}
    if isinstance(disc, dict):
        metrics.web_queries_total += int(disc.get("search_queries") or 0)
        metrics.pages_fetched_total += int(disc.get("pages_fetched") or 0)
        metrics.http_429 += int(disc.get("http_429") or 0)
        metrics.timeouts += int(disc.get("timeouts") or 0)

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
                    "source_published_at": c.source.source_published_at if c.source else None,
                    "observed_at": c.source.observed_at if c.source else None,
                    "verified_at": c.source.verified_at if c.source else None,
                    "evidence_sha256": c.evidence_sha256,
                    "email_explicitly_published": c.email_explicitly_published,
                    "name_explicitly_published": c.name_explicitly_published,
                    "role_explicitly_published": c.role_explicitly_published,
                    "human_identity_evidence_valid": c.human_identity_evidence_valid,
                    "identity_evidence_urls": list(c.identity_evidence_urls),
                    "source_urls": list(c.source_urls or []),
                    "source_types": list(c.source_types or []),
                },
                "name": c.name,
                "cargo": c.cargo,
                "phone_e164": c.phone_e164,
                "email": c.email,
                "email_explicitly_published": c.email_explicitly_published,
                "name_explicitly_published": c.name_explicitly_published,
                "role_explicitly_published": c.role_explicitly_published,
                "human_identity_evidence_valid": c.human_identity_evidence_valid,
                "identity_evidence_urls": list(c.identity_evidence_urls),
                "evidence_sha256": c.evidence_sha256,
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
                "source_date": (
                    (
                        c.source.source_published_at
                        or c.source.verified_at
                        or c.source.observed_at
                        or c.source.source_date
                        or ""
                    )
                    if c.source
                    else ""
                )[:10],
                "source_date_semantics": (
                    "source_published_at"
                    if c.source and c.source.source_published_at
                    else "verified_at"
                    if c.source and c.source.verified_at
                    else "observed_at"
                    if c.source and c.source.observed_at
                    else "legacy_source_date"
                    if c.source and c.source.source_date
                    else "missing"
                ),
                "source_published_at": (c.source.source_published_at if c.source else "") or "",
                "observed_at": (c.source.observed_at if c.source else "") or "",
                "verified_at": (c.source.verified_at if c.source else "") or "",
                "evidence_sha256": c.evidence_sha256 or "",
                "verification_status": c.verification_status,
                "ownership_status": c.ownership_status,
                "ownership_reason": c.ownership_reason or "",
                "verification_reason": c.verification_reason or "",
                "third_party_type": c.third_party_type or "",
                "confidence": str(c.confidence),
                "enrollable": bool(c.enrollable),
                "recommended": bool(c.recommended),
                "email_explicitly_published": c.email_explicitly_published,
                "name_explicitly_published": c.name_explicitly_published,
                "role_explicitly_published": c.role_explicitly_published,
                "human_identity_evidence_valid": c.human_identity_evidence_valid,
                "identity_evidence_urls": list(c.identity_evidence_urls),
                "provenance": {
                    "source_type": c.source.source_type if c.source else None,
                    "source_url": c.source.source_url if c.source else None,
                    "source_document": c.source.source_document if c.source else None,
                    "source_date": c.source.source_date if c.source else None,
                    "source_published_at": c.source.source_published_at if c.source else None,
                    "observed_at": c.source.observed_at if c.source else None,
                    "verified_at": c.source.verified_at if c.source else None,
                    "evidence_sha256": c.evidence_sha256,
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
        if not resume:
            # A forced rerun replaces the run checkpoint just as it replaces
            # the final artifacts. Do not accumulate duplicate completion
            # entries that make an otherwise idempotent run look different.
            self._checkpoint = {"completed_cnpjs": [], "failed_cnpjs": {}, "updated_at": None}
        done = set(self._checkpoint.get("completed_cnpjs") or []) if resume else set()
        todo = [j for j in ordered if j.cnpj14 not in done]
        if max_companies is not None:
            todo = todo[: max(0, int(max_companies))]

        # Propagate job meta (economic group, razao) into resolver for production path
        job_meta: dict[str, dict[str, Any]] = {}
        for j in ordered:
            meta = dict(j.meta or {})
            if j.razao_social:
                meta.setdefault("razao_social", j.razao_social)
            if j.priority_tier:
                meta.setdefault("priority_tier", j.priority_tier)
            # economic_group_id from explicit field or meta
            eg = meta.get("economic_group_id") or meta.get("grupo_economico_id")
            if eg:
                meta["economic_group_id"] = str(eg)
            job_meta[j.cnpj14] = meta
            # Pre-register group for reuse graph before any resolve
            self.resolver.reuse_graph.register_company(
                j.cnpj14,
                razao_social=j.razao_social,
                economic_group_id=str(eg) if eg else None,
            )
        self.resolver.config.job_meta = job_meta
        self.metrics.fixtures_dir = (
            str(self.resolver.config.fixtures_dir) if self.resolver.config.fixtures_dir else None
        )
        if self.resolver.config.fixtures_dir:
            self.metrics.synthetic_contacts = -1  # signal: fixture mode, not commercial proof

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
        # 1) cheap local/registry seed of reuse graph (no full discovery cascade)
        # 2) full discovery + ownership so SHARED_EXTERNAL sees the cohort graph
        # Skipping cascade on pass1 avoids double network cost (search/crawl once).
        # National batches (large todo): skip pass1 — it can hang for hours on network
        # registry lookups with zero checkpoint progress before any terminal is written.
        prev_ownership = self.resolver.config.apply_ownership
        prev_cascade = self.resolver.config.discovery_cascade
        # A network-enabled shard is still a national drain. Repeating a
        # registry lookup for every row before the real cascade adds no
        # evidence and can delay the first checkpoint by hours.
        skip_pass1 = len(todo) > 200 or (self.resolver.config.allow_network and len(todo) > 20)
        cached = None
        if not skip_pass1:
            self.resolver.config.apply_ownership = False
            self.resolver.config.discovery_cascade = None
            pass1: list[AccountContactResolution] = []
            for job in todo:
                try:
                    res = self._resolve_with_retry(job.cnpj14)
                    if not res.razao_social and job.razao_social:
                        res.razao_social = job.razao_social
                    pass1.append(res)
                    eg = job_meta.get(job.cnpj14, {}).get("economic_group_id")
                    for c in res.candidates:
                        self.resolver.reuse_graph.observe_candidate(
                            res.cnpj14,
                            email=c.email,
                            phone=c.phone_e164 or c.phone_raw,
                            razao_social=res.razao_social,
                            economic_group_id=str(eg) if eg else None,
                        )
                except Exception as exc:  # noqa: BLE001
                    self.metrics.retries += 1
                    self.retry_stats.retries += 1
                    self.retry_stats.last_error = str(exc)
                    self._checkpoint.setdefault("failed_cnpjs", {})[job.cnpj14] = f"pass1:{exc}"

            self.resolver.config.apply_ownership = True
            self.resolver.config.discovery_cascade = prev_cascade
            # Drop pass1 cache entries so pass2 recomputes with discovery + ownership
            if self.resolver.config.cache is not None:
                cached = self.resolver.config.cache
                self.resolver.config.cache = None
            else:
                cached = None
        else:
            # Ensure pass2 uses ownership + cascade as configured
            self.resolver.config.apply_ownership = True
            self.resolver.config.discovery_cascade = prev_cascade

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

            enrollable_contacts = principal_publishable_human_contacts(res)
            likely = [c for c in res.candidates if c.ownership_status == OwnershipStatus.LIKELY_COMPANY_OWNED.value]

            if enrollable_contacts:
                verified_rows.append(row)
                # Flat commercial feed rows (one per enrollable contact)
                for c in enrollable_contacts:
                    warmbly_enrollable.append(
                        {
                            "cnpj14": res.cnpj14,
                            "company_name": res.razao_social,
                            "email": c.email,
                            "phone": c.phone_e164 or c.phone_raw,
                            "role_class": c.role_class,
                            "ownership_status": c.ownership_status,
                            "verification_status": c.verification_status,
                            "confidence": c.confidence,
                            "source_url": c.source.source_url if c.source else None,
                            "source_type": c.source.source_type if c.source else None,
                            "enrollable": True,
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
            # Incremental artifact flush so national drains expose ESR mid-run
            # (full rewrite still happens at end of run).
            if enrollable_contacts:
                feed_dir = self.output_dir / WARMBLY_FEED_DIR
                feed_dir.mkdir(parents=True, exist_ok=True)
                with (feed_dir / "contacts_enrollable.jsonl").open("a", encoding="utf-8") as fh:
                    for c in enrollable_contacts:
                        fh.write(
                            json.dumps(
                                {
                                    "cnpj14": res.cnpj14,
                                    "company_name": res.razao_social,
                                    "email": c.email,
                                    "phone": c.phone_e164 or c.phone_raw,
                                    "role_class": c.role_class,
                                    "ownership_status": c.ownership_status,
                                    "verification_status": c.verification_status,
                                    "confidence": c.confidence,
                                    "source_url": c.source.source_url if c.source else None,
                                    "source_type": c.source.source_type if c.source else None,
                                    "enrollable": True,
                                },
                                ensure_ascii=False,
                            )
                            + "\n"
                        )
            if not res.candidates and not res.rejected_contacts:
                with (self.output_dir / NO_CONTACT).open("a", encoding="utf-8") as fh:
                    fh.write(
                        json.dumps(
                            {
                                "cnpj14": res.cnpj14,
                                "company_name": res.razao_social,
                                "commercial_contact_state": res.commercial_contact_state,
                                "absence_reason": res.absence_reason,
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
            # periodic checkpoint every 10 (national drain needs frequent resume points)
            if len(resolutions) % 10 == 0:
                self._save_checkpoint()
                # mid-run metrics snapshot (overwrite)
                try:
                    snap = self.metrics.as_dict()
                    snap["mid_run"] = True
                    snap["resolutions_so_far"] = len(resolutions)
                    snap["checkpoint_completed"] = len(self._checkpoint.get("completed_cnpjs") or [])
                    (self.output_dir / METRICS_FILENAME).write_text(
                        json.dumps(snap, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8",
                    )
                except Exception as exc:  # noqa: BLE001
                    # Mid-run metrics are best-effort observability only.
                    logger.debug("mid-run metrics snapshot failed: %s", exc)

        if cached is not None:
            self.resolver.config.cache = cached
        self.resolver.config.apply_ownership = prev_ownership

        self._save_checkpoint()
        duration = time.time() - t0

        # Persist graph + registry
        self.resolver.reuse_graph.save(self.output_dir / REUSE_GRAPH_FILENAME)
        self.resolver.third_party_registry.save(self.output_dir / REGISTRY_FILENAME)
        self.metrics.reuse_graph_metrics = self.resolver.reuse_graph.sharing_metrics()
        self.metrics.finalize(duration_s=duration, baseline=self.baseline_metrics)

        # Artifacts
        resolution_dicts = [r.as_dict() for r in resolutions]
        source_attempt_rows: list[dict[str, Any]] = []
        terminal_rows: list[dict[str, Any]] = []
        for resolution in resolutions:
            discovery = resolution.discovery_stats or {}
            attempts = list(discovery.get("source_attempts") or [])
            source_attempt_rows.extend(attempts)
            sources = list(discovery.get("sources_attempted") or [])
            external_blocker = any(a.get("outcome") == "EXTERNAL_BLOCKER" for a in attempts)
            strict_contacts = [c for c in resolution.candidates if is_publishable_human_contact(c)]
            principal_contacts = principal_publishable_human_contacts(resolution)
            ladder_complete = bool(attempts) and sources_cover_required_ladder(sources) and not external_blocker
            terminal = classify_contact_terminal(
                cnpj_raiz=resolution.cnpj14[:8],
                sources_attempted=sources,
                network_discovery=bool(attempts),
                ladder_complete=ladder_complete,
                email_candidates=sum(1 for c in resolution.candidates if c.email),
                email_send_ready=len(strict_contacts),
                external_blocker=("public_source_access_or_document_validation_required" if external_blocker else None),
                retryable_error=external_blocker
                or resolution.investigation_outcome in {"BUDGET_EXHAUSTED", "RETRY_LATER", "ERROR"},
                last_attempt_at=max(
                    (str(a.get("observed_at")) for a in attempts if a.get("observed_at")),
                    default=None,
                ),
                meta={
                    "cnpj14": resolution.cnpj14,
                    "strict_human_recipient_count": len(strict_contacts),
                    "principal_recipient_count": len(principal_contacts),
                    "attempt_evidence_sha256": [
                        str(a.get("evidence_sha256")) for a in attempts if a.get("evidence_sha256")
                    ],
                },
            )
            terminal_rows.append(terminal.as_dict())
        write_jsonl(self.output_dir / FULL_RESOLUTIONS, resolution_dicts)
        write_jsonl(self.output_dir / CONTACTS_VERIFIED, verified_rows)
        write_jsonl(self.output_dir / CONTACTS_REVIEW, review_rows)
        write_jsonl(self.output_dir / CONTACTS_REJECTED, rejected_rows)
        write_jsonl(self.output_dir / ACCOUNTING_REJECTIONS, accounting_rows)
        write_jsonl(self.output_dir / NO_CONTACT, no_contact_rows)
        write_jsonl(self.output_dir / SOURCE_ATTEMPTS_FILENAME, source_attempt_rows)
        write_jsonl(self.output_dir / TERMINALS_FILENAME, terminal_rows)

        feed_dir = self.output_dir / WARMBLY_FEED_DIR
        feed_dir.mkdir(parents=True, exist_ok=True)
        write_jsonl(feed_dir / "contacts.jsonl", warmbly_rows)
        write_jsonl(feed_dir / "contacts_enrollable.jsonl", warmbly_enrollable)

        # Human review package — never auto-approves
        from scripts.confenge_contact_resolution.human_review import write_human_review_package

        human_status = write_human_review_package(self.output_dir, resolution_dicts, n_each=20)

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
            "human_review": human_status,
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
                "human_review": "human-review/",
                "source_attempts": SOURCE_ATTEMPTS_FILENAME,
                "contact_terminals": TERMINALS_FILENAME,
            },
            "finished_at": _now(),
            "ok": True,
        }
        (self.output_dir / MANIFEST_FILENAME).write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return manifest

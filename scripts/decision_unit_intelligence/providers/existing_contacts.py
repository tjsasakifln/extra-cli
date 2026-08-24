"""Tier 0 reconciliation of already-produced, account-linked contact artifacts.

The batch contract records every input path and content hash at enqueue time.
Workers verify those hashes before reading a contact, so an operator cannot
silently replace the historical evidence underneath an in-flight cohort.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.decision_unit_intelligence.controlled_email import (
    dedupe_feed_contacts_by_mailbox,
    route_from_feed_contact,
)
from scripts.decision_unit_intelligence.models import (
    ChannelObservation,
    EpistemicClass,
    FieldEvidence,
    SearchAttempt,
    stable_id,
)
from scripts.decision_unit_intelligence.providers.base import (
    InvestigationContext,
    ProviderResult,
)


@dataclass(frozen=True)
class ContactSeedInput:
    path: str
    sha256: str
    size_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest_contact_seed_inputs(paths: list[str] | tuple[str, ...]) -> list[dict[str, Any]]:
    """Resolve and hash explicit bridge JSONL inputs for a durable cohort."""
    manifested: list[ContactSeedInput] = []
    seen: set[str] = set()
    for raw in paths:
        path = Path(raw).expanduser().resolve()
        key = str(path)
        if key in seen:
            continue
        if not path.is_file():
            raise ValueError(f"existing contact seed is not a file: {path}")
        seen.add(key)
        manifested.append(
            ContactSeedInput(
                path=key,
                sha256=_sha256_file(path),
                size_bytes=path.stat().st_size,
            )
        )
    manifested.sort(key=lambda item: (item.sha256, item.path))
    return [item.to_dict() for item in manifested]


def bind_contact_seeds_to_input_version(
    input_evidence_version: str,
    seed_inputs: list[dict[str, Any]],
) -> str:
    """Bind historical contact evidence without making host paths authoritative."""
    if not seed_inputs:
        return input_evidence_version
    content_hashes = sorted(str(item.get("sha256") or "") for item in seed_inputs)
    payload = json.dumps(
        {
            "input_evidence_version": input_evidence_version,
            "contact_seed_hashes": content_hashes,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"{input_evidence_version}.contacts-{digest}"


_INDEX_CACHE: dict[
    tuple[tuple[str, str], ...],
    dict[str, dict[str, Any]],
] = {}


def _canonical_cnpj(value: Any) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return digits[:14] if len(digits) >= 14 else ""


def _load_verified_index(seed_inputs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    cache_key = tuple(
        sorted(
            (str(item.get("path") or ""), str(item.get("sha256") or ""))
            for item in seed_inputs
        )
    )
    if cache_key in _INDEX_CACHE:
        return _INDEX_CACHE[cache_key]

    by_cnpj: dict[str, dict[str, Any]] = {}
    for raw in seed_inputs:
        path = Path(str(raw.get("path") or ""))
        expected = str(raw.get("sha256") or "")
        if not path.is_file():
            raise ValueError(f"CONTACT_SEED_FILE_MISSING:{path}")
        observed = _sha256_file(path)
        if not expected or observed != expected:
            raise ValueError(f"CONTACT_SEED_HASH_MISMATCH:{path}")
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                text = line.strip()
                if not text or text.startswith("#"):
                    continue
                try:
                    row = json.loads(text)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"CONTACT_SEED_JSON_INVALID:{path}:{line_number}") from exc
                if not isinstance(row, dict):
                    raise ValueError(f"CONTACT_SEED_ROW_NOT_OBJECT:{path}:{line_number}")
                cnpj = _canonical_cnpj(
                    row.get("cnpj14")
                    or row.get("canonical_account_id")
                    or row.get("cnpj")
                )
                if not cnpj:
                    continue
                existing = by_cnpj.setdefault(
                    cnpj,
                    {"cnpj14": cnpj, "contacts": [], "official_domain": ""},
                )
                contacts = [
                    dict(item)
                    for item in (row.get("contacts") or [])
                    if isinstance(item, dict)
                ]
                for contact in contacts:
                    contact.setdefault("contact_seed_sha256", expected)
                    contact.setdefault("contact_seed_path", str(path))
                existing["contacts"] = dedupe_feed_contacts_by_mailbox(
                    [*(existing.get("contacts") or []), *contacts]
                )
                if not existing.get("official_domain") and row.get("official_domain"):
                    existing["official_domain"] = str(row["official_domain"])
    _INDEX_CACHE[cache_key] = by_cnpj
    return by_cnpj


def _evidence_for_contact(
    contact: dict[str, Any],
    *,
    cnpj: str,
    email: str,
) -> FieldEvidence | None:
    raw_provenance = contact.get("provenance")
    provenance: dict[str, Any] = raw_provenance if isinstance(raw_provenance, dict) else {}
    source_type = str(
        contact.get("source")
        or contact.get("source_type")
        or provenance.get("source_type")
        or "existing_contact_artifact"
    )
    source_url = str(contact.get("source_url") or provenance.get("source_url") or "") or None
    document_id = str(
        contact.get("source_document")
        or provenance.get("source_document")
        or ""
    ) or None
    source_id = str(contact.get("source_contact_id") or "") or None
    if not (source_url or document_id or source_id):
        return None
    evidence_id = stable_id(
        "existing-contact",
        cnpj,
        email,
        source_url or document_id or source_id or "",
    )
    return FieldEvidence(
        evidence_id=evidence_id,
        field="company_email",
        value=email,
        epistemic_class=EpistemicClass.OBSERVED,
        source_type=source_type,
        source_url=source_url,
        source_id=source_id,
        document_id=document_id,
        document_sha256=str(contact.get("evidence_sha256") or "") or None,
        evidence_snippet=email,
        observed_at=str(contact.get("observed_at") or contact.get("source_date") or "") or None,
        extraction_method="reconciled_existing_contact_artifact",
        extractor_version="existing-contacts.v1",
        extra={
            "contact_seed_sha256": contact.get("contact_seed_sha256"),
            "source_date_semantics": contact.get("source_date_semantics"),
        },
    )


class ExistingContactsProvider:
    """Replay already-observed contacts before spending on public discovery."""

    provider_id = "existing_contacts"
    tier = 0

    def __init__(self, seed_inputs: list[dict[str, Any]] | None = None) -> None:
        self.seed_inputs = [dict(item) for item in (seed_inputs or [])]

    def collect(self, context: InvestigationContext) -> ProviderResult:
        cnpj = _canonical_cnpj(context.cnpj)
        if not self.seed_inputs:
            return ProviderResult(
                attempts=[
                    SearchAttempt(
                        attempt_id=stable_id("att", self.provider_id, cnpj, "not-configured"),
                        company_entity_id=cnpj,
                        tier=self.tier,
                        provider_id=self.provider_id,
                        source="versioned_contact_seed",
                        status="skipped",
                        reason="contact_seed_not_configured",
                    )
                ],
                terminal="skipped",
            )
        index = _load_verified_index(self.seed_inputs)
        row = index.get(cnpj)
        if not row:
            return ProviderResult(
                attempts=[
                    SearchAttempt(
                        attempt_id=stable_id("att", self.provider_id, cnpj, "miss"),
                        company_entity_id=cnpj,
                        tier=self.tier,
                        provider_id=self.provider_id,
                        source="versioned_contact_seed",
                        status="miss",
                        reason="cnpj_not_in_contact_seed",
                    )
                ],
                terminal="miss",
            )

        official_domain = str(row.get("official_domain") or "").strip()
        channels: list[ChannelObservation] = []
        evidence: list[FieldEvidence] = []
        for contact in row.get("contacts") or []:
            if not isinstance(contact, dict):
                continue
            email = str(contact.get("email") or contact.get("value") or "").strip().lower()
            if not email or "@" not in email:
                continue
            route = route_from_feed_contact(
                contact,
                account_id=cnpj,
                official_domain=official_domain or None,
            )
            item_evidence = _evidence_for_contact(contact, cnpj=cnpj, email=email)
            if item_evidence:
                evidence.append(item_evidence)
            extra = dict(route.extra or {})
            extra.update(
                {
                    "contact_seed_sha256": contact.get("contact_seed_sha256"),
                    "mailbox_company_evidence": contact.get("mailbox_company_evidence")
                    or extra.get("mailbox_company_evidence"),
                    "mailbox_department_evidence": contact.get("mailbox_department_evidence")
                    or extra.get("mailbox_department_evidence"),
                    "mailbox_person_evidence": contact.get("mailbox_person_evidence")
                    or extra.get("mailbox_person_evidence"),
                }
            )
            channels.append(
                ChannelObservation(
                    observation_id=stable_id("seed-channel", cnpj, email, route.source_url or ""),
                    company_entity_id=cnpj,
                    channel_type=route.channel_type,
                    channel_value=email,
                    person_name=str(contact.get("name") or "").strip() or None,
                    target_role=str(contact.get("mailbox_department") or contact.get("role") or "").strip()
                    or None,
                    source_type=route.source_type or "existing_contact_artifact",
                    source_url=route.source_url,
                    document_id=(item_evidence.document_id if item_evidence else None),
                    observed_at=route.observed_at,
                    epistemic_class=route.epistemic_class,
                    ownership=route.ownership,
                    evidence_id=(item_evidence.evidence_id if item_evidence else None),
                    extra=extra,
                )
            )
        attempt = SearchAttempt(
            attempt_id=stable_id("att", self.provider_id, cnpj, "hit" if channels else "empty"),
            company_entity_id=cnpj,
            tier=self.tier,
            provider_id=self.provider_id,
            source="versioned_contact_seed",
            status="hit" if channels else "miss",
            reason=None if channels else "seed_row_has_no_email",
            documents_checked=len(self.seed_inputs),
            extra={"contact_count": len(channels)},
        )
        return ProviderResult(
            channels=channels,
            evidence=evidence,
            attempts=[attempt],
            terminal=attempt.status,
            company_site=f"https://{official_domain}" if official_domain else None,
            extra={
                "domain_resolution": {
                    "canonical_domain": official_domain,
                    "confidence": "RECONCILED_EXISTING_EVIDENCE",
                }
                if official_domain
                else {},
            },
        )

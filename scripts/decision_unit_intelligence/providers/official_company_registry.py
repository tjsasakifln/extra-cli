"""Tier 1 lookup of account-linked public cadastral contact fields.

Only the locally activated Receita Federal release is consulted. A missing
release is recorded as a provider failure so a completed no-route job cannot be
mistaken for a complete waterfall, while later public sources are still free to
produce a usable route.
"""

from __future__ import annotations

from collections.abc import Callable

from scripts.company_registry.lookup import lookup_cnpj
from scripts.company_registry.models import OfficialCompanyRecord, OfficialMatchStatus
from scripts.decision_unit_intelligence.controlled_email import is_freemail
from scripts.decision_unit_intelligence.models import (
    ChannelObservation,
    ChannelType,
    EpistemicClass,
    FieldEvidence,
    OwnershipStatus,
    SearchAttempt,
    normalize_cnpj,
    stable_id,
)
from scripts.decision_unit_intelligence.providers.base import InvestigationContext, ProviderResult

Lookup = Callable[[str], OfficialCompanyRecord]


class OfficialCompanyRegistryProvider:
    """Read exact-CNPJ public e-mail/phone without inventing a person."""

    provider_id = "official_company_registry"
    tier = 1

    def __init__(self, lookup: Lookup = lookup_cnpj) -> None:
        self._lookup = lookup

    def collect(self, context: InvestigationContext) -> ProviderResult:
        cnpj = normalize_cnpj(context.cnpj)
        record = self._lookup(cnpj)
        status = str(record.official_match_status)
        common = {
            "official_match_status": status,
            "official_authority": record.official_authority,
            "official_release_id": record.official_release_id,
            "registry_cnpj14": record.cnpj,
        }
        if status != OfficialMatchStatus.MATCHED.value:
            unavailable = status == OfficialMatchStatus.OFFICIAL_REGISTRY_UNAVAILABLE.value
            return ProviderResult(
                attempts=[
                    SearchAttempt(
                        attempt_id=stable_id("att", self.provider_id, cnpj, status),
                        company_entity_id=cnpj,
                        tier=self.tier,
                        provider_id=self.provider_id,
                        source="rfb_public_cadastral",
                        status="skipped" if unavailable else "miss",
                        reason=status,
                        extra={**common, **({"failures": [status]} if unavailable else {})},
                    )
                ],
                terminal="blocked" if unavailable else "miss",
            )

        observed_at = record.fetched_from_local_registry_at
        provenance = dict(record.source_provenance or {})
        source_id = str(record.official_release_id or provenance.get("release_id") or "") or None
        channels: list[ChannelObservation] = []
        evidence: list[FieldEvidence] = []

        email = str(record.email or "").strip().lower()
        registry_domain = email.rsplit("@", 1)[-1] if "@" in email and not is_freemail(email) else ""
        if email:
            evidence_id = stable_id("rfb-email", cnpj, email, source_id or "")
            evidence.append(
                FieldEvidence(
                    evidence_id=evidence_id,
                    field="company_email",
                    value=email,
                    epistemic_class=EpistemicClass.OBSERVED,
                    source_type="company_registry",
                    source_id=source_id,
                    document_id=source_id,
                    evidence_snippet=email,
                    observed_at=observed_at,
                    extraction_method="exact_cnpj_public_cadastre",
                    extractor_version="official-company-registry.v1",
                    extra={**common, "source_provenance": provenance},
                )
            )
            channels.append(
                ChannelObservation(
                    observation_id=stable_id("rfb-email-channel", cnpj, email, source_id or ""),
                    company_entity_id=cnpj,
                    channel_type=ChannelType.GENERIC_CORPORATE_EMAIL,
                    channel_value=email,
                    source_type="company_registry",
                    document_id=source_id,
                    observed_at=observed_at,
                    epistemic_class=EpistemicClass.OBSERVED,
                    ownership=OwnershipStatus.COMPANY_OWNED,
                    evidence_id=evidence_id,
                    extra={
                        **common,
                        "source_provenance": provenance,
                        "company_associated": True,
                        "mailbox_company_evidence": "OBSERVED",
                        "mailbox_person_evidence": "UNKNOWN",
                        **({"official_domain": registry_domain} if registry_domain else {}),
                    },
                )
            )

        phone = str(record.phone or "").strip()
        if phone:
            phone_evidence_id = stable_id("rfb-phone", cnpj, phone, source_id or "")
            evidence.append(
                FieldEvidence(
                    evidence_id=phone_evidence_id,
                    field="company_phone",
                    value=phone,
                    epistemic_class=EpistemicClass.OBSERVED,
                    source_type="company_registry",
                    source_id=source_id,
                    document_id=source_id,
                    evidence_snippet=phone,
                    observed_at=observed_at,
                    extraction_method="exact_cnpj_public_cadastre",
                    extractor_version="official-company-registry.v1",
                    extra={**common, "source_provenance": provenance},
                )
            )
            channels.append(
                ChannelObservation(
                    observation_id=stable_id("rfb-phone-channel", cnpj, phone, source_id or ""),
                    company_entity_id=cnpj,
                    channel_type=ChannelType.COMPANY_SWITCHBOARD,
                    channel_value=phone,
                    source_type="company_registry",
                    document_id=source_id,
                    observed_at=observed_at,
                    epistemic_class=EpistemicClass.OBSERVED,
                    ownership=OwnershipStatus.COMPANY_OWNED,
                    evidence_id=phone_evidence_id,
                    extra={**common, "source_provenance": provenance, "person_owns_phone": False},
                )
            )

        attempt_status = "hit" if channels else "miss"
        return ProviderResult(
            channels=channels,
            evidence=evidence,
            attempts=[
                SearchAttempt(
                    attempt_id=stable_id("att", self.provider_id, cnpj, attempt_status),
                    company_entity_id=cnpj,
                    tier=self.tier,
                    provider_id=self.provider_id,
                    source="rfb_public_cadastral",
                    status=attempt_status,
                    reason=None if channels else "MATCHED_WITHOUT_PUBLIC_CONTACT",
                    documents_checked=1,
                    extra={**common, "contact_fields_found": len(channels)},
                )
            ],
            terminal=attempt_status,
            legal_name=record.legal_name,
            extra={
                "official_company_registry": {**common, "source_provenance": provenance},
                **(
                    {
                        "domain_resolution": {
                            "canonical_domain": registry_domain,
                            "confidence": "EXACT_CNPJ_REGISTRY_EMAIL_DOMAIN",
                        }
                    }
                    if registry_domain
                    else {}
                ),
            },
        )

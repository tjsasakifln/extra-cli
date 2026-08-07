"""Dedupe and conflict merge for raw observations → candidates."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime

from scripts.confenge_contact_resolution.email_policy import assess_email
from scripts.confenge_contact_resolution.freshness import freshness_score
from scripts.confenge_contact_resolution.models import (
    ContactCandidate,
    RawObservation,
    SourceProvenance,
    VerificationStatus,
)
from scripts.confenge_contact_resolution.phone_policy import assess_phone, default_whatsapp_block
from scripts.confenge_contact_resolution.role_map import map_role_class


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _norm_name(n: str | None) -> str:
    if not n:
        return ""
    return re.sub(r"\s+", " ", n.strip().lower())


def _dedupe_key(obs: RawObservation, email: str | None, phone_e164: str | None) -> str:
    """Key for merging same person/channel across sources."""
    name = _norm_name(obs.name)
    if email:
        return f"email:{email}"
    if phone_e164:
        return f"phone:{phone_e164}"
    if name:
        return f"name:{name}|cargo:{_norm_name(obs.cargo)}"
    # unique fallback per observation fingerprint
    raw = f"{obs.adapter}|{obs.email}|{obs.phone_raw}|{obs.name}|{obs.source.source_url}"
    return "anon:" + hashlib.sha256(raw.encode()).hexdigest()[:12]


def _source_priority(source_type: str | None) -> int:
    order = {
        "human_outcome": 100,
        "registry": 80,
        "contact_page": 60,
        "site": 50,
        "public_docs": 40,
        "web_search": 20,
        "unknown": 0,
    }
    return order.get(source_type or "unknown", 0)


def observations_to_candidates(
    observations: list[RawObservation],
    *,
    cnpj14: str,
    account_key: str | None = None,
    check_mx: bool = False,
    mx_resolver=None,
) -> list[ContactCandidate]:
    """Merge raw observations into ContactCandidate list (pre-ranking)."""
    buckets: dict[str, list[RawObservation]] = {}
    for obs in observations:
        email_a = assess_email(
            obs.email,
            pattern_guessed=obs.pattern_guessed_email,
            check_mx_flag=check_mx,
            mx_resolver=mx_resolver,
        )
        phone_a = assess_phone(obs.phone_raw)
        key = _dedupe_key(obs, email_a.email, phone_a.phone_e164)
        buckets.setdefault(key, []).append(obs)

    candidates: list[ContactCandidate] = []
    for key, group in buckets.items():
        # Prefer higher-priority sources; DNC/bounce from any source dominate
        group_sorted = sorted(
            group,
            key=lambda o: _source_priority(o.source.source_type if o.source else None),
            reverse=True,
        )
        primary = group_sorted[0]
        dnc = any(o.dnc for o in group)
        bounce = any(o.bounce for o in group)
        dnc_reason = next((o.dnc_reason for o in group if o.dnc_reason), None)

        # Conflict: multiple different emails for same name key → keep all as separate
        # (already bucketed by email/phone). For same key, prefer primary values.
        email_a = assess_email(
            primary.email,
            pattern_guessed=primary.pattern_guessed_email,
            check_mx_flag=check_mx,
            mx_resolver=mx_resolver,
        )
        phone_a = assess_phone(primary.phone_raw)

        # If primary lacks email but another in group has observed email, promote
        if not email_a.email:
            for o in group_sorted[1:]:
                ea = assess_email(o.email, pattern_guessed=o.pattern_guessed_email)
                if ea.email and ea.verification_status == VerificationStatus.OBSERVED.value:
                    email_a = ea
                    break
        if not phone_a.phone_e164:
            for o in group_sorted[1:]:
                pa = assess_phone(o.phone_raw)
                if pa.valid:
                    phone_a = pa
                    break

        # Name/cargo: prefer non-empty from highest priority
        name = next((o.name for o in group_sorted if o.name), None)
        cargo = next((o.cargo for o in group_sorted if o.cargo), None)
        role = map_role_class(cargo, name_hint=name)

        # Source date: newest known for freshness
        dates = [o.source.source_date for o in group if o.source and o.source.source_date]
        source_date = max(dates) if dates else (primary.source.source_date if primary.source else None)
        fresh, age = freshness_score(source_date)

        conf = 0.15  # base for existence
        conf += email_a.confidence_delta
        conf += phone_a.confidence_delta
        conf *= fresh
        if dnc or bounce:
            conf = 0.0
        conf = round(max(0.0, min(1.0, conf)), 4)

        wa_status = primary.whatsapp_consent
        wa_prov = primary.whatsapp_consent_provenance
        for o in group:
            if o.whatsapp_consent == "OPTED_IN" and o.whatsapp_consent_provenance:
                wa_status = "OPTED_IN"
                wa_prov = o.whatsapp_consent_provenance
                break

        site = next((o.site for o in group_sorted if o.site), None)
        linkedin = next((o.linkedin_public for o in group_sorted if o.linkedin_public), None)

        # Conflict note: conflicting emails across same name (edge) already split by key
        limitations: list[str] = list(email_a.notes)
        if len({(o.email or "").lower() for o in group if o.email}) > 1:
            limitations.append("conflicting_emails_merged_by_channel_key")
        if len({digits for o in group if (digits := re.sub(r"\D", "", o.phone_raw or ""))}) > 1:
            limitations.append("conflicting_phones_prefer_primary_source")

        cid = hashlib.sha256(f"{cnpj14}|{key}".encode()).hexdigest()[:16]
        src = primary.source or SourceProvenance(source_type=primary.adapter)
        if not src.observed_at:
            src = SourceProvenance(
                source_type=src.source_type,
                source_url=src.source_url,
                source_document=src.source_document,
                source_date=src.source_date,
                observed_at=_now_iso(),
                notes=src.notes,
            )

        epistemic = primary.epistemic_class
        if email_a.verification_status == VerificationStatus.CANDIDATE_UNVERIFIED.value:
            epistemic = "INFERRED"

        cand = ContactCandidate(
            candidate_id=cid,
            cnpj14=cnpj14,
            account_key=account_key or cnpj14,
            name=name,
            cargo=cargo,
            role_class=role,
            email=email_a.email,
            email_display=email_a.email_display,
            phone_raw=phone_a.phone_raw,
            phone_e164=phone_a.phone_e164,
            phone_type=phone_a.phone_type,
            site=site,
            linkedin_public=linkedin,
            source=src,
            verification_status=email_a.verification_status
            if email_a.email
            else (
                VerificationStatus.OBSERVED.value
                if phone_a.valid
                else VerificationStatus.NOT_AVAILABLE.value
            ),
            email_layers=email_a.layers,
            confidence=conf,
            freshness=fresh,
            freshness_days=age,
            dnc=dnc,
            bounce=bounce,
            dnc_reason=dnc_reason,
            whatsapp=default_whatsapp_block(
                phone_a.phone_e164,
                consent_status=wa_status,
                consent_provenance=wa_prov,
            ),
            enrollable=email_a.enrollable and not dnc and not bounce,
            epistemic_class=epistemic,
            limitations=limitations,
        )
        candidates.append(cand)

    return candidates

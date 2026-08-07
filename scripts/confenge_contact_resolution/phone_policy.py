"""Brazilian phone normalization to E.164 and mobile/landline typing.

Public phone does NOT imply WhatsApp opt-in — consent is handled separately.
No unauthorized WhatsApp account existence checks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from scripts.confenge_contact_resolution.models import PhoneType, WhatsAppBlock, WhatsAppConsent


@dataclass(frozen=True)
class PhoneAssessment:
    phone_raw: str | None
    phone_e164: str | None
    phone_type: str
    valid: bool
    confidence_delta: float
    notes: list[str]


def digits_only(raw: str | None) -> str:
    return re.sub(r"\D", "", raw or "")


def normalize_br_e164(raw: str | None) -> str | None:
    """Normalize BR phone to +55… E.164.

    Accepts:
      - 10 digits (landline with DDD)
      - 11 digits (mobile with 9th digit + DDD)
      - 12–13 digits starting with 55
      - already-prefixed +55…
    Returns None if invalid.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    d = digits_only(s)
    if not d:
        return None

    # Strip leading zeros occasionally seen in exports
    d = d.lstrip("0") or d

    if d.startswith("55") and len(d) in {12, 13}:
        national = d[2:]
    elif len(d) in {10, 11}:
        national = d
    else:
        return None

    if len(national) not in {10, 11}:
        return None
    ddd = national[:2]
    subscriber = national[2:]
    if not (10 <= int(ddd) <= 99):
        return None
    if len(subscriber) == 9 and not subscriber.startswith("9"):
        # 9-digit subscriber in BR mobile must start with 9
        return None
    if len(subscriber) == 8 and subscriber[0] in {"6", "7", "8", "9"}:
        # Ambiguous legacy; still accept as landline/unknown later
        pass
    if not subscriber.isdigit() or not ddd.isdigit():
        return None
    return f"+55{ddd}{subscriber}"


def classify_phone_type(e164: str | None) -> str:
    if not e164 or not e164.startswith("+55"):
        return PhoneType.UNKNOWN.value
    national = e164[3:]
    if len(national) == 11 and national[2] == "9":
        return PhoneType.MOBILE.value
    if len(national) == 10:
        return PhoneType.LANDLINE.value
    return PhoneType.UNKNOWN.value


def assess_phone(raw: str | None) -> PhoneAssessment:
    display = (str(raw).strip() if raw is not None else None) or None
    if not display:
        return PhoneAssessment(
            phone_raw=None,
            phone_e164=None,
            phone_type=PhoneType.UNKNOWN.value,
            valid=False,
            confidence_delta=0.0,
            notes=["phone_absent"],
        )
    e164 = normalize_br_e164(display)
    if not e164:
        return PhoneAssessment(
            phone_raw=display,
            phone_e164=None,
            phone_type=PhoneType.UNKNOWN.value,
            valid=False,
            confidence_delta=0.0,
            notes=["phone_invalid"],
        )
    ptype = classify_phone_type(e164)
    delta = 0.25 if ptype == PhoneType.MOBILE.value else 0.18 if ptype == PhoneType.LANDLINE.value else 0.1
    return PhoneAssessment(
        phone_raw=display,
        phone_e164=e164,
        phone_type=ptype,
        valid=True,
        confidence_delta=delta,
        notes=[f"phone_type_{ptype}"],
    )


def default_whatsapp_block(
    e164: str | None,
    *,
    consent_status: str | None = None,
    consent_provenance: str | None = None,
) -> WhatsAppBlock:
    """Public phone → UNKNOWN/NO_OPT_IN unless explicit verifiable provenance."""
    status = (consent_status or "").strip().upper() or WhatsAppConsent.UNKNOWN.value
    if status == WhatsAppConsent.OPTED_IN.value:
        if not consent_provenance or not str(consent_provenance).strip():
            # Fail closed: cannot claim opt-in without provenance
            status = WhatsAppConsent.NO_OPT_IN.value
            consent_provenance = None
    elif status not in {w.value for w in WhatsAppConsent}:
        status = WhatsAppConsent.UNKNOWN.value

    if status == WhatsAppConsent.OPTED_IN.value:
        return WhatsAppBlock(
            consent_status=WhatsAppConsent.OPTED_IN.value,
            consent_provenance=consent_provenance,
            e164=e164,
        )
    # Prefer NO_OPT_IN when we have a phone but no consent; UNKNOWN when no phone
    if e164 and status == WhatsAppConsent.UNKNOWN.value:
        status = WhatsAppConsent.NO_OPT_IN.value
    return WhatsAppBlock(
        consent_status=status,
        consent_provenance=consent_provenance if status == WhatsAppConsent.OPTED_IN.value else None,
        e164=e164,
    )

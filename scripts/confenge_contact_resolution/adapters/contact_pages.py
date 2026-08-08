"""Public contact/team pages adapter (fixture or injected extracts)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from scripts.confenge_contact_resolution.adapters.base import AdapterContext
from scripts.confenge_contact_resolution.models import RawObservation, SourceProvenance


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class ContactPageAdapter:
    name = "contact_page"

    def collect(self, ctx: AdapterContext) -> list[RawObservation]:
        pages: list[dict[str, Any]] = list(ctx.contact_pages or [])
        if ctx.fixtures_dir:
            p = ctx.fixtures_dir / f"{ctx.cnpj14}_contact_page.json"
            if p.is_file():
                import json

                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    pages.extend(data)
                elif isinstance(data, dict):
                    pages.append(data)

        out: list[RawObservation] = []
        for page in pages:
            people = page.get("people") or page.get("contacts") or []
            if not people and (page.get("email") or page.get("phone")):
                people = [page]
            for person in people:
                email = person.get("email")
                phone = person.get("phone") or person.get("telefone")
                name = person.get("name") or person.get("nome")
                cargo = person.get("cargo") or person.get("role") or person.get("funcao")
                if not email and not phone and not name:
                    continue
                # Human outcomes / DNC may be attached on contact pages feed
                out.append(
                    RawObservation(
                        adapter="contact_page",
                        cnpj14=ctx.cnpj14,
                        name=str(name).strip() if name else None,
                        cargo=str(cargo).strip() if cargo else None,
                        email=str(email).strip() if email else None,
                        phone_raw=str(phone).strip() if phone else None,
                        site=page.get("site"),
                        linkedin_public=person.get("linkedin") or person.get("linkedin_public"),
                        source=SourceProvenance(
                            source_type="contact_page",
                            source_url=page.get("url") or person.get("url"),
                            source_document=page.get("document"),
                            source_date=str(page.get("source_date") or "")[:10] or None,
                            observed_at=_now(),
                            notes="Public team/contact page",
                        ),
                        pattern_guessed_email=bool(person.get("pattern_guessed_email")),
                        dnc=bool(person.get("dnc")),
                        bounce=bool(person.get("bounce")),
                        dnc_reason=person.get("dnc_reason"),
                        whatsapp_consent=str(person.get("whatsapp_consent") or "UNKNOWN"),
                        whatsapp_consent_provenance=person.get("whatsapp_consent_provenance"),
                        epistemic_class="OBSERVED_PUBLIC",
                    )
                )
        # Also ingest human outcomes (DNC etc.) as dominant signals
        for ho in ctx.human_outcomes or []:
            if _digits_match(ho.get("cnpj14") or ho.get("cnpj"), ctx.cnpj14) is False:
                continue
            out.append(
                RawObservation(
                    adapter="human_outcome",
                    cnpj14=ctx.cnpj14,
                    name=ho.get("name"),
                    cargo=ho.get("cargo"),
                    email=ho.get("email"),
                    phone_raw=ho.get("phone") or ho.get("telefone"),
                    source=SourceProvenance(
                        source_type="human_outcome",
                        source_url=ho.get("source_url"),
                        source_document=ho.get("outcome_id"),
                        source_date=str(ho.get("source_date") or "")[:10] or None,
                        observed_at=_now(),
                        notes="Human decision/outcome memory — dominant when DNC/bounce",
                    ),
                    dnc=bool(ho.get("dnc") or str(ho.get("state") or "").upper() == "DO_NOT_CONTACT"),
                    bounce=bool(ho.get("bounce")),
                    dnc_reason=ho.get("dnc_reason") or ho.get("reason"),
                    whatsapp_consent=str(ho.get("whatsapp_consent") or "UNKNOWN"),
                    whatsapp_consent_provenance=ho.get("whatsapp_consent_provenance"),
                    epistemic_class="HUMAN_OUTCOME",
                )
            )
        return out


def _digits_match(a: str | None, b: str | None) -> bool | None:
    import re

    if a is None or b is None:
        return None
    da, db = re.sub(r"\D", "", a), re.sub(r"\D", "", b)
    if not da or not db:
        return None
    return da == db

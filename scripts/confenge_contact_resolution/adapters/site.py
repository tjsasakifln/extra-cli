"""Institutional site adapter — consumes pre-fetched or fixture page extracts.

Does not perform fragile live scraping by default. Tests inject site_pages.
"""

from __future__ import annotations

from typing import Any

from scripts.confenge_contact_resolution.adapters.base import AdapterContext
from scripts.confenge_contact_resolution.models import RawObservation, SourceProvenance


def _obs_from_page(cnpj14: str, page: dict[str, Any]) -> list[RawObservation]:
    out: list[RawObservation] = []
    contacts = page.get("contacts") or []
    if not contacts and (page.get("email") or page.get("phone")):
        contacts = [page]
    source_url = page.get("url") or page.get("source_url")
    source_published_at = page.get("source_published_at") or page.get("published_at") or page.get("source_date")
    observed_at = page.get("observed_at")
    verified_at = page.get("verified_at")
    for c in contacts:
        email = c.get("email")
        phone = c.get("phone") or c.get("telefone")
        name = c.get("name") or c.get("nome")
        cargo = c.get("cargo") or c.get("role") or c.get("funcao")
        if not email and not phone and not name:
            continue
        out.append(
            RawObservation(
                adapter="site",
                cnpj14=cnpj14,
                name=str(name).strip() if name else None,
                cargo=str(cargo).strip() if cargo else None,
                email=str(email).strip() if email else None,
                phone_raw=str(phone).strip() if phone else None,
                site=source_url or page.get("site"),
                linkedin_public=c.get("linkedin") or c.get("linkedin_public"),
                source=SourceProvenance(
                    source_type="site",
                    source_url=source_url,
                    source_document=page.get("document"),
                    source_date=str(source_published_at)[:10] if source_published_at else None,
                    source_published_at=str(source_published_at) if source_published_at else None,
                    observed_at=str(observed_at) if observed_at else None,
                    verified_at=str(verified_at) if verified_at else None,
                    notes="Institutional site extract (no private social scrape)",
                ),
                pattern_guessed_email=bool(c.get("pattern_guessed_email")),
                epistemic_class="INFERRED" if c.get("pattern_guessed_email") else "OBSERVED_PUBLIC",
            )
        )
    return out


class SiteAdapter:
    name = "site"

    def collect(self, ctx: AdapterContext) -> list[RawObservation]:
        pages = list(ctx.site_pages or [])
        if ctx.fixtures_dir:
            p = ctx.fixtures_dir / f"{ctx.cnpj14}_site.json"
            if p.is_file():
                import json

                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    pages.extend(data)
                elif isinstance(data, dict):
                    pages.append(data)
        out: list[RawObservation] = []
        for page in pages:
            out.extend(_obs_from_page(ctx.cnpj14, page))
        return out

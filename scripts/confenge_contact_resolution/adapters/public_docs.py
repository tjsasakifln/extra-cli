"""Already-ingested public contract/licitação documents adapter.

Reads injected document contact extracts (from datalake pipelines), never
re-scrapes portals in this module.
"""

from __future__ import annotations

from typing import Any

from scripts.confenge_contact_resolution.adapters.base import AdapterContext
from scripts.confenge_contact_resolution.models import RawObservation, SourceProvenance


class PublicDocsAdapter:
    name = "public_docs"

    def collect(self, ctx: AdapterContext) -> list[RawObservation]:
        docs: list[dict[str, Any]] = list(ctx.public_docs or [])
        if ctx.fixtures_dir:
            p = ctx.fixtures_dir / f"{ctx.cnpj14}_public_docs.json"
            if p.is_file():
                import json

                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    docs.extend(data)
                elif isinstance(data, dict):
                    docs.append(data)

        out: list[RawObservation] = []
        for doc in docs:
            email = doc.get("email")
            phone = doc.get("phone") or doc.get("telefone")
            name = doc.get("name") or doc.get("nome") or doc.get("representante")
            cargo = doc.get("cargo") or doc.get("funcao")
            published_at = doc.get("source_published_at") or doc.get("source_date") or doc.get("document_date")
            if not email and not phone and not name:
                continue
            out.append(
                RawObservation(
                    adapter="public_docs",
                    cnpj14=ctx.cnpj14,
                    name=str(name).strip() if name else None,
                    cargo=str(cargo).strip() if cargo else None,
                    email=str(email).strip() if email else None,
                    phone_raw=str(phone).strip() if phone else None,
                    source=SourceProvenance(
                        source_type="public_docs",
                        source_url=doc.get("url") or doc.get("source_url"),
                        source_document=doc.get("document_id") or doc.get("document"),
                        source_date=str(published_at)[:10] if published_at else None,
                        source_published_at=str(published_at) if published_at else None,
                        observed_at=str(doc.get("observed_at")) if doc.get("observed_at") else None,
                        verified_at=str(doc.get("verified_at")) if doc.get("verified_at") else None,
                        notes="From already-ingested public contract/licitação materials",
                    ),
                    pattern_guessed_email=bool(doc.get("pattern_guessed_email")),
                    epistemic_class="OBSERVED_PUBLIC",
                    extra={
                        "doc_type": doc.get("doc_type"),
                        "evidence_strength": doc.get("evidence_strength"),
                        "document_cnpj14": doc.get("cnpj14"),
                    },
                )
            )
        return out

"""Response formatting with mandatory provenance fields."""

from __future__ import annotations

import json
from typing import Any

DISCLAIMER = (
    "Evidência documental do acervo EXTRA EMPREITEIRA LTDA. "
    "Não constitui parecer jurídico de habilitação. "
    "Distingue evidência documental, inferência e necessidade de análise do edital."
)


def provenance_block(
    *,
    document_type: str | None,
    certificate_number: str | None,
    art_number: str | None,
    quantity: float | None,
    unit: str | None,
    source_file: str | None,
    source_page: Any,
    restrictions: list[str] | None = None,
    evidence_level: str | None = None,
) -> dict[str, Any]:
    return {
        "document": document_type,
        "number": certificate_number,
        "art": art_number,
        "quantity": quantity,
        "unit": unit,
        "source": source_file,
        "page": source_page,
        "evidence_level": evidence_level,
        "restrictions": list(restrictions or []),
    }


def format_item_hit(hit: dict[str, Any]) -> dict[str, Any]:
    return {
        **provenance_block(
            document_type=hit.get("document_type"),
            certificate_number=hit.get("certificate_number"),
            art_number=hit.get("art_number"),
            quantity=hit.get("quantity"),
            unit=hit.get("unit"),
            source_file=hit.get("source_file"),
            source_page=hit.get("source_page"),
            restrictions=hit.get("restrictions"),
            evidence_level=hit.get("evidence_level"),
        ),
        "experience_id": hit.get("experience_id"),
        "title": hit.get("title"),
        "contractor": hit.get("contractor"),
        "city": hit.get("city"),
        "state": hit.get("state"),
        "activity": hit.get("activity"),
        "service": hit.get("service"),
        "original_description": hit.get("original_description"),
        "original_text": hit.get("original_text"),
        "individual_cat_not_provided": hit.get("individual_cat_not_provided"),
        "document_status": hit.get("document_status"),
        "review_flags": hit.get("review_flags") or [],
        "score": hit.get("score"),
        "matched_terms": hit.get("matched_terms"),
    }


def format_document(doc: dict[str, Any], experiences: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "id": doc.get("id"),
        "document_type": doc.get("document_type"),
        "certificate_number": doc.get("certificate_number"),
        "art_number": doc.get("art_number"),
        "art_numbers": doc.get("art_numbers"),
        "issued_at": doc.get("issued_at"),
        "valid_until": doc.get("valid_until"),
        "current_status": doc.get("current_status"),
        "has_registered_attestation": doc.get("has_registered_attestation"),
        "source_files": doc.get("source_files"),
        "duplicate_aliases": doc.get("duplicate_aliases"),
        "restrictions": doc.get("restrictions") or [],
        "review_flags": doc.get("review_flags") or [],
        "notes": doc.get("notes"),
        "experiences": [
            {
                "id": e.get("id"),
                "title": e.get("title"),
                "contractor": e.get("contractor"),
                "city": e.get("city"),
                "evidence_level": e.get("evidence_level"),
                "individual_cat_not_provided": e.get("individual_cat_not_provided"),
            }
            for e in (experiences or [])
        ],
        "disclaimer": DISCLAIMER,
    }


def render_text_inventory(inventory: dict[str, Any]) -> str:
    lines = [
        "=== ACERVO TÉCNICO EXTRA EMPREITEIRA LTDA. ===",
        f"CATs: {inventory.get('cats')} | CAO: {inventory.get('caos')} | "
        f"Experiências: {inventory.get('experiences')}",
        f"Profissionais: {inventory.get('professionals')} | "
        f"Organizações: {inventory.get('organizations')}",
        "",
        DISCLAIMER,
    ]
    return "\n".join(lines)


def render_text_hits(hits: list[dict[str, Any]], *, title: str = "RESULTADOS") -> str:
    if not hits:
        return f"=== {title} ===\nNenhum resultado.\n\n{DISCLAIMER}"
    lines = [f"=== {title} ({len(hits)}) ===", ""]
    for i, h in enumerate(hits, 1):
        fmt = format_item_hit(h) if "service" in h else h
        lines.append(f"{i}. {fmt.get('title') or fmt.get('service') or fmt.get('experience_id')}")
        lines.append(
            f"   Documento: {fmt.get('document') or fmt.get('document_type')} "
            f"nº {fmt.get('number') or fmt.get('certificate_number')}"
        )
        lines.append(f"   ART: {fmt.get('art') or fmt.get('art_number')}")
        if fmt.get("service"):
            lines.append(
                f"   Serviço: {fmt.get('activity')} — {fmt.get('service')} | "
                f"{fmt.get('quantity')} {fmt.get('unit')} "
                f"({fmt.get('original_text') or ''})"
            )
        lines.append(
            f"   Fonte: {fmt.get('source') or fmt.get('source_file')} "
            f"pág. {fmt.get('page') or fmt.get('source_page')}"
        )
        lines.append(f"   Evidência: {fmt.get('evidence_level')} | Status doc: {fmt.get('document_status')}")
        if fmt.get("individual_cat_not_provided"):
            lines.append("   ⚠ Comprovada apenas por CAO — CAT individual não fornecida.")
        for r in (fmt.get("restrictions") or [])[:3]:
            lines.append(f"   Ressalva: {r}")
        lines.append("")
    lines.append(DISCLAIMER)
    return "\n".join(lines)


def render_text_match(result: dict[str, Any]) -> str:
    req = result.get("requirement") or {}
    lines = [
        "=== ADERÊNCIA A EXIGÊNCIA DE EDITAL ===",
        f"Requisito: {req.get('service')}",
        f"Modalidade: {req.get('modality')}",
        f"Quantidade: {req.get('quantity')} {req.get('unit')}",
        f"allow_sum: {result.get('allow_sum')}",
        f"Nível de aderência: {result.get('adherence_level')}",
        f"Maior quantitativo individual: {result.get('max_individual_quantity')}",
        f"Análise humana necessária: {result.get('human_review_required')}",
        "",
        "— Candidatos —",
    ]
    for c in (result.get("candidates") or [])[:10]:
        lines.append(
            f"  • {c.get('document_type')} {c.get('certificate_number')} ART {c.get('art_number')} | "
            f"{c.get('service')} | {c.get('quantity')} {c.get('unit')} | "
            f"{c.get('source_file')} p.{c.get('source_page')} | "
            f"evidência={c.get('evidence_level')}"
        )
    if result.get("allow_sum") and result.get("summed_records"):
        lines.append("")
        lines.append(f"Somatório explícito: {result.get('sum_total')} {req.get('unit')}")
        for r in result.get("summed_records") or []:
            lines.append(
                f"  + {r.get('certificate_number') or r.get('experience_id')}: "
                f"{r.get('quantity')} {r.get('unit')}"
            )
    lines.append("")
    lines.append("— Limitações —")
    for lim in result.get("limitations") or []:
        lines.append(f"  • {lim}")
    lines.append("")
    lines.append(result.get("disclaimer") or DISCLAIMER)
    return "\n".join(lines)


def render_text_document(doc: dict[str, Any], experiences: list[dict[str, Any]]) -> str:
    fmt = format_document(doc, experiences)
    lines = [
        f"=== {fmt['document_type']} nº {fmt['certificate_number']} ===",
        f"ART: {fmt.get('art_number')} | ARTs: {fmt.get('art_numbers')}",
        f"Emissão: {fmt.get('issued_at')} | Validade: {fmt.get('valid_until')}",
        f"Status: {fmt.get('current_status')}",
        f"Atestado registrado: {fmt.get('has_registered_attestation')}",
        f"Fontes: {', '.join(fmt.get('source_files') or [])}",
        f"Aliases: {', '.join(fmt.get('duplicate_aliases') or [])}",
        "",
        "— Restrições —",
    ]
    for r in fmt.get("restrictions") or []:
        lines.append(f"  • {r}")
    if fmt.get("review_flags"):
        lines.append("")
        lines.append("— Review flags —")
        for f in fmt["review_flags"]:
            if isinstance(f, dict):
                lines.append(f"  • {f.get('flag')}: {f.get('reason')}")
            else:
                lines.append(f"  • {f}")
    lines.append("")
    lines.append("— Experiências vinculadas —")
    for e in fmt.get("experiences") or []:
        lines.append(
            f"  • {e.get('title')} | {e.get('contractor')} | {e.get('city')} | "
            f"evidência={e.get('evidence_level')}"
        )
        if e.get("individual_cat_not_provided"):
            lines.append("    (somente CAO — sem CAT individual fornecida)")
    # list items for each experience if available
    for exp in experiences:
        lines.append("")
        lines.append(f"Itens técnicos — {exp.get('title')}:")
        for item in exp.get("technical_items") or []:
            lines.append(
                f"  • [{item.get('activity')}] {item.get('service')}: "
                f"{item.get('quantity')} {item.get('unit')} "
                f"({item.get('original_text')}) — "
                f"{item.get('source_file')} p.{item.get('source_page')}"
            )
    lines.append("")
    lines.append(DISCLAIMER)
    return "\n".join(lines)


def dumps_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)

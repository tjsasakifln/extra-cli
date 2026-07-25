"""Phase 1 — explicit raw open-edital universe contract + metrics.

Recall denominator MUST come from this universe, never only keyword hits.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from scripts.ops.hybrid_sector.models import RawOpportunity


@dataclass
class UniverseMetrics:
    raw_universe_count: int = 0
    records_with_object: int = 0
    records_with_items: int = 0
    records_with_category: int = 0
    records_with_documents: int = 0
    records_missing_critical_text: int = 0
    source_coverage_status: dict[str, str] = field(default_factory=dict)
    source_freshness_status: dict[str, str] = field(default_factory=dict)
    classify_full_universe: bool = False
    full_universe_threshold: int = 500

    def to_dict(self) -> dict[str, Any]:
        return {
            "raw_universe_count": self.raw_universe_count,
            "records_with_object": self.records_with_object,
            "records_with_items": self.records_with_items,
            "records_with_category": self.records_with_category,
            "records_with_documents": self.records_with_documents,
            "records_missing_critical_text": self.records_missing_critical_text,
            "source_coverage_status": dict(self.source_coverage_status),
            "source_freshness_status": dict(self.source_freshness_status),
            "classify_full_universe": self.classify_full_universe,
            "full_universe_threshold": self.full_universe_threshold,
            "recall_denominator": self.raw_universe_count,
        }


def record_from_dict(d: dict[str, Any]) -> RawOpportunity:
    """Normalize a free-form dict into RawOpportunity."""
    items = d.get("items") or d.get("itens") or []
    if isinstance(items, str):
        items = [items]
    cats = d.get("categories") or d.get("categorias") or []
    if isinstance(cats, str):
        cats = [cats]
    urls = d.get("urls") or []
    if isinstance(urls, str):
        urls = [urls]
    valor = d.get("valor_estimado")
    if valor is not None:
        try:
            valor = float(valor)
        except (TypeError, ValueError):
            valor = None
    return RawOpportunity(
        source=str(d.get("source") or d.get("fonte") or "unknown"),
        official_id=str(d.get("official_id") or d.get("id") or d.get("numero") or ""),
        objeto=str(d.get("objeto") or d.get("object") or ""),
        titulo=str(d.get("titulo") or d.get("title") or ""),
        items=[str(x) for x in items],
        categories=[str(x) for x in cats],
        orgao=str(d.get("orgao") or d.get("orgao_nome") or ""),
        municipio=str(d.get("municipio") or ""),
        uf=str(d.get("uf") or ""),
        modalidade=str(d.get("modalidade") or ""),
        valor_estimado=valor,
        data_abertura=d.get("data_abertura"),
        data_encerramento=d.get("data_encerramento"),
        urls=[str(u) for u in urls],
        has_edital=bool(d.get("has_edital")),
        has_tr=bool(d.get("has_tr")),
        has_etp=bool(d.get("has_etp")),
        has_anexos=bool(d.get("has_anexos")),
        captured_at=str(d.get("captured_at") or ""),
        source_coverage_status=str(d.get("source_coverage_status") or "unknown"),
        source_freshness_status=str(d.get("source_freshness_status") or "unknown"),
        extra={k: v for k, v in d.items() if k not in {
            "source", "fonte", "official_id", "id", "numero", "objeto", "object",
            "titulo", "title", "items", "itens", "categories", "categorias",
            "orgao", "orgao_nome", "municipio", "uf", "modalidade", "valor_estimado",
            "data_abertura", "data_encerramento", "urls", "has_edital", "has_tr",
            "has_etp", "has_anexos", "captured_at", "source_coverage_status",
            "source_freshness_status",
        }},
    )


def build_raw_universe(
    records: Iterable[dict[str, Any] | RawOpportunity],
    *,
    full_universe_threshold: int = 500,
) -> tuple[list[RawOpportunity], UniverseMetrics]:
    """Build raw universe list + metrics. Missing official_id gets synthetic index id."""
    out: list[RawOpportunity] = []
    for i, r in enumerate(records):
        if isinstance(r, RawOpportunity):
            rec = r
        else:
            rec = record_from_dict(r)
        if not rec.official_id:
            rec.official_id = f"auto-{i:06d}"
        out.append(rec)

    metrics = UniverseMetrics(full_universe_threshold=full_universe_threshold)
    metrics.raw_universe_count = len(out)
    for rec in out:
        if (rec.objeto or rec.titulo).strip():
            metrics.records_with_object += 1
        else:
            metrics.records_missing_critical_text += 1
        if rec.items:
            metrics.records_with_items += 1
        if rec.categories:
            metrics.records_with_category += 1
        if rec.has_edital or rec.has_tr or rec.has_etp or rec.has_anexos:
            metrics.records_with_documents += 1
        metrics.source_coverage_status[rec.source] = rec.source_coverage_status
        metrics.source_freshness_status[rec.source] = rec.source_freshness_status

    # When volume is operationally manageable, classify the full universe.
    metrics.classify_full_universe = metrics.raw_universe_count <= full_universe_threshold
    return out, metrics

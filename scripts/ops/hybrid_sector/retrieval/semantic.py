"""Canal B — semantic retrieval with versioned offline embedding provider.

Provider-decoupled. Default CI uses deterministic hash embeddings (no paid API).
Text representation combines object, title, items, category, document names, organ.
"""
from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Protocol

from scripts.ops.sector_classifier import normalize_text
from scripts.ops.hybrid_sector.models import RawOpportunity, RetrievalHit


# Prototype queries representing Extra engineering market (Portuguese)
DEFAULT_QUERY_PROTOTYPES = [
    "execução de obras de engenharia civil pavimentação asfáltica drenagem urbana",
    "construção reforma ampliação de edifício escola creche prédio público",
    "saneamento básico rede de esgoto adutora estação de tratamento",
    "terraplenagem contenção de encosta muro de arrimo infraestrutura urbana",
    "manutenção predial civil recuperação estrutural cobertura telhado",
    "requalificação urbana revitalização de praça adequação de acessibilidade",
    "implantação de rede pressurizada instalação de drenagem pluvial",
    "contratação integrada empreitada construção modular recuperação de ponte",
]


class EmbeddingProvider(Protocol):
    model_id: str
    model_version: str

    def embed(self, texts: list[str]) -> list[list[float]]:
        ...


@dataclass
class HashEmbeddingProvider:
    """Deterministic offline embedding for Portuguese text (no network).

    Uses character n-gram hashing into a fixed dim — good enough for
    paraphrase proximity tests without external models.
    """

    model_id: str = "offline-hash-embedding-pt-v1"
    model_version: str = "1.0.0"
    dim: int = 128
    ngram: int = 3

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        t = normalize_text(text)
        vec = [0.0] * self.dim
        if not t:
            return vec
        padded = f"  {t}  "
        for i in range(len(padded) - self.ngram + 1):
            gram = padded[i : i + self.ngram]
            h = int(hashlib.sha256(gram.encode("utf-8")).hexdigest(), 16)
            idx = h % self.dim
            sign = 1.0 if (h >> 8) % 2 == 0 else -1.0
            vec[idx] += sign
        # L2 normalize
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


@dataclass
class SemanticRunReport:
    model_id: str
    model_version: str
    text_fields_used: list[str]
    n_queries: int
    n_docs: int
    top_k: int
    min_similarity: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "model_version": self.model_version,
            "text_fields_used": list(self.text_fields_used),
            "n_queries": self.n_queries,
            "n_docs": self.n_docs,
            "top_k": self.top_k,
            "min_similarity": self.min_similarity,
        }


def representation_text(rec: RawOpportunity) -> str:
    """Combine object, title, items, category, document names, organ context."""
    docs = []
    if rec.has_edital:
        docs.append("edital")
    if rec.has_tr:
        docs.append("termo de referencia")
    if rec.has_etp:
        docs.append("estudo tecnico preliminar")
    if rec.has_anexos:
        docs.append("anexos tecnicos")
    parts = [
        rec.objeto,
        rec.titulo,
        " ".join(rec.items),
        " ".join(rec.categories),
        " ".join(docs),
        rec.orgao,
        rec.modalidade,
    ]
    return " ".join(p for p in parts if p).strip()


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def retrieve_semantic(
    universe: Iterable[RawOpportunity],
    *,
    provider: EmbeddingProvider | None = None,
    queries: list[str] | None = None,
    top_k: int = 200,
    min_similarity: float = 0.12,
) -> tuple[dict[str, RetrievalHit], SemanticRunReport]:
    provider = provider or HashEmbeddingProvider()
    queries = queries or list(DEFAULT_QUERY_PROTOTYPES)
    records = list(universe)
    texts = [representation_text(r) for r in records]
    doc_vecs = provider.embed(texts)
    q_vecs = provider.embed(queries)

    # Max similarity to any prototype query
    scored: list[tuple[str, float]] = []
    for rec, dvec in zip(records, doc_vecs):
        if not rec.text_blob().strip():
            continue
        sim = max((_cosine(dvec, qv) for qv in q_vecs), default=0.0)
        if sim >= min_similarity:
            scored.append((rec.canonical_id, float(sim)))

    scored.sort(key=lambda x: (-x[1], x[0]))
    scored = scored[:top_k]

    hits: dict[str, RetrievalHit] = {}
    for rank, (cid, score) in enumerate(scored, start=1):
        hits[cid] = RetrievalHit(
            channel="semantic",
            score=score,
            rank=rank,
            reason=f"max_cosine={score:.4f} model={provider.model_id}",
        )

    report = SemanticRunReport(
        model_id=provider.model_id,
        model_version=getattr(provider, "model_version", "unknown"),
        text_fields_used=["objeto", "titulo", "items", "categories", "documents", "orgao", "modalidade"],
        n_queries=len(queries),
        n_docs=len(records),
        top_k=top_k,
        min_similarity=min_similarity,
    )
    return hits, report


def paraphrase_similarity(
    text_a: str,
    text_b: str,
    *,
    provider: EmbeddingProvider | None = None,
) -> float:
    """Utility for paraphrase / no-keyword proximity tests."""
    provider = provider or HashEmbeddingProvider()
    va, vb = provider.embed([text_a, text_b])
    return _cosine(va, vb)

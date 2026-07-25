"""Canal B — semantic retrieval with versioned embedding providers.

HashEmbeddingProvider is lexical_fuzzy_hash only (CI/offline fallback).
Real semantic path: SentenceTransformerEmbeddingProvider or OpenAI-compatible.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import time
import urllib.error
import urllib.request
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from scripts.ops.hybrid_sector.models import RawOpportunity, RetrievalHit
from scripts.ops.sector_classifier import normalize_text

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

EMBEDDING_CLASS_LEXICAL_FUZZY_HASH = "lexical_fuzzy_hash"
EMBEDDING_CLASS_SENTENCE_TRANSFORMER = "sentence_transformer"
EMBEDDING_CLASS_OPENAI_COMPATIBLE = "openai_compatible_embedding"


class EmbeddingProvider(Protocol):
    model_id: str
    model_version: str
    embedding_class: str

    def embed(self, texts: list[str]) -> list[list[float]]:
        ...


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _text_hash(text: str, model_id: str) -> str:
    h = hashlib.sha256()
    h.update(model_id.encode("utf-8"))
    h.update(b"\0")
    h.update(text.encode("utf-8"))
    return h.hexdigest()


@dataclass
class EmbeddingCache:
    """Persistent disk cache keyed by model_id + text hash."""

    path: Path | None = None
    store: dict[str, list[float]] = field(default_factory=dict)
    hits: int = 0
    misses: int = 0

    def __post_init__(self) -> None:
        if self.path and self.path.is_file():
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self.store = {k: list(v) for k, v in raw.items() if isinstance(v, list)}
            except (OSError, json.JSONDecodeError):
                self.store = {}

    def get(self, key: str) -> list[float] | None:
        v = self.store.get(key)
        if v is not None:
            self.hits += 1
            return list(v)
        self.misses += 1
        return None

    def put(self, key: str, vec: list[float]) -> None:
        self.store[key] = list(vec)

    def persist(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.store, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    def stats(self) -> dict[str, Any]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "size": len(self.store),
            "path": str(self.path) if self.path else None,
        }


@dataclass
class HashEmbeddingProvider:
    """Offline lexical fuzzy hash n-gram vectors — NOT operational semantic embedding.

    Classification: lexical_fuzzy_hash. Suitable for CI fixtures and offline fallback only.
    """

    model_id: str = "offline-hash-embedding-pt-v1"
    model_version: str = "1.0.0"
    embedding_class: str = EMBEDDING_CLASS_LEXICAL_FUZZY_HASH
    dim: int = 128
    ngram: int = 3
    operational_semantic: bool = False

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
        return _l2_normalize(vec)


@dataclass
class SentenceTransformerEmbeddingProvider:
    """Real multilingual/PT embedding via sentence-transformers (local preferred).

    Default model: paraphrase-multilingual-MiniLM-L12-v2 (multilingual, local).
    Falls back raising ImportError/RuntimeError if model unavailable — callers
    must record BLOCKED and use lexical_fuzzy_hash fallback explicitly.
    """

    model_id: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    model_version: str = "1.0.0"
    embedding_class: str = EMBEDDING_CLASS_SENTENCE_TRANSFORMER
    batch_size: int = 32
    normalize: bool = True
    dim: int | None = None  # enforced if set
    timeout_seconds: float = 60.0
    max_retries: int = 2
    cache: EmbeddingCache | None = None
    operational_semantic: bool = True
    _model: Any = field(default=None, repr=False, compare=False)

    def _load(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers not installed; real embedding unavailable"
            ) from exc
        last: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                self._model = SentenceTransformer(self.model_id)
                return self._model
            except Exception as exc:  # noqa: BLE001
                last = exc
                time.sleep(0.1 * (attempt + 1))
        raise RuntimeError(f"failed to load embedding model: {last}") from last

    def embed(self, texts: list[str]) -> list[list[float]]:
        cache = self.cache or EmbeddingCache()
        out: list[list[float] | None] = [None] * len(texts)
        todo_idx: list[int] = []
        todo_texts: list[str] = []
        for i, t in enumerate(texts):
            key = _text_hash(t, self.model_id)
            cached = cache.get(key)
            if cached is not None:
                out[i] = cached
            else:
                todo_idx.append(i)
                todo_texts.append(t)

        if todo_texts:
            model = self._load()
            for start in range(0, len(todo_texts), self.batch_size):
                batch = todo_texts[start : start + self.batch_size]
                vectors = model.encode(
                    batch,
                    batch_size=self.batch_size,
                    normalize_embeddings=self.normalize,
                    show_progress_bar=False,
                )
                for j, vec in enumerate(vectors):
                    v = [float(x) for x in vec]
                    if self.normalize:
                        v = _l2_normalize(v)
                    if self.dim is not None:
                        if len(v) > self.dim:
                            v = v[: self.dim]
                            v = _l2_normalize(v)
                        elif len(v) < self.dim:
                            v = v + [0.0] * (self.dim - len(v))
                    gi = todo_idx[start + j]
                    out[gi] = v
                    cache.put(_text_hash(todo_texts[start + j], self.model_id), v)
            cache.persist()

        return [v if v is not None else [0.0] for v in out]


@dataclass
class OpenAICompatibleEmbeddingProvider:
    """OpenAI-compatible embeddings HTTP API with cache, timeout, retry, cost log."""

    model_id: str = "text-embedding-3-small"
    model_version: str = "1.0.0"
    embedding_class: str = EMBEDDING_CLASS_OPENAI_COMPATIBLE
    base_url: str | None = None
    api_key: str | None = None
    batch_size: int = 64
    timeout_seconds: float = 30.0
    max_retries: int = 2
    normalize: bool = True
    dim: int | None = None
    cache: EmbeddingCache | None = None
    cost_per_1k_tokens: float = 0.00002
    operational_semantic: bool = True
    observed_cost_usd: float = 0.0
    call_log: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.base_url = (
            self.base_url
            or os.environ.get("HYBRID_SECTOR_EMBED_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL")
            or "https://api.openai.com/v1"
        ).rstrip("/")
        self.api_key = (
            self.api_key
            or os.environ.get("OPENAI_API_KEY")
            or os.environ.get("HYBRID_SECTOR_EMBED_API_KEY")
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not self.api_key:
            raise RuntimeError("embedding API key not set")
        cache = self.cache or EmbeddingCache()
        out: list[list[float] | None] = [None] * len(texts)
        todo_idx: list[int] = []
        todo_texts: list[str] = []
        for i, t in enumerate(texts):
            key = _text_hash(t, self.model_id)
            cached = cache.get(key)
            if cached is not None:
                out[i] = cached
            else:
                todo_idx.append(i)
                todo_texts.append(t)

        for start in range(0, len(todo_texts), self.batch_size):
            batch = todo_texts[start : start + self.batch_size]
            vectors = self._http_embed(batch)
            for j, v in enumerate(vectors):
                if self.normalize:
                    v = _l2_normalize(v)
                if self.dim is not None:
                    if len(v) > self.dim:
                        v = _l2_normalize(v[: self.dim])
                    elif len(v) < self.dim:
                        v = v + [0.0] * (self.dim - len(v))
                gi = todo_idx[start + j]
                out[gi] = v
                cache.put(_text_hash(batch[j], self.model_id), v)
        cache.persist()
        return [v if v is not None else [0.0] for v in out]

    def _http_embed(self, texts: list[str]) -> list[list[float]]:
        url = f"{self.base_url}/embeddings"
        body: dict[str, Any] = {"model": self.model_id, "input": texts}
        if self.dim is not None:
            body["dimensions"] = self.dim
        last: Exception | None = None
        for attempt in range(self.max_retries + 1):
            t0 = time.monotonic()
            try:
                if not str(url).startswith(("https://", "http://")):
                    raise RuntimeError(f"refusing non-http embedding url: {url}")
                req = urllib.request.Request(  # noqa: S310
                    url,
                    data=json.dumps(body).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.api_key}",
                    },
                    method="POST",
                )
                # nosec B310 — HTTPS OpenAI-compatible embeddings endpoint only
                with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:  # noqa: S310
                    payload = json.loads(resp.read().decode("utf-8"))
                data = sorted(payload["data"], key=lambda x: x["index"])
                usage = payload.get("usage") or {}
                tokens = int(usage.get("total_tokens") or 0)
                cost = tokens / 1000.0 * self.cost_per_1k_tokens
                self.observed_cost_usd += cost
                self.call_log.append(
                    {
                        "event": "ok",
                        "n": len(texts),
                        "tokens": tokens,
                        "cost_usd": cost,
                        "latency_s": time.monotonic() - t0,
                        "attempt": attempt,
                    }
                )
                return [[float(x) for x in row["embedding"]] for row in data]
            except Exception as exc:  # noqa: BLE001
                last = exc
                self.call_log.append(
                    {
                        "event": "error",
                        "error": str(exc),
                        "attempt": attempt,
                        "latency_s": time.monotonic() - t0,
                    }
                )
                time.sleep(0.05 * (attempt + 1))
        raise RuntimeError(f"embedding provider failed: {last}") from last


def build_embedding_provider(cfg: dict[str, Any] | None = None) -> EmbeddingProvider:
    """Wire YAML semantic config → runtime provider.

    provider: lexical_fuzzy_hash | sentence_transformer | openai_compatible
    Default CI: lexical_fuzzy_hash.
    """
    cfg = cfg or {}
    sem = cfg.get("semantic") if "semantic" in cfg else cfg
    sem = sem or {}
    name = str(
        sem.get("provider")
        or os.environ.get("HYBRID_SECTOR_EMBED_PROVIDER")
        or "lexical_fuzzy_hash"
    ).lower()
    cache_path = sem.get("cache_path")
    cache = EmbeddingCache(path=Path(cache_path)) if cache_path else EmbeddingCache()

    if name in {"hash", "lexical_fuzzy_hash", "offline-hash", "offline"}:
        return HashEmbeddingProvider(
            model_id=str(sem.get("model_id") or "offline-hash-embedding-pt-v1"),
            model_version=str(sem.get("model_version") or "1.0.0"),
            dim=int(sem.get("dim") or 128),
        )
    if name in {"sentence_transformer", "sentence-transformers", "st"}:
        return SentenceTransformerEmbeddingProvider(
            model_id=str(
                sem.get("model_id")
                or "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
            ),
            model_version=str(sem.get("model_version") or "1.0.0"),
            batch_size=int(sem.get("batch_size") or 32),
            normalize=bool(sem.get("normalize", True)),
            dim=sem.get("dim"),
            timeout_seconds=float(sem.get("timeout_seconds") or 60),
            max_retries=int(sem.get("max_retries") or 2),
            cache=cache,
        )
    if name in {"openai_compatible", "openai", "openai_embedding"}:
        return OpenAICompatibleEmbeddingProvider(
            model_id=str(sem.get("model_id") or "text-embedding-3-small"),
            model_version=str(sem.get("model_version") or "1.0.0"),
            base_url=sem.get("base_url"),
            batch_size=int(sem.get("batch_size") or 64),
            timeout_seconds=float(sem.get("timeout_seconds") or 30),
            max_retries=int(sem.get("max_retries") or 2),
            normalize=bool(sem.get("normalize", True)),
            dim=sem.get("dim"),
            cache=cache,
            cost_per_1k_tokens=float(sem.get("cost_per_1k_tokens") or 0.00002),
        )
    # Unknown → safe offline fallback, labeled honestly
    return HashEmbeddingProvider()


@dataclass
class SemanticRunReport:
    model_id: str
    model_version: str
    embedding_class: str
    text_fields_used: list[str]
    n_queries: int
    n_docs: int
    top_k: int
    min_similarity: float
    operational_semantic: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "model_version": self.model_version,
            "embedding_class": self.embedding_class,
            "operational_semantic": self.operational_semantic,
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

    # Max similarity to any prototype query — score all, then curve by volume
    scored: list[tuple[str, float]] = []
    for rec, dvec in zip(records, doc_vecs):
        if not rec.text_blob().strip():
            continue
        sim = max((_cosine(dvec, qv) for qv in q_vecs), default=0.0)
        if sim >= min_similarity:
            scored.append((rec.canonical_id, float(sim)))

    scored.sort(key=lambda x: (-x[1], x[0]))
    # Keep full ranked list for curves; hits limited by top_k policy
    full_ranked = list(scored)
    scored = scored[:top_k] if top_k > 0 else scored

    hits: dict[str, RetrievalHit] = {}
    for rank, (cid, score) in enumerate(scored, start=1):
        hits[cid] = RetrievalHit(
            channel="semantic",
            score=score,
            rank=rank,
            reason=(
                f"max_cosine={score:.4f} model={provider.model_id} "
                f"class={getattr(provider, 'embedding_class', 'unknown')}"
            ),
        )

    report = SemanticRunReport(
        model_id=provider.model_id,
        model_version=getattr(provider, "model_version", "unknown"),
        embedding_class=getattr(
            provider, "embedding_class", EMBEDDING_CLASS_LEXICAL_FUZZY_HASH
        ),
        text_fields_used=[
            "objeto",
            "titulo",
            "items",
            "categories",
            "documents",
            "orgao",
            "modalidade",
        ],
        n_queries=len(queries),
        n_docs=len(records),
        top_k=top_k,
        min_similarity=min_similarity,
        operational_semantic=bool(
            getattr(provider, "operational_semantic", False)
        ),
    )
    # Attach recall-vs-volume curve metadata (not top-k only)
    report_dict_extra = {
        "ranked_count_above_threshold": len(full_ranked),
        "recall_vs_volume_curve_points": _volume_curve_points(full_ranked),
    }
    # stash on report via dynamic attr for pipeline consumers
    setattr(report, "extra", report_dict_extra)
    return hits, report


def _volume_curve_points(
    scored: list[tuple[str, float]], volumes: list[int] | None = None
) -> list[dict[str, Any]]:
    volumes = volumes or [10, 25, 50, 100, 200, 500, 1000]
    out = []
    for v in volumes:
        slice_ = scored[:v]
        out.append(
            {
                "volume": v,
                "n_returned": len(slice_),
                "min_score": slice_[-1][1] if slice_ else None,
                "max_score": slice_[0][1] if slice_ else None,
            }
        )
    return out


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

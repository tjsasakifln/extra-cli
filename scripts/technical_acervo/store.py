"""Canonical acervo store loader, indexes and pure helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from scripts.technical_acervo.normalize import (
    art_number_variants,
    normalize_certificate_number,
    normalize_text,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ACERVO_PATH = REPO_ROOT / "data" / "extra_technical_acervo.json"

# Patterns that must never appear in embeddings/chunks/normal responses.
FORBIDDEN_PII_PATTERNS = (
    r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b",  # CPF-like
    r"\b\d{2}/\d{2}/\d{4}\b.*nascimento",
    r"data\s+de\s+nascimento",
    r"\bcpf\b",
)


@dataclass
class AcervoStore:
    """In-memory view of the canonical EXTRA technical acervo."""

    raw: dict[str, Any]
    path: Path
    documents: list[dict[str, Any]] = field(default_factory=list)
    experiences: list[dict[str, Any]] = field(default_factory=list)
    professionals: list[dict[str, Any]] = field(default_factory=list)
    organizations: list[dict[str, Any]] = field(default_factory=list)
    synonyms: dict[str, list[str]] = field(default_factory=dict)
    _doc_by_id: dict[str, dict[str, Any]] = field(default_factory=dict)
    _exp_by_id: dict[str, dict[str, Any]] = field(default_factory=dict)
    _cert_index: dict[str, str] = field(default_factory=dict)
    _art_index: dict[str, set[str]] = field(default_factory=dict)
    _file_index: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.documents = list(self.raw.get("technical_documents") or [])
        self.experiences = list(self.raw.get("technical_experiences") or [])
        self.professionals = list(self.raw.get("professionals") or [])
        self.organizations = list(self.raw.get("organizations") or [])
        self.synonyms = dict(self.raw.get("synonyms") or {})
        self._build_indexes()

    def _build_indexes(self) -> None:
        self._doc_by_id = {d["id"]: d for d in self.documents}
        self._exp_by_id = {e["id"]: e for e in self.experiences}
        self._cert_index = {}
        self._art_index = {}
        self._file_index = {}
        for doc in self.documents:
            cert = normalize_certificate_number(doc.get("certificate_number"))
            if cert:
                self._cert_index[cert] = doc["id"]
                self._cert_index[normalize_text(cert)] = doc["id"]
            for art in doc.get("art_numbers") or []:
                for variant in art_number_variants(art):
                    self._art_index.setdefault(variant, set()).add(doc["id"])
            if doc.get("art_number"):
                for variant in art_number_variants(doc["art_number"]):
                    self._art_index.setdefault(variant, set()).add(doc["id"])
            for fname in doc.get("source_files") or []:
                self._file_index[normalize_text(fname)] = doc["id"]
                self._file_index[fname.lower()] = doc["id"]
            for alias in doc.get("duplicate_aliases") or []:
                self._file_index[normalize_text(alias)] = doc["id"]
                self._file_index[alias.lower()] = doc["id"]

    # --- counts / inventory -------------------------------------------------

    def cats(self) -> list[dict[str, Any]]:
        return [d for d in self.documents if d.get("document_type") == "CAT"]

    def caos(self) -> list[dict[str, Any]]:
        return [d for d in self.documents if d.get("document_type") == "CAO"]

    def count_cats(self) -> int:
        return len(self.cats())

    def count_caos(self) -> int:
        return len(self.caos())

    def count_experiences(self) -> int:
        return len(self.experiences)

    def inventory(self) -> dict[str, Any]:
        return {
            "documents_total": len(self.documents),
            "cats": self.count_cats(),
            "caos": self.count_caos(),
            "experiences": self.count_experiences(),
            "professionals": len(self.professionals),
            "organizations": len(self.organizations),
            "disclaimer": self.raw.get("disclaimer"),
        }

    # --- lookups ------------------------------------------------------------

    def get_document(self, doc_id: str) -> dict[str, Any] | None:
        return self._doc_by_id.get(doc_id)

    def get_experience(self, exp_id: str) -> dict[str, Any] | None:
        return self._exp_by_id.get(exp_id)

    def find_document(
        self,
        *,
        certificate: str | None = None,
        art: str | None = None,
        source_file: str | None = None,
        document_type: str | None = None,
        query: str | None = None,
    ) -> list[dict[str, Any]]:
        found_ids: set[str] = set()
        if certificate:
            cert = normalize_certificate_number(certificate)
            doc_id = self._cert_index.get(cert) or self._cert_index.get(normalize_text(cert))
            if doc_id:
                found_ids.add(doc_id)
            # partial / CAO style
            for d in self.documents:
                if cert and cert in normalize_certificate_number(d.get("certificate_number")):
                    found_ids.add(d["id"])
        if art:
            for variant in art_number_variants(art):
                found_ids |= self._art_index.get(variant, set())
            # also search experiences linked arts
            for exp in self.experiences:
                for linked in exp.get("linked_arts") or []:
                    if art_number_variants(art) & art_number_variants(linked):
                        for doc_id in exp.get("linked_documents") or []:
                            found_ids.add(doc_id)
        if source_file:
            key = normalize_text(source_file)
            doc_id = self._file_index.get(key) or self._file_index.get(source_file.lower())
            if doc_id:
                found_ids.add(doc_id)
            # basename match
            for fname, did in self._file_index.items():
                if key and key in fname:
                    found_ids.add(did)
        if query and not found_ids:
            q = normalize_text(query)
            for d in self.documents:
                blob = normalize_text(
                    " ".join(
                        [
                            d.get("document_type") or "",
                            d.get("certificate_number") or "",
                            d.get("art_number") or "",
                            " ".join(d.get("art_numbers") or []),
                            " ".join(d.get("source_files") or []),
                            d.get("notes") or "",
                        ]
                    )
                )
                if q in blob or any(tok in blob for tok in q.split() if len(tok) > 2):
                    found_ids.add(d["id"])
        results = [self._doc_by_id[i] for i in found_ids if i in self._doc_by_id]
        if document_type:
            dt = document_type.upper()
            results = [d for d in results if (d.get("document_type") or "").upper() == dt]
        return results

    def experiences_for_document(self, doc_id: str) -> list[dict[str, Any]]:
        return [e for e in self.experiences if doc_id in (e.get("linked_documents") or [])]

    def experiences_for_contractor(self, contractor: str) -> list[dict[str, Any]]:
        q = normalize_text(contractor)
        return [
            e
            for e in self.experiences
            if q in normalize_text(e.get("contractor"))
            or q in normalize_text(e.get("owner"))
            or q in normalize_text(e.get("company"))
        ]

    # --- dedup integrity ----------------------------------------------------

    def duplicate_source_file_groups(self) -> list[dict[str, Any]]:
        """Return documents that share multiple source file aliases (expected dedup)."""
        groups = []
        for doc in self.documents:
            files = list(doc.get("source_files") or [])
            aliases = list(doc.get("duplicate_aliases") or [])
            combined = sorted(set(files + aliases))
            if len(files) > 1 or (len(files) >= 1 and any(a not in files for a in aliases)):
                if len(combined) > 1:
                    groups.append(
                        {
                            "document_id": doc["id"],
                            "certificate_number": doc.get("certificate_number"),
                            "source_files": files,
                            "duplicate_aliases": aliases,
                            "canonical_count": 1,
                        }
                    )
        return groups

    def assert_dedup_integrity(self) -> dict[str, Any]:
        """Validate certificate uniqueness and arquivo5/arquivo8 mapping."""
        certs: dict[str, list[str]] = {}
        for d in self.cats():
            cert = normalize_certificate_number(d.get("certificate_number"))
            certs.setdefault(cert, []).append(d["id"])
        duplicate_certs = {c: ids for c, ids in certs.items() if len(ids) > 1}
        f5 = self.find_document(source_file="arquivo5.pdf")
        f8 = self.find_document(source_file="arquivo8.pdf")
        same = bool(f5 and f8 and f5[0]["id"] == f8[0]["id"])
        return {
            "cat_count": self.count_cats(),
            "duplicate_certificate_numbers": duplicate_certs,
            "arquivo5_arquivo8_same_document": same,
            "shared_document_id": f5[0]["id"] if same else None,
            "certificate": f5[0].get("certificate_number") if same else None,
            "ok": not duplicate_certs and same and self.count_cats() == 7,
        }

    def experience_items_flat(self) -> list[dict[str, Any]]:
        """Flatten technical items with experience and document context."""
        rows: list[dict[str, Any]] = []
        for exp in self.experiences:
            primary = self.get_document(exp.get("primary_document_id") or "")
            for item in exp.get("technical_items") or []:
                rows.append(
                    {
                        "experience": exp,
                        "item": item,
                        "document": primary or self.get_document(item.get("source_document") or ""),
                    }
                )
        return rows

    def all_text_blobs_for_pii_scan(self) -> list[str]:
        """Collect text fields used for search chunks / responses (no PII expected)."""
        blobs: list[str] = []
        blobs.append(json.dumps(self.raw, ensure_ascii=False))
        return blobs


def load_store(path: Path | str | None = None) -> AcervoStore:
    p = Path(path) if path else DEFAULT_ACERVO_PATH
    with p.open(encoding="utf-8") as fh:
        raw = json.load(fh)
    return AcervoStore(raw=raw, path=p)

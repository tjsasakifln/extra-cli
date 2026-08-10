"""Document yield scoring: company-authored first.

Score = expected_contact_information_yield / retrieval_cost (relative units).
Priors are configurable; metrics can update them later (source learning).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("_", " ").replace("-", " ")
    text = re.sub(r"\.(pdf|zip|docx?|xlsx?|odt|csv|json)\b", " ", text, flags=re.I)
    return re.sub(r"\s+", " ", text.lower()).strip()


# (pattern, yield 0-1, company_authored_likely, label)
_YIELD_RULES: list[tuple[re.Pattern[str], float, bool, str]] = [
    (re.compile(r"\bproposta (comercial|de precos|de preco|tecnica)?\b|\bcarta proposta\b"), 0.95, True, "proposal"),
    (re.compile(r"\bdeclarac"), 0.90, True, "company_declaration"),
    (re.compile(r"\bprocurac|\bcredenciamento\b|\btermo de represent"), 0.92, True, "power_of_attorney"),
    (re.compile(r"\bpreposto\b|\bresponsavel tecnico\b|\bindicacao de"), 0.93, True, "representative_indication"),
    (re.compile(r"\bhabilitac"), 0.85, True, "qualification"),
    (re.compile(r"\brequeriment|\bpedido de (aditivo|reajuste|reequilibrio)|\boficio\b"), 0.88, True, "company_request"),
    (re.compile(r"\brecurso\b|\bcontrarraz"), 0.80, True, "appeal"),
    (re.compile(r"\bmedicao\b|\bcomunicacao de medicao\b"), 0.75, True, "measurement_notice"),
    (re.compile(r"\bcontrato\b|\btexto de contrato\b"), 0.70, False, "contract"),
    (re.compile(r"\baditiv|\bapostil"), 0.65, False, "amendment"),
    (re.compile(r"\bata\b"), 0.55, False, "minutes"),
    (re.compile(r"\bparecer\b|\bdecis"), 0.35, False, "admin_opinion"),
    (re.compile(r"\bedital\b|\baviso\b|\btermo de refer"), 0.20, False, "notice"),
    (re.compile(r"\bplanilha\b|\borcament"), 0.40, False, "budget_sheet"),
]


@dataclass
class DocumentPriority:
    title: str
    yield_score: float
    retrieval_cost: float
    efficiency: float
    company_authored_likely: bool
    label: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "yield_score": self.yield_score,
            "retrieval_cost": self.retrieval_cost,
            "efficiency": self.efficiency,
            "company_authored_likely": self.company_authored_likely,
            "label": self.label,
        }


def estimate_retrieval_cost(
    *,
    size_bytes: int | None = None,
    requires_ocr: bool = False,
    requires_login: bool = False,
    remote: bool = True,
) -> float:
    """Relative cost units (lower is cheaper)."""
    cost = 1.0 if remote else 0.2
    if size_bytes:
        if size_bytes > 5_000_000:
            cost += 2.0
        elif size_bytes > 1_000_000:
            cost += 1.0
        elif size_bytes > 200_000:
            cost += 0.3
    if requires_ocr:
        cost += 3.0
    if requires_login:
        cost += 5.0
    return max(cost, 0.1)


def score_document(
    title: str | None,
    *,
    category: str | None = None,
    size_bytes: int | None = None,
    requires_ocr: bool = False,
    requires_login: bool = False,
    remote: bool = True,
    prior_overrides: dict[str, float] | None = None,
) -> DocumentPriority:
    norm = _norm(title or "")
    cat = _norm(category or "")
    blob = f"{norm} {cat}".strip()
    yield_score = 0.25
    company = False
    label = "other"
    for pattern, y, is_co, lab in _YIELD_RULES:
        if pattern.search(blob):
            yield_score = y
            company = is_co
            label = lab
            break
    if prior_overrides and label in prior_overrides:
        yield_score = float(prior_overrides[label])
    cost = estimate_retrieval_cost(
        size_bytes=size_bytes,
        requires_ocr=requires_ocr,
        requires_login=requires_login,
        remote=remote,
    )
    return DocumentPriority(
        title=title or "",
        yield_score=yield_score,
        retrieval_cost=cost,
        efficiency=yield_score / cost,
        company_authored_likely=company,
        label=label,
    )


def rank_documents(docs: list[dict[str, Any]], *, prior_overrides: dict[str, float] | None = None) -> list[dict[str, Any]]:
    """Return documents sorted by efficiency desc, with priority fields attached."""
    scored: list[tuple[float, dict[str, Any]]] = []
    for d in docs:
        pr = score_document(
            d.get("title") or d.get("original_title") or d.get("name"),
            category=d.get("category") or d.get("document_category") or d.get("doc_type"),
            size_bytes=d.get("size_bytes"),
            requires_ocr=bool(d.get("requires_ocr")),
            requires_login=bool(d.get("requires_login")),
            remote=d.get("remote", True),
            prior_overrides=prior_overrides,
        )
        enriched = dict(d)
        enriched["yield_score"] = pr.yield_score
        enriched["retrieval_cost"] = pr.retrieval_cost
        enriched["efficiency"] = pr.efficiency
        enriched["company_authored_likely"] = pr.company_authored_likely
        enriched["priority_label"] = pr.label
        scored.append((pr.efficiency, enriched))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [d for _, d in scored]

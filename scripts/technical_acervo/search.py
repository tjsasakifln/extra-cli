"""Search and ranking over the technical acervo (pure + store)."""

from __future__ import annotations

import re
from typing import Any

from scripts.technical_acervo.normalize import (
    item_service_blob,
    normalize_text,
    normalize_unit,
)
from scripts.technical_acervo.store import AcervoStore
from scripts.technical_acervo.synonyms import (
    _STOPWORDS,
    expand_query_terms,
    synonym_map_from_store,
    terms_match_blob,
)

# Ranking priority weights (higher = better).
W_EXACT_SERVICE = 100
W_SERVICE_RELEVANT = 80
W_ACTIVITY = 40
W_QUANTITY = 30
W_CAT_ATTESTATION = 50
W_VALIDITY = 20
W_SEMANTIC = 15
W_TAG = 10  # context only — never invents quantitativo for a different service
W_TITLE = 8


def _doc_status_score(doc: dict[str, Any] | None) -> float:
    if not doc:
        return 0.0
    status = (doc.get("current_status") or "").lower()
    if status == "valid":
        return W_VALIDITY
    if status == "no_expiration_identified":
        return W_VALIDITY * 0.7
    if status == "expired":
        return -W_VALIDITY
    if status == "requires_review":
        return -W_VALIDITY * 0.5
    return 0.0


def _evidence_score(exp: dict[str, Any], doc: dict[str, Any] | None) -> float:
    level = (exp.get("evidence_level") or "").lower()
    score = 0.0
    if level == "cat_with_registered_attestation" or (doc and doc.get("has_registered_attestation")):
        score += W_CAT_ATTESTATION
    if level == "operational_certificate_only" or exp.get("individual_cat_not_provided"):
        score -= 10  # still findable, but ranked below CAT
    if doc and (doc.get("document_type") or "").upper() == "CAO":
        score -= 15
    return score


def _activity_from_query(query: str) -> str | None:
    q = normalize_text(query)
    for act in (
        "projeto e execucao",
        "projeto_e_execucao",
        "restauracao",
        "reforma",
        "montagem",
        "instalacao",
        "execucao",
        "projeto",
    ):
        if normalize_text(act.replace("_", " ")) in q:
            return act.replace("_", " ")
    return None


def _query_content_tokens(query: str) -> list[str]:
    nq = normalize_text(query)
    return [t for t in nq.split() if len(t) >= 3 and t not in _STOPWORDS]


def _token_in_blob(token: str, blob: str) -> bool:
    return bool(re.search(rf"(?<!\w){re.escape(token)}(?!\w)", f" {blob} "))


def service_relevance(
    query: str,
    item: dict[str, Any],
    terms: set[str],
) -> tuple[bool, bool, list[str]]:
    """Decide if an item's *service* (not experience tags) answers the query.

    Returns (service_relevant, exact_service_match, matched_service_terms).

    Rules (any of):
    1. Exact / substring of full query on service or original_description
    2. Multi-word term/synonym hit on the item service blob
    3. All significant query tokens appear in the service blob
    """
    service_blob = item_service_blob(item)
    ns = normalize_text(item.get("service"))
    norig = normalize_text(item.get("original_description"))
    nq = normalize_text(query)
    if not nq:
        return True, False, []

    exact = bool(
        nq == ns
        or nq in ns
        or (ns and ns in nq)
        or nq in norig
        or nq in service_blob
    )
    _ok, hits = terms_match_blob(terms, service_blob)
    multi_hits = [h for h in hits if " " in h]
    q_tokens = _query_content_tokens(query)
    if q_tokens:
        covered = all(_token_in_blob(t, service_blob) for t in q_tokens)
    else:
        covered = bool(hits)

    # Synonym multi-word that is itself a full service-family phrase
    service_relevant = exact or bool(multi_hits) or covered
    return service_relevant, exact, sorted(set(hits + multi_hits))


def rank_item_hits(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rank: service-relevant first, then exact, then score, then quantity."""
    return sorted(
        hits,
        key=lambda r: (
            0 if r.get("service_relevant") else 1,
            0 if r.get("exact_service_match") else 1,
            -(r.get("score") or 0),
            -(r.get("quantity") or 0),
            r.get("service") or "",
        ),
    )


def service_relevant_hits(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter to items whose service (not only tags) matches the query."""
    rel = [h for h in hits if h.get("service_relevant")]
    return rank_item_hits(rel)


def search_items(
    store: AcervoStore,
    query: str,
    *,
    min_quantity: float | None = None,
    unit: str | None = None,
    activity: str | None = None,
    evidence: str | None = None,
    document_type: str | None = None,
    limit: int = 50,
    service_only: bool = False,
) -> list[dict[str, Any]]:
    """Search technical items with synonym expansion and structured filters.

    Tag/title matches may surface an item for discovery, but only
    ``service_relevant`` hits are used for quantitativos / match / max.
    """
    syn_map = synonym_map_from_store(store)
    terms = expand_query_terms(query, syn_map)
    wanted_activity = normalize_text(activity) if activity else _activity_from_query(query)
    wanted_unit = normalize_unit(unit) if unit else None
    wanted_dtype = document_type.upper() if document_type else None
    wanted_evidence = normalize_text(evidence) if evidence else None

    results: list[dict[str, Any]] = []
    for row in store.experience_items_flat():
        exp = row["experience"]
        item = row["item"]
        doc = row["document"]
        if wanted_dtype and doc and (doc.get("document_type") or "").upper() != wanted_dtype:
            continue
        if wanted_evidence:
            el = normalize_text(exp.get("evidence_level"))
            if wanted_evidence not in el and wanted_evidence not in normalize_text(
                "cao_only" if exp.get("individual_cat_not_provided") else ""
            ):
                if wanted_evidence in ("operational_certificate_only", "cao", "somente_cao"):
                    if not exp.get("individual_cat_not_provided") and el != "operational_certificate_only":
                        continue
                else:
                    continue
        item_unit = normalize_unit(item.get("unit"))
        qty = item.get("quantity")
        if min_quantity is not None:
            if qty is None or float(qty) < float(min_quantity):
                continue
            if wanted_unit and item_unit != wanted_unit:
                continue
        elif wanted_unit and item_unit != wanted_unit:
            continue

        service_blob = item_service_blob(item)
        # Tags use underscores (edificacao_tombada); search phrases use spaces.
        tag_blob = normalize_text(
            " ".join(exp.get("capability_tags") or []).replace("_", " ")
        )
        title_blob = normalize_text(
            " ".join(
                [
                    exp.get("title") or "",
                    exp.get("description") or "",
                    exp.get("contractor") or "",
                    exp.get("city") or "",
                    exp.get("address") or "",
                ]
            )
        )
        full_blob = f"{service_blob} {tag_blob} {title_blob}"

        svc_relevant, exact, hits_svc = service_relevance(query, item, terms)
        ok_tag, hits_tag = terms_match_blob(terms, tag_blob)
        ok_title, hits_title = terms_match_blob(terms, title_blob)

        if query.strip():
            if service_only:
                if not svc_relevant:
                    continue
            elif not (svc_relevant or ok_tag or ok_title):
                continue

        score = 0.0
        if exact:
            score += W_EXACT_SERVICE
        if svc_relevant:
            score += W_SERVICE_RELEVANT + 5 * len(hits_svc)
        # Tag/title only boost discovery rank — never alone for quantitativo max
        if ok_tag and not svc_relevant:
            score += W_TAG
        elif ok_tag and svc_relevant:
            score += W_TAG // 2
        if ok_title and not svc_relevant:
            score += W_TITLE
        elif ok_title and svc_relevant:
            score += W_TITLE // 2
        if wanted_activity:
            ia = normalize_text(item.get("activity"))
            if wanted_activity in ia or ia in wanted_activity:
                score += W_ACTIVITY
        if min_quantity is not None and qty is not None and svc_relevant:
            score += W_QUANTITY
        score += _evidence_score(exp, doc)
        score += _doc_status_score(doc)

        results.append(
            {
                "score": score,
                "exact_service_match": exact,
                "service_relevant": svc_relevant,
                "matched_terms": sorted(set(hits_svc + hits_tag + hits_title)),
                "experience_id": exp.get("id"),
                "title": exp.get("title"),
                "contractor": exp.get("contractor"),
                "city": exp.get("city"),
                "state": exp.get("state"),
                "evidence_level": exp.get("evidence_level"),
                "individual_cat_not_provided": bool(exp.get("individual_cat_not_provided")),
                "activity": item.get("activity"),
                "service": item.get("service"),
                "quantity": item.get("quantity"),
                "unit": item.get("unit"),
                "original_text": item.get("original_text"),
                "original_description": item.get("original_description"),
                "source_page": item.get("source_page"),
                "source_file": item.get("source_file"),
                "document_id": (doc or {}).get("id"),
                "document_type": (doc or {}).get("document_type"),
                "certificate_number": (doc or {}).get("certificate_number"),
                "art_number": (doc or {}).get("art_number")
                or ((doc or {}).get("art_numbers") or [None])[0],
                "document_status": (doc or {}).get("current_status"),
                "restrictions": list((doc or {}).get("restrictions") or [])
                + list(exp.get("restrictions") or []),
                "review_flags": list((doc or {}).get("review_flags") or []),
                "capability_tags": list(exp.get("capability_tags") or []),
                "blob": full_blob,
            }
        )

    results = rank_item_hits(results)
    return results[:limit]


def search_experiences(
    store: AcervoStore,
    query: str,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Search at experience level (for tombada, galpão, etc.)."""
    syn_map = synonym_map_from_store(store)
    terms = expand_query_terms(query, syn_map)
    out: list[dict[str, Any]] = []
    for exp in store.experiences:
        doc = store.get_document(exp.get("primary_document_id") or "")
        blob = normalize_text(
            " ".join(
                [
                    exp.get("title") or "",
                    exp.get("description") or "",
                    exp.get("contractor") or "",
                    exp.get("city") or "",
                    exp.get("address") or "",
                    " ".join(exp.get("capability_tags") or []).replace("_", " "),
                    " ".join(
                        (i.get("service") or "") + " " + (i.get("original_description") or "")
                        for i in (exp.get("technical_items") or [])
                    ),
                ]
            ).replace("_", " ")
        )
        ok, hits = terms_match_blob(terms, blob)
        if query.strip() and not ok:
            continue
        score = 10 * len(hits) + _evidence_score(exp, doc) + _doc_status_score(doc)
        out.append(
            {
                "score": score,
                "matched_terms": hits,
                "experience_id": exp.get("id"),
                "title": exp.get("title"),
                "contractor": exp.get("contractor"),
                "city": exp.get("city"),
                "state": exp.get("state"),
                "address": exp.get("address"),
                "start_date": exp.get("start_date"),
                "end_date": exp.get("end_date"),
                "contract_value_brl": exp.get("contract_value_brl"),
                "evidence_level": exp.get("evidence_level"),
                "individual_cat_not_provided": bool(exp.get("individual_cat_not_provided")),
                "capability_tags": list(exp.get("capability_tags") or []),
                "linked_documents": list(exp.get("linked_documents") or []),
                "linked_arts": list(exp.get("linked_arts") or []),
                "primary_document_id": exp.get("primary_document_id"),
                "document_type": (doc or {}).get("document_type"),
                "certificate_number": (doc or {}).get("certificate_number"),
                "art_number": (doc or {}).get("art_number"),
                "source_files": list((doc or {}).get("source_files") or []),
                "document_status": (doc or {}).get("current_status"),
                "restrictions": list((doc or {}).get("restrictions") or [])
                + list(exp.get("restrictions") or []),
                "review_flags": list((doc or {}).get("review_flags") or []),
                "item_count": len(exp.get("technical_items") or []),
                "max_quantity": max(
                    (i.get("quantity") or 0 for i in (exp.get("technical_items") or [])),
                    default=None,
                ),
            }
        )
    out.sort(key=lambda r: -r["score"])
    return out[:limit]


def max_quantity_for_service(
    store: AcervoStore,
    service_query: str,
    *,
    unit: str | None = "m2",
    single_work_only: bool = True,
) -> dict[str, Any]:
    """Largest individual quantity for a service (never auto-sums works).

    Only items whose *service* is relevant (exact / multi-word synonym / full
    token coverage on the service blob) participate — experience tags alone
    cannot invent a quantitativo for an unrelated line item.
    """
    hits = search_items(
        store, service_query, unit=unit, limit=200, service_only=True
    )
    relevant = service_relevant_hits(hits) if hits else []
    # Among service-relevant, max quantity; rank preserves exact > score > qty
    if not relevant:
        return {
            "service_query": service_query,
            "unit": unit,
            "max_individual_quantity": None,
            "best": None,
            "candidates": [],
            "sum_note": "Somatório multi-obra não aplicado (default).",
            "allow_sum": False,
        }
    by_qty = sorted(
        relevant,
        key=lambda h: (
            0 if h.get("exact_service_match") else 1,
            -(h.get("score") or 0),
            -(h.get("quantity") or 0),
        ),
    )
    # Canonical max = highest quantity among service-relevant (not among tag noise)
    max_row = max(relevant, key=lambda h: (h.get("quantity") or 0))
    best = by_qty[0]
    # Prefer the highest qty row when scores are comparable and both service-relevant
    if (max_row.get("quantity") or 0) >= (best.get("quantity") or 0):
        best = max_row
    return {
        "service_query": service_query,
        "unit": unit,
        "max_individual_quantity": best.get("quantity"),
        "best": best,
        "candidates": sorted(relevant, key=lambda h: -(h.get("quantity") or 0))[:10],
        "sum_note": "Somatório multi-obra não aplicado (default)."
        if single_work_only
        else "Somatório solicitado explicitamente — ver match_requirement.",
        "allow_sum": False,
    }


def build_search_chunks(store: AcervoStore) -> list[dict[str, Any]]:
    """Generate semantic chunks for document/obra/atividade/serviço/etc."""
    chunks: list[dict[str, Any]] = []
    for doc in store.documents:
        chunks.append(
            {
                "chunk_type": "documento",
                "document_id": doc["id"],
                "text": (
                    f"{doc.get('document_type')} {doc.get('certificate_number')} "
                    f"ART {doc.get('art_number')} status {doc.get('current_status')} "
                    f"fontes {' '.join(doc.get('source_files') or [])} "
                    f"{' '.join(doc.get('restrictions') or [])}"
                ),
                "source_files": list(doc.get("source_files") or []),
                "pages": doc.get("source_pages"),
            }
        )
    for exp in store.experiences:
        primary_doc: dict[str, Any] = (
            store.get_document(exp.get("primary_document_id") or "") or {}
        )
        chunks.append(
            {
                "chunk_type": "obra",
                "experience_id": exp["id"],
                "document_id": exp.get("primary_document_id"),
                "text": (
                    f"{exp.get('title')} contratante {exp.get('contractor')} "
                    f"local {exp.get('city')}/{exp.get('state')} "
                    f"periodo {exp.get('start_date')} a {exp.get('end_date')} "
                    f"evidencia {exp.get('evidence_level')} "
                    f"tags {' '.join(exp.get('capability_tags') or [])} "
                    f"{exp.get('description') or ''}"
                ),
                "source_files": list(primary_doc.get("source_files") or []),
            }
        )
        for item in exp.get("technical_items") or []:
            chunks.append(
                {
                    "chunk_type": "servico",
                    "experience_id": exp["id"],
                    "document_id": item.get("source_document"),
                    "text": (
                        f"atividade {item.get('activity')} servico {item.get('service')} "
                        f"quantitativo {item.get('original_text')} "
                        f"{item.get('original_description')} "
                        f"tipo_evidencia {exp.get('evidence_level')}"
                    ),
                    "quantity": item.get("quantity"),
                    "unit": item.get("unit"),
                    "source_file": item.get("source_file"),
                    "source_page": item.get("source_page"),
                }
            )
        # restrictions / legal notes
        for r in exp.get("restrictions") or []:
            chunks.append(
                {
                    "chunk_type": "restricao",
                    "experience_id": exp["id"],
                    "text": r,
                }
            )
    for doc in store.documents:
        for r in doc.get("restrictions") or []:
            chunks.append(
                {
                    "chunk_type": "restricao_documental",
                    "document_id": doc["id"],
                    "text": r,
                    "source_files": list(doc.get("source_files") or []),
                }
            )
    # Guard: never include CPF / birth date fields (professionals only name/title/crea/rnp)
    for prof in store.professionals:
        chunks.append(
            {
                "chunk_type": "profissional",
                "text": (
                    f"{prof.get('full_name')} {prof.get('title')} "
                    f"CREA-SC {prof.get('crea_sc')} RNP {prof.get('rnp') or ''}"
                ),
            }
        )
    return chunks

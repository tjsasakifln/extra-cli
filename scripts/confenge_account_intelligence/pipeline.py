"""End-to-end pipeline: record → confenge-account-intelligence-v1 dossier."""

from __future__ import annotations

import concurrent.futures
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.confenge_account_intelligence.approach import build_approach_fields
from scripts.confenge_account_intelligence.cache import AccountIntelCache
from scripts.confenge_account_intelligence.catalog import load_catalog
from scripts.confenge_account_intelligence.enrich import EnrichProvider, get_default_provider
from scripts.confenge_account_intelligence.facts import build_epistemic_layers, portfolio_summary, why_now
from scripts.confenge_account_intelligence.models import (
    DOMINANT_STATES,
    SCHEMA_ID,
    SCHEMA_VERSION,
    cache_key,
    cnpj_root,
    stable_source_hash,
)
from scripts.confenge_account_intelligence.normalize import normalize_record
from scripts.confenge_account_intelligence.router import select_services
from scripts.confenge_account_intelligence.structure import build_structure_hypothesis

# Re-export for package API
__all__ = [
    "SCHEMA_ID",
    "SCHEMA_VERSION",
    "build_dossier",
    "process_record",
    "process_batch",
]


def _dominant_state(bag: dict[str, Any]) -> dict[str, Any]:
    state = str(bag.get("commercial_state") or "NEW").upper()
    human = bag.get("human_outcome") if isinstance(bag.get("human_outcome"), dict) else None
    human_status = None
    if human:
        human_status = str(human.get("status") or human.get("outcome") or human.get("state") or "").upper()

    # Human outcome and DO_NOT_CONTACT dominate outreach.
    if human_status and human_status in DOMINANT_STATES:
        return {
            "state": human_status,
            "is_dominant": True,
            "blocks_outreach": True,
            "source": "human_outcome",
            "notes": "Outcome humano dominante — ângulo de serviço gerado para registro, sem autorizar contato.",
        }
    if state in DOMINANT_STATES:
        return {
            "state": state,
            "is_dominant": True,
            "blocks_outreach": True,
            "source": "commercial_state",
            "notes": "Estado comercial dominante preservado no dossiê.",
        }
    if human_status:
        return {
            "state": human_status,
            "is_dominant": False,
            "blocks_outreach": False,
            "source": "human_outcome",
            "notes": "Outcome humano registrado sem bloqueio de outreach.",
        }
    return {
        "state": state or "NEW",
        "is_dominant": False,
        "blocks_outreach": False,
        "source": "commercial_state",
        "notes": None,
    }


def build_dossier(
    raw: dict[str, Any],
    *,
    catalog: dict[str, Any] | None = None,
    as_of: str | None = None,
    enricher: EnrichProvider | None = None,
    use_cache: bool = False,
    cache_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Pure-ish transform with optional FS cache. Offline-safe."""
    cat = catalog if catalog is not None else load_catalog()
    provider = enricher or get_default_provider()
    enriched = provider.enrich(raw)
    source_hash = stable_source_hash(enriched)
    bag = normalize_record(enriched, as_of=as_of)
    root = bag["cnpj_root"]
    as_of_value = bag["as_of"]
    key = cache_key(cnpj_root_value=root, source_hash=source_hash, as_of=as_of_value)

    cache: AccountIntelCache | None = None
    if use_cache:
        cache = AccountIntelCache(cache_dir)
        hit = cache.get(cnpj_root=root, source_hash=source_hash, as_of=as_of_value)
        if hit is not None:
            # Ensure cache metadata is consistent
            hit = dict(hit)
            hit["cache_hit"] = True
            hit["cache_key"] = key
            return hit

    layers = build_epistemic_layers(bag)
    structure = build_structure_hypothesis(bag)
    why = why_now(bag, layers)
    selection = select_services(bag, structure=structure, why=why, catalog=cat)
    approach = build_approach_fields(
        bag,
        structure=structure,
        why=why,
        selection=selection,
        layers=layers,
    )
    dominant = _dominant_state(bag)

    limitations = [
        "Dossiê gerado a partir do input fornecido; não consulta internet no core.",
        "Inferências não são fatos e não devem ser exportadas como confirmadas.",
        "Valores de contrato somam apenas o observado no input.",
    ]
    if dominant.get("blocks_outreach"):
        limitations.append(f"Estado dominante {dominant.get('state')}: não realizar outreach automatizado.")

    dossier: dict[str, Any] = {
        "schema_id": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "catalog_version": str(cat.get("catalog_version") or cat.get("version")),
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "as_of": as_of_value,
        "cnpj_root": root,
        "source_hash": source_hash,
        "cache_key": key,
        "cache_hit": False,
        "account_snapshot": {
            "cnpj14": bag.get("cnpj14"),
            "cnpj_root": root,
            "razao_social": bag.get("razao_social"),
            "nome_fantasia": bag.get("nome_fantasia"),
            "municipio": bag.get("municipio"),
            "uf": bag.get("uf"),
            "cnae_principal": bag.get("cnae_principal"),
            "activity_class": bag.get("activity_class"),
        },
        "portfolio_summary": portfolio_summary(bag),
        "why_now": why,
        "confirmed_facts": layers["confirmed_facts"],
        "strong_inferences": layers["strong_inferences"],
        "weak_inferences": layers["weak_inferences"],
        "internal_structure_hypothesis": structure,
        "primary_service": selection["primary_service"],
        "secondary_service": selection["secondary_service"],
        "service_fit_rationale": selection["service_fit_rationale"],
        "fact_to_mention": approach["fact_to_mention"],
        "question_to_ask": approach["question_to_ask"],
        "cta": approach["cta"],
        "objection_expected": approach["objection_expected"],
        "claims_to_avoid": approach["claims_to_avoid"],
        "message_tone": approach["message_tone"],
        "research_gaps": approach["research_gaps"],
        "evidence": bag.get("evidence") or [],
        "dominant_state": dominant,
        "limitations": limitations,
    }

    if cache is not None:
        cache.put(dossier, cnpj_root=root, source_hash=source_hash, as_of=as_of_value)

    return dossier


def process_record(
    raw: dict[str, Any],
    **kwargs: Any,
) -> dict[str, Any]:
    """Alias of build_dossier for CLI clarity."""
    return build_dossier(raw, **kwargs)


def process_batch(
    records: Iterable[dict[str, Any]],
    *,
    max_workers: int = 4,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """Process many records with limited concurrency. Order preserved."""
    items = list(records)
    if not items:
        return []
    workers = max(1, min(int(max_workers), len(items)))
    if workers == 1:
        return [build_dossier(r, **kwargs) for r in items]

    results: list[dict[str, Any] | None] = [None] * len(items)

    def _job(idx: int, rec: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        return idx, build_dossier(rec, **kwargs)

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_job, i, r) for i, r in enumerate(items)]
        for fut in concurrent.futures.as_completed(futs):
            idx, dossier = fut.result()
            results[idx] = dossier
    return [r for r in results if r is not None]


def resolve_cnpj_from_records(
    records: list[dict[str, Any]],
    cnpj: str,
) -> dict[str, Any] | None:
    """Find a record matching CNPJ root/14 in a list."""
    target = cnpj_root(cnpj)
    for r in records:
        root = cnpj_root(r.get("cnpj14") or r.get("cnpj") or r.get("cnpj_root"))
        if root == target:
            return r
    return None

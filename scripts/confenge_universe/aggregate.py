"""Incremental per-root (or independent-brand) aggregation — bounded memory.

Contracts are folded into entity buckets as they stream in. Full contract
lists are NOT retained for every entity at export time: only summary stats
and a capped recent-contract sample.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from scripts.commercial_leads.sector_fit import ContractHistoryAccumulator
from scripts.confenge_universe.dedupe import (
    EntityKey,
    brand_tokens,
    entity_key_for_establishment,
    prefer_matriz_cnpj,
    should_split_independent_brand,
)
from scripts.confenge_universe.identity import Identity, resolve_identity

RECENT_YEARS = 2
MAX_RECENT_CONTRACTS_SAMPLE = 8
MAX_OBJECT_SNIPPET = 160
MAX_ESTABLISHMENTS = 40
MAX_ALIASES = 20
MAX_ORGAOS = 50
MAX_CATEGORIES = 30


def _parse_date(val: Any) -> date | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, date):
        return val
    s = str(val)[:10]
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _safe_float(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


@dataclass
class EstablishmentAgg:
    cnpj14: str
    razao_social: str
    uf: str | None = None
    municipio: str | None = None
    contract_count: int = 0
    value_total: float = 0.0


@dataclass
class EntityBucket:
    """Mutable streaming aggregate for one operational group.

    Memory is bounded: only min/max contract dates (not per-contract date lists),
    capped classify buffer, capped recent sample, capped orgaos/aliases.
    """

    entity_key: EntityKey
    cnpj_root: str
    identities: dict[str, Identity] = field(default_factory=dict)
    establishments: dict[str, EstablishmentAgg] = field(default_factory=dict)
    aliases: set[str] = field(default_factory=set)
    ufs: set[str] = field(default_factory=set)
    municipios: set[str] = field(default_factory=set)
    orgaos: set[str] = field(default_factory=set)
    object_snippets_pass: list[str] = field(default_factory=list)
    contract_count: int = 0
    value_total: float = 0.0
    value_recent: float = 0.0
    contract_count_recent: int = 0
    active_count: int = 0
    # Bounded temporal envelope — NEVER retain O(n) per-contract date lists
    first_date: date | None = None
    last_date: date | None = None
    recent_sample: list[dict[str, Any]] = field(default_factory=list)
    # Keep raw contracts only while classifying — cleared after finalize if large
    contracts_for_classify: list[dict[str, Any]] = field(default_factory=list)
    max_contracts_for_classify: int = 500
    independent_brand: bool = False
    input_contract_rows: int = 0
    sector_history: ContractHistoryAccumulator = field(
        default_factory=ContractHistoryAccumulator
    )

    def sorted_aliases(self) -> list[str]:
        """Deterministic alias order (set iteration is PYTHONHASHSEED-sensitive)."""
        return sorted(self.aliases)

    def matriz_establishment(self) -> EstablishmentAgg | None:
        """Prefer ordem 0001 (matriz) as geo/name representative."""
        if not self.establishments:
            return None
        for c14 in sorted(self.establishments.keys()):
            if len(c14) == 14 and c14[8:12] == "0001":
                return self.establishments[c14]
        return self.establishments[sorted(self.establishments.keys())[0]]

    def representative_name(self) -> str | None:
        """Stable display name: matriz razao first, else first sorted alias."""
        est = self.matriz_establishment()
        if est and est.razao_social:
            return est.razao_social
        aliases = self.sorted_aliases()
        return aliases[0] if aliases else None

    def add_contract(
        self,
        row: dict[str, Any],
        identity: Identity,
        *,
        as_of: date,
        is_relevant: bool,
        category: str | None = None,
    ) -> None:
        self.input_contract_rows += 1
        self.contract_count += 1
        self.sector_history.add(row)
        valor = _safe_float(row.get("valor_total"))
        self.value_total += valor
        c14 = identity.cnpj14 or ""
        if c14:
            self.identities[c14] = identity
            est = self.establishments.get(c14)
            if est is None:
                est = EstablishmentAgg(
                    cnpj14=c14,
                    razao_social=identity.razao_social,
                    uf=(str(row.get("uf") or "").upper() or None),
                    municipio=row.get("municipio"),
                )
                self.establishments[c14] = est
            est.contract_count += 1
            est.value_total += valor
            if identity.razao_social:
                self.aliases.add(identity.razao_social.strip())

        uf = str(row.get("uf") or "").upper()
        if uf:
            self.ufs.add(uf)
        mun = row.get("municipio")
        if mun:
            self.municipios.add(str(mun).strip())
        org = row.get("orgao_nome") or row.get("orgao_cnpj")
        if org:
            self.orgaos.add(str(org).strip()[:120])

        d = (
            _parse_date(row.get("data_publicacao"))
            or _parse_date(row.get("data_assinatura"))
            or _parse_date(row.get("data_inicio"))
        )
        if d:
            if self.first_date is None or d < self.first_date:
                self.first_date = d
            if self.last_date is None or d > self.last_date:
                self.last_date = d
            cutoff = date(as_of.year - RECENT_YEARS, as_of.month, as_of.day)
            if d >= cutoff:
                self.contract_count_recent += 1
                self.value_recent += valor

        active = row.get("is_active")
        if active is True or str(active).lower() in {"t", "true", "1", "yes"}:
            self.active_count += 1
        fim = _parse_date(row.get("data_fim"))

        if is_relevant and len(self.contracts_for_classify) < self.max_contracts_for_classify:
            self.contracts_for_classify.append(row)
        elif not is_relevant and len(self.contracts_for_classify) < min(
            50, self.max_contracts_for_classify
        ):
            # retain some non-relevant for sector_fit denominator honesty
            self.contracts_for_classify.append(row)

        if is_relevant:
            obj = str(row.get("objeto_contrato") or row.get("objeto") or "")[:MAX_OBJECT_SNIPPET]
            if obj and len(self.object_snippets_pass) < 20:
                self.object_snippets_pass.append(obj)
            sample = {
                "contrato_id": row.get("contrato_id"),
                "orgao_nome": row.get("orgao_nome"),
                "objeto": obj,
                "valor_total": valor if valor else None,
                "uf": uf or None,
                "data_publicacao": d.isoformat() if d else None,
                "data_fim": fim.isoformat() if fim else None,
                "is_active": bool(active) if active is not None else None,
                "category": category,
            }
            self.recent_sample.append(sample)
            # Keep top-N by date then value — bounded
            self.recent_sample.sort(
                key=lambda x: (x.get("data_publicacao") or "", x.get("valor_total") or 0),
                reverse=True,
            )
            self.recent_sample = self.recent_sample[:MAX_RECENT_CONTRACTS_SAMPLE]


class UniverseAggregator:
    """Stream contracts → entity buckets with root dedupe + brand exception."""

    def __init__(self, *, as_of: date, enable_independent_brand: bool = True) -> None:
        self.as_of = as_of
        self.enable_independent_brand = enable_independent_brand
        self.buckets: dict[str, EntityBucket] = {}
        # Track names seen per root for brand-split decisions
        self._root_names: dict[str, set[str]] = defaultdict(set)
        self._root_to_keys: dict[str, set[str]] = defaultdict(set)
        self.stats = {
            "input_contract_rows": 0,
            "identity_exclusions": 0,
            "identity_exclusion_breakdown": defaultdict(int),
        }
        # Roots that were identity-invalid only (no valid cnpj) — counted later
        self.identity_excluded_rows: list[dict[str, Any]] = []
        self._max_identity_excluded_samples = 100

    def _bucket_display_name(self, bucket: EntityBucket) -> str | None:
        """Deterministic name for brand-split comparisons (no set-iter)."""
        return bucket.representative_name()

    def _promote_root_bucket_to_brand(self, root: str) -> None:
        """When first independent brand is detected, re-key the plain-root bucket."""
        plain_key = root
        bucket = self.buckets.get(plain_key)
        if bucket is None or bucket.entity_key.brand_slug:
            return
        name = self._bucket_display_name(bucket)
        new_ek = entity_key_for_establishment(root, name, independent_brand=True)
        new_key = new_ek.key
        if new_key == plain_key or new_key in self.buckets:
            bucket.independent_brand = True
            return
        bucket.entity_key = new_ek
        bucket.independent_brand = True
        self.buckets[new_key] = bucket
        del self.buckets[plain_key]
        keys = self._root_to_keys.get(root) or set()
        keys.discard(plain_key)
        keys.add(new_key)
        self._root_to_keys[root] = keys

    def _resolve_entity_key(
        self, identity: Identity, row: dict[str, Any]
    ) -> EntityKey | None:
        if not identity.valid or not identity.cnpj_root:
            return None
        root = identity.cnpj_root
        name = identity.razao_social
        self._root_names[root].add(name)

        if not self.enable_independent_brand:
            return EntityKey(cnpj_root=root)

        existing_keys = self._root_to_keys.get(root) or set()
        if not existing_keys:
            return EntityKey(cnpj_root=root)

        # Match similar brand → collapse into that bucket
        for k in list(existing_keys):
            bucket = self.buckets.get(k)
            if bucket is None:
                continue
            other_name = self._bucket_display_name(bucket)
            if not should_split_independent_brand(
                name,
                other_name,
                both_have_construction=bool(bucket.object_snippets_pass)
                or bool(bucket.contract_count),
            ):
                return bucket.entity_key

        # Diverges from all existing buckets with construction evidence → split
        any_constr = any(
            bool(self.buckets[k].object_snippets_pass) or self.buckets[k].contract_count > 0
            for k in existing_keys
            if k in self.buckets
        )
        if any_constr:
            # Promote plain-root bucket to its own brand key (first time only)
            self._promote_root_bucket_to_brand(root)
            return entity_key_for_establishment(root, name, independent_brand=True)

        return EntityKey(cnpj_root=root)

    def ingest_batch(
        self,
        batch: list[dict[str, Any]],
        *,
        relevance_fn: Any,
    ) -> None:
        for row in batch:
            self.stats["input_contract_rows"] += 1
            identity = resolve_identity(
                row.get("fornecedor_cnpj"), row.get("fornecedor_nome")
            )
            if not identity.valid:
                self.stats["identity_exclusions"] += 1
                code = identity.exclusion_code or "UNKNOWN"
                self.stats["identity_exclusion_breakdown"][code] += 1
                if len(self.identity_excluded_rows) < self._max_identity_excluded_samples:
                    self.identity_excluded_rows.append(
                        {
                            "tax_id": row.get("fornecedor_cnpj"),
                            "name": row.get("fornecedor_nome"),
                            "code": code,
                            "detail": identity.exclusion_detail,
                        }
                    )
                continue

            rel = relevance_fn(row.get("objeto_contrato") or row.get("objeto"))
            is_relevant = getattr(rel, "status", None) == "PASS"
            category = None
            if is_relevant:
                strong = getattr(rel, "strong_hits", None) or []
                category = strong[0] if strong else "obra_engenharia"

            ek = self._resolve_entity_key(identity, row)
            if ek is None:
                continue
            key = ek.key
            bucket = self.buckets.get(key)
            if bucket is None:
                bucket = EntityBucket(
                    entity_key=ek,
                    cnpj_root=identity.cnpj_root or "",
                    independent_brand=bool(ek.brand_slug),
                )
                self.buckets[key] = bucket
                self._root_to_keys[identity.cnpj_root or ""].add(key)

            bucket.add_contract(
                row, identity, as_of=self.as_of, is_relevant=is_relevant, category=category
            )

    def all_buckets(self) -> list[EntityBucket]:
        return list(self.buckets.values())


def bucket_to_portfolio_dict(bucket: EntityBucket) -> dict[str, Any]:
    first_d = bucket.first_date
    last_d = bucket.last_date
    est_list = sorted(
        (
            {
                "cnpj14": e.cnpj14,
                "razao_social": e.razao_social,
                "uf": e.uf,
                "municipio": e.municipio,
                "contract_count": e.contract_count,
                "value_total": round(e.value_total, 2),
            }
            for e in bucket.establishments.values()
        ),
        key=lambda x: x["cnpj14"],
    )[:MAX_ESTABLISHMENTS]
    rep_name = bucket.representative_name()
    return {
        "contract_count_total": bucket.contract_count,
        "contract_count_recent": bucket.contract_count_recent,
        "value_total_brl": round(bucket.value_total, 2),
        "value_recent_brl": round(bucket.value_recent, 2),
        "orgaos": sorted(bucket.orgaos)[:MAX_ORGAOS],
        "ufs_atuacao": sorted(bucket.ufs),
        "municipios_sample": sorted(bucket.municipios)[:20],
        "object_categories": [],  # filled after construction assess
        "recent_contracts": list(bucket.recent_sample),
        "first_contract_date": first_d.isoformat() if first_d else None,
        "last_contract_date": last_d.isoformat() if last_d else None,
        "active_contract_count": bucket.active_count,
        "establishments": est_list,
        "aliases": bucket.sorted_aliases()[:MAX_ALIASES],
        "representative_cnpj14": prefer_matriz_cnpj(
            [{"cnpj14": e.cnpj14} for e in bucket.establishments.values()]
        ),
        "independent_brand": bucket.independent_brand,
        # Deterministic: tokens from matriz/representative name only
        "brand_tokens": sorted(brand_tokens(rep_name)),
    }

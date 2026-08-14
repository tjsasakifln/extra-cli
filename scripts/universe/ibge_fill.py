"""#301 — fill the 19 included universe rows that lack a 7-digit IBGE code.

Only the municipal IBGE field is written. CNPJ, canonical key, distance,
radius decision and the 1.093 included set stay identical. Ambiguous
municipality names are not guessed.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from scripts.lib.universe import normalize_codigo_ibge

SCHEMA_VERSION = "ibge-fill/1.0"
CATALOG_VERSION = "ibge-municipios-br-2024-sc-overlay"
# Official IBGE municipality code for Florianópolis / SC.
# Source: IBGE territorial division (municípios), UF=SC, nome=Florianópolis.
FLORIANOPOLIS_IBGE = "4205407"

OFFICIAL_MUNICIPAL_CODES: dict[tuple[str, str], str] = {
    ("florianopolis", "sc"): FLORIANOPOLIS_IBGE,
    # Explicit homonym pair used by tests — same name, two UFs, never guessed.
    ("sao jose", "sc"): "4216602",
    ("sao jose", "sp"): "3549904",
}


class IbgeFillError(ValueError):
    """Ambiguous or invalid IBGE enrichment."""


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _fold(value: str | None) -> str:
    decomposed = unicodedata.normalize("NFKD", value or "")
    ascii_text = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(ascii_text.casefold().replace("-", " ").split())


def catalog_hash() -> str:
    payload = {
        "version": CATALOG_VERSION,
        "codes": {f"{name}|{uf}": code for (name, uf), code in sorted(OFFICIAL_MUNICIPAL_CODES.items())},
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass(frozen=True)
class UniverseIbgeRow:
    canonical_entity_key: str
    cnpj: str
    municipio: str
    uf: str
    codigo_ibge: str
    distancia_km: float
    radius_decision: str
    included: bool

    def identity_tuple(self) -> tuple[str, str, float, str, bool]:
        return (
            self.canonical_entity_key,
            self.cnpj,
            self.distancia_km,
            self.radius_decision,
            self.included,
        )


@dataclass(frozen=True)
class FillDecision:
    canonical_entity_key: str
    codigo_ibge: str
    source: str
    method: str
    municipio: str
    uf: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FillReport:
    catalog_version: str
    catalog_hash: str
    as_of: str
    method: str
    filled: tuple[FillDecision, ...]
    skipped: tuple[str, ...]
    blockers: tuple[str, ...]
    included_before: int
    included_after: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "catalog_version": self.catalog_version,
            "catalog_hash": self.catalog_hash,
            "as_of": self.as_of,
            "method": self.method,
            "filled": [f.as_dict() for f in self.filled],
            "skipped": list(self.skipped),
            "blockers": list(self.blockers),
            "included_before": self.included_before,
            "included_after": self.included_after,
        }


def lookup_official_ibge(municipio: str, uf: str) -> str:
    name = _fold(municipio)
    state = _fold(uf)
    if not name:
        raise IbgeFillError("municipio_empty")
    if not state:
        matches = [code for (n, _uf), code in OFFICIAL_MUNICIPAL_CODES.items() if n == name]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise IbgeFillError(f"ambiguous_municipio:{municipio}")
        raise IbgeFillError(f"unknown_municipio:{municipio}")
    code = OFFICIAL_MUNICIPAL_CODES.get((name, state))
    if not code:
        raise IbgeFillError(f"unknown_municipio:{municipio}/{uf}")
    if not normalize_codigo_ibge(code):
        raise IbgeFillError(f"invalid_official_code:{code}")
    return code


def list_missing_included(rows: tuple[UniverseIbgeRow, ...]) -> tuple[UniverseIbgeRow, ...]:
    return tuple(r for r in rows if r.included and not normalize_codigo_ibge(r.codigo_ibge))


def apply_ibge_fill(
    rows: tuple[UniverseIbgeRow, ...],
    *,
    as_of: str | None = None,
    only_municipio: str | None = None,
) -> tuple[tuple[UniverseIbgeRow, ...], FillReport]:
    """Return enriched rows plus a nominal report. Identity fields are untouched."""
    included_before = sum(1 for r in rows if r.included)
    missing = list_missing_included(rows)
    if only_municipio:
        missing = tuple(r for r in missing if _fold(r.municipio) == _fold(only_municipio))
    filled: list[FillDecision] = []
    skipped: list[str] = []
    blockers: list[str] = []
    by_key = {r.canonical_entity_key: r for r in rows}
    for row in missing:
        try:
            code = lookup_official_ibge(row.municipio, row.uf)
        except IbgeFillError as exc:
            blockers.append(f"{row.canonical_entity_key}:{exc}")
            continue
        if row.uf and _fold(row.uf) not in {"sc", "santa catarina"} and _fold(row.municipio) == "florianopolis":
            blockers.append(f"{row.canonical_entity_key}:refuses_cross_uf_guess")
            continue
        filled.append(
            FillDecision(
                canonical_entity_key=row.canonical_entity_key,
                codigo_ibge=code,
                source="IBGE-DTB-municipios",
                method="exact_municipio_uf",
                municipio=row.municipio,
                uf=row.uf,
            )
        )
        by_key[row.canonical_entity_key] = UniverseIbgeRow(
            canonical_entity_key=row.canonical_entity_key,
            cnpj=row.cnpj,
            municipio=row.municipio,
            uf=row.uf,
            codigo_ibge=code,
            distancia_km=row.distancia_km,
            radius_decision=row.radius_decision,
            included=row.included,
        )

    enriched = tuple(by_key[r.canonical_entity_key] for r in rows)
    included_after = sum(1 for r in enriched if r.included)
    if included_after != included_before:
        raise IbgeFillError("included_set_size_changed")
    before_ids = {r.identity_tuple() for r in rows if r.included}
    after_ids = {r.identity_tuple() for r in enriched if r.included}
    if before_ids != after_ids:
        raise IbgeFillError("identity_or_radius_changed")
    report = FillReport(
        catalog_version=CATALOG_VERSION,
        catalog_hash=catalog_hash(),
        as_of=as_of or _utc_now(),
        method="exact_municipio_uf",
        filled=tuple(filled),
        skipped=tuple(skipped),
        blockers=tuple(blockers),
        included_before=included_before,
        included_after=included_after,
    )
    if blockers:
        raise IbgeFillError(";".join(blockers))
    return enriched, report


def rows_from_canonical_universe() -> tuple[UniverseIbgeRow, ...]:
    """Adapter over the shipped seed. Fill logic does not depend on openpyxl internals."""
    from scripts.lib.universe import load_canonical_universe, resolve_default_seed_path

    universe = load_canonical_universe(seed_path=resolve_default_seed_path())
    rows: list[UniverseIbgeRow] = []
    for entity in universe.entities:
        rows.append(
            UniverseIbgeRow(
                canonical_entity_key=entity.entity_id,
                cnpj=entity.cnpj8,
                municipio=entity.municipio or "",
                uf="SC",
                codigo_ibge=entity.codigo_ibge or "",
                distancia_km=float(entity.distancia_km or 0.0),
                radius_decision=entity.radius_decision,
                included=entity.radius_decision == "included",
            )
        )
    return tuple(rows)

"""Índices e match do universo canônico (target_entities_200km)."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from scripts.ops.multi_source_open_pack.models import BuyerEntity
from scripts.ops.multi_source_open_pack.textutil import cnpj8, digits_only, norm, optional_float


def load_universe(path: Path) -> list[BuyerEntity]:
    if not path.is_file():
        return []
    entities: list[BuyerEntity] = []
    with path.open(encoding="utf-8", newline="") as f:
        for i, row in enumerate(csv.DictReader(f)):
            c = digits_only(row.get("cnpj") or "")
            c8 = c[:8] if len(c) >= 8 else c.zfill(8) if c else f"noid{i:05d}"
            lat = optional_float(row.get("lat"))
            lon = optional_float(row.get("lon"))
            dist = optional_float(row.get("distance_km"))
            name = (row.get("canonical_name") or row.get("name") or "").strip()
            entities.append(
                BuyerEntity(
                    entity_key=c8,
                    cnpj=c,
                    cnpj8=c8,
                    name=(row.get("name") or name).strip(),
                    canonical_name=name,
                    municipio=(row.get("municipio") or "").strip(),
                    uf=(row.get("uf") or "SC").strip(),
                    ibge_code=(row.get("ibge_code") or "").strip(),
                    lat=lat,
                    lon=lon,
                    distance_km=dist,
                    zone=(row.get("zone") or "").strip(),
                    distance_method="universe_seed_geodesic_from_florianopolis",
                )
            )
    return entities


def build_indexes(
    entities: list[BuyerEntity],
) -> tuple[dict[str, BuyerEntity], set[str], dict[str, BuyerEntity], set[str]]:
    by_cnpj8: dict[str, BuyerEntity] = {}
    names: set[str] = set()
    by_name: dict[str, BuyerEntity] = {}
    municipios: set[str] = set()
    for e in entities:
        if e.cnpj8:
            # prefer first; keep closest if multiple
            prev = by_cnpj8.get(e.cnpj8)
            if prev is None or (
                e.distance_km is not None
                and (prev.distance_km is None or e.distance_km < prev.distance_km)
            ):
                by_cnpj8[e.cnpj8] = e
        n = norm(e.canonical_name or e.name)
        if n:
            names.add(n)
            by_name.setdefault(n, e)
        m = norm(e.municipio)
        if m:
            municipios.add(m)
    return by_cnpj8, names, by_name, municipios


def match_universe(
    *,
    cnpj: str | None,
    orgao: str | None,
    municipio: str | None,
    by_cnpj8: dict[str, BuyerEntity],
    names: set[str],
    by_name: dict[str, BuyerEntity],
    municipios: set[str],
) -> tuple[bool, str, BuyerEntity | None]:
    c8 = cnpj8(cnpj)
    if c8 and c8 in by_cnpj8:
        return True, "cnpj8", by_cnpj8[c8]
    on = norm(orgao or "")
    if on and on in by_name:
        return True, "orgao_name", by_name[on]
    if on and len(on) >= 12:
        for n, ent in by_name.items():
            if on in n or n in on:
                return True, "orgao_name_partial", ent
    mn = norm(municipio or "")
    if mn and mn in municipios:
        # municipio-only is weak: mark as match but without unique entity
        # Prefer not to invent distance — leave entity None unless unique
        return True, "municipio", None
    return False, "out_of_universe", None


def annotate_observation_universe(
    obs: Any,
    *,
    by_cnpj8: dict[str, BuyerEntity],
    names: set[str],
    by_name: dict[str, BuyerEntity],
    municipios: set[str],
) -> None:
    ok, how, ent = match_universe(
        cnpj=obs.orgao_cnpj,
        orgao=obs.orgao,
        municipio=obs.municipio,
        by_cnpj8=by_cnpj8,
        names=names,
        by_name=by_name,
        municipios=municipios,
    )
    obs.in_universe = ok
    obs.match_universo = how
    if ent is not None:
        obs.distance_km = ent.distance_km
        obs.distance_method = ent.distance_method
        obs.entity_key = ent.entity_key
        if not obs.municipio and ent.municipio:
            obs.municipio = ent.municipio
    else:
        obs.entity_key = cnpj8(obs.orgao_cnpj) or ""

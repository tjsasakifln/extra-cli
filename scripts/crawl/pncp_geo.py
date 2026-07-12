from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from scripts.crawl.pncp_contract import digits_only, normalize_text
from scripts.lib.geocode import haversine

FLORIANOPOLIS_LAT = float(os.getenv("FLORIANOPOLIS_LAT", "-27.5954"))
FLORIANOPOLIS_LON = float(os.getenv("FLORIANOPOLIS_LON", "-48.5480"))
PRIORITY_RADIUS_KM = float(os.getenv("PRIORITY_RADIUS_KM", "200"))


@dataclass
class LocationResolution:
    codigo_municipio_ibge: str | None
    municipio: str | None
    uf: str | None
    latitude: float | None
    longitude: float | None
    distance_from_florianopolis_km: float | None
    within_200km: bool
    geographic_priority: str
    location_confidence: str


class GeographyResolver:
    def __init__(self, entities: list[dict[str, Any]]):
        self.by_cnpj8: dict[str, dict[str, Any]] = {}
        self.by_ibge: dict[str, dict[str, Any]] = {}
        self.by_municipio: dict[str, dict[str, Any]] = {}

        for entity in entities:
            cnpj8 = digits_only(entity.get("cnpj_8"))[:8]
            if cnpj8:
                self.by_cnpj8.setdefault(cnpj8, entity)

            ibge = digits_only(entity.get("codigo_ibge"))
            if ibge and entity.get("latitude") is not None and entity.get("longitude") is not None:
                self.by_ibge.setdefault(ibge, entity)

            municipio = normalize_text(entity.get("municipio"))
            if municipio and entity.get("latitude") is not None and entity.get("longitude") is not None:
                self.by_municipio.setdefault(municipio, entity)

    def resolve(self, record: dict[str, Any]) -> LocationResolution:
        uf = (record.get("uf") or "").upper() or None
        ibge = digits_only(record.get("codigo_municipio_ibge"))
        municipio = record.get("municipio")
        orgao_cnpj = digits_only(record.get("orgao_cnpj"))

        entity = None
        confidence = "nao_confirmada"

        if ibge and ibge in self.by_ibge:
            entity = self.by_ibge[ibge]
            confidence = "codigo_ibge_pncp"
        elif municipio and normalize_text(municipio) in self.by_municipio:
            entity = self.by_municipio[normalize_text(municipio)]
            confidence = "municipio_unidade_compradora"
        elif len(orgao_cnpj) >= 8 and orgao_cnpj[:8] in self.by_cnpj8:
            entity = self.by_cnpj8[orgao_cnpj[:8]]
            confidence = "cnpj_sc_public_entities"

        latitude = entity.get("latitude") if entity else None
        longitude = entity.get("longitude") if entity else None
        resolved_ibge = ibge or (entity.get("codigo_ibge") if entity else None)
        resolved_municipio = municipio or (entity.get("municipio") if entity else None)

        distance = None
        within = False
        priority = "LOCALIZACAO_NAO_CONFIRMADA"

        if uf and uf != "SC":
            priority = "FORA_DO_ESCOPO"
        elif latitude is not None and longitude is not None:
            distance = round(haversine(FLORIANOPOLIS_LAT, FLORIANOPOLIS_LON, float(latitude), float(longitude)), 2)
            within = distance <= PRIORITY_RADIUS_KM
            priority = "PRIORIDADE_1" if within else "PRIORIDADE_2"
        elif uf == "SC":
            priority = "LOCALIZACAO_NAO_CONFIRMADA"

        return LocationResolution(
            codigo_municipio_ibge=resolved_ibge or None,
            municipio=resolved_municipio,
            uf=uf,
            latitude=float(latitude) if latitude is not None else None,
            longitude=float(longitude) if longitude is not None else None,
            distance_from_florianopolis_km=distance,
            within_200km=within,
            geographic_priority=priority,
            location_confidence=confidence,
        )

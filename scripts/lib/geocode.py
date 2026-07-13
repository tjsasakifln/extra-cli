"""
Modulo de geocoding para entes publicos de Santa Catarina.

Niveis:
1. Cache local (data/geocode_cache.json)
2. IBGE API (nome do municipio por codigo_ibge)
3. Nominatim/OSM (coordenadas por nome do municipio)

Uso:
    from scripts.lib.geocode import Geocoder
    g = Geocoder()
    lat, lon, method = g.geocode(ibge='4205407', municipio='Florianopolis')
"""

from __future__ import annotations

import json
import logging
import math
import os
import time
from datetime import datetime
from typing import Any

import requests

log = logging.getLogger(__name__)

CACHE_FILE = "data/geocode_cache.json"
IBGE_API_URL = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios/{ibge}"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_RATE = 1.0  # 1 request per second (OSM policy)
USER_AGENT = "ExtraConsultoria/1.0 (coverage-analysis)"

# Bounding box de Santa Catarina
SC_BBOX = {
    "min_lat": -29.5,
    "max_lat": -25.5,
    "min_lon": -53.5,
    "max_lon": -48.0,
}

# Coordenadas de Florianopolis (sede administrativa de SC)
FLORIANOPOLIS = (-27.5954, -48.5480)
EARTH_RADIUS_KM = 6371


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calcula distancia em km entre dois pontos geograficos (formula de Haversine).

    Args:
        lat1, lon1: Coordenadas do ponto 1 (em graus decimais).
        lat2, lon2: Coordenadas do ponto 2 (em graus decimais).

    Returns:
        Distancia em quilometros.
    """
    # Converter graus decimais para radianos
    lat1_r, lon1_r, lat2_r, lon2_r = map(math.radians, [lat1, lon1, lat2, lon2])

    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r

    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return EARTH_RADIUS_KM * c


def validate_coords(lat: float, lon: float) -> bool:
    """Valida se coordenadas estao dentro do bounding box de SC.

    Args:
        lat: Latitude em graus decimais.
        lon: Longitude em graus decimais.

    Returns:
        True se estiver dentro do bounding box de Santa Catarina.
    """
    return SC_BBOX["min_lat"] <= lat <= SC_BBOX["max_lat"] and SC_BBOX["min_lon"] <= lon <= SC_BBOX["max_lon"]


class Geocoder:
    """Geocodificador com cache e fallback em niveis.

    Nivel 1: Cache local (data/geocode_cache.json)
    Nivel 2: IBGE API (nome oficial do municipio por codigo_ibge)
    Nivel 3: Nominatim OpenStreetMap (coordenadas por nome do municipio)
    """

    def __init__(self, cache_file: str = CACHE_FILE):
        self.cache = self._load_cache(cache_file)
        self.cache_file = cache_file
        self._last_nominatim_time = 0.0
        self.stats = {"cache_hit": 0, "ibge_api": 0, "nominatim": 0, "failed": 0}

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    def _load_cache(self, path: str) -> dict[str, Any]:
        """Carrega o cache de coordenadas de arquivo JSON.

        Realiza migracao automatica do formato legado:
        - Formato antigo: {"municipio|UF": [lat, lon]}
        - Formato novo:   {"codigo_ibge": {"municipio": ..., "lat": ..., "lon": ..., "method": ...}}
        """
        if not os.path.exists(path):
            return {}

        with open(path) as f:
            try:
                data: dict = json.load(f)
            except (json.JSONDecodeError, ValueError):
                log.warning("Cache corrompido em %s — resetando cache", path)
                return {}

        # Migrar formato legado para novo formato
        migrated = False
        for key, value in list(data.items()):
            if isinstance(value, list) and len(value) == 2:
                municipio_nome = key.split("|")[0] if "|" in key else key
                data[key] = {
                    "municipio": municipio_nome,
                    "lat": value[0],
                    "lon": value[1],
                    "method": "legacy_cache",
                    "cached_at": datetime.now().isoformat(),
                }
                migrated = True

        if migrated:
            log.info(
                "Cache migrado do formato legado para novo formato (%d entradas)",
                sum(1 for v in data.values() if isinstance(v, dict) and v.get("method") == "legacy_cache"),
            )

        return data

    def _save_cache(self) -> None:
        """Persiste o cache em arquivo JSON."""
        os.makedirs(os.path.dirname(self.cache_file) or ".", exist_ok=True)
        with open(self.cache_file, "w") as f:
            json.dump(self.cache, f, indent=2, ensure_ascii=False)

    # ------------------------------------------------------------------
    # Geocoding methods
    # ------------------------------------------------------------------

    def geocode(
        self,
        ibge: str | None = None,
        municipio: str | None = None,
    ) -> tuple[float | None, float | None, str]:
        """Retorna (lat, lon, method) para um municipio.

        Nivel 1: Cache local (por codigo_ibge ou nome do municipio)
        Nivel 2: IBGE API (nome oficial do municipio — NAO retorna coordenadas)
        Nivel 3: Nominatim (coordenadas por nome do municipio)

        Args:
            ibge: Codigo IBGE de 7 digitos do municipio.
            municipio: Nome do municipio.

        Returns:
            Tupla (lat, lon, method). method indica a origem:
            - 'cache'      — acertou no cache local
            - 'nominatim'  — geocodificado via OpenStreetMap
            - 'failed'     — nao foi possivel geocodificar
            - 'out_of_bounds' — coordenadas fora do bounding box SC
        """
        # Nivel 1: Cache local
        cache_key = ibge or municipio
        if cache_key and cache_key in self.cache:
            entry = self.cache[cache_key]
            if isinstance(entry, dict) and entry.get("lat") is not None and entry.get("lon") is not None:
                self.stats["cache_hit"] += 1
                return entry["lat"], entry["lon"], "cache"

        if not municipio:
            self.stats["failed"] += 1
            return None, None, "failed"

        # Nivel 2: IBGE API (obter nome oficial do municipio)
        municipio_nome = municipio
        if ibge:
            try:
                url = IBGE_API_URL.format(ibge=ibge)
                resp = requests.get(url, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    municipio_nome = data.get("nome", municipio)
                    self.stats["ibge_api"] += 1
                else:
                    log.warning("IBGE API retornou status %s para IBGE %s", resp.status_code, ibge)
            except requests.RequestException as e:
                log.warning("IBGE API falhou para IBGE %s: %s", ibge, e)

        # Nivel 3: Nominatim (OpenStreetMap)
        if municipio_nome:
            try:
                # Rate limit: 1 req/s (politica do OSM)
                elapsed = time.time() - self._last_nominatim_time
                if elapsed < NOMINATIM_RATE:
                    time.sleep(NOMINATIM_RATE - elapsed)

                query = f"{municipio_nome}, SC, Brazil"
                params = {
                    "q": query,
                    "format": "json",
                    "limit": 1,
                    "countrycodes": "br",
                    "bounded": 1,
                    "viewbox": (f"{SC_BBOX['min_lon']},{SC_BBOX['min_lat']},{SC_BBOX['max_lon']},{SC_BBOX['max_lat']}"),
                }
                headers = {"User-Agent": USER_AGENT}

                resp = requests.get(NOMINATIM_URL, params=params, headers=headers, timeout=10)
                self._last_nominatim_time = time.time()

                if resp.status_code == 200:
                    results = resp.json()
                    if results:
                        data = results[0]
                        lat, lon = float(data["lat"]), float(data["lon"])

                        # Validar bounding box
                        if not validate_coords(lat, lon):
                            log.warning(
                                "Coordenadas fora do bounding box SC para %s: (%s, %s)",
                                municipio_nome,
                                lat,
                                lon,
                            )
                            self.stats["failed"] += 1
                            return None, None, "out_of_bounds"

                        # Salvar no cache
                        final_key = ibge or municipio_nome
                        self.cache[final_key] = {
                            "municipio": municipio_nome,
                            "lat": lat,
                            "lon": lon,
                            "method": "nominatim",
                            "cached_at": datetime.now().isoformat(),
                        }
                        self._save_cache()

                        self.stats["nominatim"] += 1
                        return lat, lon, "nominatim"
                else:
                    log.warning(
                        "Nominatim retornou status %s para %s",
                        resp.status_code,
                        municipio_nome,
                    )

            except requests.RequestException as e:
                log.warning("Nominatim falhou para %s: %s", municipio_nome, e)
            except (ValueError, KeyError, IndexError) as e:
                log.warning("Erro ao parsear resposta Nominatim para %s: %s", municipio_nome, e)

        self.stats["failed"] += 1
        return None, None, "failed"

    def geocode_batch(self, entities: list[dict]) -> dict[str, Any]:
        """Geocodifica uma lista de entidades, agrupando por municipio.

        Agrupa entidades por codigo_ibge para evitar N chamadas externas
        para entidades do mesmo municipio. Cada municipio unico gera no
        maximo 1 chamada Nominatim.

        Args:
            entities: Lista de dicts com 'id', 'codigo_ibge', 'municipio'.

        Returns:
            Dict com estatisticas:
            - geocoded: numero de municipios geocodificados com sucesso
            - failed: numero de municipios que falharam
            - total_municipios: total de municipios unicos processados
            - total_entities: total de entidades recebidas
            - updated_ids: lista de IDs de entidades com geocoding bem-sucedido
        """
        # Agrupar por codigo_ibge (ou municipio como fallback)
        municipios: dict[str, dict] = {}
        for ent in entities:
            key = ent.get("codigo_ibge") or ent.get("municipio")
            if key is None:
                continue  # ente sem identificacao geografica — impossivel geocodificar
            if key not in municipios:
                municipios[key] = {
                    "ibge": ent.get("codigo_ibge"),
                    "municipio": ent.get("municipio"),
                    "entity_ids": [],
                }
            municipios[key]["entity_ids"].append(ent["id"])

        log.info(
            "Agrupados %d entidades em %d municipios unicos",
            len(entities),
            len(municipios),
        )

        results: dict[str, Any] = {
            "geocoded": 0,
            "failed": 0,
            "total_municipios": len(municipios),
            "total_entities": len(entities),
            "updated_ids": [],
        }

        for key, mun in municipios.items():
            lat, lon, method = self.geocode(ibge=mun["ibge"], municipio=mun["municipio"])

            if lat is not None and lon is not None:
                results["geocoded"] += 1
                results["updated_ids"].extend(mun["entity_ids"])
            else:
                results["failed"] += 1
                log.warning("Falha ao geocodificar municipio: %s (metodo=%s)", key, method)

        return results

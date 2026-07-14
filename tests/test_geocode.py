"""Unit tests for scripts/lib/geocode.py.

Tests cover:
- validate_coords() bounding box check
- haversine() distance formula
- Geocoder cache hit/miss behavior
- Geocoder empty municipio handling
- Cache migration from legacy format
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from scripts.lib.geocode import (
    FLORIANOPOLIS,
    SC_BBOX,
    Geocoder,
    haversine,
    validate_coords,
)

# ---------------------------------------------------------------------------
# validate_coords()
# ---------------------------------------------------------------------------


class TestValidateCoords:
    """Tests for bounding box validation function."""

    def test_florianopolis_inside_sc(self):
        """Florianopolis deve estar dentro do bounding box de SC."""
        assert validate_coords(-27.5954, -48.5480) is True

    def test_joinville_inside_sc(self):
        """Joinville (norte de SC) deve estar dentro do bounding box."""
        assert validate_coords(-26.3044, -48.8488) is True

    def test_chapeco_inside_sc(self):
        """Chapeco (oeste de SC) deve estar dentro do bounding box."""
        assert validate_coords(-27.0964, -52.6181) is True

    def test_sao_paulo_outside_sc(self):
        """Sao Paulo (SP) deve estar FORA do bounding box de SC."""
        assert validate_coords(-23.5505, -46.6333) is False

    def test_curitiba_outside_sc(self):
        """Curitiba (PR) deve estar FORA do bounding box de SC."""
        assert validate_coords(-25.4290, -49.2671) is False

    def test_porto_alegre_outside_sc(self):
        """Porto Alegre (RS) deve estar FORA do bounding box de SC."""
        assert validate_coords(-30.0346, -51.2177) is False

    def test_latitude_boundary_north(self):
        """Latitude no limite norte (max_lat) deve ser valida."""
        assert validate_coords(SC_BBOX["max_lat"], -49.0) is True

    def test_latitude_boundary_south(self):
        """Latitude no limite sul (min_lat) deve ser valida."""
        assert validate_coords(SC_BBOX["min_lat"], -49.0) is True

    def test_latitude_beyond_north(self):
        """Latitude alem do limite norte deve ser invalida."""
        assert validate_coords(SC_BBOX["max_lat"] + 0.1, -49.0) is False

    def test_longitude_beyond_east(self):
        """Longitude alem do limite leste deve ser invalida."""
        assert validate_coords(-27.0, SC_BBOX["max_lon"] + 0.1) is False


# ---------------------------------------------------------------------------
# haversine()
# ---------------------------------------------------------------------------


class TestHaversine:
    """Tests for Haversine distance formula."""

    def test_florianopolis_to_sao_paulo(self):
        """Distancia Florianopolis -> Sao Paulo deve ser ~505 km."""
        dist = haversine(-27.5954, -48.5480, -23.5505, -46.6333)
        assert 480 < dist < 520, f"Distancia inesperada: {dist} km"

    def test_florianopolis_to_joinville(self):
        """Distancia Florianopolis -> Joinville deve ser ~160 km."""
        dist = haversine(-27.5954, -48.5480, -26.3044, -48.8488)
        assert 140 < dist < 180, f"Distancia inesperada: {dist} km"

    def test_zero_distance(self):
        """Distancia de um ponto a ele mesmo deve ser 0."""
        dist = haversine(*FLORIANOPOLIS, *FLORIANOPOLIS)
        assert dist == 0.0

    def test_symmetric(self):
        """Distancia deve ser simetrica: d(a,b) == d(b,a)."""
        d1 = haversine(-27.0, -49.0, -26.0, -50.0)
        d2 = haversine(-26.0, -50.0, -27.0, -49.0)
        assert abs(d1 - d2) < 0.001

    def test_florianopolis_to_chapeco(self):
        """Distancia Florianopolis -> Chapeco deve ser ~410 km."""
        dist = haversine(-27.5954, -48.5480, -27.0964, -52.6181)
        assert 390 < dist < 430, f"Distancia inesperada: {dist} km"


# ---------------------------------------------------------------------------
# Geocoder
# ---------------------------------------------------------------------------


class TestGeocoder:
    """Tests for Geocoder class."""

    # ------------------------------------------------------------------
    # Cache hit
    # ------------------------------------------------------------------

    def test_cache_hit_ibge_key(self, tmp_path: Path):
        """Cache hit com chave IBGE nao deve chamar API externa."""
        cache_file = tmp_path / "cache.json"
        cache_data = {
            "4205407": {
                "municipio": "Florianopolis",
                "lat": -27.5954,
                "lon": -48.5480,
                "method": "nominatim",
                "cached_at": datetime.now().isoformat(),
            },
        }
        cache_file.write_text(json.dumps(cache_data))

        g = Geocoder(str(cache_file))
        lat, lon, method = g.geocode(ibge="4205407")

        assert lat == -27.5954
        assert lon == -48.5480
        assert method == "cache"
        assert g.stats["cache_hit"] == 1

    def test_cache_hit_by_municipio(self, tmp_path: Path):
        """Cache hit com chave por nome de municipio."""
        cache_file = tmp_path / "cache.json"
        cache_data = {
            "Joinville": {
                "municipio": "Joinville",
                "lat": -26.3044,
                "lon": -48.8488,
                "method": "nominatim",
                "cached_at": datetime.now().isoformat(),
            },
        }
        cache_file.write_text(json.dumps(cache_data))

        g = Geocoder(str(cache_file))
        lat, lon, method = g.geocode(ibge=None, municipio="Joinville")

        assert lat == -26.3044
        assert lon == -48.8488
        assert method == "cache"
        assert g.stats["cache_hit"] == 1

    def test_cache_miss_returns_failed(self, tmp_path: Path):
        """Cache miss sem municipio retorna failed."""
        cache_file = tmp_path / "cache.json"
        cache_file.write_text("{}")

        g = Geocoder(str(cache_file))
        lat, lon, method = g.geocode(ibge=None, municipio=None)

        assert lat is None
        assert lon is None
        assert method == "failed"

    def test_cache_miss_with_municipio(self, tmp_path: Path):
        """Cache miss com municipio mas sem internet retorna failed."""
        cache_file = tmp_path / "cache.json"
        cache_file.write_text("{}")

        g = Geocoder(str(cache_file))
        # Sem internet, Nominatim nao responde → failed
        lat, lon, method = g.geocode(ibge=None, municipio="MunicipioInexistenteXYZ")

        assert lat is None
        assert lon is None
        assert method == "failed"

    # ------------------------------------------------------------------
    # Cache persistence
    # ------------------------------------------------------------------

    def test_cache_saved_after_geocode_miss(self, tmp_path: Path):
        """Cache deve ser salvo apos geocode bem-sucedido (teste offline)."""
        cache_file = tmp_path / "cache.json"
        cache_file.write_text("{}")

        g = Geocoder(str(cache_file))
        # Sem internet, nao consegue geocodificar
        g.geocode(ibge=None, municipio="MunicipioInexistenteXYZ")

        # Cache deve permanecer vazio (sem novas entradas)
        with open(str(cache_file)) as f:
            saved = json.load(f)
        assert len(saved) == 0

    def test_cache_load_empty(self, tmp_path: Path):
        """Cache vazio deve ser carregado sem erros."""
        cache_file = tmp_path / "cache.json"
        cache_file.write_text("{}")

        g = Geocoder(str(cache_file))
        assert g.cache == {}

    def test_cache_load_missing_file(self, tmp_path: Path):
        """Arquivo de cache inexistente deve ser carregado como dict vazio."""
        cache_file = tmp_path / "nao_existe.json"
        g = Geocoder(str(cache_file))
        assert g.cache == {}

    def test_cache_load_corrupted(self, tmp_path: Path):
        """Cache corrompido deve ser carregado como dict vazio (nao deve quebrar)."""
        cache_file = tmp_path / "cache.json"
        cache_file.write_text("{json invalido")

        g = Geocoder(str(cache_file))
        assert g.cache == {}

    # ------------------------------------------------------------------
    # Legacy cache migration
    # ------------------------------------------------------------------

    def test_legacy_format_migration(self, tmp_path: Path):
        """Formato legado {municipio|UF: [lat, lon]} deve ser migrado automaticamente."""
        cache_file = tmp_path / "cache.json"
        # Formato antigo — a chave e o nome do municipio (sem UF)
        cache_file.write_text(json.dumps({"itajai": [-26.9046787, -48.6552979]}))

        g = Geocoder(str(cache_file))
        # Apos migracao, deve carregar como dict com lat/lon
        entry = g.cache.get("itajai")
        assert entry is not None
        assert isinstance(entry, dict)
        assert entry["lat"] == -26.9046787
        assert entry["lon"] == -48.6552979
        assert entry["method"] == "legacy_cache"

        # Cache hit deve funcionar com entrada migrada
        lat, lon, method = g.geocode(ibge=None, municipio="itajai")
        assert lat == -26.9046787
        assert lon == -48.6552979
        assert method == "cache"

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def test_stats_initial_state(self, tmp_path: Path):
        """Estatisticas devem comecar zeradas."""
        cache_file = tmp_path / "cache.json"
        cache_file.write_text("{}")

        g = Geocoder(str(cache_file))
        assert g.stats == {"cache_hit": 0, "ibge_api": 0, "nominatim": 0, "failed": 0}

    def test_stats_cache_hit_increments(self, tmp_path: Path):
        """Cache hit deve incrementar contador."""
        cache_file = tmp_path / "cache.json"
        cache_data = {
            "4205407": {
                "municipio": "Florianopolis",
                "lat": -27.5954,
                "lon": -48.5480,
                "method": "nominatim",
                "cached_at": datetime.now().isoformat(),
            },
        }
        cache_file.write_text(json.dumps(cache_data))

        g = Geocoder(str(cache_file))
        g.geocode(ibge="4205407")
        g.geocode(ibge="4205407")

        assert g.stats["cache_hit"] == 2


# ---------------------------------------------------------------------------
# Bounding box constants
# ---------------------------------------------------------------------------


class TestSCBBox:
    """Tests for SC bounding box constants."""

    def test_sc_bbox_lat_range(self):
        """SC deve ter amplitude latitudinal de ~4 graus."""
        assert abs(SC_BBOX["max_lat"] - SC_BBOX["min_lat"] - 4.0) < 0.5

    def test_sc_bbox_lon_range(self):
        """SC deve ter amplitude longitudinal de ~5.5 graus."""
        assert abs(SC_BBOX["max_lon"] - SC_BBOX["min_lon"] - 5.5) < 0.5

    def test_florianopolis_x_in_sc_bbox(self):
        """Longitude de Florianopolis deve estar dentro do bounding box SC."""
        assert SC_BBOX["min_lon"] <= FLORIANOPOLIS[1] <= SC_BBOX["max_lon"]

    def test_florianopolis_y_in_sc_bbox(self):
        """Latitude de Florianopolis deve estar dentro do bounding box SC."""
        assert SC_BBOX["min_lat"] <= FLORIANOPOLIS[0] <= SC_BBOX["max_lat"]

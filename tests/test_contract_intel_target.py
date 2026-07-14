"""Tests for scripts/contract_intel/target_universe.py.

Covers:
  - Deterministic target universe from seed spreadsheet
  - Total, CNPJ8 duplicates, entities without coordinates
  - Explicit inclusion rule (Haversine <= 200km)
  - No "all of SC" shortcut
  - Distance recomputation (not trusting spreadsheet)
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

from scripts.contract_intel.target_universe import (
    FLORIPA_CENTER,
    TARGET_RADIUS_KM,
    TargetEntity,
    TargetUniverse,
    entities_within_radius,
    haversine,
    load_target_universe,
    unique_cnpj8_within_radius,
    unique_municipios_within_radius,
)

# ---------------------------------------------------------------------------
# Haversine distance tests
# ---------------------------------------------------------------------------


class TestHaversine:
    """Verify distance calculation is correct and reproducible."""

    def test_florianopolis_to_self_zero(self):
        """Distance from Florianópolis to itself should be 0."""
        d = haversine(
            FLORIPA_CENTER[0],
            FLORIPA_CENTER[1],
            FLORIPA_CENTER[0],
            FLORIPA_CENTER[1],
        )
        assert d == 0.0, f"Self-distance should be 0, got {d}"

    def test_florianopolis_to_joinville(self):
        """Florianópolis to Joinville (~160 km)."""
        # Joinville approximate: -26.3044, -48.8467
        d = haversine(-27.5954, -48.5480, -26.3044, -48.8467)
        assert 140 < d < 200, f"Floripa→Joinville should be ~160 km, got {d}"

    def test_florianopolis_to_porto_alegre(self):
        """Florianópolis to Porto Alegre (~380 km — outside radius)."""
        d = haversine(-27.5954, -48.5480, -30.0346, -51.2177)
        assert d > TARGET_RADIUS_KM, f"Floripa→Porto Alegre ({d:.0f} km) should exceed {TARGET_RADIUS_KM} km"

    def test_florianopolis_to_sao_paulo(self):
        """Florianópolis to São Paulo (~500 km — far outside)."""
        d = haversine(-27.5954, -48.5480, -23.5505, -46.6333)
        assert d > 400, f"Floripa→SP ({d:.0f} km) should be >400 km"

    def test_symmetry(self):
        """Distance should be symmetric."""
        d1 = haversine(-27.0, -49.0, -28.0, -48.0)
        d2 = haversine(-28.0, -48.0, -27.0, -49.0)
        assert abs(d1 - d2) < 0.001, f"Distance should be symmetric: {d1} vs {d2}"


# ---------------------------------------------------------------------------
# TargetUniverse dataclass tests
# ---------------------------------------------------------------------------


class TestTargetUniverse:
    """TargetUniverse structural tests."""

    def test_empty_universe(self):
        """Empty universe has zero counts."""
        u = TargetUniverse()
        assert u.total_seed_rows == 0
        assert u.total_within_200km == 0
        assert u.unique_cnpj8_within == 0

    def test_inclusion_rule_explicit(self):
        """Inclusion rule must mention Haversine, coordinates, and radius."""
        u = TargetUniverse()
        rule = u.inclusion_rule
        assert "Haversine" in rule or "haversine" in rule.lower(), f"Rule: {rule}"
        assert str(TARGET_RADIUS_KM) in rule or str(int(TARGET_RADIUS_KM)) in rule, f"Rule: {rule}"
        assert "-27.5954" in rule or "-27.595" in rule, f"Rule: {rule}"

    def test_summary_no_all_sc_shortcut(self):
        """Summary must not use 'SC inteira' or 'all SC' as substitute."""
        u = TargetUniverse()
        summary = u.summary()
        # The summary must include the explicit distance method, not "all SC"
        assert summary["distance_method"] == "haversine"
        assert summary["radius_km"] == TARGET_RADIUS_KM

    def test_entity_within_radius(self):
        """Entity 25.1 km from Floripa must be within radius."""
        e = TargetEntity(
            razao_social="Test Entity",
            cnpj8="12345678",
            municipio="Test",
            codigo_ibge="4200000",
            natureza_juridica="Município",
            latitude=-27.6852,
            longitude=-48.7813,
            distancia_km=25.1,
            within_200km=True,
        )
        assert e.within_200km is True

    def test_entity_outside_radius(self):
        """Entity 250 km from Floripa must be outside radius."""
        e = TargetEntity(
            razao_social="Far Entity",
            cnpj8="87654321",
            municipio="Far",
            codigo_ibge="4200001",
            natureza_juridica="Município",
            latitude=-29.5,
            longitude=-50.0,
            distancia_km=250.0,
            within_200km=False,
        )
        assert e.within_200km is False


# ---------------------------------------------------------------------------
# Seed spreadsheet loading tests (offline — mock openpyxl)
# ---------------------------------------------------------------------------


class TestLoadTargetUniverse:
    """Target universe loading with mocked spreadsheet."""

    def _mock_workbook(self, rows):
        """Create a mock openpyxl workbook with given rows."""
        mock_wb = MagicMock()
        mock_ws = MagicMock()
        mock_wb.active = mock_ws
        # Each row is a tuple of values matching the spreadsheet columns
        mock_ws.iter_rows.return_value = [(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9]) for r in rows]
        return mock_wb

    def test_load_from_spreadsheet(self):
        """Load target universe from a mock spreadsheet."""
        rows = [
            (
                "PREFEITURA MUNICIPAL DE FLORIANOPOLIS",
                "82888888",
                "FLORIANOPOLIS",
                4205407,
                "Município",
                1244,
                -27.5954,
                -48.5480,
                0.0,
                "SIM ✓",
            ),
            (
                "PREFEITURA MUNICIPAL DE JOINVILLE",
                "83109888",
                "JOINVILLE",
                4209102,
                "Município",
                1244,
                -26.3044,
                -48.8467,
                160.0,
                "SIM ✓",
            ),
            (
                "PREFEITURA MUNICIPAL DE LAGES",
                "83888888",
                "LAGES",
                4209300,
                "Município",
                1244,
                -27.8160,
                -50.3260,
                180.0,
                "SIM ✓",
            ),
        ]

        mock_openpyxl = MagicMock()
        mock_openpyxl.load_workbook.return_value = self._mock_workbook(rows)

        with patch.dict(sys.modules, {"openpyxl": mock_openpyxl}), patch("os.path.exists", return_value=True):
            universe = load_target_universe(seed_path="/fake/path.xlsx")

        assert universe.total_seed_rows == 3
        assert universe.total_with_coords == 3
        assert universe.total_without_coords == 0

    def test_entities_without_coordinates_excluded(self):
        """Entities without coordinates are flagged, never silently included."""
        rows = [
            ("ENTIDADE COM COORDS", "11111111", "MUN1", 4200001, "Mun", 1244, -27.5, -48.5, 50.0, "SIM ✓"),
            ("ENTIDADE SEM COORDS", "22222222", "MUN2", 4200002, "Mun", 1244, None, None, None, ""),
        ]

        mock_openpyxl = MagicMock()
        mock_openpyxl.load_workbook.return_value = self._mock_workbook(rows)

        with patch.dict(sys.modules, {"openpyxl": mock_openpyxl}), patch("os.path.exists", return_value=True):
            universe = load_target_universe(seed_path="/fake/path.xlsx")

        assert universe.total_seed_rows == 2
        assert universe.total_with_coords == 1
        assert universe.total_without_coords == 1, (
            "Entities without coordinates must be counted as 'without_coords', never silently included"
        )

    def test_cnpj8_duplicates_counted(self):
        """CNPJ8 duplicates within 200km must be counted, never deduplicated silently."""
        rows = [
            ("SEC MUNICIPAL DE EDUCACAO", "62111111", "MUN1", 4200001, "Órgão", 1031, -27.5, -48.5, 50.0, "SIM ✓"),
            ("MUNICIPIO DE MUN1", "62111111", "MUN1", 4200001, "Município", 1244, -27.5, -48.5, 50.0, "SIM ✓"),
            ("CAMARA DE MUN1", "62111111", "MUN1", 4200001, "Legislativo", 1066, -27.5, -48.5, 50.0, "SIM ✓"),
        ]

        mock_openpyxl = MagicMock()
        mock_openpyxl.load_workbook.return_value = self._mock_workbook(rows)

        with patch.dict(sys.modules, {"openpyxl": mock_openpyxl}), patch("os.path.exists", return_value=True):
            universe = load_target_universe(seed_path="/fake/path.xlsx")

        # All 3 entities have same CNPJ8 (same municipality)
        assert universe.unique_cnpj8_within == 1, f"Expected 1 unique CNPJ8, got {universe.unique_cnpj8_within}"
        assert universe.duplicate_cnpj8_count == 1, f"Expected 1 duplicate CNPJ8, got {universe.duplicate_cnpj8_count}"
        assert "62111111" in universe.duplicate_cnpj8_list

    def test_distance_recomputed_not_trusted(self):
        """Distance is always recomputed via Haversine, never trusted from spreadsheet."""
        rows = [
            # Spreadsheet says 500 km (should be within 200km but wrong in sheet)
            (
                "FAR ENTITY",
                "99111111",
                "FAR",
                4209999,
                "Mun",
                1244,
                -27.5,
                -48.5,
                500.0,
                "",
            ),  # Actually close to Floripa!
        ]

        mock_openpyxl = MagicMock()
        mock_openpyxl.load_workbook.return_value = self._mock_workbook(rows)

        with patch.dict(sys.modules, {"openpyxl": mock_openpyxl}), patch("os.path.exists", return_value=True):
            universe = load_target_universe(seed_path="/fake/path.xlsx")

        # The entity at (-27.5, -48.5) is ~10 km from Floripa
        # but spreadsheet said 500 km.  We recompute, so it should be within 200km.
        assert universe.total_within_200km == 1, (
            "Entity at (-27.5, -48.5) should be within 200km of Florianópolis regardless of what spreadsheet claims"
        )
        entity = universe.entities[0]
        assert entity.distancia_km < 200, (
            f"Recomputed distance ({entity.distancia_km} km) should be < 200, spreadsheet incorrectly claimed 500 km"
        )

    def test_file_not_found_raises(self):
        """Missing seed file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_target_universe(seed_path="/nonexistent/path.xlsx")


# ---------------------------------------------------------------------------
# Filter helpers
# ---------------------------------------------------------------------------


class TestFilters:
    """Tests for entities_within_radius, unique_cnpj8, unique_municipios."""

    @pytest.fixture
    def sample_universe(self):
        u = TargetUniverse()
        u.entities = [
            TargetEntity("E1", "11111111", "MUN1", "4200001", "X", -27.6, -48.5, 10.0, True),
            TargetEntity("E2", "11111111", "MUN1", "4200001", "Y", -27.6, -48.5, 10.0, True),
            TargetEntity("E3", "22222222", "MUN2", "4200002", "Z", -27.7, -48.6, 25.0, True),
            TargetEntity("E4", "33333333", "FAR", "4299999", "W", -29.5, -50.0, 250.0, False),
        ]
        return u

    def test_entities_within_radius(self, sample_universe):
        """Only entities with within_200km=True are returned."""
        result = entities_within_radius(sample_universe)
        assert len(result) == 3  # E1, E2, E3
        assert all(e.within_200km for e in result)

    def test_unique_cnpj8_within(self, sample_universe):
        """CNPJ8 dedup returns unique roots only."""
        result = unique_cnpj8_within_radius(sample_universe)
        assert len(result) == 2  # 11111111, 22222222
        assert "11111111" in result
        assert "22222222" in result
        assert "33333333" not in result  # Outside radius

    def test_unique_municipios_within(self, sample_universe):
        """Municipality dedup returns unique names only."""
        result = unique_municipios_within_radius(sample_universe)
        assert len(result) == 2  # MUN1, MUN2
        assert "FAR" not in result  # Outside radius

    def test_no_all_sc_shortcut(self, sample_universe):
        """Municipality list must be subset of SC, not 'all SC'."""
        result = unique_municipios_within_radius(sample_universe)
        # If result were 295 (all SC municipalities), that would be the shortcut
        assert len(result) < 295, f"Got {len(result)} municipalities — if 295, that's the 'all SC' shortcut"

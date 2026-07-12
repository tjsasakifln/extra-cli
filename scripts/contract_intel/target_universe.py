"""Target Universe — deterministic entity set within 200 km of Florianópolis.

Loads the seed spreadsheet, computes Haversine distances, and produces
a reconciled, auditable list of public entities whose contracts should
be fetched from the PNCP contracts API.

Design constraints (per goal criteria):
  - No "all of SC" shortcut — every entity must have measured distance.
  - Entities without coordinates are flagged, never silently included.
  - CNPJ-base duplicates are counted and reported, never deduplicated silently.
  - The 200 km boundary is explicit and reproducible.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.lib.geocode import EARTH_RADIUS_KM, FLORIANOPOLIS, haversine  # noqa: E402

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_SEED = "Extra - alvos de licitação. R-0.xlsx"
TARGET_RADIUS_KM = 200.0
FLORIPA_CENTER = FLORIANOPOLIS  # (-27.5954, -48.5480)

# Column mapping for the seed spreadsheet (0-indexed)
COL_RAZAO_SOCIAL = 0
COL_CNPJ8 = 1
COL_MUNICIPIO = 2
COL_IBGE = 3
COL_NATUREZA = 4
COL_COD_NATUREZA = 5
COL_LATITUDE = 6
COL_LONGITUDE = 7
COL_DISTANCIA_SEED = 8  # Pre-computed in spreadsheet (km)
COL_RAIO200 = 9  # 'SIM ✓' or ''


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


@dataclass
class TargetEntity:
    """One public entity within the 200 km radius."""

    razao_social: str
    cnpj8: str  # CNPJ raiz (8 dígitos)
    municipio: str
    codigo_ibge: str
    natureza_juridica: str
    latitude: float
    longitude: float
    distancia_km: float  # Haversine-computed (reproducible)
    within_200km: bool


@dataclass
class TargetUniverse:
    """Deterministic universe of entities within 200 km of Florianópolis."""

    entities: list[TargetEntity] = field(default_factory=list)
    total_seed_rows: int = 0
    total_with_coords: int = 0
    total_without_coords: int = 0
    total_within_200km: int = 0
    total_outside_200km: int = 0
    unique_cnpj8_within: int = 0
    duplicate_cnpj8_count: int = 0
    duplicate_cnpj8_list: list[str] = field(default_factory=list)
    distance_method: str = "haversine"
    center_reference: tuple[float, float] = FLORIPA_CENTER
    radius_km: float = TARGET_RADIUS_KM
    seed_file: str = ""

    @property
    def inclusion_rule(self) -> str:
        """Explicit, auditable inclusion rule."""
        return (
            f"Haversine distance from ({self.center_reference[0]:.4f}, "
            f"{self.center_reference[1]:.4f}) <= {self.radius_km:.1f} km, "
            f"using Earth radius {EARTH_RADIUS_KM} km. "
            f"Entities without coordinates are EXCLUDED and flagged."
        )

    def summary(self) -> dict[str, Any]:
        """Deterministic summary for audit trail."""
        return {
            "seed_file": self.seed_file,
            "total_seed_rows": self.total_seed_rows,
            "total_with_coords": self.total_with_coords,
            "total_without_coords": self.total_without_coords,
            "total_within_200km": self.total_within_200km,
            "total_outside_200km": self.total_outside_200km,
            "unique_cnpj8_within_200km": self.unique_cnpj8_within,
            "duplicate_cnpj8_count": self.duplicate_cnpj8_count,
            "duplicate_cnpj8_list": self.duplicate_cnpj8_list,
            "inclusion_rule": self.inclusion_rule,
            "distance_method": self.distance_method,
            "center_lat": self.center_reference[0],
            "center_lon": self.center_reference[1],
            "radius_km": self.radius_km,
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_target_universe(
    seed_path: str | None = None,
    radius_km: float = TARGET_RADIUS_KM,
) -> TargetUniverse:
    """Load the seed spreadsheet and build the deterministic target universe.

    Args:
        seed_path: Path to the seed Excel file. Defaults to DEFAULT_SEED.
        radius_km: Radius in km from Florianópolis center.

    Returns:
        TargetUniverse with all entities classified and metrics computed.

    Raises:
        FileNotFoundError: If the seed file does not exist.
        ValueError: If the seed file has unexpected structure.
    """
    if seed_path is None:
        seed_path = str(_PROJECT_ROOT / DEFAULT_SEED)

    if not os.path.exists(seed_path):
        raise FileNotFoundError(f"Seed file not found: {seed_path}")

    # Lazy import — only this module needs openpyxl
    try:
        import openpyxl
    except ImportError:
        raise ImportError(
            "openpyxl is required to read the seed spreadsheet. "
            "Install with: pip install openpyxl"
        )

    wb = openpyxl.load_workbook(seed_path, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(min_row=2, values_only=True))  # Skip header
    wb.close()

    universe = TargetUniverse(
        seed_file=seed_path,
        radius_km=radius_km,
        total_seed_rows=len(rows),
    )

    cnpj8_seen: dict[str, int] = {}  # cnpj8 -> count within 200km
    entities_without_coords: list[dict[str, str]] = []

    for row in rows:
        if not row or not row[COL_RAZAO_SOCIAL]:
            continue

        razao = str(row[COL_RAZAO_SOCIAL]).strip()
        cnpj8 = str(row[COL_CNPJ8]).strip() if row[COL_CNPJ8] else ""
        municipio = str(row[COL_MUNICIPIO]).strip() if row[COL_MUNICIPIO] else ""
        ibge = str(int(row[COL_IBGE])) if row[COL_IBGE] else ""
        natureza = str(row[COL_NATUREZA]).strip() if row[COL_NATUREZA] else ""

        # Parse coordinates
        lat_raw = row[COL_LATITUDE] if len(row) > COL_LATITUDE else None
        lon_raw = row[COL_LONGITUDE] if len(row) > COL_LONGITUDE else None

        has_coords = False
        lat = None
        lon = None

        if lat_raw is not None and lon_raw is not None:
            try:
                lat = float(lat_raw)
                lon = float(lon_raw)
                has_coords = True
            except (ValueError, TypeError):
                pass

        if not has_coords:
            entities_without_coords.append({
                "razao_social": razao,
                "cnpj8": cnpj8,
                "municipio": municipio,
                "codigo_ibge": ibge,
            })
            universe.total_without_coords += 1
            continue

        universe.total_with_coords += 1

        # Compute distance (always recompute — do not trust spreadsheet)
        dist = haversine(
            FLORIPA_CENTER[0], FLORIPA_CENTER[1],
            lat, lon,
        )
        within = dist <= radius_km

        entity = TargetEntity(
            razao_social=razao,
            cnpj8=cnpj8,
            municipio=municipio,
            codigo_ibge=ibge,
            natureza_juridica=natureza,
            latitude=lat,
            longitude=lon,
            distancia_km=round(dist, 1),
            within_200km=within,
        )

        universe.entities.append(entity)

        if within:
            universe.total_within_200km += 1
            cnpj8_seen[cnpj8] = cnpj8_seen.get(cnpj8, 0) + 1
        else:
            universe.total_outside_200km += 1

    # Compute CNPJ8 duplicates within 200km
    universe.unique_cnpj8_within = len(cnpj8_seen)
    for cnpj8, count in cnpj8_seen.items():
        if count > 1:
            universe.duplicate_cnpj8_count += 1
            universe.duplicate_cnpj8_list.append(cnpj8)

    # Log summary
    logger.info(
        "Target universe: %s seed rows, %s with coords, %s without, "
        "%s within %s km, %s outside, %s unique CNPJ8 (%s duplicated)",
        universe.total_seed_rows,
        universe.total_with_coords,
        universe.total_without_coords,
        universe.total_within_200km,
        universe.total_outside_200km,
        universe.unique_cnpj8_within,
        universe.duplicate_cnpj8_count,
    )

    if entities_without_coords:
        logger.warning(
            "%d entities excluded due to missing coordinates: %s",
            len(entities_without_coords),
            [e["razao_social"] for e in entities_without_coords[:10]],
        )

    return universe


def entities_within_radius(
    universe: TargetUniverse,
) -> list[TargetEntity]:
    """Return only entities within the configured radius."""
    return [e for e in universe.entities if e.within_200km]


def unique_cnpj8_within_radius(
    universe: TargetUniverse,
) -> list[str]:
    """Return deduplicated list of CNPJ8 roots within the radius."""
    seen: set[str] = set()
    result: list[str] = []
    for e in entities_within_radius(universe):
        if e.cnpj8 and e.cnpj8 not in seen:
            seen.add(e.cnpj8)
            result.append(e.cnpj8)
    return sorted(result)


def unique_municipios_within_radius(
    universe: TargetUniverse,
) -> list[str]:
    """Return deduplicated list of municipality names within the radius."""
    seen: set[str] = set()
    result: list[str] = []
    for e in entities_within_radius(universe):
        if e.municipio and e.municipio not in seen:
            seen.add(e.municipio)
            result.append(e.municipio)
    return sorted(result)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Print target universe summary as JSON for auditability."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Build the deterministic target universe (200km from Florianópolis)."
    )
    parser.add_argument(
        "--seed", default=None,
        help=f"Path to seed Excel (default: {DEFAULT_SEED})",
    )
    parser.add_argument(
        "--radius", type=float, default=TARGET_RADIUS_KM,
        help=f"Radius in km (default: {TARGET_RADIUS_KM})",
    )
    parser.add_argument(
        "--output", default=None,
        help="Write JSON to file instead of stdout",
    )
    parser.add_argument(
        "--list-entities", action="store_true",
        help="Include full entity list in output",
    )
    parser.add_argument(
        "--list-cnpj8", action="store_true",
        help="List unique CNPJ8 roots within radius",
    )
    args = parser.parse_args()

    universe = load_target_universe(seed_path=args.seed, radius_km=args.radius)

    output: dict[str, Any] = universe.summary()

    if args.list_entities:
        output["entities"] = [
            {
                "razao_social": e.razao_social,
                "cnpj8": e.cnpj8,
                "municipio": e.municipio,
                "distancia_km": e.distancia_km,
                "within_200km": e.within_200km,
            }
            for e in universe.entities
        ]

    if args.list_cnpj8:
        output["unique_cnpj8_within"] = unique_cnpj8_within_radius(universe)
        output["unique_municipios_within"] = unique_municipios_within_radius(universe)

    json_str = json.dumps(output, indent=2, ensure_ascii=False, default=str)

    if args.output:
        with open(args.output, "w") as f:
            f.write(json_str)
        print(f"Target universe written to {args.output}")
    else:
        print(json_str)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    main()

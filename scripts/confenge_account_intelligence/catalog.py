"""Load the versioned CONFENGE account service catalog."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CATALOG = _ROOT / "config" / "commercial" / "confenge_account_service_catalog.yaml"

# Ten families required by the product objective (service_id keys).
REQUIRED_SERVICE_IDS: frozenset[str] = frozenset(
    {
        "estruturacao_pleito_reajuste",
        "reequilibrio_economico_financeiro",
        "aditivos_extracontratuais",
        "medicoes_glosas_memoria",
        "auditoria_orcamento_bdi",
        "gestao_monitoramento_contratual",
        "apoio_licitacoes_propostas",
        "inteligencia_pncp_mercado",
        "diagnostico_contratual_b2g",
        "reforco_temporario_backoffice",
    }
)


class CatalogError(ValueError):
    """Invalid or incomplete service catalog."""


def default_catalog_path() -> Path:
    return _DEFAULT_CATALOG


@lru_cache(maxsize=4)
def load_catalog(path: str | None = None) -> dict[str, Any]:
    """Load and validate catalog YAML. Cached by path string."""
    catalog_path = Path(path) if path else _DEFAULT_CATALOG
    if not catalog_path.is_file():
        raise CatalogError(f"Catalog not found: {catalog_path}")
    raw = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise CatalogError("Catalog root must be a mapping")
    return validate_catalog(raw)


def validate_catalog(raw: dict[str, Any]) -> dict[str, Any]:
    """Ensure required version stamp and ten service families are present."""
    version = raw.get("catalog_version") or raw.get("version")
    if not version:
        raise CatalogError("catalog_version is required")
    services = raw.get("services")
    if not isinstance(services, list) or not services:
        raise CatalogError("catalog.services must be a non-empty list")
    ids = {str(s.get("service_id")) for s in services if isinstance(s, dict)}
    missing = REQUIRED_SERVICE_IDS - ids
    if missing:
        raise CatalogError(f"Catalog missing required service_ids: {sorted(missing)}")
    return raw


def service_index(catalog: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    cat = catalog if catalog is not None else load_catalog()
    out: dict[str, dict[str, Any]] = {}
    for svc in cat.get("services") or []:
        if isinstance(svc, dict) and svc.get("service_id"):
            out[str(svc["service_id"])] = svc
    return out


def catalog_version(catalog: dict[str, Any] | None = None) -> str:
    cat = catalog if catalog is not None else load_catalog()
    return str(cat.get("catalog_version") or cat.get("version") or "0")


def discovery_service_id(catalog: dict[str, Any] | None = None) -> str:
    cat = catalog if catalog is not None else load_catalog()
    policy = cat.get("routing_policy") or {}
    return str(policy.get("discovery_when_best_fit") or "diagnostico_contratual_b2g")

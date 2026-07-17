"""Acquisition strategies that recover previously uncovered entities."""

from __future__ import annotations

from scripts.source_registry.acquisition.ciga_municipio_expand import (
    expand_ciga_by_municipio,
)
from scripts.source_registry.acquisition.pncp_orgao_probe import probe_pncp_orgaos

__all__ = [
    "expand_ciga_by_municipio",
    "probe_pncp_orgaos",
]

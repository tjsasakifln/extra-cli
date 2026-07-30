"""Load public-agency service catalog."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml

_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT = _ROOT / "config/commercial/public_agency_service_catalog.yaml"


def load_catalog(path: Path | None = None) -> dict[str, Any]:
    p = path or _DEFAULT
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"invalid catalog: {p}")
    return data


def catalog_hash(path: Path | None = None) -> str:
    p = path or _DEFAULT
    return hashlib.sha256(p.read_bytes()).hexdigest()


def services_list(path: Path | None = None) -> list[dict[str, Any]]:
    return list((load_catalog(path).get("services") or []))


def get_service(service_id: str, path: Path | None = None) -> dict[str, Any] | None:
    for s in services_list(path):
        if str(s.get("service_id")) == service_id:
            return s
    return None

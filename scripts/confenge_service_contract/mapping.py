"""Load and resolve confenge.service.v1 — fail closed on unknown codes."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

SCHEMA_ID = "confenge.service.v1"
_DEFAULT_PATH = (
    Path(__file__).resolve().parents[2]
    / "config"
    / "commercial"
    / "confenge_service_v1.yaml"
)


class UnknownServiceCodeError(ValueError):
    """Raised when a service code cannot be mapped — never fall back to REAJUSTE."""


@lru_cache(maxsize=4)
def load_service_contract(path: str | None = None) -> dict[str, Any]:
    p = Path(path) if path else _DEFAULT_PATH
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_id") != SCHEMA_ID:
        raise ValueError(f"invalid service contract at {p}")
    return data


def _index(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map any known alias/id/code (upper) → service record."""
    idx: dict[str, dict[str, Any]] = {}
    for svc in contract.get("services") or []:
        if not isinstance(svc, dict):
            continue
        keys = {
            str(svc.get("canonical_service_code") or "").upper(),
            str(svc.get("extra_cli_service_id") or "").upper(),
            str(svc.get("warmbly_playbook_code") or "").upper(),
        }
        for a in svc.get("aliases") or []:
            keys.add(str(a).upper())
        for k in keys:
            if k:
                idx[k] = svc
    return idx


def resolve_service(code: str | None, *, contract: dict[str, Any] | None = None) -> dict[str, Any]:
    """Resolve any known code to the service record. Raises on unknown."""
    cat = contract or load_service_contract()
    raw = (code or "").strip()
    if not raw:
        raise UnknownServiceCodeError("empty service code")
    idx = _index(cat)
    key = raw.upper()
    if key in idx:
        return dict(idx[key])
    # prefix before first _ only if full prefix is a known canonical (REAJUSTE_14133)
    if "_" in key:
        prefix = key.split("_", 1)[0]
        if prefix in idx and idx[prefix].get("canonical_service_code", "").upper() == prefix:
            return dict(idx[prefix])
    raise UnknownServiceCodeError(f"unknown service code: {code!r}")


def map_to_canonical(code: str | None, *, contract: dict[str, Any] | None = None) -> str:
    svc = resolve_service(code, contract=contract)
    return str(svc["canonical_service_code"])


def map_to_warmbly(code: str | None, *, contract: dict[str, Any] | None = None) -> str:
    svc = resolve_service(code, contract=contract)
    return str(svc["warmbly_playbook_code"])


def canonical_to_extra_cli(canonical: str, *, contract: dict[str, Any] | None = None) -> str:
    svc = resolve_service(canonical, contract=contract)
    return str(svc["extra_cli_service_id"])


def fallback_canonical(contract: dict[str, Any] | None = None) -> str:
    cat = contract or load_service_contract()
    rules = cat.get("routing_rules") or {}
    return str(rules.get("fallback_canonical") or "DIAGNOSTICO")


def export_contract_json(path: str | Path | None = None) -> dict[str, Any]:
    """Export contract as JSON-serializable dict for artifacts / Warmbly."""
    cat = load_service_contract(str(path) if path else None)
    return {
        "schema_id": cat.get("schema_id"),
        "schema_version": cat.get("schema_version"),
        "version_date": cat.get("version_date"),
        "routing_rules": cat.get("routing_rules"),
        "services": [
            {
                "canonical_service_code": s.get("canonical_service_code"),
                "extra_cli_service_id": s.get("extra_cli_service_id"),
                "warmbly_playbook_code": s.get("warmbly_playbook_code"),
                "aliases": list(s.get("aliases") or []),
                "display_name": s.get("display_name"),
                "valid_triggers": list(s.get("valid_triggers") or []),
                "valid_micro_offers": list(s.get("valid_micro_offers") or []),
                "prohibited_fallbacks": list(s.get("prohibited_fallbacks") or []),
                "is_fallback": bool(s.get("is_fallback")),
            }
            for s in (cat.get("services") or [])
            if isinstance(s, dict)
        ],
    }


def write_contract_artifact(out_path: str | Path) -> Path:
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(export_contract_json(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p

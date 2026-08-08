"""Official company registry / RFB adapter.

Reuses ``scripts.company_registry.lookup`` when local release is active.
Optional BrasilAPI only when ``allow_network`` is True (never in default tests).
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from scripts.confenge_contact_resolution.adapters.base import AdapterContext
from scripts.confenge_contact_resolution.models import RawObservation, SourceProvenance


def _digits(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")[:14]


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _from_registry_dict(cnpj14: str, rec: dict[str, Any]) -> list[RawObservation]:
    email = rec.get("email")
    phone = rec.get("phone") or rec.get("telefone") or rec.get("telefone1")
    if not email and not phone:
        # Still emit empty shell only if we have legal name? Prefer silence on absence.
        return []
    source_date = rec.get("source_date") or rec.get("registration_status_date")
    prov = SourceProvenance(
        source_type="registry",
        source_url=rec.get("source_url") or "official_company_registry",
        source_document=rec.get("official_release_id") or rec.get("release_id"),
        source_date=str(source_date)[:10] if source_date else None,
        observed_at=_now(),
        notes="RFB/public cadastral fields only; not a personal scrape",
    )
    return [
        RawObservation(
            adapter="registry",
            cnpj14=cnpj14,
            name=None,  # registry email is firm-level, not a named person
            cargo=None,
            email=str(email).strip() if email else None,
            phone_raw=str(phone).strip() if phone else None,
            site=rec.get("site"),
            source=prov,
            company_size=str(rec.get("company_size") or rec.get("porte") or "") or None,
            razao_social=rec.get("legal_name") or rec.get("razao_social"),
            epistemic_class="OBSERVED_PUBLIC",
            extra={
                "official_match_status": rec.get("official_match_status"),
                "registration_status": rec.get("registration_status") or rec.get("situacao_cadastral"),
            },
        )
    ]


def _lookup_local(cnpj14: str) -> dict[str, Any] | None:
    try:
        from scripts.company_registry.lookup import lookup_cnpj
        from scripts.company_registry.models import OfficialMatchStatus
    except ImportError:
        return None
    rec = lookup_cnpj(cnpj14)
    if rec.official_match_status != OfficialMatchStatus.MATCHED.value:
        return None
    d = rec.as_dict()
    return d


def _brasilapi(cnpj14: str, *, timeout: float = 12.0) -> dict[str, Any] | None:
    url = f"https://brasilapi.com.br/api/cnpj/v1/{cnpj14}"
    if not url.startswith("https://"):
        return None
    req = Request(url, headers={"User-Agent": "extra-cli-confenge-contact/1.0"})  # noqa: S310
    try:
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


class RegistryAdapter:
    name = "registry"

    def __init__(self, *, prefer_network: bool = False) -> None:
        self.prefer_network = prefer_network

    def collect(self, ctx: AdapterContext) -> list[RawObservation]:
        cnpj14 = _digits(ctx.cnpj14)
        if len(cnpj14) != 14:
            return []

        if ctx.registry_record:
            return _from_registry_dict(cnpj14, ctx.registry_record)

        # Offline / test fixtures: {cnpj14}_registry.json under fixtures_dir
        if ctx.fixtures_dir:
            p = ctx.fixtures_dir / f"{cnpj14}_registry.json"
            if p.is_file():
                try:
                    data = json.loads(p.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        return _from_registry_dict(cnpj14, data)
                except (OSError, json.JSONDecodeError):
                    pass

        local = _lookup_local(cnpj14)
        if local:
            return _from_registry_dict(cnpj14, local)

        if ctx.allow_network and self.prefer_network:
            data = _brasilapi(cnpj14)
            if data:
                mapped = {
                    "email": data.get("email"),
                    "phone": data.get("ddd_telefone_1") or data.get("telefone"),
                    "legal_name": data.get("razao_social"),
                    "company_size": data.get("porte") or data.get("descricao_porte"),
                    "source_url": "https://brasilapi.com.br/api/cnpj/v1/",
                    "source_date": datetime.now(UTC).date().isoformat(),
                    "official_match_status": "MATCHED",
                    "registration_status": data.get("descricao_situacao_cadastral"),
                }
                return _from_registry_dict(cnpj14, mapped)
        return []

"""Public business contact enrichment (LGPD-aware).

Only uses public registry / BrasilAPI-style endpoints. No private personal scraping.
"""

from __future__ import annotations

# Public HTTPS only; schemes restricted by caller URL builders.
# ruff: noqa: S310
import json
import re
import time
import urllib.error
import urllib.request
from datetime import UTC, date, datetime
from typing import Any


def _digits(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")[:14]


def brasilapi_cnpj(cnpj: str, *, timeout: float = 12.0) -> dict[str, Any] | None:
    c = _digits(cnpj)
    if len(c) != 14:
        return None
    url = f"https://brasilapi.com.br/api/cnpj/v1/{c}"
    req = urllib.request.Request(url, headers={"User-Agent": "extra-cli-reajuste-14133/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):  # noqa: S310
        return None


def _is_business_email(email: str | None) -> bool:
    if not email:
        return False
    e = email.strip().lower()
    if "@" not in e:
        return False
    # reject common personal domains for cold outreach enrichment
    personal = (
        "gmail.com", "hotmail.com", "yahoo.com", "outlook.com", "icloud.com",
        "bol.com.br", "uol.com.br", "terra.com.br", "live.com",
    )
    domain = e.split("@", 1)[-1]
    if domain in personal:
        return False
    return True


def enrich_from_registry_row(reg: dict[str, Any] | None) -> dict[str, Any]:
    """Map supplier_registry row to contact block (no personal phones invented)."""
    reg = reg or {}
    return {
        "site_oficial": None,
        "email_comercial": None,
        "telefone_empresarial": None,
        "formulario_contato": None,
        "linkedin_institucional": None,
        "municipio_sede": reg.get("municipio"),
        "uf_sede": reg.get("uf"),
        "nome_fantasia": reg.get("nome_fantasia"),
        "razao_social_registry": reg.get("razao_social"),
        "cnae_principal": reg.get("cnae_principal"),
        "situacao_cadastral": reg.get("situacao_cadastral"),
        "contact_sources": [
            {
                "field": "registry",
                "source": reg.get("source"),
                "source_date": str(reg.get("source_date") or ""),
                "verified_at": datetime.now(UTC).date().isoformat(),
            }
        ]
        if reg
        else [],
        "contact_score": 0.15 if reg else 0.0,
        "has_personal_only_contact": False,
    }


def enrich_from_brasilapi(cnpj: str, *, sleep_s: float = 0.15) -> dict[str, Any]:
    data = brasilapi_cnpj(cnpj)
    time.sleep(sleep_s)
    if not data:
        return {
            "contact_score": 0.0,
            "contact_sources": [],
            "has_personal_only_contact": False,
            "limitations": ["brasilapi_unavailable"],
        }
    email = data.get("email")
    phone = data.get("ddd_telefone_1") or data.get("telefone")
    business_email = email if _is_business_email(email) else None
    personal_only = bool(email) and not business_email
    score = 0.2
    if business_email:
        score += 0.35
    if phone:
        score += 0.25
    if data.get("descricao_situacao_cadastral") == "ATIVA" or str(data.get("situacao_cadastral")) in {"2", "ATIVA", "Ativa"}:
        score += 0.1
    verified = date.today().isoformat()
    sources = [
        {
            "field": "brasilapi_cnpj",
            "source": "brasilapi.com.br",
            "source_date": verified,
            "verified_at": verified,
        }
    ]
    return {
        "site_oficial": None,
        "email_comercial": business_email,
        "telefone_empresarial": str(phone) if phone else None,
        "formulario_contato": None,
        "linkedin_institucional": None,
        "municipio_sede": data.get("municipio") or data.get("cidade"),
        "uf_sede": data.get("uf"),
        "nome_fantasia": data.get("nome_fantasia"),
        "razao_social_registry": data.get("razao_social"),
        "cnae_principal": str(data.get("cnae_fiscal") or data.get("cnae_principal") or ""),
        "situacao_cadastral": data.get("descricao_situacao_cadastral") or str(data.get("situacao_cadastral") or ""),
        "contact_sources": sources,
        "contact_score": min(1.0, score),
        "has_personal_only_contact": personal_only,
        "limitations": (
            ["email_pessoal_ignorado_lgpd"] if personal_only else []
        ),
    }


def merge_contacts(*parts: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "site_oficial": None,
        "email_comercial": None,
        "telefone_empresarial": None,
        "formulario_contato": None,
        "linkedin_institucional": None,
        "municipio_sede": None,
        "uf_sede": None,
        "nome_fantasia": None,
        "cnae_principal": None,
        "situacao_cadastral": None,
        "contact_sources": [],
        "contact_score": 0.0,
        "has_personal_only_contact": False,
        "limitations": [],
    }
    for p in parts:
        if not p:
            continue
        for k in (
            "site_oficial", "email_comercial", "telefone_empresarial",
            "formulario_contato", "linkedin_institucional", "municipio_sede",
            "uf_sede", "nome_fantasia", "cnae_principal", "situacao_cadastral",
        ):
            if p.get(k) and not out.get(k):
                out[k] = p[k]
        out["contact_sources"].extend(p.get("contact_sources") or [])
        out["contact_score"] = max(float(out["contact_score"]), float(p.get("contact_score") or 0))
        out["has_personal_only_contact"] = out["has_personal_only_contact"] or bool(
            p.get("has_personal_only_contact")
        )
        out["limitations"].extend(p.get("limitations") or [])
    return out

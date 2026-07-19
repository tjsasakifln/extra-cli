"""Resolve full CNPJ-14 for public entities via PNCP orgaos search API.

Uses GET /api/pncp/v1/orgaos?razaoSocial=...
Preference: cnpj8 prefix match > exact name > token containment.
"""
from __future__ import annotations

import json
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

UA = "ExtraConsultoria-OPS95/1.0"
PNCP_ORGAOS = "https://pncp.gov.br/api/pncp/v1/orgaos"


def normalize_name(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^A-Z0-9 ]+", " ", s.upper())
    return re.sub(r"\s+", " ", s).strip()


def digits(s: str | None) -> str:
    return re.sub(r"\D", "", str(s or ""))


def search_orgaos(razao: str, *, pagina: int = 1, tamanho: int = 20, timeout: int = 20) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode(
        {"razaoSocial": razao[:80], "pagina": str(pagina), "tamanhoPagina": str(tamanho)}
    )
    url = f"{PNCP_ORGAOS}?{params}"
    if not url.startswith("https://"):
        raise ValueError(f"refusing non-HTTPS URL: {url[:32]!r}")
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})  # noqa: S310 — HTTPS PNCP orgaos API
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — HTTPS PNCP orgaos API
        data = json.loads(resp.read().decode("utf-8"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return list(data.get("data") or [])
    return []


@dataclass
class ResolveResult:
    cnpj8: str
    cnpj14: str | None
    method: str | None
    razao_hit: str | None
    n_hits: int
    error: str | None = None


def pick_match(cnpj8: str, razao: str, hits: list[dict[str, Any]]) -> tuple[str, str, dict[str, Any]] | None:
    """Pick CNPJ-14 only when the root CNPJ-8 matches the entity.

    Name/token signals rank among candidates with the same root; they must never
    override a different CNPJ root (false identity / false success_zero risk).
    """
    cnpj8 = digits(cnpj8)[:8]
    target = normalize_name(razao)
    # 1) Prefer exact CNPJ-8 prefix (any razao)
    for h in hits:
        cnpj = digits(h.get("cnpj"))
        if len(cnpj) == 14 and cnpj[:8] == cnpj8:
            return cnpj, "cnpj8_prefix", h
    # 2) Same root only — name exact among residual hits (defensive)
    for h in hits:
        cnpj = digits(h.get("cnpj"))
        if len(cnpj) != 14 or cnpj[:8] != cnpj8:
            continue
        if normalize_name(h.get("razaoSocial")) == target:
            return cnpj, "name_exact", h
    # 3) Same root only — token containment
    stop = {"MUNICIPIO", "PREFEITURA", "SECRETARIA", "FUNDO", "ESTADO", "SANTA", "CATARINA", "SOCIAL", "PUBLICOS"}
    tokens = [t for t in target.split() if len(t) > 3 and t not in stop]
    if len(tokens) >= 2:
        for h in hits:
            cnpj = digits(h.get("cnpj"))
            if len(cnpj) != 14 or cnpj[:8] != cnpj8:
                continue
            nh = normalize_name(h.get("razaoSocial"))
            if all(t in nh for t in tokens[:3]):
                return cnpj, "token_containment", h
    return None


def resolve_entity(
    cnpj8: str,
    razao: str,
    municipio: str | None = None,
    *,
    delay_s: float = 0.4,
) -> ResolveResult:
    c8 = digits(cnpj8)[:8]
    try:
        hits = search_orgaos(razao)
        time.sleep(delay_s)
        picked = pick_match(c8, razao, hits)
        if not picked and municipio:
            hits2 = search_orgaos(f"PREFEITURA {municipio}")
            time.sleep(delay_s)
            hits = hits + hits2
            picked = pick_match(c8, razao, hits2) or pick_match(c8, razao, hits)
        if not picked:
            return ResolveResult(c8, None, None, None, len(hits))
        cnpj14, method, hit = picked
        return ResolveResult(c8, cnpj14, method, hit.get("razaoSocial"), len(hits))
    except Exception as exc:  # noqa: BLE001
        return ResolveResult(c8, None, None, None, 0, error=f"{type(exc).__name__}:{exc}")

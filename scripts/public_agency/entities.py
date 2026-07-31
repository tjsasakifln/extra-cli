"""PUBLIC_AGENCY_PROSPECT entity model — separate from supplier leads."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from scripts.public_agency import ENTITY_TYPE


def normalize_cnpj14(raw: Any) -> str | None:
    digits = re.sub(r"\D", "", str(raw or ""))
    if len(digits) >= 14:
        return digits[-14:]
    if len(digits) == 14:
        return digits
    return None


def agency_id_from_parts(cnpj14: str | None, nome: str | None, uf: str | None) -> str:
    base = f"{cnpj14 or ''}|{(nome or '').strip().upper()}|{(uf or '').upper()}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]


@dataclass
class PublicAgencyProspect:
    entity_type: str = ENTITY_TYPE
    agency_id: str = ""
    cnpj: str | None = None
    nome_oficial: str = ""
    nome_unidade: str | None = None
    esfera: str | None = None  # municipal | estadual | federal | consorcio
    poder: str | None = None
    natureza_juridica: str | None = None
    municipio: str | None = None
    uf: str | None = None
    codigo_ibge: str | None = None
    populacao: int | None = None
    faixa_populacional: str | None = None
    consorcio_publico: bool = False
    autarquia: bool = False
    fundacao: bool = False
    unidade_gestora: str | None = None
    fontes: list[dict[str, Any]] = field(default_factory=list)
    identidade_canonica: str | None = None
    confidence: float = 0.0
    last_verified_at: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def infer_agency_flags(nome: str | None) -> dict[str, Any]:
    n = (nome or "").upper()
    return {
        "consorcio_publico": "CONSÓRCIO" in n or "CONSORCIO" in n,
        "autarquia": "AUTARQUIA" in n,
        "fundacao": "FUNDAÇÃO" in n or "FUNDACAO" in n,
        "esfera": (
            "municipal"
            if any(x in n for x in ("PREFEITURA", "MUNICÍPIO", "MUNICIPIO", "CÂMARA MUNICIPAL", "CAMARA MUNICIPAL"))
            else "estadual"
            if any(x in n for x in ("ESTADO", "SECRETARIA DE ESTADO", "GOVERNO DO"))
            else "federal"
            if any(x in n for x in ("UNIÃO", "UNIAO", "MINISTÉRIO", "MINISTERIO", "FEDERAL"))
            else "indeterminada"
        ),
    }


def build_prospect_from_contract_rows(
    rows: list[dict[str, Any]],
    *,
    population_info: dict[str, Any] | None = None,
) -> PublicAgencyProspect:
    if not rows:
        raise ValueError("rows required")
    first = rows[0]
    cnpj = normalize_cnpj14(first.get("orgao_cnpj"))
    nome = str(first.get("orgao_nome") or "").strip() or "ORGÃO NÃO IDENTIFICADO"
    uf = (str(first.get("uf") or "").strip().upper() or None)
    flags = infer_agency_flags(nome)
    pop = population_info or {}
    aid = agency_id_from_parts(cnpj, nome, uf)
    sources = [
        {
            "source": "pncp_supplier_contracts",
            "role": "buyer_side_aggregate",
            "contract_count": len(rows),
        }
    ]
    conf = 0.5
    if cnpj:
        conf += 0.25
    if pop.get("population") is not None:
        conf += 0.15
    if nome and nome != "ORGÃO NÃO IDENTIFICADO":
        conf += 0.1
    return PublicAgencyProspect(
        agency_id=aid,
        cnpj=cnpj,
        nome_oficial=nome,
        nome_unidade=nome,
        esfera=flags["esfera"],
        poder="executivo" if "PREFEITURA" in nome.upper() else None,
        natureza_juridica=None,
        municipio=pop.get("municipio"),
        uf=uf,
        codigo_ibge=pop.get("ibge_code"),
        populacao=pop.get("population"),
        faixa_populacional=pop.get("population_band"),
        consorcio_publico=flags["consorcio_publico"],
        autarquia=flags["autarquia"],
        fundacao=flags["fundacao"],
        unidade_gestora=cnpj,
        fontes=sources,
        identidade_canonica=f"cnpj:{cnpj}" if cnpj else f"name_uf:{nome}|{uf}",
        confidence=min(conf, 0.95),
        last_verified_at=datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    )

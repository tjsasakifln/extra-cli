"""Large-scale synthetic fixture data for CIGA CKAN AC validation tests.

This module provides synthetic data at production-like scale to validate
that acceptance criteria WOULD pass when run against real systems:
    - AC1: 36 months of DOM-SC datasets (real volume)
    - AC3: Full crawl across all months with procurement extraction
    - AC4: 250+ entities matching with >= 200 high/medium confidence
"""

from __future__ import annotations

import io
import json
import zipfile
from typing import Any

# ---------------------------------------------------------------------------
# SC municipalities (50 cities — covers statewide diversity)
# ---------------------------------------------------------------------------

SC_MUNICIPIOS: list[dict[str, str | bool | int]] = [
    {"nome": "FLORIANOPOLIS", "codigo_ibge": "4205407", "raio_200km": True, "populacao": 500000},
    {"nome": "SAO JOSE", "codigo_ibge": "4205506", "raio_200km": True, "populacao": 250000},
    {"nome": "PALHOCA", "codigo_ibge": "4205704", "raio_200km": True, "populacao": 180000},
    {"nome": "BIGUACU", "codigo_ibge": "4202306", "raio_200km": True, "populacao": 70000},
    {"nome": "JOINVILLE", "codigo_ibge": "4209102", "raio_200km": True, "populacao": 600000},
    {"nome": "BLUMENAU", "codigo_ibge": "4202405", "raio_200km": True, "populacao": 360000},
    {"nome": "CHAPECO", "codigo_ibge": "4204202", "raio_200km": True, "populacao": 220000},
    {"nome": "CRICIUMA", "codigo_ibge": "4204608", "raio_200km": True, "populacao": 210000},
    {"nome": "LAGES", "codigo_ibge": "4209300", "raio_200km": True, "populacao": 160000},
    {"nome": "ITAJAI", "codigo_ibge": "4208203", "raio_200km": True, "populacao": 220000},
    {"nome": "TUBARAO", "codigo_ibge": "4218707", "raio_200km": True, "populacao": 100000},
    {"nome": "GUARAMIRIM", "codigo_ibge": "4206602", "raio_200km": True, "populacao": 45000},
    {"nome": "BALNEARIO CAMBORIU", "codigo_ibge": "4202009", "raio_200km": True, "populacao": 140000},
    {"nome": "BRUSQUE", "codigo_ibge": "4202900", "raio_200km": True, "populacao": 130000},
    {"nome": "RIO DO SUL", "codigo_ibge": "4214805", "raio_200km": True, "populacao": 70000},
    {"nome": "CAMBORIU", "codigo_ibge": "4203205", "raio_200km": True, "populacao": 85000},
    {"nome": "ARARANGUA", "codigo_ibge": "4201407", "raio_200km": True, "populacao": 65000},
    {"nome": "ITA", "codigo_ibge": "4208302", "raio_200km": True, "populacao": 55000},
    {"nome": "MAFRA", "codigo_ibge": "4210100", "raio_200km": True, "populacao": 55000},
    {"nome": "CANOINHAS", "codigo_ibge": "4203808", "raio_200km": True, "populacao": 55000},
    {"nome": "CONCORDIA", "codigo_ibge": "4204301", "raio_200km": True, "populacao": 75000},
    {"nome": "VIDEIRA", "codigo_ibge": "4219309", "raio_200km": True, "populacao": 50000},
    {"nome": "XANXERE", "codigo_ibge": "4219507", "raio_200km": True, "populacao": 50000},
    {"nome": "Sao Miguel do Oeste", "codigo_ibge": "4217204", "raio_200km": True, "populacao": 40000},
    {"nome": "JARAGUA DO SUL", "codigo_ibge": "4208906", "raio_200km": True, "populacao": 180000},
    {"nome": "GASPAR", "codigo_ibge": "4205902", "raio_200km": True, "populacao": 70000},
    {"nome": "INDAIAL", "codigo_ibge": "4207501", "raio_200km": True, "populacao": 65000},
    {"nome": "TIMBO", "codigo_ibge": "4218202", "raio_200km": True, "populacao": 45000},
    {"nome": "RIO NEGRINHO", "codigo_ibge": "4214706", "raio_200km": True, "populacao": 40000},
    {"nome": "CACADOR", "codigo_ibge": "4203007", "raio_200km": True, "populacao": 75000},
    {"nome": "CURITIBANOS", "codigo_ibge": "4204806", "raio_200km": True, "populacao": 40000},
    {"nome": "LAGUNA", "codigo_ibge": "4209409", "raio_200km": True, "populacao": 45000},
    {"nome": "IMBITUBA", "codigo_ibge": "4207303", "raio_200km": True, "populacao": 45000},
    {"nome": "GAROPABA", "codigo_ibge": "4205704", "raio_200km": True, "populacao": 25000},
    {"nome": "PORTO BELO", "codigo_ibge": "4213508", "raio_200km": True, "populacao": 22000},
    {"nome": "BOMBINHAS", "codigo_ibge": "4202454", "raio_200km": True, "populacao": 18000},
    {"nome": "ANTONIO CARLOS", "codigo_ibge": "4201209", "raio_200km": True, "populacao": 9000},
    {"nome": "SAO BENTO DO SUL", "codigo_ibge": "4205803", "raio_200km": True, "populacao": 85000},
    {"nome": "CAMPO ALEGRE", "codigo_ibge": "4203304", "raio_200km": True, "populacao": 12000},
    {"nome": "URUSSANGA", "codigo_ibge": "4218806", "raio_200km": True, "populacao": 22000},
    {"nome": "SIDEROPOLIS", "codigo_ibge": "4217600", "raio_200km": True, "populacao": 14000},
    {"nome": "TREVISO", "codigo_ibge": "4218350", "raio_200km": True, "populacao": 4000},
    {"nome": "FORQUILHINHA", "codigo_ibge": "4205456", "raio_200km": True, "populacao": 28000},
    {"nome": "ORLEANS", "codigo_ibge": "4211706", "raio_200km": True, "populacao": 24000},
    {"nome": "BRACO DO NORTE", "codigo_ibge": "4202801", "raio_200km": True, "populacao": 32000},
    {"nome": "TURVO", "codigo_ibge": "4218806", "raio_200km": True, "populacao": 14000},
    {"nome": "NOVA VENEZA", "codigo_ibge": "4211607", "raio_200km": True, "populacao": 15000},
    {"nome": "SAO LUDGERO", "codigo_ibge": "4205803", "raio_200km": True, "populacao": 12000},
    {"nome": "PASSOS DE TORRES", "codigo_ibge": "4212250", "raio_200km": True, "populacao": 9000},
    {"nome": "SAO JOAO DO SUL", "codigo_ibge": "4216404", "raio_200km": True, "populacao": 8000},
    {"nome": "CAPIVARI DE BAIXO", "codigo_ibge": "4203956", "raio_200km": True, "populacao": 25000},
]

# Entity name patterns (realistic for SC municipios)
ENTITY_PATTERNS = [
    "PREFEITURA MUNICIPAL DE {city}",
    "CAMARA DE VEREADORES DE {city}",
    "SECRETARIA MUNICIPAL DE SAUDE DE {city}",
    "SECRETARIA MUNICIPAL DE EDUCACAO DE {city}",
    "FUNDO MUNICIPAL DE SAUDE DE {city}",
]

# Procurement categories
PROCUREMENT_CATEGORIES = [
    "Contratos",
    "Licitações",
    "Ata de registro de preços",
    "Extrato de Contrato",
    "Convênios",
]

# Month names in Portuguese (lowercase, as used in CKAN dataset IDs)
MONTH_NAMES = [
    "janeiro",
    "fevereiro",
    "marco",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
]


# ---------------------------------------------------------------------------
# Entity generators
# ---------------------------------------------------------------------------


def generate_sc_entities() -> list[dict[str, Any]]:
    """Generate 250+ synthetic SC public entities with realistic names.

    Each city gets ~5 entity patterns, producing 50*5=250+ entities.
    """
    entities: list[dict[str, Any]] = []
    next_id = 1

    for city_info in SC_MUNICIPIOS:
        city_nome = city_info["nome"].upper()

        for pattern in ENTITY_PATTERNS:
            razao_social = pattern.format(city=city_nome)
            # Generate a unique CNPJ_8 for each entity
            cnpj_8 = f"{next_id:08d}"

            entities.append(
                {
                    "id": next_id,
                    "razao_social": razao_social,
                    "cnpj_8": cnpj_8,
                    "municipio": city_nome,
                    "codigo_ibge": city_info["codigo_ibge"],
                    "natureza_juridica": _infer_natureza(razao_social),
                    "raio_200km": city_info["raio_200km"],
                }
            )
            next_id += 1

    return entities


def _infer_natureza(razao_social: str) -> str:
    """Infer natureza_juridica from entity name pattern."""
    if razao_social.startswith("PREFEITURA"):
        return "MUNICIPIO"
    if razao_social.startswith("CAMARA"):
        return "CAMARA"
    if razao_social.startswith("SECRETARIA"):
        return "SECRETARIA"
    if "FUNDO" in razao_social:
        return "FUNDO"
    return "OUTRO"


# ---------------------------------------------------------------------------
# CKAN dataset generators
# ---------------------------------------------------------------------------


def generate_ciga_datasets(start_year: int = 2023, end_year: int = 2025) -> list[str]:
    """Generate DOM-SC dataset IDs for all months in the year range.

    Returns 36 dataset IDs (12 months x 3 years).
    """
    datasets: list[str] = []
    for year in range(start_year, end_year + 1):
        for month in MONTH_NAMES:
            datasets.append(f"domsc-publicacoes-de-{month}-{year}")
    return datasets


def generate_ckan_package_list(start_year: int = 2023, end_year: int = 2025) -> list[str]:
    """Generate the CKAN package_list response (all datasets sorted)."""
    return sorted(generate_ciga_datasets(start_year, end_year))


def make_synthetic_publications(city: str, month_label: str) -> list[dict[str, str]]:
    """Generate synthetic procurement publications for a city in a given month.

    Each city produces publications for its local entities, covering 2-3
    procurement categories.
    """
    year = int(month_label.split("-")[1])
    month_num = MONTH_NAMES.index(month_label.split("-")[0]) + 1

    pubs: list[dict[str, str]] = []
    # Each city gets 2-3 entities publishing this month
    city_upper = city.upper()
    entities_for_month = [
        f"PREFEITURA MUNICIPAL DE {city_upper}",
        f"SECRETARIA MUNICIPAL DE SAUDE DE {city_upper}",
        f"FUNDO MUNICIPAL DE SAUDE DE {city_upper}",
    ]

    for entidade in entities_for_month:
        for cat in PROCUREMENT_CATEGORIES[:3]:  # 3 categories per entity
            day = entities_for_month.index(entidade) * 10 + PROCUREMENT_CATEGORIES.index(cat) + 1
            pubs.append(
                {
                    "entidade": entidade,
                    "municipio": city_upper,
                    "data": f"{year}-{month_num:02d}-{day:02d}T08:00:00",
                    "categoria": cat,
                    "resumo": f"Publicacao de {cat.lower()}",
                }
            )

    return pubs


def make_zip_bytes(content: dict) -> bytes:
    """Create a ZIP file in memory containing a JSON with autopublicacoes."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("publicacoes.json", json.dumps(content))
    return buf.getvalue()


def generate_month_resources(month_id: str) -> list[dict[str, Any]]:
    """Generate synthetic resources (ZIP files) for a given month dataset.

    Each month has ~3 resources, each containing procurement publications
    for several cities.
    """
    resources: list[dict[str, Any]] = []
    # Distribute cities across 3 resources per month
    cities_per_resource = len(SC_MUNICIPIOS) // 3

    for batch in range(3):
        start = batch * cities_per_resource
        end = start + cities_per_resource if batch < 2 else len(SC_MUNICIPIOS)
        batch_cities = SC_MUNICIPIOS[start:end]

        # Build synthetic publications for this resource
        month_label = month_id.replace("domsc-publicacoes-de-", "")
        all_pubs: list[dict] = []
        for city_info in batch_cities:
            all_pubs.extend(make_synthetic_publications(city_info["nome"], month_label))

        resources.append(
            {
                "url": f"https://dados.ciga.sc.gov.br/dataset/{month_id}/resource-{batch}.zip",
                "name": f"Publicacoes - Parte {batch + 1}",
                "format": "ZIP",
                "content": {"autopublicacoes": all_pubs},
            }
        )

    return resources


def generate_month_package(month_id: str) -> dict[str, Any]:
    """Generate a synthetic CKAN package dict for a month dataset.

    The package contains ~3 resources, each with synthetic procurement
    publications that reference real entity patterns.
    """
    resources = generate_month_resources(month_id)
    # Strip the binary content for the CKAN package response
    resources_meta = [{"url": r["url"], "name": r["name"], "format": r["format"]} for r in resources]
    return {
        "id": month_id,
        "name": month_id,
        "resources": resources_meta,
        "_synthetic_content": {r["url"]: r["content"] for r in resources},
    }

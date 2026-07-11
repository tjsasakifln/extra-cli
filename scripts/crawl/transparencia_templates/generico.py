"""Generic Fallback Template — Extra Consultoria.

Template genérico para portais de transparência NÃO identificados
como Betha, Ipam ou E-gov.

Estratégia:
    1. Busca por tabelas HTML com keywords comuns (licitação, edital, pregão)
    2. Busca por divs com classes/ids contendo "licitacao" ou "edital"
    3. Tenta extrair linhas de qualquer tabela com pelo menos 3 colunas
    4. Loga os seletores encontrados para facilitar diagnóstico

Usado como fallback quando os templates específicos não se aplicam.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from scripts.crawl.transparencia_templates.base import (
    extract_link,
    extract_text,
    make_record,
)

_logger = logging.getLogger(__name__)

PLATFORM = "generico"
NAME = "Genérico (Fallback)"
DESCRIPTION = "Template genérico para portais não identificados"
URL_PATTERNS: list[str] = []

SELECTORS: dict[str, str] = {}

# Keywords that suggest a table contains licitacao data
_LICITACAO_KEYWORDS = [
    "licitação", "licitacao", "edital", "pregão", "pregao",
    "modalidade", "objeto", "data de publicação", "data limite",
    "concorrência", "concorrencia", "tomada de preço", "tomada de precos",
    "convite", "dispensa", "inexigibilidade",
]


def parse_page(soup: Any, url: str = "", slug: str = "", ibge: str = "") -> list[dict]:
    """Parse an unknown transparency portal HTML using heuristics.

    Strategy:
    1. Find all tables and score them by keyword match
    2. Parse the highest-scoring table
    3. If no table found, try div-based extraction

    Args:
        soup: BeautifulSoup parsed page.
        url: Full portal URL.
        slug: Municipality slug.
        ibge: IBGE code.

    Returns:
        List of record dicts (may be empty if nothing found).
    """
    records: list[dict] = []

    # Strategy 1: Find most relevant table by keyword scoring
    records = _score_and_parse_tables(soup, url, slug, ibge)
    if records:
        return records

    # Strategy 2: Try div-based extraction
    records = _div_based_extraction(soup, url, slug, ibge)
    if records:
        return records

    # Strategy 3: Try any table with enough columns
    records = _any_table_extraction(soup, url, slug, ibge)
    if records:
        return records

    _logger.info("Generico: no data found for %s", slug)
    return records


def _score_and_parse_tables(soup: Any, url: str, slug: str, ibge: str) -> list[dict]:
    """Find all tables, score by keyword relevance, parse best one."""
    all_tables = soup.find_all("table")
    if not all_tables:
        return []

    scored: list[tuple[int, Any, int]] = []  # (score, table, row_count)

    for table in all_tables:
        html_lower = str(table).lower()
        score = sum(2 for kw in _LICITACAO_KEYWORDS if re.search(rf'\b{re.escape(kw)}\b', html_lower))
        trs = table.find_all("tr")
        row_count = len(trs)
        # Bonus for having header-like structure
        if row_count > 1:
            score += 1
        scored.append((score, table, row_count))

    scored.sort(key=lambda x: (-x[0], -x[2]))  # Highest score, most rows

    # Try tables with score > 0 first
    for score, table, _ in scored:
        if score <= 0:
            continue
        records = _parse_table(table, url, slug, ibge)
        if records:
            _logger.info("Generico: parsed table with score %d for %s (%d records)", score, slug, len(records))
            return records

    # Try the largest table if nothing scored
    for _, table, row_count in scored[:3]:
        if row_count <= 2:
            continue
        records = _parse_table(table, url, slug, ibge)
        if records:
            _logger.info("Generico: parsed largest table (%d rows) for %s (%d records)", row_count, slug, len(records))
            return records

    return []


def _parse_table(table: Any, url: str, slug: str, ibge: str) -> list[dict]:
    """Parse a single table element into records, trying column heuristics."""
    records: list[dict] = []
    seen_hashes: set[str] = set()

    trs = table.find_all("tr")
    for idx, tr in enumerate(trs):
        if idx == 0:
            continue  # skip header
        if tr.name != "tr":
            continue

        tds = tr.find_all("td")
        if len(tds) < 2:
            continue

        # Heuristic column assignment:
        # td[0] = modalidade or data
        # td[1] = data or objeto
        # td[2] = objeto or valor
        # td[3] = orgao or valor
        # td[4] = link or valor
        col_count = len(tds)

        if col_count >= 5:
            # Standard 5-column: modalidade, data, objeto, orgao, valor
            modalidade = extract_text(tds[0])
            data_txt = extract_text(tds[1])
            objeto = extract_text(tds[2])
            orgao = extract_text(tds[3])
            valor = extract_text(tds[4])
            link = extract_link(tr, "a[href]", url)
        elif col_count == 4:
            # 4-column: data, modalidade, objeto, valor
            data_txt = extract_text(tds[0])
            modalidade = extract_text(tds[1])
            objeto = extract_text(tds[2])
            valor = extract_text(tds[3])
            orgao = ""
            link = extract_link(tr, "a[href]", url)
        elif col_count == 3:
            # 3-column: data, modalidade, objeto
            data_txt = extract_text(tds[0])
            modalidade = extract_text(tds[1])
            objeto = extract_text(tds[2])
            orgao = ""
            valor = ""
            link = extract_link(tr, "a[href]", url)
        else:
            # 2-column: try key-value
            data_txt = ""
            modalidade = extract_text(tds[0])
            objeto = extract_text(tds[1])
            orgao = ""
            valor = ""
            link = extract_link(tr, "a[href]", url)

        record = make_record(
            slug=slug,
            ibge=ibge,
            portal_url=url,
            modalidade=modalidade,
            data_publicacao=data_txt,
            objeto=objeto,
            orgao=orgao,
            valor=valor,
            link=link,
        )
        if record and record["content_hash"] not in seen_hashes:
            seen_hashes.add(record["content_hash"])
            records.append(record)

    return records


def _div_based_extraction(soup: Any, url: str, slug: str, ibge: str) -> list[dict]:
    """Try extracting from divs with licitacao-related classes/ids."""
    records: list[dict] = []
    seen_hashes: set[str] = set()

    patterns = [
        "div[id*='licitacao']", "div[class*='licitacao']",
        "div[id*='edital']", "div[class*='edital']",
        "div[id*='resultado']", "div[class*='resultado']",
        "div[class*='lista']", "section[class*='licitacao']",
    ]

    for pattern in patterns:
        containers = soup.select(pattern)
        for container in containers:
            items = container.find_all(["div", "li"], recursive=False)
            for item in items:
                texto = item.get_text(strip=True)
                if not texto or len(texto) < 10:
                    continue

                links = item.find_all("a")
                link = ""
                if links:
                    link = extract_link(links[0], "", url)

                record = make_record(
                    slug=slug,
                    ibge=ibge,
                    portal_url=url,
                    modalidade=extract_text(item, "[class*='modalidade'], .tipo, span:first-child"),
                    data_publicacao=extract_text(item, "[class*='data'], .data"),
                    objeto=texto[:200],  # Use full text as objeto fallback
                    link=link,
                )
                if record and record["content_hash"] not in seen_hashes:
                    seen_hashes.add(record["content_hash"])
                    records.append(record)

        if records:
            _logger.info("Generico: div extraction found %d records via '%s'", len(records), pattern)
            return records

    return records


def _any_table_extraction(soup: Any, url: str, slug: str, ibge: str) -> list[dict]:
    """Last resort: try any table with at least 2 data rows."""
    all_tables = soup.find_all("table")
    for table in all_tables:
        trs = table.find_all("tr")
        if len(trs) > 3:  # header + at least 2 data rows
            records = _parse_table(table, url, slug, ibge)
            if records:
                _logger.info("Generico: any-table extraction found %d records for %s", len(records), slug)
                return records
    return []

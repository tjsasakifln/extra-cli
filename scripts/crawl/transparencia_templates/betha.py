"""Betha Platform Template — Extra Consultoria.

Plataforma Betha Sistemas (``atende.net``).
Usada por ~80 municípios de Santa Catarina.

Padrão de URL:
    https://{slug}.atende.net/transparencia

Estrutura HTML típica:
    - Tabela com classe ``.licitacao`` ou ``.tabela-licitacoes``
    - Colunas: Data, Modalidade, Objeto, Órgão, Valor
"""

from __future__ import annotations

import logging
from typing import Any

from scripts.crawl.transparencia_templates.base import (
    extract_link,
    extract_text,
    make_record,
)

_logger = logging.getLogger(__name__)

PLATFORM = "betha"
NAME = "Betha Sistemas"
DESCRIPTION = "Portal Transparência Betha (atende.net) — ~80 municípios SC"
URL_PATTERNS = ["{slug}.atende.net/transparencia"]

# Default CSS selectors for Betha portals
SELECTORS: dict[str, str] = {
    "lista_licitacoes": "table.licitacao, table.tabela-licitacoes, table.table",
    "modalidade": "td:nth-child(2)",
    "data": "td:nth-child(1)",
    "objeto": "td:nth-child(3)",
    "orgao": "td:nth-child(4)",
    "valor": "td:nth-child(5)",
    "link": "a[href]",
}


def parse_page(soup: Any, url: str = "", slug: str = "", ibge: str = "") -> list[dict]:
    """Parse Betha transparency portal HTML into record dicts.

    Tries multiple table selectors in order of specificity.
    Falls back to extracting any <tr> elements from the page.

    Args:
        soup: BeautifulSoup parsed page.
        url: Full portal URL.
        slug: Municipality slug.
        ibge: IBGE code.

    Returns:
        List of record dicts with keys: slug, codigo_municipio_ibge,
        portal_url, modalidade, data_publicacao, objeto, orgao,
        valor, link, content_hash.
    """
    records: list[dict] = []
    seen_hashes: set[str] = set()

    # Ordered list of table selectors to try
    table_selectors = [
        "table.licitacao",
        "table.tabela-licitacoes",
        "table.table.table-striped",
        "table.table",
        "table[id*='licitacao']",
        "table[id*='Licitacao']",
        "table[id*='grid']",
        "table",
    ]

    parsed_table = False
    for sel in table_selectors:
        table = soup.select_one(sel)
        if table is None:
            continue

        trs = table.find_all("tr")
        if len(trs) <= 1:
            continue  # header only, skip

        _logger.debug("Betha: matched table selector '%s' (%d rows)", sel, len(trs))

        for idx, tr in enumerate(trs):
            if idx == 0:
                continue  # skip header
            if tr.name != "tr":
                continue

            modalidade = extract_text(tr, "td:nth-child(2)")
            data_txt = extract_text(tr, "td:nth-child(1)")
            objeto = extract_text(tr, "td:nth-child(3)")
            orgao = extract_text(tr, "td:nth-child(4)")
            valor = extract_text(tr, "td:nth-child(5)")
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

        parsed_table = True
        break  # Found a working selector

    if not parsed_table:
        _logger.info("Betha: no table structure found for %s — trying generic div extraction", slug)
        records = _fallback_div_parse(soup, url, slug, ibge)

    _logger.debug("Betha: extracted %d records from %s", len(records), slug)
    return records


def _fallback_div_parse(soup: Any, url: str, slug: str, ibge: str) -> list[dict]:
    """Fallback: try to extract from div-based layouts."""
    records: list[dict] = []
    seen_hashes: set[str] = set()

    containers = soup.select("div[id*='licitacao'], div[class*='licitacao'], div[class*='resultado']")

    for container in containers:
        items = container.find_all("div", recursive=False)
        for item in items:
            modalidade = extract_text(item, ".modalidade, [class*='modalidade'], span:nth-child(2)")
            data_txt = extract_text(item, ".data, [class*='data'], span:nth-child(1)")
            objeto = extract_text(item, ".objeto, [class*='objeto'], span:nth-child(3)")
            link = extract_link(item, "a[href]", url)

            record = make_record(
                slug=slug,
                ibge=ibge,
                portal_url=url,
                modalidade=modalidade,
                data_publicacao=data_txt,
                objeto=objeto,
                link=link,
            )
            if record and record["content_hash"] not in seen_hashes:
                seen_hashes.add(record["content_hash"])
                records.append(record)

    return records

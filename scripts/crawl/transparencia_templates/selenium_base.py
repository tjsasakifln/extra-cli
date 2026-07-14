"""Selenium Base Template — Extra Consultoria.

Generic template for JavaScript-rendered transparency portals.
Designed to work with ``SeleniumCrawler`` which pre-renders JS before handing
the HTML to this template for parsing.

Strategy:
    1. Use the same CSS selectors as other platform templates
    2. Handle common JS-rendered patterns: dynamic tables, infinite scroll,
       paginated containers, shadow DOM fallback
    3. Support for multi-page scraping via "next page" selector
    4. Same ``parse_page(soup, url, slug, ibge)`` interface as other templates

This template is the default for municipios with ``requires_js: true``
when no platform-specific template is available.
"""

from __future__ import annotations

import logging
from typing import Any

from scripts.crawl.transparencia_templates.base import (
    extract_link,
    extract_text,
    make_record,
    parse_div_list,
    parse_table_rows,
)

_logger = logging.getLogger(__name__)

PLATFORM = "selenium_base"
NAME = "Selenium Generic (JS-Rendered)"
DESCRIPTION = "Template genérico para portais JS-rendered via Selenium"
URL_PATTERNS: list[str] = []

# Default CSS selectors for JS-rendered transparency portals
SELECTORS: dict[str, str] = {
    "lista_licitacoes": "table.licitacao, table.tabela-licitacoes, "
    "div.lista-licitacoes, div#licitacoes, "
    "div[class*='grid'] table, section[class*='licitacao'] table",
    "modalidade": "td:nth-child(2), .modalidade, [class*='modalidade']",
    "data": "td:nth-child(1), .data, [class*='data'], .data-publicacao",
    "objeto": "td:nth-child(3), .objeto, [class*='objeto'], .descricao",
    "orgao": "td:nth-child(4), .orgao, [class*='orgao'], .unidade",
    "valor": "td:nth-child(5), .valor, [class*='valor'], .val or",
    "link": "a[href]",
}

# Selectors for "next page" in paginated JS tables
_NEXT_PAGE_SELECTORS = [
    "a.next",
    "a[rel='next']",
    ".pagination .next a",
    ".pagination a:last-child",
    "button.next",
    "button[aria-label='Next']",
    "a[class*='proxima']",
    "a[class*='next']",
    "[class*='paginacao'] a:last-child",
    "li.next a",
]


def parse_page(soup: Any, url: str = "", slug: str = "", ibge: str = "") -> list[dict]:
    """Parse a JS-rendered transparency portal HTML into record dicts.

    Tries multiple strategies in order:
    1. Direct table extraction using SELECTORS
    2. Div-based list extraction
    3. Generic fallback: find any table with data

    Args:
        soup: BeautifulSoup parsed page (post-JS-rendering).
        url: Full portal URL.
        slug: Municipality slug.
        ibge: IBGE code.

    Returns:
        List of record dicts with keys: slug, codigo_municipio_ibge,
        portal_url, modalidade, data_publicacao, objeto, orgao,
        valor, link, content_hash.
    """
    records: list[dict] = []

    # Strategy 1: Direct table extraction
    records = _table_extraction(soup, url, slug, ibge)
    if records:
        _logger.debug("Selenium base: table extraction found %d records for %s", len(records), slug)
        return records

    # Strategy 2: Div-based list extraction
    records = _div_extraction(soup, url, slug, ibge)
    if records:
        _logger.debug("Selenium base: div extraction found %d records for %s", len(records), slug)
        return records

    # Strategy 3: Generic table fallback
    records = _generic_table_fallback(soup, url, slug, ibge)
    if records:
        _logger.debug("Selenium base: generic fallback found %d records for %s", len(records), slug)

    return records


def _table_extraction(soup: Any, url: str, slug: str, ibge: str) -> list[dict]:
    """Try extracting data from tables using standard selectors."""
    sel = SELECTORS["lista_licitacoes"]

    # Try each comma-separated selector
    for single_sel in [s.strip() for s in sel.split(",")]:
        if not single_sel:
            continue
        try:
            records = parse_table_rows(
                soup,
                single_sel,
                url=url,
                slug=slug,
                ibge=ibge,
                modalidade_sel=SELECTORS["modalidade"],
                data_sel=SELECTORS["data"],
                objeto_sel=SELECTORS["objeto"],
                orgao_sel=SELECTORS.get("orgao", ""),
                valor_sel=SELECTORS.get("valor", ""),
                link_sel=SELECTORS.get("link", "a[href]"),
            )
            if records:
                _logger.debug("Selenium base: matched table '%s' -> %d records", single_sel, len(records))
                return records
        except Exception as e:
            _logger.debug("Selenium base: selector '%s' failed: %s", single_sel, e)
            continue

    return []


def _div_extraction(soup: Any, url: str, slug: str, ibge: str) -> list[dict]:
    """Try extracting from div-based list layouts (common in SPAs)."""
    container_patterns = [
        "div.lista-licitacoes, div#lista-licitacoes",
        "div[class*='licitacao']",
        "div[id*='licitacao']",
        "div[class*='resultado']",
        "section[class*='licitacao']",
        "div[class*='grid']",
        "div[class*='table']",
    ]

    for pattern in container_patterns:
        try:
            records = parse_div_list(
                soup,
                pattern,
                url=url,
                slug=slug,
                ibge=ibge,
                item_selector="div.row, div.item, div[class*='linha'], div.card, li",
                modalidade_sel=".modalidade, [class*='modalidade'], span:nth-child(2)",
                data_sel=".data, [class*='data'], span:nth-child(1)",
                objeto_sel=".objeto, [class*='objeto'], span:nth-child(3)",
                orgao_sel=".orgao, [class*='orgao']",
                valor_sel=".valor, [class*='valor']",
                link_sel="a[href]",
            )
            if records:
                return records
        except Exception:
            _logger.debug("Selenium base: div extraction pattern '%s' failed", pattern)
            continue

    return []


def _generic_table_fallback(soup: Any, url: str, slug: str, ibge: str) -> list[dict]:
    """Last resort: find any table with 3+ columns and try to extract data."""
    all_tables = soup.find_all("table")
    records: list[dict] = []
    seen_hashes: set[str] = set()

    for table in all_tables:
        trs = table.find_all("tr")
        if len(trs) <= 1:
            continue

        for idx, tr in enumerate(trs):
            if idx == 0:
                continue  # skip header
            if tr.name != "tr":
                continue

            tds = tr.find_all("td")
            if len(tds) < 2:
                continue

            col_count = len(tds)
            if col_count >= 5:
                modalidade = extract_text(tds[0])
                data_txt = extract_text(tds[1])
                objeto = extract_text(tds[2])
                orgao = extract_text(tds[3])
                valor = extract_text(tds[4])
                link = extract_link(tr, "a[href]", url)
            elif col_count == 4:
                data_txt = extract_text(tds[0])
                modalidade = extract_text(tds[1])
                objeto = extract_text(tds[2])
                valor = extract_text(tds[3])
                orgao = ""
                link = extract_link(tr, "a[href]", url)
            elif col_count == 3:
                data_txt = extract_text(tds[0])
                modalidade = extract_text(tds[1])
                objeto = extract_text(tds[2])
                orgao = ""
                valor = ""
                link = extract_link(tr, "a[href]", url)
            else:
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

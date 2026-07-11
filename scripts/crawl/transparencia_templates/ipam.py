"""Ipam Platform Template — Extra Consultoria.

Plataforma Ipam (``ipm.org.br``).
Usada por ~50 municípios de Santa Catarina.

Padrão de URL:
    https://{slug}.ipm.org.br/transparencia

Estrutura HTML típica:
    - Tabela padronizada com classes ``.tabela-padrao`` ou ``.table``
    - Colunas: Modalidade, Data, Objeto, Valor
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

PLATFORM = "ipam"
NAME = "Ipam"
DESCRIPTION = "Portal Transparência Ipam (ipm.org.br) — ~50 municípios SC"
URL_PATTERNS = ["{slug}.ipm.org.br/transparencia"]

# Default CSS selectors for Ipam portals
SELECTORS: dict[str, str] = {
    "lista_licitacoes": "table.tabela-padrao, table.table, table.grid",
    "modalidade": "td:nth-child(1)",
    "data": "td:nth-child(2)",
    "objeto": "td:nth-child(3)",
    "orgao": "td:nth-child(4)",
    "valor": "td:nth-child(5)",
    "link": "a[href]",
}


def parse_page(soup: Any, url: str = "", slug: str = "", ibge: str = "") -> list[dict]:
    """Parse Ipam transparency portal HTML into record dicts.

    Tries multiple table selectors. Ipam portals typically use
    a standard grid/table layout with class ``.tabela-padrao``.

    Args:
        soup: BeautifulSoup parsed page.
        url: Full portal URL.
        slug: Municipality slug.
        ibge: IBGE code.

    Returns:
        List of record dicts.
    """
    records: list[dict] = []
    seen_hashes: set[str] = set()

    table_selectors = [
        "table.tabela-padrao",
        "table.grid",
        "table.table.table-bordered",
        "table.table",
        "table[id*='grid']",
        "table[id*='GridView']",
        "table",
    ]

    parsed_table = False
    for sel in table_selectors:
        table = soup.select_one(sel)
        if table is None:
            continue

        trs = table.find_all("tr")
        if len(trs) <= 1:
            continue

        _logger.debug("Ipam: matched table selector '%s' (%d rows)", sel, len(trs))

        for idx, tr in enumerate(trs):
            if idx == 0:
                continue
            if tr.name != "tr":
                continue

            tds = tr.find_all("td")
            if len(tds) < 2:
                continue

            modalidade = extract_text(tds[0]) if len(tds) > 0 else ""
            data_txt = extract_text(tds[1]) if len(tds) > 1 else ""
            objeto = extract_text(tds[2]) if len(tds) > 2 else ""
            orgao = extract_text(tds[3]) if len(tds) > 3 else ""
            valor = extract_text(tds[4]) if len(tds) > 4 else ""
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
        break

    if not parsed_table:
        _logger.info("Ipam: no table structure found for %s — trying generic extraction", slug)
        records = _generic_fallback(soup, url, slug, ibge)

    _logger.debug("Ipam: extracted %d records from %s", len(records), slug)
    return records


def _generic_fallback(soup: Any, url: str, slug: str, ibge: str) -> list[dict]:
    """Fallback: look for any data-like table structure."""
    records: list[dict] = []
    all_tables = soup.find_all("table")
    for table in all_tables:
        trs = table.find_all("tr")
        if len(trs) <= 2:
            continue
        for tr in trs[1:]:
            if tr.name != "tr":
                continue
            tds = tr.find_all("td")
            if len(tds) < 2:
                continue
            record = make_record(
                slug=slug,
                ibge=ibge,
                portal_url=url,
                modalidade=extract_text(tds[0]),
                data_publicacao=extract_text(tds[1]) if len(tds) > 1 else "",
                objeto=extract_text(tds[2]) if len(tds) > 2 else "",
            )
            if record:
                records.append(record)
        if records:
            break
    return records

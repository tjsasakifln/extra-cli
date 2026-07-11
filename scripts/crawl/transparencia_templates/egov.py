"""E-gov Platform Template — Extra Consultoria.

Plataforma E-gov Betha (``e-gov.betha.com.br``).
Usada por ~40 municípios de Santa Catarina.

Padrão de URL:
    https://{slug}.e-gov.betha.com.br

Estrutura HTML típica:
    - Container ``div.lista-licitacoes`` com tabela interna
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

PLATFORM = "egov"
NAME = "E-gov Betha"
DESCRIPTION = "Portal Transparência E-gov (e-gov.betha.com.br) — ~40 municípios SC"
URL_PATTERNS = ["{slug}.e-gov.betha.com.br"]

# Default CSS selectors for E-gov portals
SELECTORS: dict[str, str] = {
    "lista_licitacoes": "div.lista-licitacoes table, div#lista-licitacoes table",
    "modalidade": "td:nth-child(1)",
    "data": "td:nth-child(2)",
    "objeto": "td:nth-child(3)",
    "orgao": "",
    "valor": "td:nth-child(4)",
    "link": "a[href]",
}


def parse_page(soup: Any, url: str = "", slug: str = "", ibge: str = "") -> list[dict]:
    """Parse E-gov transparency portal HTML into record dicts.

    E-gov portals typically use a ``div.lista-licitacoes`` container
    with an internal table structure. Columns are usually:
    1 - Modalidade, 2 - Data, 3 - Objeto, 4 - Valor.

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

    # Try div.lista-licitacoes first (E-gov specific)
    container_selectors = [
        "div.lista-licitacoes",
        "div#lista-licitacoes",
        "div.conteudo-licitacoes",
        "div.resultado-licitacoes",
        "section.licitacoes",
    ]

    parsed = False
    for container_sel in container_selectors:
        container = soup.select_one(container_sel)
        if container is None:
            continue

        # Try table inside container
        table = container.select_one("table")
        if table:
            trs = table.find_all("tr")
            _logger.debug("E-gov: matched container '%s' with table (%d rows)", container_sel, len(trs))

            for idx, tr in enumerate(trs):
                if idx == 0:
                    continue
                if tr.name != "tr":
                    continue

                modalidade = extract_text(tr, "td:nth-child(1)")
                data_txt = extract_text(tr, "td:nth-child(2)")
                objeto = extract_text(tr, "td:nth-child(3)")
                valor = extract_text(tr, "td:nth-child(4)")
                link = extract_link(tr, "a[href]", url)

                record = make_record(
                    slug=slug,
                    ibge=ibge,
                    portal_url=url,
                    modalidade=modalidade,
                    data_publicacao=data_txt,
                    objeto=objeto,
                    valor=valor,
                    link=link,
                )
                if record and record["content_hash"] not in seen_hashes:
                    seen_hashes.add(record["content_hash"])
                    records.append(record)

            parsed = True
            break

        # Try div items inside container
        items = container.find_all("div", class_=True, recursive=False)
        if items:
            _logger.debug("E-gov: matched container '%s' with div items (%d)", container_sel, len(items))
            for item in items:
                modalidade = extract_text(item, "[class*='modalidade'], .tipo")
                data_txt = extract_text(item, "[class*='data'], .data-publicacao")
                objeto = extract_text(item, "[class*='objeto'], .descricao")
                valor = extract_text(item, "[class*='valor'], .val")
                link = extract_link(item, "a[href]", url)

                record = make_record(
                    slug=slug,
                    ibge=ibge,
                    portal_url=url,
                    modalidade=modalidade,
                    data_publicacao=data_txt,
                    objeto=objeto,
                    valor=valor,
                    link=link,
                )
                if record and record["content_hash"] not in seen_hashes:
                    seen_hashes.add(record["content_hash"])
                    records.append(record)

            parsed = True
            break

    if not parsed:
        # Fallback: try table extraction directly
        records = _table_fallback(soup, url, slug, ibge)

    _logger.debug("E-gov: extracted %d records from %s", len(records), slug)
    return records


def _table_fallback(soup: Any, url: str, slug: str, ibge: str) -> list[dict]:
    """Fallback: try any table on the page."""
    records: list[dict] = []
    seen_hashes: set[str] = set()

    tables = soup.find_all("table")
    for table in tables:
        trs = table.find_all("tr")
        if len(trs) <= 2:
            continue
        for idx, tr in enumerate(trs):
            if idx == 0:
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
            if record and record["content_hash"] not in seen_hashes:
                seen_hashes.add(record["content_hash"])
                records.append(record)
        if records:
            break
    return records

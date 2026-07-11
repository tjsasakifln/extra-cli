"""Base utilities for transparencia template modules.

Shared parsing helpers used by all platform-specific templates.
"""

from __future__ import annotations

import hashlib
import logging
import re
from typing import Any
from urllib.parse import urlparse

_logger = logging.getLogger(__name__)


def extract_text(element: Any, selector: str = "") -> str:
    """Extract text from a CSS-selected element, or from the element itself.

    If ``selector`` is empty/blank, returns the element's own text content.
    If ``selector`` is provided, returns the text of the first matching child.
    Returns empty string on any error or missing element.
    """
    if element is None:
        return ""
    try:
        if selector:
            el = element.select_one(selector)
            return el.get_text(strip=True) if el else ""
        else:
            return element.get_text(strip=True) if hasattr(element, "get_text") else str(element).strip()
    except Exception:
        return ""


def extract_link(element: Any, selector: str, base_url: str) -> str:
    """Extract href from a CSS-selected anchor element, resolving relative URLs."""
    try:
        el = element.select_one(selector) if selector else element
        if el and el.name == "a" and el.get("href"):
            href = el["href"]
            if href.startswith("/"):
                parsed = urlparse(base_url)
                return f"{parsed.scheme}://{parsed.netloc}{href}"
            return href
    except Exception:
        pass
    return ""


def make_record(
    *,
    slug: str,
    ibge: str,
    portal_url: str,
    modalidade: str = "",
    data_publicacao: str = "",
    objeto: str = "",
    orgao: str = "",
    valor: str = "",
    link: str = "",
) -> dict | None:
    """Create a normalized record dict with content hash.

    Returns ``None`` if no meaningful data was extracted (all fields empty).
    """
    if not any([modalidade, objeto, data_publicacao]):
        return None

    record: dict[str, Any] = {
        "slug": slug,
        "codigo_municipio_ibge": ibge,
        "portal_url": portal_url,
        "modalidade": modalidade,
        "data_publicacao": data_publicacao,
        "objeto": objeto,
        "orgao": orgao,
        "valor": valor,
        "link": link,
    }

    content_key = f"{modalidade}|{objeto}|{data_publicacao}|{valor}"
    record["content_hash"] = hashlib.md5(content_key.encode(), usedforsecurity=False).hexdigest()

    return record


def parse_table_rows(
    soup: Any,
    table_selector: str,
    *,
    url: str = "",
    slug: str = "",
    ibge: str = "",
    modalidade_sel: str = "",
    data_sel: str = "",
    objeto_sel: str = "",
    orgao_sel: str = "",
    valor_sel: str = "",
    link_sel: str = "",
    skip_header: bool = True,
) -> list[dict]:
    """Parse HTML table rows into record dicts.

    Args:
        soup: BeautifulSoup parsed page.
        table_selector: CSS selector for the table element.
        url: Portal URL (for relative link resolution).
        slug: Municipality slug.
        ibge: IBGE code.
        *_sel: CSS selectors for each column within a row.
        skip_header: Whether to skip the first <tr> (header row).

    Returns:
        List of record dicts.
    """
    table = soup.select_one(table_selector) if table_selector else None
    if table is None:
        return []

    rows: list[dict] = []
    trs = table.find_all("tr")

    for idx, tr in enumerate(trs):
        if skip_header and idx == 0:
            continue
        if tr.name != "tr":
            continue

        record = make_record(
            slug=slug,
            ibge=ibge,
            portal_url=url,
            modalidade=extract_text(tr, modalidade_sel),
            data_publicacao=extract_text(tr, data_sel),
            objeto=extract_text(tr, objeto_sel),
            orgao=extract_text(tr, orgao_sel),
            valor=extract_text(tr, valor_sel),
            link=extract_link(tr, link_sel, url) if link_sel else "",
        )
        if record:
            rows.append(record)

    return rows


def parse_div_list(
    soup: Any,
    container_selector: str,
    *,
    url: str = "",
    slug: str = "",
    ibge: str = "",
    item_selector: str = "",
    modalidade_sel: str = "",
    data_sel: str = "",
    objeto_sel: str = "",
    orgao_sel: str = "",
    valor_sel: str = "",
    link_sel: str = "",
) -> list[dict]:
    """Parse a list of div items into record dicts.

    Similar to ``parse_table_rows`` but for div-based layouts.
    """
    container = soup.select_one(container_selector) if container_selector else None
    if container is None:
        return []

    items = container.select(item_selector) if item_selector else container.children

    rows: list[dict] = []
    for item in items:
        if hasattr(item, "name") and item.name is None:
            continue

        record = make_record(
            slug=slug,
            ibge=ibge,
            portal_url=url,
            modalidade=extract_text(item, modalidade_sel),
            data_publicacao=extract_text(item, data_sel),
            objeto=extract_text(item, objeto_sel),
            orgao=extract_text(item, orgao_sel),
            valor=extract_text(item, valor_sel),
            link=extract_link(item, link_sel, url) if link_sel else "",
        )
        if record:
            rows.append(record)

    return rows

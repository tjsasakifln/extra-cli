"""DOE-SC Selenium Crawler adapter — Extra Consultoria.

Fallback Selenium-based crawler for the DOE-SC (Diario Oficial do Estado de
Santa Catarina) portal when the HTTP API is blocked by anti-bot measures or
when JS rendering is required for authentication.

Portal: https://portal.doe.sea.sc.gov.br
API base: https://portal.doe.sea.sc.gov.br/apis/doe-api/

This adapter uses the SeleniumCrawler base class to:
    1. Navigate to the DOE-SC Angular SPA portal
    2. Authenticate via the login form (CPF + password) if credentials provided
    3. Scrape publication data from the rendered pages
    4. Extract materia details from the SPA state

Adaptado para a interface sync esperada pelo monitor.py:
    crawl(mode) -> list[dict]       # busca dados da pagina renderizada
    transform(records) -> list[dict] # normaliza para schema pncp_raw_bids
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from scripts.crawl.common import extract_cnpj, safe_float

# Add project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DOE_SC_PORTAL = "https://portal.doe.sea.sc.gov.br"

DOE_SC_LOGIN = os.getenv("DOE_SC_LOGIN", "")
DOE_SC_PASSWORD = os.getenv("DOE_SC_PASSWORD", "")

DOE_SC_ENABLED = os.getenv("DOE_SC_ENABLED", "true").lower() in ("true", "1")

DOE_SC_FULL_DAYS = int(os.getenv("DOE_SC_FULL_DAYS", "90"))
DOE_SC_INCREMENTAL_DAYS = int(os.getenv("DOE_SC_INCREMENTAL_DAYS", "1"))

SELENIUM_TIMEOUT = int(os.getenv("SELENIUM_TIMEOUT", "30"))
SELENIUM_REQUEST_DELAY = float(os.getenv("SELENIUM_REQUEST_DELAY", "3.0"))

PAGE_SIZE = int(os.getenv("DOE_SC_PAGE_SIZE", "50"))
MAX_PAGES = int(os.getenv("DOE_SC_MAX_PAGES", "10"))  # conservative for Selenium

ESFERA_ID_ESTADUAL = 2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _generate_content_hash(record: dict) -> str:
    """Deterministic MD5 hash for dedup using visible fields."""
    titulo = (record.get("titulo") or "").strip()
    orgao = (record.get("orgao") or "").strip()
    data = (record.get("data") or "").strip()
    key_fields = [titulo, orgao, data]
    key_str = "|".join(key_fields)
    return hashlib.md5(key_str.encode("utf-8"), usedforsecurity=False).hexdigest()


# ---------------------------------------------------------------------------
# Crawl interface
# ---------------------------------------------------------------------------


def crawl(mode: str = "full") -> list[dict]:
    """Crawl DOE-SC portal using Selenium for JS rendering.

    Args:
        mode: 'full' (90 days) or 'incremental' (1 day)

    Returns:
        List of raw materia dicts extracted from the rendered portal.
    """
    if not DOE_SC_ENABLED:
        _logger.info("[DOE-SC-SELENIUM] Disabled (DOE_SC_ENABLED=false)")
        return []

    days = DOE_SC_FULL_DAYS if mode == "full" else DOE_SC_INCREMENTAL_DAYS
    data_final = date.today()
    data_inicial = data_final - timedelta(days=days)

    _logger.info(
        "[DOE-SC-SELENIUM] Selenium crawl %s mode: %s to %s (%d days)",
        mode,
        data_inicial,
        data_final,
        days,
    )

    # Try to import and use the SeleniumCrawler base class
    try:
        from scripts.crawl.selenium_crawler import SeleniumCrawler
    except ImportError as e:
        _logger.error("[DOE-SC-SELENIUM] SeleniumCrawler not available: %s", e)
        return []

    crawler = SeleniumCrawler(
        browser="chrome",
        headless=True,
        timeout=SELENIUM_TIMEOUT,
        request_delay=SELENIUM_REQUEST_DELAY,
    )

    try:
        records = _selenium_crawl(crawler, data_inicial, data_final)
        return records
    except Exception as e:
        _logger.error("[DOE-SC-SELENIUM] Crawl failed: %s: %s", type(e).__name__, e)
        return []
    finally:
        crawler.close()


def _selenium_crawl(
    crawler: Any,
    date_from: date,
    date_to: date,
) -> list[dict]:
    """Execute the Selenium-based crawl.

    Login flow:
        1. Navigate to portal
        2. If login form present, fill credentials and submit
        3. Wait for authenticated state
        4. Navigate to materia listing
        5. Extract data from rendered pages

    Args:
        crawler: SeleniumCrawler instance.
        date_from: Start date.
        date_to: End date.

    Returns:
        List of record dicts.
    """

    driver = crawler._ensure_driver()

    # Step 1: Navigate to portal
    _logger.info("[DOE-SC-SELENIUM] Navigating to %s", DOE_SC_PORTAL)
    driver.get(DOE_SC_PORTAL)
    time.sleep(3)  # Allow SPA boot

    # Step 2: Login if credentials available
    if DOE_SC_LOGIN and DOE_SC_PASSWORD:
        _logger.info("[DOE-SC-SELENIUM] Credentials found — attempting login")
        try:
            _selenium_login(driver, DOE_SC_LOGIN, DOE_SC_PASSWORD)
        except Exception as e:
            _logger.warning("[DOE-SC-SELENIUM] Login failed: %s", e)
            # Continue anyway — might get partial data
    else:
        _logger.warning(
            "[DOE-SC-SELENIUM] No credentials (DOE_SC_LOGIN/DOE_SC_PASSWORD) — "
            "cannot authenticate. Set env vars to enable login."
        )
        # Try to scrape any public content
        pass

    # Step 3: Navigate to materia listing
    records = _selenium_extract_materias(driver, date_from, date_to)

    _logger.info("[DOE-SC-SELENIUM] Extracted %d records", len(records))
    return records


def _selenium_login(driver: Any, login: str, password: str) -> None:
    """Authenticate on the DOE-SC Angular SPA via login form.

    Looks for input fields and login button in the Angular SPA.

    Args:
        driver: Selenium WebDriver instance.
        login: CPF/username.
        password: Password.
    """
    from selenium.webdriver.common.by import By

    # Look for login input fields — various possible selectors
    # Angular SPA may use different input structures
    login_field = None
    password_field = None
    submit_button = None

    # Try common patterns for the login form
    selectors = {
        "login": [
            "input[type='text']",
            "input[name='login']",
            "input[placeholder*='CPF']",
            "input[placeholder*='usuário']",
            "input[placeholder*='Usuário']",
            "input[formcontrolname='login']",
            "input[pinputtext]",
        ],
        "password": [
            "input[type='password']",
            "input[name='password']",
            "input[formcontrolname='password']",
        ],
        "submit": [
            "button[type='submit']",
            "button:has-text('Entrar')",
            "button:has-text('Login')",
            "button[pbutton]",
            "button[class*='login']",
            "button[class*='submit']",
        ],
    }

    # Find login field
    for sel in selectors["login"]:
        try:
            login_field = driver.find_element(By.CSS_SELECTOR, sel)
            if login_field.is_displayed():
                break
        except Exception:
            _logger.debug("[DOE-SC-SELENIUM] Login selector '%s' not found", sel)
            continue
    else:
        _logger.warning("[DOE-SC-SELENIUM] Login input field not found")
        return

    # Find password field
    for sel in selectors["password"]:
        try:
            password_field = driver.find_element(By.CSS_SELECTOR, sel)
            if password_field.is_displayed():
                break
        except Exception:
            _logger.debug("[DOE-SC-SELENIUM] Password selector '%s' not found", sel)
            continue
    else:
        _logger.warning("[DOE-SC-SELENIUM] Password input field not found")
        return

    # Fill credentials
    login_field.clear()
    login_field.send_keys(login)
    password_field.clear()
    password_field.send_keys(password)

    # Find and click submit
    for sel in selectors["submit"]:
        try:
            submit_button = driver.find_element(By.CSS_SELECTOR, sel)
            if submit_button.is_displayed():
                break
        except Exception:
            _logger.debug("[DOE-SC-SELENIUM] Submit button selector '%s' not found", sel)
            continue
    else:
        _logger.warning("[DOE-SC-SELENIUM] Submit button not found")
        return

    submit_button.click()
    time.sleep(3)  # Wait for auth response

    # Check if login succeeded (URL changed or no login form visible)
    current_url = driver.current_url
    if "login" not in current_url.lower():
        _logger.info("[DOE-SC-SELENIUM] Login successful — redirected to %s", current_url)
    else:
        _logger.warning("[DOE-SC-SELENIUM] Login may have failed — still on login page")


def _selenium_extract_materias(
    driver: Any,
    date_from: date,
    date_to: date,
) -> list[dict]:
    """Extract materia records from the rendered SPA.

    Navigates to pages and extracts data from the DOM.

    Args:
        driver: Selenium WebDriver instance.
        date_from: Start date.
        date_to: End date.

    Returns:
        List of extracted record dicts.
    """
    from selenium.webdriver.common.by import By

    records: list[dict] = []
    seen_hashes: set[str] = set()

    # Try multiple URL patterns to find the materia listing
    materia_urls = [
        f"{DOE_SC_PORTAL}/#/materias",
        f"{DOE_SC_PORTAL}/#/consultar-materia",
        f"{DOE_SC_PORTAL}/#/diario/consulta",
        f"{DOE_SC_PORTAL}/#/portal/materias",
    ]

    page = 1

    while page <= MAX_PAGES:
        # Try to navigate to materia listing
        navigated = False
        for url_template in materia_urls:
            url = url_template
            # Add pagination if supported
            try:
                driver.get(url)
                time.sleep(3)

                # Check if the page loaded with content
                body_text = driver.find_element(By.TAG_NAME, "body").text
                if body_text and len(body_text) > 100:
                    navigated = True
                    _logger.info("[DOE-SC-SELENIUM] Loaded materia page: %s", url)
                    break
            except Exception:
                _logger.debug("[DOE-SC-SELENIUM] Navigation to '%s' failed — skipping", url)
                continue

        if not navigated:
            _logger.warning("[DOE-SC-SELENIUM] Could not navigate to materia listing")
            break

        # Extract data from the current page
        page_records = _extract_page_data(driver, date_from, date_to, seen_hashes)
        records.extend(page_records)
        _logger.info(
            "[DOE-SC-SELENIUM] Page %d: %d records",
            page,
            len(page_records),
        )

        # Try to find and click "next page" button
        next_selectors = [
            "button[class*='next']",
            "a[class*='next']",
            "button[aria-label*='Próximo']",
            "button[aria-label*='próxima']",
            "button[pbutton][icon*='chevron-right']",
            "button[pbutton][icon*='pi-chevron-right']",
            ".p-paginator-next",
            "a[paginatornexticon]",
        ]

        found_next = False
        for sel in next_selectors:
            try:
                next_btn = driver.find_element(By.CSS_SELECTOR, sel)
                if next_btn.is_displayed() and next_btn.is_enabled():
                    next_btn.click()
                    time.sleep(2)
                    found_next = True
                    page += 1
                    break
            except Exception:
                _logger.debug("[DOE-SC-SELENIUM] Next page selector '%s' not found", sel)
                continue

        if not found_next:
            _logger.info("[DOE-SC-SELENIUM] No more pages")
            break

    return records


def _extract_page_data(
    driver: Any,
    date_from: date,
    date_to: date,
    seen_hashes: set[str],
) -> list[dict]:
    """Extract materia records from the current page DOM.

    Args:
        driver: Selenium WebDriver instance.
        date_from: Start date filter.
        date_to: End date filter.
        seen_hashes: Set of content hashes already seen (dedup).

    Returns:
        List of record dicts.
    """
    from selenium.webdriver.common.by import By

    records: list[dict] = []

    # Try multiple table/container selectors
    row_selectors = [
        "table tbody tr",
        ".p-datatable tbody tr",
        ".p-table tbody tr",
        "[class*='materia'] tr",
        "[class*='table'] tr",
        ".ui-datatable tbody tr",
        ".listagem tr",
        "tr[class*='ng-star']",
    ]

    rows = []
    for sel in row_selectors:
        try:
            rows = driver.find_elements(By.CSS_SELECTOR, sel)
            if rows:
                _logger.debug(
                    "[DOE-SC-SELENIUM] Found %d rows with selector '%s'",
                    len(rows),
                    sel,
                )
                break
        except Exception:
            _logger.debug("[DOE-SC-SELENIUM] Row selector '%s' failed", sel)
            continue

    if not rows:
        _logger.debug("[DOE-SC-SELENIUM] No rows found with known selectors")
        # Fallback: extract all visible text and parse
        try:
            body = driver.find_element(By.TAG_NAME, "body")
            text = body.text
            _logger.debug(
                "[DOE-SC-SELENIUM] Body text length: %d chars",
                len(text),
            )
        except Exception:
            _logger.debug("[DOE-SC-SELENIUM] Body text extraction failed")

    for row in rows:
        try:
            cells = row.find_elements(By.CSS_SELECTOR, "td")
            if len(cells) < 3:
                continue

            # Extract cell text
            cell_texts = [cell.text.strip() for cell in cells]

            # Try to identify columns by position
            materia = {
                "titulo": cell_texts[0] if len(cell_texts) > 0 else "",
                "orgao": cell_texts[1] if len(cell_texts) > 1 else "",
                "data": _extract_date_from_text(cell_texts[2]) if len(cell_texts) > 2 else "",
                "descricao": " | ".join(cell_texts[3:]) if len(cell_texts) > 3 else "",
            }

            # Find link in row
            try:
                link_el = row.find_element(By.CSS_SELECTOR, "a[href]")
                href = link_el.get_attribute("href")
                if href:
                    materia["link"] = href
            except Exception:
                materia["link"] = ""

            # Generate hash for dedup
            materia["_hash"] = _generate_content_hash(materia)

            if materia["_hash"] not in seen_hashes:
                seen_hashes.add(materia["_hash"])
                records.append(materia)

        except Exception as e:
            _logger.debug("[DOE-SC-SELENIUM] Row parse error: %s", e)
            continue

    return records


def _extract_date_from_text(text: str) -> str:
    """Extract a YYYY-MM-DD date from arbitrary text.

    Args:
        text: Text that may contain a date.

    Returns:
        ISO date string or empty string.
    """
    if not text:
        return ""

    # Try DD/MM/YYYY or DD-MM-YYYY
    m = re.search(r"(\d{2})[/-](\d{2})[/-](\d{4})", text)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"

    # Try YYYY-MM-DD
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        return m.group(0)

    return text[:10] if len(text) >= 10 else text


# ---------------------------------------------------------------------------
# Transform interface
# ---------------------------------------------------------------------------


def transform(records: list[dict]) -> list[dict]:
    """Transform raw records from Selenium crawl to pncp_raw_bids schema.

    Args:
        records: List of raw dicts from crawl().

    Returns:
        List of dicts normalized to pncp_raw_bids schema.
    """
    transformed: list[dict] = []
    skipped = 0

    for rec in records:
        try:
            titulo = (rec.get("titulo") or "").strip()
            if not titulo:
                skipped += 1
                continue

            orgao_nome = (rec.get("orgao") or "").strip()
            data_publicacao = _extract_date_from_text(rec.get("data") or "") or ""
            link = rec.get("link") or ""
            descricao = (rec.get("descricao") or "").strip()

            # Try to extract CNPJ from text
            combined_text = f"{titulo} {descricao}"
            cnpj = extract_cnpj(combined_text)

            # Extract value if present
            valor = None
            valor_match = re.search(
                r"(?:R\$|valor[:\s]+|total[:\s]+)\s*([\d\.,]+)",
                combined_text,
                re.IGNORECASE,
            )
            if valor_match:
                valor = safe_float(valor_match.group(1))

            # Build synthetic pncp_id
            pncp_id_input = f"doe_sc_selenium_{_generate_content_hash(rec)}"
            pncp_id = hashlib.md5(pncp_id_input.encode("utf-8"), usedforsecurity=False).hexdigest()

            # Build link
            full_link = link
            if full_link and not full_link.startswith("http"):
                full_link = f"https://portal.doe.sea.sc.gov.br/repositorio/{full_link}"

            transformed.append(
                {
                    "pncp_id": pncp_id,
                    "objeto_compra": titulo[:500] if len(titulo) > 500 else titulo,
                    "valor_total_estimado": valor,
                    "modalidade_id": 0,
                    "modalidade_nome": "Diario Oficial",
                    "esfera_id": ESFERA_ID_ESTADUAL,
                    "uf": "SC",
                    "municipio": "",
                    "codigo_municipio_ibge": "",
                    "orgao_razao_social": orgao_nome or None,
                    "orgao_cnpj": cnpj or None,
                    "data_publicacao": data_publicacao,
                    "data_abertura": None,
                    "data_encerramento": None,
                    "link_pncp": full_link or None,
                    "content_hash": _generate_content_hash(rec),
                    "source_id": pncp_id,
                }
            )

        except (KeyError, ValueError, TypeError, AttributeError) as exc:
            _logger.debug("[DOE-SC-SELENIUM] Transform error: %s: %s", type(exc).__name__, exc)
            skipped += 1
        except Exception as exc:
            _logger.debug("[DOE-SC-SELENIUM] Unexpected transform error: %s: %s", type(exc).__name__, exc)
            skipped += 1

    _logger.info("[DOE-SC-SELENIUM] Transform: %d records, %d skipped", len(transformed), skipped)
    return transformed

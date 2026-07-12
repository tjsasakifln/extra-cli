"""Residual Portal Scraper — Individual Scraping for Residual Transparency Portals.

Cobre os municipios residuais que nao foram capturados pelo batch detect_platform
(COVERAGE-1.3) por terem plataforma de transparencia desconhecida, personalizada
ou nao suportada entre as 8 plataformas mapeadas.

Pipeline por municipio:
    Level 1: Template generico HTTP (requests + BeautifulSoup)
        → Tenta 4 templates genericos: tabela HTML, divs de licitacao,
          listas de contratos, sections de dados
    Level 2: Fallback Selenium (se Level 1 falhar)
        → Renderiza JS, detecta tabelas/divs de licitacao automaticamente
    Level 3: Documentar como inviavel (se ambos falharem)

Integracao com monitor.py:
    - ``crawl(mode)`` → carrega lista residual, executa scraping, retorna resultados
    - ``transform(records)`` → normaliza para schema pncp_raw_bids
      com ``source = 'transparencia_residual'``
    - ``_match_entities_cascade(conn, source, entities)`` → entity matching

Usage:
    python -m scripts.fix.scrape_residual_portals --mode full
    python -m scripts.fix.scrape_residual_portals --municipio chapeco
    python -m scripts.fix.scrape_residual_portals --resume
"""

from __future__ import annotations

import csv
import hashlib
import json
import logging
import os
import re
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

# Add project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (env vars with RESIDUAL_ prefix)
# ---------------------------------------------------------------------------

RESIDUAL_TIMEOUT = int(os.getenv("RESIDUAL_TIMEOUT", "30"))
"""Timeout em segundos para requisicoes HTTP (default: 30s)."""

RESIDUAL_REQUEST_DELAY = float(os.getenv("RESIDUAL_REQUEST_DELAY", "1.0"))
"""Delay entre requisicoes para o mesmo dominio (default: 1s)."""

RESIDUAL_PORTALS_FILE = os.getenv(
    "RESIDUAL_PORTALS_FILE",
    str(_PROJECT_ROOT / "data" / "residual_portals.csv"),
)
"""Caminho para CSV com lista de municipios residuais e URLs."""

RESIDUAL_PROGRESS_FILE = os.getenv(
    "RESIDUAL_PROGRESS_FILE",
    str(_PROJECT_ROOT / "data" / "scrape_residual_progress.json"),
)
"""Caminho para checkpoint de progresso (retomavel)."""

RESIDUAL_OUTPUT_DIR = os.getenv(
    "RESIDUAL_OUTPUT_DIR",
    str(_PROJECT_ROOT / "data"),
)
"""Diretorio para salvar resultados."""

RESIDUAL_MAX_MINUTES = int(os.getenv("RESIDUAL_MAX_MINUTES", "30"))
"""Tempo maximo por municipio em minutos (default: 30) — stop-loss."""

RESIDUAL_BATCH_SIZE = int(os.getenv("RESIDUAL_BATCH_SIZE", "5"))
"""Numero de municipios para processar antes de salvar checkpoint."""

RESIDUAL_SELENIUM_ENABLED = os.getenv("RESIDUAL_SELENIUM_ENABLED", "false").lower() in (
    "true",
    "1",
    "yes",
)
"""Habilita fallback Selenium para portais JS-rendered."""

# ---------------------------------------------------------------------------
# Slug utilities
# ---------------------------------------------------------------------------


def _slugify(name: str) -> str:
    """Convert municipality name to URL slug.

    Lowercase, remove accents, replace spaces with hyphens.
    """
    name = name.lower().strip()
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode("ascii")
    name = re.sub(r"[^a-z0-9]+", "-", name)
    name = name.strip("-")
    return name


# ---------------------------------------------------------------------------
# Templates genericos para extracao HTTP
# ---------------------------------------------------------------------------

TEMPLATES_GENERICOS = [
    {"name": "tabela_html", "selector": "table"},
    {"name": "div_licitacao", "selector": 'div[class*="licit"], div[class*="edit"], div[class*="contrato"]'},
    {"name": "lista_contratos", "selector": "ul.lista-contratos, div.lista-contratos"},
    {"name": "section_dados", "selector": 'section[class*="dados"], section[class*="conteudo"]'},
]

# Keywords para identificar linhas de licitacao em textos extraidos
_LICITACAO_KEYWORDS = [
    "pregao",
    "concorrencia",
    "tomada de precos",
    "convite",
    "concurso",
    "leilao",
    "dispensa",
    "inexigibilidade",
    "edital",
    "licitacao",
    "contrato",
    "rp",
    "registro de precos",
]

_LICITACAO_KEYWORDS_PATTERN = re.compile(
    "|".join(re.escape(kw) for kw in _LICITACAO_KEYWORDS),
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# ResidualPortalScraper
# ---------------------------------------------------------------------------


class ResidualPortalScraper:
    """Scraping individual para portais de transparencia residuais.

    Pipeline:
        1. Carrega lista de municipios residuais de ``residual_portals.csv``
        2. Para cada municipio, tenta extracao via template generico HTTP
        3. Se falhar, tenta fallback Selenium
        4. Se ambos falharem, documenta como inviavel
        5. Resultados sao persistidos e retomaveis via checkpoint
    """

    def __init__(self, timeout: int | None = None):
        self.timeout = timeout or RESIDUAL_TIMEOUT
        self.session = self._init_session()

    def _init_session(self):
        """Inicializa sessao requests com headers padrao."""
        import requests

        session = requests.Session()
        session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        })
        return session

    # ------------------------------------------------------------------
    # Level 1: Template generico HTTP
    # ------------------------------------------------------------------

    def try_generic_templates(self, url: str, municipio: str = "") -> list[dict]:
        """Tenta templates genericos de extracao via HTTP.

        Tenta 4 templates em ordem:
            1. ``table`` — tabela HTML basica
            2. ``div[class*=licit]`` — divs de licitacao
            3. ``ul.lista-contratos`` — listas de contratos
            4. ``section[class*=dados]`` — sections de dados

        Para cada template, verifica se o conteudo extraido contem
        palavras-chave de licitacao. Se encontrar, retorna os bids.

        Args:
            url: URL do portal de transparencia.
            municipio: Nome do municipio (para logging).

        Returns:
            Lista de dicts de bids extraidos, ou [] se falhar.
        """
        try:
            import requests

            resp = self.session.get(url, timeout=self.timeout)
            if resp.status_code not in (200, 301, 302):
                _logger.debug("[%s] HTTP %s for %s", municipio, resp.status_code, url)
                return []

            # Seguir redirect se necessario
            if resp.status_code in (301, 302):
                redirect_url = resp.headers.get("Location", "")
                if redirect_url:
                    resp = self.session.get(redirect_url, timeout=self.timeout)

            content_type = resp.headers.get("Content-Type", "")
            if "text/html" not in content_type and "text/plain" not in content_type:
                _logger.debug("[%s] Non-HTML content: %s", municipio, content_type)
                return []

            from bs4 import BeautifulSoup

            soup = BeautifulSoup(resp.text, "html.parser")

            for template in TEMPLATES_GENERICOS:
                try:
                    elements = soup.select(template["selector"])
                except Exception:
                    continue

                if not elements:
                    continue

                bids = self._parse_elements(elements, template["name"], url, municipio)
                if bids:
                    _logger.info(
                        "[%s] Level 1 SUCCESS via '%s' (%d bids)",
                        municipio,
                        template["name"],
                        len(bids),
                    )
                    return bids

            # Fallback: procurar tabelas com th/td contendo keywords
            all_tables = soup.find_all("table")
            if all_tables:
                for table in all_tables[:5]:  # max 5 tables
                    rows = table.find_all("tr")
                    bid_rows = []
                    for row in rows:
                        cells = row.find_all(["td", "th"])
                        cell_text = " ".join(c.get_text(strip=True) for c in cells)
                        if _LICITACAO_KEYWORDS_PATTERN.search(cell_text):
                            bid_rows.append(row)

                    if bid_rows:
                        bids = self._parse_rows_direct(bid_rows, url, municipio)
                        if bids:
                            _logger.info(
                                "[%s] Level 1 SUCCESS via keyword-detected table (%d bids)",
                                municipio,
                                len(bids),
                            )
                            return bids

            _logger.debug("[%s] Level 1: no content found via generic templates", municipio)
            return []

        except ImportError:
            _logger.error("requests or beautifulsoup4 not installed")
            return []
        except requests.exceptions.Timeout:
            _logger.warning("[%s] Level 1: timeout for %s", municipio, url)
            return []
        except requests.exceptions.ConnectionError:
            _logger.warning("[%s] Level 1: connection error for %s", municipio, url)
            return []
        except requests.exceptions.RequestException as e:
            _logger.warning("[%s] Level 1: HTTP error for %s: %s", municipio, url, e)
            return []
        except Exception as e:
            _logger.warning("[%s] Level 1: unexpected error for %s: %s", municipio, url, e)
            return []

    def _parse_elements(
        self, elements: list[Any], template_name: str, url: str, municipio: str
    ) -> list[dict]:
        """Parse extracted elements into bid records.

        Args:
            elements: List of BeautifulSoup elements.
            template_name: Name of template used.
            url: Portal URL.
            municipio: Municipality name.

        Returns:
            List of bid dicts.
        """
        bids: list[dict] = []
        seen_hashes: set[str] = set()

        for element in elements[:50]:  # limit per template
            # If element is a table, walk rows
            if element.name == "table":
                rows = element.find_all("tr")
                for row in rows:
                    cells = row.find_all(["td", "th"])
                    if len(cells) < 2:
                        continue
                    bid = self._cell_text_to_bid(cells, url, municipio)
                    if bid and bid.get("content_hash") and bid["content_hash"] not in seen_hashes:
                        seen_hashes.add(bid["content_hash"])
                        bids.append(bid)
            elif element.name in ("ul", "ol"):
                items = element.find_all("li")
                for item in items:
                    bid = self._li_to_bid(item, url, municipio)
                    if bid and bid.get("content_hash") and bid["content_hash"] not in seen_hashes:
                        seen_hashes.add(bid["content_hash"])
                        bids.append(bid)
            elif element.name == "div":
                # Try to find sub-items
                sub_items = element.find_all(["div", "li"], recursive=True, limit=30)
                for sub in sub_items:
                    if sub == element:
                        continue
                    bid = self._div_to_bid(sub, url, municipio)
                    if bid and bid.get("content_hash") and bid["content_hash"] not in seen_hashes:
                        seen_hashes.add(bid["content_hash"])
                        bids.append(bid)

        # Log se nao encontrou bids estruturados
        if not bids:
            # Fallback: extrair texto bruto e verificar keywords
            for element in elements[:10]:
                text = element.get_text(strip=True)
                if _LICITACAO_KEYWORDS_PATTERN.search(text) and len(text) > 50:
                    bid = self._text_to_bid(text, url, municipio)
                    if bid and bid.get("content_hash") and bid["content_hash"] not in seen_hashes:
                        seen_hashes.add(bid["content_hash"])
                        bids.append(bid)

        return bids

    def _cell_text_to_bid(self, cells: list[Any], url: str, municipio: str) -> dict | None:
        """Convert table cells to a bid record.

        Args:
            cells: List of td/th BeautifulSoup elements.
            url: Portal URL.
            municipio: Municipality name.

        Returns:
            Bid dict, or None if no relevant data.
        """
        texts = [c.get_text(strip=True) for c in cells]
        full_text = " | ".join(t for t in texts if t)

        if not _LICITACAO_KEYWORDS_PATTERN.search(full_text) and len(full_text) < 30:
            return None

        # Extract link
        link = ""
        for c in cells:
            a = c.find("a")
            if a and a.get("href"):
                href = a["href"]
                if href.startswith("/"):
                    from urllib.parse import urlparse

                    parsed = urlparse(url)
                    link = f"{parsed.scheme}://{parsed.netloc}{href}"
                else:
                    link = href
                break

        # Tentar identificar campos por posicao
        modalidade = ""
        data_publicacao = ""
        objeto = ""
        valor = ""

        if len(texts) >= 3:
            # Heuristica: procurar data no primeiro campo
            data_match = re.search(r"(\d{2})[/-](\d{2})[/-](\d{4})", texts[0])
            if data_match:
                data_publicacao = f"{data_match.group(3)}-{data_match.group(2)}-{data_match.group(1)}"
                if len(texts) >= 2:
                    modalidade = texts[1]
                if len(texts) >= 3:
                    objeto = texts[2]
                if len(texts) >= 4:
                    valor = texts[3]
            else:
                data_match = re.search(r"(\d{2})[/-](\d{2})[/-](\d{4})", full_text)
                if data_match:
                    data_publicacao = f"{data_match.group(3)}-{data_match.group(2)}-{data_match.group(1)}"
                modalidade = texts[0] if texts else ""
                objeto = texts[-1] if texts else ""

        content_key = f"{modalidade}|{objeto}|{data_publicacao}|{valor}"
        content_hash = hashlib.md5(content_key.encode(), usedforsecurity=False).hexdigest()

        return {
            "slug": _slugify(municipio),
            "municipio": municipio,
            "modalidade": modalidade,
            "data_publicacao": data_publicacao,
            "objeto": objeto,
            "valor": valor,
            "link": link,
            "portal_url": url,
            "content_hash": content_hash,
            "_source_subtype": "generic_http",
        }

    def _li_to_bid(self, item: Any, url: str, municipio: str) -> dict | None:
        """Convert a list item to a bid record.

        Args:
            item: BeautifulSoup li element.
            url: Portal URL.
            municipio: Municipality name.

        Returns:
            Bid dict, or None.
        """
        text = item.get_text(strip=True)
        if not _LICITACAO_KEYWORDS_PATTERN.search(text) or len(text) < 30:
            return None

        a = item.find("a")
        link = ""
        if a and a.get("href"):
            href = a["href"]
            if href.startswith("/"):
                from urllib.parse import urlparse

                parsed = urlparse(url)
                link = f"{parsed.scheme}://{parsed.netloc}{href}"
            else:
                link = href

        data_match = re.search(r"(\d{2})[/-](\d{2})[/-](\d{4})", text)
        data_publicacao = ""
        if data_match:
            data_publicacao = f"{data_match.group(3)}-{data_match.group(2)}-{data_match.group(1)}"

        content_hash = hashlib.md5(text.encode(), usedforsecurity=False).hexdigest()

        return {
            "slug": _slugify(municipio),
            "municipio": municipio,
            "modalidade": "",
            "data_publicacao": data_publicacao,
            "objeto": text[:500],
            "valor": "",
            "link": link,
            "portal_url": url,
            "content_hash": content_hash,
            "_source_subtype": "generic_http",
        }

    def _div_to_bid(self, div: Any, url: str, municipio: str) -> dict | None:
        """Convert a div item to a bid record.

        Args:
            div: BeautifulSoup div (or similar) element.
            url: Portal URL.
            municipio: Municipality name.

        Returns:
            Bid dict, or None.
        """
        text = div.get_text(strip=True)
        if not _LICITACAO_KEYWORDS_PATTERN.search(text) or len(text) < 30:
            return None

        a = div.find("a")
        link = ""
        if a and a.get("href"):
            href = a["href"]
            if href.startswith("/"):
                from urllib.parse import urlparse

                parsed = urlparse(url)
                link = f"{parsed.scheme}://{parsed.netloc}{href}"
            else:
                link = href

        # Try to extract structured data from spans/paragraphs
        spans = div.find_all(["span", "p", "label"], recursive=True)
        modalidade = ""
        data_publicacao = ""
        objeto = text[:500]
        valor = ""

        for sp in spans:
            sp_text = sp.get_text(strip=True)
            sp_lower = sp_text.lower()
            cls = " ".join(sp.get("class", [])).lower() if sp.get("class") else ""

            if "data" in cls or any(d in sp_lower for d in ["data", "publicacao", "publicado"]):
                data_match = re.search(r"(\d{2})[/-](\d{2})[/-](\d{4})", sp_text)
                if data_match:
                    data_publicacao = f"{data_match.group(3)}-{data_match.group(2)}-{data_match.group(1)}"
            elif "modalidade" in cls or "tipo" in cls:
                modalidade = sp_text
            elif "valor" in cls:
                valor = sp_text
            elif "objeto" in cls:
                objeto = sp_text

        content_key = f"{modalidade}|{objeto}|{data_publicacao}|{valor}"
        content_hash = hashlib.md5(content_key.encode(), usedforsecurity=False).hexdigest()

        return {
            "slug": _slugify(municipio),
            "municipio": municipio,
            "modalidade": modalidade,
            "data_publicacao": data_publicacao,
            "objeto": objeto,
            "valor": valor,
            "link": link,
            "portal_url": url,
            "content_hash": content_hash,
            "_source_subtype": "generic_http",
        }

    def _text_to_bid(self, text: str, url: str, municipio: str) -> dict | None:
        """Convert plain text to a bid record (fallback).

        Args:
            text: Extracted text content.
            url: Portal URL.
            municipio: Municipality name.

        Returns:
            Bid dict, or None.
        """
        if not text or len(text) < 30:
            return None

        data_match = re.search(r"(\d{2})[/-](\d{2})[/-](\d{4})", text)
        data_publicacao = ""
        if data_match:
            data_publicacao = f"{data_match.group(3)}-{data_match.group(2)}-{data_match.group(1)}"

        content_hash = hashlib.md5(text[:1000].encode(), usedforsecurity=False).hexdigest()

        return {
            "slug": _slugify(municipio),
            "municipio": municipio,
            "modalidade": "",
            "data_publicacao": data_publicacao,
            "objeto": text[:500],
            "valor": "",
            "link": "",
            "portal_url": url,
            "content_hash": content_hash,
            "_source_subtype": "generic_http",
        }

    # ------------------------------------------------------------------
    # Level 2: Fallback Selenium
    # ------------------------------------------------------------------

    def try_selenium_fallback(self, url: str, municipio: str) -> list[dict]:
        """Fallback: tenta extracao via Selenium com deteccao automatica.

        Args:
            url: URL do portal de transparencia.
            municipio: Nome do municipio.

        Returns:
            Lista de bids extraidos, ou [] se falhar.
        """
        if not RESIDUAL_SELENIUM_ENABLED:
            _logger.debug("[%s] Level 2: Selenium disabled via env var", municipio)
            return []

        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support import expected_conditions as EC  # noqa: N812
            from selenium.webdriver.support.ui import WebDriverWait
        except ImportError:
            _logger.warning("[%s] Level 2: Selenium not installed", municipio)
            return []

        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )

        driver = None
        try:
            driver = webdriver.Chrome(options=options)
            driver.set_page_load_timeout(self.timeout)
            driver.get(url)

            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            time.sleep(1)  # Allow async rendering

            # Detect tables/rows via JavaScript
            bids_js = driver.execute_script("""
                const results = [];
                const tables = document.querySelectorAll('table');

                tables.forEach(table => {
                    const rows = table.querySelectorAll('tr');
                    rows.forEach(row => {
                        const cells = row.querySelectorAll('td, th');
                        if (cells.length >= 2) {
                            const rowData = Array.from(cells).map(c => c.textContent.trim());
                            results.push(rowData.join(' | '));
                        }
                    });
                });

                // If no tables, try div-based layouts
                if (results.length === 0) {
                    const divs = document.querySelectorAll(
                        'div[class*="licit"], div[class*="edit"], div[class*="contrato"], ' +
                        'div[class*="transparencia"], div[class*="lista"], div[class*="resultado"]'
                    );
                    divs.forEach(div => {
                        const items = div.querySelectorAll('div, li, p');
                        items.forEach(item => {
                            const text = item.textContent.trim();
                            if (text.length > 30) {
                                results.push(text);
                            }
                        });
                    });
                }

                return results;
            """)

            if not bids_js:
                _logger.debug("[%s] Level 2: no content found via Selenium", municipio)
                return []

            bids = self._parse_selenium_results(bids_js, municipio, url)
            _logger.info(
                "[%s] Level 2 SUCCESS via Selenium (%d bids)",
                municipio,
                len(bids),
            )
            return bids

        except Exception as e:
            _logger.warning("[%s] Level 2: Selenium error: %s", municipio, e)
            return []
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

    def _parse_selenium_results(self, results: list[str], municipio: str, url: str) -> list[dict]:
        """Parse Selenium extraction results into bid records.

        Args:
            results: List of text strings from JS extraction.
            municipio: Municipality name.
            url: Portal URL.

        Returns:
            List of bid dicts.
        """
        bids: list[dict] = []
        seen_hashes: set[str] = set()

        for text in results[:100]:
            if not text or len(text) < 20:
                continue

            data_match = re.search(r"(\d{2})[/-](\d{2})[/-](\d{4})", text)
            data_publicacao = ""
            if data_match:
                data_publicacao = f"{data_match.group(3)}-{data_match.group(2)}-{data_match.group(1)}"

            # Try to split by pipe (from table extraction)
            parts = [p.strip() for p in text.split("|") if p.strip()]
            modalidade = ""
            objeto = text[:500]
            valor = ""

            if len(parts) >= 3:
                data_idx = -1
                for i, p in enumerate(parts):
                    if re.search(r"\d{2}[/-]\d{2}[/-]\d{4}", p):
                        data_idx = i
                        break

                if data_idx >= 0:
                    modalidade = parts[data_idx - 1] if data_idx > 0 else ""
                    if data_idx + 1 < len(parts):
                        objeto = parts[data_idx + 1]
                    if data_idx + 2 < len(parts):
                        valor = parts[data_idx + 2]
                else:
                    modalidade = parts[0]
                    objeto = parts[-1]

            content_key = f"{modalidade}|{objeto}|{data_publicacao}|{valor}"
            content_hash = hashlib.md5(content_key.encode(), usedforsecurity=False).hexdigest()

            if content_hash in seen_hashes:
                continue
            seen_hashes.add(content_hash)

            # Extract link if present
            link = ""
            url_match = re.search(r"https?://[^\s|]+", text)
            if url_match:
                link = url_match.group(0)

            bids.append({
                "slug": _slugify(municipio),
                "municipio": municipio,
                "modalidade": modalidade,
                "data_publicacao": data_publicacao,
                "objeto": objeto,
                "valor": valor,
                "link": link,
                "portal_url": url,
                "content_hash": content_hash,
                "_source_subtype": "selenium",
            })

        return bids

    # ------------------------------------------------------------------
    # Pipeline completo por municipio
    # ------------------------------------------------------------------

    def scrape_municipio(self, entry: dict) -> dict:
        """Pipeline completo para um municipio residual.

        Args:
            entry: Dict com chaves ``municipio``, ``slug``, ``ibge``, ``url``.

        Returns:
            Dict com resultados do scraping.
        """
        municipio = entry.get("municipio", entry.get("slug", "unknown"))
        url = entry.get("url", "")
        slug = entry.get("slug", _slugify(municipio))
        ibge = entry.get("ibge", "")

        start_time = time.time()

        result: dict[str, Any] = {
            "municipio": municipio,
            "slug": slug,
            "ibge": ibge,
            "portal_url": url,
            "bids": [],
            "method": None,
            "error": None,
            "status": "unknown",
            "duration_seconds": 0,
            "scraped_at": datetime.now().isoformat(),
        }

        if not url:
            result["status"] = "inviavel"
            result["error"] = "no_url"
            result["method"] = "none"
            return result

        # Level 1: Template generico HTTP
        bids = self.try_generic_templates(url, municipio)
        if bids:
            result["bids"] = bids
            result["method"] = "generic_http"
            result["status"] = "ok"
            result["duration_seconds"] = round(time.time() - start_time, 1)
            return result

        # Level 2: Fallback Selenium
        bids = self.try_selenium_fallback(url, municipio)
        if bids:
            result["bids"] = bids
            result["method"] = "selenium_fallback"
            result["status"] = "ok"
            result["duration_seconds"] = round(time.time() - start_time, 1)
            return result

        # Falhou — marcar como inviavel
        result["status"] = "inviavel"
        result["error"] = "unreachable_or_no_content"
        result["method"] = "failed"
        result["duration_seconds"] = round(time.time() - start_time, 1)
        return result

    # ------------------------------------------------------------------
    # Batch processing
    # ------------------------------------------------------------------

    def scrape_all(self, entries: list[dict], resume: bool = False) -> list[dict]:
        """Processa todos os municipios residuais.

        Args:
            entries: Lista de dicts de municipios residuais.
            resume: Se True, carrega checkpoint e pula ja processados.

        Returns:
            Lista de resultados.
        """
        # Carregar checkpoint se retomando
        progress = self._load_progress() if resume else {}
        processed_slugs: set[str] = set(progress.get("processed", []))

        results: list[dict] = list(progress.get("results", []))
        inviaveis: list[dict] = list(progress.get("inviaveis", []))
        batch_count = 0
        total_bids = 0
        new_entities = 0

        total = len(entries)
        _logger.info("Processing %d residual municipalities (resume=%s, already_done=%d)", total, resume, len(processed_slugs))

        for i, entry in enumerate(entries):
            slug = entry.get("slug", _slugify(entry.get("municipio", "")))

            if resume and slug in processed_slugs:
                _logger.debug("[%d/%d] Skipping %s (already processed)", i + 1, total, slug)
                continue

            _logger.info("[%d/%d] Processing %s (%s)...", i + 1, total, entry.get("municipio", slug), entry.get("url", "no URL"))

            result = self.scrape_municipio(entry)
            results.append(result)
            processed_slugs.add(slug)

            if result["status"] == "ok":
                total_bids += len(result["bids"])
                new_entities += 1
                _logger.info("  -> OK: %d bids (method=%s)", len(result["bids"]), result["method"])
            else:
                inviaveis.append({
                    "municipio": entry.get("municipio", slug),
                    "slug": slug,
                    "ibge": entry.get("ibge", ""),
                    "url": entry.get("url", ""),
                    "motivo": result.get("error", "unknown"),
                    "method": result.get("method", "failed"),
                    "duration_seconds": result.get("duration_seconds", 0),
                })
                _logger.info("  -> INVIABLE: %s", result.get("error", "unknown"))

            batch_count += 1

            # Salvar checkpoint a cada batch
            if batch_count >= RESIDUAL_BATCH_SIZE:
                self._save_progress(processed_slugs, results, inviaveis, total_bids)
                batch_count = 0

        # Salvar checkpoint final
        self._save_progress(processed_slugs, results, inviaveis, total_bids)

        _logger.info(
            "Scraping complete: %d total, %d ok (%d bids), %d inviaveis",
            len(results),
            new_entities,
            total_bids,
            len(inviaveis),
        )

        return results

    # ------------------------------------------------------------------
    # Checkpoint / Progress
    # ------------------------------------------------------------------

    def _load_progress(self) -> dict:
        """Load progress checkpoint from JSON file.

        Returns:
            Dict with ``processed``, ``results``, ``inviaveis``, ``total_bids``.
        """
        path = Path(RESIDUAL_PROGRESS_FILE)
        if path.exists():
            try:
                with open(path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                _logger.warning("Failed to load progress from %s: %s", path, e)
        return {"processed": [], "results": [], "inviaveis": [], "total_bids": 0}

    def _save_progress(
        self,
        processed_slugs: set[str],
        results: list[dict],
        inviaveis: list[dict],
        total_bids: int,
    ) -> str:
        """Save progress checkpoint to JSON file.

        Args:
            processed_slugs: Set of already-processed slugs.
            results: List of scraping results.
            inviaveis: List of inviable municipality dicts.
            total_bids: Total bids extracted so far.

        Returns:
            Path to saved file.
        """
        path = Path(RESIDUAL_PROGRESS_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)

        progress = {
            "processed": sorted(processed_slugs),
            "results": results,
            "inviaveis": inviaveis,
            "total_bids": total_bids,
            "updated_at": datetime.now().isoformat(),
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(progress, f, ensure_ascii=False, indent=2)

        _logger.info("Progress saved to %s (%d processed, %d inviaveis)", path, len(processed_slugs), len(inviaveis))
        return str(path)


# ---------------------------------------------------------------------------
# Residual list loading
# ---------------------------------------------------------------------------


def load_residual_list(filepath: str | None = None) -> list[dict]:
    """Load residual municipality list from CSV.

    CSV columns:
        municipio, slug, ibge, url, entities_count

    Args:
        filepath: Path to CSV file (default: RESIDUAL_PORTALS_FILE).

    Returns:
        List of dicts sorted by entities_count descending.
    """
    path = Path(filepath or RESIDUAL_PORTALS_FILE)
    if not path.exists():
        _logger.warning("Residual list not found at %s", path)
        return []

    entries: list[dict] = []
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            municipio = row.get("municipio", "").strip()
            slug = row.get("slug", _slugify(municipio))
            ibge = row.get("ibge", "").strip()
            url = row.get("url", "").strip()
            entities_count = int(row.get("entities_count", "0") or "0")

            if municipio:
                entries.append({
                    "municipio": municipio,
                    "slug": slug,
                    "ibge": ibge,
                    "url": url,
                    "entities_count": entities_count,
                })

    # Sort by entities_count descending (higher priority first)
    entries.sort(key=lambda e: e["entities_count"], reverse=True)
    return entries


# ---------------------------------------------------------------------------
# Crawler interface (called by monitor.py)
# ---------------------------------------------------------------------------


def crawl(mode: str = "full") -> list[dict]:
    """Crawl residual transparency portals.

    Args:
        mode:
            ``"full"`` — process all residual municipalities.
            ``"incremental"`` — resume from checkpoint (skip processed).
            ``"dry-run"`` — list municipalities that would be processed.

    Returns:
        List of scraping result dicts (see ``scrape_municipio`` for schema).
    """
    entries = load_residual_list()
    if not entries:
        _logger.warning("No residual entries to process")
        return []

    if mode == "dry-run":
        _logger.info("DRY RUN: %d residual municipalities would be processed", len(entries))
        for e in entries:
            _logger.info("  %s (%s) — %s — %d entities", e.get("municipio"), e.get("slug"), e.get("url"), e.get("entities_count", 0))
        return []

    scraper = ResidualPortalScraper()
    resume = mode == "incremental"
    results = scraper.scrape_all(entries, resume=resume)

    # Save results
    output_path = Path(RESIDUAL_OUTPUT_DIR) / "scrape_residual_results.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ok_count = sum(1 for r in results if r["status"] == "ok")
    inviavel_count = sum(1 for r in results if r["status"] == "inviavel")
    total_bids = sum(len(r.get("bids", [])) for r in results)

    output = {
        "results": results,
        "metadata": {
            "version": 1,
            "total": len(results),
            "ok": ok_count,
            "inviaveis": inviavel_count,
            "total_bids": total_bids,
            "mode": mode,
            "scraped_at": datetime.now().isoformat(),
        },
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    _logger.info(
        "Crawl complete: %d total, %d ok (%d bids), %d inviaveis. Saved to %s",
        len(results), ok_count, total_bids, inviavel_count, output_path,
    )

    return results


def transform(records: list[dict]) -> list[dict]:
    """Normalize raw scrape results to pncp_raw_bids schema.

    Args:
        records: Raw scrape result dicts from ``crawl()``.

    Returns:
        List of normalized dicts ready for upsert with ``source='transparencia_residual'``.
    """
    normalized: list[dict] = []
    seen_hashes: set[str] = set()

    for record in records:
        if record.get("status") != "ok":
            continue

        bids = record.get("bids", [])
        municipio = record.get("municipio", "")
        slug = record.get("slug", "")
        ibge = record.get("ibge", "")
        method = record.get("method", "generic_http")

        for bid in bids:
            content_hash = bid.get("content_hash", "")
            if content_hash and content_hash in seen_hashes:
                continue
            if content_hash:
                seen_hashes.add(content_hash)

            # Parse valor
            valor_str = bid.get("valor", "")
            valor = None
            if valor_str:
                cleaned = re.sub(r"[R$\s]", "", valor_str)
                cleaned = cleaned.replace(".", "").replace(",", ".")
                try:
                    valor = float(cleaned)
                except ValueError:
                    valor = None

            # Parse date to ISO
            data_publicacao = bid.get("data_publicacao", "")
            if data_publicacao:
                m = re.search(r"(\d{4})-(\d{2})-(\d{2})", str(data_publicacao))
                if not m:
                    m = re.search(r"(\d{2})/(\d{2})/(\d{4})", str(data_publicacao))
                    if m:
                        data_publicacao = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
                    else:
                        data_publicacao = ""

            normalized.append({
                "pncp_id": content_hash or hashlib.md5(str(datetime.now().timestamp()).encode(), usedforsecurity=False).hexdigest(),
                "objeto_compra": bid.get("objeto", ""),
                "valor_total_estimado": valor,
                "modalidade_nome": bid.get("modalidade", ""),
                "uf": "SC",
                "municipio": municipio,
                "codigo_municipio_ibge": ibge,
                "orgao_razao_social": bid.get("orgao", ""),
                "data_publicacao": data_publicacao or None,
                "link_pncp": bid.get("link", ""),
                "content_hash": content_hash,
                "source": "transparencia_residual",
                "source_subtype": bid.get("_source_subtype", method),
                "source_id": f"transparencia_residual_{slug}",
                "method": method,
            })

    _logger.info("transform: %d records -> %d normalized", len(records), len(normalized))
    return normalized


# ---------------------------------------------------------------------------
# Geracao do CSV de municipios residuais
# ---------------------------------------------------------------------------


def generate_residual_csv(output_path: str | None = None) -> str:
    """Generate residual_portals.csv from platform detection results.

    Le os resultados do detect_platform (pass2) e compila lista de
    municipios residuais com dados do banco (contagem de entidades).

    Args:
        output_path: Caminho para salvar o CSV (default: RESIDUAL_PORTALS_FILE).

    Returns:
        Caminho do arquivo gerado.
    """
    import csv

    path = Path(output_path or RESIDUAL_PORTALS_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Load pass2 results
    pass2_path = _PROJECT_ROOT / "data" / "platform_detection_results_pass2.json"
    if not pass2_path.exists():
        _logger.warning("Platform detection results not found at %s", pass2_path)
        return ""

    with open(pass2_path, encoding="utf-8") as f:
        not_found_list = json.load(f)

    # Get entity counts per municipio from database
    entity_counts: dict[str, int] = {}
    try:
        import psycopg2

        from config.settings import DEFAULT_DSN

        conn = psycopg2.connect(DEFAULT_DSN)
        cur = conn.cursor()
        cur.execute("""
            SELECT LOWER(TRIM(municipio)), COUNT(*) as cnt
            FROM sc_public_entities
            WHERE municipio IS NOT NULL AND municipio != ''
            GROUP BY LOWER(TRIM(municipio))
        """)
        for row in cur.fetchall():
            entity_counts[row[0]] = row[1]
        cur.close()
        conn.close()
    except Exception as e:
        _logger.warning("Could not load entity counts from DB: %s", e)

    rows: list[dict] = []
    for entry in not_found_list:
        if entry.get("status") != "not_found":
            continue

        municipio = entry.get("municipio", "")
        slug = entry.get("slug", _slugify(municipio))
        ibge = entry.get("ibge", "")
        muni_lower = municipio.lower().strip()
        entities_count = entity_counts.get(muni_lower, 0)

        # Try to find a URL from pass2 patterns
        url = ""
        patterns = entry.get("pass2_patterns_tried", [])
        # Use the first sc_gov_main pattern as candidate (most likely portal URL)
        for p in patterns:
            if p.get("pattern") in ("sc_gov_main", "sc_gov_www"):
                url = p.get("url", "")
                break
        if not url and patterns:
            url = patterns[0].get("url", "")

        rows.append({
            "municipio": municipio,
            "slug": slug,
            "ibge": ibge,
            "url": url,
            "entities_count": entities_count,
        })

    # Sort by entities_count descending
    rows.sort(key=lambda r: r["entities_count"], reverse=True)

    # Write CSV
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["municipio", "slug", "ibge", "url", "entities_count"])
        writer.writeheader()
        writer.writerows(rows)

    _logger.info("Generated residual CSV at %s (%d entries)", path, len(rows))
    return str(path)


# ---------------------------------------------------------------------------
# Entity matching
# ---------------------------------------------------------------------------


def match_entities(conn: Any, source: str, entities: list[dict]) -> dict:
    """Run entity matching for transparencia_residual bids.

    Reuses monitor.py's cascade matching logic.

    Args:
        conn: Database connection.
        source: Data source name.
        entities: List of entity dicts.

    Returns:
        Stats dict with match counts.
    """
    # Import and reuse monitor's cascade matcher
    try:
        from scripts.crawl.monitor import _match_entities_cascade

        stats = _match_entities_cascade(conn, source, entities)
        _logger.info(
            "Entity matching for %s: %d matched (%d CNPJ, %d name, %d fuzzy), %d unmatched",
            source,
            stats.get("cnpj", 0) + stats.get("name_normalized", 0) + stats.get("fuzzy", 0),
            stats.get("cnpj", 0),
            stats.get("name_normalized", 0),
            stats.get("fuzzy", 0),
            stats.get("unmatched", 0),
        )
        return stats
    except ImportError as e:
        _logger.error("Could not import monitor._match_entities_cascade: %s", e)
        return {"cnpj": 0, "name_normalized": 0, "fuzzy": 0, "unmatched": 0, "total": 0}
    except Exception as e:
        _logger.error("Entity matching failed: %s", e)
        return {"cnpj": 0, "name_normalized": 0, "fuzzy": 0, "unmatched": 0, "total": 0}


# ---------------------------------------------------------------------------
# Coverage count query
# ---------------------------------------------------------------------------


def count_new_covered_entities(conn: Any, source: str = "transparencia_residual") -> int:
    """Count distinct entities covered by a source.

    Args:
        conn: Database connection.
        source: Data source name (default: transparencia_residual).

    Returns:
        Count of distinct entity IDs with is_covered = TRUE for this source.
    """
    cur = conn.cursor()
    cur.execute(
        """SELECT COUNT(DISTINCT entity_id)
           FROM entity_coverage
           WHERE source = %s AND is_covered = TRUE""",
        (source,),
    )
    count = cur.fetchone()[0]
    cur.close()
    return count


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    import argparse

    parser = argparse.ArgumentParser(
        description="Residual Portal Scraper — scraping individual para portais de transparencia residuais"
    )
    parser.add_argument(
        "--mode",
        choices=["full", "incremental", "dry-run"],
        default="full",
        help="Modo de execucao (default: full)",
    )
    parser.add_argument(
        "--municipio",
        default=None,
        help="Processar um unico municipio (slug)",
    )
    parser.add_argument(
        "--generate-csv",
        action="store_true",
        help="Apenas gerar CSV de municipios residuais e sair",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Retomar do checkpoint (pular ja processados)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Log em nivel DEBUG",
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.generate_csv:
        path = generate_residual_csv()
        if path:
            print(f"CSV generated: {path}")
        else:
            print("Failed to generate CSV")
            sys.exit(1)
        sys.exit(0)

    if args.municipio:
        # Single municipio mode
        entries = load_residual_list()
        entry = None
        for e in entries:
            if e.get("slug") == args.municipio:
                entry = e
                break
            if e.get("municipio", "").lower().replace(" ", "-") == args.municipio:
                entry = e
                break

        if not entry:
            print(f"Municipio '{args.municipio}' not found in residual list")
            sys.exit(1)

        scraper = ResidualPortalScraper()
        result = scraper.scrape_municipio(entry)

        print(f"\nResult for {entry['municipio']}:")
        print(f"  Status: {result['status']}")
        print(f"  Method: {result.get('method', 'N/A')}")
        print(f"  Bids: {len(result.get('bids', []))}")
        print(f"  Duration: {result.get('duration_seconds', 0)}s")
        if result.get("bids"):
            print("\n  Sample bids:")
            for bid in result["bids"][:3]:
                print(f"    - {bid.get('modalidade', '')} | {bid.get('objeto', '')[:80]}")
        if result.get("error"):
            print(f"  Error: {result['error']}")
        sys.exit(0)

    # Full/incremental mode
    results = crawl(mode=args.mode)

    if results:
        ok_count = sum(1 for r in results if r["status"] == "ok")
        inviavel_count = sum(1 for r in results if r["status"] == "inviavel")
        total_bids = sum(len(r.get("bids", [])) for r in results)
        total_duration = sum(r.get("duration_seconds", 0) for r in results)

        print("\nResidual scraping complete:")
        print(f"  Total:     {len(results)}")
        print(f"  OK:        {ok_count}")
        print(f"  Inviaveis: {inviavel_count}")
        print(f"  Total bids: {total_bids}")
        print(f"  Total time: {total_duration:.0f}s ({total_duration / 60:.1f} min)")

        # Log de efetividade
        print(f"\n{'=' * 72}")
        print("  EFETIVIDADE — Residual Scraping")
        print(f"{'=' * 72}")
        print(f"  {'Municipio':35s} | {'Status':>10s} | {'Metodo':>16s} | {'Bids':>5s} | {'Tempo':>5s}")
        print(f"  {'-' * 35} | {'-' * 10} | {'-' * 16} | {'-' * 5} | {'-' * 5}")
        for r in results[:50]:  # show top 50
            status = r.get("status", "?")
            method = r.get("method", "?")[:16]
            bids = len(r.get("bids", []))
            dur = r.get("duration_seconds", 0)
            print(f"  {r['municipio']:35s} | {status:>10s} | {method:>16s} | {bids:>5d} | {dur:>5.0f}s")
        if len(results) > 50:
            print(f"  ... and {len(results) - 50} more")
        print(f"{'=' * 72}")
    else:
        print("No results. Check data/residual_portals.csv for residual municipalities.")
        sys.exit(1)

"""SeleniumCrawler — Base class for JavaScript-rendered portal crawling.

Provides a headless browser automation layer for transparency portals
that require JavaScript rendering (SPAs, React, Angular, Vue).

Usage:
    crawler = SeleniumCrawler()
    html = crawler.render_page("https://example.com")
    records = crawler.scrape("slug", "https://example.com", selectors, template_module)
    crawler.close()

Design:
    - Chrome headless primary, Firefox fallback
    - Anti-bot measures: UA rotation, viewport randomisation, webdriver masking
    - Configurable timeouts, retries, rate limiting
    - Graceful degradation: HTTP fallback if Selenium is unavailable
    - Output format matches transparencia_crawler transformer expectations
"""

from __future__ import annotations

import logging
import os
import random
import time
from datetime import datetime
from typing import Any

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (env vars with SELENIUM_ prefix)
# ---------------------------------------------------------------------------

SELENIUM_HEADLESS = os.getenv("SELENIUM_HEADLESS", "true").lower() in ("true", "1", "yes")
"""Run browser in headless mode (default: true)."""

SELENIUM_TIMEOUT = int(os.getenv("SELENIUM_TIMEOUT", "30"))
"""Timeout in seconds for page render (default: 30)."""

SELENIUM_REQUEST_DELAY = float(os.getenv("SELENIUM_REQUEST_DELAY", "5.0"))
"""Minimum delay in seconds between Selenium requests to the same domain (default: 5.0)."""

SELENIUM_BROWSER = os.getenv("SELENIUM_BROWSER", "chrome")
"""Preferred browser: 'chrome' (default) or 'firefox'."""

SELENIUM_IMPLICIT_WAIT = int(os.getenv("SELENIUM_IMPLICIT_WAIT", "10"))
"""Implicit wait in seconds for element detection (default: 10)."""

SELENIUM_PAGE_LOAD_TIMEOUT = int(os.getenv("SELENIUM_PAGE_LOAD_TIMEOUT", "30"))
"""Page load timeout in seconds (default: 30)."""

SELENIUM_UA_FILE = os.getenv("SELENIUM_UA_FILE", "")
"""Optional path to a JSON file with a list of User-Agent strings for rotation."""

# Default User-Agent rotation pool
_DEFAULT_USER_AGENTS = [
    # Chrome 125 on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    # Chrome 125 on macOS
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    # Firefox 127 on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    # Edge 125 on Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
    # Chrome 125 on Linux
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]

# Viewport sizes for randomisation (common real-user resolutions)
_VIEWPORT_SIZES = [
    (1366, 768),
    (1920, 1080),
    (1536, 864),
    (1440, 900),
    (1280, 720),
    (1600, 900),
]


class SeleniumCrawlerError(Exception):
    """Base exception for SeleniumCrawler errors."""


class SeleniumUnavailableError(SeleniumCrawlerError):
    """Raised when neither Chrome nor Firefox WebDriver can be initialised."""


class PageTimeoutError(SeleniumCrawlerError):
    """Raised when a page takes longer than SELENIUM_TIMEOUT to render."""


# ---------------------------------------------------------------------------
# SeleniumCrawler
# ---------------------------------------------------------------------------


class SeleniumCrawler:
    """Base class for Selenium-based crawling of JavaScript-rendered portals.

    Attributes:
        browser: Preferred browser name ('chrome' or 'firefox').
        headless: Whether to run browser in headless mode.
        timeout: Page render timeout in seconds.
        request_delay: Minimum delay between requests to the same domain.
        driver: The active WebDriver instance (None if not yet initialised).
        _last_request: Timestamp of the last request (for rate limiting).
    """

    def __init__(
        self,
        *,
        browser: str | None = None,
        headless: bool | None = None,
        timeout: int | None = None,
        request_delay: float | None = None,
        user_agents: list[str] | None = None,
    ) -> None:
        """Initialise the SeleniumCrawler with configurable settings.

        Args:
            browser: Browser to use ('chrome' or 'firefox').
                Defaults to SELENIUM_BROWSER env var or 'chrome'.
            headless: Whether to run headless.
                Defaults to SELENIUM_HEADLESS env var or True.
            timeout: Page render timeout in seconds.
                Defaults to SELENIUM_TIMEOUT env var or 30.
            request_delay: Minimum delay between requests.
                Defaults to SELENIUM_REQUEST_DELAY env var or 5.0.
            user_agents: List of User-Agent strings to rotate through.
                Defaults to built-in pool of 5 modern UAs.
        """
        self.browser = browser or SELENIUM_BROWSER
        self.headless = headless if headless is not None else SELENIUM_HEADLESS
        self.timeout = timeout or SELENIUM_TIMEOUT
        self.request_delay = request_delay or SELENIUM_REQUEST_DELAY
        self._user_agents = user_agents or list(_DEFAULT_USER_AGENTS)
        self._ua_index = random.randint(0, len(self._user_agents) - 1)  # noqa: S311  # Non-cryptographic, UA rotation for anti-bot

        self.driver: Any = None
        self._last_request: float = 0.0
        self._driver_initialised = False

        _logger.info(
            "SeleniumCrawler initialised: browser=%s headless=%s timeout=%ds delay=%.1fs",
            self.browser,
            self.headless,
            self.timeout,
            self.request_delay,
        )

    # ------------------------------------------------------------------
    # User-Agent rotation
    # ------------------------------------------------------------------

    def _next_user_agent(self) -> str:
        """Return the next User-Agent string (round-robin rotation)."""
        ua = self._user_agents[self._ua_index % len(self._user_agents)]
        self._ua_index += 1
        return ua

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------

    def _apply_rate_limit(self) -> None:
        """Wait if needed to respect SELENIUM_REQUEST_DELAY between requests."""
        if self._last_request == 0:
            self._last_request = time.time()
            return

        elapsed = time.time() - self._last_request
        if elapsed < self.request_delay:
            wait = self.request_delay - elapsed
            _logger.debug("Rate limit: waiting %.2fs before next request", wait)
            time.sleep(wait)

        self._last_request = time.time()

    # ------------------------------------------------------------------
    # Driver setup
    # ------------------------------------------------------------------

    def _setup_driver(self) -> Any:
        """Initialise a Chrome WebDriver with anti-bot options.

        Configures:
            - Headless mode (configurable)
            - Randomised viewport
            - Custom User-Agent rotation
            - Disabled automation-controlled flag
            - Disabled GPU (headless optimisation)
            - Sandbox disabled (WSL/Docker compatibility)

        Returns:
            selenium webdriver Chrome instance.

        Raises:
            SeleniumUnavailableError: If ChromeDriver cannot be initialised.
        """
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options as ChromeOptions
        except ImportError as e:
            raise SeleniumUnavailableError(
                "Selenium package not installed. Install with: pip install selenium>=4.15.0"
            ) from e

        options = ChromeOptions()

        # Headless mode
        if self.headless:
            options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")

        # Anti-bot: mask webdriver presence
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        # Compatibility
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-setuid-sandbox")

        # Performance
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-background-networking")
        options.add_argument("--disable-sync")

        # User-Agent
        ua = self._next_user_agent()
        options.add_argument(f"--user-agent={ua}")

        # Language / locale
        options.add_argument("--lang=pt-BR")
        options.add_argument("--accept-lang=pt-BR,pt;q=0.9,en;q=0.8")

        try:
            driver = webdriver.Chrome(options=options)
            # Mask navigator.webdriver via CDP
            driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {
                    "source": """
                        Object.defineProperty(navigator, 'webdriver', {
                            get: () => undefined
                        });
                    """
                },
            )
            # Randomise viewport
            width, height = random.choice(_VIEWPORT_SIZES)  # noqa: S311  # Non-cryptographic, viewport randomisation for anti-bot
            driver.set_window_size(width, height)
            driver.implicitly_wait(SELENIUM_IMPLICIT_WAIT)
            driver.set_page_load_timeout(SELENIUM_PAGE_LOAD_TIMEOUT)

            _logger.info("Chrome WebDriver initialised (viewport: %dx%d, UA: %s...)", width, height, ua[:50])
            return driver
        except Exception as e:
            raise SeleniumUnavailableError(
                f"Failed to initialise Chrome WebDriver: {e}. "
                "Ensure chromedriver is installed: pip install webdriver-manager"
            ) from e

    def _setup_driver_fallback(self) -> Any:
        """Fallback: initialise a Firefox/GeckoDriver WebDriver.

        Tried when Chrome initialisation fails.

        Returns:
            selenium webdriver Firefox instance.

        Raises:
            SeleniumUnavailableError: If Firefox also cannot be initialised.
        """
        try:
            from selenium import webdriver
            from selenium.webdriver.firefox.options import Options as FirefoxOptions
        except ImportError as e:
            raise SeleniumUnavailableError(
                "Selenium package not installed. Install with: pip install selenium>=4.15.0"
            ) from e

        options = FirefoxOptions()
        if self.headless:
            options.add_argument("--headless")

        ua = self._next_user_agent()
        options.set_preference("general.useragent.override", ua)
        options.set_preference("intl.accept_languages", "pt-BR,pt")
        options.set_preference("dom.webdriver.enabled", False)
        options.set_preference("useAutomationExtension", False)

        try:
            driver = webdriver.Firefox(options=options)
            width, height = random.choice(_VIEWPORT_SIZES)  # noqa: S311  # Non-cryptographic, viewport randomisation for anti-bot
            driver.set_window_size(width, height)
            driver.implicitly_wait(SELENIUM_IMPLICIT_WAIT)
            driver.set_page_load_timeout(SELENIUM_PAGE_LOAD_TIMEOUT)

            _logger.info("Firefox WebDriver initialised (viewport: %dx%d)", width, height)
            return driver
        except Exception as e:
            raise SeleniumUnavailableError(
                f"Failed to initialise Firefox WebDriver: {e}. Ensure geckodriver is installed."
            ) from e

    def _ensure_driver(self) -> Any:
        """Ensure a driver instance is available, initialising if needed.

        Tries Chrome first, then Firefox fallback.

        Returns:
            Active WebDriver instance.
        """
        if self.driver is not None:
            return self.driver

        if self.browser == "firefox":
            # Try Firefox first if explicitly requested
            try:
                self.driver = self._setup_driver_fallback()
            except SeleniumUnavailableError:
                _logger.warning("Firefox not available, trying Chrome fallback")
                self.driver = self._setup_driver()
        else:
            # Chrome first (default), Firefox fallback
            try:
                self.driver = self._setup_driver()
            except SeleniumUnavailableError:
                _logger.warning("Chrome not available, trying Firefox fallback")
                self.driver = self._setup_driver_fallback()

        self._driver_initialised = True
        return self.driver

    # ------------------------------------------------------------------
    # Page rendering
    # ------------------------------------------------------------------

    def render_page(self, url: str, wait_for: str | None = None) -> str:
        """Navigate to a URL, wait for JS rendering, return the rendered HTML.

        Args:
            url: Full URL to navigate to.
            wait_for: Optional CSS selector to wait for (confirms JS render).

        Returns:
            Rendered page HTML as a string.

        Raises:
            SeleniumUnavailableError: If no browser driver can be initialised.
            PageTimeoutError: If the page takes longer than timeout to render.
        """
        self._apply_rate_limit()
        driver = self._ensure_driver()

        _logger.info("Rendering page: %s (wait_for=%s)", url, wait_for)

        try:
            driver.get(url)
        except Exception as e:
            _logger.warning("Page load error for %s: %s", url, e)
            raise PageTimeoutError(f"Page load failed for {url}: {e}") from e

        # Wait for a specific selector (confirms JS render)
        if wait_for:
            try:
                from selenium.webdriver.common.by import By
                from selenium.webdriver.support import expected_conditions as ec
                from selenium.webdriver.support.ui import WebDriverWait

                WebDriverWait(driver, self.timeout).until(ec.presence_of_element_located((By.CSS_SELECTOR, wait_for)))
                _logger.debug("Wait condition met: '%s' on %s", wait_for, url)
            except Exception as e:
                _logger.warning(
                    "Wait for selector '%s' timed out on %s: %s. Returning current DOM state.",
                    wait_for,
                    url,
                    e,
                )

        # Allow any remaining async rendering
        time.sleep(0.5)

        try:
            html = driver.page_source
            _logger.debug("Rendered page for %s: %d chars", url, len(html))
            return html
        except Exception as e:
            _logger.error("Failed to get page source from %s: %s", url, e)
            raise PageTimeoutError(f"Failed to get page source: {e}") from e

    def render_page_with_retry(
        self,
        url: str,
        wait_for: str | None = None,
        max_retries: int = 2,
    ) -> str:
        """Render a page with retry logic.

        Args:
            url: Full URL to navigate to.
            wait_for: Optional CSS selector to wait for.
            max_retries: Maximum number of retry attempts (default: 2).

        Returns:
            Rendered HTML as a string.

        Raises:
            PageTimeoutError: If all retries fail.
        """
        last_error: Exception | None = None

        for attempt in range(max_retries + 1):
            try:
                return self.render_page(url, wait_for=wait_for)
            except (SeleniumUnavailableError, PageTimeoutError) as e:
                last_error = e
                if attempt < max_retries:
                    backoff = (attempt + 1) * 2.0
                    _logger.warning(
                        "Render attempt %d/%d failed for %s: %s. Retrying in %.1fs...",
                        attempt + 1,
                        max_retries + 1,
                        url,
                        e,
                        backoff,
                    )
                    time.sleep(backoff)
                    # Recreate driver if it died
                    self.close()
                    self.driver = None
                    self._driver_initialised = False

        raise PageTimeoutError(f"Failed to render {url} after {max_retries + 1} attempts: {last_error}")

    # ------------------------------------------------------------------
    # Scrape (render + delegate to template)
    # ------------------------------------------------------------------

    def scrape(
        self,
        slug: str,
        portal_url: str,
        selectors: dict | None = None,
        template_module: Any = None,
        *,
        municipio_nome: str = "",
        ibge: str = "",
        wait_for: str | None = None,
        fallback_to_http: bool = True,
    ) -> dict:
        """Render a portal page and delegate parsing to a template module.

        Combines Selenium rendering with existing BS4-based template parsing.

        Args:
            slug: Municipality slug.
            portal_url: Full portal URL.
            selectors: Dict of CSS selectors (required if no template_module).
            template_module: An existing template module with ``parse_page(soup, url, slug, ibge)``.
            municipio_nome: Original municipality name.
            ibge: IBGE code.
            wait_for: CSS selector to wait for JS rendering.
            fallback_to_http: If True, fall back to HTTP fetch when Selenium fails.

        Returns:
            Dict with keys matching scrape_municipio() output:
                municipio, slug, ibge, portal_url, status, records, count,
                error, scraped_at, method.
        """
        result: dict[str, Any] = {
            "municipio": municipio_nome or slug,
            "slug": slug,
            "ibge": ibge,
            "portal_url": portal_url,
            "status": "unknown",
            "records": [],
            "count": 0,
            "error": None,
            "scraped_at": datetime.now().isoformat(),
            "method": "selenium",
        }

        # Phase 1: Render page with Selenium
        try:
            html = self.render_page_with_retry(portal_url, wait_for=wait_for)
        except Exception as e:
            _logger.warning(
                "Selenium render failed for %s (%s): %s",
                municipio_nome or slug,
                portal_url,
                e,
            )
            if fallback_to_http:
                _logger.info(
                    "Falling back to HTTP for %s (%s)",
                    municipio_nome or slug,
                    portal_url,
                )
                return self._http_fallback(
                    slug=slug,
                    portal_url=portal_url,
                    selectors=selectors,
                    template_module=template_module,
                    municipio_nome=municipio_nome,
                    ibge=ibge,
                    original_error=str(e),
                )
            result["status"] = "unreachable"
            result["error"] = f"Selenium render failed: {e}"
            result["method"] = "selenium_error"
            return result

        # Phase 2: Parse rendered HTML with BeautifulSoup
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "html.parser")
        except Exception as e:
            result["status"] = "parse_error"
            result["error"] = f"BeautifulSoup parse error: {e}"
            return result

        # Phase 3: Delegate to template module or use selectors
        records: list[dict] = []
        source_subtype = "generico"

        if template_module is not None:
            try:
                records = template_module.parse_page(soup, url=portal_url, slug=slug, ibge=ibge)
                source_subtype = getattr(template_module, "PLATFORM", "generico")
            except Exception as e:
                _logger.warning("Template parse failed for %s: %s", slug, e)
                result["status"] = "parse_error"
                result["error"] = f"Template parse failed: {e}"
                return result
        elif selectors:
            # Direct selector-based extraction (inline scraping)
            records = self._scrape_with_selectors(soup, selectors, slug, ibge, portal_url)
        else:
            result["status"] = "parse_error"
            result["error"] = "No template_module or selectors provided"
            return result

        result["status"] = "ok" if records else "no_content"
        result["records"] = records
        result["count"] = len(records)
        result["source_subtype"] = source_subtype

        _logger.info(
            "Selenium scrape: %s -> %d records (method=selenium, platform=%s)",
            municipio_nome or slug,
            len(records),
            source_subtype,
        )

        return result

    def _scrape_with_selectors(
        self,
        soup: Any,
        selectors: dict,
        slug: str,
        ibge: str,
        portal_url: str,
    ) -> list[dict]:
        """Extract records from soup using inline CSS selectors.

        Args:
            soup: BeautifulSoup parsed HTML.
            selectors: Dict with keys like lista_licitacoes, modalidade, data, etc.
            slug: Municipality slug.
            ibge: IBGE code.
            portal_url: Portal URL.

        Returns:
            List of record dicts.
        """
        from scripts.crawl.transparencia_templates.base import (
            extract_link,
            extract_text,
            make_record,
            parse_table_rows,
        )

        container_sel = selectors.get("lista_licitacoes", "")
        if not container_sel:
            return []

        # Try table-based parsing first
        try:
            records = parse_table_rows(
                soup,
                container_sel,
                url=portal_url,
                slug=slug,
                ibge=ibge,
                modalidade_sel=selectors.get("modalidade", ""),
                data_sel=selectors.get("data", ""),
                objeto_sel=selectors.get("objeto", ""),
                orgao_sel=selectors.get("orgao", ""),
                valor_sel=selectors.get("valor", ""),
                link_sel=selectors.get("link", ""),
            )
            if records:
                return records
        except Exception:
            _logger.warning("CSS selector extraction failed, falling back to container-based extraction", exc_info=True)

        # Fallback: container-based extraction
        try:
            container = soup.select_one(container_sel)
            if container is None:
                return []

            records: list[dict] = []
            seen_hashes: set[str] = set()

            for tr in container.find_all("tr"):
                if tr.name != "tr":
                    continue

                modalidade = extract_text(tr, selectors.get("modalidade", ""))
                data_txt = extract_text(tr, selectors.get("data", ""))
                objeto = extract_text(tr, selectors.get("objeto", ""))
                orgao = extract_text(tr, selectors.get("orgao", ""))
                valor = extract_text(tr, selectors.get("valor", ""))
                link = extract_link(tr, selectors.get("link", "a[href]"), portal_url)

                record = make_record(
                    slug=slug,
                    ibge=ibge,
                    portal_url=portal_url,
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
        except Exception:
            return []

    # ------------------------------------------------------------------
    # HTTP fallback
    # ------------------------------------------------------------------

    def _http_fallback(
        self,
        *,
        slug: str,
        portal_url: str,
        selectors: dict | None = None,
        template_module: Any = None,
        municipio_nome: str = "",
        ibge: str = "",
        original_error: str = "",
    ) -> dict:
        """Fall back to HTTP-based scraping when Selenium is unavailable.

        Delegates to ``transparencia_crawler.scrape_municipio()``.

        Returns:
            Dict with the same schema as scrape().
        """
        try:
            from scripts.crawl.transparencia_crawler import scrape_municipio

            resolved_selectors = selectors or {}
            result = scrape_municipio(
                slug=slug,
                portal_url=portal_url,
                selectors=resolved_selectors,
                municipio_nome=municipio_nome,
                ibge=ibge,
            )
            result["method"] = "http_fallback"
            result["selenium_error"] = original_error
            _logger.info(
                "HTTP fallback for %s: %s records (was: %s)",
                municipio_nome or slug,
                result.get("count", 0),
                original_error,
            )
            return result
        except Exception as e:
            return {
                "municipio": municipio_nome or slug,
                "slug": slug,
                "ibge": ibge,
                "portal_url": portal_url,
                "status": "error",
                "records": [],
                "count": 0,
                "error": f"Selenium: {original_error}; HTTP fallback also failed: {e}",
                "scraped_at": datetime.now().isoformat(),
                "method": "fallback_error",
            }

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the WebDriver and release browser resources."""
        if self.driver is not None:
            try:
                self.driver.quit()
                _logger.debug("WebDriver closed")
            except Exception as e:
                _logger.warning("Error closing WebDriver: %s", e)
            finally:
                self.driver = None
                self._driver_initialised = False

    def __enter__(self) -> SeleniumCrawler:
        """Context manager entry."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit — ensures cleanup."""
        self.close()


# ---------------------------------------------------------------------------
# Convenience function: render with Selenium, return BeautifulSoup
# ---------------------------------------------------------------------------


def render_to_soup(
    url: str,
    wait_for: str | None = None,
    *,
    crawler: SeleniumCrawler | None = None,
    **kwargs: Any,
) -> Any | None:
    """Convenience: render a JS page and return a BeautifulSoup object.

    Args:
        url: Full URL to render.
        wait_for: Optional CSS selector to wait for.
        crawler: Reusable SeleniumCrawler instance (created/destroyed if None).
        **kwargs: Extra args passed to SeleniumCrawler constructor.

    Returns:
        BeautifulSoup object, or None if rendering fails.
    """
    from bs4 import BeautifulSoup

    own_crawler = crawler is None
    if own_crawler:
        crawler = SeleniumCrawler(**kwargs)

    try:
        html = crawler.render_page(url, wait_for=wait_for)
        return BeautifulSoup(html, "html.parser")
    except Exception as e:
        _logger.error("render_to_soup failed for %s: %s", url, e)
        return None
    finally:
        if own_crawler:
            crawler.close()

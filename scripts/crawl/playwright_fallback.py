"""PlaywrightFallback — Fallback para Selenium usando Playwright.

Quando Selenium falha em renderizar um portal JS-rendered (timeout, CAPTCHA,
incompatibilidade de driver), esta classe tenta renderizar usando Playwright.

Playwright oferece:
- Stealth mode nativo (passa em Cloudflare/bot detection com mais frequencia)
- Chromium/Firefox/WebKit (multi-browser)
- Network interception (bloquear CSS/imagens para acelerar)
- Screenshot nativo para debug

Usage::

    from scripts.crawl.playwright_fallback import PlaywrightFallback

    fallback = PlaywrightFallback()
    html = fallback.render_page("https://...")
    fallback.close()

Design:
    - Mesma interface de ``SeleniumCrawler.render_page()``
    - Import opcional (apenas se Playwright estiver instalado)
    - Timeout configravel por porta
    - Anti-bot measures: stealth mode, viewport aleatorio, UA realista
"""
from __future__ import annotations
import logging
import os
import random
import time
from pathlib import Path
from typing import Any

_logger = logging.getLogger(__name__)

# Configuration
PLAYWRIGHT_HEADLESS = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() in ("true", "1", "yes")
PLAYWRIGHT_TIMEOUT = int(os.getenv("PLAYWRIGHT_TIMEOUT", "60"))
PLAYWRIGHT_BROWSER = os.getenv("PLAYWRIGHT_BROWSER", "chromium")

# Viewport sizes for randomisation
_VIEWPORT_SIZES = [
    (1366, 768),
    (1920, 1080),
    (1536, 864),
    (1440, 900),
    (1280, 720),
]

_DEVICE_SCALE_FACTORS = [1, 1, 1, 1, 2]

# User-Agent strings
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
]


class PlaywrightUnavailableError(Exception):
    """Raised when Playwright is not installed or browser cannot be launched."""


class PlaywrightPageError(Exception):
    """Raised when page rendering fails for any reason."""


class PlaywrightFallback:
    """Fallback browser automation using Playwright.

    Provides the same ``render_page()`` interface as ``SeleniumCrawler``
    so it can be used as a drop-in replacement.

    Attributes:
        timeout: Page load timeout in seconds.
        headless: Run browser in headless mode.
        browser_type: Browser type (``chromium``, ``firefox``, ``webkit``).
    """

    def __init__(
        self,
        timeout: int | None = None,
        headless: bool | None = None,
        browser_type: str | None = None,
    ) -> None:
        """Initialise the Playwright fallback.

        Args:
            timeout: Page timeout in seconds (default: ``PLAYWRIGHT_TIMEOUT`` env or 60).
            headless: Whether to run headless (default: ``PLAYWRIGHT_HEADLESS`` env or True).
            browser_type: Browser to use (default: ``PLAYWRIGHT_BROWSER`` env or ``chromium``).
        """
        self.timeout = (timeout or PLAYWRIGHT_TIMEOUT) * 1000  # Playwright uses ms
        self.headless = headless if headless is not None else PLAYWRIGHT_HEADLESS
        self.browser_type = browser_type or PLAYWRIGHT_BROWSER
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None

        _logger.info(
            "PlaywrightFallback initialised: browser=%s headless=%s timeout=%dms",
            self.browser_type,
            self.headless,
            self.timeout,
        )

    # ------------------------------------------------------------------
    # Browser setup
    # ------------------------------------------------------------------

    def _ensure_browser(self) -> Any:
        """Ensure Playwright browser is launched."""
        if self._browser is not None:
            return self._browser

        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            raise PlaywrightUnavailableError("Playwright not installed. Install with: pip install playwright") from e

        try:
            self._playwright = sync_playwright().start()

            browser_launcher = getattr(self._playwright, self.browser_type, None)
            if browser_launcher is None:
                _logger.warning(
                    "Browser '%s' not available, falling back to chromium",
                    self.browser_type,
                )
                browser_launcher = self._playwright.chromium

            self._browser = browser_launcher.launch(
                headless=self.headless,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-gpu",
                ],
            )

            # Create context with stealth configuration
            width, height = random.choice(_VIEWPORT_SIZES)  # noqa: S311  # Non-cryptographic, viewport randomisation for anti-bot
            device_scale = random.choice(_DEVICE_SCALE_FACTORS)  # noqa: S311  # Non-cryptographic, device scale randomisation
            user_agent = random.choice(_USER_AGENTS)  # noqa: S311  # Non-cryptographic, UA rotation for anti-bot

            self._context = self._browser.new_context(
                viewport={"width": width, "height": height},
                device_scale_factor=device_scale,
                user_agent=user_agent,
                locale="pt-BR",
                timezone_id="America/Sao_Paulo",
                # Stealth: disable webdriver flag
                permissions=["geolocation"],
                java_script_enabled=True,
                ignore_https_errors=True,
            )

            # Block unnecessary resources for speed
            self._context.route(
                "**/*.{png,jpg,jpeg,gif,svg,css,woff,woff2,ttf}",
                lambda route: route.abort(),
            )

            self._page = self._context.new_page()
            self._page.set_default_timeout(self.timeout)

            _logger.info(
                "Playwright browser launched: %s (viewport: %dx%d, scale: %d)",
                self.browser_type,
                width,
                height,
                device_scale,
            )
            return self._browser

        except Exception as e:
            raise PlaywrightUnavailableError(
                f"Failed to launch Playwright {self.browser_type}: {e}. Run: playwright install"
            ) from e

    # ------------------------------------------------------------------
    # Page rendering
    # ------------------------------------------------------------------

    def render_page(self, url: str, wait_for: str | None = None) -> str:
        """Navigate to a URL and return rendered HTML.

        Args:
            url: Full URL to navigate to.
            wait_for: Optional CSS selector to wait for (confirms JS render).

        Returns:
            Rendered page HTML as string.

        Raises:
            PlaywrightUnavailableError: If Playwright is not available.
            PlaywrightPageError: If page rendering fails.
        """
        self._ensure_browser()

        _logger.info("Playwright rendering: %s (wait_for=%s)", url, wait_for)

        try:
            response = self._page.goto(url, wait_until="networkidle", timeout=self.timeout)
            if response is None:
                _logger.warning("No response for %s", url)
        except Exception as e:
            _logger.warning("Playwright goto warning for %s: %s", url, e)
            # Page may still be partially rendered

        # Wait for specific selector
        if wait_for:
            try:
                self._page.wait_for_selector(wait_for, timeout=min(self.timeout, 30000))
                _logger.debug("Wait condition met: '%s' on %s", wait_for, url)
            except Exception as e:
                _logger.warning(
                    "Wait for '%s' timed out on %s: %s. Returning current DOM.",
                    wait_for,
                    url,
                    e,
                )

        # Extra time for async rendering
        time.sleep(1.0)

        try:
            html = self._page.content()
            _logger.debug("Playwright rendered %s: %d chars", url, len(html))
            return html
        except Exception as e:
            raise PlaywrightPageError(f"Failed to get page content from {url}: {e}") from e

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
            max_retries: Maximum retry attempts (default: 2).

        Returns:
            Rendered HTML as string.

        Raises:
            PlaywrightPageError: If all retries fail.
        """
        last_error: Exception | None = None

        for attempt in range(max_retries + 1):
            try:
                return self.render_page(url, wait_for=wait_for)
            except (PlaywrightUnavailableError, PlaywrightPageError) as e:
                last_error = e
                if attempt < max_retries:
                    backoff = (attempt + 1) * 2.0
                    _logger.warning(
                        "Render attempt %d/%d failed for %s. Retrying in %.1fs...",
                        attempt + 1,
                        max_retries + 1,
                        url,
                        backoff,
                    )
                    time.sleep(backoff)
                    self.close()
                    self._browser = None
                    self._context = None
                    self._page = None

        raise PlaywrightPageError(f"Failed to render {url} after {max_retries + 1} attempts: {last_error}")

    # ------------------------------------------------------------------
    # Screenshot (debug)
    # ------------------------------------------------------------------

    def save_screenshot(self, filepath: str) -> str | None:
        """Save a screenshot of the current page.

        Args:
            filepath: Path to save the screenshot.

        Returns:
            Path to saved screenshot, or None if failed.
        """
        if self._page is None:
            return None
        try:
            Path(filepath).parent.mkdir(parents=True, exist_ok=True)
            self._page.screenshot(path=filepath, full_page=True)
            _logger.info("Playwright screenshot saved: %s", filepath)
            return filepath
        except Exception as e:
            _logger.warning("Failed to save screenshot: %s", e)
            return None

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close browser and release resources."""
        if self._page is not None:
            try:
                self._page.close()
            except Exception:  # noqa: S110  # Best-effort cleanup in close()
                logging.getLogger(__name__).warning(
                    "swallowed exception in %s", __name__, exc_info=True
                )
            self._page = None

        if self._context is not None:
            try:
                self._context.close()
            except Exception:  # noqa: S110  # Best-effort cleanup in close()
                logging.getLogger(__name__).warning(
                    "swallowed exception in %s", __name__, exc_info=True
                )
            self._context = None

        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:  # noqa: S110  # Best-effort cleanup in close()
                logging.getLogger(__name__).warning(
                    "swallowed exception in %s", __name__, exc_info=True
                )
            self._browser = None

        if hasattr(self, "_playwright") and self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:  # noqa: S110  # Best-effort cleanup in close()
                logging.getLogger(__name__).warning(
                    "swallowed exception in %s", __name__, exc_info=True
                )

        _logger.debug("PlaywrightFallback closed")

    def __enter__(self) -> PlaywrightFallback:
        """Context manager entry."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit — ensures cleanup."""
        self.close()

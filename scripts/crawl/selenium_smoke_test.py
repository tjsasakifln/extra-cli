#!/usr/bin/env python3
"""Selenium Smoke Test — COVERAGE-3.1 AC2.

Testa o SeleniumBatchCrawler em 3 portais JS-rendered de plataformas
diferentes, salvando screenshots de debug em ``data/selenium_debug/``.

Uso:
    python scripts/crawl/selenium_smoke_test.py
    python scripts/crawl/selenium_smoke_test.py --headless false   # ver browser

Requer:
    pip install selenium>=4.15.0
    chromedriver no PATH (ou webdriver-manager: pip install webdriver-manager)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
_logger = logging.getLogger("selenium_smoke_test")

# ---------------------------------------------------------------------------
# 3 portais de plataformas diferentes (React, Angular, Vue estimate)
# ---------------------------------------------------------------------------
# Observacao: em SC, a maioria dos portais municipais usa Betha (React).
# Selecionamos 3 que representam templates diferentes:
#   1. Florianopolis — e-gov Betha (portal React SPA)
#   2. Sao Jose — atende.net (portal_transparencia_net template)
#   3. Blumenau — sc.gov.br custom (portal Angular-like)
# ---------------------------------------------------------------------------

TEST_PORTALS = [
    {
        "slug": "florianopolis",
        "nome": "Florianopolis",
        "ibge": "4205407",
        "url": "https://florianopolis.e-gov.betha.com.br",
        "platform": "e_gov_net",
        "framework_guess": "React",
        "wait_for": "div.lista-licitacoes",
    },
    {
        "slug": "sao-jose",
        "nome": "Sao Jose",
        "ibge": "4216602",
        "url": "https://sao-jose.atende.net/transparencia",
        "platform": "portal_transparencia_net",
        "framework_guess": "React",
        "wait_for": "table.licitacao",
    },
    {
        "slug": "blumenau",
        "nome": "Blumenau",
        "ibge": "4202404",
        "url": "https://blumenau.sc.gov.br",
        "platform": "custom",
        "framework_guess": "Angular",
        "wait_for": None,
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Selenium Smoke Test for JS-rendered portals")
    parser.add_argument(
        "--headless",
        default="true",
        choices=["true", "false"],
        help="Run browser headless (default: true)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Per-portal timeout in seconds (default: 60)",
    )
    parser.add_argument(
        "--debug-dir",
        default="data/selenium_debug/",
        help="Debug screenshot directory (default: data/selenium_debug/)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    headless = args.headless.lower() == "true"
    debug_dir = args.debug_dir

    _logger.info("=" * 60)
    _logger.info("SELENIUM SMOKE TEST — COVERAGE-3.1 AC2")
    _logger.info("=" * 60)
    _logger.info("Headless: %s | Timeout: %ds | Debug: %s", headless, args.timeout, debug_dir)

    # Ensure debug directory exists
    Path(debug_dir).mkdir(parents=True, exist_ok=True)

    try:
        from scripts.crawl.selenium_crawler import SeleniumBatchCrawler

        batch = SeleniumBatchCrawler(
            headless=headless,
            timeout=args.timeout,
            debug_dir=debug_dir,
        )
    except ImportError as e:
        _logger.error("Failed to import SeleniumBatchCrawler: %s", e)
        _logger.error("Ensure selenium_crawler.py is available and syntactically valid.")
        return 1

    results = []
    all_passed = True

    try:
        # Initialize crawler
        from scripts.crawl.selenium_crawler import SeleniumCrawler

        crawler = SeleniumCrawler(headless=headless, timeout=min(args.timeout, 60))
        driver = crawler._ensure_driver()
        batch.driver = driver  # re-use for screenshot method

        for idx, portal in enumerate(TEST_PORTALS):
            slug = portal["slug"]
            nome = portal["nome"]
            url = portal["url"]
            platform = portal["platform"]
            wait_for = portal.get("wait_for")

            _logger.info("")
            _logger.info("[%d/%d] Testing: %s (%s) — %s", idx + 1, len(TEST_PORTALS), nome, slug, url)
            _logger.info("  Platform: %s | Framework guess: %s", platform, portal["framework_guess"])

            result = {
                "slug": slug,
                "municipio": nome,
                "url": url,
                "platform": platform,
                "status": "pending",
                "framework_detected": "unknown",
                "bid_count": 0,
                "error": None,
                "screenshot": None,
            }

            try:
                # Step 1: Detect framework
                framework = batch.detect_framework(driver, url)
                result["framework_detected"] = framework
                _logger.info("  Framework detected: %s", framework)

                # Step 2: Wait for render
                import time

                time.sleep(2.0)

                # Step 3: Extract bids
                bids = batch.extract_bids_from_page(driver, url)
                result["bid_count"] = len(bids)
                _logger.info("  Bids extracted: %d", len(bids))

                if bids:
                    # Log first bid as sample
                    sample = bids[0]
                    _logger.info(
                        "  Sample bid: orgao=%s | modalidade=%s | objeto=%s",
                        sample.get("orgao", "")[:40],
                        sample.get("modalidade", "")[:20],
                        sample.get("objeto", "")[:60],
                    )

                result["status"] = "ok" if bids else "no_content"

            except Exception as e:
                _logger.warning("  Error: %s", e)
                result["status"] = "error"
                result["error"] = str(e)[:200]
                all_passed = False

                # Debug screenshot on failure
                try:
                    ss = batch._save_debug_screenshot(slug)
                    if ss:
                        result["screenshot"] = ss
                        _logger.info("  Debug screenshot saved: %s", ss)
                except Exception:
                    pass

            results.append(result)

    except Exception as e:
        _logger.error("Crawler initialization failed: %s", e)
        return 1
    finally:
        if "crawler" in locals():
            crawler.close()

    # Summary
    _logger.info("")
    _logger.info("=" * 60)
    _logger.info("SMOKE TEST SUMMARY")
    _logger.info("=" * 60)

    passed = sum(1 for r in results if r["status"] in ("ok", "no_content"))
    failed = sum(1 for r in results if r["status"] == "error")

    for r in results:
        icon = "PASS" if r["status"] in ("ok", "no_content") else "FAIL"
        _logger.info(
            "  %s | %-15s | framework=%-10s | bids=%-3d | %s",
            icon,
            r["municipio"],
            r["framework_detected"],
            r["bid_count"],
            r.get("error", "")[:60] if r.get("error") else "",
        )

    _logger.info("")
    _logger.info("Passed: %d/%d | Failed: %d", passed, len(results), failed)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())

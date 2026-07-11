---
name: error-handling-td-3-4
description: Story TD-3.4 error handling improvements across all 7 crawlers
metadata:
  type: project
---

# Error Handling Improvements (Story TD-3.4)

**Completed:** 2026-07-11

## Changes Made

1. **dom_sc_crawler.py** -- Biggest change: added retry loop with exponential backoff to `_api_request()` (had NO retry before). Added specific exception handling for HTTPError, URLError, TimeoutError, OSError, JSONDecodeError. Added context to all error messages (URL, attempt number, exception type).

2. **transparencia_crawler.py** -- Replaced 13 generic `except Exception` blocks with specific exception types across `detect_platform()`, `scrape_municipio()`, `load_config()`, `_load_entities()`, `crawl_template()`, `crawl()`.

3. **compras_gov_crawler.py** -- Replaced generic `except Exception` in `_make_request()` with specific (HTTPError, URLError, TimeoutError, OSError, JSONDecodeError). Same in both `_normalize_legacy()` and `_normalize_lei_14133()`.

4. **pcp_crawler.py** -- Added JSONDecodeError handling in `_fetch_page()`. Replaced generic `except Exception` in `_transform_record()`. Added URL and entity context to error messages.

5. **tce_sc_crawler.py** -- Added specific exception handling in `crawl()` (licitacoes e contratos). Replaced generic in both `_transform_licitacao()` and `_transform_contrato()`. Added exception safety net in `_api_request()`.

6. **doe_sc_crawler.py** -- Added specific exception handling in `_get_token()` (URLError, TimeoutError, OSError, JSONDecodeError). Replaced generic in `_transform_record()`.

7. **contracts_crawler.py** -- Added explicit 429 handling (was implicitly caught by HTTPError catch-all). Added JSONDecodeError handling. Replaced generic in `_transform_record()`.

## Pattern Used

Use OSError catch for HTTPError/URLError hierarchy (since HTTPError is subclass of URLError, which is subclass of OSError). Avoid importing urllib.error at module level by catching the base OSError type where specific status-code handling isn't needed.

## Key Insight

Python's urllib.error.HTTPError and urllib.error.URLError are subclasses of OSError. When a function doesn't already import urllib at module level, catching OSError is sufficient to cover the entire HTTP/networking exception hierarchy.

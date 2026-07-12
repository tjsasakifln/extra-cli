# SC Compras Crawler Diagnostic Report

> **Story:** COVERAGE-2.2 | **Date:** 2026-07-11
> **Crawler:** `scripts/crawl/sc_compras_crawler.py` (20.8 KB)
> **Orchestrator:** `scripts/crawl/monitor.py`

## Overview

The SC Compras crawler connects to the Portal de Compras do Governo de Santa
Catarina (`compras.sc.gov.br`) and the electronic bidding system
(`e-lic.sc.gov.br`, Paradigma platform). This diagnostic verifies connectivity,
anti-bot detection, and list page availability.

## Endpoints

| Endpoint | URL | Purpose |
|----------|-----|---------|
| Main Portal | `https://compras.sc.gov.br` | Unified procurement portal |
| e-lic | `https://e-lic.sc.gov.br` | Electronic bidding system |
| Listagem | `https://compras.sc.gov.br/licitacoes` | Paginated listing |
| e-lic Listagem | `https://e-lic.sc.gov.br/licitacao` | Paginated listing (fallback) |

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `SC_COMPRAS_BASE_URL` | `https://compras.sc.gov.br` | Main portal URL |
| `SC_COMPRAS_E_LIC_URL` | `https://e-lic.sc.gov.br` | e-lic portal URL |
| `SC_COMPRAS_TIMEOUT` | `45` | HTTP timeout in seconds |
| `SC_COMPRAS_MAX_RETRIES` | `3` | Max retry attempts per URL |
| `SC_COMPRAS_PAGE_DELAY_S` | `1.0` | Delay between pages |
| `SC_COMPRAS_MAX_PAGES` | `100` | Max pages to crawl |
| `SC_COMPRAS_FULL_DAYS` | `30` | Days to look back in full mode |
| `SC_COMPRAS_INCREMENTAL_DAYS` | `3` | Days to look back in incremental mode |

## Diagnostic Function

The crawler exposes a `diagnostic()` function that tests connectivity without
performing a full crawl. It returns structured data including:

- **Main portal**: reachability, HTTP status, response time, Cloudflare detection
- **e-lic portal**: reachability, HTTP status, response time
- **List page test**: test of one list page with 3-day date range
- **Summary**: human-readable assessment of portal status

### Usage

```bash
# Via monitor.py (recommended)
python scripts/crawl/monitor.py --source sc-compras --mode dry-run

# Direct diagnostic
python -c "
from scripts.crawl.sc_compras_crawler import diagnostic
import json
print(json.dumps(diagnostic(), indent=2, default=str))
"
```

## Execution Modes

| Mode | Command | Description |
|------|---------|-------------|
| Dry-run | `monitor.py --source sc-compras --mode dry-run` | Connectivity test only |
| Full | `monitor.py --source sc-compras --mode full` | Full crawl (last 30 days) |
| Incremental | `monitor.py --source sc-compras --mode incremental` | Incremental (last 3 days) |

## Anti-Bot Detection

The diagnostic function checks for these anti-bot indicators in the HTTP response:

1. **Cloudflare Challenge**: Detects Cloudflare JS challenge pages,
   `cf-browser-verification`, `cf_challenge`, `cf-turnstile`
2. **CAPTCHA**: Detects reCAPTCHA, hCaptcha, Turnstile widgets
3. **Generic Challenge**: Detects JS challenge patterns

### If Anti-Bot Detected

If Cloudflare or anti-bot protection is detected, the crawler falls back to:

```bash
python scripts/crawl/monitor.py --source selenium \
  --target "https://compras.sc.gov.br" \
  --mode full --uf SC
```

This uses `scripts/crawl/selenium_crawler.py` (from FEAT-2.4) which can
handle JavaScript-rendered pages.

## Data Schema

After a successful crawl, data is persisted in `pncp_raw_bids` with
`source = 'sc-compras'`:

```sql
SELECT COUNT(*) as total_records,
       MIN(data_publicacao) as oldest,
       MAX(data_publicacao) as newest
FROM pncp_raw_bids
WHERE source = 'sc-compras';
```

## Entity Matching

After ingestion, the cascade matching pipeline is executed automatically:

1. **Level 1 — CNPJ match** (8-digit base) [confidence: high]
2. **Level 2 — Normalized name + municipio** [confidence: high]
3. **Level 3 — Fuzzy matching** (rapidfuzz/difflib) [confidence: high|medium|low]

Coverage impact can be measured via:

```bash
python scripts/crawl/monitor.py --report-coverage
```

## Known Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Cloudflare/anti-bot | HTTP crawler fails | Selenium fallback |
| Layout changes | Parser breaks — data not extracted | Diagnostic + manual fix |
| Rate limiting (429) | Incomplete crawl | Increase `SC_COMPRAS_PAGE_DELAY_S` |
| Portal offline | No data | Accept partial coverage via PNCP |

## Systemd Timer

A systemd timer is available for weekly incremental crawls:

```bash
# Install
sudo cp deploy/systemd/sc-compras-crawl.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable sc-compras-crawl.timer
sudo systemctl start sc-compras-crawl.timer

# Check status
sudo systemctl status sc-compras-crawl.timer
sudo systemctl list-timers 'sc-compras-*'
```

- **Schedule**: Sundays at 09:00 UTC
- **Delay**: Randomized 0-10 minutes
- **Persistent**: Yes (catches up missed runs)

## Changelog

| Date | Version | Change |
|------|---------|--------|
| 2026-07-11 | 1.0.0 | Initial diagnostic document — COVERAGE-2.2 |

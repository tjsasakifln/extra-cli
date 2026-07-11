---
name: story-td-0.3-config-fix
description: TD-0.3 — config package fix: created config/constants.py with RetryConfig + 23 constants, updated __init__.py
metadata:
  type: project
---

# Story TD-0.3: Config Package Fix

**Status:** Done (InReview, awaiting QA gate)
**Date:** 2026-07-11

## What was done

Created `config/constants.py` with:
- `RetryConfig` dataclass (10 fields: base_delay, exponential_base, max_delay, jitter, connect_timeout, read_timeout, max_retries, timeout, retryable_status_codes, retryable_exceptions)
- 22 constants: DEFAULT_MODALIDADES, MODALIDADES_EXCLUIDAS, 10 circuit breaker constants (5 sources x 2), 6 PNCP timing constants, 2 Redis constants
- ITEM_INSPECTION_TIMEOUT (used by async_client.py internally)

Updated `config/__init__.py` — from 0 bytes to explicit re-exports of all 23 names from constants.py + PNCP_MAX_PAGES from settings.py.

## Key decisions

- **RetryConfig expanded** beyond story spec: added max_retries, timeout, retryable_status_codes, retryable_exceptions — required by sync_client/async_client `self.config.xxx` access patterns
- **PNCP_MAX_PAGES** NOT duplicated in constants.py — already in settings.py as env-based config; __init__.py re-exports from settings
- **Strategy**: constants.py for static defaults, settings.py for env-based config, __init__.py re-exports both

## Blockers found

AC9 cannot pass — 4 crawl modules depend on missing modules outside TD-0.3 scope: `exceptions`, `middleware`, `metrics`, `degradation`, `redis_pool`, `rate_limiter`. Config-related imports all verified OK.

## Verification

- 73/73 pytest tests passing (test_common.py + test_orchestrator.py)
- ruff: 0 errors
- mypy: 0 new errors
- AC8: all 23 config names importable

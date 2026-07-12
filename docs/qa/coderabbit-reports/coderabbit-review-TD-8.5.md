# CodeRabbit Review Report — TD-8.5

**Date:** 2026-07-11
**Agent:** @dev (Dex)
**Scope:** uncommitted (scripts/ directory)
**Mode:** light (dev phase)

## Results

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0 | N/A |
| MAJOR/HIGH | 11 | Documented (all in files not modified by this story) |
| MINOR/MEDIUM | 29 | Documented as tech debt |

## HIGH Findings (all pre-existing, outside story scope)

| File | Issue | Notes |
|------|-------|-------|
| `ciga_ckan_crawler.py` | Unindexed months access, within-200km arg missing negative option | Pre-existing |
| `generate_transparencia_config.py` | Missing main() guard, non-atomic config write | Pre-existing |
| `check_imports.py` | `__init__.py` not validated, no subprocess isolation | Pre-existing |
| `entity_hierarchy.py` | Savepoint isolation for per-entity processing | Pre-existing |
| `doe_sc_selenium_crawler.py` | Date range not applied in _extract_page_data | Pre-existing |
| `batch_detect_platforms.py` | Hardcoded DB connection string | Pre-existing |
| `sc_dados_abertos_backfill.py` | Missing savepoint in Level 1 lookup | Pre-existing |

## Decision: PASS

No self-healing needed. No CRITICAL findings. No HIGH findings in files modified by this story.

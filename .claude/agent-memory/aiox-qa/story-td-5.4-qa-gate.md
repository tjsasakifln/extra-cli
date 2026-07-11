---
name: story-td-5.4-qa-gate
description: FAIL verdict for TD-5.4 Hardening de Seguranca — scope mismatch, security.py unused, 0/6 ACs met
metadata:
  type: reference
---

# QA Gate: Story TD-5.4 (Hardening de Seguranca)

**Verdict:** FAIL
**Date:** 2026-07-11
**Gate File:** `docs/qa/gates/td-5.4-hardening-seguranca.yml`

## Key Findings

1. **Scope mismatch**: Story ACs describe server/network hardening (firewall, fail2ban, pg_hba.conf, SSL, nmap) but @dev implemented CODE-level hardening. ALL server ACs explicitly deferred to @devops — 0/6 ACs met.

2. **security.py is dead code**: Module created at `scripts/crawl/security.py` but NOT imported or used by any crawler. Zero imports of `sanitize_url_param` or `USER_AGENT` in any crawler file.

3. **URL sanitization not applied**: All 7 crawlers still use unsafe `f"{k}={v}"` pattern. No crawler calls `sanitize_url_param()`.

4. **User-Agent not standardized**: No crawler imports `USER_AGENT` from security.py. Hardcoded UA strings remain.

5. **md5 fix partial**: Claimed 10 files, only 3 actually have `usedforsecurity=False` (common.py, doe_sc_crawler.py, transparencia_templates/base.py).

6. **Documentation misaligned**: `docs/td-001/security-hardening.md` describes code changes not present in working tree.

## Issues Documented

- REQ-001 (high): 0/6 ACs met — scope mismatch
- SEC-001 (high): security.py unused, URL sanitization not applied
- SEC-002 (medium): md5 fix only in 3/10 files
- DOC-001 (medium): documentation aspirational, not actual
- TEST-001 (low): no tests for security.py

## Status Transition
InReview → InProgress (returned to @dev for fixes)

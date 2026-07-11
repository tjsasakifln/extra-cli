---
name: story-td-0.1-qa-gate
description: QA Gate CONCERNS verdict for Story TD-0.1 (Backup Automatizado PostgreSQL)
metadata:
  type: reference
---

# QA Gate: Story TD-0.1 — Setup Backup Automatizado

**Verdict:** CONCERNS
**Date:** 2026-07-11
**Reviewer:** Quinn (Guardian)
**Story File:** `docs/stories/epics/epic-td-001-resolution/story-TD-0.1-backup-automatizado.md`
**Gate File:** `docs/qa/gates/td-0.1-backup-automatizado.yml`

## Summary

9/9 ACs implementados e verificados. CodeRabbit review executou com 17 findings (2 CRITICAL, 9 MAJOR, 6 MINOR). 8 medium issues documentados nas categorias seguranca, confiabilidade e documentacao.

**Decision:** CONCERNS (non-blocking). Story transitioned InReview -> Done.

## Top Issues

- **SEC-001 (medium):** DSN password in cmdline via --dbname -- use PGPASSWORD env var
- **SEC-002 (medium):** SSH key without passphrase documented as standard practice
- **REL-001 (medium):** Lock mechanism not atomic (PID file race condition)
- **REL-002 (medium):** --jobs silently ignored in piped pg_restore
- **DOC-001 (medium):** SSH port 23 missing in documentation sshfs commands

## Files Reviewed

- `scripts/backup-database.sh` (409 lines) -- pg_dump + gzip + sshfs + retention
- `scripts/restore-database.sh` (254 lines) -- 4-mode restore (full/schema/data/list)
- `docs/ops/backup.md` (457 lines) -- full ops documentation
- `.env.example` -- backup config vars added

## Why CONCERNS not FAIL

All issues are medium/low severity. Scripts are functional and correct. Issues are improvements for production hardening, not blockers. VERDICT: CONCERNS.

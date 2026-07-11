---
name: Story TD-1.2 QA Gate
description: PASS verdict (upgraded from CONCERNS). SEC-001/002 resolved. Zero hardcoded passwords in all .py + .sh. AC6 rotation pending.
metadata:
  type: project
---

# Story TD-1.2 QA Gate — PASS (upgraded from CONCERNS)

**Story:** TD-1.2 — Remover Segredos Hardcoded
**Gate Verdict:** PASS (upgraded from CONCERNS)
**Date:** 2026-07-11 (re-verification)

## 7 Quality Checks

| Check | Result |
|-------|--------|
| 1. Code Review | PASS |
| 2. Unit Tests | N/A |
| 3. Acceptance Criteria | 9/10 |
| 4. No Regressions | PASS |
| 5. Performance | PASS |
| 6. Security | PASS |
| 7. Documentation | PASS |

## Issues Resolved

- **SEC-001** (high): db/setup_db.sh — hardcoded smartlic_local replaced with `${LOCAL_DATALAKE_DSN:?Erro:...}` (fail-safe, script aborts if env var unset)
- **SEC-002** (high): deploy/install.sh:32,50 — hardcoded smartlic_local replaced with `${PG_PASSWORD:?Erro:...}` and `${LOCAL_DATALAKE_DSN:?Erro:...}`

## Remaining

- **REQ-001** (medium): AC6 password rotation pending — requires Hetzner VPS access and stakeholder coordination

## Key Takeaway

Shell scripts now use `${VAR:?erro}` pattern (fail-safe, abort if env var not set), matching the `os.getenv()` pattern used in Python files. All 13 .py files and 4 shell scripts verified: zero hardcoded passwords in source code.

**Why CONCERNS-to-PASS upgrade:** The 3 shell script residues were the only remaining code-level issues from the original gate. All resolved with `${VAR:?erro}` pattern. AC6 rotation is a process/operations coordination item, not a code quality issue.

**How to apply:** When auditing secrets, check ALL file types including .sh. The `${VAR:?erro}` pattern is the correct shell equivalent of `os.getenv("VAR", "")` for security-critical env vars — it fails fast if unset rather than silently using empty string.

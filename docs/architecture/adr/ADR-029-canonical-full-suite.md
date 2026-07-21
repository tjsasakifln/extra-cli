# ADR-029 — Canonical full suite entrypoint

**Status:** Accepted  
**Date:** 2026-07-20  
**Campaign:** STABILIZE-GLOBAL-FULL-SUITE-01

## Context

Selective CI paths (`make test`, default `pytest.ini` `addopts` with `-m "not slow"`)
were green while the global suite remained undefined: `make test-all` inherited
implicit marker exclusion, and the GitHub Actions job `Test All (full suite)` was
gated to `workflow_dispatch` only without PostgreSQL.

## Decision

1. **Single executable definition:** `python -m scripts.ops.run_full_suite`
2. **Shared by** local `make test-all` and CI job `Test All (full suite)`
3. **Flags:** `pytest tests/ -m "" -o addopts=''` plus coverage thresholds
4. **DB:** caller provisions disposable PostgreSQL 16 (pgvector image in CI);
   entrypoint applies **all** versioned migrations (no hard-coded max) and
   deterministic seeds (`db/seed/001_sc_entities.py`, `002_entity_aliases.py`)
5. **Isolation env:** `REQUIRE_REAL_DB=1` and `RESILIENCE_REQUIRE_DB=1` so
   `tests/conftest.py` does not mock `psycopg2.connect`
6. **CI triggers:** `pull_request` → `main`, `push` → `main`, `workflow_dispatch`

Default `make test` retains `-m "not slow"` for fast feedback.

## Consequences

- Claims of FULL_SUITE_EXECUTED / “Suíte global completa verde” require this path
  (or proven equivalent) with exit 0, zero FAILED/ERROR/DESELECTED, and CI job success.
- Live/external tests remain explicitly marked; they must not be used as operational proof.

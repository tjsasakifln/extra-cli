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
4. **DB:** caller provisions local PostgreSQL 16 (pgvector image in CI) with
   `CREATEDB`; the entrypoint creates a disposable sibling database, applies
   **all** versioned migrations (no hard-coded max), and loads deterministic
   seeds (`db/seed/001_sc_entities.py`, `002_entity_aliases.py`)
5. **Isolation env:** `REQUIRE_REAL_DB=1` and `RESILIENCE_REQUIRE_DB=1` so
   `tests/conftest.py` does not mock `psycopg2.connect`
6. **CI triggers:** `pull_request` → `main`, `push` → `main`, `workflow_dispatch`

Default `make test` retains `-m "not slow"` for fast feedback.

## Consequences

- Claims of FULL_SUITE_EXECUTED / “Suíte global completa verde” require this path
  (or proven equivalent) with exit 0, zero FAILED/ERROR/DESELECTED, and CI job success.
- Live/external tests remain explicitly marked; they must not be used as operational proof.

## Amendment — strict `real_db` convergence (#285, 2026-08-26)

The same entrypoint owns the opt-in selection through
`python -m scripts.ops.run_full_suite --real-db-only --repeat 2`:

1. The supplied DSN must be local and its user must have `CREATEDB`; production
   and soak database names are rejected.
2. Every repetition creates a uniquely named empty sibling database, applies
   every canonical migration and both deterministic seeds, validates the exact
   migration ledger, seed cardinalities, and a real psycopg2 connection, then
   drops the database even on failure.
3. The first repetition uses collection order and the second reverses it. Any
   skip from a `real_db` test while the opt-in is active is converted to failure.
4. Administrative operations use psycopg2. `psql` is not a hidden local or CI
   prerequisite; a missing Python driver fails preflight as
   `REAL_DB_TOOLING_MISSING`.

This is a mode of the canonical runner, not a second marker or fixture framework.

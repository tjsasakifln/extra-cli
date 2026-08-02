# BASELINE — EXTRA-DECISION-OUTCOME-MEMORY-01

Captured: 2026-08-02 (UTC session)

## Git

| Fact | Value |
|------|--------|
| Baseline branch | `origin/main` |
| Baseline SHA | `704975a7bcdd43d4dc6769fbf6c14726327ab37b` |
| Baseline tip | `fix(integration): bid_readiness acervo path + CC consulting adapters (#195)` |
| Campaign branch | `campaign/EXTRA-DECISION-OUTCOME-MEMORY-01` (created from origin/main) |
| Working tree start | Clean relative to origin/main (local WIP stashed as `wip-before-decision-memory-campaign` from `feat/pseo-export-isolated`) |

## Open PRs (not merged by this campaign)

| PR | Title | Head | CI (at pre-flight) | Scope relation |
|----|-------|------|--------------------|----------------|
| #196 | feat(ops): make extra-cli production-operational and prove readiness | `feat/production-readiness-closeout` | Mostly SUCCESS (one CANCELLED policy run) | Production readiness — **do not duplicate** |
| #197 | feat(predictive): genuine predictive intelligence with honest claim gates | `campaign/EXTRA-PREDICTIVE-INTELLIGENCE-PRODUCTION-01` | FAILURE (ruff, full suite, edital relevance) | Predictive — **do not incorporate**; optional decoupled prediction ref only |

## Migrations on origin/main (`db/migrations/`)

Highest present file: `067_process_documents_runs.sql`

Sequence observed (suffix): …062, 063, 064, **gap 065**, 066, 067.

**Next migration number for this campaign: `068`** (derived from filesystem on origin/main, not assumed a priori).

Local test DB (`postgresql://test:***@127.0.0.1:5433/extra_test`) already contains version `068` named `068_predictive_intelligence.sql` from unmerged PR #197 work. That object is **not** on origin/main. Campaign migration will be `068_decision_outcome_memory.sql`. Local proof must reconcile orphaned 068 (clean DB or remove orphaned ledger row + objects) before claiming migration apply.

## Decision-loop files (origin/main)

| Path | Role |
|------|------|
| `scripts/ops/extra_decision_loop.py` | Weekly decision loop orchestration |
| `scripts/ops/extra_decision_review.py` | Human ACCEPT/REJECT/DEFER ledger → `human-decisions.jsonl`; finalize → `decision-loop-state.json` |
| `scripts/ops/extra_actionable.py` | Actionable classification |
| `scripts/ops/extra_profile.py` | Profile stamp / validation |
| `scripts/ops/weekly_decision_artifacts.py` | Weekly package artifacts |
| `scripts/ops/weekly_cycle.py` | Weekly cycle entry |
| `config/client_profiles/extra.yaml` | Extra client profile |
| `scripts/extra_ledger/cli.py` | Separate ledger CLI (not canonical cross-run decision memory) |

### Legacy review facts

- Decisions: `ACCEPT`, `REJECT`, `DEFER` only.
- Ledger: append-only JSONL `human-decisions.jsonl` under run_dir.
- State: `decision-loop-state.json` after finalize.
- PASS terminal: `PASS_EXTRA_DECISION_LOOP_ACCEPTED` only after human package finalize.
- No PostgreSQL persistence in review path today.
- Mapping target (campaign): ACCEPT→GO, DEFER→REVIEW, REJECT→NO_GO (preserve original).

## PostgreSQL connection pattern

- Env: `LOCAL_DATALAKE_DSN` (default `postgresql://test:test@127.0.0.1:5433/extra_test` in docs).
- Helper: `scripts.workspace.common.get_dsn` / `try_connect`.
- Commercial pattern: `scripts.commercial_leads.dbutil.connect` (psycopg2 + RealDictCursor).
- Migrations: `python3 -m scripts.ops.apply_migrations --dsn …` tracks `public._migrations(version, name, applied_at, checksum)`.

## Patterns to reuse

- Append-style ledger ideas: `062_commercial_leads_ledger.sql`, `commercial_feedback_ledger`.
- Client isolation tests pattern: `scripts/commercial_leads/isolation.py`.
- CLI JSON machine-readable: `scripts.commercial_leads.cli`.
- Idempotent migration apply/skip.

## Local environment facts

| Fact | Value |
|------|--------|
| PostgreSQL | Reachable at 127.0.0.1:5433 (PostgreSQL 18.4) |
| Applied max on local test DB | 068 (predictive orphan, not on main) |
| Decision/outcome tables on local DB | None for this domain |

## Non-actions at baseline

- No merge of #196 or #197.
- No pSEO / predictive model / Command Center redesign.
- No invented Extra decisions or outcomes.

## Campaign scope (implementation target)

Vertical slice **Decision & Outcome Memory v1**:

1. Migration `068_decision_outcome_memory.sql`
2. Generic module `scripts/decision_memory/`
3. Integrate `extra_decision_review` (PG-first, fail-closed)
4. Import legacy, weekly-board, metrics, CLI, tests, evidence pack

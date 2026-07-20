# ADR-023 — Architecture Reset Campaign 2026-07-20

- **Status:** ACCEPTED (campaign charter) — implementation phased via subsequent PRs  
- **Date:** 2026-07-20  
- **Commit (baseline):** `d6d9e1984e348d64a669546613e192e4ebf610cd`  
- **Campaign:** `ARCH-RESET-2026-07-20`  
- **Supersedes / relates:** ADR-017 (workspace facade), ADR-018 (coverage multi-metric), ADR-019 (source registry), ADR-020 (ops data not in git), ADR-021 (adapter fail-closed), ADR-022 (client profile law). Does **not** revoke commercial DoD gates.

## Context

The repository is a single-operator B2G consultive tool for Extra Construtora. Main (`d6d9e19`) already declares `make extra-weekly` as the product cycle, yet multiple orchestrators, coverage/freshness paths, and ledgers coexist. Open PRs include a large CTO Autopilot stack (#48–#51) and a product decision/ledger lineage (#52–#53). External research proposed dbt, Soda, Splink, PyMuPDF, rule-engine, XlsxWriter, fpdf2 — these are **hypotheses**, not decisions.

## Problem

1. Ambiguous “how do I run the system?” among weekly / golden-path / run-pipeline / resilient / intel / ROI force-next.  
2. More than one implementation per responsibility (coverage, freshness, ledger).  
3. Risk of agent-governance theater (CTO stack) competing with product delivery.  
4. Risk of adopting OSS frameworks without reproducible net gain.  
5. Documentation lagging or conflicting with executed code.

## Forces

- Single maintainer → cognitive load dominates.  
- Commercial promises (95% coverage/recall, freshness, PDF+Excel pack) must not be silently reduced.  
- Local-first PostgreSQL + CLI/Make preferred.  
- Full test suite is often red or skipped — honesty over greenwashing.  
- Incremental modernization (Branch by Abstraction, Strangler Fig) over rewrite.

## Options evaluated

| Option | Pros | Cons |
|--------|------|------|
| A. Big-bang rewrite | Clean slate | Forbidden; high risk; long dark time |
| B. Status quo + more campaigns | Fast short-term | Complexity compounds; false greens |
| C. **Architecture reset campaign** (this ADR) | Inventories first; spikes with REJECT allowed; one product pipeline; OSS only with proof | Multi-PR discipline required |
| D. Merge all open PRs | Clears board | Imports agent theater + suite failures |

## Decision

Adopt **option C**: campaign `ARCH-RESET-2026-07-20` with the following non-negotiables:

1. **Monolith modular, local-first** — Python 3.12, PostgreSQL 16, CLI/Make; no K8s/Kafka/Redis-required/Airflow/microservices.  
2. **One product pipeline:** `collect → raw → normalize → reconcile → quality → intelligence → decision → delivery`, entered via **`make extra-weekly`** unless a later ADR renames it with evidence.  
3. **One engineering verify command** (to be introduced) — validates system; does not compete as product orchestration.  
4. **At most one canonical implementation** per: source registry, coverage contract, freshness contract, operational ledger, weekly flow, decision rules, evidence model, weekly pack generator.  
5. **OSS adoption only after spike** meeting the campaign dependency criteria; `REJECTED_SPIKE` is a valid outcome.  
6. **Existing PR disposition** as documented in campaign `PR-DISPOSITION.md` — prefer product #52/#53 path; park/supersede CTO stack for mainline product.  
7. **No auto-merge; no force-push; no false seals** (`LOCAL_READY`, 95%, `VPS_OPERATIONAL`, `PROJECT_DONE`) without HEAD-bound evidence.  
8. **LLM non-authority** over coverage, freshness, official status, entity merge, invented values, eliminatory criteria without explicit rules.

## Consequences

### Positive

- Clear campaign order: baseline → characterization → consolidate pipeline → spikes → adoption → docs → cleanup.  
- Explicit rejection path for OSS.  
- Reduces dual orchestration risk if followed.

### Negative / costs

- CTO Autopilot work may not land on main (sunk cost if rejected).  
- Spikes consume time without guaranteed adoption.  
- Full suite debt remains a blocker for honest READY.

### Risks

- Documentation-only “progress” without capacity change — mitigated by requiring live weekly cycle proof before campaign close.  
- Premature DoD flips — forbidden without evidence + independent review.  
- Stacked PRs reappearing — fitness function: no alternate pipeline without ADR.

## Migration strategy

1. PR A (this campaign baseline + ADR) — docs only.  
2. Characterization tests and seams before behavior change.  
3. Consolidate weekly pipeline (Branch by Abstraction).  
4. Conditional spikes (OCDS, dbt, quality, parsing, entity resolution, rules, reporting).  
5. Adoption PRs only for spikes that pass criteria.  
6. Final docs rebaseline + cleanup after live cycle.

## Rollback

- Revert campaign doc PRs independently.  
- Each code PR must document rollback commands.  
- Never force-push main.

## Evidence

- `docs/ops/campaigns/ARCH-RESET-2026-07-20/BASELINE.md`  
- `docs/ops/campaigns/ARCH-RESET-2026-07-20/baseline.json`  
- `docs/ops/campaigns/ARCH-RESET-2026-07-20/PR-DISPOSITION.md`  
- `docs/ops/campaigns/ARCH-RESET-2026-07-20/ARCHITECTURE-CURRENT.md`  
- `docs/ops/campaigns/ARCH-RESET-2026-07-20/PR-PLAN.md`  
- `docs/ops/campaigns/ARCH-RESET-2026-07-20/FITNESS-FUNCTIONS.md`

## Allowed claims (this ADR)

- Campaign charter accepted for execution planning.  
- Baseline SHA and inventories recorded.

## Forbidden claims (this ADR)

- Architecture fully modernized.  
- Any OSS library adopted.  
- Coverage/freshness/LOCAL_READY seals.  
- Existing PRs merged or closed by this decision alone.

## Status note

Implementation PRs may refine details; structural deviations require a new ADR.

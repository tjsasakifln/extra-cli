# Feature Specification: National Contracts Intelligence Architecture

**Feature Branch**: `campaign/national-contracts-intelligence-architecture-01`  
**Spec dir**: `specs/003-national-contracts-intelligence-architecture`  
**Created**: 2026-07-22  
**Status**: Draft → Ready for plan after checklist  
**Campaign ID**: `NATIONAL-CONTRACTS-INTELLIGENCE-ARCHITECTURE-01`  
**Base SHA**: `a38981bfa616b8f47363da6ff91b12a28bec218c` (`origin/main`)  
**Input**: Transform national PNCP contracts ingestion into a structured strategic intelligence asset for Extra Construtora, while preserving SC operational metrology, canonical-universe coverage truth (spec 001), and full isolation from the live `HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01` 3y backfill.

## Context & Authorities

| Authority | Role |
|-----------|------|
| `specs/001-dual-capability-coverage-truth` | Sole authority for operational coverage gates of `open_tenders` and `historical_contracts` |
| Canonical universe via `load_canonical_universe()` | Sole denominator identity for SC operational coverage (~1093 when seed matches) |
| `pncp_supplier_contracts` | Existing national contracts fact table (UF, orgao, fornecedor, objeto, valores, windows) |
| `scripts/contract_intel` | Existing intelligence CLI (historico, fornecedores, precos, …) — preferred delivery surface |
| `scripts/ops/deliverable_*` | Existing product scripts A–E to reuse, not replace |
| HC Operational Closure campaign | Parallel live writer of national contracts; **out of scope for interference** |

## Non-Goals *(mandatory)*

1. Do **not** run a new multi-year national PNCP backfill.
2. Do **not** interrupt, reset, or write to HC checkpoints (`hc_closure_3y` etc.).
3. Do **not** write to the HC database (`extra_test` on port 5433) from this campaign’s default tooling.
4. Do **not** claim SC operational coverage ≥95%, LOCAL_READY, VPS ready, or DOD complete based on national volume.
5. Do **not** treat national row count as coverage numerator or denominator.
6. Do **not** invent partnership, consortium, or subcontract relationships without evidence fields.
7. Do **not** treat textual similarity of objetos as technical equivalence without an explicit non-comparable flag.
8. Do **not** build a second SmartLic-class platform or competing weekly pipeline.
9. Do **not** perform destructive migrations (DROP/RENAME of tables used by live ingestion).
10. Do **not** average dual capabilities or revive legacy undifferentiated `is_covered` as coverage.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Separate national raw from SC operational truth (Priority: P1)

As an architect/operator, I need every contracts analysis path to declare whether it is using national raw inventory, SC-filtered facts, canonical-universe operational coverage, or strategic intelligence products — so national scale cannot be mistaken for SC monitoring completeness.

**Why this priority**: False coverage is an existential integrity risk for commercial and DOD claims.

**Independent Test**: Fixtures with millions of non-SC rows + zero SC entity evidence yield **unchanged** dual `historical_contracts` coverage vs empty national table; SC coverage only moves when canonical-entity evidence changes.

**Acceptance Scenarios**:

1. **Given** a fixed canonical universe and fixed SC coverage evidence, **When** N non-SC national contracts are inserted, **Then** `historical_contracts` denominator, numerator, and gate status are identical to the baseline.
2. **Given** the same baseline, **When** non-SC national contracts are removed, **Then** SC operational coverage metrics remain identical.
3. **Given** an entity never queried for contracts, **When** national rows exist for unrelated UFs, **Then** the entity is **not** classified as `success_zero` or covered.

---

### User Story 2 — Query competitors and geographic footprint (Priority: P1)

As a commercial strategist at Extra, I need to see which suppliers win similar construction-related contracts in SC and other UFs, with clear labels of fact vs inference.

**Why this priority**: Directly supports bid strategy and competitive positioning.

**Independent Test**: Fixture with known suppliers across UFs; CLI/SQL product returns ranked suppliers with UF set, contract counts, and value bands; no partnership claims without co-bid evidence.

**Acceptance Scenarios**:

1. **Given** contracts for supplier X in SC and PR, **When** competitor geographic map runs, **Then** X appears with UF list `{SC, PR}` labeled as **fact** from contract rows.
2. **Given** supplier Y only outside SC with objects textually similar to Extra’s segment, **When** entrant radar runs, **Then** Y is listed as **potential entrant (hypothesis)** with similarity method and confidence bound, not as “will enter SC”.
3. **Given** missing objeto text, **When** similarity ranking runs, **Then** row is excluded or marked non-comparable.

---

### User Story 3 — Benchmark values without false precision (Priority: P1)

As a pricing analyst, I need national vs SC value distributions by rough segment filters, with explicit non-comparability when objects are not aligned.

**Why this priority**: Wrong price benchmarks destroy commercial trust.

**Independent Test**: Fixture with known value distributions; report shows percentiles and sample sizes; incompatible objects flagged.

**Acceptance Scenarios**:

1. **Given** ≥N comparable contracts in a filter (UF/period/keyword), **When** benchmark runs, **Then** output includes count, p50, p90, min, max, and filter definition.
2. **Given** fewer than minimum sample size, **When** benchmark runs, **Then** status is `insufficient_sample`, not a fake market price.
3. **Given** unit price requested without valid quantity denominator, **When** benchmark runs, **Then** unit price is omitted and limitation recorded.

---

### User Story 4 — Agency (órgão) demand profiles (Priority: P2)

As a BD lead, I need profiles of contracting agencies with volume, recurrence of suppliers, and ticket dispersion to prioritize outreach.

**Why this priority**: Supports targeting and partnership exploration with honesty about evidence limits.

**Independent Test**: Fixture agencies produce ranked profiles with supplier concentration HHI-like indicator labeled as **indicator**, not “cartel”.

**Acceptance Scenarios**:

1. **Given** agency A with multiple contracts, **When** profile runs, **Then** totals, period span, top suppliers, and concentration indicator are returned.
2. **Given** no contracts for agency B, **When** profile runs, **Then** empty/not-found is explicit (not zero-demand claim without query scope).

---

### User Story 5 — Single delivery surface for intelligence (Priority: P2)

As an operator, I need a minimal canonical interface (prefer extending `scripts.contract_intel`) for strategic products, without a new parallel “platform” entry point.

**Why this priority**: Entry-point proliferation breaks operability (constitution CLI-first + canonical entry points).

**Independent Test**: Documented subcommands or SQL entrypoints produce JSON artifacts under campaign products path; weekly operational pipeline unchanged.

**Acceptance Scenarios**:

1. **Given** isolated DSN with fixtures, **When** approved intelligence command runs, **Then** JSON/CSV artifact is written with lineage fields (as_of, filter, git_sha if available, row counts).
2. **Given** weekly operational command, **When** intelligence features exist, **Then** weekly path behavior is unchanged unless explicitly opted in.

---

### User Story 6 — Safe parallel development with live backfill (Priority: P1)

As a platform engineer, I need this campaign’s migrations and tests to run only on an isolated database/port so the live 3y backfill is never blocked or corrupted.

**Why this priority**: Parallel campaign safety is a hard constraint.

**Independent Test**: Safety artifacts prove distinct worktree, branch, port 5435 DB; test suite default DSN is isolated; protected path list exists.

**Acceptance Scenarios**:

1. **Given** HC backfill writing to 5433, **When** this campaign applies additive migrations, **Then** only 5435 (or declared isolated DSN) is targeted.
2. **Given** protected checkpoint paths, **When** campaign scripts run, **Then** they never open those paths for write.

---

### Edge Cases

- UF null/blank on national rows → scope classification `unknown_uf`; excluded from UF-strict products unless explicitly included.
- Entity in canonical universe without CNPJ match to contracts → not covered for operational capability; may still appear in intelligence via name match only if labeled low-confidence.
- Duplicate `contrato_id` upserts → intelligence counts distinct contracts, not raw insert events.
- PNCP partial windows / failed pages in source campaign → intelligence products must not claim “complete national market”.
- Extremely large result sets → commands enforce LIMIT/default caps and streaming/export mode.
- Text search false friends on objeto → always surface match method and sample size.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001 (Scope classification)**: System MUST allow determining, for a contracts analysis context, whether data is (a) national raw inventory, (b) SC geographic filter, (c) canonical-universe operational scope, (d) strategic intelligence product scope — without ambiguous inference. Classification rules and canonical-universe version/stamp MUST be recorded in product lineage when operational scope is used.
- **FR-002 (Provenance)**: Products MUST preserve or surface available provenance fields already present in storage/ingestion (source, windows, ingested_at, source dates, run metadata when available). System MUST NOT invent provenance fields the crawler/API did not supply.
- **FR-003 (SC coverage independence)**: Operational `historical_contracts` coverage MUST remain governed by spec 001 dual engine and canonical universe. National inventory volume MUST NOT change operational denominator or auto-promote entities to covered / `success_zero`.
- **FR-004 (No second backfill)**: Campaign MUST NOT execute a new multi-year national crawl; development uses fixtures, isolated DB, and optional future read-only samples after HC completion.
- **FR-005 (Competitor intelligence)**: System MUST provide a product answering supplier rankings by filter (segment keywords/UF/period) with geographic UF footprint and concentration indicators, labeling fact vs indicator vs hypothesis.
- **FR-006 (Benchmarks)**: System MUST provide value distribution benchmarks with sample size gates and non-comparable handling.
- **FR-007 (Agency intelligence)**: System MUST provide contracting-agency profiles (volume, frequency proxy, top suppliers, ticket dispersion).
- **FR-008 (Partners / interstate — honest)**: System MAY surface co-occurrence and multi-UF activity as **hypotheses** for partners/expansion; MUST NOT assert partnership/consortium/subcontract without dedicated evidence.
- **FR-009 (Product catalog)**: System MUST maintain a prioritized catalog of at least the nine strategic products listed in the campaign brief, each with user, question, decision supported, data, frequency, format, limitations, misinterpretation risk, compute cost class, priority.
- **FR-010 (Interface)**: System MUST expose a minimal canonical interface by extending existing `contract_intel` and/or versioned SQL under `contracts/` + ops deliverable reuse — not a net-new competing top-level product brand.
- **FR-011 (Layering)**: Architecture MUST document four logical layers (Raw National, Curated SC, Extra Intelligence, Delivery) and map them to concrete physical objects (tables/views/marts/commands) chosen for simplicity and compatibility.
- **FR-012 (Additive schema)**: Any schema change MUST be additive (new views/indexes/tables/schemas); MUST NOT drop/rename live ingestion tables.
- **FR-013 (Isolation)**: Default runtime for campaign tests/migrations MUST use isolated DB (`extra_national_intelligence_test` / port 5435 or equivalent). Protected HC paths/processes are off-limits for write.
- **FR-014 (Adversarial coverage tests)**: Automated tests MUST prove national inventory cannot inflate SC operational coverage metrics.
- **FR-015 (Lineage on outputs)**: JSON/CSV strategic outputs MUST include filter definition, as_of timestamp, row counts, and limitations array.
- **FR-016 (Reuse)**: Implementation MUST prefer reusing `deliverable_b_competitors`, `deliverable_d_prices`, `deliverable_a_org_ranking`, and `contract_intel` queries over duplicating logic.

### Non-Functional Requirements

- **NFR-001**: Migrations additive only; no long ACCESS EXCLUSIVE locks on live HC DB (HC DB not targeted).
- **NFR-002**: Priority analytical queries documented with EXPLAIN on isolated/fixture scale; no “fast enough” claim without measurement artifact.
- **NFR-003**: Reproducible via command + fixture + config; no manual-only reports as done definition.
- **NFR-004**: Secrets masked in artifacts; DSNs never committed with real credentials.
- **NFR-005**: Portable to local Docker Postgres and future VPS Postgres; no mandatory proprietary cloud DB.
- **NFR-006**: Host resource courtesy: avoid heavy scans on 5433 while backfill runs.

## Success Criteria *(mandatory, technology-agnostic where possible)*

- **SC-001**: An auditor can distinguish national inventory metrics from SC operational coverage in every primary report (two clearly named sections or products).
- **SC-002**: Adversarial tests pass showing SC operational coverage unchanged under large non-SC inventory insert/delete.
- **SC-003**: At least three strategic products (competitors geo, benchmark SC vs national, agency or supplier profile) produce reproducible artifacts from fixtures.
- **SC-004**: Product catalog of ≥9 items exists with limitations and priority.
- **SC-005**: Parallel isolation gate documented and still true (separate worktree, branch, DB/port; HC process not stopped by this campaign).
- **SC-006**: No DOD operational coverage checkbox is marked complete solely by this campaign’s national intelligence work.
- **SC-007**: Operators can run the primary intelligence entrypoints from documented quickstart in one isolated environment without using the HC write DSN.

## Key Entities

- **National contract fact**: a PNCP-sourced contract row (identity `contrato_id` when present) with org, supplier, object, values, geography, timestamps.
- **Canonical SC entity**: member of the monitored universe for operational coverage (spreadsheet/seed identity).
- **Scope stamp**: metadata declaring which layer/filter/universe version produced a metric.
- **Strategic product run**: a reproducible execution of an intelligence question with lineage and limitations.
- **Coverage evidence (operational)**: per-entity proof used only by dual coverage engine (spec 001) — not interchangeable with “has rows in national table”.

## Assumptions

1. `pncp_supplier_contracts` remains the physical home of national contracts facts; logical layers are primarily views/query scopes, not full table clones.
2. HC backfill will eventually complete; this campaign prepares architecture that can consume completed data later via read-only integration, not live coupling.
3. Extra’s competitive segment is construction/engineering-adjacent; keyword filters are configurable, not hard-coded as complete taxonomy.
4. Minimum sample sizes for benchmarks default to conservative thresholds (documented in plan); adjustable via parameters.
5. Spec 001 dual coverage implementation on `origin/main` is the operational coverage authority even if HC branch has additional adapters not yet merged.

## Dependencies

| Dependency | Type | Notes |
|------------|------|-------|
| Spec 001 dual coverage | hard | Must not regress |
| HC 3y backfill completion | soft (future data richness) | Not required to finish architecture + fixture products |
| Canonical universe seed | hard for operational claims | Intelligence geographic SC filter may use UF=SC without claiming coverage |
| Existing contract_intel / deliverables | reuse | Prefer adapt over rewrite |
| Isolated Postgres 5435 | hard for safe implementation | Campaign default |

## Integration plan (later, with HC campaign)

1. After HC backfill windows complete and entity projection exists, optionally refresh intelligence marts from production-grade national table.
2. Rebase/merge this branch onto accepted main **after** HC-related merges, resolving conflicts consciously.
3. Never copy HC checkpoint semantics into intelligence layer.
4. Keep dual coverage path independent; intelligence remains descriptive analytics.

## Risks (summary)

| Risk | Severity | Mitigation |
|------|----------|------------|
| False coverage claims | CRITICAL | FR-003 + adversarial tests + non-claims |
| Collision with live backfill | CRITICAL | Isolation DB/worktree; protected paths |
| Misleading price benchmarks | HIGH | sample gates; non-comparable flags |
| Over-claiming partners/consortia | HIGH | hypothesis labels only |
| Code drift vs HC branch | MEDIUM | integration plan; feature flags |
| Duplicate CLIs | MEDIUM | extend contract_intel |

## Out of scope details deferred to plan

Physical choice among schemas vs views vs MVs, exact index DDL, command names, and task breakdown are decided in `/speckit-plan` and `/speckit-tasks` after inventory subagents return — constrained by simplicity and FR-010/FR-016.

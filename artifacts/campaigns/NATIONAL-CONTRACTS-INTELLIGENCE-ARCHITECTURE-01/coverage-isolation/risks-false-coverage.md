# Risks — False SC Coverage from National Contracts Work

**Campaign:** NATIONAL-CONTRACTS-INTELLIGENCE-ARCHITECTURE-01  
**Subagent:** C — Metrology  
**As of:** 2026-07-22  

---

## Risk rating scale

| Level | Meaning |
|-------|---------|
| **P0** | Can produce false PASS / false ≥95% / wrong commercial claim |
| **P1** | Can mislead operators or dashboards without hard gate PASS |
| **P2** | Documentation / process drift |

---

## R1 — Volume conflation (P0)

**Risk:** Operators or docs treat `pncp_supplier_contracts` row growth (~millions on HC DB) as SC coverage progress.

**Mechanism:** Human narrative shortcut: “more contracts ingested ⇒ better coverage.”

**Why false:** Dual `coverage_pct` is entity-scoped validated evidence / A_C, independent of `|R|`.

**Mitigations:**

- Campaign STATUS non-claims (already): *National row volume ≠ coverage*  
- Invariants I3, I4, I8  
- Dashboard labels: “ingestion_rows” vs `capability_monitoring_coverage`  
- Adversarial NV-01 / NV-02  

**Residual:** High while HC backfill dashboard shows impressive counts next to SC metrics.

---

## R2 — Presence promoted to coverage (P0)

**Risk:** `data_presence_pct` (from DISTINCT mapped organs in contracts/bids tables) is reported as “coverage.”

**Mechanism:** Both metrics share A_C denominator and similar % shape; naming slip in CLI/UI.

**Engine guard:** Limitations strings; separate fields `data_presence_*` vs `covered_numerator`; FR-007.

**Gaps:** Downstream reports (`multi_source`, workspace CLI, commercial decks) may still mix labels.

**Mitigations:** Metric catalog in `coverage_contract.py`; forbid aliasing commercial signal as coverage; QA claim scan.

---

## R3 — Legacy `is_covered` / calculator (P0)

**Risk:** `scripts/coverage/calculator.py` or `entity_coverage.is_covered` cited as DoD dual coverage.

**Mechanism:** Older readiness/docs used undifferentiated flags; migration 058 still keeps table for diagnostic.

**Engine guard:** `FORBIDDEN_METHODS`; dual ignores admin flags.

**Mitigations:** Comment on table; errata for 214/1093=19.5791%; golden path method stamp `dual_capability_coverage`.

**Residual:** Any new script that `COUNT is_covered` for national campaign KPIs reopens the hole.

---

## R4 — Fake success_zero (P0)

**Risk:** Empty national pages or failed scopes persisted as `success_zero` without pagination/window proof → false covered entities.

**Mechanism:** Crawler writes state string without validators; dual may still reject if validators run — **unless** a bypass path writes covered flags elsewhere.

**Engine guard:** `validate_success_zero` strict; error tokens; contracts backfill years.

**Mitigations:** Ingest pipelines must not set success_zero without proof fields; SZ adversarial suite; never map “0 rows returned” alone to success_zero.

**Residual:** Legacy writers that set state without metadata remain dangerous if dual validators are skipped by alternate gates (`consulting_readiness` pre-dual path).

---

## R5 — Unqueried counted as healthy empty (P0)

**Risk:** Entities never checked reported as success_zero or as 0 gaps.

**Mechanism:** Absence of rows misread as “no contracts, covered.”

**Engine guard:** Missing obs → `never_checked`; FR-022 publishes never_checked aggregates.

**Mitigations:** UQ matrix; gap lists require `never_checked` / `next_action=run_required_sources`.

---

## R6 — Denominator inflation / deflation (P0)

| Variant | Failure mode |
|---------|--------------|
| **Inflate U** | National organs enter seed incorrectly or DB radius used as U |
| **Shrink A_C** | Mark hard entities `not_applicable` without justification to raise % |
| **Hardcode 1093** | Hide seed drift; wrong membership with same count |

**Engine guard:** Seed identity hashes; expected count/sha fail closed; unknown/blocked block PASS; not silent applicable.

**Residual:** Session pipelines with fixed `DENOMINATOR = 1093` (`session_coverage_pipeline.py`) can still publish non-dual %.

---

## R7 — Soft-join CNPJ8 collisions (P1→P0 if multi-entity)

**Risk:** National contracts keyed by CNPJ8 attach to wrong SC entity or double-count presence.

**Mechanism:** Migration 055 soft keys; multi-entity same root (fundação vs prefeitura).

**Engine guard:** Multi-key identity; ambiguous CNPJ8 not first-wins for dual mapping.

**Mitigations:** Prefer CNPJ14 / matched_entity_id for evidence; presence partial unmapped fails measurement completeness when required.

---

## R8 — Outsider evidence silent drop (P0 if silent)

**Risk:** Evidence for non-U entities dropped silently, reconciling counts incorrectly.

**Engine guard:** Dual **raises** on outsider/unmapped evidence (fail closed) — good.

**Residual:** Alternate reporters that filter `WHERE entity_id IN U` without dual may under-report gaps while showing high % on subset.

---

## R9 — Cross-capability leakage (P0)

**Risk:** Strong open_tenders monitoring used to claim historical_contracts readiness (or average).

**Engine guard:** Independent A_C and N_C; FR-009 no average.

**Residual:** Human dashboards that show one “coverage” number.

---

## R10 — Freshness laundering via national re-ingest (P1)

**Risk:** Global table touch / bulk upsert updates “last seen” used by **legacy** 90-day windows, making stale SC entities look fresh without entity-scoped re-query.

**Engine guard:** Dual uses observation `completed_at` + SLA on evidence rows, not table mtime.

**Residual:** `coverage_truth` / `COVERAGE_WINDOW_DAYS=90` still diverge from dual SLAs (documented in c2-coverage-formulas).

---

## R11 — Shared DB with HC operational backfill (P0 operational)

**Risk:** Architecture work on same DB as live national backfill corrupts evidence, locks, or confuses metrics.

**Campaign control:** Isolated DSN `extra_national_intelligence_test:5435`; do not write HC checkpoints; no docker restart of extraconsultoria-test-db-1.

**Residual:** Read-only queries on 5433 still see live volume — must not be pasted into SC gate claims.

---

## R12 — Policy fallback silent applicable (P0)

**Risk:** `DEFAULT_REQUIRED_SOURCES` used as if canonical → wrong required set → false covered.

**Engine guard:** Fallback forces non-canonical / measurement_success=false when used on live path; draft policy NOT_READY.

**Mitigations:** Always `require_active` policy for acceptance packs.

---

## R13 — Marketing / DoD language (P2→P0 if accepted)

**Risk:** DOD or STATUS claims measurement_success or 95% from wrong pack.

**Mitigations:** FR-031 method_acceptance vs live_operational_state vs coverage_gate_state; only ACCEPTED with evidence.

---

## False coverage attack scenarios (summary)

| # | Attack | Expected dual response |
|---|--------|------------------------|
| 1 | Insert 5M non-SC contracts | coverage_pct unchanged |
| 2 | Delete non-SC contracts | coverage_pct unchanged |
| 3 | Flip is_covered true for all | dual coverage_pct unchanged |
| 4 | Write success_zero without pages | not covered |
| 5 | Leave entity unqueried | never_checked, not success_zero |
| 6 | Average two capabilities | field absent / not used as gate |
| 7 | Count national rows / 1093 | not a dual formula |
| 8 | Use DB raio_200km as U | non-canonical; dual uses seed |

---

## Monitoring recommendations (post Spec Kit)

1. CI job: pure dual fixtures including NV-01/NV-03 style presence injects.  
2. Claim scanner: ban phrases linking “milhões de contratos” to “cobertura SC %”.  
3. Artifact schema: require `method=dual_capability_coverage` + `universe.seed_sha256` on any coverage gate export.  
4. Separate panels: Ingestion (rows/s) | Presence (entities with rows) | Monitoring coverage (dual).  
5. Never run adversarial DB mutators on HC backfill database.

---

## Open residual questions for Architect / Spec Kit

1. Will national intelligence products store **separate** coverage metrics for national market scope (new denominator), and how will naming prevent SC collision?  
2. Should presence queries for historical_contracts **filter UF=SC or entity_id∈U at SQL** to reduce unmapped load (performance R), without changing coverage semantics?  
3. Is `session_coverage_pipeline` still callable in prod paths that operators confuse with dual gates?

---

## Cross-links

- [coverage-engine-map.md](./coverage-engine-map.md)  
- [invariants.md](./invariants.md)  
- [adversarial-test-matrix.md](./adversarial-test-matrix.md)  
- Campaign [STATUS.md](../STATUS.md)  
- Spec `specs/001-dual-capability-coverage-truth/spec.md`  

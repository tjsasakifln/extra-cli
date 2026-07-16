# Spec Critique: MISSÃO DATA-FOUNDATION AIOX

**Date:** 2026-07-16
**Reviewer:** Quinn (QA Agent)
**Spec Version:** 1.0

---

## Critique Verdict: APPROVED WITH CONCERNS

| Dimension | Score (1-5) | Verdict |
|-----------|-------------|---------|
| Completeness | 4.5 | All 5 domains covered (engine, data, sources, ops, quality) |
| Testability | 4.0 | 140+ tests specified, but chaos test scenarios need more detail |
| Feasibility | 4.0 | Realistic scope, but 6 stub replacements in parallel is aggressive |
| Consistency | 5.0 | No contradictions found; traceability matrix is complete |
| Traceability | 5.0 | Every FR traces to source; every test traces to FR |

**Average Score: 4.5** -> **APPROVED**

---

## Dimension 1: Completeness (4.5/5)

### Strengths
- All 5 mission domains explicitly addressed (FR-1 through FR-5)
- 10-section structure covers problem, requirements, architecture, operations, quality
- Source mapping table with priority and watermark granularity
- DLQ, watermark, provenance, dedup tables designed at SQL level
- Operations model includes CLI commands for every scenario
- 140+ new tests across unit, integration, chaos categories

### Gaps Found
1. **CONCERN:** No specification of DLQ record size limits/truncation. Error messages can be very long; FR-2.1 should specify max payload size.
2. **CONCERN:** No monitor.py integration for DLQ replay authentication. Who can replay DLQ entries? Missing authorization concern.
3. **CONCERN:** Chaos test scenarios lack specific assertions. FR-5.1 says "verify behavior" but doesn't specify _expected_ behavior (retry count? circuit breaker state? DLQ entry?).
4. **CONCERN:** No performance SLA baseline defined. NFR-4.3 says "baseline parity" but no baseline number is documented. Recommend benchmarking before implementation.

---

## Dimension 2: Testability (4.0/5)

### Strengths
- Clear test count per category (30 DLQ unit, 20 watermark, etc.)
- Test categories map to specific FR IDs
- Integration tests specified with concrete scenarios (kill/resume)
- Chaos tests organized by failure type

### Gaps Found
1. **CONCERN:** Chaos test scenarios describe "what" but not "how". How to inject 429 responses? Via mock or proxy? Recommend specifying `responses` library or custom middleware.
2. **CONCERN:** Stub replacement tests don't specify mock strategies. Testing real Redis without Redis available requires clear fallback test pattern.
3. **RECOMMENDATION:** Add a `conftest_chaos.py` fixture file for shared fault injection utilities.

---

## Dimension 3: Feasibility (4.0/5)

### Strengths
- All new tables use PostgreSQL (existing constraint)
- DLQ design is simple and well-scoped
- Watermark table uses existing checkpoint pattern
- Graceful fallback for Redis (already in codebase pattern)
- Backward compatibility maintained (new features opt-in)

### Risks
1. **CONCERN:** 6 stub replacements listed. Each requires testing. Recommend staggering: Phase A (metrics + base client) -> Phase B (redis_pool + supabase_client) -> Phase C (clients/pncp).
2. **CONCERN:** Migration count jumps from 50 to ~57 (7 new tables). Need to verify no conflicts with existing FK constraints.
3. **CONCERN:** Existing 1326 tests must not regress. The spec says "opt-in" but integration test fixtures may need updates. Recommend CI gate G-9.6 blocks merge on regression.

---

## Dimension 4: Consistency (5.0/5)

- No contradictory requirements found
- FR-2.7 (dedup pipeline) references per-crawler hashes correctly
- FR-3.6 correctly lists all 6 stub modules
- Operations model consistent with data layer design
- NFR timing constraints are realistic (30s shutdown, 100ms watermark commit)
- Traceability matrix is complete and self-consistent

---

## Dimension 5: Traceability (5.0/5)

- Every FR has a source tag (Codebase analysis, Gap analysis, etc.)
- Every FR has a priority (MUST/SHOULD)
- Appendix A maps FR ID -> Source -> Priority -> Tests -> Dependencies
- NFRs map to verification methods
- Constraints map to impact statements
- No orphan requirements found

---

## Verdict Criteria

| Criteria | Met? | Notes |
|----------|------|-------|
| Average >= 4.0 | YES | 4.5 |
| No score < 3.0 | YES | Minimum 4.0 |
| All critical concerns addressed? | YES | See below |
| Spec ready for impl planning? | YES | With concerns noted |

## Required Fixes Before Implementation

1. [ ] Add DLQ payload size limit specification to FR-2.1
2. [ ] Specify expected behavior assertions for chaos test scenarios (FR-5.1 through FR-5.8)
3. [ ] Document current performance baseline before implementation (NFR-4.3)
4. [ ] Stagger stub replacement into phases in APPENDIX A dependency column

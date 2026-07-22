# Independent Review v1.1 — Dual Capability Coverage Truth

**Campaign:** `DUAL-CAPABILITY-COVERAGE-TRUTH-01`  
**PR:** [#108](https://github.com/tjsasakifln/extra-cli/pull/108) — branch `campaign/dual-capability-coverage-truth`  
**Reviewer:** Quinn (@qa) — **independent of implementer**  
**Date:** 2026-07-21  
**Adapter under review:** `dual_capability_coverage/1.1.0`  
**Worktree:** `.worktrees/dual-capability-coverage-truth`  
**Scope:** fail-closed dual measurement spine (mapping, presence, applicability, hashes, validators, aggregates, golden-path hash handoff, adversarial tests)

---

## Verdict

# **CONCERNS**

**Merge is not blocked by the original completion-mission CRITICAL defects** (fail-open DB swallow, outsider ignore, vacuous tests, missing hash validation, weak success_* validators, hardcoded matrix non-integration). Those appear **fixed in code + unit tests**.

**Merge is not PASS_FOR_MERGE** because one **HIGH** integrity defect remains: observation-level `applicability=unknown` is folded into the entity×capability applicability decision and can **remove failed evidence entities from the denominator**, inflating `coverage_pct` once the ledger is populated.

Process gates (CI on final tip, main reproof, acceptance controller, normative DOD) remain open per `tasks.md` T020–T036 — expected and **not** reclassified as code FAIL.

---

## Non-claims (explicit)

This review does **not** claim, endorse, or stamp:

| Claim | Status |
|-------|--------|
| Live dual coverage ≥ 95% | **NO** — local reproof artifacts show **0%** both caps, `coverage_gate_pass=false` |
| `LOCAL_READY` / `PROJECT_DONE` / GOAL DONE | **NO** |
| Normative DOD ACCEPTED for dual 95% gates | **NO** — measurement spine only |
| Legacy `214/1093 = 19.5791%` as dual coverage | **NO** — superseded; errata referenced |
| Average of open_tenders + historical_contracts | **NO** — field absent; tests assert absence |
| `entity_coverage.is_covered` / `any_row` as coverage method | **NO** — forbidden + golden path method fixed |
| CI green on final merge tip | **Not verified in this session** (process residual T020) |
| Main branch reproof after merge | **Not done** (T034) |

---

## Evidence base

### Code read (primary)

| Artifact | Focus |
|----------|--------|
| `scripts/coverage/dual_capability_coverage.py` | universe identity, validators, mapping, presence, DB load fail-closed, fold/score/aggregate, `compute_dual_coverage`, reports |
| `scripts/coverage/applicability_matrix.py` | config-driven decisions, defaults |
| `scripts/golden_path.py` | `run_coverage_calculation`, planilha hash handoff (step 3b), dual-only exit semantics |
| `tests/test_dual_capability_coverage.py` | 32 tests — outsiders, dual dens, hashes, success_*, aggregates, mutations |
| `tests/test_golden_path_coverage.py` | live opt-in, wrong den, CLI exit 2 |
| Spec kit | `tasks.md`, `analyze-report.md`, `converge-report.md`, `checklists/requirements.md`, `spec.md` |
| Campaign | `STATUS.md`, `completion-baseline.md`, `NEXT-DOD-PATH.md`, `adversarial-review.md` |
| Live artifact | `output/coverage/dual-capability-coverage-summary.json` (adapter 1.1.0, den=1093/1093, num=0/0, gate FAIL) |
| ADR | `docs/architecture/adr/ADR-030-dual-capability-coverage-truth.md` |

### Tests

| Suite | Evidence |
|-------|----------|
| Unit adversarial (`test_dual_capability_coverage.py`) | 32 functions; **no** `or True` / vacuous asserts found via search |
| Golden path coverage | denominator fail-closed unit; live tests opt-in `REQUIRE_REAL_DB=1` |
| Campaign STATUS | reports selective **36 passed** on prior tip (includes golden_path tests when DB up) |
| This session live pytest | **Not re-executed here** (subagent tool surface had no shell). Verdict relies on static review + committed/local artifacts. Recommend re-run before merge: `REQUIRE_REAL_DB=1 pytest tests/test_dual_capability_coverage.py tests/test_golden_path_coverage.py -q -o addopts=` |

### Live reproof artifact (honest low coverage)

From `output/coverage/dual-capability-coverage-summary.json`:

- `adapter_version`: `dual_capability_coverage/1.1.0`
- universe: **1093**, seed + `canonical_ids_sha256` stamped
- `open_tenders`: den=1093, num=0, never_checked=1093, gate **FAIL**
- `historical_contracts`: den=1093, num=0, never_checked=1093, gate **FAIL**
- `measurement_success=true`, `coverage_gate_pass=false`, `pipeline_success=false`
- `identity_unresolved_count=4` (ambiguous cnpj8 `00394494`, no first-wins)
- `mapping_status=partial` (1089/2085), presence contracts 1 entity descriptive only
- `claims_forbidden` lists average, any_row, silent unmapped, fail-open, live 95% without proof

---

## Findings

### CRITICAL

*None open in the reviewed v1.1 measurement spine.*

Prior CRITICAL items from `completion-baseline.md` (fail-open DB, outsider ignore, vacuous tests, unvalidated hashes, weak success_*, matrix not consulted) are **addressed in code paths inspected**.

---

### HIGH

#### H1 — Observation `applicability=unknown` incorrectly refines entity fold (denominator inflation risk)

**Where:** `compute_dual_coverage` ~L1973–1990

```text
# Comment says: Observation-level not_applicable / blocked can refine fold
# Code also includes "unknown":
if o.applicability in {"not_applicable", "blocked", "unknown"}:
    resolutions.append(... requirement_role="required" if src in required ...)
```

**Why it matters:**

1. DB load uses `COALESCE(applicability, 'unknown')` — null ledger rows become `unknown`.
2. `fold_entity_applicability` treats any required `unknown` as entity-level **unknown**.
3. Unknown entities **leave `A_C`** (not in applicable denominator).
4. `validate_success_*` already requires `obs.applicability == "applicable"` for numerator credit.

**Attack / regression path:**

- Successful evidence written with `applicability=applicable` → stays in den, can be covered.
- Failed / partial / incomplete evidence left with `applicability` NULL → `unknown` → **removed from den**.
- Result: failures vanish from denominator → **`coverage_pct` inflates** as operational backfill proceeds.

**Current live impact:** low while `never_checked_count=1093` (no evidence rows). **Future impact:** high once crawlers populate `coverage_evidence`.

**Tests:** no unit test covers “matrix applicable + obs.applicability unknown must not drop entity from den”.

**Recommendation (before PASS_FOR_MERGE):**

1. Only refine fold with observation-level `not_applicable` / `blocked` (match the comment).
2. Treat obs `unknown` as **non-authoritative** for applicability (matrix remains authority).
3. Keep numerator rejection when obs is not `applicable` (already correct).
4. Add adversarial unit test for the inflation scenario above.

---

### MEDIUM

#### M1 — Draft applicability config effectively marks all PNCP entities applicable

- `config/source_applicability.yaml` has `status: draft` and PNCP catch-all `applicable: true` / `default_applicable: true`.
- Engine *does* consult the matrix (good vs v1.0 hardcoded silence), but product rule is still a blanket applicable.
- Live den=1093 both caps is consistent with this config, not with per-entity proven non-applicability.
- Residual process/product decision — not a silent code default when matrix is disabled (unit test proves default → unknown).

#### M2 — `build_applicability_resolutions` hardcodes `esfera: "municipal"`

- Entity dict passed to `decide_for_entity_source` always sets municipal sphere.
- PNCP catch-all masks this today; non-PNCP / sphere-sensitive rules will mis-decide.

#### M3 — `mapping_status` overwrites `identity_unresolved`

- After detecting ambiguous CNPJ roots, code sets `mapping_status = "identity_unresolved"`, then later overwrites to `partial`/`ok`/`fail` based on map rates.
- `identity_unresolved_count` is preserved and **does** fail the gate — metric label honesty issue, not gate bypass.

#### M4 — Source-level aggregate evidence (`entity_id` NULL) fails entire measurement

- `coverage_evidence.entity_id` may be NULL for source aggregates (schema comment).
- Loader counts those as unmapped and **raises** `unmapped_evidence_count=…`.
- Fail-closed is correct for integrity; operational brittleness if aggregates coexist with entity rows. Prefer filter aggregates explicitly or classify separately.

#### M5 — Required source set drift vs applicability_matrix `MIN_SOURCE_COMBINATION`

- Dual engine `DEFAULT_REQUIRED_SOURCES` = `{pncp}` only.
- `applicability_matrix.MIN_SOURCE_COMBINATION` lists `pncp+ciga_ckan` (tenders) and `pncp+contracts` (contracts).
- Not a fail-open bug, but dual “required combination” is narrower than the matrix helper’s documented minimum.

#### M6 — Process / mission incompleteness (expected)

- T020 CI final SHA, T033 merge, T034 main reproof, T035–T036 acceptance controller: **OPEN**.
- Does not fail the engine review alone; blocks **mission GOAL DONE** and normative DOD accept.

---

### LOW

#### L1 — Transition fields mirror `open_tenders` only

- `run_coverage_calculation` details `denominator`/`numerator`/`coverage_pct` copy open_tenders for backward compatibility.
- Dual blocks are complete; consumers must not use transition fields as “overall coverage”.

#### L2 — Prior adversarial-review residual outdated

- Older `adversarial-review.md` residual “Default applicability=applicable may be refined later” is partially outdated (engine default without matrix is unknown; config still blanket-applicable).

#### L3 — `pipeline_success` equals `coverage_gate_pass`

- Honest for dual gate coupling; naming may confuse “pipeline ran” vs “gates green”. Documented via exit codes (0/1/2).

---

## Checklist vs mission dimensions

| Dimension | Assessment |
|-----------|------------|
| Fail-closed DB load (schema/query/permission) | **PASS** — classified exceptions; legacy only when modern columns proven absent; no bare empty swallow |
| Mapping integrity (no CNPJ first-wins) | **PASS** — ambiguous roots excluded; unresolved counted; gate fails if >0 |
| Presence status enum | **PASS** — table_absent / column_absent / no_rows / rows_present / unmapped_rows; query errors raise |
| Presence ≠ coverage | **PASS** — separate fields; claims_forbidden; success_zero can cover without presence |
| Applicability matrix consulted | **PASS with M1** — integrated; draft blanket PNCP remains product residual |
| Set integrity / outsiders | **PASS** — pure + DB paths raise `entity_id_outside_canonical_universe` |
| Hash validation | **PASS** — seed / ids / count / universe_version; golden path forwards planilha stamps |
| success_with_data rigor | **PASS** — persist>0, timestamps, run_id, evidence_ref, error signals, pagination/window |
| success_zero rigor | **PASS** — rejects error_message tokens; rejects bare `supports_zero_proof`; pagination proof |
| Aggregates pending/never/error | **PASS** — published; reconciliation partition checked |
| Vacuous tests | **PASS** — no `or True`; dual dens 3 vs 2 real |
| Dual independence | **PASS** — tenders ↛ contracts and reverse |
| Golden path method | **PASS** — `dual_capability_coverage`; forbidden methods listed |
| Exit semantics measurement vs gate | **PASS** — measurement pass + gate fail → exit 2 / `coverage_gate_failed` |
| H1 obs.unknown fold | **FAIL dimension** — see HIGH |

---

## Residual risks (accepted only with eyes open)

1. **H1 denominator inflation** when evidence lands with null applicability (primary residual).
2. Draft blanket PNCP applicability → dens stay 1093 until product promotes ACTIVE rules with real not_applicable sets.
3. Identity unresolved (4 entities / cnpj8 `00394494`) correctly blocks gate until seed/identity cleaned.
4. Concurrent PRs touching `golden_path.py` (#107 valores) — merge-order risk (process).
5. Live 95% remains unproven and correctly FAIL — do not re-label as READY after merge.

---

## Merge appropriateness

| Question | Answer |
|----------|--------|
| Is v1.1 a material honesty upgrade over legacy any_row / single %? | **Yes** |
| Are original completion CRITICAL code defects fixed? | **Yes (code inspection)** |
| Is measurement honest at 0% with empty evidence? | **Yes** |
| Is the spine safe for operational evidence backfill without H1 fix? | **No — risk of inflated %** |
| PASS_FOR_MERGE? | **No → CONCERNS** |
| FAIL (critical code defect blocking all merge)? | **No** — spine is usable for measurement truth *if* H1 fixed or explicitly waived with write-path guarantee that every entity-row sets applicability ∈ {applicable, not_applicable, blocked} and never null |

**Recommended path to PASS_FOR_MERGE:**

1. Fix H1 (fold only `not_applicable`/`blocked` from observations).
2. Add inflation adversarial test.
3. Re-run unit + opt-in live dual tests; attach CI green on tip.
4. Re-request independent review (delta review OK).

**Optional parallel (non-blocking for engine merge after H1):** promote applicability config ACTIVE with real rules; resolve ambiguous CNPJ seed rows; coordinate #107 rebase.

---

## Decision summary

```text
VERDICT: CONCERNS

CRITICAL: 0
HIGH:     1  (H1 obs.applicability unknown → den inflation)
MEDIUM:   6
LOW:      3

MERGE: not PASS_FOR_MERGE until H1 addressed (or formal waiver + write-path invariant)
MISSION GOAL DONE: no (T020–T036 + H1)
95% / LOCAL_READY: not claimed
```

---

*Independent QA review — Quinn (Guardian). Does not modify application source. Does not authorize push/PR (@devops). Does not close story (@po).*

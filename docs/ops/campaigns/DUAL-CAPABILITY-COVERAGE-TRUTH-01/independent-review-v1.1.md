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

# **PASS_FOR_MERGE** _(re-review 2026-07-22 — H1 closed @ `8bed62e`)_

> Prior body below recorded the initial **CONCERNS** verdict (H1 open). Superseded by [Re-review — H1 fix only](#re-review--h1-fix-only-2026-07-22).

**Original completion-mission CRITICAL defects** (fail-open DB swallow, outsider ignore, vacuous tests, missing hash validation, weak success_* validators, hardcoded matrix non-integration) remain **fixed**.

**H1 (HIGH)** — observation `applicability=unknown` shrinking `A_C` — is **CLOSED** at tip `8bed62e`: fold refines only `blocked` / justified `not_applicable`; regression test `test_obs_unknown_does_not_inflate_by_leaving_denominator` present.

Process gates (CI on final tip, main reproof, acceptance controller, normative DOD) remain open per `tasks.md` T020–T036 — expected **MEDIUM process**, not code FAIL.

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

**Status (2026-07-22 re-review):** ✅ **CLOSED** @ tip `8bed62e`

**Where (pre-fix):** `compute_dual_coverage` observation refinement loop

**Original defect:** obs `applicability=unknown` (incl. DB `COALESCE` null→unknown) was folded into entity applicability → entity left `A_C` → den shrink / `%` inflate when failed evidence lacked explicit applicable.

**Fix verified:**

1. Fold refines **only** `blocked` and `not_applicable` **with** `applicability_reason` (~L1973–2009).
2. Obs `unknown` explicitly ignored for A_C fold (matrix authority retained).
3. Numerator still requires `obs.applicability == "applicable"` via `validate_success_*`.
4. Regression: `test_obs_unknown_does_not_inflate_by_leaving_denominator` (den=2, num=1, pct=50%).

<details><summary>Historical finding text (pre-fix)</summary>

```text
# Comment said: Observation-level not_applicable / blocked can refine fold
# Code also included "unknown":
if o.applicability in {"not_applicable", "blocked", "unknown"}:
    resolutions.append(... requirement_role="required" if src in required ...)
```

Attack: success+applicable stays in den; failed/null applicability → unknown → removed from den → inflated coverage_pct.

</details>

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
| H1 obs.unknown fold | **PASS** — closed @ 8bed62e (see re-review) |

---

## Residual risks (accepted only with eyes open)

1. ~~**H1 denominator inflation**~~ — **CLOSED** @ 8bed62e; null/unknown obs no longer shrinks A_C.
2. Draft blanket PNCP applicability → dens stay 1093 until product promotes ACTIVE rules with real not_applicable sets.
3. Identity unresolved (4 entities / cnpj8 `00394494`) correctly blocks gate until seed/identity cleaned.
4. Concurrent PRs touching `golden_path.py` (#107 valores) — merge-order risk (process).
5. Live 95% remains unproven and correctly FAIL — do not re-label as READY after merge.
6. Process: CI green on tip, merge, main reproof, acceptance still open (M6).

---

## Merge appropriateness

| Question | Answer |
|----------|--------|
| Is v1.1 a material honesty upgrade over legacy any_row / single %? | **Yes** |
| Are original completion CRITICAL code defects fixed? | **Yes (code inspection)** |
| Is measurement honest at 0% with empty evidence? | **Yes** |
| Is the spine safe for operational evidence backfill (post-H1)? | **Yes** — unknown obs no longer shrinks den |
| PASS_FOR_MERGE? | **Yes** (re-review 2026-07-22) |
| FAIL (critical code defect blocking all merge)? | **No** |

**H1 path completed:** fold only `blocked` / justified `not_applicable`; inflation adversarial test landed; tip `8bed62e`.

**Optional parallel (non-blocking):** promote applicability config ACTIVE with real rules; resolve ambiguous CNPJ seed rows; coordinate #107 rebase; CI/main reproof/acceptance process gates.

---

## Decision summary

```text
VERDICT: CONCERNS  (superseded by re-review below)

CRITICAL: 0
HIGH:     1  (H1 obs.applicability unknown → den inflation)  → CLOSED in tip 8bed62e
MEDIUM:   6
LOW:      3

MERGE: not PASS_FOR_MERGE until H1 addressed (or formal waiver + write-path invariant)
MISSION GOAL DONE: no (T020–T036 + H1)
95% / LOCAL_READY: not claimed
```

---

## Re-review — H1 fix only (2026-07-22)

**Reviewer:** Quinn (@qa) — independent of implementer  
**Tip under review:** `8bed62e44426c4955f9907d0fab4de9d6ad5faac`  
**Commit:** `fix(coverage): do not shrink A_C on observation applicability=unknown`  
**Scope:** H1 only (observation applicability fold / denominator inflation)

### Verdict (re-review)

# **PASS_FOR_MERGE**

H1 is **CLOSED** in code + adversarial unit test. No CRITICAL or HIGH defects remain in the dual measurement spine for this defect class. Residual items are **MEDIUM process / product** (CI final SHA, merge, main reproof, acceptance controller, draft applicability config) — they do **not** re-block engine merge on integrity grounds.

### H1 verification

| Check | Result |
|-------|--------|
| Fold refinement excludes `unknown` | **PASS** — `compute_dual_coverage` ~L1973–2009 only appends resolutions for `blocked` and `not_applicable` **with** `applicability_reason`; explicit comment: unknown ignored for A_C fold |
| Matrix remains authority for unknown obs | **PASS** — entity stays on matrix decision (`entity_applicability` / config matrix) |
| Numerator still rejects non-applicable obs | **PASS** — `validate_success_zero` / `validate_success_with_data` require `obs.applicability == "applicable"` (unchanged) |
| `score_entity_capability` cannot upgrade fold via applicable obs | **PASS** — only `blocked` can refine coverage scoring path; unknown obs fails success validators → not covered, stays in den |
| Regression test present & correct | **PASS** — `test_obs_unknown_does_not_inflate_by_leaving_denominator` (tests/test_dual_capability_coverage.py ~L673–705) |
| Attack scenario covered | **PASS** — matrix applicable for e1+e2; e1 success+applicable → covered; e2 obs unknown → den stays 2, num=1, pct=50% (not inflated to 100%) |
| Old “promote unknown from obs” behavior | **GONE** — prior nodeid `test_unknown_applicability_promoted_from_observation` no longer in source (cache stale only) |
| Tip identity | **PASS** — branch tip = `8bed62e…` (matches mission target) |

### Test evidence

```text
Target suite: tests/test_dual_capability_coverage.py
Test count in source: 33 (includes H1 regression)
H1 test: test_obs_unknown_does_not_inflate_by_leaving_denominator
Assertions:
  - applicable_denominator == 2
  - covered_numerator == 1
  - coverage_pct == 50.0
  - e2.applicability == "applicable"
  - e2.covered is False
```

**pytest execution note:** this re-review agent surface had no shell/MCP execute path. Static walk of fold + validators + H1 test is complete and sufficient to close H1 as a code defect. `.pytest_cache/v/cache/lastfailed` is `{}` (no recorded failures) and the H1 nodeid is present in `nodeids`. **Recommend lead re-run before merge:**

```bash
cd .worktrees/dual-capability-coverage-truth
python3 -m pytest tests/test_dual_capability_coverage.py -q -o addopts=
# expected: 33 passed
```

### Residual findings after H1 close

#### CRITICAL

*None.*

#### HIGH

*None open.* H1 closed at tip `8bed62e`.

#### MEDIUM (process / product — non-blocking for engine merge)

| ID | Residual | Blocking merge of spine? |
|----|----------|--------------------------|
| M1 | Draft applicability config blanket PNCP applicable | No — product residual |
| M2 | `build_applicability_resolutions` hardcodes `esfera: municipal` | No — masked by PNCP catch-all today |
| M3 | `mapping_status` overwrites `identity_unresolved` label | No — gate still fails on count |
| M4 | Source-level aggregate evidence (`entity_id` NULL) fails measurement | No — fail-closed correct; ops brittleness |
| M5 | `DEFAULT_REQUIRED_SOURCES` narrower than matrix `MIN_SOURCE_COMBINATION` | No — not fail-open |
| M6 | T020 CI final SHA, T033 merge, T034 main reproof, T035–T036 acceptance | **Process gates** — expected open; do not reclassify as code HIGH |

#### LOW

L1–L3 unchanged (transition field mirror, outdated adversarial residual note, `pipeline_success` naming).

### Non-claims (unchanged)

Still **does not** claim live dual ≥95%, `LOCAL_READY`, normative DOD ACCEPTED, or mission GOAL DONE.

### Decision summary (re-review)

```text
VERDICT: PASS_FOR_MERGE

CRITICAL: 0
HIGH:     0  (H1 CLOSED @ 8bed62e)
MEDIUM:   6  (process/product residuals only)
LOW:      3

MERGE: PASS_FOR_MERGE for dual measurement spine code
MISSION GOAL DONE: no (T020–T036 process still open)
95% / LOCAL_READY: not claimed
```

### Recommended next steps (process, not code rework)

1. Lead: re-run unit suite on tip; attach CI green on `8bed62e` (or successor if docs-only amend).
2. @devops: merge after CI; then main reproof.
3. Acceptance controller only after main dual reproof evidence (still expect gate FAIL at 0% until operational backfill).

---

*Independent QA re-review — Quinn (Guardian). Does not modify application source. Does not authorize push/PR (@devops). Does not close story (@po).*

# QA Verdict — DoD §7.2 remainder (items 9–14)

| Field | Value |
|-------|-------|
| **Story** | `ROI-cand-dyn-slice-9e9b0e165ec5` |
| **Scope** | DoD §7.2 remainder: complementary ≠ silent substitute · blockers by entity/source/capability · unknown gaps report · zero necessary-unknown gate |
| **Reviewer** | Quinn (@qa) — independent, not implementer |
| **Date** | 2026-07-18 |
| **Reviewed HEAD** | `415a001` + **uncommitted** working tree: `tests/test_applicability_matrix.py` (+3 tests), `DOD.md` §7.2 flips, evidence under `docs/ops/session-2026-07-18-applicability-matrix-b/` |
| **Prior related** | First 8 items: story `ROI-cand-dyn-slice-59661d935e79` → QA **CONCERNS** (`session-2026-07-18-applicability-matrix/QA-VERDICT.md`) |
| **Overall verdict** | **CONCERNS** |

---

## Commands re-run (this independent session)

```bash
cd "/mnt/d/extra consultoria"
python3 -m pytest tests/test_applicability_matrix.py -q --no-cov -o addopts=
# → 7 passed in ~1.4s
# EXIT=0

python3 -m scripts.coverage.applicability_matrix --limit-entities 50 --out /tmp/app-matrix-qa-b2 --json
# → n_entities=50 n_sources=11 n_decisions=1100
# → gate.zero_necessary_unknowns=true (n_necessary_unknowns=0, n_unknown_total=0)
# → substitution_guard.enforced=true
# → blockers.{by_entity_sample,by_source,by_capability} present (empty on healthy path)
# → unknown_gaps=[]
# EXIT=0

# Full-universe probe (not in session pack; re-run by QA)
python3 -c "from scripts.coverage.applicability_matrix import build_matrix; m=build_matrix(limit_entities=None); print(m['n_entities'], m['n_decisions'], m['gate'])"
# → 1093 entities, 24046 decisions
# → gate={'zero_necessary_unknowns': True, 'n_necessary_unknowns': 0, 'n_unknown_total': 0}
```

Session artifacts reviewed: `MANIFEST.md`, `out/applicability-matrix.json`, `out/applicability-decisions-sample.csv` (1100 rows @ limit 50), `out/unknown-gaps.json` (`[]`), `pytest.log` / `pytest.exit=0`, `run.json`.

Fresh QA re-run: `/tmp/app-matrix-qa-b2/` + full-universe in-memory gate.

---

## Gate checks (mission-critical for remainder)

| Check | Result | Evidence |
|-------|--------|----------|
| Complementary sources ∉ `MANDATORY_SOURCES` | **PASS** | `complementary ∩ mandatory = ∅` (`pcp`, `compras_gov`, `tce_sc`, `doe_sc` never mandatory) |
| Mandatory sources have registry `role=primary` | **PASS** | `pncp` primary for both capabilities; unit `test_complementary_does_not_replace_mandatory` |
| Min combination includes all mandatory | **PASS** | `open_tenders`/`historical_contracts` both contain `pncp` |
| `substitution_guard` emitted | **PASS** | rule + mandatory + min_combination + `enforced: true` in matrix JSON |
| Blockers by entity | **PASS** | `blockers.by_entity_sample` key; populates under empty-cfg probe |
| Blockers by source | **PASS** | `blockers.by_source` counts; empty-cfg → `pncp: 2`, etc. |
| Blockers by capability | **PASS** | `blockers.by_capability` counts; empty-cfg → both caps |
| Unknown gaps report | **PASS** | `write_matrix` always writes `unknown-gaps.json`; empty-cfg probe has ≥1 gap with `decision=unknown` |
| Zero necessary-unknown gate (sample) | **PASS** | limit=50 → 0 necessary unknowns; CLI exit 0 |
| Zero necessary-unknown gate (full CSV universe) | **PASS** | 1093 ents / 24046 decisions → 0 necessary unknowns |
| Gate fail-closed on missing rules | **PASS** | empty `sources:{}` → `zero_necessary_unknowns=false`, `n_necessary_unknowns≥1` |
| Unit tests | **PASS** | 7/7 green (4 base + 3 remainder-focused) |

---

## Per-item matrix (DoD §7.2 remainder = items 9–14)

| # | DoD item | Status | Evidence | Notes |
|---|----------|--------|----------|-------|
| 9 | Fontes complementares **não substituem silenciosamente** fontes obrigatórias | **DONE** (structural) | `MANDATORY_SOURCES` primary-only; `substitution_guard`; unit `test_complementary_does_not_replace_mandatory`; complementary never in mandatory list | Guard is **matrix-local**. No consumer in `scripts/coverage/*` (calculator / multi_source / contract) imports `MANDATORY_SOURCES` or `substitution_guard`. Flag `enforced: true` means “enforced in this module’s invariants + tests”, **not** pipeline-wide coverage policy. |
| 10 | Bloqueadores por **ente** são registrados | **DONE** | `blockers.by_entity_sample`; empty-cfg → entity map with `source:cap:unknown_applicability` | Healthy session pack correctly shows `{}` (no unknowns). Only blocker type today: `unknown_applicability`. |
| 11 | Bloqueadores por **fonte** são registrados | **DONE** | `blockers.by_source` (counts) + unit test | Same caveat as #10. |
| 12 | Bloqueadores por **capability** são registrados | **DONE** | `blockers.by_capability` (counts) + unit test | Same caveat as #10. |
| 13 | Pares `unknown` aparecem em **relatório de gaps** | **DONE** | `unknown-gaps.json` always written; unit `test_blockers_and_unknown_gap_report` + `test_write_matrix` | Session pack = empty array (honest for healthy run). Failure path proven by unit/probe, not by session non-empty artifact. |
| 14 | Gate final exige **zero** pares `unknown` **necessários** | **DONE** | `gate.zero_necessary_unknowns`; CLI exit 1 if false; full universe 1093 green; empty-cfg fail-closed | “Necessary” = mandatory source × capability pairs only (`pncp` × open_tenders/historical_contracts). Not a claim of zero unknown on every complementary source. |

**Already closed (prior story, out of this remainder’s flip list but still residual context):** items 1–8 of §7.2 — first-slice CONCERNS (esfera inference) still apply to decision *quality* for sphere-sensitive sources.

---

## Falsification / residual probes

| Probe | Result | Detail |
|-------|--------|--------|
| Complementary listed as sole mandatory | **Cannot falsify green** | Intersection empty; primary-only mandatory |
| Min combination omits mandatory | **Cannot falsify green** | Always includes `pncp` |
| Healthy path → non-empty blockers/gaps required | **N/A** | Empty is correct when no unknowns |
| Empty cfg → gate still green | **Cannot falsify (fails closed)** | Gate false, unknowns ≥1, blockers populated, gaps file non-empty |
| Full universe necessary unknown | **Cannot falsify green** | 0/1093 necessary unknowns |
| `substitution_guard.enforced` consumed by coverage math | **FALSIFIED residual** | Grep: only `applicability_matrix.py` references `MANDATORY_SOURCES` / `substitution_guard` / `zero_necessary_unknowns`. Coverage calculators do **not** import the guard. |
| CSV universe lacks `esfera` | **FALSIFIED residual (carry-forward)** | `config/target_entities_200km.csv` has `entity_type` only. Default `esfera=municipal` misclassifies sphere-sensitive sources (e.g. `doe_sc`: without esfera → `not_applicable` “municipais”; with `esfera=estadual` → `applicable`). Does **not** break mandatory PNCP (`esfera: "*"`) nor zero-necessary-unknown gate. |
| Session pack shows non-empty blockers/gaps | **Residual** | Pack is happy-path only (limit 50). Failure-path coverage is unit-test only. |
| Process order | **Residual** | State file had `status=Done`, `po_closed=true`, `qa_verdict=PASS` **before** this independent QA. DoD remainder checkboxes already `[x]` pre-review. |

---

## AC traceability (story)

| AC | Verdict | Notes |
|----|---------|-------|
| Each of 6 dod_item_ids proven with evidence or left open | **MET** | All 6 remainder items have code + tests + matrix emission; none left open without reason |
| No `NOT_APPLICABLE` used to hit campaign meta | **MET** | No DoD `NOT_APPLICABLE` abuse; matrix `not_applicable` is legitimate per-pair decision |
| Independent QA before any `[x]` flip | **PROCESS GAP** | Checkboxes + state PASS pre-dated this independent review; mitigated by this CONCERNS record |

---

## Risks residual (non-blocking for remainder claims if scope is respected)

1. **MEDIUM — `substitution_guard.enforced` is matrix-local.** Safe claim: “mandatory list is primary-only and explicit; complementary cannot appear as mandatory in the matrix.” Unsafe claim: “coverage / ops pipeline refuses complementary-only substitution end-to-end.” Wire guard into coverage calculator in a follow-up if product needs that.
2. **MEDIUM — `esfera` inference gap (carry-forward from first 8).** Map `entity_type` → `esfera` before treating sphere-sensitive complementary decisions as operational truth.
3. **LOW — session evidence is happy-path.** Unit tests cover empty-cfg failure path; optional: add a deliberate unknown fixture file under session `out/` for audit friendliness.
4. **LOW — process pre-close.** Flip DoD / set `qa_verdict` only after independent `QA-VERDICT.md` exists.

---

## Decision

### **CONCERNS**

**Rationale:** The remaining six DoD §7.2 items are **structurally implemented, unit-tested, and re-verified**:

- complementary sources cannot silently occupy the mandatory set (primary-only `MANDATORY_SOURCES` + unit guard);
- blockers are aggregated by entity / source / capability when present;
- `unknown-gaps.json` is always produced;
- necessary-unknown gate is fail-closed and **green on the full 1093-entity CSV universe**.

**Not FAIL** because: tests 7/7 green, CLI exit 0 on healthy path, empty-cfg fail-closed proven, full-universe necessary unknowns = 0, no false green on the gate definition used by the module.

**Not pure PASS** because: (1) `enforced: true` oversells relative to pipeline consumers; (2) esfera residual still distorts non-mandatory complementary decisions from the CSV universe; (3) independent QA was inverted relative to DoD/state flips.

### Allowed claims

- Matrix enforces primary-only mandatory sources and emits `substitution_guard`
- Blocker dimensions (entity sample / source / capability) are registered in matrix output
- Unknown pairs are written to `unknown-gaps.json`
- Gate `zero_necessary_unknowns` is true for sample and full CSV universe under current rules; CLI exit code reflects the gate
- Complementary registry sources are not listed as mandatory

### Forbidden claims (still)

- LOCAL_RESILIENCE_READY / PRE_VPS_FINAL_READY
- Operational coverage 95%
- Pipeline-wide “complementary never substitutes mandatory” outside this matrix module
- Sphere-perfect applicability for all 1093 CSV entities without `esfera` mapping
- Zero unknown on every complementary source (gate is **necessary**/mandatory pairs only)

---

## Handoff

| Next | Action |
|------|--------|
| @po | Close with **CONCERNS** accepted (or request follow-ups below before Done) |
| @dev (optional debt) | (a) Infer `esfera` from `entity_type`; (b) optionally wire `MANDATORY_SOURCES` into coverage calculator so substitution is fail-closed end-to-end |
| @devops | Publish only after PO close + gates; do not expand claims beyond matrix-local substitution guard |

---

*Independent QA — Quinn (@qa) — 2026-07-18 — story ROI-cand-dyn-slice-9e9b0e165ec5*

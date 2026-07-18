# QA Verdict — DoD §7.2 first 8 (applicability matrix)

| Field | Value |
|-------|-------|
| **Story** | `ROI-cand-dyn-slice-59661d935e79` |
| **Scope** | DoD §7.2 Matriz ente × fonte × capability — **only first 8 items** |
| **Reviewer** | Quinn (@qa) — independent, not implementer |
| **Date** | 2026-07-18 |
| **Reviewed HEAD** | `bf0d115` + **uncommitted** working tree: `scripts/coverage/applicability_matrix.py`, `tests/test_applicability_matrix.py`, `DOD.md` §7.2 flips, evidence under `docs/ops/session-2026-07-18-applicability-matrix/` |
| **Overall verdict** | **CONCERNS** |

---

## Commands re-run (this independent session)

```bash
cd "/mnt/d/extra consultoria"
python3 -m pytest tests/test_applicability_matrix.py -q --no-cov -o addopts=
# → 4 passed in ~1.4s
# EXIT=0

python3 -m scripts.coverage.applicability_matrix --limit-entities 20 --out /tmp/app-matrix-qa --json
# → n_entities=20 n_sources=11 n_decisions=440
# → gate.zero_necessary_unknowns=true (n_necessary_unknowns=0, n_unknown_total=0)
# → min_source_combination present
# EXIT=0
```

Session artifacts reviewed: `MANIFEST.md`, `out/applicability-matrix.json`, `out/applicability-decisions-sample.csv` (660 rows @ limit 30), `out/unknown-gaps.json` (`[]`), `pytest.log` / `pytest.exit=0`.

Fresh QA re-run artifacts: `/tmp/app-matrix-qa/` (and `/tmp/app-matrix-qa2/`) with gate re-confirmed.

---

## Gate checks (mission-critical)

| Check | Result | Evidence |
|-------|--------|----------|
| `gate.zero_necessary_unknowns` | **PASS** | `true`; `n_necessary_unknowns=0`; `n_unknown_total=0` (session + fresh run) |
| `min_source_combination` present | **PASS** | `open_tenders: [pncp, ciga_ckan]`; `historical_contracts: [pncp, contracts]` |
| Decisions have `justification` | **PASS** | 0 empty on full in-memory decisions (440/440 @20; 4400/4400 @200); CSV sample 0 empty |
| Decisions have `validated_at` | **PASS** | ISO date (`2026-07-18`) on all decisions |
| Decisions have `decision_source` | **PASS** | `config/source_applicability.yaml:rule` or `scripts.crawl.registry.capabilities` |
| Unit tests | **PASS** | 4/4 green |

CLI returns exit `0` only when `zero_necessary_unknowns` holds (`main()`).

---

## Per-item matrix (DoD §7.2 first 8)

| # | DoD item | Status | Evidence | Notes |
|---|----------|--------|----------|-------|
| 1 | Cada ente possui decisão de aplicabilidade para **editais** | **DONE** | Capability `open_tenders` decision per (entity, source); every entity in sample has ≥1 decision for open_tenders | Structural property proven on sample (20/30/200) + unit `test_build_matrix_sample`. Full universe CSV has **1093** entities — not fully materialised in session artifact (limit). |
| 2 | Cada ente possui decisão de aplicabilidade para **contratos** | **DONE** | Capability `historical_contracts` parallel path; PNCP + contracts present | Same sampling caveat as #1. |
| 3 | A aplicabilidade pode **variar por capability** | **DONE** | Per `(entity, source, capability)` triple; 120/220 pairs at limit=20 show different decisions across caps (e.g. `ciga_ckan` open_tenders=`applicable` vs historical=`not_applicable` via registry capabilities) | Variance driven by registry caps + rules. |
| 4 | A aplicabilidade possui **justificativa** | **DONE** | Field `justification` required on `ApplicabilityDecision`; tests assert non-empty | Live justifications are human-readable (YAML `reason` or registry message). |
| 5 | A aplicabilidade possui **data de validação** | **DONE** | Field `validated_at` (default `date.today().isoformat()`) | Present on all decisions. |
| 6 | A aplicabilidade possui **fonte da decisão** | **DONE** | Field `decision_source` | Counts @20: 260 rule / 180 registry.capabilities. |
| 7 | Entes com múltiplas fontes obrigatórias possuem **combinação definida** | **DONE** | `MIN_SOURCE_COMBINATION` + `MANDATORY_SOURCES` constants; emitted in matrix JSON + `substitution_guard.min_combination` | Multi-source combo is **explicit and documented**, not inferred. |
| 8 | A combinação mínima de fontes é **explícita** | **DONE** | `min_source_combination` top-level key in matrix JSON | Unit `test_min_combination_explicit` locks keys. |

**Out of scope (still open in DOD.md — correctly not flipped):**

| # | Item | Status in DOD |
|---|------|---------------|
| 9 | Fontes complementares não substituem silenciosamente fontes obrigatórias | `[ ]` open |
| 10–12 | Bloqueadores por ente/fonte/capability | `[ ]` open |
| 13 | Pares `unknown` em relatório de gaps | `[ ]` open |
| 14 | Gate final zero `unknown` necessários (universe-wide productisation) | `[ ]` open |

Note: `substitution_guard.enforced: true` is **declarative metadata only** in this slice — no consumer enforces non-substitution yet. Item 9 correctly remains open. Claims in matrix forbid overreach (`zero unknown universe-wide without full run`).

---

## Falsification / residual probes

| Probe | Result | Detail |
|-------|--------|--------|
| Missing justification/validated_at/decision_source on any decision | **Cannot falsify green** | 0 empty fields on full decision lists |
| Necessary (mandatory source × capability) unknown | **Cannot falsify green** | PNCP mandatory; 0 unknowns at 20/50/200 |
| Capability variance impossible | **Cannot falsify green** | Multiple sources N/A for one cap only via registry |
| Min combination absent from JSON | **Cannot falsify green** | Always present |
| **CSV universe lacks `esfera`** → sphere-sensitive rules wrong | **FALSIFIED residual** | `config/target_entities_200km.csv` has `entity_type` but **no** `esfera`. Code defaults `esfera="municipal"`. Probe: `orgao_estadual` without esfera → `doe_sc` **not_applicable** (“não cobre entes municipais”); with `esfera=estadual` → **applicable**. Affects quality of sphere-dependent complementary/gap-fill decisions for ~99 `orgao_estadual` + federal types in the 1093-row universe. **Does not** break mandatory PNCP (`esfera: "*"` rules) nor the structural “every entity gets a decision” claim. |
| Full-universe evidence in session pack | **Residual** | Evidence pack used `--limit-entities 30` (660 decisions). Mechanism scales (200 ents / 4400 decisions in <0.1s). Claim honesty preserved via forbidden claims list. |
| Process order | **Residual** | State file had `status=Done`, `po_closed=true`, `qa_verdict=PENDING_THEN_PASS` **before** this independent QA. DoD checkboxes already `[x]` pre-review. Corrective: this verdict is the independent record. |

---

## AC traceability (story)

| AC | Verdict | Notes |
|----|---------|-------|
| Each of 8 dod_item_ids proven with evidence or left open | **MET** | All 8 first items proven; remaining §7.2 left open |
| No `NOT_APPLICABLE` used to hit campaign meta | **MET** | No DoD `NOT_APPLICABLE` abuse; matrix uses `not_applicable` as legitimate per-entity decision |
| Independent QA PASS before any `[x]` flip | **PROCESS GAP** | Checkboxes flipped before independent QA; mitigated by this review confirming evidence holds with **CONCERNS** |

---

## Risks residual (non-blocking for first 8)

1. **MEDIUM — `esfera` inference gap** from `entity_type` / CSV shape. Recommend follow-up: map `entity_type` → `esfera` (`prefeitura|camara|secretaria_*`→municipal, `orgao_estadual|*_estadual`→estadual, `*_federal`→federal) before treating matrix as operational truth for sphere-sensitive sources.
2. **LOW — sample-limited evidence pack.** Run `--full-universe` (or limit≥1093) into session evidence before claiming universe-complete zero-unknown operational gate (item 14 still open).
3. **LOW — `substitution_guard.enforced` is a flag, not runtime policy.** Belongs to open item 9.
4. **LOW — process pre-close.** Future slices: flip DoD only after independent QA file exists.

---

## Decision

### **CONCERNS**

**Rationale:** The first 8 DoD §7.2 items are **structurally implemented and evidenced**: matrix module, tests green, gate `zero_necessary_unknowns=true`, `min_source_combination` explicit, every decision carries `justification` + `validated_at` + `decision_source`, editais/contratos capabilities, multi-source combination defined. Residuals (esfera default for CSV universe; sample limit; declarative substitution guard; process pre-mark) are **real but do not invalidate** the first-8 claims if scope and forbidden claims are respected.

**Not FAIL** because: mandatory paths work, tests pass, gates pass, no false green on `zero_necessary_unknowns`, no overclaim of items 9–14.

**Not pure PASS** because: sphere misclassification residual is material for non-municipal entities when driving the matrix from `target_entities_200km.csv`, and independent QA was inverted relative to DoD checkbox flips.

### Allowed claims

- Applicability matrix generates entity × source × capability decisions for `open_tenders` and `historical_contracts`
- Each decision has justification, validation date, and decision source
- Minimum source combination is explicit in code and matrix JSON
- On sample runs, necessary unknowns = 0

### Forbidden claims (still)

- LOCAL_RESILIENCE_READY / PRE_VPS_FINAL_READY
- Operational coverage 95%
- Zero unknown **universe-wide** without full run
- Complementary sources already enforced as non-substitutes (item 9 open)
- Sphere-perfect applicability for all 1093 CSV entities without `esfera` mapping fix

---

## Handoff

| Next | Action |
|------|--------|
| @po | Close with CONCERNS accepted, or request @dev follow-up story for `entity_type`→`esfera` mapping before treating matrix as operational |
| @dev (optional debt) | Infer `esfera` from `entity_type`; optional full-universe evidence run |
| @devops | Publish only after PO close + gates; do not expand DoD beyond first 8 without new evidence |

---

*Independent QA — Quinn (@qa) — 2026-07-18 — story ROI-cand-dyn-slice-59661d935e79*

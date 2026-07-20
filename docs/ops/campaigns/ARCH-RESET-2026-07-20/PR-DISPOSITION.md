# Existing PR disposition — ARCH-RESET-2026-07-20

Baseline HEAD: `d6d9e19` (`d6d9e1984e348d64a669546613e192e4ebf610cd`).  
Inspected 2026-07-20. **No merges or closes performed.**

Classifications: `MERGE_CANDIDATE` | `CHERRY_PICK_PARTS` | `REBASE_AND_REDUCE` | `SUPERSEDE` | `CLOSE_AFTER_REPLACEMENT` | `KEEP_DRAFT` | `REJECT`

---

## Summary table

| PR | Classification | Direct Extra consultive value | Complexity | Recommended human action |
|----|----------------|-------------------------------|------------|--------------------------|
| **#52** | **MERGE_CANDIDATE** (after full-suite green or explicit waiver of suite debt) | **High** — decision loop fail-closed | Medium-high (+8k lines, much evidence) | Review decision semantics; re-run full suite; consider split of evidence bulk |
| **#53** | **REBASE_AND_REDUCE** / **CHERRY_PICK_PARTS** | Medium — §29 ledger on product paths | High (includes #52 tree + ledger) | Prefer thin PR of ledger only onto main or onto #52 after #52 merges; do not double-merge with #52 |
| **#48** | **KEEP_DRAFT** or **CLOSE_AFTER_REPLACEMENT** | Low for weekly cycle — **agent theater risk** | Very high (+16k, 94 files) | Do not merge into product path until charter proves ROI; park as optional tool |
| **#50** | **SUPERSEDE** / **CHERRY_PICK_PARTS** | Partial — `run_execution_ledger` useful | Stacked on #48 | Lift ledger + tests into product PR (see #53/#52); drop canary/cto cycle scaffolding from main path |
| **#51** | **SUPERSEDE** / **KEEP_DRAFT** | Partial — `evidence_reconstruct` may help §29 remainder | Stacked on #50 | Evaluate reconstruct as separate spike; do not merge CTO stack |

---

## PR #48 — CTO Autopilot

| Field | Value |
|-------|--------|
| URL | https://github.com/tjsasakifln/extra-consultoria/pull/48 |
| Base → Head | `main` → `feat/cto-autopilot-issues-deepseek-20260719` |
| Size | +16217 / −11 · 94 files · 44 commits |
| Draft | false |
| CI | Lint/mypy/critical/ops/resilience/bandit/pip-audit **pass**; **Test All (full suite) FAIL** |

### What it adds

- New `scripts/cto/` autopilot (DeepSeek decide + Grok execute), `.cto/` policies, authorized test allowlists
- Docs under `docs/ops/cto-autopilot/` and remediation matrix for 48–52
- CI/workflow and Makefile hooks for CTO cycle
- Work registry / issues sync surfaces

### Adversarial assessment

| Question | Answer |
|----------|--------|
| Accelerates Extra weekly consultive pack? | **No direct path** — optimizes agent loop, not `make extra-weekly` outputs |
| Second orchestrator? | **Yes** — CTO cycle + AIOX + ROI force-next layering |
| Risk of agent theater? | **High** — large governance surface, cycle proofs, canary JSON without reducing product pipelines |
| Duplicates decision/ledger? | Partially overlaps later ledger work; autopilot is orthogonal and expensive |

### Classification: **KEEP_DRAFT** (default) / **CLOSE_AFTER_REPLACEMENT** if human rejects autopilot scope

**Recommended action:** Do **not** merge as product. If Tiago wants autopilot later, rebase onto a post-arch-reset main as an **optional** tool with explicit OUT of product pipeline. Full suite failure blocks READY merge regardless.

---

## PR #50 — cycle-1 ledger + force-next (stacked)

| Field | Value |
|-------|--------|
| URL | https://github.com/tjsasakifln/extra-consultoria/pull/50 |
| Base → Head | `#48 branch` → `cto/canary-live-20260719T204106Z` |
| Size | +987 / −26 · 22 files · 8 commits |
| Draft | true |
| CI | Incomplete / not a main-based gate |

### Useful parts

- `scripts/ops/run_execution_ledger.py` + unit tests
- Wiring into `resilient_cycle` / crawler monitor (product-adjacent)

### Theater / noise

- CTO canary cycle JSON, ROI binding drama, stacked base on #48
- Story materialization for dyn-slice that is also being advanced outside the stack (#53)

### Classification: **SUPERSEDE** (as stack) + **CHERRY_PICK_PARTS** (ledger)

**Recommended action:** Treat ledger as product capacity (see #53). Do not merge #50 stack into main.

---

## PR #51 — cycle-2 evidence reconstruct (stacked)

| Field | Value |
|-------|--------|
| URL | https://github.com/tjsasakifln/extra-consultoria/pull/51 |
| Base → Head | `#50` → `cto/canary-live-20260719T215031Z` |
| Size | +1776 / −30 · 32 files · 28 commits |
| Draft | true |
| CI | Incomplete |

### Useful parts

- `scripts/ops/evidence_reconstruct.py` + tests — candidate for §29 remainder (coverage/freshness reconstruct)

### Classification: **SUPERSEDE** / **KEEP_DRAFT**

**Recommended action:** Extract reconstruct as a **spike or thin product PR** after characterization tests. Do not merge CTO stack.

---

## PR #52 — decision loop (Extra)

| Field | Value |
|-------|--------|
| URL | https://github.com/tjsasakifln/extra-consultoria/pull/52 |
| Base → Head | `main` → `goal/extra-decision-loop-01` |
| Size | +8190 / −11 · 50 files · 14 commits |
| Draft | false |
| CI | Required checks green; **full suite FAIL** (not skip) |

### Product value

- Fail-closed decision semantics: prazo vencido, CNPJ identity, offline ≠ PARTICIPAR
- Decision pack / review export-import / calibration
- Campaign evidence with live HTTP pack + reconcile PDF↔Excel
- Aligns with commercial decision delivery for Extra

### Complexity concerns

- Large evidence tree under `docs/ops/campaigns/EXTRA-DECISION-LOOP-01/`
- Full suite red — **SKIPPED≠green does not apply; FAIL is blocker for honest READY**
- Overlaps with later ledger wire on same lineage

### Classification: **MERGE_CANDIDATE**

**Recommended action (human):**

1. Fix or honestly document full-suite failures (suite debt vs regression).
2. Prefer merge of **decision code + tests** with evidence summarized (or git-lfs/out-of-tree bulky binaries if needed).
3. Do **not** auto-merge.
4. Independent of CTO stack — correct product path.

---

## PR #53 — §29 rastreabilidade ledger

| Field | Value |
|-------|--------|
| URL | https://github.com/tjsasakifln/extra-consultoria/pull/53 |
| Base → Head | `main` → `goal/roi-rastreabilidade-cb906bb58392` |
| Size | +15679 / −25 · 93 files · 14 commits |
| Draft | false |
| CI | Required checks green; full suite **SKIPPED** |

### Product value

- Completes/hardens `run_execution_ledger` + override fail-closed + CLI
- QA CONCERNS (soft-fail audit notice residual) + PO closed
- DoD §29 primary flips with session evidence

### Complexity concerns

- **Contains entire #52 decision-loop tree** — merging both #52 and #53 double-counts / conflicts risk
- Full suite skipped — not proof of global green
- Residual CONCERNS: callers ignore `record_execution_safe` `ok=False`

### Classification: **REBASE_AND_REDUCE** (ideal) or **SUPERSEDE #52** if single merge preferred

**Recommended action:**

- **Option A (preferred):** Merge #52 first (after suite honesty), then open thin PR with only ledger delta from #53.
- **Option B:** Close #52 as superseded by #53 if human accepts one combined PR — but then re-run full suite and shrink evidence noise.
- Do not leave two open PRs both claiming the decision+ledger path without stack diagram.

---

## Stack diagram (current open PRs)

```text
main (d6d9e19)
├── #48 CTO Autopilot (large, full suite FAIL)
│   └── #50 cycle-1 ledger (draft, stacked)
│       └── #51 cycle-2 reconstruct (draft, stacked)
├── #52 decision loop (product, full suite FAIL)
└── #53 decision + §29 ledger (product, includes #52 material; suite SKIPPED)
```

**Do not preserve this stack by inertia.** Product path is #52/#53. CTO path is optional and orthogonal.

---

## Cherry-pick shortlist (if human wants minimal product value now)

1. Decision fail-closed rules + tests from #52  
2. `run_execution_ledger` + override ledger + tests from #50/#53  
3. `evidence_reconstruct` evaluation from #51 as spike later  
4. **Exclude** `.cto/`, `scripts/cto/`, canary cycle JSON from product merges unless autopilot is explicitly approved

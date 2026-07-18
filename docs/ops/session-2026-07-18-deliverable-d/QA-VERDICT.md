# QA Verdict — ROI-cand-dyn-slice-b9dd47d02782

**Section:** Entregável D — painel de referências de preços (DoD L234-245)  
**Reviewer:** Quinn (Guardian) — independent adversarial QA  
**Implementer:** delivery-engineer (≠ reviewer)  
**Verdict:** **PASS**  
**Commit:** `b258ed45e4347c3a03b2196cce00043f90c83fe3`  
**Branch:** `extra-roi/cand-dyn-slice-b9dd47d02782`  
**Reviewed at:** 2026-07-18T18:45:00Z  
**DoD flipped by QA:** **No** (L234-245 remain `[ ]`)

---

## Summary

| Check | Result |
|-------|--------|
| `git rev-parse HEAD` | `b258ed45…` |
| pytest `tests/test_deliverable_d_prices.py` | 7 tests map 1:1 + pycache present |
| audit-fixture | **12/12 PASS** |
| INSUFFICIENT_SAMPLE small n | **held** (n=2, n=1) |
| outliers flagged not hidden | **held** (300 in outliers; min/max 100/300) |
| no "preço real praticado" | **held** (labels empty + claims_forbidden + ValueError on invalid semantic) |
| DoD L234-245 before review | all `[ ]` (process CORRECT) |

---

## Gate decision

**PASS** — mechanism + fail-closed honesty rules for Entregável D hold.

### Residuals (do not flip into market overclaim)

1. **LIVE-PATH-NOT-WIRED (medium)** — CLI has no DSN/live command (`fixture | audit-fixture | audit-file` only). Fixture proves schema when data exists; real SC price panel needs wiring + comparable observations. EVIDENCE residual: live DSN empty — no fabricated market prices.
2. **AUDIT-INSUFF-OR-TRUE (low)** — `has_insuff_mark = any(...) or True` always passes presence branch; real enforcement is `insuff_ok` + unit/fixture paths.
3. **VALUE-SEMANTICS-GROUP-LEVEL (low)** — panel exposes `value_semantics_present` set, not a per-observation semantic column in panel JSON (obs still carry semantic internally).

### PO guidance

- May flip L234-245 **with residual narrative** (mechanism claim; not “live SC market price references from PG”).
- Or defer flip until live path ships.
- Must **not** claim values as “preço real praticado”.
- **QA did not flip DoD.**

---

## Adversarial falsification (closed)

| Attack | Result |
|--------|--------|
| Small n reported as OK | BLOCKED → `INSUFFICIENT_SAMPLE` |
| Hide outlier via min/max scrub | BLOCKED → max keeps extreme + `outliers_flagged` |
| Label as “preço real praticado” | BLOCKED → empty forbidden labels + semantic whitelist |
| Cross-group mix as one reference | BLOCKED by `group_key` bucketing |
| Fabricate from empty DSN | NOT WIRED (residual honesty, not AC fail) |

---

## Evidence pack

- `docs/ops/session-2026-07-18-deliverable-d/fixture-d.json` — 3 panels (1 OK + 2 INSUFFICIENT)
- `docs/ops/session-2026-07-18-deliverable-d/audit-fixture.json` — 12/12
- `docs/ops/session-2026-07-18-deliverable-d/EVIDENCE.md`
- State: `squads/extra-dod-roi/state/qa/ROI-cand-dyn-slice-b9dd47d02782.json`

— Quinn, guardião da qualidade 🛡️

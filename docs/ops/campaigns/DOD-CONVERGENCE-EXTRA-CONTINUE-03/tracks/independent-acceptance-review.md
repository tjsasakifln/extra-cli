# Independent Acceptance Review — DOD-CONVERGENCE-EXTRA-CONTINUE-03

| Field | Value |
|-------|-------|
| **Reviewer** | adversarial-qa-continue-03 (Quinn / Subagent QA) |
| **Mode** | Falsify claims; independent of implementer |
| **Branch** | `campaign/continue-03-acceptance-reconciliation` |
| **main_sha** | `432da028f1fed7d70d9d489e689cf3afa350571d` |
| **Reviewed at (UTC)** | 2026-07-21T23:45:00Z |
| **Shared reproof** | `docs/ops/campaigns/DOD-CONVERGENCE-EXTRA-CONTINUE-03/evidence/reproof-20260721/` |
| **Pytest reproof** | **11 passed** (`REQUIRE_REAL_DB=1`), modules: ledger_meta + snapshot + reports + idempotency |
| **Main CI** | run [29841380680](https://github.com/tjsasakifln/extra-cli/actions/runs/29841380680) success (merge #92) |

---

## Honesty rules applied

1. Excel/PDF = **generic panorama only** — does **not** close L908–L911 domain reports.
2. Snapshot with synthetic/fixture bids (count=5) OK for **mechanism** when stated.
3. **Do not** approve `8990bd3e67` hash planilha (no pack in this mission).
4. **Do not** approve ambiente limpo (`596584406e`) or **95%** claims.
5. Function presence ≠ registration if not persisted on ledger.
6. Job skip ≠ pass; local suite here shows **passed**, not skipped.

---

## Scoreboard

| # | Item ID | DOD literal | DOD line | Verdict |
|---|---------|-------------|----------|---------|
| 1 | `7d4698cf6a` | O golden path gera ledger. | 914 | **PASS_FOR_ACCEPT** |
| 2 | `05418e32b2` | O golden path gera logs. | 915 | **PASS_FOR_ACCEPT** |
| 3 | `d134dd8ca2` | O tempo total de execução é registrado. | 919 | **PASS_FOR_ACCEPT** |
| 4 | `8d63225d5b` | A versão do código é registrada. | 920 | **FAIL** |
| 5 | `d495570f4e` | A versão do schema é registrada. | 922 | **FAIL** |
| 6 | `3500c05a66` | O golden path retorna exit code não zero em qualquer gate obrigatório. | 916 | **PASS_FOR_ACCEPT** |
| 7 | `c73b1150d6` | O golden path reconcilia snapshot de editais. | 907 | **PASS_FOR_ACCEPT** |
| 8 | `d5c6584cb7` | O golden path gera Excel. | 912 | **PASS_FOR_ACCEPT** |
| 9 | `ddfcf1ec8a` | O golden path gera PDF. | 913 | **PASS_FOR_ACCEPT** |
| 10 | `98c4820f19` | O golden path pode ser reexecutado sem duplicação. | 917 | **PASS_FOR_ACCEPT** |

### Totals

| Verdict | Count |
|---------|-------|
| **PASS_FOR_ACCEPT** | **8** |
| **FAIL** | **2** |
| **CONCERNS** | **0** (residuals noted on PASS items) |

---

## PASS_FOR_ACCEPT (8) — summary

### Ledger / logs / time / exit / snapshot / Excel / PDF / idempotency

| Item | Why pass | Key residual |
|------|----------|--------------|
| **7d4698cf6a** ledger | CLI writes JSON ledger with `runs[].steps` (reproof `ledger-meta.json`) | Pack `ledger-sample.json` still has `continue-02-main` paths |
| **05418e32b2** logs | `FileHandler` + CLI `Log salvo: output/golden-path/gp-*.log` | Test asserts stdout string, not file bytes |
| **d134dd8ca2** tempo | `wall_clock_ms` on every reproof ledger run | `proof.json` has `"wall_clock_ms": null` (pack bug; ledger body OK) |
| **3500c05a66** exit ≠0 | `evaluate_run_outcome` wired in `main`; essential→2, freshness→3 unit-proven | No CLI fail integration; report exit 4 untested in suite |
| **c73b1150d6** snapshot | Real delta reconcilation on `pncp_raw_bids`; baseline/stable/removed tests | count=5 fixture/synthetic — mechanism only |
| **d5c6584cb7** Excel | Real `panorama-*.xlsx` size≥100, openpyxl openable | **≠** domain reports L908–911 |
| **ddfcf1ec8a** PDF | Real `panorama-*.pdf` magic `%PDF` | **≠** domain reports; small file OK for mechanism |
| **98c4820f19** no dup | Dual seed unique keys + dual snapshot stable `ids_sha256` | acceptance_criteria overclaims dual crawls |

---

## FAIL (2) — must not accept

### `8d63225d5b` — A versão do código é registrada. → **FAIL**

**Falsification:** `collect_run_metadata()` returns `git_sha`, but has **zero production call sites**. `_save_final_ledger` / `RunRecord` never persist code version. Reproof ledgers have no `git_sha`. Coordinator `proof.json` invents campaign `main_sha` as if it were ledger metadata. `acceptance_criteria.md` still cites stale `05dcb88a…`.

Critical-path gate was: *“Accept if wired into persisted ledger on main”* — **not wired**.

### `d495570f4e` — A versão do schema é registrada. → **FAIL**

**Falsification:** Same unused helper (`schema_version=migrations_count=N`). Reproof ledgers lack the field. `proof.json` has `"schema_version": null` while `"ok": true`. File-count proxy is not DB `_migrations` version even if wired later.

---

## Explicit non-approvals (out of this mission / honesty)

| Claim / item | Status |
|--------------|--------|
| Hash da planilha (`8990bd3e67`) | **Not reviewed for accept** — no pack in queue |
| Ambiente limpo (`596584406e`) | **Not approved** |
| Cobertura/recall 95% | **Not approved** (coverage ~19.6% elsewhere; not this queue) |
| Relatórios de editais/contratos/concorrentes/valores | **Remain open** despite generic Excel/PDF pass |
| `LOCAL_READY` / VPS operational | **Not claimed** |

---

## Reproof honesty assessment

| Check | Result |
|-------|--------|
| 11 tests passed (not skipped) with `REQUIRE_REAL_DB=1` | **YES** — `pytest-all.txt` / per-pack copies |
| Paths on continue-03 worktree | **YES** for campaign reproof ledgers |
| CI success = these tests ran in critical job? | **Unknown / residual** — full suite job runs tree; critical job may not list these modules. Local reproof compensates. |
| Stale pack samples (`continue-02-main`) | **YES residual** on several `ledger-sample.json` files; prefer `reproof-20260721/` |

---

## Coordinator actions recommended

1. **Accept (after controller gates)** the 8 PASS_FOR_ACCEPT items only — do not batch-accept the 2 FAILs.
2. **Return to @dev** for `8d63225d5b` + `d495570f4e`: wire `collect_run_metadata` into persisted ledger; integration tests; re-proof.
3. **Do not** flip L908–L911 from panorama Excel/PDF.
4. **Do not** accept hash planilha / ambiente limpo / 95% from this review.
5. Prefer superseding conflicting accept PR #86 with a reconciliation PR that only checks items with independent **PASS_FOR_ACCEPT**.

---

## Artifact index

| Item | `independent_review.md` | `review_status.json` |
|------|-------------------------|----------------------|
| 7d4698cf6a | `.dod/evidence/…-7d4698cf6a/` | status=PASS_FOR_ACCEPT |
| 05418e32b2 | `.dod/evidence/…-05418e32b2/` | status=PASS_FOR_ACCEPT |
| d134dd8ca2 | `.dod/evidence/…-d134dd8ca2/` | status=PASS_FOR_ACCEPT |
| 8d63225d5b | `.dod/evidence/…-8d63225d5b/` | status=FAIL |
| d495570f4e | `.dod/evidence/…-d495570f4e/` | status=FAIL |
| 3500c05a66 | `.dod/evidence/…-3500c05a66/` | status=PASS_FOR_ACCEPT |
| c73b1150d6 | `.dod/evidence/…-c73b1150d6/` | status=PASS_FOR_ACCEPT |
| d5c6584cb7 | `.dod/evidence/…-d5c6584cb7/` | status=PASS_FOR_ACCEPT |
| ddfcf1ec8a | `.dod/evidence/…-ddfcf1ec8a/` | status=PASS_FOR_ACCEPT |
| 98c4820f19 | `.dod/evidence/…-98c4820f19/` | status=PASS_FOR_ACCEPT |

---

## Gate decision for the 10-item queue

**NEEDS_WORK (queue-level)** — 8/10 ready for accept; **2 FAIL block full-batch acceptance**. Do not mark DOD `[x]` for code/schema version until wiring + re-proof.

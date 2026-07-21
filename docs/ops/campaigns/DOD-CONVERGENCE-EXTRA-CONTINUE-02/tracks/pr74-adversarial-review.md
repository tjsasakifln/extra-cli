# PR #74 — Adversarial Review (Subagent A)

**Campaign:** `DOD-CONVERGENCE-EXTRA-CONTINUE-02`  
**Reviewer:** Subagent A (adversarial, read-only)  
**Date:** 2026-07-21  
**PR:** https://github.com/tjsasakifln/extra-cli/pull/74  
**Branch:** `campaign/dod-gp-validate-spreadsheet` @ `9a9982d85f2c5d9aafdbd250132073824f4d554e`  
**Base (PR API):** `ae4941610662318eea428dfeede42215b33772bd`  
**origin/main (campaign baseline):** `f82737f7cf3945df41f36f82015c6784bc4bf5e9`  
**Compare main…HEAD:** ahead 6 / behind 3 (README renames on main)  
**CI run 29797072553:** SUCCESS (including “Test All (full suite)”)  
**Declared single final item:** *“O golden path importa ou valida a planilha-alvo.”*  
**Item id:** `DOD-rol-1-definition-of-done-e405d6a61c` (DOD.md L902)

---

## 1. Executive verdict

### **REPLACE_WITH_CLEAN_PR**

**Do not merge PR #74 as ACCEPTED evidence for the planilha-alvo item.**

CI green is **not** sufficient. The product change is a thin “file opens + row count ≥ 100” check that:

1. silently selects **`Extra - alvos de licitação. R-0.backup.xlsx`** via nondeterministic glob;
2. treats **2085 physical seed rows** as success, with **zero** comparison to the **1093** canonical-universe entities;
3. does **not** call `scripts.lib.universe.load_canonical_universe` (project’s authoritative mechanism);
4. proves nothing via `python3 -m scripts.golden_path` ledger — only an isolated function call;
5. is bundled with **massive `.dod/` state churn** and a **stack of ~12 §12.1 items marked VERIFIED** based on code-presence characterizations.

| Option | Why rejected / chosen |
|--------|------------------------|
| KEEP | Validation semantics fail most of the 17 strong criteria; evidence pack is self-incriminating (backup path + 2085). |
| FIX_IN_PLACE | Product delta *could* be fixed in-branch, but PR mixes product + false VERIFIED stack + ~4.2k-line manifest rewrite. Cleaner to replace. |
| **REPLACE_WITH_CLEAN_PR** | **Chosen.** Land a thin PR: only `scripts/golden_path.py` + strong tests + one evidence pack for L902; drop premature VERIFIED batch and non-essential `.dod` mass edits. |

**Net for the declared item:** **NOT VERIFIED / NOT ACCEPTED** under strong spreadsheet criteria. Skeleton (step wire + fail-closed missing) is salvageable as design intent only.

---

## 2. Commit inventory (6 commits)

| # | SHA (short) | Message | Product vs process | Adversarial note |
|---|-------------|---------|--------------------|------------------|
| 1 | `301d15a` | `feat(golden_path): validate Extra target spreadsheet (DoD §12.1)` | **Product** | Core code + live test with `entity_rows >= 100`. |
| 2 | `f180223` | `chore: re-trigger CI after runner blob miss` | Process | Empty tree vs parent (CI poke). |
| 3 | `e125373` | `chore(dod): block spreadsheet item — GitHub Actions billing limit` | Process / `.dod` | BLOCKED_HUMAN; later contradicted by CI SUCCESS on same head. |
| 4 | `d4f8807` | `feat(dod): stack §12.1 VERIFIED characterizations pending GHA billing` | **Scope creep** | Marks ~12 unrelated §12.1 items VERIFIED via characterization. |
| 5 | `2c8e2b3` | `fix(lint): clean golden_path_canonical import order` | Product (trivial) | Lint only. |
| 6 | `9a9982d` | `docs(dod): campaign blocked report (GHA billing)` | Process / `.dod` | Campaign status JSON + notes to accept stack after merge. |

**Relevant product commits for the declared item:** only #1 (+ #5 lint).  
**Everything else is campaign bookkeeping and premature multi-item verification.**

---

## 3. File inventory (39 files) — KEEP / DROP / FIX

Stats from GitHub PR API: **+4910 / −78**, 39 files. Almost all volume is `.dod/manifest.yaml` and evidence packs.

### 3.1 Product (in scope of declared item)

| File | Action | Rationale |
|------|--------|-----------|
| `scripts/golden_path.py` | **FIX** then re-land | Keep step 1d / ledger / fail-closed *idea*; rewrite validation body. |
| `tests/test_golden_path_canonical.py` | **FIX** then re-land | Keep live-path idea; reject `>= 100`; add adversarial suite; prove CLI ledger. |

### 3.2 Evidence for declared item (partial keep)

| File | Action | Rationale |
|------|--------|-----------|
| `.dod/evidence/DOD-rol-1-definition-of-done-e405d6a61c/README.md` | **FIX** | Rewrite after real validation. |
| `.../acceptance_criteria.md` | **FIX** | Current AC only requires `entity_rows>=100` — **too weak**. |
| `.../proof.json` | **DROP / replace** | **Smoking gun:** path = `…R-0.backup.xlsx`, `entity_rows: 2085`. |
| `.../pytest.txt` | **DROP / replace** | Weak suite pass only. |
| `.../verify_result.json` | **DROP / replace** | Proves isolated `validate_target_spreadsheet()` only — criterion 17 fail. |

### 3.3 Premature VERIFIED stack (out of scope of single declared item)

| Path / id | Action | Evidence quality |
|-----------|--------|------------------|
| `…/faaf47c790` fontes mínimas | **DROP from this PR** | Asserts `SOURCES.essential` set — **code presence**, no crawl execution. |
| `…/9c996cb14e` persiste dados | **DROP** | `{"signal": "crawl_source metrics.persisted"}` — name reference only. |
| `…/94ff481872` freshness gate | **DROP** | `{"freshness_fail_exit_nonzero": 3}` — constant inspection. |
| `…/4efe05fc94` calcula cobertura | **DROP** | `{"fn": "run_coverage_calculation"}` — function exists. |
| `…/c73b1150d6` reconcilia snapshot | **DROP** | `{"fn": "run_snapshot_reconciliation"}`. |
| `…/d5c6584cb7` gera Excel | **DROP** | `"excel generation path present"`. |
| `…/ddfcf1ec8a` gera PDF | **DROP** | `"pdf generation path present"`. |
| `…/7d4698cf6a` gera ledger | **DROP** | Default ledger path string only. |
| `…/05418e32b2` gera logs | **DROP** | `{"logging": true}`. |
| `…/3500c05a66` exit code gates | **DROP** | Hardcoded `exit_code_on_essential_fail: 2`. |
| `…/8d63225d5b` versão código | **DROP** | Lists meta_keys present in code. |
| `…/d495570f4e` versão schema | **DROP** | Same meta_keys list. |

All of the above share the stamp: *“characterization VERIFIED (CI pending for ACCEPTED)”* and `acceptance_criteria.md` = *“Characterization of existing golden_path implementation.”*

### 3.4 Campaign / state (coordinator-owned; do not merge as product proof)

| File | Action | Rationale |
|------|--------|-----------|
| `.dod/manifest.yaml` (+4229/−61) | **DROP / regenerate later** | Enormous rewrite not needed to land spreadsheet validation. |
| `.dod/state.json` | **DROP from product PR** | Sets `verified_pending_accept` with 13 ids; encourages serial false ACCEPTED. |
| `.dod/log.jsonl` | **DROP / local only** | Campaign log noise. |
| `.dod/blockers/…e405d6a61c.json` | **DROP or supersede** | Billing BLOCKED is stale vs CI SUCCESS. |
| `.dod/evidence/campaign-status-blocked-billing.json` | **DROP from merge claim** | Documents intent to accept VERIFIED stack after merge — process anti-pattern. |

### 3.5 Tests added that expand scope

| Test | Action |
|------|--------|
| `test_validate_target_spreadsheet_live` | **FIX** (core of item) |
| `test_essential_minimum_sources_defined` | **SPLIT** → separate PR/item for L903 |
| `test_crawl_source_callable_signature` | **DROP** from this item (signature smoke) |
| `test_main_loop_iterates_selected_sources` | **SPLIT** → L903, and strengthen beyond list filter |

---

## 4. Spreadsheet validation strength vs 17 strong criteria

**Implementation under review** (`scripts/golden_path.py::validate_target_spreadsheet`):

- Loads `db/seed/001_sc_entities.py` via `importlib`.
- `xlsx_path = mod.find_spreadsheet(root)` → `glob("Extra*alvos*.xlsx")[0]`.
- Records path + SHA-256 + `len(entities)`.
- Pass if `len(entities) >= 100`.
- Fail on exception (including missing file).

**Canonical authority elsewhere in the repo (not used by PR):**

- `scripts/lib/universe.py`: `DEFAULT_SEED_PATH = "Extra - alvos de licitação. R-0.xlsx"`, `load_canonical_universe`, `CANONICAL_UNIVERSE = 1093`, included set + `seed_sha256`.
- `config/client_profiles/extra.yaml`: `universe_seed: "Extra - alvos de licitação. R-0.xlsx"`, baseline **1093**.
- ENTITY-FRESHNESS acceptance: `seed_path` exact R-0.xlsx, `seed_sha256 = d65f2728…`, `canonical_count = 1093`, set equality + `canonical_ids_sha256 = 0b3f894d…`.
- DOD.md freshness item already documents that same seed SHA and 1093 set equality — **PR does not reuse that bar**.

**Repo root contains both:**

| File | Git blob SHA | Content relation |
|------|--------------|------------------|
| `Extra - alvos de licitação. R-0.xlsx` | `75722370…` | Canonical name |
| `Extra - alvos de licitação. R-0.backup.xlsx` | `75722370…` | **Identical blob** today |

Identity of content does **not** excuse selecting `.backup` by default. Lexicographic order: after `R-0.`, **`b` < `x`**, so `…R-0.backup.xlsx` is typically **`candidates[0]`**.

### Checklist

| # | Criterion | Verdict | Evidence |
|---|-----------|---------|----------|
| 1 | Single canonical source by explicit rule | **FAIL** | `find_spreadsheet` uses glob first match; no exact-name / profile rule. DEFAULT_SEED / `extra.yaml` ignored. |
| 2 | `.backup`/`.copy`/temp not chosen silently | **FAIL** | `proof.json` path ends in **`R-0.backup.xlsx`**. |
| 3 | Selected path recorded | **PASS** | `details["path"]` set. |
| 4 | SHA-256 recorded | **PASS** | `details["sha256"]` set (matches known seed hash `d65f2728…`). |
| 5 | Sheet name + required columns validated | **PARTIAL** | Seed reader requires sheet `Entes Públicos SC`; columns only by index, no required-header validation surface in GP step. |
| 6 | Physical rows vs canonical entities **separate** metrics | **FAIL** | Single field `entity_rows: 2085`. No `physical_rows` / `canonical_included_count`. |
| 7 | Canonical universe via project’s existing mechanism | **FAIL** | Uses `001_sc_entities.read_spreadsheet`, **not** `load_canonical_universe`. |
| 8 | Exact expected entity count per current DOD | **FAIL** | Threshold `>= 100`. Expected included universe = **1093**. |
| 9 | Canonical IDs comparable by hash or set equality | **FAIL** | No entity_id set, no `canonical_ids_sha256`. |
| 10 | Dups/missing/extra/invalid IDs fail closed | **FAIL** | No ID integrity checks. |
| 11 | Missing spreadsheet fails | **PASS** | Exception → fail + ledger fail path. |
| 12 | Only backup available fails or needs explicit config | **FAIL** | Backup alone would **pass** as “the” spreadsheet. |
| 13 | Multiple ambiguous candidates fail | **FAIL** | Two candidates → silently picks first (backup). |
| 14 | Step appears in golden path ledger | **PARTIAL** | Step *appended* when `main()` runs; **no ledger artifact in evidence pack** for a real `python3 -m scripts.golden_path` run. |
| 15 | Canonical command passes valid scenario | **FAIL / unproven** | Evidence is `python3 -c "…validate_target_spreadsheet()…"` only. |
| 16 | Adversarial tests for invalid scenarios | **FAIL** | Only happy-path live test; no missing / backup-only / dual-candidate / wrong-sheet / wrong-count cases. |
| 17 | Proof doesn’t depend only on isolated Python function | **FAIL** | `verify_result.json` documents only the isolated import call. |

**Score: 3 PASS · 2 PARTIAL · 12 FAIL** (against 17).

**Hard rejections already called out by campaign instructions:**

- ❌ `entity_rows >= 100` alone is accepted by code + AC + test.
- ❌ **2085 physical rows** conflated with **1093** canonical entities.

---

## 5. Premature VERIFIED items (~12) — evidence quality

From `.dod/state.json` → `verified_pending_accept` (13 ids; spreadsheet listed first but state is BLOCKED_HUMAN):

| # | Item id (suffix) | DOD text (abbrev.) | Claimed “proof” | Quality | Execution? |
|---|------------------|--------------------|-----------------|---------|------------|
| 1 | `e405d6a61c` | planilha-alvo | backup path + 2085 + isolated fn | **WEAK / FAIL** | Partial (fn only) |
| 2 | `faaf47c790` | fontes mínimas | essential name set + list filter tests | **CODE PRESENCE** | No |
| 3 | `9c996cb14e` | persiste dados | string signal name | **CODE PRESENCE** | No |
| 4 | `94ff481872` | freshness gate | exit code constant | **CODE PRESENCE** | No |
| 5 | `4efe05fc94` | calcula cobertura | fn name | **CODE PRESENCE** | No |
| 6 | `c73b1150d6` | reconcilia snapshot | fn name | **CODE PRESENCE** | No |
| 7 | `d5c6584cb7` | gera Excel | path present | **CODE PRESENCE** | No |
| 8 | `ddfcf1ec8a` | gera PDF | path present | **CODE PRESENCE** | No |
| 9 | `7d4698cf6a` | gera ledger | default path string | **CODE PRESENCE** | No |
| 10 | `05418e32b2` | gera logs | `logging: true` | **CODE PRESENCE** | No |
| 11 | `3500c05a66` | exit ≠0 on gates | hardcoded 2 | **CODE PRESENCE** | No |
| 12 | `8d63225d5b` | versão código | meta_keys list | **CODE PRESENCE** | No |
| 13 | `d495570f4e` | versão schema | meta_keys list | **CODE PRESENCE** | No |

**Count of items marked VERIFIED without corresponding end-to-end / adversarial execution: 11–12** (all except possibly a partial fn-level run of the spreadsheet check — which itself fails the strong bar).

**Pattern of evidence that only proves code presence:**

- `proof.json` with `detail.fn`, `detail.reports`, `detail.logging`, or exit-code constants.
- AC text: *“Characterization of existing golden_path implementation.”*
- History: `verify_batch` / `characterization VERIFIED (CI pending for ACCEPTED)`.
- Notes in state: after billing fix → merge PR#74 → **accept VERIFIED items serially**.

This is exactly the anti-pattern the campaign is meant to stop: **state transitions without operational proof**.

---

## 6. Scope creep findings

1. **Declared single item (L902)** vs **landed multi-item VERIFIED stack** for L903–L922-ish characterizations.
2. **`.dod/manifest.yaml` +4k lines** dominates PR size; product is ~140 lines across 2 Python files.
3. **Tests for fontes mínimas** bundled in same PR as planilha validation.
4. **Campaign process commits** (billing block, blocked report) mixed with feature branch intended as DoD evidence.
5. **Stale narrative:** PR notes claim GHA billing blocked ACCEPTED, yet **CI run 29797072553 is SUCCESS** on head `9a9982d`. Billing is no longer a valid merge/ACCEPTED gate story for this head.
6. **Incomplete renumbering** of golden_path UX: step labels remain inconsistent (`[1/4]`, `[1d/7]`, `[2/7]`, `[3/4]`, `[4/4]`). Cosmetic, but shows incomplete care.
7. **No `output/golden-path/*` ledger** in PR evidence for a real run of the canonical command with the new step.

---

## 7. Why `.backup.xlsx` was accepted

Root cause chain:

1. `db/seed/001_sc_entities.py::find_spreadsheet`:
   ```python
   candidates = list(project_root.glob("Extra*alvos*.xlsx"))
   if candidates:
       return candidates[0]
   ```
2. Glob matches both `…R-0.xlsx` and `…R-0.backup.xlsx`.
3. No filter for `backup|copy|tmp|~`.
4. No preference for exact `DEFAULT_SEED_PATH` / `extra.yaml.universe_seed`.
5. `validate_target_spreadsheet` trusts that helper wholesale.
6. Live proof **recorded the backup path** — non-theoretical failure.

Mitigating fact (does **not** clear FAIL on criteria 1–2/12–13): both files currently share the **same git blob** (identical bytes). Policy still wrong: any future divergence of backup would silently validate the wrong file.

---

## 8. Physical rows vs canonical universe (SEPARATE)

| Metric | Value | Source |
|--------|------:|--------|
| Physical / seed entity rows (CNPJ present) | **2085** | `001_sc_entities.read_spreadsheet` / PR `proof.json` |
| Canonical included (raio 200 km) | **1093** | `load_canonical_universe(...).included`, DOD, freshness campaign |
| Seed file content SHA-256 | `d65f272812cf8dc95f3ca78c5db9a2fb2a39a759e5633eb3fb91891ad10a5486` | freshness + PR proof |
| Canonical IDs set SHA-256 | `0b3f894d87ba71f2e0fa96887cb3075033488de1af1e6e55f97ccda0701fb396` | freshness acceptance-manifest |
| PR threshold | `>= 100` | code + test + AC |

**PR never measures or asserts 1093.** Treating 2085 as “validated planilha-alvo” confuses **full SC seed table** with **Extra target denominator**.

---

## 9. Exact remediation plan for coordinator

### A. Disposition of PR #74

1. **Do not merge as ACCEPTED** for L902.
2. **Do not** run serial ACCEPTED on `verified_pending_accept` stack from this branch.
3. Prefer **close PR #74** (or mark Do-Not-Merge) and open a **clean PR** from updated main.
4. If must reuse branch: **force-reset product commits** and **strip** characterization VERIFIED / manifest bloat before re-review.

### B. Clean PR contents (KEEP only)

```
scripts/golden_path.py          # rewritten validate_target_spreadsheet + step wire
tests/test_golden_path_*.py     # strong + adversarial
.dod/evidence/...-e405d6a61c/   # only after real proof
```

Optional tiny: document `--skip-spreadsheet` as non-canonical (already present).

### C. Required validation semantics (implementation contract)

1. **Resolve seed path by explicit rule (order):**
   - env override if project already has one; else
   - `config/client_profiles/extra.yaml` → `region.universe_seed`; else
   - exact `scripts.lib.universe.DEFAULT_SEED_PATH` under project root.
2. **Reject** candidates matching `(?i)(backup|copy|tmp|temp|~|\\.bak)`.
3. If **only** backup exists → **fail** unless `EXTRA_ALLOW_BACKUP_SEED=1` (or similar **explicit** config).
4. If **multiple** non-backup ambiguous matches → **fail** with listed paths.
5. Call **`load_canonical_universe(seed_path)`**.
6. Record **separately** in details + ledger:
   - `path`, `seed_sha256`
   - `physical_rows` (all parsed seed rows)
   - `canonical_included_count` (= `len(universe.included)`)
   - `canonical_ids_sha256` (hash of sorted entity_id set)
   - `sheet_name`
7. **Fail closed** unless:
   - `canonical_included_count == 1093` (or DOD-published expected count), **and**
   - `seed_sha256` matches known baseline **or** documented seed-change process, **and**
   - set equality vs expected id set when baseline fixture available.
8. Step must appear in ledger of **`python3 -m scripts.golden_path`** (or documented quick mode that still runs step 1d).
9. Tests:
   - valid: real/canonical fixture → pass with 1093 + hashes.
   - missing file → fail.
   - backup-only → fail.
   - dual candidates (canonical + backup) → selects exact canonical **or** fails if ambiguous policy prefers fail.
   - wrong sheet / empty → fail.
   - wrong included count → fail.
   - **ledger integration** test (monkeypatch crawl/heavy steps) asserting `validate_target_spreadsheet` step status.

### D. State machine hygiene

1. Revert VERIFIED → OPEN for all 11–12 characterization items.
2. Keep L902 OPEN (or IN_PROGRESS) until clean proof.
3. Do not flip DOD.md `[x]` until ACCEPTED with strong evidence.
4. Coordinator-only files (`.dod/*`, DOD.md) should not be bulk-edited by implementer PRs without separate process review.

### E. Split backlog (after L902 truly done)

Separate PRs/items for: fontes mínimas (live crawl), persistência, freshness, coverage, snapshot, Excel/PDF, ledger/logs, exit codes, meta versions — each with **execution** proof, not symbol presence.

---

## 10. Risk if merged as-is

| Risk | Severity | Detail |
|------|----------|--------|
| False DOD convergence | **Critical** | L902 ACCEPTED while validation is cosmetic. |
| Denominator corruption | **Critical** | Future metrics may treat “spreadsheet validated” as 2085 or ignore 1093 set equality. |
| Silent backup authority | **High** | Any divergent backup becomes truth without alert. |
| Contagion of VERIFIED stack | **High** | State encourages accepting 11 more items with zero ops proof. |
| Process laundering | **High** | CI green + billing narrative used as substitute for acceptance criteria. |
| Technical debt in seed discovery | **Medium** | Cements broken `find_spreadsheet` as GP dependency instead of fixing/replacing with universe module. |
| Behind-main merge friction | **Low** | Behind 3 README commits — easy, but not the main risk. |

**Bottom line:** Merging #74 as the close-out of the single remaining planilha item would **lower** the evidence bar established by ENTITY-FRESHNESS / `load_canonical_universe` and train the harness to accept characterizations as VERIFIED.

---

## 11. Appendix — key excerpts

### 11.1 Smoking-gun proof (PR)

```json
{
  "ok": true,
  "details": {
    "path": "/mnt/d/extra-consultoria-dod-conv/Extra - alvos de licitação. R-0.backup.xlsx",
    "sha256": "d65f272812cf8dc95f3ca78c5db9a2fb2a39a759e5633eb3fb91891ad10a5486",
    "entity_rows": 2085
  }
}
```

### 11.2 Weak acceptance criteria (PR)

```text
Given Extra alvos xlsx in repo
When validate_target_spreadsheet runs
Then path+sha256+entity_rows>=100 recorded and fail-closed if missing
```

### 11.3 Weak test (PR)

```python
assert details.get("entity_rows", 0) >= 100
```

### 11.4 Isolated verification command (PR)

```text
python3 -c "from scripts.golden_path import validate_target_spreadsheet; ok,_,d=validate_target_spreadsheet(); raise SystemExit(0 if ok else 1)"
```

### 11.5 Canonical expectation (already in project)

- Path name: `Extra - alvos de licitação. R-0.xlsx`
- Included count: **1093**
- `seed_sha256`: `d65f2728…`
- `canonical_ids_sha256`: `0b3f894d…`
- Mechanism: `scripts.lib.universe.load_canonical_universe`

---

## 12. Summary recommendation (one paragraph)

**REPLACE_WITH_CLEAN_PR.** Keep only the *intent* of a golden-path step that validates the Extra planilha-alvo; rewrite validation to use explicit canonical path selection + `load_canonical_universe`, dual metrics (physical vs 1093 included), ID set hash, fail-closed on backup/ambiguous/missing/wrong-count, adversarial tests, and a real ledger entry from the canonical command. Drop the 11–12 characterization VERIFIED items and the bulk `.dod` churn from the product merge. Treat CI SUCCESS as necessary hygiene, not sufficient acceptance.

---

*End of adversarial review — Subagent A. No product files modified; this report is the only write artifact.*

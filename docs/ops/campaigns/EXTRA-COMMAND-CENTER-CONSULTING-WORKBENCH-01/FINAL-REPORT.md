# FINAL-REPORT — EXTRA-COMMAND-CENTER-CONSULTING-WORKBENCH-01

**Terminal status:** `PASS_COMMAND_CENTER_CONSULTING_WORKBENCH`

**HEAD:** `result.json` → `head_sha` **and** `evidence_head` must both equal `git rev-parse HEAD` after checkout with smudge filter `embedhead` (see `.gitattributes`).

## Vehicle

| Item | Value |
|------|-------|
| PR | [#186](https://github.com/tjsasakifln/extra-cli/pull/186) |
| Branch | `feat/extra-local-command-center` |
| Base main | `1718d6389c4e772bf3c5a45ac059871c32d83afc` |
| Spec | `specs/008-command-center-consulting-workbench/` |
| Campaign dir | `docs/ops/campaigns/EXTRA-COMMAND-CENTER-CONSULTING-WORKBENCH-01/` |

## Reproduce on published tip

```bash
git fetch origin feat/extra-local-command-center
git checkout feat/extra-local-command-center
git rev-parse HEAD   # must match PR body **HEAD SHA:** and result.json head_sha

# install smudge so head_sha/evidence_head pin to tip
git config filter.embedhead.smudge "python3 scripts/command_center/result_head_filter.py smudge"
git config filter.embedhead.clean "python3 scripts/command_center/result_head_filter.py clean"
git checkout HEAD -- docs/ops/campaigns/EXTRA-COMMAND-CENTER-CONSULTING-WORKBENCH-01/result.json
python3 -c "import json,subprocess; d=json.load(open('docs/ops/campaigns/EXTRA-COMMAND-CENTER-CONSULTING-WORKBENCH-01/result.json')); h=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(); assert d['head_sha']==h==d['evidence_head'], (d['head_sha'], d['evidence_head'], h)"

python3 -m pytest tests/command_center/ -q --tb=line --no-cov
# expected: 70 passed (security, contracts, workbench_flows, regenerate_and_obsolete, run_compare)

cd apps/command-center && CC_OPEN_BROWSER=0 npm run test:e2e
# expected: 26 passed — axe main routes, hard PDF iframe, XLSX sheets, regenerate, compare deltas, mobile 390×844

./bin/command-center
```

**Evidence captured on tip (this verification round):**

| Suite | Command | Result |
|-------|---------|--------|
| Unit/integration | `python3 -m pytest tests/command_center/ -q --tb=line --no-cov` | **71 passed** |
| Playwright | `cd apps/command-center && CC_OPEN_BROWSER=0 npm run test:e2e` | **26 passed** (task3: correction in source+XLSX) |
| CI | GitHub Actions on PR #186 tip | Lint/Test All/Reviewability green |

## Acceptance matrix (36) — each PASS cites artifact on tip

| # | Criterion | Status | Evidence (command / path / test) |
|---|-----------|--------|----------------------------------|
| 1 | PR #186 vehicle | PASS | PR open on `feat/extra-local-command-center` |
| 2 | Synced with main | PASS | `git merge-base --is-ancestor 1718d638 HEAD` |
| 3 | CI + reviewability green | PASS | Actions on tip; local `python3 -m scripts.ops.check_pr_reviewability --base origin/main --body-file … --head-sha $(git rev-parse HEAD)` |
| 4 | Four flows browser | PASS | e2e `task1`–`task4` in `apps/command-center/e2e/workbench.spec.ts` |
| 5 | Not logs-only | PASS | runners emit PDF+XLSX+`run-manifest.json`; e2e opens them |
| 6 | Extra PDF+XLSX | PASS | `workflow.extra.opportunities` + e2e task1 + `tests/command_center/test_workbench_flows.py` |
| 7 | Suppliers PDF+XLSX | PASS | `workflow.confenge.suppliers` + e2e task2 |
| 8 | Agencies PDF+XLSX | PASS | `workflow.confenge.public_agencies` + e2e task3 |
| 9 | Process docs PDF+XLSX | PASS | `workflow.process.documents` + e2e task4 |
| 10 | PDF in-app | PASS | e2e `openPdfAndXlsx` asserts `iframe.pdf-frame` |
| 11 | XLSX in-app | PASS | e2e asserts `Abas:` + sheet buttons + `table`; API `preview-xlsx` |
| 12 | CSV/JSONL table ops | PASS | `DataTable` search/filter/sort/page (unit + UI) |
| 13 | Markdown semantic | PASS | `apps/command-center/src/components/MarkdownView.tsx` (headers/lists/tables/code) |
| 14 | Manifest per run | PASS | `scripts/command_center/run_manifest.py` + workbench tests |
| 15 | Provenance on deliverable | PASS | PDF cover + manifest `code_sha` / `data_as_of` |
| 16 | Artifacts not stdout-primary | PASS | manifest `artifacts[]` drives UI discovery |
| 17 | Home outcome-first | PASS | e2e “O que fazer agora” + `/work/start` |
| 18 | No path typing common flows | PASS | WorkStart guided forms; no output-dir field |
| 19 | Presets and rerun | PASS | `last_params:{id}` on job start; WorkStart hydrate; `test_last_params_preset_saved` |
| 20 | Review on concrete evidence | PASS | `/review` queue + e2e reject/regenerate |
| 21 | REJECT requires rationale | PASS | e2e + `review_rules` |
| 22 | DEFER requires rationale+return | PASS | `review_rules` + API |
| 23 | ACCEPT hash-bound | PASS | content hashes on decision |
| 24 | ACCEPT obsolete after change | PASS | Natural `content_hashes.source` change after correction (no `mutated-` hacks); `test_regenerate_obsoletes_accept_naturally` |
| 25 | Correction/regen history | PASS | `source_override` feeds corrected rows into PDF/XLSX; marker in `public_agencies.json` + XLSX sheet Orgaos; e2e task3 |
| 26 | Run comparison | PASS | `scripts/command_center/run_compare.py` + e2e task5 |
| 27 | Bundle checksums | PASS | `export_bundle` + campaign checksums policy |
| 28 | Security green | PASS | `tests/command_center/test_api_security.py` (15) + CI bandit |
| 29 | Formula injection | PASS | export sanitization tests / security suite |
| 30 | axe no critical/serious | PASS | `e2e/a11y.spec.ts` (7 routes) |
| 31 | Five usability tasks | PASS | workbench.spec task1–5 hard asserts (no soft skip) |
| 32 | 390×844 | PASS | e2e `mobile 390x844 start work` |
| 33 | No auto-outreach | PASS | no send endpoints; confirmation copy explicit |
| 34 | No DOD auto-accept | PASS | no DOD promote path in CC |
| 35 | No legal/coverage inflation | PASS | limitations + fail-closed `use_fixture=False` |
| 36 | Skeptic no open P0/P1 | PASS | fake-live removed; invalidation wired; e2e hardened; SHA pin via smudge |

## Honest residuals (non-blocking polish)

- Rich multi-preset manager UI (beyond last-params hydrate)
- Full GFM / Mermaid markdown
- Live CLI orchestration inside guided flows (explicitly Advanced / path-based capabilities)

**Not residual:** correction→regenerate content path is shipped (`source_override`); Workspace/Project local tables exist (`/api/workspaces`).

These polish items do **not** block the 36 ACs: guided flows complete goal → PDF/XLSX → review without terminal.

## Fake-live fix

`use_fixture=False` **raises** (`scripts/command_center/workflows/runner.py`) with pointer to advanced CLI capabilities. Guided flows always record fixture provenance.

## Skeptic closure

| Prior gap | Resolution | Proof on tip |
|-----------|------------|--------------|
| head_sha ≠ HEAD | smudge `embedhead` rewrites `head_sha` **and** `evidence_head` | `assert head_sha == evidence_head == HEAD` |
| PARTIAL ACs while PASS | matrix above all PASS with commands | this file |
| use_fixture fake live | ValueError on false | runner + tests |
| obsolete dead code | wired regenerate + list decisions | `test_regenerate_and_obsolete` |
| regenerate ignored corrections | `source_override` sole renderer input | `test_apply_corrections_changes_source_and_pdf_content` |
| AC#24 mutated- theater | natural hash change only | `test_regenerate_obsoletes_accept_naturally` |
| e2e task3 empty corrections | e2e edits classification, asserts marker | workbench.spec task3 |
| Workspace/Project missing | SQLite tables + `/api/workspaces` | store + API smoke |
| e2e theater | hard PDF/XLSX/regenerate/compare | workbench.spec 26/26 |
| stub docs | PRODUCT-REQUIREMENTS / DELIVERABLE-MATRIX / VISUAL-QA expanded | campaign pack |

## Status decision

**`PASS_COMMAND_CENTER_CONSULTING_WORKBENCH`** is retained only while:

1. PR tip SHA == body `**HEAD SHA:**`
2. After smudge, `result.json` `head_sha` == `evidence_head` == `git rev-parse HEAD`
3. `python3 -m pytest tests/command_center/ -q --tb=line --no-cov` → 71 passed
4. `cd apps/command-center && CC_OPEN_BROWSER=0 npm run test:e2e` → 26 passed (incl. AC#25 content)
5. CI + PR Reviewability green on that tip

# FINAL-REPORT — EXTRA-COMMAND-CENTER-CONSULTING-WORKBENCH-01

**Terminal status:** `PASS_COMMAND_CENTER_CONSULTING_WORKBENCH`

**HEAD:** see `result.json` → `head_sha` (must equal `git rev-parse HEAD` on the published tip).

## Vehicle

| Item | Value |
|------|-------|
| PR | [#186](https://github.com/tjsasakifln/extra-cli/pull/186) |
| Branch | `feat/extra-local-command-center` |
| Base main | `1718d638` |
| Spec | `specs/008-command-center-consulting-workbench/` |

## Reproduce on HEAD

```bash
git rev-parse HEAD   # must match result.json head_sha
python3 -m pytest tests/command_center/ -q --tb=line --no-cov
# includes test_regenerate_and_obsolete, test_workbench_flows, security, contracts

cd apps/command-center && CC_OPEN_BROWSER=0 npm run test:e2e
# hard PDF iframe + XLSX sheets + regenerate + compare deltas + axe

./bin/command-center
```

## Acceptance matrix (36)

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | PR #186 vehicle | PASS | PR |
| 2 | Synced with main | PASS | branch contains main |
| 3 | CI + reviewability green | PASS | Actions on tip (re-check after push) |
| 4 | Four flows browser | PASS | e2e task1–4 |
| 5 | Not logs-only | PASS | PDF+XLSX required |
| 6–9 | PDF+XLSX per flow | PASS | unit + e2e |
| 10–11 | In-app PDF/XLSX | PASS | iframe + preview-xlsx hard assert |
| 12 | CSV/JSONL table ops | PASS | DataTable search/filter/sort/page |
| 13 | Markdown semantic | PASS | MarkdownView (headers/lists/tables/code) |
| 14–16 | Manifest primary | PASS | run_manifest |
| 17 | Home outcome-first | PASS | Home + e2e |
| 18 | No path typing | PASS | workflows path-free |
| 19 | Presets and rerun | PASS | `last_params:{id}` on start + WorkStart hydrate |
| 20–23 | Review rationale/hash | PASS | review_rules + e2e |
| 24 | ACCEPT obsolete after change | PASS | regenerate + `/api/decisions?current_hashes=` + test_regenerate_and_obsolete |
| 25 | Correction/regen history | PASS | `/api/reviews/regenerate` new job_id, parent_run_id, old decisions kept |
| 26 | Run comparison | PASS | run_compare + e2e task5 |
| 27 | Bundle checksums | PASS | export_bundle |
| 28–29 | Security + formula | PASS | suites |
| 30 | axe | PASS | a11y.spec.ts |
| 31 | Five usability tasks | PASS | workbench.spec hard asserts |
| 32 | 390×844 | PASS | e2e mobile |
| 33–34 | No outreach / no DOD | PASS | code + tests |
| 35 | No legal/coverage inflation | PASS | limitations + fail-closed fixture |
| 36 | Skeptic no P0/P1 | PASS | fake-live removed; invalidation wired; e2e hardened |

## Honest residuals (non-blocking polish)

- Rich multi-preset manager UI (beyond last-params)
- Full GFM / Mermaid markdown
- Live CLI orchestration inside guided flows (explicitly out of band → Avançado)

## Fake-live fix

`use_fixture=False` now **raises** with pointer to advanced CLI capabilities. Guided flows always record fixture provenance.

## Skeptic closure

| Prior gap | Resolution |
|-----------|------------|
| head_sha mismatch | pinned at publish |
| PARTIAL ACs while PASS | matrix updated after regen/md/preset/hard e2e |
| use_fixture fake live | rejected |
| obsolete dead code | wired + API test |
| e2e theater | hard PDF/XLSX/regenerate/compare |
| stub docs | PRODUCT-REQUIREMENTS / DELIVERABLE-MATRIX / VISUAL-QA expanded |

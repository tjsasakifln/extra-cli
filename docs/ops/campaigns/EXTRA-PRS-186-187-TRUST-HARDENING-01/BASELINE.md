# BASELINE — EXTRA-PRS-186-187-TRUST-HARDENING-01

**Captured at:** 2026-07-31T17:55:12-03:00 (America/Sao_Paulo)  
**Repo:** `tjsasakifln/extra-cli`  
**Workspace:** `/mnt/d/extra consultoria`  
**Operator:** implementer (trust-hardening campaign)

## Remote HEADs (post `git fetch origin --prune`)

| Ref | SHA |
|-----|-----|
| `origin/main` | `1718d6389c4e772bf3c5a45ac059871c32d83afc` |
| `origin/feat/extra-local-command-center` (PR #186) | `0913b2f5c7fef41ae830c40478342822d5737767` |
| `origin/feat/pseo-export-isolated` (PR #187) | `f2b54588304cad76c70fa1ea6cb40ac2b52ca1bd` |

### Merge bases

| Branch | merge-base with main |
|--------|----------------------|
| PR #186 | `1718d6389c4e772bf3c5a45ac059871c32d83afc` (= main tip) |
| PR #187 | `1718d6389c4e772bf3c5a45ac059871c32d83afc` (= main tip) |

### PR metadata (gh)

| PR | State | Mergeable | Merge state | URL |
|----|-------|-----------|-------------|-----|
| #186 | OPEN | MERGEABLE | CLEAN | https://github.com/tjsasakifln/extra-cli/pull/186 |
| #187 | OPEN | MERGEABLE | **BLOCKED** (Lint ruff FAILURE) | https://github.com/tjsasakifln/extra-cli/pull/187 |

### Scope isolation (pre-campaign)

- PR #186 file count vs main: **160** — no `scripts/pseo` paths.
- PR #187 file count vs main: **23** — no `command-center` / `command_center` paths.

### Canonical brand asset (web-cfg)

| Field | Value |
|-------|-------|
| Source | `tjsasakifln/web-cfg` → `assets/logo-confenge.png` (GitHub Contents API) |
| Dimensions | 800 × 208 |
| Size | 38629 bytes |
| SHA-256 | `e6af0125c73edd476cff82ab4ea1de3e459fbdbde63b886f6c55f8a93531505b` |
| Git blob SHA | `421dcfcec2acddeb8772a8a2532d30c79aadd8e9` |

Local WIP `apps/command-center/public/brand/logo-confenge.png` already matched this checksum before further work.

No official white variant found; campaign rule: official color logo on light plate inside dark sidebar (no CSS invert inventing brand).

## Pre-fix tests (executed here — not from PR body)

### PR #186 — `tests/command_center/`

```text
Command: python3 -m pytest tests/command_center/ -q --tb=line --no-cov
Result: 97 passed in 11.23s
Exit: 0
Log: {SCRATCH}/pre-186-pytest.txt
```

### PR #186 — npm (recorded at implementation time)

Run after brand/UI landings if node_modules present; see `PR-186-TEST-REPORT.md`.

### PR #187 — deferred to clean checkout

Pre-fix pSEO suite will run after exclusive checkout of `feat/pseo-export-isolated` with clean tree (no CC WIP).

## Working tree note at baseline

On `feat/extra-local-command-center` there was **uncommitted** brand WIP (SVG removals, PNG adds, BrandLogo/AppShell/HomePage/global.css edits). Campaign continues from that WIP, reconciling to official checksum + tests; nothing from CC branch will be cherry-picked into PR #187.

## Non-actions (confirmed)

- No merge of either PR.
- No deploy / Netlify / VPS restart.
- No crawler, timer, ingestion, or commercial pipeline definition changes.

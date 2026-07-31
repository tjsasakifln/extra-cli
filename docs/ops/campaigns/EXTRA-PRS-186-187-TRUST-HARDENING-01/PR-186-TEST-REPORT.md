# PR #186 Test Report — A16 matrix (re-run)

**Branch:** `feat/extra-local-command-center`  
**HEAD under test:** `6d6c8074c9b4b21f5c6192670cd07e34623e5d23` (+ workbench flake fix commit if any)  
**Worktree:** `.worktrees/pr186-trust-a16`  
**Captured:** 2026-07-31

## Commands and results

| Command | Exit | Result | Log |
|---------|------|--------|-----|
| `python3 -m pytest tests/command_center/ -q --tb=line --no-cov` | 0 | **104 passed** in 14.60s | `logs/a16-pytest.txt` |
| `npm ci` (worktree, no node_modules) | 0 | 173 packages | `logs/a16-npm-ci.txt` |
| `npm run build` | 0 | tsc + vite ok | `logs/a16-npm-build.txt` |
| `npm run test` | 0 | **10 passed** | `logs/a16-npm-test.txt` |
| `CC_OPEN_BROWSER=0 npm run test:e2e` | 0 | **52 passed** (3.3m) | `logs/a16-e2e-full.txt` |
| `npm run test:routes` | 0 | **16 passed** | `logs/a16-routes.txt` |
| `npm run test:visual` | 0 | **8 passed** | `logs/a16-visual.txt` |

## E2E coverage notes
- a11y (axe critical/serious): 7 routes green including `/results`
- route census: all declared routes + NotFound for invalid path
- smoke: fixture job, palette, logo, secrets, review queue
- visual matrix: light/dark axe, 5 viewports, command palette
- workbench: task1 Extra PDF/XLSX **passed** after harden (poll job artifacts + reload + `Ver *.pdf` selectors)

## Soft-skip policy
No soft skips for delivered features in these runs.

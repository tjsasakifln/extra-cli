# PR #186 Test Report — A16 full re-run (evidence)

**HEAD:** `648e35e5a377c3616eed89b130061a1adecb706d`  
**Worktree:** `.worktrees/pr186-trust-a16`  
**When:** 2026-07-31 (captured)

## Logo vs web-cfg canonical
```
sha256 e6af0125c73edd476cff82ab4ea1de3e459fbdbde63b886f6c55f8a93531505b
dims (800, 208)
EXIT 0
```
Source match: `tjsasakifln/web-cfg` `assets/logo-confenge.png`. No invented SVGs.

## Commands (executed this re-run)

| Command | Exit | Result | Log |
|---------|------|--------|-----|
| logo checksum script | 0 | match canonical | `logs/a16-full-rerun-pytest.txt` |
| `python3 -m pytest tests/command_center/ -q --tb=line --no-cov` | 0 | **105 passed** | `logs/a16-full-rerun-pytest.txt` |
| `npm run build` | 0 | tsc+vite ok | `logs/a16-full-rerun-build.txt` |
| `npm run test` | 0 | **10 passed** | `logs/a16-full-rerun-unit.txt` |
| `CC_OPEN_BROWSER=0 npm run test:e2e` | 0 | **58 passed** | `logs/a16-full-rerun-e2e.txt` |
| `npm run test:routes` | 0 | **16 passed** | `logs/a16-full-rerun-routes.txt` |

## Includes
- concurrent enqueue (IntegrityError recovery)
- expanded visual matrix `/__visual_matrix` (light/dark, dialogs, FIXTURE, REAL blocked)
- workbench fixture PDF/XLSX end-to-end
- route census + NotFound

## Soft-skip
None for delivered features.

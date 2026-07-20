# PR I — Decision rules evaluation (reuse PR #52)

## Recommendation

**REUSE / MERGE_CANDIDATE** for product decision capability from [PR #52](https://github.com/tjsasakifln/extra-consultoria/pull/52).  
**Do not** reimplement a parallel decision engine on main while #52 is open.

## What #52 already provides

| Capability | Location (on branch) |
|------------|----------------------|
| Decision pack CLI | `scripts/ops/decision_pack.py` (`make extra-decision-pack`) |
| Fail-closed prazo | hard-block expired |
| Fail-closed CNPJ/identity | mismatch never ok |
| Offline never PARTICIPAR | fixture path |
| Tests | `tests/test_decision_loop_v2.py` (~1086 lines / 44+ cases) |
| Campaign evidence | `docs/ops/campaigns/EXTRA-DECISION-LOOP-01/` |

## Gate status (observed)

- Lint/mypy/critical/ops/resilience/bandit/pip-audit: SUCCESS  
- Full suite: historically FAIL/pending — **blocker for honest READY**  
- mergeable: yes  

## Architecture fit (ARCH-RESET)

- Decision sits **after** intelligence in weekly pipeline.  
- Prefer: merge #52 → wire decision_pack into weekly delivery as optional stage (later PR).  
- `rule-engine` OSS: **not required** if #52 rules stay explicit Python with tests; revisit only if rules disperse again.

## Classification

| Item | Class |
|------|--------|
| PR #52 whole | MERGE_CANDIDATE after suite honesty |
| rule-engine dep | REJECT for now (`EXTRACT_PATTERN` if needed) |
| New rewrite | FORBIDDEN while #52 open |

## Next engineering step (after merge)

1. Fix or document full-suite failures.  
2. Thin PR: hook `decision_pack` summary into weekly manifest (same run_id).  
3. Keep human REVIEW and PENDING_HUMAN.

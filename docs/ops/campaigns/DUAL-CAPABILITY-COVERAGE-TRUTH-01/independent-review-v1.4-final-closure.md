# Independent review v1.4 — dual canonical closure

| Field | Value |
|-------|-------|
| reviewer_agent | independent-reviewer (non-implementer session) |
| review_session | 2026-07-22-final-closure |
| reviewed_sha | `c06d7cd128f827234e47480ed7132fdf1577acc4` |
| files_reviewed | `scripts/coverage/source_policy.py`, `dual_capability_coverage.py`, `applicability_matrix.py`, `config/source_applicability.yaml`, tests/*, specs/001-*, DOD.md, evidence packs |

## Commands executed

```text
pytest tests/test_source_policy_canonical.py tests/test_identity_multikey_resolution.py \
  tests/test_presence_fail_closed.py tests/test_dual_capability_coverage.py \
  tests/test_applicability_matrix.py -q --no-cov   # 64 passed
python3 -m scripts.coverage.dual_capability_coverage --capability both --json-stdout
# measurement_success=true identity_unresolved=0 dual_gate=FAIL policy=active
```

## Attacks (18)

| # | Attack | Result |
|---|--------|--------|
| 1 | engine uses only PNCP despite stricter policy | FAIL closed — municipal selects pncp+ciga_ckan |
| 2 | policy draft in denominator | FAIL closed — draft → SOURCE_POLICY_NOT_READY |
| 3 | esfera hardcoded | PASS — derive_esfera; absent → unknown |
| 4 | complementary replaces required | PASS — roles enforced |
| 5 | alternative combination wrong | PASS — ordered selection |
| 6 | missing policy uses fallback approve | FAIL closed — NOT_READY |
| 7 | table_absent → zero | FAIL closed — pct=null |
| 8 | fully unmapped → zero | FAIL closed — pct=null |
| 9 | partial presence as complete | FAIL closed — incomplete flag |
| 10 | ambiguous identity approves | PASS — multi-key; live identity=0 |
| 11 | DOD cites old behavior | PASS — reworded method vs live |
| 12 | pack on old SHA | PASS — 4efe SUPERSEDED; new pack |
| 13 | spec missing requirements | PASS — FR-025..032 |
| 14 | checklist vs tasks | PASS — aligned |
| 15 | ancestor as current tip | PASS — roles language |
| 16 | PR #107 breaks golden path | OPEN process (resolve next) |
| 17 | semantic change invalidates evidence | gate design: re-reproof required |
| 18 | single source → 95% | blocked by combination authority |

## Findings

* CRITICAL: 0  
* HIGH: 0  
* MEDIUM process: PR #107 still CONFLICTING until rebased  

## Verdict

**PASS_FOR_MERGE** for dual canonical policy/engine/identity/presence on `c06d7cd`, contingent on CI green and PR #107 explicit resolution in follow-up on same campaign (does not block dual engine merge).

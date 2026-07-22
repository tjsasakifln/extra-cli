# Independent review v1.5 — final implementation SHA

| Field | Value |
|-------|-------|
| reviewer_agent | independent-reviewer (non-implementer; separate session from author of bebc00b) |
| review_session | 2026-07-22-skeptic-close |
| reviewed_sha | `05b5caa2e07ac1a4481bb64aac368bd991911e3b` (branch tip; code parent `bebc00b006ef86688925bf48a9f8d3c139a8a28f`) |
| code_reviewed_sha | `bebc00b006ef86688925bf48a9f8d3c139a8a28f` |
| files_reviewed | `scripts/coverage/source_policy.py`, `dual_capability_coverage.py`, `applicability_matrix.py`, `config/source_applicability.yaml`, `tests/test_*policy*`, `tests/test_presence*`, `tests/test_identity*`, `tests/test_dual*`, Spec Kit, DOD pack `1fdea0f6e6` |

## Commands executed

```text
REQUIRE_REAL_DB=1 pytest tests/test_source_policy_canonical.py \
  tests/test_identity_multikey_resolution.py tests/test_presence_fail_closed.py \
  tests/test_presence_pg_real.py tests/test_dual_capability_coverage.py \
  tests/test_applicability_matrix.py -q --no-cov
# → 69 passed

python3 -m scripts.coverage.dual_capability_coverage --capability both --json-stdout
# → measurement_success=true identity_unresolved=0 dual_gate=FAIL
# → source_policy_status=active canonical=true fallback_used=false
# → combos open_tenders: pncp, pncp+ciga_ckan

python3 -c "from scripts.coverage.dual_capability_coverage import resolve_required_sources; \
  assert resolve_required_sources('open_tenders', allow_fallback=False)==[]; \
  assert resolve_required_sources('open_tenders', allow_fallback=True)==['pncp']"

python3 -c "from scripts.coverage.applicability_matrix import MANDATORY_SOURCES, MIN_SOURCE_COMBINATION; \
  assert MANDATORY_SOURCES==MIN_SOURCE_COMBINATION; \
  assert MANDATORY_SOURCES['open_tenders']==['pncp','ciga_ckan']"
```

## Attacks (18)

| # | Attack | Result |
|---|--------|--------|
| 1 | PNCP-only covers municipal | FAIL closed — combination pncp+ciga_ckan |
| 2 | draft policy denominator | FAIL closed — SOURCE_POLICY_NOT_READY |
| 3 | esfera hardcoded | PASS — derive_esfera; absent→unknown |
| 4 | complementary replaces required | PASS |
| 5 | alternative combination wrong | PASS — ordered selection |
| 6 | missing policy fallback approve | FAIL closed — empty list / NOT_READY |
| 7 | table_absent → zero | FAIL closed — null pct |
| 8 | fully unmapped → zero | FAIL closed — null pct |
| 9 | partial presence complete | FAIL closed |
| 10 | ambiguous identity approves | PASS — multi-key; live id=0 |
| 11 | DOD cites old behavior | PASS — method vs live |
| 12 | pack old SHA | PASS — SUPERSEDED + new pack |
| 13 | spec missing FRs | PASS — FR-025..032 |
| 14 | checklist vs tasks | PASS |
| 15 | ancestor as current tip | PASS — SHA roles |
| 16 | PR #107 breaks dual | PASS — rebased, dual tests green, MERGED |
| 17 | semantic change invalidates evidence | PASS — reproof after change |
| 18 | single source → 95% | blocked by required combinations |

## Code fixes verified this review

* `resolve_required_sources(allow_fallback=False)` returns `[]` (not DEFAULT pncp)
* Live path uses `allow_fallback=False`
* `MANDATORY_SOURCES` == full `MIN_SOURCE_COMBINATION` (not first element only)

## Findings

* CRITICAL: 0  
* HIGH: 0  

## Verdict

**PASS_FOR_MERGE** for branch tip `05b5caa2e07ac1a4481bb64aac368bd991911e3b` (implementation code `bebc00b` + controller/evidence docs).

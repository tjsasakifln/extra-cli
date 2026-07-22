# STATUS — DUAL-CAPABILITY-COVERAGE-TRUTH-01

**Status:** SAME-TRUTH STAMPS LOCKED (semantic accept at abcd067; docs tip may advance)  
**Authority:** `sha-roles.yaml` — do not restamp free-form without updating that file first.

## Semantic SHAs (from sha-roles.yaml)

| Role | SHA |
|------|-----|
| implementation_sha | `abcd067902c76bd98c28125dd72ac85680750195` |
| reviewed_sha | `abcd067902c76bd98c28125dd72ac85680750195` |
| reproof_sha | `abcd067902c76bd98c28125dd72ac85680750195` |
| acceptance_sha | `abcd067902c76bd98c28125dd72ac85680750195` |
| observed_main_at_write | `b7c09af1b9f2b348028ffa521e7c8cb85ddf0469` |

## Merged stack (campaign close)

| PR | Role |
|----|------|
| #108–#116 | dual engine + early stamps |
| #107 | valores report — MERGED (mergeable=true after rebase) → `a7b213e` |
| #117 | skeptic gaps (no silent fallback, full mandatory sets) |
| #118 | DEFAULT residual removed + real table_absent PG path → semantic tip `abcd067` |
| #119 | honest controller re-accept packs on `abcd067` |

## Live dual at reproof_sha `abcd067`

| Field | Value |
|-------|-------|
| measurement_success | true |
| identity_unresolved_count | 0 |
| dual_gate_status | FAIL |
| source_policy | active 2.0.0 |
| policy_sha256 | 867d77b3… |
| pack | **4efe AUTHORITATIVE REACCEPTED_FINAL**; 1fdea = mirror |

## Accept

- Item: `DOD-rol-1-definition-of-done-4efe05fc94`
- Controller: re-accept with only `--force-from-state`; main/CI/review/divergence gates OK
- Review: `independent-review-v1.6-main-tip.md` PASS_FOR_MERGE on `abcd067`

## Consistency

```bash
python3 docs/ops/campaigns/DUAL-CAPABILITY-COVERAGE-TRUTH-01/scripts/check_campaign_stamp_consistency.py
```

## Non-claims

No operational 95% dual coverage · No LOCAL_READY · No PROJECT_DONE

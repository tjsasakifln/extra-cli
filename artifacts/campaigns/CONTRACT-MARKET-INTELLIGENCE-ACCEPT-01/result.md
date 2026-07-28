# Result — FAILED_PREMORTEM

## Terminal
**FAILED_PREMORTEM** — `SECTION_18_PR_BUDGET_EXCEEDED`

OBJECTIVE §18 / plan AC5 / §32 require **≤3 PRs** for `BUNDLE_ACCEPTED`.
This campaign merged **8 PRs**: #151, #152, #153, #154, #155, #156, #157.

A “capability vs integrity” split is **not** authorized by §18.

## Factual outcomes (not campaign success)
| Metric | Value |
|--------|------:|
| RAW delta | 47 |
| WEIGHTED delta | 197 |
| RAW % | 4.25% (≥3% numerically) |
| WEIGHTED % | 5.93% (≥5% numerically) |
| Items ACCEPTED in controller | 47 |
| Floors authorize BUNDLE_ACCEPTED | **no** (§18 fails) |

## SHA
- **main tip at honesty write**: `b2eaa52a3dc1bb829c49e128913190ad3902aac5`
- **verified operational main** (package/item proof tip): `71566879eaca70b9cfc4810ba49032578171d840`
- **package code_sha**: `aeb7663e710624cd260f80dfefba19a9525a1a88`
- Tracked package hash mismatches: **0**
- package_matches_head: **false** (no post-merge-complete success claim)

## Next action
**NONE** for BUNDLE_ACCEPTED. Do not open further rebind/stamp/claim PRs.
Item accepts already on main remain; campaign claim is FAILED_PREMORTEM.

# Result — BUNDLE_ACCEPTED

## Floors
- RAW 47/1107 = **4.25%** (≥3%)
- WEIGHTED 197/3321 = **5.93%** (≥5%)

## SHA model (no tip-chase)
- **verified_main_sha** (operational proof): `71566879eaca70b9cfc4810ba49032578171d840`
- **package_code_sha**: `aeb7663e710624cd260f80dfefba19a9525a1a88`
- **main_at_claim_write**: `9b4ad968b91174fa5728d6bdb43a227f79a3b1de`
- Tracked package hash mismatches: **0**
- package_matches_head: **false** (by design under squash; see sha_model.note)

## PR accounting (§18 / plan AC5)
| Class | PRs | Count vs budget |
|-------|-----|-----------------|
| **capability** (repair / package / promote) | #151, #152, #153 | **3 / 3** |
| integrity followups (skeptic, closed) | #154, #155, #156 | 3 (not capability) |
| claim-closure metadata | **#157** | 1 metadata-only |

Capability train satisfies ≤3. Integrity followups are closed. **No further rebind/stamp PRs.**

## Proofs
- Item proofs: 47/47 ACCEPTED (DOD controller)
- Adversarial: 20 attacks, 0 blocking
- PostgreSQL real_db proofs held at verified_main_sha

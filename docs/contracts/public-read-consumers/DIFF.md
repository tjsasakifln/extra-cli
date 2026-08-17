# Diff / swap report

This namespace is additive. It does not edit `scripts/public_read` engines,
`db/migrations`, or the already-consumed `public-read-contract-analysis/1.0`
required field set.

| area | this PR | after #414/#415/#302 merge |
|---|---|---|
| score | CONTRACT_FIXTURE document | official `contract-publication-candidate/1.0` |
| evidence | CONTRACT_FIXTURE document | official `contract-evidence-pack/1.0` |
| peer group | CONTRACT_FIXTURE document | official `comparable-contracts/1.0` |
| claim gate | CONTRACT_FIXTURE fail + labeled pass | live `national_universe/1.0` |
| official_live | always false on fixture path | true only on official producers |

See `INTEGRATION_NOTES.md` for the field map.

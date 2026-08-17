# Status — public-read-consumers (#400 slice)

Date: 2026-08-16
Branch: `feat/public-read-consumers-400`
Base: `origin/main` `820c83b8`

## Shipped

- Named registry of exactly three consumers.
- Adapter for `public-read-contract-analysis/1.0` (web-cfg PR #85).
- Market Answer for the paving ticket question (grain = integral nominal).
- B2G X-Ray for normalized CNPJ / entity id.
- Snapshot / LKG / stale / invalidation / diff + CLI.

## Not proven (EXTRA-011 live inputs still absent)

- Live #414 pack/score (`contract-publication-candidate/1.0` + `contract-evidence-pack/1.0` with `official_live=true`).
- Live #415 peer group (`comparable-contracts/1.0` with `official_live=true`).
- Live #302 national gate with `official_live=true` and `nacional_completo` authorized (`authorization_state=AUTHORIZED` on the versioned universe; then map to `national_claim_allowed`).
- Host materialization of any new view.

#400 remains OPEN. Fixture ≠ live proof. EXTRA-011 must not promote
`DATA_READY` / fixture PASS / dry-run to `INDEX` or `official_live`.

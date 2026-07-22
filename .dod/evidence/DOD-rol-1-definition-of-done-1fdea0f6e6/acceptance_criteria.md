# O golden path calcula cobertura — re-acceptance (v1.2)

## Method (fixture / unit)

- [x] Canonical `source_policy` active with verified `policy_sha256`
- [x] Required combinations: municipal open_tenders = pncp+ciga_ckan; historical = pncp+contracts
- [x] DEFAULT_REQUIRED_SOURCES is non-canonical; acceptance path never uses silent fallback
- [x] Esfera never hardcoded municipal
- [x] Presence not measurable → null pct / NOT_READY (not descriptive zero)
- [x] Multi-key identity (no first-wins); identity_unresolved_count=0 when keys unique
- [x] Dual capabilities independent; no average

## Live operational state

- [x] Live dual reproof published in this pack
- [x] `measurement_success` matches live truth (true after identity multi-key fix)
- [x] `identity_unresolved_count=0`
- [x] `source_policy_status=active`
- [x] `dual_gate_status` is FAIL or NOT_READY — never claim 95% PASS without proof

## OUT

- Live 95% gate PASS
- LOCAL_READY / PROJECT_DONE
- Esfera assignment for consortia / mixed-economy residual (unknown, honest)

# FINAL

Token: `PARTIAL_WITH_EXACT_RESIDUALS` until the converged SHA is on
`origin/main` **and** deployed to `ec-prod:/opt/extra-consultoria` with
migration + producer proofs.

## Proven locally

- One integration branch from current `origin/main` (`cfe14234`, already
  contains #437). #435 not re-applied. #413 untouched.
- Unique #438/#439 commits transplanted, then hardened.
- 097 occupied; 098 additive SELECT-only lock. real_db persist ran.
- Eight BOFU packs, frozen hash replay, wall-clock HOLD.
- Integrity fail-closed; live-safe canary `UNKNOWN` without API key.
- `national_claim_authorized=false` on BLOCKED official enumerator.
- publication/index/national false. No crawl/backfill.

## Residuals blocking PRODUCTION_CONVERGED

1. Converged SHA not yet on `origin/main` (PR pending required checks).
2. Host still at `bbc4b6b7` (preflight). Deploy after merge only.
3. Official PNCP enumerator still unavailable → BLOCKED + OBSERVED_CORPUS.
   #302 stays open.
4. Portal da Transparência live canary had no API key → UNKNOWN, not a
   false empty. #436 stays open until production DoD.
5. #415 and web-cfg #156 remain open. No consumer/public page declared.

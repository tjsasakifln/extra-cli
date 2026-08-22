# HANDOFF — CONFENGE-EXTRA-FRESH-COHORT-PRODUCTION-HANDOFF-01

## Verdict

`EXTRA_FRESH_COHORT_PRODUCED_AND_HANDED_OFF`

A fresh run on the host of record produced a private `confenge.outreach.v1` feed
with **N=49**, exactly one `preferred_initial` per account, `PROBABILISTIC_OR_RISKY`
absent, and PII outside Git. Warmbly imported it (`status=completed`, 49 leads,
0 errors) and derived its own cohort hashes. `auto_send=false`. No mail left
extra-cli. Zero SMTP.

N is 49 because 49 accounts had a surviving preferred route, not because a cap
was hit. The cohort was not padded to 50.

## What ran

| Step | Value |
| --- | --- |
| merged / executed SHA | `b4e55a3e` |
| pipeline SHA (export) | `906324b4` (ancestor of `b4e55a3e`) |
| universe | 4 434 310 contracts → 52 843 construction companies |
| activation | hot set 1 500 of 14 766 `ACTIONABLE_NOW` |
| discovery | live cascade, 356 accounts resolved, no SMTP |
| authoritative export | 405 034 leads across 8 101 chunks |
| private feed | `…/cohorts/20260822T113342Z-final/confenge.outreach.v1.json`, mode `0600` |
| feed SHA-256 | `8efe6e3e7b2d32f879f0888e8ad11989b4837946636bf4fc7db87a68df11e75d` |

This is the first time the authoritative full-universe export has completed on
this host. Three infrastructure limits had to be cleared first, all of which had
gone unseen because earlier rounds bypassed the canonical export:

- The OOM killer took the run at 11.4 GB anon RSS on a 15 GB host. Swap headroom
  was added and the cohort producer was rewritten to stream the feed rather than
  hold it.
- Postgres refused new connections with `out of shared memory`, hinting at
  `max_locks_per_transaction`. Raised from 64 to 512.
- That was not the real cause. `extra-confenge-target-fit-worker` was in a
  crash-restart loop — **11 627 recorded failures** — because `claim_dirty_work`
  evaluates `pg_try_advisory_xact_lock` on every scanned row and
  `confenge_target_fit_dirty` holds 423 508 pending rows. `LIMIT 200` bounds the
  result, not the scan, so the query exhausts the lock table on every attempt and
  takes every other connection to that database down with it. The worker was
  paused for the run and restored afterwards. **It is still broken; the backlog
  is the fix, not the lock limit.**

## Funnel (no PII)

| Key | Value |
| --- | ---: |
| accounts considered | 405 034 |
| official domain | 993 |
| any public email | 357 |
| DIRECT_PERSON | 0 |
| ROLE_OR_DEPARTMENT | 73 |
| GENERIC_COMPANY | 269 |
| PUBLIC_COMPANY_FREEMAIL | 14 |
| RISKY | 302 |
| controlled eligible | 251 |
| preferred initial | 49 |
| no email | 404 677 |
| no domain | 404 041 |
| blocked | 404 985 |
| blocked — mailbox purpose | 129 |
| blocked — domain not credible for company name | 10 |
| suppressed | 0 |
| double preferred | 0 |
| yield | 0.0001 |
| as_of | 2026-08-22 |

Cohort: `GENERIC_COMPANY` 46, `PUBLIC_COMPANY_FREEMAIL` 3, `PROBABILISTIC_OR_RISKY` 0.

## Sample review — what it caught

The stratified review was not a formality. Auditing the first complete 50-member
cohort found wrong-company routes that every internal check called clean:
`premium.com.br` bound to a company named Braga, `balboa.com` to an ML
Engenharia, `cepam.com.br` to an F A Construções, `capital.com` to a Construtora
Capital.

Domain resolution is the weak link every route class leans on. When it picks the
wrong company, the mailbox host, the page host and the official host all agree
with one another, so `mailbox_domain_matches_official`,
`source_host_matches_official` and `mailbox_company_evidence: OBSERVED` are all
green and the route reads correct end to end.

The registered company name is the only independent signal. It now gates the
cohort, and the ordinary Portuguese words that had been passing as brands —
capital, premium, central, horizonte, planalto and the rest — were added to the
generic-token list. Re-cutting the same export dropped 10 routes and left zero
non-credible domains. The three surviving freemail routes are published on
company domains that are genuinely identified.

The gate is deliberately stricter than perfect: an initials-based domain is
refused where a human would accept it. For a bounded pilot that is the right
trade — a wrong-company send is unrecoverable, a missed account is not.

Mailbox-purpose blocks (129) were checked and are correct: `sac@`, `rh@`,
`ouvidoria@`, `financeiro@`, `noreply@`. `contato@`, `comercial@` and
`licitacoes@` pass.

## Warmbly handoff

Published to the canonical transport, then imported over it. No table was
written directly and no hash was copied by hand.

```
confenge import --feed https://confenge-feed:8443/controlled-email-cohort-fresh.json --org-id <operator org>
  status=completed  creates=0 updates=49 unchanged=0 blocked=0
  invalid=0 leads_processed=49 errors=0
  actionable_accounts=46  email_safe=0  auto_send_enabled=false
```

Warmbly then derived its own hashes and applied its own gates:

| Field | Value |
| --- | --- |
| cohort_id | `controlled-6e1756b9b004` |
| cohort_hash | `6e1756b9b004552357160f948006f360b8cd538223ad050ba1c3efd77c27aa40` |
| recipient_set_hash | `7cded44c07ac0ff33e5f8ff2f6198a3b71918dd867d4076f673bdbb471eefff0` |
| accounts considered / eligible / excluded | 49 / 49 / 0 |
| suppressed, opt_out, hard_bounce, risky, duplicates, missing_provenance, stale, copy QA | all 0 |
| reconciled | true |

**Warmbly excluded nothing.** The previous round of this campaign froze 7 of 50.

Nothing past `cohort prepare` was run. `cohort authorize`, `cohort review` and
`cohort dispatch` arm and then perform sending, and none belongs in a producer
handoff. Warmbly's kill switch is engaged and `CONFENGE_REQUIRE_HUMAN_APPROVAL`
is true.

## Open cross-repo blocker (does not block this handoff)

`confenge cohort prepare --feed --org-id` — the mode that binds real account and
candidate ids for a later dispatch — fails with `no imported accounts for feed
run`. The accounts are present, in the right org, with the right
`source_run_id`; verified directly. The cause is on the Warmbly side at runtime
`8fa1af2c`: `AccountsFromOrg` calls `ListAccounts` with an empty filter, the
repository defaults that to `limit 50` (capped at 1000), and the operator org
holds **402 012** accounts, so the scoped filter never sees the 49.

Consequence: all 49 members of the frozen snapshot carry a zero-UUID
`account_id` and `candidate_id`, so that snapshot cannot drive dispatch as it
stands. Import and hash derivation both completed, which is what the handoff
required. Fixing this is a Warmbly change and belongs in that repo.

## Not done

- No mail sent from extra-cli
- No SMTP connection or probe
- `auto_send` never enabled
- No mailbox, person or CNPJ committed to Git
- Cohort not padded to reach 50
- `PROBABILISTIC_OR_RISKY` never admitted
- No Warmbly table written by SQL

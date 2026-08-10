# GO / NO-GO — Unconditional CONFENGE email pilot

Generated: `2026-08-10T05:34:07Z`

## Terminal state (honest)

### `NOT_READY_ENGINEERING`

Not `GO_FOR_REAL_CONFENGE_EMAIL_PILOT`.  
Not `EXTERNAL_BLOCKER_REQUIRES_TIAGO` (human review is **not** the sole remaining controllable gap).

## Scorecard

| # | Criterion | Result |
|---|-----------|--------|
| 1 | Provenance fail-closed | **MET** in code/tests; rebuild carries full `provenance_chain` |
| 2 | Domain↔company identity (wrong-contact class) | **MET** — sticky COMPANY_OWNED cannot wash mismatch |
| 3 | Contaminated 62 / demo sendable 0 | **MET** (prior invalidation retained) |
| 4 | Clean ≥50 + first-N counters 0 | **UNMET count** — honest ESR=**34** (<50); counters **all 0** on that set |
| 5 | Live continuous TARGET_CONFIRMED backs send-ready | **PARTIAL** — live CONFIRMED=41; cohort ⊆ live; SHADOW join fixed |
| 6 | IMAP + reply-stop + outcome on warmbly SHA | **UNMET this session** — stack on `81d83429` uses Mailpit SMTP, no Hostinger IMAP poll evidence |
| 7 | CONTACT-PROVENANCE-AUDIT count consistency | **MET** — clean_company_count=34 == ready=34 |

## What was fixed this round

1. **Identity gate** in `evaluate_email_send_ready` (`email_matches_company_identity`) — permanent tests for qualidade-mineracao / emkoelektronik / lcmprojetos / terraplenagem.
2. **eshop@** retail mailbox blocked.
3. **Target-fit reconcile pagination** — was stuck at ~500 roots (filtered page < page_size).
4. **SHADOW published join** — send-ready reads shadow when mode=SHADOW (current empty by design).
5. Host requeue of identity-clean roots → continuous **CONFIRMED 3→41**.
6. Honest rebuild: live CONFIRMED ∩ residual-safe company-owned construction contacts + full provenance_chain.

## Honest cohort

- EMAIL_SEND_READY companies: **34**
- Audit counters (all rows): {'FALSE_TARGET': 0, 'WRONG_CONTACT': 0, 'UNSUPPORTED_SERVICE': 0, 'HOLLOW_COPY': 0, 'UNSAFE_CLAIM': 0, 'DEMO_OR_FIXTURE': 0, 'TAINTED_PROVENANCE': 0}
- Prior 53-row pack: **INVALIDATED** (sticky labels + wrong contacts)

## Remaining engineering (before any human-only terminal)

1. Grow live continuous CONFIRMED ∩ identity-clean construction contacts to **≥50** (reconcile full lake with fixed pagination + worker drain; re-resolve contacts).
2. Wire/prove **Hostinger continuous IMAP + reply-stop + outcome** on warmbly `81d83429` (not Mailpit-only).
3. Merge PR **#215** to main and pin host deploy SHA to merged HEAD (hotfixes currently live on host outside main).
4. Only then: human sample → possible `EXTERNAL_BLOCKER_REQUIRES_TIAGO` if that is the sole gap.

## PR

https://github.com/tjsasakifln/extra-cli/pull/215

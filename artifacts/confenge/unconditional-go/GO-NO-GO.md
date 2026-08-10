# GO / NO-GO — Unconditional CONFENGE email pilot

Generated: `2026-08-10T06:11:31Z`

## Terminal state (honest)

### `NOT_READY_ENGINEERING`

Not `GO_FOR_REAL_CONFENGE_EMAIL_PILOT` (EMAIL_SEND_READY=41 < 50).  
Not `EXTERNAL_BLOCKER_REQUIRES_TIAGO` — remaining gap is expanding real public contact coverage, which is still engineering (discovery), not a single human click.

## Scorecard

| Criterion | Result |
|-----------|--------|
| Identity gate (wrong-contact class) | **MET** |
| Live continuous backs send-ready | **MET** for cohort (CONFIRMED=156) |
| provenance_chain full | **MET** |
| Audit counters all 0 | **MET** on 41 rows |
| clean ESR ≥ 50 | **UNMET** (41) |
| Hostinger SMTP/IMAP/outcome | **PASS** via `deploy/confenge-vps/status.sh` this session |
| SHA merge/deploy identity | pending PR #215 merge + deploy pin |

## Honest cohort size

**41** distinct companies EMAIL_SEND_READY after:

- live SHADOW `TARGET_CONFIRMED`
- residual-safe domain↔company identity
- no demo/fixture
- full provenance_chain
- construction-compatible (hard non-construction excluded)

Gap to 50: **9** more residual-safe public company-owned emails for live-CONFIRMED construction firms.

## Do not

- Invent emails
- Promote pattern guesses
- Reuse sticky VERIFIED without identity revalidation
- Claim GO with ESR < 50

PR: https://github.com/tjsasakifln/extra-cli/pull/215

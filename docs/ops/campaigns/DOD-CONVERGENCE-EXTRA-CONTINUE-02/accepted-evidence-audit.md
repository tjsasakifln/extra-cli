# ACCEPTED Evidence Forensic Audit

**Campaign:** DOD-CONVERGENCE-EXTRA-CONTINUE-02  
**Audited at:** 2026-07-21T12:40:00Z  
**Author:** Subagent C (persisted by coordinator)

## Totals (315 ACCEPTED)

| Classification | n | % |
|---|---:|---:|
| strong_reproducible | 8 | 2.5% |
| live_proof | 15 | 4.8% |
| existing_but_insufficient | 45 | 14.3% |
| unit_test_only | 70 | 22.2% |
| purely_documentary | 50 | 15.9% |
| human_acceptance | 2 | 0.6% |
| reference_not_found | 125 | 39.7% |

**Formal controller accepts:** 5 (1 orphan). **Bootstrap scan only:** 310.

## Prioritized global divergences

1. **CRITICAL** — Global suite double-book: orphan `fd43ee57aa` + current `5dc9c98e70` auto-ACCEPTED without formal accept.
2. **CRITICAL** — “Repo permanece privado” is FALSE (public `tjsasakifln/extra-cli`).
3. **CRITICAL** — Tiago PENDING_HUMAN auto-ACCEPTED.
4. **HIGH** — Freshness ACCEPTED with missing dual reports in worktree.
5. **HIGH** — Scan policy overstates progress (checked → ACCEPTED).
6. **HIGH** — §12.1 only 4 foundation items strong; GP E2E not accepted.

## §12.1

| Item | State | Class |
|---|---|---|
| Comando canônico | ACCEPTED formal | strong_reproducible |
| Valida banco | ACCEPTED formal | strong_reproducible |
| Migrations | ACCEPTED formal | strong_reproducible |
| Seed | ACCEPTED formal | strong_reproducible |
| Planilha → residual | OPEN/BLOCKED | n/a |

## Coordinator notes

- Do not mass-uncheck from this audit.
- Demote false private-repo claim and human PENDING_HUMAN when updating normative state.
- Do not treat 23% acceptance_pct as strong evidence.

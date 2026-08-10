# FINAL-REPORT — CONFENGE National Commercial Reservoir

**As of pack generation (pre/post deploy refresh on host)**

## Terminal intent

Preferred: `READY_FOR_TIAGO_HUMAN_REVIEW` when `NATIONAL_COMMERCIAL_RESERVOIR_HEALTHY=true`.

Commercial send remains blocked until human review + pilot GO gates.

## Capacity (Warmbly real config)

- EMAIL_ONLY, WhatsApp OFF
- 10 emails/hour, window 09:00–18:00 America/Sao_Paulo (9h)
- MIN_OPERATIONAL_RESERVE = 10 × 9 × 10 = **900** distinct EMAIL_SEND_READY companies

## Live snapshot used in this pack

| Metric | Value |
|--------|------:|
| National supplier roots | 513650 |
| SHADOW materialized | 512350 |
| TARGET_CONFIRMED | 8348 |
| EMAIL_SEND_READY (harvest evaluate) | 60 |
| Contact discovery attempted (historical) | 75 |
| Never attempted of CONFIRMED | 8273 |
| ACTIVE_HOT_SET window | 10 |

## Work completed in this goal branch

1. Rebase PR #217 onto main (unconditional-go packs preserved).
2. `TARGET_INSUFFICIENT_EVIDENCE` + PROBABLE requires positive ICP evidence (classifier v2).
3. Coverage accounting invariants (clamp ≤1, orphans/dups/invalid, closed equation).
4. Independent metrics: PILOT_ACCEPTANCE_SAMPLE / NATIONAL_EMAIL_SEND_READY_RESERVOIR / ACTIVE_HOT_SET.
5. Contact discovery terminal state machine + continuous enrichment wiring.
6. Rolling hot-set selector (evict DNC/reply/sent → refill).
7. Interactive `python -m scripts.confenge.human_review` (A/R/S, never auto-approve).
8. Process-first enrichment package brought onto the branch for source ladder B/C.
9. Permanent pytest regressions for the above.

## Remaining host operations (post-merge)

1. Deploy SHA bind
2. `reclassify-insufficient` on SHADOW
3. `reconcile` + worker drain / coverage refresh
4. Continuous network enrichment over all TARGET_CONFIRMED (resumable, no Top-N)
5. Grow ESR toward MIN_OPERATIONAL_RESERVE=900 or prove external yield blocker
6. Tiago human review on sample

## Human review command

```bash
python -m scripts.confenge.human_review \
  --sample artifacts/confenge/national-commercial-ready/HUMAN-REVIEW-SAMPLE.json \
  --reviewer tiago
```

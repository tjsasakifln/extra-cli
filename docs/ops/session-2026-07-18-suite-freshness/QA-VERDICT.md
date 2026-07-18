# QA Verdict — suite inventory + entity freshness

**Cycle:** `cyc-2026-07-18T164226Z`  
**Story:** `ROI-cand-dyn-slice-a53bdc0173af`  
**Reviewer:** adversarial-qa-auditor / Quinn (@qa)  
**Implementer:** delivery-engineer (≠ QA)  
**Reviewed commit:** `1c8e988f084010584e31ac6fa33d3e1be46e17f4`  
**Verdict:** **CONCERNS**  
**Date:** 2026-07-18

## Independent re-runs

| Command | Exit | Result |
|---------|------|--------|
| `pytest tests/test_entity_freshness.py -o addopts=''` | 0 | 6 passed |
| `entity_freshness` measure → `/tmp/qa-entity-freshness-rerun/` | 0 | num=0 den=1093 pct=0.0 READY |
| `entity_freshness --gate --min-pct 95` | 2 | fail-closed |
| Live SQL active∧raio_200km | 0 | den=1093 authentic |
| `git show 1c8e988` | 0 | DOD.md **not** modified |

## Adversarial checks

| Attack | Outcome |
|--------|---------|
| Fixture-only measurement | **Rejected** — live PG den matches SQL |
| Full suite green claim | **Not claimed** — LEAVE OPEN |
| SLA met at pct=0 | **Not claimed** — gate exit 2, never=1093 |
| Denominator gaming | **Rejected** — den full 1093, pct honest 0.0 |

## DoD recommendations (for PO / evidence steward)

| Item | Action |
|------|--------|
| L32 `dod:b06848ca7f90` suíte global | **LEAVE OPEN** |
| L33 `dod:925f2c0e059a` freshness mensurável | **FLIP** (capability only; pct operational still 0) |

## Residual concerns

1. Flip L33 must not be misread as operational freshness green.
2. `entity_coverage` empty (0 rows) — writers still needed.
3. Full suite debt remains.

## Process

- Status stays **InReview** until PO close.
- QA does **not** edit `DOD.md` checkboxes.

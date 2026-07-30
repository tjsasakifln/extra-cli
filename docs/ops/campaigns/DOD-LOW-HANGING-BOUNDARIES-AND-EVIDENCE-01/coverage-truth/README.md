# Coverage truth — adversarial pack (semantic)

Campaign: `DOD-LOW-HANGING-BOUNDARIES-AND-EVIDENCE-01`  
Engine: `scripts/coverage/dual_capability_coverage.py`  
No live crawlers. No new 95% measurement.

## Attacks

| # | Attack | Expected defense |
|---|--------|------------------|
| 1 | editais 0%, contratos 100% | Separate capability metrics; no combined pass |
| 2 | editais 100%, contratos 0% | Same |
| 3 | high presence, incomplete query | presence incomplete ≠ operational coverage |
| 4 | zero records + valid `success_zero` | may count under dual rules |
| 5 | zero records without `success_zero` | not covered |
| 6 | publish average of both coverages | in `claims_forbidden` |
| 7 | rename presence as coverage | `data_presence labeled as coverage` forbidden |

## Code anchors

- `claims_forbidden` includes:
  - `average of open_tenders and historical_contracts`
  - `data_presence labeled as coverage`
- Module header: data_presence is descriptive only

## Proof commands

```bash
python3 -c "from scripts.coverage import dual_capability_coverage as d; \
  s=open(d.__file__).read(); \
  assert 'average of open_tenders and historical_contracts' in s; \
  assert 'data_presence labeled as coverage' in s"
python3 -m pytest tests/test_dual_capability_coverage.py tests/test_dod_low_hanging_audit.py -q -k coverage --no-cov
```

## Non-claims

This pack does not assert operational coverage ≥95% or recall ≥95%.

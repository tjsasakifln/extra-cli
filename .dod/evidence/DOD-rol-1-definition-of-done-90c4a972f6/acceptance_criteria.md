# DOD-rol-1-definition-of-done-90c4a972f6

## Exact text

`data_presence` nunca é chamada de cobertura.

## Campaign

DOD-LOW-HANGING-BOUNDARIES-AND-EVIDENCE-01

## Family

D_COVERAGE_TRUTH

## Proof command

```
python3 -m pytest tests/test_dod_low_hanging_audit.py -q -k coverage_truth --tb=no --no-cov
```

## Evidence sha

`1b21f322b15e3c60063c0e75c73d2d306c0ecd5d6bb7cc05251e64767343f21e`

## QA

Independent QA PASS_WITH_REDUCED_SET; item in surviving_proven_item_ids.

## Non-claims

No 95% coverage/recall/VPS/commercial/LOCAL_READY.

# DOD-rol-1-definition-of-done-bb9d5de811

## Exact text

`data_presence` é publicada apenas como métrica descritiva.

## Campaign

DOD-LOW-HANGING-BOUNDARIES-AND-EVIDENCE-01

## Family

D_COVERAGE_TRUTH

## Proof command

```
python3 -m pytest tests/test_dod_low_hanging_audit.py -q -k coverage_truth --tb=no --no-cov
```

## Evidence sha

`1f81fefbd10864cb4015d23320b4029a14976621f0ba9baf18e54b5938dacf2a`

## QA

Independent QA PASS_WITH_REDUCED_SET; item in surviving_proven_item_ids.

## Non-claims

No 95% coverage/recall/VPS/commercial/LOCAL_READY.

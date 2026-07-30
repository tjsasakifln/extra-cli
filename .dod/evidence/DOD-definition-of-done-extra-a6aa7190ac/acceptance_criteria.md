# DOD-definition-of-done-extra-a6aa7190ac

## Exact text

Campo indisponível na fonte é registrado como `SOURCE_UNAVAILABLE` ou `NOT_READY`, nunca como zero e nunca como concluído por conveniência.

## Campaign

DOD-LOW-HANGING-BOUNDARIES-AND-EVIDENCE-01

## Family

A_GOVERNANCE

## Proof command

```
python3 -m pytest tests/test_dod_governance_invariants.py -q --tb=no --no-cov
```

## Evidence sha

`f6e953f298dfa539b2e6b105e067b0e4d50558a0fdb69849f4ec73d16272dbce`

## QA

Independent QA PASS_WITH_REDUCED_SET; item in surviving_proven_item_ids.

## Non-claims

No 95% coverage/recall/VPS/commercial/LOCAL_READY.

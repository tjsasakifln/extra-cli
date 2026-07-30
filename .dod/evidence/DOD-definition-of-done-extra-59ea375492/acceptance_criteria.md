# DOD-definition-of-done-extra-59ea375492

## Exact text

Teste unitário isolado não substitui execução ponta a ponta.

## Campaign

DOD-LOW-HANGING-BOUNDARIES-AND-EVIDENCE-01

## Family

A_GOVERNANCE

## Proof command

```
python3 -m pytest tests/test_dod_governance_invariants.py -q --tb=no --no-cov
```

## Evidence sha

`486957080900c5c1eecaa8b707652f91bfabc6ed5c70ddecf7285bf47d2b0fd6`

## QA

Independent QA PASS_WITH_REDUCED_SET; item in surviving_proven_item_ids.

## Non-claims

No 95% coverage/recall/VPS/commercial/LOCAL_READY.

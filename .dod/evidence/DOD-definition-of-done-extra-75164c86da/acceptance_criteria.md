# DOD-definition-of-done-extra-75164c86da

## Exact text

Código existente sem execução comprovada não é considerado concluído.

## Campaign

DOD-LOW-HANGING-BOUNDARIES-AND-EVIDENCE-01

## Family

A_GOVERNANCE

## Proof command

```
python3 -m pytest tests/test_dod_governance_invariants.py -q --tb=no --no-cov
```

## Evidence sha

`6a9e83d4ae67caa3448a3b3d5d20383571cd6688a9319cd29170f54d60e72ceb`

## QA

Independent QA PASS_WITH_REDUCED_SET; item in surviving_proven_item_ids.

## Non-claims

No 95% coverage/recall/VPS/commercial/LOCAL_READY.

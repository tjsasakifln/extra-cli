# STATUS — EXTRA-DECISION-LOOP-01

| Campo | Valor |
|-------|--------|
| Veredito técnico | **DONE** (implementação + evidência + PR) |
| Aceite de produto | **PENDING_HUMAN** |
| Branch | `goal/extra-decision-loop-01` |
| Baseline main | `d6d9e19` |
| Live pack run | `decision-20260719T215322Z-2a79c2846a` |
| Live counts | PARTICIPAR=0, REVIEW=200, NÃO_PARTICIPAR=0 (limit 200) |
| Reconcile PDF↔Excel | **PASS** |
| Testes campanha | `tests/test_decision_loop_v2.py` — 27 passed |

## Comandos canônicos

```bash
make extra-decision-pack
make extra-review-export DECISIONS_CSV=... REVIEW_OUT=...
make extra-review-import REVIEW_CSV=...
make extra-calibrate
```

## Próxima ação humana

1. Revisar `evidence/live-pack/executive_decision_brief.pdf` + Excel.
2. Preencher amostra em `human_review_queue.csv` e importar.
3. Registrar aceite em `human-acceptance.md` (ACCEPTED / ACCEPTED_WITH_LIMITATIONS / REJECTED).

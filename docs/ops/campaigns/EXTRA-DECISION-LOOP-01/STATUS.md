# STATUS — EXTRA-DECISION-LOOP-01

| Campo | Valor |
|-------|--------|
| Veredito técnico | **DONE** (implementação + evidência + PR + CI verde) |
| Aceite de produto | **PENDING_HUMAN** |
| Branch | `goal/extra-decision-loop-01` |
| Baseline main | `d6d9e19` |
| PR | https://github.com/tjsasakifln/extra-consultoria/pull/52 |
| Live pack (offline) | `decision-20260719T215322Z-2a79c2846a` — REVIEW=200 |
| Live pack (HTTP) | `decision-20260719T215652Z-65ba60f985` — 20 reconfirms (12 ok, 7 error, 1 http_403), high_conf_open=12 |
| Live counts HTTP | PARTICIPAR=0, REVIEW=100, NÃO_PARTICIPAR=0 (limit 100) |
| Reconcile PDF↔Excel | **PASS** (ambos packs) |
| CI PR #52 | Lint/mypy/critical/ops/resilience/bandit/pip-audit **pass** |
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

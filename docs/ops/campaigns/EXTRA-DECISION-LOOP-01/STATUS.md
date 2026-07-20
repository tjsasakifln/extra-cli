# STATUS — EXTRA-DECISION-LOOP-01

| Campo | Valor |
|-------|--------|
| Veredito técnico | **DONE** (implementação + evidência + PR + CI verde) |
| Aceite de produto | **PENDING_HUMAN** |
| Branch | `goal/extra-decision-loop-01` |
| Baseline main | `d6d9e19` |
| PR | https://github.com/tjsasakifln/extra-consultoria/pull/52 |
| Live pack (offline) | `decision-20260719T215322Z-2a79c2846a` — REVIEW=200 |
| Live pack (HTTP) | `decision-20260719T221130Z-fb0c4820ba` — 20 reconfirms (13 ok); reconcile **PASS** (PDF/Excel lidos) |
| Live counts HTTP | PARTICIPAR=0, REVIEW=8, NÃO_PARTICIPAR=**92** (limit 100; fit Extra real) |
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

## Remediation 2026-07-19 (semantic false positives)

| Fix | Before | After |
|-----|--------|-------|
| Prazo vencido | status open podia mascarar deadline | `prazo_encerrado` hard blocker sempre |
| Reconfirm ok | HTTP 200 genérico | identity match (control/CNPJ/numero) obrigatório |
| Offline | tratado quase como ok path | `skipped_offline_fixture` → nunca PARTICIPAR |
| Testes | 27 | 41 passed em `tests/test_decision_loop_v2.py` |

Estado: **IMPLEMENTED_AWAITING_MERGE** — sem selo LOCAL_READY / 95%.


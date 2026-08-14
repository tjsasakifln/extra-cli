# Runbook — Decision-Unit Intelligence + Reachability

## Track A (30 contas reais)

```bash
python3 -m scripts.decision_unit_intelligence plan --out /tmp/dui-cohort.json --limit 30
python3 -m scripts.decision_unit_intelligence run \
  --out /tmp/dui-run-1 \
  --operator-out /tmp/dui-operator \
  --manifest /tmp/dui-cohort.json
python3 -m scripts.decision_unit_intelligence run \
  --out /tmp/dui-run-2 \
  --manifest /tmp/dui-cohort.json
python3 -m scripts.decision_unit_intelligence replay \
  --run-a /tmp/dui-run-1 --run-b /tmp/dui-run-2
```

Fontes Tier 0: artefatos da campanha `reajuste_14133-2026-08-05-56dc6c48` e planilha CRM enriquecida.
DSN (`LOCAL_DATALAKE_DSN`) é opcional.

## Shadow

```bash
python3 -m scripts.decision_unit_intelligence shadow --out /tmp/dui-shadow-100 --limit 100
python3 -m scripts.decision_unit_intelligence shadow --out /tmp/dui-shadow-1000 --limit 1000
```

O shadow 1000 só cresce se o índice histórico/datalake tiver as contas. Sem inventar.

## Métrica

`Decision-Unit Reachability Rate` = contas com ≥1 rota defensável / contas não-`BLOCKED`.

`BLOCKED` ≠ `R0`. Falta de e-mail nominal ≠ fracasso.

## Warmbly

Apenas rotas `R1` com e-mail nominal **observado** entram em `confenge.outreach.v1`.
O restante permanece ação manual no pack operador.

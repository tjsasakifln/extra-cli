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

## Web discovery canary

Busca web é explícita, limitada e reutilizável. O backend `off` registra `POLICY_SKIP`; não conta como cobertura.

```bash
python3 -m scripts.decision_unit_intelligence run \
  --out /tmp/dui-web-10 \
  --limit 10 \
  --search-backend ddgs \
  --search-max-queries 2 \
  --search-results-per-query 4 \
  --crawl-max-pages 2 \
  --verify-email-dns
```

Para SearXNG, use `--search-backend searxng` e `--searxng-url` ou `CONFENGE_SEARXNG_URL`. Não use instância pública de terceiros para batch. Cache local: `.cache/confenge-prospect/`. Instância privada CONFENGE: [`searxng-private-backend.md`](searxng-private-backend.md).

O manifesto registra contas tentadas, domínios resolvidos, buscas, páginas, bytes e custo externo. Falha de fonte, orçamento esgotado e ausência de evidência são estados diferentes.

`--verify-email-dns` verifica apenas sintaxe/DNS/MX. Catch-all permanece `UNKNOWN_NOT_PROBED` e SMTP permanece `SKIPPED_POLICY`; MX não prova caixa nem identidade.

## Shadow

```bash
python3 -m scripts.decision_unit_intelligence shadow --out /tmp/dui-shadow-100 --limit 100
python3 -m scripts.decision_unit_intelligence shadow --out /tmp/dui-shadow-1000 --limit 1000
```

O shadow 1000 só cresce se o índice histórico/datalake tiver as contas. Sem inventar.

## Métrica

`Decision-Unit Reachability Rate` = contas com ≥1 rota defensável / contas não-`BLOCKED`.

`BLOCKED` ≠ `R0`. Falta de e-mail nominal ≠ fracasso.

Cada `run` grava `affiliation_cohort.json` (schema `confenge.dui.affiliation_cohort.v1`)
com confiança por campo, uplift de emails antes ambíguos agora associáveis
somente quando a corroboração permite, contradições e próxima recomendação.
Delta 0 é honesto quando a Track A só tem QSA + caixa genérica.

## Warmbly

Apenas rotas `R1` com e-mail nominal **observado** entram em `confenge.outreach.v1`.
O restante permanece ação manual no pack operador.

# N09 — Amostra-ouro / recall independente — BLOCKED_SOURCE

**Status:** `BLOCKED_SOURCE`  
**Atualizado:** 2026-07-19T08:25Z  
**Campanha:** EXTRA-OPS-95-FOUNDATION  

## Classe

`BLOCKED_SOURCE` — depende de corpus de verdade independente (publicações oficiais estratificadas) não contido no repositório operacional.

## Owner

Tiago / operador + campanha futura de recall

## Causa

Recall ≥95% exige amostra-ouro **independente e estratificada** (oportunidades relevantes e irrelevantes, multi-fonte, multi-município). O repositório tem:

- fixture/preliminar de 4 publicações CIGA (PARTIAL/NOT_READY por estratos ausentes);
- `docs/qa/recall-sample-2026-07-17.json` (não qualifica como gold independente completo).

Não há amostra-ouro formal versionada com labels humanos e política de inclusão.

## Evidência

- `DOD.md` itens recall/amostra-ouro abertos
- `docs/ops/campaigns/EXTRA-OPS-95/baseline/foundation-baseline.json` → N09 BLOCKED_SOURCE
- `docs/ops/campaigns/EXTRA-OPS-95/evidence/M3-intel/workspace-coverage.json` → opportunity_recall NOT_READY

## Impacto

- Gates campanha: recall ≥95%, amostra-ouro estratificada → abertos
- Não bloqueia ops proxy de contratos nem crescimento de presença de editais
- Impede claim DONE da campanha e LOCAL_READY

## Workaround tentado

- Reutilizar sample CIGA 4/4 → insuficiente (estratos, independência)
- Não fabricar labels a partir do próprio lake (contaminação)

## Próximo teste

1. Definir protocolo de amostragem estratificada (UF, esfera, modalidade, valor, relevância Extra)
2. Coletar ≥N publicações oficiais fora do pipeline de treino
3. Rotular GO/REVIEW/NO_GO e relevância
4. Medir recall/precisão do classificador atual

## Condição de desbloqueio

Arquivo de amostra-ouro versionado + manifesto de proveniência + métricas de recall/precisão reproduzíveis ≥ meta, sem contaminação pelo conjunto de treino.

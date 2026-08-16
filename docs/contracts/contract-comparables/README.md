# Engine inbound de comparáveis — valor integral nominal de pavimentação

Canário #415. Owner: `scripts/contract_comparables`, `tests/contract_comparables`, este diretório.

## O que o engine responde

Somente: **como o valor integral nominal de um contrato público de pavimentação se posiciona frente a contratos comparáveis?**

Recusa é tão auditável quanto o cálculo. Estados: `COMPARABLE`, `HOLD_FOR_DATA`, `NOT_COMPARABLE`.

## O que o engine não faz

- custo/km, custo/m², preço unitário, BDI, deságio, produtividade
- “caro/barato”, “sobrepreço”, “irregular”, causalidade
- ranking nacional ou market share
- LLM ou embeddings como critério de inclusão
- rotular fixture como `official_live`

Preço por unidade física só existiria se quantidade, unidade, escopo, normalização e amostra fossem documentalmente verificáveis. Neste canário isso não ocorre: `HOLD_FOR_DATA` / `NOT_COMPARABLE` com `physical_unit_price_not_verified` se alguém pedir.

## Método

1. Recorte determinístico (tipologia por palavras-chave documentadas, regime, UF/região, ano, semântica, base original/atualizado).
2. Gates fail-closed (funções puras).
3. Métricas só depois do gate: n, mediana, P25/P75, IQR, MAD, percentil do focal, distância robusta, min/max com cautela, coverage/missingness, estrato por UF.
4. Outlier permanece na amostra e é descrito como diferença estatística (`statistical_difference_only`).

`UNKNOWN` é excluído do denominador. Duplicata com mesmo `revision` e valores conflitantes recusa o grupo. Retificação posterior invalida só grupos que contêm o contrato afetado.

## CLI

```bash
python3 -m scripts.contract_comparables build --case comparable_clear
python3 -m scripts.contract_comparables canary
python3 -m scripts.contract_comparables report \
  --out docs/contracts/contract-comparables/reports/canary-observability.json \
  --markdown docs/contracts/contract-comparables/reports/canary-observability.md
python3 -m scripts.contract_comparables live --as-of 2026-08-01
python3 -m scripts.contract_comparables official-canary --as-of 2026-08-01
```

Sem `LOCAL_DATALAKE_DSN` o modo do `live` legado é `FIXTURE_ONLY`. O canário oficial (`official-canary`) **não** cai para fixture: emite `BLOCKED` com pré-requisito e próximo comando.

Com DSN, o canário lê só colunas oficiais de `pncp_supplier_contracts` e filtra pavimentação pelo classificador documentado. Se `unidade`, `quantidade`, `regime`, `modalidade` e `valor_semantic` não existirem, o grupo é `HOLD_FOR_DATA` (`live_columns_unavailable`). Snapshot vazio = `BLOCKED` (`official_dataset_empty`). Pedido de custo/km = `HOLD_FOR_DATA` (`physical_unit_price_not_verified`). Não inventar semântica. Replay: mesmo `--dsn --focal --as-of --metric` deve reproduzir o `content_hash` se o snapshot não mudou.

Ver [OFFICIAL_CANARY.md](./OFFICIAL_CANARY.md).

## Live smoke (quando houver snapshot)

```bash
export LOCAL_DATALAKE_DSN="${LOCAL_DATALAKE_DSN:-postgresql://test:test@127.0.0.1:5433/extra_test}"
python3 -m scripts.contract_comparables live --as-of 2026-08-01 --limit 200
python3 -m scripts.contract_comparables live --as-of 2026-08-01 --limit 200
# comparar content_hash das duas saídas
```

Não rotular o resultado como `official_live` até as colunas semânticas existirem e a coverage ser comprovada.

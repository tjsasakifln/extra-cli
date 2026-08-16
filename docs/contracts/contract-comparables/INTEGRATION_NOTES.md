# INTEGRATION_NOTES — contract-comparables inbound (#415)

Este arquivo é o único lugar em que este slice descreve integrações compartilhadas. O código deste PR **não** edita `scripts/contract_publication/**`, adapters public-read, nem o national-claims gate. Não há migration.

## #400 (public-read contract analysis)

Contrato de saída: `comparable-contracts/1.0` (alias `public-read-comparable-contracts/1.0`).

Campos que o adapter existente `adapt_peer_group` já lê:

- `schema`
- `status` (`COMPARABLE` | `HOLD_FOR_DATA` | `NOT_COMPARABLE`) — sem campo `valid`
- `content_hash`
- `metrics`
- `contract_version` / `version`
- `comparisons` / `peers`
- `canonical_contract_ids` / `target_contract_id`

Mapeamento esperado (já invertido no adapter #400, não reimplementado aqui):

| Producer | Consumer #400 |
|----------|----------------|
| `COMPARABLE` | `PEER_VALID` |
| `HOLD_FOR_DATA` | `PEER_WEAK` |
| `NOT_COMPARABLE` | `NOT_COMPARABLE` |

#400 **não está em `origin/main`**. Fixtures locais são a única fonte. Nenhuma comparação fixture é `official_live`.

## #414 (publication candidate / evidence pack)

Este engine não produz score nem evidence pack. #414 pode anexar o documento versionado. Sem fan-in neste PR.

## #302 (denominador nacional)

Este canário não emite claim nacional. Coverage e universo são os do recorte (UF + período + tipologia). Ausência de coverage nacional não vira posição zero nem market share.

## `pncp_supplier_contracts`

Colunas oficiais atuais: identidade, objeto, `valor_total`, datas, UF/município, fornecedor/órgão.

**Não existem** `unidade`, `quantidade`, `regime`, `modalidade`, `valor_semantic`. Live sem esses campos = `HOLD_FOR_DATA` (`live_columns_unavailable`). `valor_total` é tratado como candidato a valor integral nominal **somente** quando o recorte fixture declara a semântica; no live a semântica permanece `unknown`.

## Worktree paralelo `scripts/comparable_contracts`

Não foi reutilizado nem fundido. O id de schema `comparable-contracts/1.0` é compartilhado de propósito para #400. O layout de módulos deste inbound é `scripts/contract_comparables`.

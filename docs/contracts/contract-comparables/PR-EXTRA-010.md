# feat(contract-comparables): official paving canary or auditable BLOCKED (EXTRA-010 / #415)

## Outcome

The inbound #418 producer now has an official paving canary:

`python3 -m scripts.contract_comparables official-canary`

Live SELECT-only against `public.pncp_supplier_contracts` either builds a versioned peer-group document or refuses with `HOLD_FOR_DATA` / `NOT_COMPARABLE` / `BLOCKED`. Recusal is success. Fixture `COMPARABLE` is not official proof.

**Decisão final: `READY_BEHIND_HUMAN_GATE`**

**Veredito live deste sandbox: `BLOCKED`** — `official_dataset_empty` + `live_columns_unavailable`. Valor integral nominal **não** admite peer group oficial defensável hoje.

## Scope

- Reuse `scripts.contract_comparables` (PR #418). No third producer.
- Reviewable sample: tipologia (keyword documentado), regime, porte, geografia, período, moeda/base, coverage.
- Metric whitelist: mediana / P25 / P75 / distâncias sobre valor integral nominal.
- `custo/km` sem quantidade/unidade documental → `HOLD_FOR_DATA` (`physical_unit_price_not_verified`).
- Taxa de `NOT_COMPARABLE`, latência de refresh e isolamento de late arrival/retificação.
- Replay: mesmo `--dsn --focal --as-of --metric` → mesmo `content_hash` (latência fora do hash).

## Fora de escopo

- Segundo engine (`scripts.comparable_contracts`)
- UX / Market Answer / copy / CRM (web-cfg#84)
- Merge, push, deploy, DNS, fechamento de #415
- Inventar colunas `unidade` / `quantidade` / `regime` / `modalidade` / `valor_semantic`
- Rotular fixture ou live incompleto como `official_live`
- BDI, deságio, custo/km estimado, ranking nacional, market share, irregularidade/sobrepreço
- Price Oracle / Public Market Answer no extra-cli

## Riscos

- Dois engines unmerged competem; este PR estende só o inbound #418.
- Sem colunas semânticas, `COMPARABLE` oficial é impossível. `HOLD_FOR_DATA` / `BLOCKED` é o estado honesto.
- EXTRA-003 ausente; EXTRA-004 e EXTRA-008 fora de `origin/main`.
- Snapshot local `127.0.0.1:55432/extra_test` tem a tabela e 0 linhas. Não é o host Netcup de record.

## Rollback

Remover `scripts/contract_comparables/official_canary.py`, o subcomando `official-canary` e `tests/contract_comparables/test_official_canary.py`. O engine fixture de #418 permanece intacto.

## Refs

- extra-cli#415 (peer groups fail-closed)
- extra-cli#418 (inbound producer being extended)
- web-cfg#84 (Market Answer consumer; not implemented here)
- EXTRA-003 (ausente localmente)
- EXTRA-004 (`feat/extra-004-official-national-catalog`, off-main)
- EXTRA-008 (`feat/extra-008-live-consumers`, off-main)
- Base `origin/main`: `820c83b82a35aaab0d381f54faa5357b386db1b3`

## Residual (human / ops gate)

1. Popular `pncp_supplier_contracts` no DSN oficial (Netcup ou snapshot reconciliado) com contratos de pavimentação.
2. Materializar colunas semânticas oficiais (`unidade`, `quantidade`, `regime`, `modalidade`, `valor_semantic`) — sem isso o teto continua `HOLD_FOR_DATA`.
3. Merge de EXTRA-004 (catálogo nacional) se o recorte pretender coverage nacional.
4. Merge de EXTRA-008 / #400 para o consumer public-read.
5. EXTRA-003 ainda sem branch local — tipologia permanece o classificador documentado de keywords.

Próximo comando:

```bash
export LOCAL_DATALAKE_DSN="${LOCAL_DATALAKE_DSN:-postgresql://test:test@127.0.0.1:5433/extra_test}"
python3 -m scripts.contract_comparables official-canary --as-of 2026-08-01 --metric valor_integral_nominal
python3 -m scripts.contract_comparables official-canary --as-of 2026-08-01 --metric valor_integral_nominal
# comparar content_hash
```

## Evidência executada (2026-08-16)

| Run | Status | Reason codes | Replay |
|-----|--------|--------------|--------|
| no DSN ×2 | `BLOCKED` | `dsn_unavailable` | hash idêntico |
| DSN `127.0.0.1:55432/extra_test` ×2 | `BLOCKED` | `official_dataset_empty`, `live_columns_unavailable` | hash idêntico |
| `--metric custo/km` | `HOLD_FOR_DATA` | `physical_unit_price_not_verified` | n/a |
| `pytest tests/contract_comparables/ --no-cov` | 36 passed, 1 skipped | n/a | n/a |

`catalog_mode` nunca foi `official_live`.

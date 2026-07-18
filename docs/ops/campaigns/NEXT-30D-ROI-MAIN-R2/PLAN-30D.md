# PLAN-30D — NEXT-30D-ROI-MAIN-R2 (pós DEFER SmartLic)

**UTC:** 2026-07-18T23:06:00Z  
**Critical open:** N06c (IN_PROGRESS — ganho mensurável)  
**SmartLic dataset:** `DEFERRED_STALE_SOURCE` (fora do caminho crítico)

## Policy change

Dataset SmartLic stale → **não** importar snapshots, **não** aguardar export, **não** usar em cobertura/freshness/gates.  
Bridge `smartlic_snapshot_import.py` permanece opcional/testado sem expansão.

## Extra-ROI ranking (executar nesta ordem)

| Rank | ID | Trabalho |
|-----:|----|----------|
| 1 | **N06c** | Expansão real coleta Extra + cobertura por entidade |
| 2 | N01 | Golden path live sem timeout (fontes Extra) |
| 3 | N09 | Amostra estratificada + recall real |
| 4 | N07/N18 | Histórico contratos próprio + backfill seguro |
| 5 | N14 | Revalidação residual DoD |
| 6 | N15 | Auditoria cética + encerramento |
| 7 | OPS | Outputs só com dados atuais Extra |

## N06c wave2 (em curso) — só Extra

| Métrica (universo 1093) | Antes wave2 | Após (mid-crawl) | Δ |
|-------------------------|------------:|-----------------:|--:|
| Editais (cnpj∪match) | 201 | 285 | **+84** |
| Contratos entidades | 247 | 308 | **+61** |
| Either | 301 (27.5%) | 369 (33.8%) | **+68 / +6.2pp** |
| Rows bids | 4636 | 10974 | +6338 |
| Rows contracts | 72923 | ~315k+ | +240k+ |

Fontes: PNCP full 30d + contracts 180d. **smartlic_used: false**.  
Janela curta 5d anterior: re-upsert apenas (delta 0) — não usar `inserted` do monitor como prova de cobertura.

## Critical path chain

`R0 → R1 → N02 → N04 → N05 → N06 → N06b → N06c → N11 → N12 → N14 → N15`

## Next action

1. Deixar crawls N06c terminarem / remedir after final
2. Fechar N06c com evidência delta estável
3. Seguir ranking: N01 → N09 → N07/N18 residual → N14/N15

# PLAN-30D — NEXT-30D-ROI-MAIN-R2 (pós DEFER SmartLic · N06c DONE)

**UTC:** 2026-07-19 (wave2 final)  
**Critical open:** nenhum (N06c DONE)  
**SmartLic dataset:** `DEFERRED_STALE_SOURCE`

## N06c — DONE (Extra-owned)

| Métrica (universo 1093) | Antes wave2 | Final | Δ |
|-------------------------|------------:|------:|--:|
| Editais (cnpj∪match) | 201 | **285** | **+84** |
| Contratos entidades | 247 | **368** | **+121** |
| Either | 301 (27,5%) | **406 (37,2%)** | **+105 / +9,6pp** |
| Rows bids | 4636 | 10974 | +6338 |
| Rows contracts | 72923 | **1.082.055** | +1.009.132 |

Fontes: PNCP full 30d + contracts 180d (6/6 windows, `go_no_go_3y=GO`). **smartlic_used: false**.

## Extra-ROI ranking (próximo)

1. **N01** — golden path live sem timeout  
2. **N09** — amostra estratificada + recall real  
3. **N07/N18** — residual contratos (histórico já ampliado)  
4. **N14** → **N15**  
5. Outputs só com dados Extra atuais  

## Policy

SmartLic stale → sem import, sem export, sem gates. Bridge opcional sem expansão.

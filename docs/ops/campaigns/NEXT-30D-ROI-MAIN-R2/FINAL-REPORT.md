# FINAL REPORT — NEXT-30D-ROI-MAIN-R2

**UTC:** 2026-07-18T21:53:40Z  
**HEAD inicial:** `dc7cea0`  
**HEAD final:** `6e4bc5575c3b4217bfc71456397b16c2d3b3288b`  
**origin/main:** synced

## Métricas (linhagem separada)

| Camada | Valor |
|--------|------:|
| Epic histórico (não main) | 32,3% |
| Main baseline R1 | 6,8% |
| Main pós-herança R1 | 14,4% |
| **Main R2 canônico** | **14.39% (195/1355)** |
| PERT crítico novo | **32.0d / 32.0d** |
| Meta ≥30d | **SIM** |
| Herdado recontado? | **NÃO** |

## Dados live (PostgreSQL)

| Métrica | Valor |
|---------|------:|
| pncp_supplier_contracts | 72.923 |
| pncp_raw_bids | 4.636 |
| Universo 200 km | 1.093 |
| Entes com edital ou contrato (cnpj8) | 282 (25,8%) |
| commercial_numerator session | 135/1093 |

## Escopo terminal

**DONE:** R0, R1, R2, N01, N02, N03, N04, N05, N06, N06b, N06c, N07, N07b, N08, N10, N11, N12, N13, N14, N15, N16, N17, N18  
**BLOCKED_SOURCE:** N09  
**OPEN:** nenhum (escopo 100% terminal)

## Gates

LOCAL_READY / VPS / PROJECT_DONE = **NOT_READY** (fail-closed)

## Limitações

- Recall stratified gold sample BLOCKED_SOURCE (N09)
- Competitors/values metrics explicitly NOT_READY (N16)
- Operational entity coverage 25.8% either-source — not 95%
- Single-process golden_path with PNCP+PCP may still timeout on PNCP
- 3y contracts GO not claimed (14d wave only)

## Retomada

```bash
cat docs/ops/campaigns/NEXT-30D-ROI-MAIN-R2/resume.md
cat docs/ops/campaigns/NEXT-30D-ROI-MAIN-R2/STATUS.md
```

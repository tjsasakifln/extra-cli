# FINAL REPORT — NEXT-30D-ROI-MAIN-R2

**UTC:** 2026-07-18T22:03:55Z  
**HEAD inicial:** `dc7cea0`  
**HEAD final:** `509abdedc1439632f1eb5f04607e47fa3f1f4e12`  

## Métricas (linhagem separada)

| Camada | Valor |
|--------|------:|
| Epic histórico (não main) | 32,3% |
| Main baseline R1 | 6,8% |
| Main pós-herança R1 | 14,4% |
| **Main R2 canônico** | **14.39% (195/1355)** |
| PERT critical novo | **32.0d / 32.0d** |
| Meta ≥30d | **SIM** |
| Herdado recontado? | **NÃO** |

## Escopo terminal

**DONE (23):** R0, R1, R2, N01, N02, N03, N04, N05, N06, N06b, N06c, N07, N07b, N08, N10, N11, N12, N13, N14, N15, N16, N17, N18  

**BLOCKED_SOURCE (1):** N09  

**OPEN:** nenhum (`scope_open: []` em final-report.json)

## N01 proof (single-process)

```bash
python3 -m scripts.golden_path --sources pncp,pcp --strict --dsn "$LOCAL_DATALAKE_DSN"
```
→ **SUCCESS** (2/2 fontes OK, freshness pass)  
Evidence: `evidence/N01-golden/ledger-pncp-pcp-strict-v2.json` + `golden-pncp-pcp-strict-v2.log`

## N18 proof

`pytest tests/test_checkpoint_page_promote.py -v` → **5 passed** (named asserts)

## Gates

LOCAL_READY / VPS / PROJECT_DONE = **NOT_READY**

## Limitações

- N09 BLOCKED_SOURCE — recall gold sample not available
- N16 competitors/values denominators NOT_READY (declared)
- Entity either-coverage 25.8% — not 95%
- PNCP golden may resume from committed watermark (pages_fetched counted)
- 3y contracts GO not claimed

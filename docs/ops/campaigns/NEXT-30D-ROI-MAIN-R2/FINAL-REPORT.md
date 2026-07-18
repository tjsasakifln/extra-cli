# FINAL REPORT — NEXT-30D-ROI-MAIN-R2 (mid/close)

**UTC:** 2026-07-18T21:32:31Z  
**HEAD inicial:** `dc7cea0`  
**HEAD atual:** `e8d3e9a8d9c806e2920172dd83eabe06744a30b6` (synced origin: True)

## Métricas (linhagem)

| Camada | Valor |
|--------|------:|
| Epic histórico (não main) | 32,3% |
| Main baseline R1 | 6,8% |
| Main pós-herança R1 | 14,4% |
| **Main R2 canônico** | **14.39% (195/1355)** |
| PERT crítico novo | **28.5d / 32d** |
| Meta ≥30d | **NÃO** |

Herdado **não** recontado como avanço novo.

## Entregas principais

- Bootstrap forense R2 + reconciliação legada
- SmartLic reuse matrix + snapshot import bridge (dry-run + unit tests)
- Mig 056 + apply_migrations max=56
- Universe snapshot hash + zero-dup
- Schema audit ok
- Applicability zero necessary unknowns
- Coverage M2/M3/M4 + 14d contracts wave (72.923 rows)
- Ops pack live CSV/Excel/PDF + reconcile
- Backup/restore local proof
- Checkpoint transition bugfix (PNCP pipeline)
- Resume protocol contracts (windows_skipped_resume)

## QA

Todo item DONE possui `qa-verdict.json` com reviewer adversarial-qa-auditor.

## Gates

LOCAL_READY / VPS / PROJECT_DONE permanecem **NOT_READY**.

## Próximo backlog

Ver `next-ranked-backlog.json`.

## Limitações

- N01 golden path still CONCERNS (PNCP timeout once)
- N09 recall scaffold NOT_READY
- 3y contracts GO not claimed
- coverage far below 95%

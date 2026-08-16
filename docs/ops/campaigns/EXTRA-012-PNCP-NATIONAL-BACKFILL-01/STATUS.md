# EXTRA-012 — residual live do backfill nacional PNCP

**Decisão:** `BLOCKED_WITH_WINDOW_LIST`  
**Issue:** #249 permanece **OPEN**  
**Não afirma:** `VPS_OPERATIONAL`, cobertura nacional completa, freshness SLA, incremental-only, cutover.

## Pin (re-medido 2026-08-16T23:26Z)

| Campo | Valor |
|-------|--------|
| `origin/main` | `820c83b82a35aaab0d381f54faa5357b386db1b3` |
| SHA implantado | `bbc4b6b7db295909d773f5a0e1f3314085a2f26c` (≠ main; **sem** fast-forward — janela aberta) |
| Janela | `2025-01-01` → `2026-08-15` (20 partições de 30d) |
| Universe | `pncp_supplier_contracts` |
| Partition | `date_window_30d/start=2025-01-01/end=2026-08-15` |
| Runner | `python3 -m scripts.crawl.run_contracts_90d_pilot` |
| Checkpoint | `/var/lib/extra-consultoria/checkpoints/national-2025-canary` |
| Host resume argv | `--days 592 --allow-cross-run-resume` + `CONTRACTS_UPSERT_BATCH=8` + `flock` |

`--days 592` no host **não** tem `--start-date` (código desta PR ainda não implantado). Isso derivou a chave extra `20260725_20260816` (fora do pin). Fast-forward do SHA **proibido** enquanto `current_window=20260725_20260816` p=161.

## Contagens live (checkpoint, helper)

Fonte: `python3 -m scripts.ops.report_national_backfill` sobre **byte-copy** do checkpoint do host (esta sessão). Duas execuções idênticas.

| planned | complete | failed | blocked | retry | skip on resume |
|--------:|---------:|-------:|--------:|------:|---------------:|
| 20 | 13 | 7 | 0 | 7 | 13 |

Janelas `complete` **não** foram re-buscadas (SKIP observado em dois resumes do retry batch-8).  
`20260625_20260724` também SKIP. A chave pinada `20260725_20260815` não reabriu; a derivada `20260725_20260816` sim.  
Janelas `failed` **não** foram marcadas `success`.  
Seis janelas antigas (antes do SHA com `window_results`) têm reconciliação `UNKNOWN` — não zero.

`fetched = persisted + rejected + skipped` fecha nas janelas que têm `window_results`.  
`success` do job (`partial`, exit 3) **não** prova completude.

## Retry live (já executado; falhou de novo)

Writer único `run_contracts_90d_pilot --days 592` + `CONTRACTS_UPSERT_BATCH=8` correu 17:24–19:26 -03 e morreu em `out of shared memory` / `max_locks_per_transaction=64` (GUC lido no host = 64) em **todas** as 7 janelas planejadas + a chave derivada.

Não há segundo retry com batch inventado. Elevar o GUC é gate humano/DBA.

## Freshness (SELECT no host, esta sessão)

- `pncp_supplier_contracts`: 4 572 996 linhas (não é cobertura)
- `max(data_publicacao_fonte)` = 2026-08-15
- `max(last_seen_at)` = 2026-08-17T00:26:03+02 (morte do writer; não é SLA)

## Incremental

**Não** é a única rotina normal. `pncp-contracts.timer` segue enabled (próximo Mon 06:03 -03); o serviço está inactive. O backfill residual continua a autoridade. Fence `SuccessExitStatus=75` existe no incremental; lock file está stale (pid incremental de 14/08, sem holder).

## Token terminal

`BLOCKED_WITH_WINDOW_LIST`

| window_key | terminal | in_pin | blocker |
|------------|----------|--------|---------|
| `20251127_20251226` | failed | yes | `max_locks_per_transaction` |
| `20251227_20260125` | failed | yes | `max_locks_per_transaction` |
| `20260126_20260224` | failed | yes | `max_locks_per_transaction` |
| `20260225_20260326` | failed | yes | `max_locks_per_transaction` |
| `20260327_20260425` | failed | yes | `max_locks_per_transaction` |
| `20260426_20260525` | failed | yes | `max_locks_per_transaction` |
| `20260526_20260624` | failed | yes | `max_locks_per_transaction` |
| `20260725_20260816` | blocked | **no** (drift `--days 592`) | `max_locks_per_transaction` |

## Residual aberto (backlog)

1. Sete janelas do pin (2025-11-27 → 2026-06-24) ainda `failed` depois do retry batch-8. Gate: `ALTER SYSTEM max_locks_per_transaction=256` + restart Postgres (humano/DBA).
2. SHA host ≠ `origin/main` / PR HEAD. Implantar só em fronteira de janela fechada, com `--start-date 2025-01-01 --end-date 2026-08-15`.
3. Incremental recorrente **não** habilitado como writer único.
4. Chave derivada `20260725_20260816` some quando o host ganhar o pin desta PR.
5. #249 permanece **OPEN**.

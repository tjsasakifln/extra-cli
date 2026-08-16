# EXTRA-012 — residual live do backfill nacional PNCP

**Decisão:** `READY_BEHIND_HUMAN_GATE`  
**Issue:** #249  
**Não afirma:** `VPS_OPERATIONAL`, cobertura nacional completa, freshness SLA.

## Pin (2026-08-16T20:31Z)

| Campo | Valor |
|-------|--------|
| `origin/main` | `820c83b82a35aaab0d381f54faa5357b386db1b3` |
| SHA implantado | `bbc4b6b7db295909d773f5a0e1f3314085a2f26c` (≠ main; sem fast-forward) |
| Janela | `2025-01-01` → `2026-08-15` (20 partições de 30d) |
| Universe | `pncp_supplier_contracts` |
| Partition | `date_window_30d/start=2025-01-01/end=2026-08-15` |
| Runner | `python3 -m scripts.crawl.run_contracts_90d_pilot` |
| Checkpoint | `/var/lib/extra-consultoria/checkpoints/national-2025-canary` |
| Host resume argv | `--days 592 --allow-cross-run-resume` + `CONTRACTS_UPSERT_BATCH=8` + `flock` |

`--days 591` no dia 2026-08-16 deslocaria o start para 2025-01-02. O host **não** tem `--start-date` (código desta PR). `--days 592` preserva o start `2025-01-01`. A última chave pode virar `20260725_20260816` neste resume — residual documentado.

## Contagens live (checkpoint, helper)

Fonte: `python3 -m scripts.ops.report_national_backfill` sobre o checkpoint do host.

| planned | complete | failed | blocked | retry | skip on resume |
|--------:|---------:|-------:|--------:|------:|---------------:|
| 20 | 13 | 7 | 0 | 7 | 13 |

Janelas `complete` **não** foram re-buscadas (SKIP observado em dois resumes).  
Janelas `failed` **não** foram marcadas `success`.  
Seis janelas antigas (antes do SHA com `window_results`) têm reconciliação `UNKNOWN` — não zero.

`fetched = persisted + rejected + skipped` fecha nas janelas que têm `window_results`.  
`success` do job anterior (`partial`, exit 3) **não** prova completude.

## Freshness (SELECT no host)

- `pncp_supplier_contracts`: 4 572 994 linhas
- `max(data_publicacao_fonte)` = 2026-08-15
- `max(last_seen_at)` = 2026-08-16T16:49:15-03 (último close do writer anterior)
- Não é SLA; não é cobertura.

## Incremental

**Não habilitado.** O backfill ainda é o writer. `pncp-contracts.timer` segue enabled (próximo Mon 06:03 -03); o fence `flock` / lock do incremental devolve exit 75 se o backfill estiver ativo.

## Residual aberto

1. Sete janelas `failed` (2025-11-27 → 2026-06-24) por `out of shared memory` / `max_locks_per_transaction=64` no trigger `fn_capture_contract_snapshot`. Retry ao vivo com `CONTRACTS_UPSERT_BATCH=8`: passou a p~18 que matou o batch 50; em 2026-08-16T20:34Z estava em `20251127_20251226` p=27/369 sem novo upsert failed. Ainda não é janela `complete`.
2. Drift de SHA host ≠ `origin/main`. Fast-forward só em fronteira de janela, depois desta PR.
3. `max_locks_per_transaction` é GUC postmaster — aumentar exige restart Postgres (gate humano/DBA). EXTRA-005/EXTRA-013 não têm artefato in-repo; se forem esse gate, permanecem abertos.
4. Incremental recorrente só depois do backfill terminal.
5. Chave da última janela pode derivar com `today` até o host ganhar `--start-date/--end-date`.

## Retry (já lançado)

```bash
ssh -p 2222 -i ~/.ssh/extra-consultoria-prod extra-consultoria@159.195.18.88 \
  'pgrep -af run_contracts_90d_pilot; grep -E "SKIP |WINDOW_|upsert failed|completed pages" /var/lib/extra-consultoria/output/issue-249-retry.log | tail'
```

Se o batch 8 falhar de novo:

```bash
# gate humano: ALTER SYSTEM max_locks_per_transaction=256; restart Postgres
# depois, no host, mesmo checkpoint:
CONTRACTS_UPSERT_BATCH=8 python3 -m scripts.crawl.run_contracts_90d_pilot \
  --days 592 \
  --checkpoint-dir /var/lib/extra-consultoria/checkpoints/national-2025-canary \
  --allow-cross-run-resume
```

Depois desta PR implantada (só em fronteira de janela):

```bash
python3 -m scripts.crawl.run_contracts_90d_pilot \
  --start-date 2025-01-01 --end-date 2026-08-15 \
  --checkpoint-dir /var/lib/extra-consultoria/checkpoints/national-2025-canary \
  --allow-cross-run-resume
python3 -m scripts.ops.report_national_backfill \
  --checkpoint /var/lib/extra-consultoria/checkpoints/national-2025-canary \
  --start-date 2025-01-01 --end-date 2026-08-15 \
  --origin-main-sha "$(git -C /opt/extra-consultoria rev-parse origin/main)" \
  --host-sha "$(git -C /opt/extra-consultoria rev-parse HEAD)"
```

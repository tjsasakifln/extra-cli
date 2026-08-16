## Outcome

`READY_BEHIND_HUMAN_GATE`

Reconciliação live do backfill nacional PNCP desde 2025-01-01 (#249 / EXTRA-012). Motor já está em `main` (PR #368). Esta PR **não** reimplementa o crawler: pina a identidade do run, publica complete/failed/blocked/retry a partir do checkpoint, e deixa o residual das 7 janelas com writer único já retomado no host.

Não é `VPS_OPERATIONAL`. Não fecha #249. Não faz merge.

## Scope

- Pin de range no runner: `--start-date` / `--end-date` (evita drift `today-days` que quebra as chaves).
- `planned_window_keys`, `resolve_pilot_range`, `resume_action_for_window` no runner já shipped.
- Helper fail-closed `python3 -m scripts.ops.report_national_backfill` (UNKNOWN ≠ 0).
- Evidência pequena em `docs/ops/campaigns/EXTRA-012-PNCP-NATIONAL-BACKFILL-01/`.
- Testes no caminho shipped (`evaluate_window_completion`, `ingest_window` balance, resume-skip, report).

## Out of scope

- Nova arquitetura de crawler / scheduler.
- Fast-forward do SHA do host (`bbc4b6b7` ≠ `820c83b8`).
- Alterar `max_locks_per_transaction` (GUC postmaster).
- Habilitar incremental enquanto o backfill é o writer.
- EXTRA-016 / EXTRA-032 / EXTRA-033 / #242 / PRs #412–#419.
- UX pública, CRM, API genérica.

## Live evidence (host Netcup, 2026-08-16)

| item | valor |
|------|--------|
| `origin/main` | `820c83b82a35aaab0d381f54faa5357b386db1b3` |
| SHA implantado | `bbc4b6b7db295909d773f5a0e1f3314085a2f26c` |
| checkpoint | `/var/lib/extra-consultoria/checkpoints/national-2025-canary` |
| planned | 20 (2025-01-01 → 2026-08-15) |
| complete / failed / blocked / retry | **13 / 7 / 0 / 7** |
| resume | SKIP das 13 complete (duas retomadas) |
| writer atual | `run_contracts_90d_pilot --days 592` + `flock` + `CONTRACTS_UPSERT_BATCH=8` |
| progresso | `20251127_20251226` p=33/369; passou a p~18 que matou o batch 50 |
| freshness | 4 572 994 contratos; `max(data_publicacao_fonte)=2026-08-15` (não é cobertura) |
| job anterior | `partial` exit 3 — **não** prova completude |

Seis janelas antigas não têm `window_results` → reconciliação `UNKNOWN`, não zero.

## Risks

- `max_locks_per_transaction=64` + trigger `fn_capture_contract_snapshot` ainda pode falhar; batch 8 mitiga, não remove o GUC.
- Drift de SHA: não fast-forward no meio da janela.
- `--days 592` no host de hoje pode reabrir a última janela como `20260725_20260816` depois das 7 retries.
- EXTRA-005 / EXTRA-013 sem artefato in-repo; se forem DSN/host/admission, o host **admitiu** nesta sessão.

## Rollback

- Reverter o commit desta PR. O runner antigo (`today-days`) permanece no host até implantar.
- Writer live: `pkill -TERM -f 'run_contracts_90d_pilot --days 592'` — checkpoint preserva completed; partial nunca vira success.

## Refs

- #249
- PR #368 (engine already on main)
- Deps nomeadas EXTRA-005 / EXTRA-013 (sem arquivos in-repo)
- ADR/truth plane: facts, identity, provenance, coverage, freshness, SELECT-only

## Tests / commands executed

```text
git fetch origin main
# origin/main = 820c83b82a35aaab0d381f54faa5357b386db1b3
python3 -m pytest tests/test_pncp_contracts_backfill.py tests/test_contracts_checkpoint_contract.py -q --tb=short
# 18 passed (run 1) / 18 passed (run 2)
python3 -m scripts.ops.report_national_backfill --checkpoint <host snapshot> --start-date 2025-01-01 --end-date 2026-08-15
ruff check scripts/crawl/run_contracts_90d_pilot.py scripts/ops/report_national_backfill.py tests/test_pncp_contracts_backfill.py tests/test_contracts_checkpoint_contract.py
```

## Residual (exact)

1. 7 janelas 2025-11-27→2026-06-24 ainda `failed`/`retry` (writer live, batch 8).
2. SHA host ≠ main; implantar esta PR só em fronteira de janela.
3. Incremental recorrente **não** habilitado.
4. Aumentar `max_locks_per_transaction` continua gate humano/DBA se o batch 8 falhar de novo.
5. #249 permanece **OPEN**.

## Decision

**READY_BEHIND_HUMAN_GATE**

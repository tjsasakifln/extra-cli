## Outcome

`BLOCKED_WITH_WINDOW_LIST`

Reconciliação live do backfill nacional PNCP desde 2025-01-01 (#249 / EXTRA-012). Motor já está em `main` (PR #368). Esta PR **não** reimplementa o crawler: pina a identidade do run, publica complete/failed/blocked/retry a partir do checkpoint, classifica o token terminal, e registra o residual após o retry batch-8 no host.

Não é `VPS_OPERATIONAL`. Não fecha #249. Não faz merge. Não afirma incremental-only.

## Scope

- Pin de range no runner: `--start-date` / `--end-date` (evita drift `today-days` que quebra as chaves).
- `planned_window_keys`, `resolve_pilot_range`, `resume_action_for_window` no runner já shipped.
- Helper fail-closed `python3 -m scripts.ops.report_national_backfill` (UNKNOWN ≠ 0).
- `classify_campaign_terminal` → exatamente `BACKFILL_COMPLETE_INCREMENTAL_ENABLED` ou `BLOCKED_WITH_WINDOW_LIST`.
- Evidência pequena em `docs/ops/campaigns/EXTRA-012-PNCP-NATIONAL-BACKFILL-01/`.
- Testes no caminho shipped (`evaluate_window_completion`, `ingest_window` balance, resume-skip, report, terminal).

## Out of scope

- Nova arquitetura de crawler / scheduler.
- Fast-forward do SHA do host (`bbc4b6b7` ≠ `820c83b8`) no meio da janela.
- Alterar `max_locks_per_transaction` (GUC postmaster).
- Habilitar incremental enquanto o residual do backfill é a autoridade.
- EXTRA-016 / EXTRA-032 / EXTRA-033 / #242 / PRs #412–#419.
- UX pública, CRM, API genérica.

## Live evidence (host Netcup, 2026-08-16T23:26Z)

| item | valor |
|------|--------|
| `origin/main` | `820c83b82a35aaab0d381f54faa5357b386db1b3` |
| SHA implantado | `bbc4b6b7db295909d773f5a0e1f3314085a2f26c` (**sem** implant nesta sessão) |
| checkpoint | `/var/lib/extra-consultoria/checkpoints/national-2025-canary` (byte-copy live) |
| planned | 20 (2025-01-01 → 2026-08-15) |
| complete / failed / blocked / retry | **13 / 7 / 0 / 7** |
| resume | SKIP das complete (dois resumes no retry); `20260725_20260815` não reabriu |
| writer | retry batch-8 **morto** 22:26Z; `partial` exit 3 — **não** prova completude |
| GUC | `max_locks_per_transaction=64` (SELECT no host) |
| freshness | 4 572 996 contratos; `max(data_publicacao_fonte)=2026-08-15` (não é cobertura) |
| token | `BLOCKED_WITH_WINDOW_LIST` |

Seis janelas antigas não têm `window_results` → reconciliação `UNKNOWN`, não zero.  
Chave extra `20260725_20260816` (drift `--days 592`) está `blocked`, **fora** do pin.

## Risks

- `max_locks_per_transaction=64` + trigger `fn_capture_contract_snapshot` falhou de novo em batch 8. Elevar o GUC é gate humano/DBA.
- Drift de SHA: não fast-forward no meio da janela (`current_window=20260725_20260816` p=161).
- `pncp-contracts.timer` dispara Mon 06:03 -03; incremental **não** é a rotina única enquanto o residual existir.
- EXTRA-005 / EXTRA-013 sem artefato in-repo.

## Rollback

- Reverter o commit desta PR. O runner antigo (`today-days`) permanece no host até implantar.
- Writer live já está parado. Checkpoint preserva completed; partial nunca vira success.

## Refs

- #249
- PR #368 (engine already on main)
- Deps nomeadas EXTRA-005 / EXTRA-013 (sem arquivos in-repo)
- ADR/truth plane: facts, identity, provenance, coverage, freshness, SELECT-only

## Tests / commands executed

```text
git fetch origin
# origin/main = 820c83b82a35aaab0d381f54faa5357b386db1b3
# PR HEAD / worktree = 476cac1a72051a86e586d4ae491095ca0bb71ee0
# host SHA = bbc4b6b7db295909d773f5a0e1f3314085a2f26c
python3 -m pytest tests/test_pncp_contracts_backfill.py tests/test_contracts_checkpoint_contract.py tests/test_contracts_pilot_completion.py -q --tb=short
# 66 passed (run 1) / 66 passed (run 2)
python3 -m scripts.ops.report_national_backfill \
  --checkpoint <host-byte-copy> --start-date 2025-01-01 --end-date 2026-08-15 \
  --blocker max_locks_per_transaction
# two runs identical: planned=20 complete=13 failed=7 terminal=BLOCKED_WITH_WINDOW_LIST
ruff check scripts/ops/report_national_backfill.py tests/test_pncp_contracts_backfill.py
```

## Residual (exact)

1. 7 janelas 2025-11-27→2026-06-24 ainda `failed` após retry batch-8 (`max_locks_per_transaction`).
2. SHA host ≠ main; implantar esta PR só em fronteira de janela.
3. Incremental recorrente **não** é o único writer.
4. Aumentar `max_locks_per_transaction` continua gate humano/DBA.
5. #249 permanece **OPEN**.

## Decision

**BLOCKED_WITH_WINDOW_LIST**

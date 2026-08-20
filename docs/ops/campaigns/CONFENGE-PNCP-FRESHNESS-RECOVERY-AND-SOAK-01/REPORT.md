# CONFENGE-PNCP-FRESHNESS-RECOVERY-AND-SOAK-01

**Verdict:** `PNCP_FRESHNESS_STILL_DEGRADED_UNCLOSED_CURRENT_WINDOW_UPSERT_OOM`  
**as_of:** 2026-08-20T21:21:20Z  
**Contrato:** `PNCP_CONTRACT_FRESHNESS/1.0`  
**Host:** `ec-prod` / `159.195.18.88` / `v2202607385716487230`  
**Deployed SHA:** `7ca6a8709e8e7dbf021b2f7aa12fbf4b88684428` (`origin/main`, squash #444 após #443)

`VPS_OPERATIONAL` **não** foi declarado. Soak #248 **não** iniciou.

## Disposition PRs

| PR | Resultado |
|---|---|
| #443 | **merged** squash `43579c84` 2026-08-20T15:55:19Z CI verde |
| #444 | rebased em main+#443; cadence 4h landed na mesma linha; **merged** squash `7ca6a870` 2026-08-20T16:09:24Z CI verde |
| #445 | docs-only do veredito desta campanha — **não** reimplementa #443/#444 |

## Cadence

Capacidade 2026-08-19: sucesso ~21 min, 92/92 páginas, 45703 transformed, 44M RSS, load 0.15 / 8 cores.

Escolha: **every 4h** `OnCalendar=*-*-* 00,04,08,12,16,20:00:00 America/Sao_Paulo` (explícito).  
`systemd-analyze calendar` aceita; max inter-run 4h. `--days 7` mantido (overlap late arrivals; 21 min não é custo material vs 4h).

`LOCK_BUSY`/exit 75: `SuccessExitStatus=75` permanece no unit (não dispara OnFailure em contenção); freshness classifica `LOCK_BUSY_NO_CLOSE` e **nunca FRESH**. Retry = próximo slot 4h + `Persistent=true`.

## Live canary (timer-triggered)

Não foi `systemctl start pncp-contracts.service`.

| Trigger | Quando (local −03) | Resultado |
|---|---|---|
| Persistent catch-up do slot 12:00 após `daemon-reload` | 13:09:53 | FAIL API timeout page 1; janela **não** fechada |
| OnCalendar 16:00 + RandomizedDelay | 16:03:46–16:19:51 | FAIL `out of shared memory` / `max_locks_per_transaction` no upsert page~61/109; transformed=30500 ins=0; janela **não** fechada |
| Próximo | 20:01:34 −03 | agendado |

Checkpoint v2 `/var/lib` `ok=true`, completed ainda `20260807_20260814` + `20260812_20260819`. Failed attempts rebound (`previous_run_ids` inclui 16:09Z e 19:03Z) sem pular janelas concluídas.

Canário SQL: IDs 19/08 presentes; `95782793000154-2-000833/2026` (20/08) **ausente** (`UNCLOSED_CURRENT_WINDOW`).

Live CLI ×2: `status=STALE` `reason_codes=[UNCLOSED_CURRENT_WINDOW, WINDOW_INCOMPLETE]` `health_exit=2`. SLO shipped: `sustainable_hard_guardrail=true`, `sustainable_operational_target=true`, **sem** `CADENCE_CANNOT_MEET_24H`. `check-alerts` emite CRIT freshness com status, closed window, lag, next run, last_error, checkpoint_health.

`max_locks_per_transaction` exige restart do PostgreSQL — **não** executado (fail-closed; sem restore isolado corrente).

## Issues

| Issue | Disposition |
|---|---|
| #241 | **OPEN**. FOUND live `pages_expected==pages_fetched` + requery IDs completa + 19/08 na base. Residual: empty scope devolve HTTP 204/422 → `SCOPE_INCOMPLETE`, não `ZERO_CONFIRMED`. Sem nova arquitetura. |
| #319 | **CLOSE**. Autoridade `/var/lib/.../contracts_full.json`; leftover `/opt/.../incremental/` inventariado (sha256 `d93bff71…`, 14/08) e arquivado em `/var/lib/extra-consultoria/archives/contracts-checkpoints-opt-leftover/20260820T155500Z` (source intacto, sem delete). Resume SIGTERM 16/08 em `previous_run_ids` + rebind dos attempts 20/08 sem skip das completed. |
| #277 / backup | Local dump diário fresco (2026-08-20 sha256 `397d8570…` 3.1G). Off-host Storage Box PostgreSQL daily **stale 2026-07-23**. `extra-joint-offsite-backup` **não instalado**. `extra_restore_proof` (4.48M vs prod 4.59M, created 2026-08-01) ≠ restore corrente. |
| #248 | **SOAK_BLOCKED_BY_OFFSITE_BACKUP_STALE_AND_UNCLOSED_WINDOW**. Sem `SOAK_STARTED_AT`. |
| #249 | permanece closed; não reexecutado |

## Veredito

`PNCP_FRESHNESS_STILL_DEGRADED_UNCLOSED_CURRENT_WINDOW_UPSERT_OOM`

Cadence 4h está no host e o timer dispara. A janela corrente não fecha: persistência morre em `fn_capture_contract_snapshot` / `max_locks_per_transaction`. HARD ≤24h de **janela fechada** não foi reestabelecido.

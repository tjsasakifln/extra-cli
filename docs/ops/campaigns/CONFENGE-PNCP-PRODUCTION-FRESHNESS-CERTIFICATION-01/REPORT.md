# CONFENGE-PNCP-PRODUCTION-FRESHNESS-CERTIFICATION-01

**Verdict:** `FRESHNESS_DEGRADED`
**as_of:** 2026-08-20T14:10:00Z
**Contrato:** `PNCP_CONTRACT_FRESHNESS/1.0`
**Host:** `ec-prod` / `159.195.18.88` / `v2202607385716487230`
**Deployed SHA:** `9c5e7d47f99902d9d97cf479aefbba8cd391a14d` (= `origin/main` no fetch desta campanha)

Não é `FRESHNESS_CERTIFIED`: o timer Mon/Wed/Fri não sustenta 95% ≤ 6h nem o guardrail 100% ≤ 24h, e o lag medido da última janela fechada é ~28,8h.
Não é `BLOCKED_ON_LIVE_HOST_EVIDENCE`: o host respondeu; o canário PNCP→PostgreSQL rodou.

`VPS_OPERATIONAL` **não** foi declarado.

## CURRENT_STATE

Path incremental já existente (não recriado):

| Peça | Onde |
|---|---|
| Incremental | `scripts/crawl/run_contracts_incremental.py --days 7` |
| Checkpoint v2 | `scripts/crawl/contracts_checkpoint_contract.py` |
| Recusa worktree | `scripts.contracts_truth.resolve_checkpoint_dir` → `/var/lib/extra-consultoria` |
| Timer | `deploy/systemd/pncp-contracts.{service,timer}` `OnCalendar=Mon,Wed,Fri *-*-* 06:00:00` **sem UTC** (hora local −03) |
| Tabela | `pncp_supplier_contracts` (4 591 752 linhas) |
| Gate legado | `scripts/freshness_gate.py` SLA contratos default **24d** — demasiado frouxo; **não** usado como autoridade desta campanha |

Issues:

| Issue | Estado | Residual |
|---|---|---|
| #241 | OPEN | live pagination/zero no host — canário desta campanha cobre amostra nacional de contratos, não por ente |
| #248 | OPEN | soak `NOT_STARTED` (PR #367 só gates). Ver `soak-prep.json` |
| #249 | CLOSED | backfill histórico; não reaberto |
| #319 | OPEN | path guards merged (#371); host já tem checkpoint v2 durável + `previous_run_ids` com resume SIGTERM 2026-08-16 |
| #351 #285 #341 #343 | OPEN | **reutilizar PR #443**; não reimplementados |

Timer live no fetch:

- last success: 2026-08-19 06:00:20 −03 → 09:21:14Z, janela `20260812_20260819`, pages 92/92, expected=fetched=45703
- 2026-08-17: `BLOCKED` `source_population_drift` (ainda em `blocked_windows`)
- 2026-08-15: `LOCK_BUSY` exit 75 (systemd `SuccessExitStatus=75` — unidade “success” sem fechar janela)
- next: Fri 2026-08-21 06:00 −03
- checkpoint durável sha256 `963550a83f54d53d476babf9a47c91dbc574a29e9805b3e95935d217600daa83`
- leftover worktree `/opt/extra-consultoria/data/contracts_checkpoints/incremental/` (stale 14/08, archive 16/08) — path de produção não usa

## CHANGES

1. Produtor `scripts/ops/pncp_contract_freshness.py` (`PNCP_CONTRACT_FRESHNESS/1.0`): status fail-closed `FRESH|DEGRADED|STALE|UNKNOWN` contra SLO desejado 6h/24h, com bloco honesto `sustainable_*=false` e reason codes nominais.
2. `scripts/check-alerts.py` passa a emitir alerta de freshness no host (`/opt` + `/var/lib/extra-consultoria` ou `PNCP_FRESHNESS_ALERTS=1`). Timer ativo / HTTP 200 / uma linha recente não viram FRESH.
3. Testes focados em `tests/test_pncp_contract_freshness.py` (+ extensões checkpoint/window). Sem MagicMock de `real_db`. Sem baixar threshold.
4. Artefato `freshness.json` gerado pelo CLI shipped a partir do snapshot live. Runbook idempotente.

Não alterado: crawler, schema, `pncp-contracts.timer`, backfill, adapters, PR #443.

## LIVE_EVIDENCE

API PNCP `tamanhoPagina=50` (legal):

| Dia | HTTP | totalRegistros | pages_expected (pág. 1) |
|---|---|---|---|
| 2026-08-19 | 200 | 9892 | 198 |
| 2026-08-20 | 200 | 3037 | 61 |

Spot-check `contrato_id` no PostgreSQL da VPS:

| ID PNCP | Dia | Na base? | Objeto |
|---|---|---|---|
| `83102277000152-2-000663/2026` | 19 | sim | ARMÁRIOS DE METAL… (bate) |
| `00394460005887-2-004356/2026` | 19 | sim | Alienação… (bate) |
| + 3 IDs Receita 19/08 | 19 | sim | bate |
| `95782793000154-2-000833/2026` | 20 | **não** | `UNCLOSED_CURRENT_WINDOW` |
| + 4 IDs 20/08 | 20 | **não** | mesma reason |

Lag amostra 19/08: publicação 00:00:47Z → `ingested_at`/`first_seen_at` 09:21:09Z ≈ 9,3h (> 6h, < 24h).
Lag operacional agora: última janela fechada 09:21:14Z → as_of 14:10Z ≈ **28,8h** → `STALE` + `LAG_ABOVE_HARD_GUARDRAIL`.

Checkpoint: fora do Git; `logical_job_id=pncp-contracts-incremental`; resume 2026-08-16 em `previous_run_ids` (`extra013-resume`, `extra013-after-sigterm`). Janela bloqueada `20260810_20260817` está coberta pelas lookbacks concluídas (não é incomplete material).

## RESIDUAL

- Cadência Mon/Wed/Fri **não** foi acelerada (objetivo proibia reescrever o scheduler “para limpar arquitetura”). SLO 6h/24h permanece desejado e falha de forma explícita.
- #248 soak continua `NOT_STARTED`. Evidência técnica preparada em `soak-prep.json`; veredito humano intacto.
- #241 residual por ente (este canário é nacional/janela, não `ente_id`).
- Leftover worktree em `/opt/.../data/contracts_checkpoints/incremental/` — arquivar no host, não apagar daqui.
- #351/#285/#341/#343 → PR #443.
- Interrupção controlada nova **não** foi disparada em produção (já há evidência SIGTERM 16/08; wipe de checkpoint proibido).

## DoD (evidência)

| Pergunta | Resposta |
|---|---|
| Última janela PNCP fechada? | `20260812_20260819` @ 2026-08-19T09:21:14Z |
| Lag atual? | ~28,8h |
| Janelas incompletas? | `blocked_windows`: `20260810_20260817` (overlapped, não material) |
| Incremental automático? | sim, `pncp-contracts.timer` enabled |
| Checkpoints duráveis? | sim, `/var/lib/extra-consultoria/checkpoints/contracts/` |
| Reboot/restart retoma? | código + live `previous_run_ids` 16/08; testes `resume_units` |
| Contrato recente do PNCP na base? | sim (19/08); 20/08 ausente até sexta (`UNCLOSED_CURRENT_WINDOW`) |
| Breach observável? | `check-alerts` + `--health` exit 2 |

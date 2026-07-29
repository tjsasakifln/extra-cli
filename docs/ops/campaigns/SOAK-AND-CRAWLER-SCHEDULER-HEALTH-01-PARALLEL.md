# SOAK-AND-CRAWLER-SCHEDULER-HEALTH-01-PARALLEL

| Campo | Valor |
|-------|--------|
| **Campanha** | `SOAK-AND-CRAWLER-SCHEDULER-HEALTH-01-PARALLEL` |
| **Papel** | Terminal 3 — SRE / auditoria independente (read-only) |
| **Data UTC** | 2026-07-29 (~09:37–12:55 America/Sao_Paulo) |
| **Estado terminal** | **`SCHEDULERS_FAILED`** |
| **SHA clone / VPS** | `d05d4c3de152b562493715f114e0a387fcb63dc3` (main) |
| **Host** | `v2202607385716487230` (`ssh ec-prod`) |
| **Mutações** | **Nenhuma** (NO_CODE / NO_SERVICE_RESTART / NO_TIMER_CHANGE / NO_PR nesta campanha) |

Paralelo a:

- **Terminal 1:** entrega / convergência DOD / `weekly_cycle`
- **Terminal 2:** cobertura dual editais + contratos

---

## 1. North star

> Provar ou rejeitar, de maneira independente, que a operação está saudável e capaz de manter cobertura ≥95% **sem intervenção manual diária**.

**Veredito:** **REJEITADA.**

| Gate | Resultado |
|------|-----------|
| `CONTRACTS_SOAK_PASS` | **false** |
| `OPEN_TENDERS_SOAK_PASS` | **false** |
| `SCHEDULER_HEALTH_PASS` | **false** |
| `GLOBAL_SOAK_HEALTH_PASS` | **false** |

---

## 2. Isolamento da auditoria

- Clone separado: `$HOME/extra-parallel/SOAK-AND-CRAWLER-SCHEDULER-HEALTH-01-PARALLEL/repo` (detached `origin/main`)
- Evidências locais (não versionadas nesta PR): `$HOME/extra-parallel/.../evidence/` e `report/`
- **CONCURRENT_OPERATION_OBSERVED:** Terminal 1 com  
  `weekly_cycle --strict --contracts-incremental` + flock em `/run/lock/extra-weekly.lock`  
  (consultas pesadas ao DB evitadas)

---

## 3. Achados críticos

### 3.1 Contratos — `pncp-contracts.service` quebrado após 2026-07-23

| Disparo | Resultado | InvocationID (journal `_SYSTEMD_INVOCATION_ID`) |
|---------|-----------|--------------------------------------------------|
| 2026-07-23 ~17:12 | **success** | `f533c022585544b7a4cdb9ccb9d66c05` |
| 2026-07-24 06:02 | **fail** | `89f50da34a6d4c95a0b01d93e2b6b9bf` |
| 2026-07-27 06:01 | **fail** | `2b12328221f34436b64f42a756427ef6` |
| 2026-07-29 06:02 | **fail** | `7182d84ad8bb40f6913213f86fa16600` |

**Causa:** `ValueError: checkpoint run_id mismatch`  
`existing='contracts-90d-20260723T201229Z-4da85aaee0'` vs novo `run_id` a cada disparo.

Timer `pncp-contracts.timer`: **enabled + active** (MWF 06:00 local).  
Service: **failed** (`Result=exit-code`).  
“Timer active ≠ crawler saudável.”

Único `run_id` de sucesso correlacionável:  
`contracts-90d-20260723T201229Z-4da85aaee0`.

### 3.2 Soak de contratos (reconstrução independente)

Arquivos diários em `/var/lib/extra-consultoria/backfill/soak/` (23–29/07): **7/7 presentes**.

| Métrica | Valor |
|---------|-------|
| Dias com PASS independente (automático) | **1/7** (somente 2026-07-23) |
| Dias FAIL | 6 |
| Progresso | **1/7** |
| Estado de progresso | `SOAK_PENDING_REAL_TIME_AFTER_CHECKPOINT_FIX` |
| Tracker `complete` | **false** (service soak exit 2) |

**Primeira data honesta de conclusão (se fix + sucesso a partir de Sex 2026-07-31):** **2026-08-06**.  
Alternativa (primeiro sucesso só Seg 2026-08-03): **2026-08-09**.

Freshness do tracker usa `max(data_publicacao, data_assinatura)` — **proxy inadequado** de freshness operacional do crawler.

### 3.3 Editais — timers de crawl desabilitados

**Disabled / inactive** (sem `ExecMainStart` no período auditado):

- `extra-crawl-pncp.timer`, `pncp-crawl-inc.timer`, `pncp-crawl-full.timer`
- `extra-crawl-ciga-ckan.timer`, `extra-crawl-ciga-dom.timer`, `dom-sc-crawl.timer`
- `extra-crawl-sc-compras.timer`, `sc-compras-crawl.timer`
- `extra-crawl-doe-sc.timer` e demais crawlers auxiliares

`extra-weekly.timer` **enabled** (Mon 03:30) — gap pior caso ≈ **168h >> SLA 24h** de open tenders.

Último `extra-weekly.service`: **exit-code 2** em 2026-07-27 (HTTP **429** + gate).

Artifact dual coverage open_tenders em **2026-07-23** (stale na auditoria):  
`coverage_pct=100` com `success_zero_count=1092`, `data_presence_pct=0`,  
`dual_gate_status=NOT_EVALUATED`, `pipeline_success=false`.  
**Cobertura ≥95% operacional nos 7 dias: não provada.**

### 3.4 Cron tradicional

Sem crons de projeto. Sem duplicata systemd×cron.  
`/etc/cron.d`: apenas NON_PROJECT (fstrim, sysstat, e2scrub).

### 3.5 Locks / overlap

- Units canônicas usam `flock --nonblock`.
- **Risco:** `pncp-contracts.lock` ≠ `extra-weekly.lock` — writers de contratos **não serializados**.
- Pares legados/complementares (`extra-crawl-pncp` vs `pncp-crawl-inc`, etc.) **não ativos** (disabled).

### 3.6 Alerting

**ALERTING_PARTIAL:** `OnFailure=extra-onfailure@%n` existe; `WEBHOOK_URL` **unset** → só journal.

### 3.7 Units repo × VPS

- 36 units com SHA match
- **15** services com content mismatch vs main
- **only_installed (não versionadas no repo):** `extra-contracts-soak.timer` / `.service`

Validação estática local `python3 -m scripts.ops.validate_systemd`: pass (não prova runtime).

### 3.8 Tracker gaps (não corrigidos nesta campanha)

`scripts/ops/campaign_soak_tracker.py` pode contribuir a **falso verde**:

- `health_ok` sem exigir `last_contracts_result=success` / run_id / coverage
- freshness por data de publicação
- `date.today()` local (não UTC)
- não valida enabled / next trigger

Evidência parcial: dia **2026-07-24** com `health_ok=true` no tracker apesar do fire 06:02 falhar.

---

## 4. Failed units no momento da auditoria

```text
extra-contracts-soak.service  failed
extra-weekly.service          failed
pncp-contracts.service        failed
```

Timers enabled/active (6):  
`extra-check-alerts`, `extra-health-check`, `extra-contracts-soak`,  
`extra-db-backup`, `pncp-contracts`, `extra-weekly`.

---

## 5. Ações recomendadas (por owner)

### TERMINAL 1

| Sev | Ação |
|-----|------|
| CRITICAL | Destravar checkpoint incremental (`contracts-90d-20260723T201229Z-4da85aaee0`); restaurar `pncp-contracts` a success em disparo automático |
| CRITICAL | **Não** promover DOD/soak com service failed |
| HIGH | Investigar weekly exit 2 + HTTP 429 |
| MEDIUM | Reconciliar units instaladas vs main (15 mismatches) |

### TERMINAL 2

| Sev | Ação |
|-----|------|
| HIGH | Remedir dual capability **após** crawlers reais |
| HIGH | Não tratar summary 2026-07-23 / success_zero massivo como prova de 95% operacional |

### AÇÃO MANUAL NA VPS

| Sev | Ação |
|-----|------|
| HIGH | Configurar `WEBHOOK_URL` para OnFailure externo |
| HIGH | `enable --now` timers canônicos de editais **só** com plano de carga/rate-limit (não feito nesta campanha) |
| — | `systemctl reset-failed` **somente** após correção real |

### PR FUTURO

| Sev | Ação |
|-----|------|
| HIGH | Endurecer tracker (success, run_id, ingest freshness, coverage, UTC) |
| HIGH | Lock compartilhado entre `pncp-contracts` e `weekly --contracts-incremental` |
| MEDIUM | Versionar `extra-contracts-soak.{timer,service}` no repo |
| MEDIUM | Política: uma família de timers por fonte |

### NENHUMA AÇÃO (esta campanha Terminal 3)

Não reiniciar services, não limpar locks, não editar checkpoint, não promover DOD.

---

## 6. Revalidação read-only (futuro)

```bash
ssh -o BatchMode=yes ec-prod 'systemctl show pncp-contracts.service -p Result,ExecMainStatus,InvocationID,ExecMainStartTimestamp'
ssh -o BatchMode=yes ec-prod 'journalctl -u pncp-contracts.service --since yesterday --no-pager | tail -40'
ssh -o BatchMode=yes ec-prod 'ls -la /var/lib/extra-consultoria/backfill/soak/; for f in /var/lib/extra-consultoria/backfill/soak/*.json; do echo ===== $f; cat "$f"; done'
ssh -o BatchMode=yes ec-prod 'systemctl --failed --no-pager'
ssh -o BatchMode=yes ec-prod 'systemctl list-timers --all --no-pager | grep -E "extra-|pncp-"'
```

---

## 7. Conclusões objetivas (15)

1. Soak legítimo como prova de saúde? **Não.**  
2. Sete dias consecutivos reais? Arquivos **sim**; saudáveis automáticos **não** (1/7).  
3. Tracker pode falso verde? **Sim.**  
4. Timer contratos enabled/active? **Sim.**  
5. Últimas execuções automáticas e bem-sucedidas? Automáticas **sim**; bem-sucedidas **não** desde 24/07.  
6. Editais no SLA 24h? **Não** (timers disabled; weekly >> 24h).  
7. Crons duplicando timers? **Não.**  
8. Timers legados ativos? **Não** (disabled).  
9. Concorrência lock/checkpoint? Locks distintos; **risco de dual writer** contracts.  
10. Cobertura ≥95% no período? **Não provada.**  
11. Scheduler sobrevive reboot? Catch-up parcial observado (boot 2026-07-23); Persistent=false em health/backup.  
12. Alertas? **PARTIAL** (webhook unset).  
13. Correção imediata necessária? **Sim** (checkpoint CRITICAL) — fora deste terminal.  
14. Owners: ver §5.  
15. Encerramento honesto do soak: **2026-08-06** (ou **2026-08-09**) após fix + 7 dias saudáveis.

---

## 8. Artefatos da sessão (fora do git)

Gerados em `$HOME/extra-parallel/SOAK-AND-CRAWLER-SCHEDULER-HEALTH-01-PARALLEL/`:

| Path | Conteúdo |
|------|----------|
| `report/final-report.md` | Relatório partes A–N |
| `report/result.json` | Gates + estado terminal |
| `report/contracts-soak-days.json` | 7 dias com invocation_id sourced |
| `report/contracts-soak-progress.json` | Progresso 1/7 + datas |
| `evidence/pncp-contracts-invocation-journal.txt` | Journal JSON com `_SYSTEMD_INVOCATION_ID` |
| `evidence/scheduler-health-matrix.csv` | Matriz de timers |
| `evidence/blockers.json` | B1–B8 |

**Não versionados** (política de artifacts / logs de journal). Checksums e conclusões estão neste doc.

---

## 9. Anti-confusão (regra final da campanha)

| Não confundir | Com |
|---------------|-----|
| timer active | crawler saudável |
| service success pontual | dados / coverage válidos |
| freshness de publicação | freshness de crawl |
| arquivo diário de soak | soak real saudável |
| execução manual / weekly | automação do timer de contratos |
| zero failed units (após clear) | saúde do sistema |
| `complete=true` no tracker | prova suficiente |

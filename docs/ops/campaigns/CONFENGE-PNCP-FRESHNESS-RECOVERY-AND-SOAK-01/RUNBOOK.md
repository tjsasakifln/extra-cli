# Runbook — PNCP contracts freshness recovery

Campanha: `CONFENGE-PNCP-FRESHNESS-RECOVERY-AND-SOAK-01`
Contrato: `PNCP_CONTRACT_FRESHNESS/1.0`
Host de record: `ec-prod` / `159.195.18.88`

Não refaz backfill. Não zera checkpoint. Não apaga leftover em `/opt`.

## 1. Contrato local

```bash
python3 -m scripts.ops.pncp_contract_freshness \
  --from-snapshot tests/fixtures/pncp_contract_freshness/cadence-4h.snapshot.json \
  --json --health
```

Exit: `0` FRESH, `1` DEGRADED, `2` STALE/UNKNOWN.

Cadence shipped: `OnCalendar=*-*-* 00,04,08,12,16,20:00:00 America/Sao_Paulo`.
`LOCK_BUSY` (exit 75) não é janela fechada; retry = próximo slot 4h.
`SuccessExitStatus=75` evita OnFailure em contenção esperada — freshness não trata como sucesso.

## 2. Timer no host

```bash
ssh ec-prod 'timedatectl; systemctl cat pncp-contracts.timer; \
  systemd-analyze calendar "*-*-* 00,04,08,12,16,20:00:00 America/Sao_Paulo"; \
  systemctl list-timers pncp-contracts.timer --all'
```

Próximo elapse tem de ser ≤4h (mais RandomizedDelay 300s). Timezone do spec é `America/Sao_Paulo`.

## 3. Ciclo automático (não `systemctl start` isolado)

Esperar `LastTriggerUSec` avançar pelo timer. Journal `WINDOW_*` / `incremental done`.
Checkpoint: `/var/lib/extra-consultoria/checkpoints/contracts/`.

Deploy controlado 2026-08-20: SHA `7ca6a870`. Timer 4h disparou às 16:03 −03. Janela `20260813_20260820` **não** fechou: upsert `out of shared memory` (`max_locks_per_transaction` / trigger `fn_capture_contract_snapshot`). Corrigir GUC exige restart do PostgreSQL — fora deste runbook até haver restore isolado corrente.

## 4. Alertas

`extra-check-alerts.timer` → `scripts/check-alerts.py`. Details JSON: status, last closed window, lag, unresolved, next run, last error, backup freshness, checkpoint health.

Live 2026-08-20T21:21Z: CRIT `PNCP contracts freshness STALE` (`UNCLOSED_CURRENT_WINDOW`, `WINDOW_INCOMPLETE`).

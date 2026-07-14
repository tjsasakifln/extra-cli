# Deploy — Design Técnico (v2.0)

> Gerado pelo Writer em 2026-07-13 | doc_level: completo | Base: 249340d
> **Fontes brownfield:** plano-mestre-fechamento-gaps-extra-consultoria.md §20, epic-technical-debt.md

## Interface

| Símbolo | Assinatura | Retorno | Observação |
|---------|-----------|---------|------------|
| `provision-vps.sh` | `(VPS_IP, REPO_URL, REPO_BRANCH)` implícito via env | exit code | 10 steps idempotentes, root-only |
| `install.sh` | `(nenhum)` | exit code | Instalação local de dependências |
| `ufw-rules.sh` | `(TRUSTED_IPS)` via variáveis | exit code | 177 linhas, regras UFW |
| `backup-database.sh` | `(DATABASE_URL, STORAGE_BOX)` via env | exit code + backup file | pg_dump custom + gzip |
| `restore-database.sh` | `(DATABASE_URL, backup_file)` | exit code | Full/schema-only/data-only |
| `healthcheck.py` | `(DATABASE_URL, API_KEYS)` via env | exit code + JSON | DB, disco, API keys, crawlers |
| `collect-metrics.py` | `(DATABASE_URL)` via env | JSON metrics file | Métricas de ingestão |
| `check-alerts.py` | `(metrics_file)` | exit code | Threshold-based alerts |
| systemd timers (x20) | systemd calendar | exit code 0/1 | OnCalendar + RandomizedDelaySec |

## Fluxo Principal

1. **Provisionamento inicial** (`provision-vps.sh:1-405`): VPS Ubuntu 24.04 LTS → pacotes sistema → usuário `extra-consultoria` → SSH hardening (porta 2222) → firewall UFW → PostgreSQL 16 + tuning → clone repo → migrations → systemd timers → fail2ban
2. **Operação contínua**: systemd timers disparam serviços Python conforme `OnCalendar=` + `RandomizedDelaySec=300`
3. **Monitoramento**: `collect-metrics.py` → `check-alerts.py` → alertas se thresholds excedidos
4. **Backup**: `extra-db-backup.timer` → `extra-db-backup.service` → pg_dump → gzip → Storage Box (Hetzner)
5. **OnFailure**: `onfailure@.service` → POST JSON para `$WEBHOOK_URL` com `%n` (nome da unit que falhou)

## Fluxos Alternativos

- **Provisionamento não-interativo:** `REPO_URL` e `REPO_BRANCH` customizáveis via env vars (`provision-vps.sh:22-24`)
- **Restore parcial:** `restore-database.sh` suporta flags `--schema-only`, `--data-only`, `--list` (`restore-database.sh`)
- **Saúde degradada:** `healthcheck.py` emite exit code ≠ 0 + JSON com detalhes por componente

## Dependências

| Componente | Relação | Como usa |
|------------|--------|----------|
| PostgreSQL 16 | Hard dependency | Tuning: shared_buffers=1GB, effective_cache=2GB, work_mem=64MB (CX22) |
| Hetzner Cloud CX22 | Infra atual | 2 vCPU, 4GB RAM, 40GB SSD, Storage Box para backup |
| systemd (Linux) | Hard dependency | 20 timer/service pairs, `OnFailure=`, `RandomizedDelaySec=` |
| UFW | Firewall | `ufw-rules.sh:1-177`: deny incoming, allow SSH:2222, node-exporter:9100, trusted IPs |
| fail2ban | Hardening | `fail2ban-jail.conf:1-90`: jail PostgreSQL:54399, maxretry=5, bantime=3600s |
| Prometheus Node Exporter | Métricas sistema | Instalado via apt, porta 9100 |
| sshfs | Backup | Monta Storage Box para transferência de backups |

## Decisões de Design Identificadas

| Decisão | Evidência no código | Confiança |
|---------|---------------------|-----------|
| PostgreSQL direto, sem API intermediária | `provision-vps.sh:step6`, ADR-001 | 🟢 |
| systemd timers em vez de Redis/Celery | ADR-002, 20 timer files em `deploy/systemd/` | 🟢 |
| Escalonamento com offsets de 30min + RandomizedDelaySec=300 | `deploy/systemd/*.timer` | 🟢 |
| OnFailure webhook para alertas | `onfailure@.service`, `extra-onfailure@.service` | 🟢 |
| SSH porta 2222, root key-only, sem password/X11 | `provision-vps.sh:step3` | 🟢 |
| scp + gzip para Storage Box, retention 7 diários + 4 semanais | `backup-database.sh` | 🟢 |
| Provisionamento idempotente (10 steps com guardas) | `provision-vps.sh`, cada step verifica estado antes de aplicar | 🟢 |

## Estado Interno

Não mantém estado próprio. Estado do sistema é delegado a:
- **systemd**: status de timers/services (`systemctl list-timers`)
- **PostgreSQL**: dados de aplicação
- **Storage Box**: backups versionados por data

## Observabilidade

| Componente | Sinal | Destino |
|------------|-------|---------|
| `extra-collect-metrics.service` | Métricas de ingestão (runtime, registros, erros) | `output/health/latest.json` |
| `extra-check-alerts.service` | Thresholds: fonte stale > SLA, run partial, coverage drop | exit code ≠ 0 + stderr |
| `extra-health-check.service` | DB conn, disco livre, API keys, crawler status | stdout JSON |
| Prometheus Node Exporter | CPU, RAM, disco, rede | Porta 9100 |
| `onfailure@.service` | Unit `%n` falhou | POST JSON → `$WEBHOOK_URL` |
| journald | Todos os serviços Type=oneshot | `journalctl -u extra-*` |

## Riscos e Lacunas

- 🟢 Deploy atual é local-first. Provisionamento VPS (`provision-vps.sh`) existe mas **não é o estado corrente** — o sistema roda localmente com PostgreSQL local.
- 🔴 **LACUNA (plano-mestre §20):** Deploy para Hetzner/Supabase é classificado como EPIC P2 e só deve começar após todos os gates P0 passarem. O script `provision-vps.sh` está pronto mas a migração não deve ser executada até que: cobertura ≥95%, editais sem stale, schema único, contratos atualizáveis, concorrentes validados, preço com semântica correta.
- 🔴 **LACUNA (plano-mestre §17):** Orquestração local reproduzível (EPIC P1-04) ainda não implementada. Faltam: `Makefile`, `docker-compose.local.yml`, `scripts/bootstrap_local.sh`, `scripts/run_local_pipeline.sh`.
- 🟡 A lista de 20 systemd timers pode divergir do estado real conforme fontes são adicionadas/removidas. O arquivo `deploy/systemd/` deve ser tratado como template, não como inventário estático.
- 🟡 `install.sh` (2.6KB) parece ser um wrapper de instalação local. Propósito exato e relação com `provision-vps.sh` inferidos — podem existir sobreposições.

# Runbook Operacional — Extra Consultoria

> **Criado em:** 2026-07-11
> **Propósito:** Procedimentos operacionais para operacao e manutencao do sistema de inteligencia em licitacoes.
> **Story:** TD-6.1 -- Documentacao Operacional
> **Responsavel:** @devops (Gage) / @dev (Dex)

## Sumario

- [Visao Geral do Sistema](#visao-geral-do-sistema)
- [Como Executar Crawl Manualmente](#como-executar-crawl-manualmente)
- [Como Verificar Status dos Crawlers](#como-verificar-status-dos-crawlers)
- [Como Executar Purge](#como-executar-purge)
- [Como Verificar Logs de Backup](#como-verificar-logs-de-backup)
- [Como Restaurar Backup](#como-restaurar-backup)
- [Como Aplicar Migrations](#como-aplicar-migrations)
- [Como Executar Healthcheck](#como-executar-healthcheck)
- [Como Verificar Cobertura](#como-verificar-cobertura)
- [Como Verificar Freshness Critico](#como-verificar-freshness-critico)
- [Monitoramento de Logs](#monitoramento-de-logs)
- [Runbook de Rollback](#runbook-de-rollback)
- [Runbook de Schema Drift](#runbook-de-schema-drift)
- [Runbook de Cobertura Abaixo de 95%](#runbook-de-cobertura-abaixo-de-95)

---

## Visao Geral do Sistema

O sistema Extra Consultoria e uma plataforma CLI de inteligencia em licitacoes publicas que monitora o universo canônico de **1.093 entes** (raio 200 km; ver glossário — 2.085 é referência estadual legada, não denominador de cobertura) em 5+ fontes de dados abertos.

Nota operacional desta fase:

- o projeto pode operar com datalake local legado
- cobertura isolada nao prova utilidade consultiva
- antes de qualquer analise, deve-se verificar freshness das fontes criticas
- fontes criticas atuais: `pncp` para editais e `contracts` para historico contratual

### Arquitetura Resumida

```
[Fontes Externas]                    [VPS em Nuvem]
  PNCP API ──┐                      ┌──────────────────────┐
  DOM-SC  ───┤                      │  PostgreSQL 16        │
  PCP API ───┤──► Crawlers ────────►│  pncp_raw_bids        │
  ComprasGov ┤    (Python 3.12)     │  sc_public_entities   │
  TCE-SC  ───┤                      │  entity_coverage      │
  Transparen─┘                      └──────────────────────┘
                                            │
                                     [Storage Externo]
                                     backups/postgresql/
                                       daily/ (7 dias)
                                       weekly/ (4 semanas)
```

### Componentes Principais

| Componente | Localizacao | Funcao |
|------------|-------------|--------|
| `monitor.py` | `scripts/crawl/monitor.py` | Orquestrador de crawlers (entry point) |
| `orchestrator.py` | `scripts/crawl/orchestrator.py` | Pipeline de ingestao (crawl -> transform -> upsert -> match) |
| `entity_matcher.py` | `scripts/matching/entity_matcher.py` | Entity matching 3-level cascade |
| `healthcheck.py` | `scripts/healthcheck.py` | Healthcheck unificado |
| `backup-database.sh` | `scripts/backup-database.sh` | Backup PostgreSQL |
| `restore-database.sh` | `scripts/restore-database.sh` | Restore PostgreSQL |
| `apply-migrations.sh` | `scripts/apply-migrations.sh` | Aplicacao de migrations v2 |

---

## Como Executar Crawl Manualmente

### Pre-requisitos

- Acesso SSH ao VPS (`ssh -p 2222 -i ~/.ssh/extra-consultoria-prod extra-consultoria@{VPS_IP}`)
- Python 3.12 e dependencias instaladas
- `.env` configurado com `LOCAL_DATALAKE_DSN`

### Crawl Individual por Fonte

```bash
# Crawl completo da fonte PNCP (modo full)
python scripts/crawl/monitor.py --source pncp --mode full

# Crawl incremental (ultimos 3 dias)
python scripts/crawl/monitor.py --source pncp --mode incremental

# Crawl de outras fontes
python scripts/crawl/monitor.py --source dom_sc --mode full
python scripts/crawl/monitor.py --source pcp --mode full
python scripts/crawl/monitor.py --source compras_gov --mode full
python scripts/crawl/monitor.py --source tce_sc --mode full
python scripts/crawl/monitor.py --source transparencia --mode full
python scripts/crawl/monitor.py --source contracts --mode full
```

### Crawl Multi-Source

```bash
# Crawl completo de todas as fontes
python scripts/crawl/monitor.py --source all --mode full

# Crawl incremental de todas as fontes
python scripts/crawl/monitor.py --source all --mode incremental
```

### Dry Run (sem persistir dados)

```bash
# Simula o crawl sem fazer upsert no banco
python scripts/crawl/monitor.py --source pncp --mode dry-run
```

### Crawl com Filtro Geografico

```bash
# Apenas orgaos dentro do raio de 200km de Florianopolis
python scripts/crawl/monitor.py --source pncp --mode full --within-200km-only
```

### Crawl via systemd (execucao agendada)

```bash
# Executar o servico manualmente (mesmo que o timer)
sudo systemctl start pncp-crawl-full.service

# Verificar resultado
sudo journalctl -u pncp-crawl-full.service --no-pager -n 50
```

### Crawl via VPS Production

```bash
ssh ec-prod
cd /opt/extra-consultoria
source .env
python3 scripts/crawl/monitor.py --source all --mode incremental
```

---

## Como Verificar Status dos Crawlers

### Via systemd (recomendado)

```bash
# Listar todos os timers do sistema
systemctl list-timers 'extra-*' 'pncp-*' 'coverage-*'

# Verificar status de um servico especifico
systemctl status pncp-crawl-full.service

# Verificar se o timer esta ativo
systemctl is-active pncp-crawl-full.timer
```

### Via Healthcheck Unificado

```bash
# Healthcheck completo (humano)
python scripts/healthcheck.py

# Healthcheck em JSON (para monitoramento)
python scripts/healthcheck.py --json

# Saida silenciosa em JSON
python scripts/healthcheck.py --json --quiet
```

### Via Logs do Crawl

```bash
# Ultimas 30 linhas do crawl mais recente
journalctl -u pncp-crawl-full.service --no-pager -n 30

# Logs em tempo real
journalctl -u pncp-crawl-full.service -f

# Logs de um periodo especifico
journalctl -u pncp-crawl-full.service --since "2026-07-10 00:00:00" --until "2026-07-11 00:00:00"
```

### Coverage Report

```bash
# Relatorio de cobertura (sem crawl)
python scripts/crawl/monitor.py --report-coverage
```

### Crawl Summary

```bash
# Verificar ultimas execucoes no banco
psql $LOCAL_DATALAKE_DSN -c "
  SELECT source, status, started_at, finished_at,
         records_fetched, records_upserted, entities_covered
  FROM ingestion_runs
  ORDER BY started_at DESC
  LIMIT 20;
"
```

### Crawlers Configurados

| Timer | Fonte | Schedule | Servico |
|-------|-------|----------|---------|
| `pncp-crawl-full.timer` | PNCP | Diario 05:00 UTC | `pncp-crawl-full.service` |
| `pncp-crawl-inc.timer` | PNCP | 11:00, 17:00, 23:00 UTC | `pncp-crawl-inc.service` |
| `dom-sc-crawl.timer` | DOM-SC | 06:00, 14:00, 22:00 UTC | `dom-sc-crawl.service` |
| `pcp-crawl.timer` | PCP | Diario 07:00 UTC | `pcp-crawl.service` |
| `compras-gov-crawl.timer` | ComprasGov | Diario 08:00 UTC | `compras-gov-crawl.service` |
| `tce-sc-crawl.timer` | TCE-SC | Diario 09:00 UTC | `tce-sc-crawl.service` |
| `transparencia-crawl.timer` | Transparencia | Diario 10:00 UTC | `transparencia-crawl.service` |
| `extra-crawl-doe-sc.timer` | DOE-SC | 07:00, 19:00 UTC | `extra-crawl-doe-sc.service` |
| `pncp-contracts.timer` | Contratos | Diario 12:00 UTC | `pncp-contracts.service` |
| `pncp-enrich.timer` | Enrichment | Apos crawl | `pncp-enrich.service` |
| `pncp-purge.timer` | Purge | Diario 07:00 UTC | `pncp-purge.service` |
| `coverage-report.timer` | Coverage | Diario 09:00 UTC | `coverage-report.service` |
| `coverage-report-weekly.timer` | Coverage Semanal | Seg 09:00 UTC | `coverage-report-weekly.service` |
| `pncp-report-weekly.timer` | Relatorio Semanal | Seg 07:00 UTC | `pncp-report-weekly.service` |
| `extra-db-backup.timer` | Backup | Diario 06:00 UTC | `extra-db-backup.service` |
| `extra-health-check.timer` | Healthcheck | A cada 5 min | `extra-health-check.service` |

---

## Como Executar Purge

### O Que o Purge Faz

Remove registros antigos da tabela `pncp_raw_bids` com base na data de publicacao. O limite padrao e de 400 dias (`INGESTION_PURGE_GRACE_DAYS`).

### Purge Manual

```bash
# Executar purge com o limite padrao (400 dias)
python -c "
import psycopg2, os
conn = psycopg2.connect(os.getenv('LOCAL_DATALAKE_DSN'))
cur = conn.cursor()
cur.execute('SELECT purge_old_records(400)')
conn.commit()
cur.close()
conn.close()
print('Purge concluido')
"
```

### Purge via systemd

```bash
# Executar o servico de purge manualmente
sudo systemctl start pncp-purge.service

# Verificar resultado
sudo journalctl -u pncp-purge.service --no-pager -n 20
```

### Verificar Purge

```bash
# Contar registros antes/depois do purge
psql $LOCAL_DATALAKE_DSN -c "
  SELECT COUNT(*) FROM pncp_raw_bids
  WHERE data_publicacao < NOW() - INTERVAL '400 days';
"
```

### Configuracao do Purge

A janela de retencao e configurada via `INGESTION_PURGE_GRACE_DAYS` no `.env`:

```bash
# .env
INGESTION_PURGE_GRACE_DAYS=400
```

---

## Como Verificar Logs de Backup

### Log Principal

O backup gera logs em `/var/log/backup-database.log` no formato estruturado:

```bash
# Ultimas 20 linhas do log
tail -20 /var/log/backup-database.log

# Log completo
cat /var/log/backup-database.log

# Monitorar em tempo real
tail -f /var/log/backup-database.log
```

### Exemplo de Log de Sucesso

```
[2026-07-11 03:00:01 -0300] [INFO] === Inicio da execucao (modo: backup) ===
[2026-07-11 03:00:02 -0300] [INFO] Montando Storage Box em /mnt/storage-box
[2026-07-11 03:00:05 -0300] [INFO] Storage Box montada com sucesso
[2026-07-11 03:00:06 -0300] [INFO] Iniciando pg_dump para pncp_datalake-2026-07-11.dump.gz
[2026-07-11 03:02:15 -0300] [INFO] Backup concluido: pncp_datalake-2026-07-11.dump.gz | Tamanho: 1.2G | Duracao: 129s
[2026-07-11 03:02:15 -0300] [INFO] Integridade do gzip verificada: OK
[2026-07-11 03:02:16 -0300] [INFO] Retention concluida | Diarios: 5 | Semanais: 3
[2026-07-11 03:02:17 -0300] [INFO] === Backup concluido com sucesso ===
```

### Verificar via systemd

```bash
# Status do timer de backup
systemctl status extra-db-backup.timer

# Logs do servico de backup
journalctl -u extra-db-backup.service --no-pager -n 30

# Ultimas execucoes
systemctl list-timers --all | grep extra-db
```

### Verificar Backup na Storage Box

```bash
# Montar Storage Box (se necessario)
sshfs -p 23 -o reconnect,ServerAliveInterval=15,ServerAliveCountMax=3 \
  u123456@u123456.your-storagebox.de:backups/postgresql \
  /mnt/storage-box

# Listar backups diarios
ls -lh /mnt/storage-box/daily/

# Listar backups semanais
ls -lh /mnt/storage-box/weekly/

# Verificar integridade dos backups
for f in /mnt/storage-box/daily/*.dump.gz; do
  echo -n "$(basename $f): "
  gzip -t "$f" && echo "OK" || echo "CORROMPIDO"
done
```

### JSON Estruturado do Backup

Cada backup gera uma linha JSON para ingestao externa:

```json
{
  "event": "backup",
  "timestamp": "2026-07-11T06:00:01+00:00",
  "file": "pncp_datalake-2026-07-11.dump.gz",
  "size_bytes": 1287654321,
  "duration_sec": 129,
  "status": "success"
}
```

Extraia com: `grep LOG_JSON /var/log/backup-database.log | sed 's/.*LOG_JSON: //'`

---

## Como Restaurar Backup

### Restauracao Completa

```bash
# 1. Identificar o backup mais recente
BACKUP_FILE=$(ls -t /mnt/storage-box/daily/pncp_datalake-*.dump.gz | head -1)
echo "Restaurando: $BACKUP_FILE"

# 2. (Opcional) Dropar e recriar database
psql -h localhost -U postgres -c "DROP DATABASE IF EXISTS pncp_datalake;"
psql -h localhost -U postgres -c "CREATE DATABASE pncp_datalake;"

# 3. Restaurar
./scripts/restore-database.sh "$BACKUP_FILE"

# 4. Verificar dados restaurados
psql -d pncp_datalake -c "SELECT count(*) FROM information_schema.tables;"
psql -d pncp_datalake -c "SELECT count(*) FROM pncp_raw_bids;"
psql -d pncp_datalake -c "SELECT count(*) FROM sc_public_entities;"
```

### Restauracao Seletiva

```bash
# Listar tabelas no backup
./scripts/restore-database.sh backup.dump.gz --list | grep TABLE

# Apenas schema (estrutura, sem dados)
./scripts/restore-database.sh backup.dump.gz --schema-only

# Apenas dados (schema existente)
./scripts/restore-database.sh backup.dump.gz --data-only

# Tabela especifica
./scripts/restore-database.sh backup.dump.gz --table pncp_raw_bids
```

### Restauracao para Ambiente Local (Dev)

```bash
# 1. Copiar backup da Storage Box para maquina local
rsync -avz -e "ssh -p 23" \
  u123456@u123456.your-storagebox.de:backups/postgresql/daily/ \
  /tmp/pg-restore/

# 2. Restaurar localmente
LOCAL_DATALAKE_DSN=postgresql://postgres:local@localhost:5432/pncp_datalake \
  ./scripts/restore-database.sh /tmp/pg-restore/pncp_datalake-*.dump.gz
```

---

## Como Aplicar Migrations

### Migration System v2

O sistema usa um script `apply-migrations.sh` com tracking via tabela `_migrations`.

### Aplicar Migrations Pendentes

```bash
# Aplicar todas as migrations pendentes (usa DSN do .env)
bash scripts/apply-migrations.sh

# Com DSN explicito
bash scripts/apply-migrations.sh --dsn "postgresql://postgres:senha@localhost:5432/pncp_datalake"

# Simular sem aplicar (dry-run)
bash scripts/apply-migrations.sh --dry-run
```

### Verificar Status das Migrations

```bash
# Status detalhado
bash scripts/apply-migrations.sh --status

# Consultar diretamente no banco
psql $LOCAL_DATALAKE_DSN -c "SELECT * FROM public._migrations ORDER BY version;"
```

### Estrutura das Migrations

As migrations estao em `supabase/migrations/` (formato numerado):

```
supabase/migrations/
  001_pncp_raw_bids.sql
  002_pncp_supplier_contracts.sql
  003_enriched_entities.sql
  ...
  017_td-2.3_matched_entity_id_index.sql
  _migrations.sql       (tabela de tracking)
```

### Adicionar Nova Migration

```bash
# 1. Criar arquivo SQL com numero sequencial
touch supabase/migrations/018_nova_funcionalidade.sql

# 2. Escrever o SQL
cat > supabase/migrations/018_nova_funcionalidade.sql << 'EOF'
ALTER TABLE pncp_raw_bids ADD COLUMN nova_coluna TEXT;
EOF

# 3. Aplicar
bash scripts/apply-migrations.sh
```

### Migrations Legado (db/migrations/)

O diretorio `db/migrations/` contem migrations v1 (arquivos SQL simples). Para aplicar:

```bash
# Aplicar manualmente as migrations v1
psql $LOCAL_DATALAKE_DSN -f db/migrations/013_td-1.1_gin_index_objeto_contrato.sql
```

---

## Como Executar Healthcheck

### Healthcheck Unificado

```bash
# Saida humana
python scripts/healthcheck.py

# Saida JSON (para integracao com monitoring)
python scripts/healthcheck.py --json

# Modo silencioso (apenas JSON no stdout)
python scripts/healthcheck.py --json --quiet
```

### O Healthcheck Verifica

| Check | O Que Testa | Severidade |
|-------|-------------|------------|
| `db` | Conexao PostgreSQL via psql | CRITICAL |
| `api_keys` | Variaveis de ambiente obrigatorias | CRITICAL |
| `crawlers` | Timers systemd ativos | WARNING |
| `disk` | Uso de disco (< 80% OK, > 90% CRITICAL) | WARNING/CRITICAL |

### Healthcheck via systemd

```bash
# O healthcheck roda automaticamente a cada 5 minutos
systemctl status extra-health-check.timer

# Ver ultimo resultado
journalctl -u extra-health-check.service --no-pager -n 20
```

---

## Como Verificar Cobertura

### Coverage Report

```bash
# Relatorio rapido (le dados do banco, nao faz crawl)
python scripts/crawl/monitor.py --report-coverage
```

## Como Verificar Freshness Critico

Este passo e obrigatorio antes de usar o sistema para:

- editais abertos
- contratos historicos
- concorrentes e vencedores
- analises consultivas derivadas do datalake local

```bash
# Gate unico de freshness local-first
python scripts/freshness_gate.py
```

Artefatos gerados:

- `output/readiness/freshness-gate.json`
- `output/readiness/freshness-gate.csv`

Interpretacao dos status:

- `fresh`: fonte critica provou execucao recente e persistencia dentro do SLA
- `stale`: houve execucao ou dados, mas fora do SLA
- `never`: nao existe prova de execucao bem-sucedida

SLAs padrao nesta fase:

- `pncp`: 24h
- `contracts`: 576h (24 dias)

Overrides opcionais:

```bash
FRESHNESS_SLA_PNCP_HOURS=24
FRESHNESS_SLA_CONTRACTS_HOURS=576
python scripts/freshness_gate.py
```

Regra operacional:

- exit code `0`: fontes criticas frescas
- exit code `2`: nao usar a base local como prova consultiva
- exit code `1`: corrigir `LOCAL_DATALAKE_DSN` ou disponibilidade do PostgreSQL

### Consulta Direta no Banco

```bash
# Cobertura geral
psql $LOCAL_DATALAKE_DSN -c "
  SELECT COUNT(*) FILTER (WHERE is_covered) AS covered,
         COUNT(*) FILTER (WHERE NOT is_covered) AS uncovered,
         ROUND(100.0 * COUNT(*) FILTER (WHERE is_covered) / COUNT(*), 1) AS pct
  FROM entity_coverage;
"

# Entidades nao cobertas
psql $LOCAL_DATALAKE_DSN -c "
  SELECT e.id, e.razao_social, e.municipio, e.cnpj_8
  FROM sc_public_entities e
  LEFT JOIN entity_coverage ec ON e.id = ec.entity_id
  WHERE ec.is_covered IS NOT TRUE
  ORDER BY e.municipio
  LIMIT 20;
"
```

---

## Monitoramento de Logs

### Logs do Sistema (journald)

```bash
# Todos os logs do sistema Extra Consultoria
journalctl --user -p info _COMM=python3 | grep extra-consultoria

# Logs de falha
journalctl -p err _COMM=python3 | grep -i "extra\|crawl\|pncp" | tail -30

# Logs do onfailure (notificacao de falha)
journalctl -u extra-onfailure@.service --no-pager -n 20
```

### Arquivos de Log

| Log | Localizacao | Conteudo |
|-----|-------------|----------|
| Backup | `/var/log/backup-database.log` | Execucoes do backup |
| Systemd journal | `journalctl -u <servico>.service` | Logs de cada servico |

### Metricas via Banco

```bash
# Ultimas 24h de ingestao
psql $LOCAL_DATALAKE_DSN -c "
  SELECT source, status, records_fetched, records_upserted,
         started_at, finished_at
  FROM ingestion_runs
  WHERE started_at > NOW() - INTERVAL '24 hours'
  ORDER BY started_at DESC;
"

# Tamanho do banco
psql $LOCAL_DATALAKE_DSN -c "
  SELECT pg_size_pretty(pg_database_size('pncp_datalake')) AS tamanho;
"

# Total de bids no sistema
psql $LOCAL_DATALAKE_DSN -c "
  SELECT source, COUNT(*) AS total
  FROM pncp_raw_bids
  GROUP BY source
  ORDER BY total DESC;
"
```

---

## Referencias

- `docs/ops/backup.md` -- Documentacao detalhada do backup
- `docs/ops/troubleshooting.md` -- Guia de troubleshooting
- `docs/ops/vps-access.md` -- Acesso ao VPS
- `docs/ops/vps-provisioning.md` -- Provisionamento do VPS
- `docs/architecture/system-architecture.md` -- Arquitetura completa do sistema
- `.env.example` -- Template de variaveis de ambiente

---

> **Ultima atualizacao:** 2026-07-11
> **Story:** TD-6.1 -- Documentacao Operacional

## Runbook de Rollback

Quando uma migration, crawl ou deploy local corrompe dados:

1. **Parar writers** — não rodar `monitor.py` / golden path em paralelo.
2. **Identificar artefato** — commit, `run_id`, dump em `backups/` ou `output/`.
3. **Restore** — `bash scripts/restore-database.sh <dump>` em **banco separado** antes de substituir.
4. **Reconciliação** — reexecutar schema audit + contagens chave (entities, contracts, opportunities).
5. **Git** — reverter commits da fatia na branch de feature (`git revert`); nunca force-push em `main`.
6. **DoD** — desmarcar `[x]` se a prova não se sustenta mais.

Comandos:
```bash
bash scripts/backup-database.sh
bash scripts/restore-database.sh backups/postgresql/daily/<latest>.dump.gz
python3 -m scripts.ops.schema_audit  # se disponível
```

## Runbook de Schema Drift

Sintoma: views/tabelas canônicas ausentes, migrations à frente/atrás do código.

1. `python3 -m scripts.ops.schema_audit` (ou `bash scripts/verify-schema-divergence.sh`).
2. Listar migrations aplicadas vs `db/migrations/`.
3. Aplicar apenas migrations pendentes: `bash scripts/apply-migrations.sh` (ou fluxo canônico do projeto).
4. Reexecutar queries críticas; se falhar, rollback do schema (dump pré-migration).
5. Registrar gap em `docs/ops/ledger/` se objects required estiverem ausentes.

Fail-closed: não marcar schema audit verde com `missing_required` não vazio.

## Runbook de Cobertura Abaixo de 95%

A meta DoD é **95% operacional** (não sinal comercial).

1. Gerar relatório: `python3 -m scripts.coverage.coverage_contract_cli` (ou pipeline session).
2. Confirmar denominador = 1.093 (ou valor canônico da seed).
3. Exportar gaps nominais (`entity-source-gaps.jsonl`).
4. Classificar blockers: `pending_collection`, `pending_live_verification`, `fragmented`, `blocked_external`.
5. **Não** reduzir denominador; **não** promover sinal comercial a cobertura.
6. Priorizar coleta multi-fonte nos gaps com ROI (PNCP, SC Compras, CIGA/DOM públicos).
7. Re-medir após fatia; se <95%, item DoD permanece aberto.

Comando de honestidade:
```bash
python3 -m scripts.coverage.coverage_contract_cli --json | python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('metrics',{}).get('operational_source_coverage',{}))"
```

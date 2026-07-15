# Cloud Deployment Plan — Extra Consultoria

> Plano operacional de deploy em nuvem.
> Versão: 1.0 — 2026-07-15
> Status: Proposed (pré-implantação)

---

## 1. Arquitetura Inicial (Estágio 1 — Máquina Única)

```
┌─────────────────────────────────────────────────────────────┐
│  Ambiente Local (Desenvolvedor)                              │
│                                                              │
│  Claude Code CLI ←→ SSH, Git, GitHub CLI, Ansible           │
│  (NÃO instalado na VPS)                                      │
└──────────────────────────┬──────────────────────────────────┘
                           │ SSH + Ansible
                           ▼
┌──────────────────────────────────────────────────────────────┐
│  VPS de Produção (Ubuntu 24.04 LTS)                          │
│                                                               │
│  PostgreSQL 16 ──── Dados relacionais, índices, views         │
│  Python 3.12 ───── Crawlers, pipelines, relatórios            │
│  systemd ───────── Serviços e timers (44 unidades)            │
│  Backup ────────── pg_dump → storage externo criptografado    │
│  Monitoramento ─── Logs estruturados, alertas, health checks  │
│  Segurança ─────── SSH key-only, UFW, fail2ban, non-root      │
└──────────────────────────────────────────────────────────────┘
```

### Dimensionamento de referência

| Recurso | Referência Inicial |
|---------|-------------------|
| RAM | 32 GB |
| CPU | Dedicada (boa disponibilidade sustentada) |
| Armazenamento | ~1 TB NVMe (expansível) |
| PostgreSQL | 16 |
| SO | Ubuntu 24.04 LTS |

---

## 2. Responsabilidades

### Claude Code (ambiente local)

- Criar, revisar e executar comandos de deploy
- Executar playbooks Ansible
- Interagir com Git e GitHub CLI
- Executar diagnósticos e verificações pós-deploy
- NÃO está instalado na VPS
- NÃO é requisito para operação dos serviços

### VPS (infraestrutura remota)

- Executar PostgreSQL 16
- Executar crawlers e pipelines Python
- Executar tarefas agendadas (systemd timers)
- Gerar relatórios
- Executar rotinas de backup
- Executar monitoramento operacional
- NÃO precisa do Claude Code
- NÃO precisa de Node.js
- NÃO precisa de Docker (exceto se justificado)

---

## 3. Fluxo de Deploy

O deploy é determinístico e repetível. Não depende de sessão interativa do Claude Code na VPS.

```
1. Alteração desenvolvida localmente
2. Testes locais (pytest, ruff, mypy, bandit)
3. Push ou pull request
4. Gates do GitHub Actions (lint, type-check, test, security, dependency-audit)
5. Deploy por script ou pipeline controlado
6. Sincronização do código (rsync / git pull)
7. Instalação das dependências travadas (pip install -r requirements.txt)
8. Execução das migrations (db/setup_db.sh)
9. Smoke tests (health_check.py, freshness_gate.py)
10. Execução do freshness gate (freshness_gate.py)
11. Reinício controlado dos serviços ou timers (systemctl restart)
12. Health check (health_check.py)
13. Rollback em caso de falha (git checkout versão anterior + restore backup se necessário)
```

### Anti-padrões

- ❌ "Acessar a VPS e pedir ao Claude para fazer deploy"
- ❌ Sessão SSH interativa como processo de deploy
- ❌ Edição manual de arquivos na VPS
- ❌ Deploy sem smoke test
- ❌ Deploy sem rollback definido

---

## 4. Acesso Local via CLI

O desenvolvedor interage com a VPS usando:

```bash
# Acesso SSH
ssh ec-prod

# Execução remota de comandos
ssh ec-prod "systemctl status postgresql"
ssh ec-prod "journalctl -u extra-crawl-pncp.service -n 30"

# Ansible (configuração idempotente)
ansible-playbook -i inventory.yml playbooks/site.yml

# Git + GitHub (local)
git push origin main
gh pr create --title "feat: ..."

# Diagnóstico remoto
ssh ec-prod "python scripts/health_check.py"
ssh ec-prod "python scripts/freshness_gate.py"
```

---

## 5. Migrations

```bash
# Na VPS, via SSH ou Ansible
cd /opt/extra-consultoria
bash db/setup_db.sh "$LOCAL_DATALAKE_DSN"

# Verificação pós-migration
psql "$LOCAL_DATALAKE_DSN" -c "SELECT version, name, applied_at FROM _migrations ORDER BY version DESC LIMIT 5"
```

---

## 6. Smoke Tests Pós-Deploy

```bash
# Health check completo
python scripts/health_check.py

# Freshness das fontes críticas
python scripts/freshness_gate.py

# Status dos timers
systemctl list-timers 'extra-*' 'pncp-*' 'dom-sc-*' 'coverage-*'

# Últimos logs de crawl
journalctl -u extra-crawl-pncp.service -n 10 --no-pager

# Conexão com banco
psql "$LOCAL_DATALAKE_DSN" -c "SELECT count(*) FROM sc_public_entities"
```

---

## 7. Rollback

```bash
# 1. Reverter código para versão anterior
cd /opt/extra-consultoria
git checkout <commit-anterior>

# 2. Reinstalar dependências da versão anterior
pip install -r requirements.txt

# 3. Se necessário, restaurar banco do backup mais recente
/usr/local/bin/restore-database.sh /mnt/storage-box/daily/pncp_datalake-$(date +%F).dump.gz

# 4. Reiniciar serviços
systemctl restart 'extra-*' 'pncp-*'

# 5. Verificar saúde
python scripts/health_check.py
```

---

## 8. Backups

### Estratégia (desacoplada de provedor)

- Backup fora da máquina principal
- Backup criptografado
- Retenção diária (7) e semanal (4)
- Armazenamento externo (object storage, storage box ou volume separado)
- Possibilidade de point-in-time recovery (WAL archiving quando aplicável)
- Ferramentas: pg_dump (atual) → pgBackRest ou WAL-G (futuro)
- Testes periódicos de restauração
- Registro do último backup válido
- Alertas de falha

### O que NÃO é backup

- Snapshots do provedor não substituem backup do PostgreSQL
- Réplicas não substituem backup (protegem contra falha de hardware, não contra erro lógico ou corrupção)
- Storage Box da Hetzner é uma implementação atual, não um requisito arquitetural

### Implementação atual

O script `scripts/backup-database.sh` implementa backup via `pg_dump --format=custom` com destino em storage externo montado via sshfs. Esta implementação é funcional e adequada ao estágio atual. A evolução para pgBackRest ou WAL-G é recomendada quando PITR for necessário.

---

## 9. Observabilidade

### Requisitos operacionais

| Métrica | Forma de Coleta |
|---------|----------------|
| Uso de disco | `health_check.py` (a cada 30min) |
| Crescimento diário do banco | `collect-metrics.py` (a cada 60min) |
| Duração dos crawlers | `ingestion_runs` (registrado por execução) |
| Falhas dos timers | `check-alerts.py` (a cada 15min) + OnFailure webhook |
| Atraso de coleta | `freshness_gate.py` (sob demanda / agendado) |
| Freshness por fonte | `freshness_gate.py` |
| Respostas 403, 429, 5xx | Logs dos crawlers + `check-alerts.py` |
| Latência das fontes | `collect-metrics.py` |
| Dead tuples / autovacuum | PostgreSQL pg_stat_user_tables |
| Falhas de backup | `check-alerts.py` + `BACKUP_NOTIFY_CMD` |
| Último backup válido | `check-alerts.py` |
| Testes de restauração | Procedimento manual mensal (a automatizar) |
| Falhas de migrations | `db/setup_db.sh` exit code + ledger |
| Saúde dos serviços | `health_check.py` + `systemctl list-timers` |
| Capacidade livre em disco | `health_check.py` |

### Stack de monitoramento

Estágio inicial: logs estruturados (JSON no journald) + alertas (webhook/email) + scripts de health check. Sem necessidade de Prometheus, Grafana ou ELK no primeiro momento.

---

## 10. Segurança

### Baseline

| Aspecto | Configuração |
|---------|-------------|
| Acesso SSH | Apenas por chave (ed25519) |
| Login root direto | Desabilitado |
| Usuário de deploy | `extra-consultoria` (non-root) |
| Firewall | UFW (default deny, apenas SSH) |
| PostgreSQL | Não exposto publicamente (localhost apenas) |
| Secrets | Fora do Git (`.env` gitignored) |
| `.env` | Não versionado |
| Privilégio mínimo | Cada serviço roda com o usuário necessário |
| Backups | Criptografados em trânsito (SSH) |
| Deploy | Credenciais restritas |
| Acesso ao banco | Túnel SSH, rede privada ou Tailscale |
| Rotação de chaves | Documentada, não automatizada |
| Logs | Sem exposição de credenciais ou DSNs completos |

---

## 11. Teste da API do PNCP em Múltiplas Regiões

### Pré-condição para contratação de VPS estrangeira

Antes de contratar infraestrutura fora do Brasil, executar:

```bash
# Em cada máquina de teste (BR, US-East, EU opcional):
python scripts/crawl/monitor.py --source pncp --mode full --uf SC --days 3

# Registrar:
# - Status HTTP (200, 403, 429, 5xx)
# - Latência por requisição
# - Timeouts
# - Quantidade de registros retornados
# - Paginação (total de páginas percorridas)
# - Consistência do schema (campos presentes, tipos)
# - Horário do teste
```

### Critérios de sucesso

- Mesma quantidade de registros entre BR e US-East (tolerância: ±5%)
- Sem 403 ou bloqueios geográficos no US-East
- Latência adicional aceitável (US-East vs BR)
- Schema consistente entre regiões

---

## 12. Raw Data, PDFs e Anexos

### Separação arquitetural

| Tipo | Armazenamento | Exemplo |
|------|--------------|---------|
| Dados relacionais | PostgreSQL | Campos consultáveis, índices, views |
| Payloads brutos (JSON) | PostgreSQL (JSONB) ou object storage | Resposta original da API |
| Arquivos e PDFs | Object storage / filesystem externo | Editais, anexos |
| Metadados de arquivos | PostgreSQL | URI, hash, tamanho, content-type, fonte, timestamps |

**PDFs e anexos não devem ser armazenados diretamente no PostgreSQL.** A direção arquitetural é object storage ou armazenamento externo, mantendo no PostgreSQL apenas metadados e referências.

Esta separação não é implementada nesta tarefa. O armazenamento atual de PDFs e payloads brutos permanece como está.

---

## 13. Referências

- ADR-007: Cloud Hosting Strategy (`docs/architecture/adr/ADR-007-cloud-hosting-strategy.md`)
- ADR-008: Infrastructure as Code Strategy (`docs/architecture/adr/ADR-008-infrastructure-as-code-strategy.md`)
- VPS Production Readiness Audit: `docs/audits/vps-production-readiness-2026-07.md`
- Backup: `docs/ops/backup.md`
- Monitoring: `docs/ops/monitoring.md`
- VPS Access: `docs/ops/vps-access.md`

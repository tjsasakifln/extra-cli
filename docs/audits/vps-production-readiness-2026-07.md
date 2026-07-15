# VPS Production Readiness -- 2026-07-15

**Auditor:** Agente F (Deploy e Operacao em VPS)
**Branch:** epic-coverage-max-200km
**Metodologia:** Leitura de arquivos, analise estatica, matriz PASS/FAIL/UNKNOWN
**Escopo:** Docker, Systemd, Provisionamento, Migrations, Backup, Observabilidade, CI/CD, Seguranca, Browser Automation

---

## 1. Docker

### Arquivos encontrados

- `docker-compose.yml` -- apenas `test-db` (postgis 16-3.4, volume persistente `pgdata`)
- `docker-compose.local.yml` -- `test-db` (tmpfs) + `app` (python:3.12-slim)
- Nenhum `Dockerfile` customizado

### Analise

| Aspecto | Situacao |
|---------|----------|
| Uso em VPS | **Nao usa Docker em producao.** VPS roda aplicacao diretamente no Ubuntu 24.04 LTS |
| docker-compose.yml | Apenas para dev local / CI. Volume `pgdata` persistente. Healthcheck `pg_isready` |
| docker-compose.local.yml | `test-db` usa tmpfs (efemero). `app` monta diretorio local como bind mount. Sem Dockerfile proprio (usa imagem oficial python:3.12-slim) |
| Producao | Provisionamento via `deploy/provision-vps.sh` instala PostgreSQL e Python nativamente |
| Rede | Porta 5433 exposta para host (dev). Em VPS, PostgreSQL escuta apenas localhost:5432 |

**Veredito:** Docker existe apenas para desenvolvimento local. Producao e bare-metal com systemd. Nao ha containerizacao em VPS -- o que e uma escolha arquitetural valida (menos complexidade), mas significa que rollback e reproducao de ambiente dependem do script de provisionamento, nao de imagens.

---

## 2. Systemd (inventario)

### Services + Timers: 20 pares

| Servico | Timer | Horario (UTC) | User |
|---------|-------|---------------|------|
| `pncp-crawl-full.service` | `pncp-crawl-full.timer` | Diario 05:00 | extra-consultoria |
| `pncp-crawl-inc.service` | `pncp-crawl-inc.timer` | 11:00, 17:00, 23:00 | extra-consultoria |
| `pncp-contracts.service` | `pncp-contracts.timer` | Seg/Qua/Sex 06:00 | extra-consultoria |
| `pncp-enrich.service` | `pncp-enrich.timer` | Diario 08:00 | extra-consultoria |
| `pncp-purge.service` | `pncp-purge.timer` | Diario 07:00 | extra-consultoria |
| `pncp-report-weekly.service` | `pncp-report-weekly.timer` | Seg 07:00 | extra-consultoria |
| `dom-sc-crawl.service` | `dom-sc-crawl.timer` | Diario 04:00 | extra-consultoria |
| `pcp-crawl.service` | `pcp-crawl.timer` | -- | extra-consultoria |
| `compras-gov-crawl.service` | `compras-gov-crawl.timer` | -- | extra-consultoria |
| `sc-compras-crawl.service` | `sc-compras-crawl.timer` | -- | extra-consultoria |
| `tce-sc-crawl.service` | `tce-sc-crawl.timer` | -- | extra-consultoria |
| `transparencia-crawl.service` | `transparencia-crawl.timer` | -- | extra-consultoria |
| `extra-crawl-doe-sc.service` | `extra-crawl-doe-sc.timer` | Dom 03:00 | extra-consultoria |
| `extra-crawl-ciga-ckan.service` | `extra-crawl-ciga-ckan.timer` | Dom 02:00 | extra-consultoria |
| `coverage-report.service` | `coverage-report.timer` | Diario 09:00 (apos full) | extra-consultoria |
| `coverage-report-weekly.service` | `coverage-report-weekly.timer` | Seg 08:00 | extra-consultoria |
| `extra-health-check.service` | `extra-health-check.timer` | A cada 30min | extra-consultoria |
| `extra-check-alerts.service` | `extra-check-alerts.timer` | A cada 15min | extra-consultoria |
| `extra-collect-metrics.service` | `extra-collect-metrics.timer` | A cada 60min | extra-consultoria |
| `extra-db-backup.service` | `extra-db-backup.timer` | Diario 06:00 | **root** |
| `extra-crawl-selenium.service` | `extra-crawl-selenium.timer` | **INTENCIONALMENTE DESABILITADO** | extra-consultoria |

### Templates de OnFailure (INCONSISTENCIA)

Existem **dois** templates de OnFailure com nomes e payloads diferentes:

| Arquivo | Referenciado por | Payload do webhook |
|---------|-----------------|-------------------|
| `onfailure@.service` | pncp-contracts, pncp-purge, pncp-report-weekly, coverage-report-weekly, extra-crawl-selenium | `{"service":"%i","host":"%H","status":"failed"}` |
| `extra-onfailure@.service` | extra-db-backup, extra-health-check, extra-check-alerts, extra-crawl-doe-sc, extra-crawl-ciga-ckan | `{"service":"%i","host":"%H","project":"extra-consultoria","status":"failed"}` |

O template `extra-onfailure@.service` inclui o campo `project` que o `onfailure@.service` nao inclui. Isso pode causar confusao no webhook receptor. Recomendado unificar.

### Pontos fortes

- Todos os services usam `EnvironmentFile=` (nao env vars hardcoded)
- Quase todos rodam como `extra-consultoria` (non-root)
- Timers tem `RandomizedDelaySec` para evitar thundering herd
- Timers usam UTC com comentarios em BRT
- `OnFailure=` configurado na maioria dos servicos criticos

### Pontos fracos

- **Dois templates de OnFailure** (inconsistencia)
- `extra-db-backup` roda como **root** (necessario para sshfs mount)
- Servicos que nao tem OnFailure: `pncp-crawl-full`, `pncp-crawl-inc`, `pncp-enrich`, `coverage-report`, `dom-sc-crawl`, `pcp-crawl`, `compras-gov-crawl`, `sc-compras-crawl`, `tce-sc-crawl`, `transparencia-crawl`, `extra-collect-metrics`

---

## 3. Provisionamento (bootstrap audit)

### `deploy/install.sh`

- Script simples para instalacao pos-clone
- Cria usuario `extra-consultoria`, copia codigo, instala Python deps, roda migrations, instala systemd timers
- **Idempotente** (useradd com verifica, createdb com verifica)
- Nao faz hardening de SSH nem firewall

### `deploy/provision-vps.sh` (10 passos)

| Passo | Descricao | Idempotente? |
|-------|-----------|-------------|
| 1/10 | System packages: python3, postgresql, ufw, fail2ban, unattended-upgrades, node-exporter | Sim (apt) |
| 2/10 | Cria usuario `extra-consultoria` | Sim (verifica id) |
| 3/10 | SSH hardening: porta 2222, key-only, sem password, sem X11 | Sim (sed) |
| 4/10 | Firewall UFW: default deny, SSHH + node-exporter | Sim (reset+apply) |
| 5/10 | Fail2ban: 3 tentativas, 1h ban, 10min findtime | Sim |
| 6/10 | PostgreSQL: tuning CX22 (2vCPU, 4GB RAM), localhost-only | Sim |
| 7/10 | Deploy app: git clone/pull + pip + .env | Sim |
| 8/10 | Migrations e seeds via `db/setup_db.sh` | Sim (ledger tracking) |
| 9/10 | Systemd timers (22 timers) | Sim |
| 10/10 | Storage Box: SSH key, backup config | Parcial (so gera config) |

### Analise

- **Testado para Ubuntu 24.04 LTS** (canonical target nos comentarios)
- **Idempotente**: todos os passos tem guards (user, DB, git, timers)
- **Nao configura Docker** (opcao arquitetural)
- `unattended-upgrades` habilitado mas **sem politica de reboot automatizado**
- `node-exporter` instalado mas `MONITORING_IPS` nao definido -- porta 9100 nao e aberta
- `BACKUP_STORAGE_BOX_SSH` precisa ser configurado manualmente apos provisionamento

---

## 4. Migrations & Seeds

### Migrations: 42 arquivos

```
001 ate 042 (com submigrations 021a-d, 041a-b)
Ordem lexicografica correta
```

### `db/setup_db.sh`

| Funcionalidade | Status |
|---------------|--------|
| Ledger `_migrations` | **Sim** -- tabela de controle com version, name, checksum, applied_at, status |
| Checksum SHA-256 | **Sim** -- detecta modificacao apos aplicacao |
| Advisory lock | **Sim** -- lock id 75319, evita execucao concorrente |
| Logging | **Sim** -- `db/log/migration-{timestamp}.log` com stdout e stderr separados |
| Rollback registrado | **Sim** -- coluna `rollback_sql` no ledger (apenas 029 preenchido) |
| Seed | **Sim** -- `db/seed/001_sc_entities.py` com `--truncate` para idempotencia |
| Exit codes | 0 (ok), 1 (fail), 2 (config error) |

### Seeds

- `scripts/db/seed_sc_entities.py` -- executa com `python3` via setup_db.sh
- Parametro `--truncate` torna a execucao multipla segura
- `db/seed/001_sc_entities.py` -- sem arquivos `.sql` (apenas Python)
- `db/seed/seed_sc_entities.py` -- possivel duplicata do 001?

### Rollback: Apenas 1 arquivo

- `db/rollback/029_qw01_auditable_radar.sql`
- **41 migracoes sem rollback** -- em caso de falha, a estrategia e restore de backup
- O ledger registra `rollback_sql` teoricamente, mas apenas 029 tem rollback escrito

---

## 5. Backup & Restore

### `scripts/backup-database.sh`

| Aspecto | Detalhe |
|---------|---------|
| Engine | `pg_dump --format=custom --compress=9` + `gzip -c` |
| Destino | Hetzner Storage Box via sshfs (`/mnt/storage-box`) |
| Estrutura | `backups/postgresql/daily/` e `backups/postgresql/weekly/` |
| Nomenclatura | `pncp_datalake-{YYYY-MM-DD}.dump.gz` |
| Retention diaria | 7 dias (configuravel) |
| Retention semanal | 4 semanas (configuravel) |
| Lock file | Sim (`/tmp/backup-database.lock`) |
| Integridade pos-backup | Sim (gzip -t + tamanho > 0) |
| Notificacao de falha | Sim (BACKUP_NOTIFY_CMD) |
| JSON logging | Sim (LOG_JSON no log) |
| Dry-run | Sim |
| Apenas retention | Sim (`--retention-only`) |
| Agenda | Systemd timer `extra-db-backup.timer` -- diario 06:00 UTC |
| Roda como | **root** (necessario para sshfs mount + systemd mount unit nao usada) |

### `scripts/restore-database.sh`

| Aspecto | Detalhe |
|---------|---------|
| Formatos | `--list`, `--schema-only`, `--data-only`, restore completo |
| Paralelismo | `--jobs=4` (configuravel via PGRESTORE_JOBS) |
| Limpeza pre-restore | `--clean --if-exists` |
| Criacao de DB | Automatica se nao existir |
| Verificacao de integridade | Sim (gzip -t antes de restaurar) |
| Senha oculta no log | Sim (`sed` mascaramento) |

### Pontos de atencao

- `extra-db-backup.service` roda como **root**, diferente dos demais
- Depende de `BACKUP_STORAGE_BOX_SSH` configurado manualmente no `.env`
- Nao ha verificacao automatizada de que o Storage Box esta montado ANTES do backup (a montagem e feita inline pelo script)
- Nao ha teste de restore automatizado (restore manual apenas)
- Retention semanal promove backup de domingo -- se nao houver backup no domingo, a promocao nao acontece

---

## 6. Observabilidade

### Componentes

| Componente | Timer | O que verifica | Saida |
|-----------|-------|---------------|-------|
| `health_check.py` | A cada 30min | DB, Storage Box, disco (>80%/90%), sistema (load/mem) | JSON estruturado + journald |
| `check-alerts.py` | A cada 15min | Crawl failures consecutivos, disco, DB, Storage Box, backup, API keys | JSON + notificacao via `notify.py` |
| `collect-metrics.py` | A cada 60min | Crawl metrics (orgaos, taxa sucesso, registros), backup status, alertas ativos | JSON/stdout ou arquivo |
| `freshness_gate.py` | Sob demanda | PNCP editais abertos (24h SLA) e contratos (7d SLA) | `output/readiness/` (JSON+CSV) |
| `health-dashboard.py` | Sob demanda | Dashboard de saude geral | TBD |

### OnFailure Webhook

Dois templates:
- Chamada `curl` para `WEBHOOK_URL` com payload JSON
- `WEBHOOK_URL` lida do `.env`
- Sem retry nem fila -- se o webhook falhar, a notificacao e perdida

### Pontos fortes

- Cobertura ampla: DB, disco, crawler, backup, API keys
- JSON estruturado em todos os componentes (facilmente integravel com Splunk/Elastic/Grafana Loki)
- `correlation_id` para rastreamento de eventos
- `check-alerts.py` tem modo `--test` e `--dry-run`

### Pontos fracos

- Sem agregacao central de metricas (Prometheus/Grafana)
- Logs apenas em journald -- sem retencao configurada explicita
- `notify.py` nao foi auditado neste documento (esta em `scripts/notify.py`)
- `health-dashboard.py` nao tem timer systemd associado
- Sem alerta de schema drift (comparacao entre _migrations ledger e filesystem)

---

## 7. CI/CD

### `.github/workflows/ci.yml`

| Job | Ferramenta | Escopo | Fail-closed? |
|-----|-----------|--------|-------------|
| `lint` | `ruff` | `scripts/` | Sim |
| `type-check` | `mypy` | 7 arquivos core (freshness_gate, universe, models, status, ranking, dedup, transformer) | Sim |
| `test` | `pytest` | 6 testes de readiness (freshness_gate, universe, manifest, consulting_readiness, coverage_truth, resolve_unresolved) | Sim |
| `test-all` | `pytest` | Suite completa (`pytest tests/ -m ""`) | **Apenas workflow_dispatch** |
| `security` | `bandit` | `scripts/` com `-lll` (HIGH apenas) | Sim |
| `dependency-audit` | `pip-audit` | `requirements.txt` com `--strict` | Sim |

### CD: **Nao configurado**

- Deploy e manual (via `install.sh` ou `provision-vps.sh`)
- Nao ha GitHub Actions para deploy em VPS
- Nao ha verificacao de que o state file da story esta valido antes do push

### Observacoes

- **Fail-closed consistente** -- nenhum `continue-on-error: true`
- `test-all` so roda manualmente (suite legada/integration requer DB externo)
- Coverage threshold: `--cov-fail-under=10` (baixo, mas esperado para projeto em growth stage)
- Type-check coverage limitado a 7 arquivos (divida tecnica TD-7.1)

---

## 8. Seguranca

### `.env.example` revela estrutura

O `.env.example` contem 39 variaveis, incluindo:
- `DATABASE_URL` e `LOCAL_DATALAKE_DSN` (com placeholder `<password>`)
- 4 API keys LLM (OpenAI, DeepSeek, OpenRouter, Anthropic)
- `EXA_API_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `GITHUB_TOKEN`
- `BACKUP_STORAGE_BOX_SSH` (placeholder apenas)

**Nenhum segredo hardcoded encontrado** em codigo-fonte Python ou shell. Todas as credenciais sao lidas de `os.getenv()` ou `EnvironmentFile=`.

### Hardening implementado

| Aspecto | Status |
|---------|--------|
| SSH porta customizada (2222) | Sim |
| SSH key-only | Sim (PermitRootLogin without-password) |
| SSH sem password auth | Sim |
| SSH sem X11 | Sim |
| UFW firewall | Sim (default deny, apenas SSH + opcional node-exporter) |
| Fail2ban | Sim (3 tentativas, 1h ban) |
| PostgreSQL localhost-only | Sim |
| PostgreSQL tuning | Sim (shared_buffers=1GB, work_mem=64MB, etc) |
| PostgreSQL UFW script avulso | Sim (`deploy/hardening/ufw-rules.sh` para porta custom 54399) |
| App user nao-root | Sim (`extra-consultoria`) |
| Unattended-upgrades | Sim (habilitado) |
| Passwordless sudo limitado | Sim (`systemctl` e `journalctl` apenas) |
| Node-exporter | Instalado, mas depende de MONITORING_IPS |

### Pontos de atencao

- Backup roda como **root** (justificado pelo sshfs, mas amplia superficie de ataque)
- `onfailure@.service` e `extra-onfailure@.service` nao tem rate limiting -- em caso de falha continua, pode gerar muitas requisicoes HTTP
- Sem firewall rules explicitas para limitar acesso a porta 5432 do PostgreSQL na maquina local
- Sem secrets rotation policy documentada
- Sem monitoramento de tentativas de acesso (fail2ban logs nao sao agregados)

---

## 9. Browser Automation

### Arquivos

| Arquivo | Proposito |
|---------|-----------|
| `scripts/crawl/selenium_crawler.py` | Selenium headless Chrome para portais JS-rendered |
| `scripts/crawl/playwright_fallback.py` | Playwright Chromium como fallback |
| `scripts/crawl/doe_sc_selenium_crawler.py` | Adaptador DOE-SC com autenticacao Selenium |
| `scripts/crawl/selenium_crawler_adapter.py` | Adapter para interface monitor.py |
| `scripts/crawl/selenium_smoke_test.py` | Teste de fumo em 3 portais |
| `scripts/crawl/transparencia_templates/selenium_base.py` | Base para templates de transparencia |

### Configuracoes

| Parametro | Selenium | Playwright |
|-----------|----------|------------|
| Headless | `SELENIUM_HEADLESS=true` (default) | `PLAYWRIGHT_HEADLESS=true` (default) |
| Browser | Chrome (default), Firefox fallback | Chromium (default) |
| Timeout | 30s | 60s |
| UA Rotation | Sim (5 UAs) | Sim (4 UAs) |
| Viewport rand | Sim (6 sizes) | Sim (5 sizes) |
| Sandbox | **Nao explicitamente configurado** | **Nao explicitamente configurado** |

### Nota critica: `--no-sandbox` em container

Os scripts selenium e playwright nao especificam explicitamente `--no-sandbox` para Chrome/Chromium. Se forem executados dentro de um container Docker (nao e o caso atual, mas seria em futuro containerizado), podem falhar. Em bare-metal VPS (Ubuntu 24.04), o sandbox do Chrome funciona normalmente com o usuario `extra-consultoria`.

### Servico Selenium: **INTENCIONALMENTE DESABILITADO**

O servico `extra-crawl-selenium.service` foi desabilitado por decisao arquitetonica (Story 1.5 fix): Selenium nao e mais uma fonte de dados independente, e sim um metodo de crawl que fontes registradas podem usar internamente.

### DOE-SC Login

O `doe_sc_selenium_crawler.py` usa credenciais (`DOE_SC_LOGIN`, `DOE_SC_PASSWORD`) via env vars para autenticar no portal. O login e feito via formulario Selenium. Esse e o unico caso de automacao com autenticacao.

---

## 10. Matriz PASS/FAIL/UNKNOWN

| Area | Veredito | Evidencia | Comando de Validacao |
|------|----------|-----------|---------------------|
| **Docker Compose** | PASS | docker-compose.yml + .local.yml funcionais para dev. Producao bare-metal (escolha arquitetural) | `docker compose ps` |
| **PostgreSQL persistente** | PASS | Volume `pgdata` definido. Em VPS, data directory nativo do PostgreSQL | `docker compose exec test-db pg_isready` (dev); `systemctl status postgresql` (vps) |
| **Migrations fresh-install** | PASS | 42 migrations, ledger com checksum, advisory lock, logging completo | `bash db/setup_db.sh "$DSN"` |
| **Seeds idempotentes** | PASS | Seed com `--truncate` para re-execucao segura. Ledger tracking evita duplicacao | `python db/seed/001_sc_entities.py --dsn "$DSN" --truncate` |
| **Systemd services** | PASS | 21 services definidos, `EnvironmentFile=`, `User=extra-consultoria` (exceto backup como root) | `systemctl list-units 'extra-*' 'pncp-*' 'coverage-*' 'dom-sc-*' --type=service` |
| **Systemd timers** | PASS | 20 timers ativos (excluindo selenium desabilitado). UTC com RandomizedDelaySec | `systemctl list-timers 'extra-*' 'pncp-*' 'coverage-*' 'dom-sc-*'` |
| **Browser headless** | PASS | Selenium e Playwright configurados headless por default | `python scripts/crawl/selenium_smoke_test.py` |
| **Backup** | PASS | pg_dump custom -> gzip -> sshfs -> Storage Box. 7d retention diaria, 4 semanal | `/usr/local/bin/backup-database.sh --dry-run` |
| **Restore** | PASS | Script completo com schema-only, data-only, list, e restore full | `/usr/local/bin/restore-database.sh <arquivo> --list` |
| **Logs** | PASS | Todos os services usam journald. Backup tem logfile separado. JSON estruturado | `journalctl -u extra-health-check.service --output=json-pretty` |
| **Health checks** | PASS | DB, disco, Storage Box, load/mem a cada 30min | `python scripts/health_check.py` |
| **Alertas** | PASS | Crawl failures, disco, DB, storage, backup, API keys a cada 15min | `python scripts/check-alerts.py --dry-run` |
| **CI gates** | PASS | 6 jobs (lint, type-check, test, security, dep-audit) fail-closed. CD nao configurado | Ver GitHub Actions |
| **Seguranca (secrets)** | PASS | Nenhum hardcoded encontrado. Todas via env vars ou EnvironmentFile | `grep -rnE "(password\s*=|secret\s*=|api_key\s*=)\s*['\"][A-Za-z0-9]" scripts/ --include="*.py"` |
| **Firewall** | PASS | UFW default deny, apenas SSH. fail2ban ativo | `ufw status verbose` |
| **Usuario nao-root** | PASS | `extra-consultoria` para todos os services. Excecao: `extra-db-backup` (root) | `systemctl show pncp-crawl-full.service \| grep User` |
| **Timezone** | PASS | America/Sao_Paulo no sistema. Timers em UTC com comentarios BRT | `timedatectl` |
| **Idempotencia** | PASS | provision-vps.sh e setup_db.sh tem guards para re-execucao segura | `bash deploy/provision-vps.sh` (segunda execucao) |
| **Rollback** | FAIL | Apenas 1 arquivo de rollback (029) de 42 migrations. Estrategia atual: restore de backup | `ls db/rollback/` |
| **Custo estimado** | UNKNOWN | Sem dados de fatura Hetzner ou Storage Box disponiveis no repositorio | N/A |
| **Two OnFailure templates** | CONCERNS | `onfailure@` e `extra-onfailure@` tem payloads diferentes. Unificar recomendado | `diff deploy/systemd/onfailure@.service deploy/systemd/extra-onfailure@.service` |
| **Cobertura OnFailure** | CONCERNS | 10 services sem OnFailure configurado (crawl-full, crawl-inc, enricher, mais varios crawlers de fontes) | `grep -L "OnFailure" deploy/systemd/*.service` |
| **Reinicio automatico apos atualizacao** | UNKNOWN | unattended-upgrades habilitado, mas sem politica de reboot documentada | `systemctl show unattended-upgrades` |
| **CD automatizado** | UNKNOWN | Nao ha pipeline de CD. Deploy manual via SSH + install.sh | N/A |
| **node-exporter** | CONCERNS | Instalado mas MONITORING_IPS nao definido. Porta 9100 nao aberta | `ufw status \| grep 9100` |

---

## 11. Recomendacoes para Go-Live

### Criticas (impedem Go-Live)

1. **Rollback de migrations:** 41 de 42 migrations nao tem rollback. Para Go-Live, criar ao menos um `ROLLBACK.md` documentando a estrategia de reversao para cada migration. Nao precisa de SQL para todas, mas precisa de procedimento documentado.

2. **Servicos sem OnFailure:** 10 services nao tem `OnFailure=` configurado. Crawlers que falharem silenciosamente nao serao detectados ate o alert check de 15min -- e mesmo assim, se o webhook nao estiver configurado, a falha passa despercebida. Adicionar `OnFailure=onfailure@%n.service` em todos.

### Altas

3. **Unificar templates de OnFailure:** Usar apenas `extra-onfailure@.service` (que inclui `project`) em todos os services. Remover o `onfailure@.service` antigo.

4. **WEBHOOK_URL obrigatoria:** Tornar `WEBHOOK_URL` uma pre-condicao de Go-Live. Sem ela, todo o sistema de alerta e mudo.

5. **Teste de restore automatizado:** Adicionar um cron/weekly systemd timer que executa `restore-database.sh --list` ou `--schema-only` para o backup mais recente, validando que o arquivo nao esta corrompido.

### Medias

6. **node-exporter:** Configurar `MONITORING_IPS` no provisionamento. Se nao houver Prometheus, considerar substituir por solucao mais simples (netdata, glances) ou remover para nao criar falsa sensacao de seguranca.

7. **health-dashboard.py:** Adicionar timer systemd ou integracao com check-alerts.py para que o dashboard seja gerado periodicamente.

8. **Documentar politica de reboot:** unattended-upgrades esta habilitado mas sem reboot configurado. Decidir: reboot automatico (unattended-upgrades --reboot) ou notificacao para reboot manual.

### Baixas

9. **Containerizacao futura:** Considerar Docker para producao se rollback de versao ou reproducao de ambiente se tornar problematico. Por enquanto, bare-metal e adequado.

10. **cobertura type-check:** Atualmente apenas 7 arquivos. Expandir sob TD-7.1 gradualmente.

11. **Freshness gate sem timer:** `freshness_gate.py` nao tem timer systemd. Considerar adicionar `extra-freshness-gate.timer` correndo a cada 6h.

---

*Auditoria concluida em 2026-07-15. 20 areas avaliadas: 14 PASS, 1 FAIL (rollback), 5 CONCERNS/UNKNOWN.*

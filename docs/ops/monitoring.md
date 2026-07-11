# Sistema de Monitoramento e Alertas

**Extra Consultoria — Story TD-5.5**

## Visao Geral

O sistema de monitoramento fornece visibilidade operacional do pipeline de crawlers,
backup e infraestrutura. Ele e composto por quatro componentes principais:

| Componente | Descricao | Frequencia |
|-----------|-----------|------------|
| `collect-metrics.py` | Coleta metricas de cobertura dos crawlers | A cada 60min |
| `check-alerts.py` | Verifica condicoes criticas e dispara notificacoes | A cada 15min |
| `notify.py` | Envia notificacoes via email e/ou webhook | Sob demanda |
| `health-dashboard.py` | Dashboard CLI com resumo do estado do sistema | Sob demanda |

## Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                      Systemd Timers                          │
│  ┌──────────────────┐    ┌──────────────────────┐           │
│  │ extra-collect-    │    │ extra-check-alerts   │           │
│  │ metrics.timer     │    │ .timer               │           │
│  │ (a cada 60min)    │    │ (a cada 15min)       │           │
│  └───────┬───────────┘    └──────────┬───────────┘          │
│          ▼                           ▼                      │
│  ┌──────────────────┐    ┌──────────────────────┐           │
│  │ collect-metrics  │    │  check-alerts        │           │
│  │ .py              │    │  .py                 │           │
│  └───────┬──────────┘    └──────────┬───────────┘          │
│          │                          │                      │
│          ▼                          ▼                      │
│  ┌──────────────────┐    ┌──────────────────────┐           │
│  │  Banco de Dados  │    │  notify.py           │           │
│  │  (ingestion_runs │    │  (email / webhook)   │           │
│  │   entity_coverage│    └──────────────────────┘           │
│  │   sc_entities)   │                                      │
│  └──────────────────┘                                      │
│                                                             │
│  Sob demanda:                                               │
│  ┌─────────────────────────────────────┐                   │
│  │  health-dashboard.py                │                   │
│  │  (dashboard CLI interativo)          │                   │
│  └─────────────────────────────────────┘                   │
└─────────────────────────────────────────────────────────────┘
```

## Componentes

### 1. Coleta de Metricas (`scripts/collect-metrics.py`)

Coleta metricas operacionais do banco de dados e logs.

**Metricas coletadas:**

- **Crawl:** execucoes por fonte (total, sucesso, falha), registros fetched/upserted/matched, taxa de sucesso
- **Cobertura:** entidades cobertas vs. totais por fonte
- **Backup:** timestamp do ultimo backup, status, tamanho
- **Falhas consecutivas:** fontes com N+ falhas consecutivas

**Uso:**

```bash
# Todas as metricas (JSON)
python scripts/collect-metrics.py

# Resumo legivel
python scripts/collect-metrics.py --summary

# Janela de 30 dias
python scripts/collect-metrics.py --days 30

# Exportar para arquivo
python scripts/collect-metrics.py --export /tmp/metrics.json
```

**Systemd timer:** `extra-collect-metrics.timer` (executa a cada 60 minutos).

### 2. Verificacao de Alertas (`scripts/check-alerts.py`)

Verifica condicoes criticas periodicamente e dispara notificacoes.

**Verificacoes realizadas:**

| Verificacao | Severidade | Gatilho | Descricao |
|------------|-----------|---------|-----------|
| Falha consecutiva | CRITICAL | 3+ falhas consecutivas | Crawler falhou N vezes seguidas |
| Disco cheio | CRITICAL / WARN | >90% / >80% | Espaco em disco abaixo do limite |
| DB offline | CRITICAL | Sem resposta | PostgreSQL inacessivel |
| Storage Box | CRITICAL | Nao montado | Ponto de montagem do backup ausente |
| Backup desatualizado | CRITICAL | >28h sem backup | Ultimo backup excedeu janela |
| API key faltando | WARN | Variavel vazia | Chave necessaria nao configurada |

**Uso:**

```bash
# Executar todas as verificacoes
python scripts/check-alerts.py

# JSON output
python scripts/check-alerts.py --json

# Simulacao (sem enviar notificacoes)
python scripts/check-alerts.py --dry-run

# Testar pipeline de notificacao
python scripts/check-alerts.py --test

# Threshold customizado de falhas consecutivas
python scripts/check-alerts.py --threshold 5
```

**Systemd timer:** `extra-check-alerts.timer` (executa a cada 15 minutos).

**Nota:** Quando o banco de dados esta offline, as verificacoes de crawl sao
puladas automaticamente para evitar erros em cascata.

### 3. Notificacoes (`scripts/notify.py`)

Sistema de notificacao multi-canal.

**Canais suportados:**

- **Email (SMTP):** Configurado via variaveis `NOTIFY_SMTP_*`
- **Webhook (Slack/Discord):** Configurado via `NOTIFY_WEBHOOK_URL`

**Uso:**

```bash
# Notificar com subject e body
python scripts/notify.py --subject "Alerta" --body "Descricao do problema"

# Testar configuracao
python scripts/notify.py --test

# Canal especifico
python scripts/notify.py --channel email --test
python scripts/notify.py --channel webhook --test

# Webhook URL override
python scripts/notify.py --webhook-url "https://hooks.slack.com/..." --test
```

**Comportamento:**

- Se multiplos canais estao configurados, todos sao usados
- Se nenhum canal esta configurado, um warning e logado
- Timeout de conexao: 15 segundos
- Retry nao implementado (o timer do systemd faz o retry)

### 4. Dashboard CLI (`scripts/health-dashboard.py`)

Dashboard interativo com resumo do estado do sistema.

**Uso:**

```bash
# Dashboard completo
python scripts/health-dashboard.py

# Resumo em uma linha (para monitoring tools)
python scripts/health-dashboard.py --summary

# JSON output
python scripts/health-dashboard.py --json

# Auto-refresh a cada 60s
python scripts/health-dashboard.py --watch
```

**Exemplo de saida:**

```
======================================================================
  DASHBOARD DE MONITORAMENTO — Extra Consultoria
  2026-07-11 14:30:00 UTC
  Host: hetzner-vps-1
======================================================================

  --- SAUDE DO SISTEMA ---
    [PASS] db               PostgreSQL OK
    [PASS] disk             45% used (28.3G free)
    [PASS] storage_box      Mounted
    ---
    [OK]   Overall: HEALTHY

  --- CRAWL ---
    Runs today: 3  |  Runs this week: 24
    Source              Runs   OK  Fail     Rate  Fetched           Last run
    -----------------  -----  ---- -----  -------  --------  -------------------
    pncp                  8    8     0    100%      1240  2026-07-11T12:00:00
    dom_sc                7    7     0    100%       340  2026-07-11T11:30:00
    contracts             6    6     0    100%        89  2026-07-11T10:00:00

  --- BACKUP ---
    [OK]   Last backup: 2026-07-11T06:00:00+00:00
           Status:     success
           Size:       142.3 MB
           Hours ago:  8.5h

  --- ALERTAS ATIVOS ---
    No active alerts.
    Total: 0 (critical=0, warnings=0)

======================================================================
```

**Exit codes:**
- `0` — Tudo OK
- `1` — Apenas warnings
- `2` — Problemas criticos

## Configuracao

### Variaveis de Ambiente

Adicione ao `.env` ou ao environment file do servico:

```bash
# === Alertas ===
ALERT_CONSECUTIVE_FAILURES=3      # Falhas consecutivas para alerta critico
ALERT_DISK_WARN_PCT=80            # Porcentagem de disco para warning
ALERT_DISK_CRIT_PCT=90            # Porcentagem de disco para critico
ALERT_BACKUP_MAX_HOURS=28         # Horas sem backup para alerta

# === Notificacao Email (SMTP) ===
NOTIFY_SMTP_HOST=smtp.gmail.com
NOTIFY_SMTP_PORT=587
NOTIFY_SMTP_USER=seu-email@gmail.com
NOTIFY_SMTP_PASSWORD=sua-senha-de-app
NOTIFY_SMTP_FROM=seu-email@gmail.com
NOTIFY_SMTP_TO=destinatario@exemplo.com
NOTIFY_SMTP_USE_TLS=true

# === Notificacao Webhook (Slack/Discord) ===
NOTIFY_WEBHOOK_URL=https://hooks.slack.com/services/TTT/BBB/xxx
```

### Systemd

Os timers sao instalados automaticamente pelo script de provisionamento:

```bash
# Ativar timers
sudo systemctl daemon-reload
sudo systemctl enable extra-collect-metrics.timer
sudo systemctl enable extra-check-alerts.timer
sudo systemctl start extra-collect-metrics.timer
sudo systemctl start extra-check-alerts.timer

# Verificar status
sudo systemctl status extra-collect-metrics.timer
sudo systemctl status extra-check-alerts.timer

# Ver logs
sudo journalctl -u extra-collect-metrics.service -n 20 --no-pager
sudo journalctl -u extra-check-alerts.service -n 20 --no-pager
```

## Dependencias

- **Python 3.10+** — sem dependencias externas (stdlib apenas)
- **PostgreSQL** — tabelas `ingestion_runs`, `entity_coverage`, `sc_public_entities`
- **psql** — para verificacao de conectividade com o banco (executado como subprocesso)
- **systemd** — para agendamento via timers

## Troubleshooting

### Notificacoes nao chegam

1. Verifique as variaveis de ambiente:
   ```bash
   python -c "import os; print('SMTP_HOST:', os.getenv('NOTIFY_SMTP_HOST', 'N/A'))"
   ```

2. Teste o pipeline de notificacao:
   ```bash
   python scripts/check-alerts.py --test
   ```

3. Verifique os logs:
   ```bash
   journalctl -u extra-check-alerts.service --since "5 min ago"
   ```

### Dashboard mostra dados inconsistentes

1. Verifique se as tabelas de ingestion_runs tem dados recentes:
   ```bash
   psql "$LOCAL_DATALAKE_DSN" -c "SELECT source, MAX(started_at) FROM ingestion_runs GROUP BY source"
   ```

2. Execute a coleta de metricas manualmente:
   ```bash
   python scripts/collect-metrics.py --summary
   ```

### Alertas falsos positivos

Ajuste os thresholds no `.env`:

```bash
# Aumentar tolerancia para falhas consecutivas
ALERT_CONSECUTIVE_FAILURES=5

# Aumentar limite de disco
ALERT_DISK_WARN_PCT=85
ALERT_DISK_CRIT_PCT=95

# Aumentar janela de backup
ALERT_BACKUP_MAX_HOURS=48
```

## Referencias

- Story TD-5.5: Monitoramento e Alertas
- TD-5.1: Logging Estruturado (base para logs JSON)
- TD-4.2: CI/CD e Healthcheck (healthcheck basico)
- TD-0.1: Backup Automatizado (logs de backup)
- `scripts/health_check.py`: Healthcheck de infraestrutura
- `scripts/healthcheck.py`: Healthcheck unificado extra-consultoria

---

*Documentacao gerada em 2026-07-11 — Story TD-5.5*

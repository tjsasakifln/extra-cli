# Requirements — Módulo `deploy`

> 🟢 CONFIRMADO — `deploy/install.sh`, `deploy/systemd/*`

## Funcionais

| ID | Requisito | Fonte | Confiança |
|----|-----------|-------|-----------|
| FR-DP1 | 13 systemd timers com schedules escalonados | `deploy/systemd/*.timer` | 🟢 |
| FR-DP2 | RandomizedDelaySec=300 em todos os timers (anti-pico) | `*.timer` | 🟢 |
| FR-DP3 | Template `onfailure@.service` para notificação de falhas | `onfailure@.service` | 🟢 |
| FR-DP4 | Script `install.sh`: pacotes, PostgreSQL, migrations, seed, systemd | `install.sh` | 🟢 |
| FR-DP5 | Target: Hetzner VPS Ubuntu 24.04, PostgreSQL 17, Python 3.12 | `install.sh` | 🟢 |

## Cron Schedule

| Timer | Schedule (UTC) | Frequência |
|-------|---------------|------------|
| pncp-crawl-full | 05:00 | Diário |
| pncp-crawl-inc | 11:00, 17:00, 23:00 | 3x/dia |
| dom-sc-crawl | 06:00, 14:00, 22:00 | 3x/dia |
| pcp-crawl | 08:00 | Diário |
| compras-gov-crawl | 10:00 | Diário |
| pncp-contracts | 07:00 | Seg/Qua/Sex |
| pncp-enrich | 08:00 | Diário |
| pncp-purge | 04:00 | Diário |
| coverage-report | 09:00 | Diário |
| coverage-report-weekly | 07:00 | Segunda |
| pncp-report-weekly | 07:00 | Segunda |
| tce-sc-crawl | 12:00 | Diário |
| transparencia-crawl | 13:00 | Diário |

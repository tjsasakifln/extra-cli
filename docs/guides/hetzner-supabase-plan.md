# Plano Hetzner + Supabase Self-Hosted — Extra Construtora

> **Data:** 2026-07-10 | **Autor:** AIOX PM | **Decisão:** CX43 (menor custo)

---

## Decisão: Hetzner CX43

| Item | Especificação |
|------|---------------|
| **Plano** | CX43 (Shared Intel Xeon Gold) |
| **vCPUs** | 8 |
| **RAM** | 16 GB |
| **Storage** | 160 GB NVMe |
| **Tráfego** | 20 TB/mês |
| **Preço** | **€15.99/mo** (~R$ 102/mo) |
| **Setup fee** | €0 (cloud) |
| **Contrato** | Sem mínimo, hora ou mês |
| **Data center** | Nuremberg (DE) — latência 200ms aceitável |

### Upgrade path

| Gatilho | Upgrade para | Preço |
|---------|-------------|-------|
| RAM > 80% constante | **CX53** (32 GB) | €29.49/mo |
| Disco > 120 GB | Volume adicional 100 GB | +€5.00/mo |
| CPU gargalo | **EX44** (i5-13500, 64 GB) | €44.00/mo |

> **Nota (2026):** Preços pós-aumento de Junho/2026. Instâncias CX mantiveram-se competitivas (~30% aumento vs ~170% em CCX/CPX). Fonte: [Northflank](https://northflank.com/blog/hetzner-cloud-server-price-increases), [Igor's Lab](https://www.igorslab.de/en/hetzner-to-significantly-increase-prices-for-cloud-and-dedicated-servers-from-april-2026/).

---

## Alocação de Recursos (CX43: 8 vCPU, 16 GB RAM, 160 GB)

| Serviço | vCPU | RAM | Disco |
|---------|------|-----|-------|
| PostgreSQL 17 | 2-3 | 4 GB | 60 GB |
| GoTrue (auth) | 0.5 | 256 MB | — |
| Kong (API gateway) | 0.5 | 512 MB | — |
| PostgREST | 0.5 | 256 MB | — |
| Realtime | 0.5 | 512 MB | — |
| Storage (S3) | 0.5 | 256 MB | 20 GB |
| Studio (dashboard) | 0.5 | 256 MB | — |
| Python crawlers (10 timers) | 1-2 | 2 GB | — |
| System overhead | — | 2 GB | 10 GB |
| **Total** | 6-8 | ~10 GB | 90 GB |
| **Livre** | 0-2 | ~6 GB | 70 GB |

### PostgreSQL tuning (4 GB shared_buffers)

```
shared_buffers = 4GB
effective_cache_size = 12GB
work_mem = 32MB
maintenance_work_mem = 512MB
wal_buffers = 16MB
max_connections = 50
random_page_cost = 1.1  # NVMe
```

---

## Método: Self-Hosted via Docker Compose

### Opção A: Coolify (recomendado)
- UI para deploy one-click do Supabase
- Gerencia TLS, backups, monitoramento
- Install: `curl -fsSL https://cdn.coollabs.io/coolify/install.sh | bash`

### Opção B: Docker Compose direto
- Repo oficial: `https://github.com/supabase/supabase`
- Mais controle, mais trabalho de manutenção

### Opção C: Supabase Cloud (alternativa)
- Pro plan: $25/mo → ~R$ 150/mo
- 8 GB RAM, 100 GB storage
- **Vantagem:** Zero manutenção, updates automáticos
- **Desvantagem:** Menos controle, sem acesso direto ao filesystem para crawlers

**Decisão:** Opção A (Coolify) + Docker Compose. Começar com isso; migrar para Supabase Cloud se manutenção for custosa.

---

## Setup Inicial (Playwright MCP)

Usar Playwright MCP para configuração inicial do Coolify no Hetzner:

1. **Criar VM no Hetzner Cloud Console** (via Playwright)
2. **Instalar Coolify** (SSH depois de criada)
3. **Configurar Supabase via Coolify UI** (via Playwright)
4. **Configurar DNS** (opcional — IP direto funciona para single user)
5. **Rodar migrations** (psql via SSH)
6. **Deploy systemd timers** (deploy/install.sh)
7. **Rodar seed entities** (db/seed/seed_sc_entities.py)

### Alternativa CLI: hcloud (Hetzner CLI)

```bash
# Instalar
brew install hcloud  # ou download de github.com/hetznercloud/cli

# Criar server
hcloud server create \
  --name extra-consultoria \
  --type cx43 \
  --image ubuntu-24.04 \
  --location nbg1 \
  --ssh-key ~/.ssh/id_ed25519.pub

# Ver IP
hcloud server list
```

---

## Cron Jobs (10 systemd timers)

| Timer | Schedule (UTC) | Fonte |
|-------|---------------|-------|
| pncp-crawl-full | Daily 05:00 | PNCP |
| pncp-crawl-inc | Daily */6h | PNCP |
| dom-sc-crawl | 06,14,22:00 | DOM-SC |
| pcp-crawl | 06:30,14:30 | PCP |
| compras-gov-crawl | Daily 07:00 | ComprasGov |
| pncp-contracts | Mon,Wed,Fri 06:00 | Contratos |
| pncp-enrich | Daily 08:00 | Enricher |
| pncp-purge | Daily 07:00 | Purge >400d |
| pncp-report-weekly | Mon 07:00 | Relatório |
| coverage-report | Daily 08:30 | Snapshot |

---

## Custo Total Estimado

| Item | Mensal (€) | Mensal (R$) |
|------|-----------|-------------|
| Hetzner CX43 | €15.99 | ~R$ 102 |
| Domínio (opcional) | — | — |
| Backup (snapshot) | €0.01/GB | ~R$ 1 |
| **Total** | **~€16.00** | **~R$ 103** |

> **Comparação:** Supabase Cloud Pro ($25/mo ≈ R$ 150) + VPS para crawlers (€5/mo ≈ R$ 32) = R$ 182/mo. Self-hosted no CX43 economiza ~44%.

---

## Próximos Passos

1. [ ] Criar conta Hetzner Cloud (https://accounts.hetzner.com/signUp)
2. [ ] Gerar API token no Cloud Console
3. [ ] Instalar hcloud CLI localmente
4. [ ] Criar VM CX43 via hcloud ou Playwright
5. [ ] Instalar Coolify + Supabase stack
6. [ ] Rodar setup_db.sh (migrations)
7. [ ] Rodar seed_sc_entities.py (2.085 entes)
8. [ ] Deploy systemd timers (install.sh)
9. [ ] Verificar primeiro crawl completo
10. [ ] Configurar backup automático (pg_dump + snapshot)

---

*Plano gerado por AIOX PM — 2026-07-10*

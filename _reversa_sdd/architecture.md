# Arquitetura — Extra Consultoria

> Gerado pelo Architect em 2026-07-11T15:00:00Z
> Síntese de todos os artefatos anteriores (C4, ERD, integrações)

---

## Visão Geral

Plataforma CLI single-user de inteligência em licitações públicas. Monitora 2.085 órgãos de SC via 8 fontes de dados, mantém DataLake PostgreSQL no Hetzner VPS, gera relatórios PDF/Excel sob demanda.

**Stack:** Python 3.12 → PostgreSQL 17 (psycopg2 direto) | systemd timers | GPT-4.1-nano | ReportLab

---

## Decisões de Arquitetura (ADRs)

| ADR | Decisão | Justificativa |
|-----|---------|---------------|
| [001](adrs/001-postgresql-direto-sem-api.md) | PostgreSQL direto sem API | Single-user, sem REST overhead |
| [002](adrs/002-systemd-timers-em-vez-de-redis.md) | systemd em vez de Redis/ARQ | Nativo Linux, zero dependências |
| [003](adrs/003-crawlers-sync-http.md) | HTTP síncrono (urllib) | Simples, sem asyncio para cron |
| [004](adrs/004-entity-matching-cascade-3-niveis.md) | Cascade 3 níveis (CNPJ→nome→fuzzy) | Maximiza recall mantendo precisão |
| [005](adrs/005-gpt-4.1-nano-classificacao.md) | GPT-4.1-nano classificador | Custo baixo, zero-noise |
| [006](adrs/006-pdf-reportlab-big-four.md) | ReportLab PDF Big Four | Código validado 10K+ linhas |

---

## Containers

| Container | Tecnologia | Host | Porta |
|-----------|-----------|------|------|
| Python CLI Scripts | Python 3.12 | Hetzner VPS | — |
| PostgreSQL 17 | PostgreSQL | Hetzner VPS | 5432 |
| systemd timers | systemd (Linux) | Hetzner VPS | — |

---

## Integrações Externas

| Sistema | Propósito | Protocolo | Frequência |
|---------|-----------|-----------|------------|
| PNCP API | Licitações | HTTPS REST | Diário (full) + 3x/dia (inc) |
| DOM-SC | Contratos municipais | HTTPS REST (API Key) | 3x/dia |
| PCP v2 | Licitações municipais | HTTPS REST | 2x/dia |
| ComprasGov v3 | Compras federais | HTTPS REST | 1x/dia |
| TCE-SC ESFINGE | Licitações TCE-SC | HTTPS JSON API (SCMWeb) | 1x/dia |
| Portais Transparência | Gap-fill municipal | HTTPS Web Scraping | 1x/dia |
| OpenAI API | Classificação editais | HTTPS REST (API Key) | On-demand |
| BrasilAPI | Enriquecimento CNPJ | HTTPS REST | Diário |
| IBGE API | Enriquecimento municípios | HTTPS REST | Diário |

---

## Dívidas Técnicas

| ID | Descrição | Severidade | Módulo |
|----|-----------|------------|--------|
| DT1 | Cobertura de testes <30% — sem suíte automatizada | 🔴 ALTA | Todos |
| DT2 | Código duplicado de conexão PostgreSQL em múltiplos scripts | 🟡 MÉDIA | crawl, intel, reports |
| DT3 | `intel_pipeline.py` usa `subprocess.run()` em vez de import direto | 🟡 MÉDIA | intel |
| DT4 | Enricher desenhado para ARQ/Supabase mas adaptado para psycopg2 | 🟡 MÉDIA | crawl |
| DT5 | `pncp_crawler_adapter.py` tem constantes duplicadas com `config/settings.py` | 🟡 MÉDIA | crawl |
| DT6 | Sem tratamento de rate limiting nas APIs além de delays fixos | 🟡 MÉDIA | crawl |
| DT7 | Sem health check endpoint para monitoramento dos crawlers | 🟡 MÉDIA | deploy |
| DT8 | `sectors_config.yaml` com 2.116 linhas — difícil manutenção manual | 🟢 BAIXA | config |
| DT9 | OpenAI timeout de 10s pode ser insuficiente para editais longos | 🟢 BAIXA | intel |
| DT10 | Sem logging estruturado (JSON) — apenas print() e logging básico | 🟢 BAIXA | Todos |

---

## Padrões e Anti-Padrões

### Padrões Adotados
- ✅ 12-factor config (env vars + YAML)
- ✅ Soft delete (is_active flag)
- ✅ Content hash dedup
- ✅ Idempotent upserts via RPC
- ✅ Staggered scheduling com jitter
- ✅ Cascade matching com fallback progressivo
- ✅ Zero-noise classification (REJECT on uncertainty)

### Anti-Padrões Identificados
- ❌ `subprocess.run()` para scripts Python internos (intel_pipeline)
- ❌ Duplicação de DSN default em múltiplos arquivos
- ❌ Módulo `enricher.py` com design async/ARQ adaptado para sync
- ❌ Ausência de interface comum para crawlers (adapter.py existe mas não é usado consistentemente)

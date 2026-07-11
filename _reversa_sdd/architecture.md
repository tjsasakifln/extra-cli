# Arquitetura — Extra Consultoria

> Gerado pelo Architect em 2026-07-11T22:00:00Z
> doc_level: completo
> Base: commit e9729e1 (32 stories, EPIC-FEAT-001 + EPIC-TD-001)

## Visão Geral

Plataforma de inteligência B2G single-tenant em VPS Hetzner CX22 (2 vCPU, 4GB, Ubuntu 24.04). Três camadas: **(1) ingestão multi-source** (10 crawlers sync, 8 fontes, 4 templates transparência), **(2) pipeline analítico** (7 estágios, 5 quality gates, GPT-4.1-nano), **(3) relatórios** executivos PDF/Excel Big Four.

**Stack:** Python 3.12 (98K LOC) + PostgreSQL 18.4 (5.3K LOC SQL) + Shell (3.5K LOC) + YAML (8.8K LOC)
**Scheduler:** 20 systemd timer/service pairs
**Métricas:** 196 arquivos, 9 módulos, 11 integrações externas

## 11 Decisões Arquiteturais (ADRs)

| # | Decisão | Epic |
|---|---------|------|
| 001 | PostgreSQL direto (psycopg2), sem API | EPIC-001 |
| 002 | Systemd timers, sem Redis/Celery | EPIC-001 |
| 003 | Crawlers sync HTTP (urllib) | EPIC-001 |
| 004 | Entity matching cascade 3 níveis | EPIC-001 |
| 005 | GPT-4.1-nano para classificação + análise | EPIC-001 |
| 006 | PDF ReportLab, estética Big Four | EPIC-001 |
| 007 | Migrations v2 baseline (pg_dump schema real) | EPIC-TD-001 |
| 008 | Refactor monitor.py → orchestrator + matching | EPIC-TD-001 |
| 009 | Backup pg_dump + Hetzner Storage Box | EPIC-TD-001 |
| 010 | Logging JSON com correlation_id | EPIC-TD-001 |
| 011 | Template-driven crawler transparência | EPIC-FEAT-001 |

## Subsistemas

### 1. Crawl (35 arquivos, ~14K LOC)
10 crawlers sync + orquestrador + retry/circuit breaker/checkpoint/enrichment/sanctions.
4 templates transparência (Betha, Ipam, E-gov, Genérico).

### 2. Intel Pipeline (8 arquivos, ~12K LOC)
Coleta exaustiva → Enriquecimento → Validação → Análise LLM → Extração Docs → Excel → PDF.
5 quality gates com auto-fix. 12 algoritmos de negócio.

### 3. Reports (6 arquivos, ~9.5K LOC)
Panorama, cobertura diário/semanal, proposta comercial, relatório B2G (6.4K LOC).
Design system: INK #1B2A3D, ACCENT #8B7355, Times+Helvetica, A4 2.2cm.

### 4. Lib + Matching (13 arquivos, ~2.8K LOC)
Normalização, simulação lance, estimativa custos, victory profile, doc templates, entity matching.

### 5. Database (25 arquivos, ~6K LOC)
19 migrations v1 + 5 v2 baseline. 8 tabelas, 10 funções PL/pgSQL, 5 views. Seed 2.085 entes SC.

### 6. Deploy (42 arquivos, ~3.5K LOC)
Provisionamento VPS, 20 systemd timers, hardening, backup automatizado.

## Padrões de Código

| Padrão | Uso |
|--------|-----|
| Interface Crawler (`crawl`+`transform`) | 10 crawlers sync |
| Exponential backoff (2^N) | 7 crawlers + HTTP |
| Circuit breaker | 5 APIs (singletons) |
| Cascade fallback 3 níveis | Entity matching, PDF extraction, platform detection |
| Content hash SHA-256 | Dedup cross-source |
| Quality gate pipeline | Intel (5 gates, auto-fix) |
| Section builder | B2G report (80+ funções) |
| Contextvar correlation_id | Logging thread-safe |
| Soft-delete + hard-delete | Purge (400d + 90d) |
| Template method | Transparência (4 + fallback) |

## Integrações Externas (11)

| Sistema | Protocolo | Auth | Dados |
|---------|----------|------|-------|
| PNCP API | REST/JSON | Public | Licitações, contratos, ARP, PCA |
| DOM-SC | REST/JSON | Basic + API Key | Publicações municipais SC |
| DOE-SC | REST/JSON | Bearer (login) | Diário Oficial SC |
| PCP v2 | REST/JSON | Public | Licitações portais compras |
| ComprasGov | REST/JSON | Public | Licitações federais (2 endpoints) |
| TCE-SC (SCMWeb) | Web/HTML | Public | Licitações + contratos |
| BrasilAPI | REST/JSON | Public | CNPJ + IBGE |
| IBGE API | REST/JSON | Public | Dados municipais |
| OpenAI | REST/JSON | API Key | GPT-4.1-nano + embeddings |
| Portal Transparência | REST/JSON | API Key | CEIS + CNEP |
| SICAF | Web/HTML | Captcha (Playwright) | Verificação cadastral |

## Dívidas Técnicas

| ID | Severidade | Descrição |
|----|-----------|-----------|
| DT-01 | 🔴 CRITICAL | Migrations divergentes do schema real |
| DT-02 | 🟠 HIGH | 0 views no banco real (migrations 009-012 nunca aplicadas) |
| DT-03 | 🟠 HIGH | Dois orquestradores: monitor.py + orchestrator.py |
| DT-04 | 🟠 HIGH | Dois sistemas de checkpoint (sync + async) |
| DT-05 | 🟠 HIGH | BidsCrawler = dead code (imports quebrados) |
| DT-06 | 🟡 MEDIUM | Cobertura testes <30% (98K LOC) |
| DT-07 | 🟡 MEDIUM | Helpers duplicados em crawlers |
| DT-08 | 🟡 MEDIUM | transparencia_config.yaml: municipios vazio |
| DT-09 | 🟡 MEDIUM | ARP/PCA crawlers async, incompatíveis com monitor |
| DT-10 | 🟢 LOW | Sem smoke tests para APIs externas |

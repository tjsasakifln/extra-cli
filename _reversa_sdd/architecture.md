# Arquitetura — Extra Consultoria

> Gerado pelo Architect em 2026-07-13T17:30:00Z
> doc_level: completo
> Base: commit 249340d (QW-01 Radar + Competitive Intel + Readiness Gates)
> Delta: 30 commits, +2 verticais de produto, +3 CI gates, +5 ADRs

## Visão Geral

Plataforma de inteligência B2G single-tenant em VPS Hetzner CX22 (2 vCPU, 4GB, Ubuntu 24.04). Quatro camadas: **(1) ingestão multi-source** com evidence ledger auditável, **(2) verticais de produto** (Opportunity Intel QW-01 + Contract Intel), **(3) pipeline analítico** legado (7 estágios, GPT-4.1-nano), **(4) relatórios** executivos PDF/Excel + CSV radar. CI fail-closed com 2 gates (Readiness ≥ 95%, Freshness SLA).

**Stack:** Python 3.12 (137K LOC) + PostgreSQL 18.4 + Shell + YAML (8.8K LOC)
**Scheduler:** 20 systemd timer/service pairs
**Métricas:** 277 arquivos, 17 módulos, 13 integrações externas (2 ativas, 7 bloqueadas, 4 enriquecimento)

## 16 Decisões Arquiteturais (ADRs)

| # | Decisão | Epic/Iniciativa |
|---|---------|-----------------|
| 001 | PostgreSQL direto (psycopg2), sem API REST intermediária | EPIC-001 |
| 002 | Systemd timers, sem Redis/Celery | EPIC-001 |
| 003 | Crawlers sync HTTP (urllib) | EPIC-001 |
| 004 | Entity matching cascade 3 níveis (CNPJ8→nome+município→fuzzy) | EPIC-001 |
| 005 | GPT-4.1-nano para classificação CNAE + análise | EPIC-001 |
| 006 | PDF ReportLab, estética Big Four | EPIC-001 |
| 007 | Migrations v2 baseline (pg_dump schema real) | EPIC-TD-001 |
| 008 | Refactor monitor.py → orchestrator + matching externo | EPIC-TD-001 |
| 009 | Backup pg_dump + Hetzner Storage Box | EPIC-TD-001 |
| 010 | Logging JSON estruturado com correlation_id | EPIC-TD-001 |
| 011 | Template-driven crawler transparência (4 + fallback) | EPIC-FEAT-001 |
| **012** | **QW-01 Radar PostgreSQL-only, scoring determinístico 24 regras** | **QW-01** |
| **013** | **Coverage Truth — entity-level evidence ledger (10 estados)** | **Coverage Truth** |
| **014** | **CI Gates fail-closed — Readiness (95%) + Freshness (SLA)** | **P1 Remediation** |
| **015** | **Estágios semânticos de valor (5 estágios) — Regra #8** | **Regra #8** |
| **016** | **Competitive Intelligence — market share, HHI, supplier ranking** | **Regra #9** |

## Subsistemas

### 1. Crawl + Evidence Ledger (51 arquivos, ~65K LOC)
10 crawlers sync + orquestrador + retry/circuit breaker/checkpoint/enrichment/sanctions.
**NOVO:** Evidence projection pipeline: crawl→transform→upsert→entity match→evidence projection.
4 templates transparência (Betha, Ipam, E-gov, Genérico). Mapeamento determinístico `monitor_status → evidence_state`.

### 2. Opportunity Intel (16 arquivos, ~15K LOC) 🆕
QW-01 Radar operacional. Pipeline: schema check→universe load→crawl→dedup 4 níveis→status canônico 3 níveis→ranking 24 regras→scoring dual→CSV auditável.
CLI: `radar`, `list`, `show`, `explain`, `coverage`, `source-health`, `update`, `export`.
Threshold 95%. Nunca emite veredito definitivo — sempre triagem para humano.

### 3. Contract Intel (3 arquivos, ~60K LOC) 🆕
Target universe determinístico + consulta contratos históricos + competitive intelligence.
Métricas: market share (TOP 20), HHI (global + por entidade), supplier ranking, expiring contracts.
Readiness threshold 95%. Denominador conservador.

### 4. Intel Pipeline Legado (8 arquivos, ~12K LOC)
7 estágios: collect→enrich→validate→analyze(LLM)→extract docs→excel→pdf.
5 quality gates com auto-fix. 12 algoritmos de negócio. Em transição para verticais especializadas.

### 5. Reports (6 arquivos, ~9.5K LOC)
Panorama, cobertura semanal, proposta comercial, relatório B2G (6.4K LOC).
Design system: INK #1B2A3D, ACCENT #8B7355, Times+Helvetica, A4 2.2cm.

### 6. Lib (15 arquivos, ~12K LOC)
**NOVO:** Canonical universe (planilha seed como autoridade), value semantics (5 estágios), client profile YAML.
Legado: normalização, simulação lance, estimativa custos, victory profile, doc templates.

### 7. CI Gates (2 arquivos, ~470 LOC) 🆕
Readiness Gate (`consulting_readiness.py`): coverage ≥ 95%? SOURCE_BLOCKERS override. Exit 0/2.
Freshness Gate (`freshness_gate.py`): SLA PNCP 24h, Contracts 24d. Exit 0/2.
Ambos fail-closed. Output JSON + CSV para auditoria.

### 8. Database (41 arquivos, ~6K LOC)
41 migrations (v1 029 + v2 006 + v3 006). 10 tabelas, 12 funções PL/pgSQL, 6 views.
**NOVO:** `coverage_evidence` table + `evidence_state` enum (10 valores). `opportunity_intel` table.
Seed 2.085 entes SC + 1.093 universo canônico.

### 9. Deploy (42 arquivos, ~3.5K LOC)
Provisionamento VPS, 20 systemd timers, hardening, backup automatizado.
**NOVO:** QW-01 scheduled run, readiness assessment timer.

## Padrões de Código

| Padrão | Uso | Módulos |
|--------|-----|---------|
| Interface Crawler (`crawl`+`transform`) | 10 crawlers sync | crawl |
| Exponential backoff (2^N) + jitter | 7 crawlers + HTTP | crawl, opportunity_intel |
| Circuit breaker (CLOSED→OPEN→HALF_OPEN) | 5 APIs (singletons) | crawl |
| Cascade fallback 3 níveis | Entity matching, PDF extraction, platform detection | matching, intel |
| Content hash SHA-256 | Dedup cross-source | crawl, opportunity_intel |
| Quality gate pipeline | Intel (5 gates, auto-fix) | intel |
| Evidence projection | Crawl→coverage_evidence INSERT | crawl |
| Deterministic ranking (24 regras) | Scoring sem LLM | opportunity_intel |
| **Fail-closed** | Status unknown→unknown, coverage default→not_investigated | TODOS |
| Conservative denominator | População = resolved + unresolved | lib, opportunity_intel, contract_intel |
| Value semantics 5 estágios | Valor tipado por source+entity_type | lib, contract_intel |
| Soft-delete + hard-delete | Purge (400d + 90d) | db |
| Template method | Transparência (4 + fallback) | crawl |

## Integrações Externas (13)

| Sistema | Protocolo | Auth | Dados | Status |
|---------|----------|------|-------|--------|
| PNCP API v3 | REST/JSON | Public | Licitações + contratos | ✅ ATIVA (SLA 24h) |
| DOM-SC | REST/JSON | Basic + API Key | Publicações municipais SC | 🔴 SOURCE_BLOCKED |
| DOE-SC | REST/JSON | Bearer (login) | Diário Oficial SC | 🔴 SOURCE_BLOCKED |
| PCP v2 | REST/JSON | Public | Licitações portais compras | 🔴 SOURCE_BLOCKED |
| ComprasGov | REST/JSON | Public | Licitações federais | 🟡 NÃO INGERIDO |
| TCE-SC (SCMWeb) | Web/HTML | Public | Licitações + contratos | 🔴 SOURCE_BLOCKED |
| Portais Transparência | Web/HTML | Public | 295+ portais (detectados) | 🔴 SOURCE_BLOCKED |
| BrasilAPI | REST/JSON | Public | CNPJ + IBGE | ✅ Enriquecimento |
| IBGE API | REST/JSON | Public | Dados municipais | ✅ Cache 90 dias |
| OpenAI | REST/JSON | API Key | GPT-4.1-nano + embeddings | ✅ On-demand |
| Portal Transparência | REST/JSON | API Key | CEIS + CNEP | ✅ Compliance |
| Planilha Seed | Arquivo .xlsx | — | Universo canônico | ✅ SHA-256 auditável |
| Hetzner Storage Box | SMB/rsync | SSH key | Backup pg_dump | ✅ Diário |

## Dívidas Técnicas

| ID | Severidade | Descrição | Epic/Iniciativa |
|----|-----------|-----------|-----------------|
| DT-01 | 🔴 CRITICAL | Migrations divergentes do schema real — 5 pontos críticos | EPIC-TD-001 |
| DT-02 | 🔴 CRITICAL | 7 fontes bloqueadas sem plano de ativação. Só PNCP ativo. | P1 Remediation |
| DT-03 | 🟠 HIGH | 0 views no banco real (migrations 009-012 nunca aplicadas) | EPIC-TD-001 |
| DT-04 | 🟠 HIGH | Dois orquestradores: monitor.py + orchestrator.py | EPIC-TD-001 |
| DT-05 | 🟠 HIGH | Win rate NOT_READY — métricas alternativas disponíveis mas incompletas | Regra #9 |
| DT-06 | 🟠 HIGH | ComprasGov + TCE/SC documentados mas não ingeridos | Regra #8 |
| DT-07 | 🟡 MEDIUM | BidsCrawler = dead code (imports quebrados) | EPIC-TD-001 |
| DT-08 | 🟡 MEDIUM | Cobertura testes <30% (137K LOC, 64 testes) | Qualidade |
| DT-09 | 🟡 MEDIUM | Helpers duplicados em crawlers | EPIC-TD-001 |
| DT-10 | 🟡 MEDIUM | ARP/PCA crawlers async, incompatíveis com monitor | EPIC-FEAT-001 |
| DT-11 | 🟡 MEDIUM | Dois pipelines analíticos coexistindo (Intel legado + QW-01) — sem critério de uso | QW-01 |
| DT-12 | 🟢 LOW | Sem smoke tests para APIs externas (PNCP) | Qualidade |
| DT-13 | 🟢 LOW | transparencia_config.yaml: 295 municípios detectados, crawling inativo | EPIC-FEAT-001 |

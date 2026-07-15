# Arquitetura — Extra Consultoria

## Visão Geral

Plataforma CLI de inteligência em licitações. Single-user, single-client
(Extra Construtora). DataLake PostgreSQL em VPS em nuvem. Multi-source data
ingestion. Relatórios PDF Big Four aesthetic.

Provedor de nuvem a definir. Ver `docs/architecture/adr/ADR-007-cloud-hosting-strategy.md`.

## C4 — Nível 1 (Contexto)

```
┌─────────────────────────────────────────────────────────────────┐
│  Usuário: Tiago Sasaki (Consultor)                               │
│  Acesso: SSH terminal (WSL → VPS em nuvem)                        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│  Extra Consultoria Platform (VPS em Nuvem)                        │
│                                                                   │
│  scripts/crawl/monitor.py  ← systemd timers                      │
│  scripts/intel_pipeline.py ← CLI on-demand                       │
│  scripts/reports/panorama.py ← scheduled + on-demand             │
└──────────────────────────┬───────────────────────────────────────┘
                           │
            ┌──────────────┼──────────────┬────────────┐
            ▼              ▼              ▼            ▼
     ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
     │  PNCP    │  │ DOM-SC   │  │ PCP v2   │  │ComprasGov│
     │  API     │  │  Portal  │  │  API     │  │  API     │
     └──────────┘  └──────────┘  └──────────┘  └──────────┘
```

## C4 — Nível 2 (Containers)

```
┌─────────────────────────────────────────────────────────────────┐
│                     VPS em Nuvem (Ubuntu 24.04)                    │
│                                                                   │
│  ┌─────────────────────┐  ┌──────────────────────┐              │
│  │ systemd timers      │  │ PostgreSQL 16         │              │
│  │                     │  │                       │              │
│  │ pncp-crawl-full     │  │ pncp_raw_bids         │              │
│  │ pncp-crawl-inc      │  │ pncp_supplier_contracts│             │
│  │ dom-sc-crawl        │  │ sc_public_entities    │              │
│  │ pcp-crawl           │  │ entity_coverage       │              │
│  │ compras-gov-crawl   │  │ enriched_entities     │              │
│  │ coverage-report     │  │ ingestion_runs        │              │
│  │ pncp-report-weekly  │  │ ingestion_checkpoints │              │
│  └─────────────────────┘  └──────────────────────┘              │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ Python 3.12 scripts (CLI)                                    │ │
│  │                                                              │ │
│  │ monitor.py ──→ pncp_crawler_adapter.py ──→ PNCP API         │ │
│  │             ──→ dom_sc_crawler.py ──→ DOM-SC                │ │
│  │             ──→ pcp_crawler.py ──→ PCP API                  │ │
│  │                                                              │ │
│  │ intel_pipeline.py ──→ intel_collect.py ──→ datalake + live  │ │
│  │                   ──→ intel_enrich.py                        │ │
│  │                   ──→ intel_llm_gate.py                      │ │
│  │                   ──→ intel_analyze.py ──→ OpenAI API       │ │
│  │                   ──→ intel_report.py ──→ PDF                │ │
│  └─────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

## Fluxo de Dados

```
1. INGESTÃO (systemd timers)
   PNCP/DOM-SC/PCP API → crawler → transform → upsert → entity_match

2. COVERAGE (diário)
   entity_coverage ← trigger after upsert
   coverage-report → gap detection → alert

3. PIPELINE INTEL (CLI on-demand)
   intel_collect → intel_enrich → intel_llm_gate →
   intel_extract_docs → intel_analyze → intel_report → PDF+Excel

4. RELATÓRIOS (scheduled + on-demand)
   panorama.py → terminal + Excel + PDF
```

## Decisões de Arquitetura

| Decisão | Escolha | Justificativa |
|---------|---------|---------------|
| DB | PostgreSQL raw (psycopg2) | Single user, sem REST overhead |
| Scheduler | systemd timers | Nativo Linux, sem Redis/ARQ |
| Crawl | Sync HTTP (urllib) | Simples, sem asyncio para cron |
| PDF | ReportLab | Código existente validado (10K+ linhas) |
| LLM | GPT-4.1-nano | Custo baixo, qualidade suficiente |
| Linguagem | Python 3.12 | Todo o source é Python |
| Paths | Absolutos via Path(__file__) | Independe do CWD |
| Config | Env vars + YAML | 12-factor, secrets fora do código |

## Schema (tabelas core)

```
pncp_raw_bids          ← Licitações (multi-source unificado)
pncp_supplier_contracts ← Contratos (histórico)
enriched_entities      ← Cache BrasilAPI/IBGE
sc_public_entities     ← 2.085 órgãos SC (planilha)
entity_coverage        ← Tracking de cobertura
ingestion_runs         ← Auditoria de crawls
ingestion_checkpoints  ← Crawls resumable
```

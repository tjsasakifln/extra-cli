# PRD: Plataforma de Inteligência em Licitações — Extra Construtora

> **Versão:** 1.0
> **Autor:** Morgan (PM Agent) — Synkra AIOX
> **Data:** 2026-07-10
> **Status:** Aprovado

---

## Visão

Plataforma CLI de consultoria estratégica para licitações públicas, provendo inteligência de mercado acionável para tomada de decisão da Extra Construtora.

## Problema

A Extra Construtora não tem visibilidade sistemática sobre:

- **Editais publicados** relevantes ao seu setor (engenharia civil, infraestrutura, pavimentação, edificações)
- **Histórico de preços praticados** por órgãos públicos — qual o ticket médio, qual a dispersão de valores
- **Movimentação de concorrentes** — quem ganhou o quê, por quanto, com que frequência
- **Sazonalidade e volumes** de contratação pública — quando concentram-se as publicações, quais meses são mais ativos
- **Tendências de modalidade** — pregão vs concorrência vs dispensa, mudanças ao longo do tempo

Sem esses dados, a construtora toma decisões no escuro: não sabe quais editais perseguir, qual preço propor, nem contra quem está competindo.

## Solução

Sistema automatizado que:

1. **Monitora 100% dos 2.085 órgãos públicos de SC** diariamente via múltiplas fontes (PNCP, DOM-SC, PCP, ComprasGov, TCE-SC, portais de transparência)
2. **Mantém datalake histórico** de licitações + contratos + preços praticados em PostgreSQL no Hetzner
3. **Gera relatórios de inteligência** (PDF Big Four aesthetic + Excel) sob demanda via CLI
4. **Roda em Hetzner VPS** com cron jobs (systemd timers), acessível via terminal/SSH

## Persona Única

**Tiago Sasaki** — Consultor de Inteligência em Licitações da Extra Construtora

- Acesso via terminal (SSH no Hetzner VPS ou WSL local)
- Single user, sem necessidade de interface web
- Precisa de respostas rápidas: search, stats, intel report
- Consome relatórios PDF para apresentar ao decisor da construtora

## Features (MoSCoW)

### Must Have

- [ ] **M1 — Coleta multi-source diária** — PNCP (full + incremental 3x/dia), DOM-SC, PCP, ComprasGov
- [ ] **M2 — DataLake PostgreSQL** — schema `pncp_raw_bids` + `pncp_supplier_contracts` + `sc_public_entities` + `entity_coverage`
- [ ] **M3 — Pipeline intel** — `collect → enrich → llm_gate → extract_docs → analyze → validate → report`
- [ ] **M4 — Monitoramento 100% entidades** — 2.085 órgãos SC, coverage tracking, gap detection
- [ ] **M5 — Relatório panorama setorial** — foco engenharia civil (PDF Big Four + Excel)
- [ ] **M6 — Cron jobs automatizados** — systemd timers para todos os crawlers
- [ ] **M7 — CLI access** — `search`, `stats`, `supplier`, `intel`, `panorama`

### Should Have

- [ ] **S1 — Análise de concorrência** — win rates, preços médios, ticket médio por concorrente
- [ ] **S2 — Relatório de sazonalidade** — heatmap mensal, picos por setor/UF
- [ ] **S3 — Export Excel estilizado** — openpyxl com headers formatados, fórmulas
- [ ] **S4 — Enriquecimento cadastral** — BrasilAPI (CNPJ), IBGE (municípios), SICAF (sanções)

### Could Have

- [ ] **C1 — Alertas Telegram** — notificação de novos editais matching setor
- [ ] **C2 — Simulador de lances** — `bid_simulator.py` (já existe no source)
- [ ] **C3 — Integração DOE-SC** — Diário Oficial do Estado para entidades estaduais
- [ ] **C4 — Dashboard TUI** — terminal UI com `rich` para visualização interativa

### Won't Have (agora)

- [ ] **W1 — Interface web** — escopo é CLI exclusivamente
- [ ] **W2 — Multi-tenant / multi-cliente** — single client (Extra Construtora)
- [ ] **W3 — Cobrança / Stripe** — serviço de consultoria, não SaaS
- [ ] **W4 — SEO programático** — sem interface pública
- [ ] **W5 — Auth/RLS** — single user, acesso direto ao PostgreSQL

## Fontes de Dados

| Fonte | Cobertura | Prioridade | Crawler |
|-------|-----------|------------|---------|
| **PNCP** (Portal Nacional de Contratações Públicas) | Nacional, adesão voluntária | P1 | `pncp_crawler.py` |
| **DOM-SC** (Diário Oficial dos Municípios de SC) | ~280 municípios SC | P1 | `dom_sc_crawler.py` |
| **PCP v2** (Portal de Compras Públicas) | ~100+ municípios SC | P2 | `pcp_crawler.py` |
| **ComprasGov v3** | Órgãos federais | P2 | `compras_gov_crawler.py` |
| **TCE-SC e-Sfinge** (agregador estadual) | 295 municípios SC | P1 (novo) | `tce_sc_crawler.py` |
| **Portais de Transparência Municipais** | 1 por município | P3 (gap-fill) | `transparencia_crawler.py` |

## Setores Monitorados (foco engenharia)

Do `config/sectors_config.yaml`:

1. **Engenharia e Construção** (CNAE 4120, 4110, 4212, 4221-4223, 4291-4292, 4299, 4311-4313, 4319, 4391, 4399, 7112, 7119)
2. **Engenharia Rodoviária** (CNAE 4211, 4213)
3. **Manutenção Predial** (CNAE 4321, 4322, 4329, 4330)

Demais setores (vestuário, alimentos, informática, software, facilities, vigilância, saúde, transporte, mobiliário, papelaria, materiais elétricos/hidráulicos) disponíveis para análises cruzadas.

## Métricas de Sucesso

| Métrica | Target | Medição |
|---------|--------|---------|
| Cobertura de entidades | 100% (2.085 órgãos) | `entity_coverage.is_covered = TRUE` |
| Falsos negativos | 0 | Cross-check manual periódico |
| Pipeline intel completo | < 120s (top 20) | Log de execução |
| Relatório PDF | < 30s geração | Log de execução |
| DataLake growth | < 1GB/mês | `pg_total_relation_size` |
| Uptime crawler | > 99% | `ingestion_runs.status` |
| Freshness dos dados | < 24h | `MAX(ingested_at) - NOW()` |

## Riscos e Mitigações

| Risco | Impacto | Probabilidade | Mitigação |
|-------|---------|--------------|-----------|
| PNCP API rate limiting | Bloqueio temporário | Média | Retry com exponential backoff, respeitar delays |
| DOM-SC mudar formato HTML | Crawler quebra | Média | Monitorar + alerta, adapter pattern |
| TCE-SC e-Sfinge inacessível (anti-bot) | Perda do agregador principal | Média | Fallback para portais individuais |
| Volume de dados > VPS capacity | Degradação | Baixa | Purge 400 dias, manter SC apenas |
| Custo OpenAI | Budget exceed | Baixa | Usar GPT-4.1-nano (mais barato), cache respostas |
| Bloqueio IP pela PNCP | Sem coleta | Baixa | User-agent identification, respeitar rate limits |

## Arquitetura (visão geral)

```
┌──────────────────────────────────────────────────┐
│                 Hetzner VPS (Ubuntu 24.04)        │
│                                                   │
│  systemd timers                                   │
│  ├── pncp-crawl-full.timer (daily 05:00 UTC)      │
│  ├── pncp-crawl-inc.timer (11, 17, 23 UTC)        │
│  ├── dom-sc-crawl.timer (06, 14, 22 UTC)          │
│  ├── pcp-crawl.timer (06:30, 14:30 UTC)           │
│  ├── compras-gov-crawl.timer (daily 07:00 UTC)     │
│  ├── pncp-contracts.timer (Mon/Wed/Fri 06:00)     │
│  ├── pncp-enrich.timer (daily 08:00 UTC)          │
│  ├── pncp-purge.timer (daily 07:00 UTC)           │
│  ├── coverage-report.timer (daily 09:00 UTC)      │
│  └── pncp-report-weekly.timer (Mon 07:00 UTC)     │
│                                                   │
│  PostgreSQL 17                                    │
│  ├── pncp_raw_bids (multi-source unificado)       │
│  ├── pncp_supplier_contracts                      │
│  ├── sc_public_entities (2.085 órgãos)            │
│  ├── entity_coverage (tracking)                   │
│  ├── enriched_entities (cache)                    │
│  ├── ingestion_runs (audit)                       │
│  └── ingestion_checkpoints (resume)               │
│                                                   │
│  Python 3.12 + scripts/                           │
│  ├── crawl/monitor.py (orquestrador)              │
│  ├── intel_pipeline.py (pipeline)                 │
│  ├── local_datalake.py (CLI)                      │
│  └── reports/ (panorama, sazonalidade, etc.)      │
└──────────────────────────────────────────────────┘
```

## Definição de Pronto (DoD)

- [ ] Cobertura 100% dos 2.085 órgãos verificada via `entity_coverage`
- [ ] Pipeline intel executado com sucesso para CNPJ da Extra Construtora
- [ ] Relatório panorama gerado em PDF + Excel
- [ ] Todos os systemd timers ativos e executando sem erro
- [ ] Repositório git privado com README e documentação
- [ ] PRD aprovado e versionado em `docs/prd/`

---

*Documento gerado por Morgan (PM Agent) — Synkra AIOX v5.2.9*

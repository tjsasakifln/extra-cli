# PRD: Plataforma de Inteligência em Licitações — Extra Construtora

> **Versão:** 1.1
> **Autor:** Morgan (PM Agent) — Synkra AIOX
> **Data:** 2026-07-10
> **Revisão:** 2026-07-10 — Audit de implementação, fontes reais, baselines, TCE-SC crawler ativo
> **Status:** Aprovado (living document)

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

- [x] **M1 — Coleta multi-source diária** — 8 crawlers ativos (PNCP, PNCP-ARP, PNCP-PCA, DOM-SC, PCP, ComprasGov, SC Compras, TCE-SC) + 1 gap-fill (Transparência).
- [x] **M2 — DataLake PostgreSQL** — 9 migrations aplicadas. Schema `pncp_raw_bids` + `pncp_supplier_contracts` + `sc_public_entities` + `entity_coverage` + `enriched_entities` + `ingestion_runs` + `ingestion_checkpoints`.
- [x] **M3 — Pipeline intel** — `intel_pipeline.py` completo com 7 stages: `collect → enrich → llm_gate → extract_docs → analyze → validate → report`.
- [x] **M4 — Monitoramento 100% entidades** — `sc_public_entities` (2.085 órgãos) + `entity_coverage` com coverage tracking e gap detection.
- [x] **M5 — Relatório panorama setorial** — `panorama.py` com foco engenharia civil (PDF Big Four + Excel).
- [x] **M6 — Cron jobs automatizados** — 11/12 systemd timers implementados (pncp-crawl-full, pncp-crawl-inc, coverage-report, dom-sc-crawl, pcp-crawl, compras-gov-crawl, pncp-contracts, pncp-enrich, pncp-purge, pncp-report-weekly, tce-sc-crawl). 1 pendente: a definir.
- [x] **M7 — CLI access** — `local_datalake.py` com comandos `search`, `stats`, `supplier`, `intel`, `panorama`.

### Should Have

- [x] **S1 — Análise de concorrência** — `victory_profile.py` + `win_loss_tracker.py` com win rates, preços médios, ticket médio por concorrente.
- [~] **S2 — Relatório de sazonalidade** — Estrutura base existe em `panorama.py`. Heatmap mensal e picos por setor/UF precisam de refinement.
- [x] **S3 — Export Excel estilizado** — `intel_excel.py` com openpyxl, headers formatados.
- [x] **S4 — Enriquecimento cadastral** — `enricher.py` (BrasilAPI CNPJ, IBGE municípios) + `sanctions.py` (SICAF).

### Could Have

- [ ] **C1 — Alertas Telegram** — Não implementado.
- [x] **C2 — Simulador de lances** — `bid_simulator.py` funcional.
- [ ] **C3 — Integração DOE-SC** — Não implementado. Crawler TCE-SC é pré-requisito para padronizar acesso a entidades estaduais.
- [ ] **C4 — Dashboard TUI** — Não implementado.

### Won't Have (agora)

- [x] **W1 — Interface web** — Mantido CLI exclusivamente.
- [x] **W2 — Multi-tenant / multi-cliente** — Single client (Extra Construtora).
- [x] **W3 — Cobrança / Stripe** — Serviço de consultoria, não SaaS.
- [x] **W4 — SEO programático** — Sem interface pública.
- [x] **W5 — Auth/RLS** — Single user, acesso direto ao PostgreSQL.

## Fontes de Dados

| Fonte | Cobertura | Prioridade | Crawler | Status |
|-------|-----------|------------|---------|--------|
| **PNCP API v1** (Portal Nacional de Contratações Públicas) | Nacional, adesão voluntária | P1 | `pncp_crawler_adapter.py` | ✅ Ativo |
| **PNCP — ARP** (Atas de Registro de Preço) | Nacional | P1 | `pncp_arp_crawler.py` | ✅ Ativo |
| **PNCP — PCA** (Plano de Contratação Anual) | Nacional | P2 | `pncp_pca_crawler.py` | ✅ Ativo |
| **DOM-SC** (Diário Oficial dos Municípios de SC) | ~280 municípios SC | P1 | `dom_sc_crawler.py` | ✅ Ativo |
| **PCP v2** (Portal de Compras Públicas) | ~100+ municípios SC | P2 | `pcp_crawler.py` | ✅ Ativo |
| **ComprasGov v3** | Órgãos federais | P2 | `compras_gov_crawler.py` | ✅ Ativo |
| **SC Compras** (Portal de Compras SC) | Órgãos estaduais SC | P2 | `sc_compras_crawler.py` | ✅ Ativo |
| **Portais de Transparência Municipais** | 1 por município | P3 (gap-fill) | `transparencia_crawler.py` | ✅ Ativo |
| **TCE-SC e-Sfinge** (agregador estadual) | 295 municípios SC | P2 (ativo) | `tce_sc_crawler.py` | ✅ Ativo |
| **DOE-SC** (Diário Oficial do Estado) | Entidades estaduais SC | P3 (futuro) | — | ❌ Não implementado |

> **Nota:** TCE-SC e-Sfinge era listado como P1 na v1.0. Análise do codebase revelou que o crawler nunca foi implementado. Rebaixado para P2 na v1.0. Implementado na revisão de 2026-07-10 via SCMWeb JSON API adapter (crawler ativo via monitor.py).

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

## Baselines e Métricas

| Métrica | Baseline Atual | Target | Status |
|---------|---------------|--------|--------|
| Crawlers ativos | 8 de 9 fontes | 9/9 fontes | 🟢 89% |
| Cobertura de entidades | Não medido | 100% (2.085 órgãos) | ⚪ Pendente |
| Falsos negativos | Não medido | 0 | ⚪ Pendente |
| Pipeline intel completo | Funcional (tempo não medido) | < 120s (top 20) | ⚪ Pendente |
| Relatório PDF | < 30s (não medido) | < 30s | ⚪ Pendente |
| DataLake growth | Não medido | < 1GB/mês | ⚪ Pendente |
| Uptime crawler | Não medido (sem timers) | > 99% | 🔴 0% (timers pendentes) |
| Freshness dos dados | Não medido | < 24h | ⚪ Pendente |
| Systemd timers ativos | 3/10 | 10/10 | 🔴 30% |

> **Ação imediata:** Instrumentar logging para capturar baselines reais nas primeiras 2 semanas de operação com timers completos.

## Premissas (Assumptions)

1. **PNCP API mantém contrato atual** — endpoints, rate limits e formato de resposta estáveis. Mudanças na API requerem adapter update.
2. **Hetzner VPS tem capacidade suficiente** — 4 vCPU, 8 GB RAM, 160 GB SSD estimados como suficientes para DataLake < 50 GB (SC apenas, purge 400 dias).
3. **OpenAI GPT-4.1-nano permanece disponível** — modelo econômico para LLM gate. Fallback: GPT-4o-mini ou DeepSeek.
4. **Single user, sem concorrência** — Tiago Sasaki é o único usuário. Sem necessidade de row-level security, connection pooling agressivo, ou rate limiting interno.
5. **DOM-SC mantém estrutura HTML atual** — mudanças no layout do portal quebram o parser. Adapter pattern mitiga mas não elimina risco.
6. **Fontes municipais (PCP, Transparência) mantêm acesso** — portais municipais são instáveis por natureza. Gap-fill com TCE-SC reduz dependência.
7. **Budget OpenAI < $50/mês** — com GPT-4.1-nano e cache de respostas, custo estimado viável para volume atual.
8. **SC como escopo geográfico permanente** — sem planos de expansão para outros estados no horizonte de 12 meses.

## Restrições (Constraints)

| Constraint | Tipo | Detalhe |
|-----------|------|---------|
| **Budget mensal** | Financeiro | Hetzner VPS (~€15/mês) + OpenAI (~$30-50/mês) + Domínios/Misc (~$10/mês). Total: ~$75/mês |
| **Tempo alocado** | Recurso | Desenvolvimento part-time. Estimativa: 10-15h/semana disponíveis para coding + manutenção. |
| **Single user** | Arquitetura | Sem REST API, sem auth, sem multi-tenant. PostgreSQL acessado diretamente via psycopg2. |
| **CLI only** | Interface | Sem interface web, sem dashboard browser. TUI (Could Have C4) é o máximo de UI previsto. |
| **Hetzner VPS recursos** | Infra | 4 vCPU, 8 GB RAM, 160 GB SSD. Sem escalabilidade horizontal. Monitorar disco a cada trimestre. |
| **Python 3.12** | Tecnologia | Linguagem única. Sem polyglot. Bibliotecas: psycopg2, ReportLab, openpyxl, rich, httpx. |
| **SC apenas** | Geográfico | Dados de outros estados só entram se PNCP retornar (adesão voluntária). Sem crawlers específicos para outros estados. |

## Fases e Timeline

### Fase 1 — Fundação (✅ Concluída)
**Período:** Jun-Jul 2026  
**Escopo:** M1, M2, M3, M4, M5, M7 (Must Have core)

- [x] 7 crawlers implementados e testados
- [x] DataLake schema (9 migrations)
- [x] Pipeline intel 7-stage funcional
- [x] Entity coverage (2.085 órgãos SC)
- [x] Relatório panorama PDF + Excel
- [x] CLI `local_datalake.py`

### Fase 2 — Automação (🔄 Em andamento)
**Período:** Jul 2026 (1-2 semanas)  
**Escopo:** M6 (systemd timers) + baselines

- [~] 3/10 systemd timers ativos
- [ ] 7 timers pendentes: dom-sc-crawl, pcp-crawl, compras-gov-crawl, pncp-contracts, pncp-enrich, pncp-purge, pncp-report-weekly
- [ ] Instrumentação de métricas (baselines)
- [ ] Monitoramento de uptime e freshness

### Fase 3 — Refinamento (Planejado)
**Período:** Ago 2026  
**Escopo:** Should Have + TCE-SC + qualidade

- [ ] S2 — Relatório sazonalidade com heatmap
- [x] **TCE-SC e-Sfinge crawler (SCMWeb JSON API)**
- [ ] Systemd timers refinados (retry, alertas de falha)
- [ ] Cross-check manual de falsos negativos
- [ ] Otimização de performance pipeline intel

### Fase 4 — Expansão (Backlog)
**Período:** Set 2026+  
**Escopo:** Could Have

- [ ] C1 — Alertas Telegram
- [ ] C3 — DOE-SC (se TCE-SC não cobrir)
- [ ] C4 — Dashboard TUI com `rich`
- [ ] Expansão de setores monitorados (se demanda)

---

*Documento gerado por Morgan (PM Agent) — Synkra AIOX v5.2.9*

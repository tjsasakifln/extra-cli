# PRD: Plataforma de Inteligência em Licitações — Extra Construtora

> **Versão:** 2.0
> **Autor:** Morgan (PM Agent) — Synkra AIOX
> **Data:** 2026-07-12
> **Revisão:** 2026-07-12 — Coverage manifest real (64.4%), 604 unresolved, métricas comerciais ALL not_ready, consolidação epics
> **Status:** Aprovado (living document)

> **Nota de fase:** este PRD mistura alvo futuro e capacidade atual. Na fase corrente, o baseline operacional e `local-first`, com datalake local e prioridade absoluta em freshness auditável de editais e contratos históricos. Acompanhamento de obras permanece fora de escopo.

---

## Visão

Plataforma CLI de consultoria estratégica para licitações públicas, provendo inteligência de mercado acionável para tomada de decisão da Extra Construtora.

Escopo corrente:

- editais abertos
- contratos históricos
- concorrentes/vencedores históricos
- apoio a preços praticados

Fora de escopo agora:

- acompanhamento de obras
- gestão de execução contratual

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

1. **Monitora progressivamente o universo alvo** via múltiplas fontes, sem assumir 100% de cobertura enquanto freshness e evidência não estiverem provadas
2. **Mantém datalake histórico** de licitações + contratos em PostgreSQL, atualmente operado em ambiente local
3. **Gera relatórios de inteligência** (PDF Big Four aesthetic + Excel) sob demanda via CLI
4. **Evolui para Hetzner VPS + Supabase + cron jobs** quando o fluxo local estiver validado

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
- [~] **M6 — Cron jobs automatizados** — 11/12 systemd timers implementados (pncp-crawl-full, pncp-crawl-inc, coverage-report ativos; pendentes: dom-sc-crawl, pcp-crawl, compras-gov-crawl, pncp-contracts, pncp-enrich, pncp-purge, pncp-report-weekly, tce-sc-crawl).
- [x] **M7 — CLI access** — `local_datalake.py` com comandos `search`, `stats`, `supplier`, `intel`, `panorama`.

### Should Have

- [~] **S1 — Análise de concorrência** — Estrutura base existe em `victory_profile.py` + `win_loss_tracker.py`. Dados de win rate ainda NOT_READY (sem tracking de propostas enviadas vs vencidas). Ticket médio por concorrente disponível via `v_supplier_winners`.
- [~] **S2 — Relatório de sazonalidade** — Estrutura base existe em `panorama.py`. Heatmap mensal e picos por setor/UF precisam de refinement.
- [x] **S3 — Export Excel estilizado** — `intel_excel.py` com openpyxl, headers formatados.
- [x] **S4 — Enriquecimento cadastral** — `enricher.py` (BrasilAPI CNPJ, IBGE municípios) + `sanctions.py` (SICAF).

### Could Have

- [ ] **C1 — Alertas Telegram** — Não implementado.
- [x] **C2 — Simulador de lances** — `bid_simulator.py` funcional.
- [ ] **C3 — Integração DOE-SC** — Não implementado.
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
| **PNCP API v1** (Portal Nacional de Contratações Públicas) | Nacional, adesão voluntária | P1 | `pncp_crawler_adapter.py` | Ativo |
| **PNCP — ARP** (Atas de Registro de Preço) | Nacional | P1 | `pncp_arp_crawler.py` | Ativo |
| **PNCP — PCA** (Plano de Contratação Anual) | Nacional | P2 | `pncp_pca_crawler.py` | Ativo |
| **DOM-SC** (Diário Oficial dos Municípios de SC) | ~280 municípios SC | P1 | `dom_sc_crawler.py` | Ativo |
| **PCP v2** (Portal de Compras Públicas) | ~100+ municípios SC | P2 | `pcp_crawler.py` | Ativo |
| **ComprasGov v3** | Órgãos federais | P2 | `compras_gov_crawler.py` | Ativo |
| **SC Compras** (Portal de Compras SC) | Órgãos estaduais SC | P2 | `sc_compras_crawler.py` | Ativo |
| **Portais de Transparência Municipais** | 1 por município | P3 (gap-fill) | `transparencia_crawler.py` | Ativo |
| **TCE-SC e-Sfinge** (agregador estadual) | 295 municípios SC | P2 (ativo) | `tce_sc_crawler.py` | Ativo |
| **DOE-SC** (Diário Oficial do Estado) | Entidades estaduais SC | P3 (futuro) | — | Nao implementado |

## Setores Monitorados (foco engenharia)

Do `config/sectors_config.yaml`:

1. **Engenharia e Construção** (CNAE 4120, 4110, 4212, 4221-4223, 4291-4292, 4299, 4311-4313, 4319, 4391, 4399, 7112, 7119)
2. **Engenharia Rodoviária** (CNAE 4211, 4213)
3. **Manutenção Predial** (CNAE 4321, 4322, 4329, 4330)

Demais setores (vestuário, alimentos, informática, software, facilities, vigilância, saúde, transporte, mobiliário, papelaria, materiais elétricos/hidráulicos) disponíveis para análises cruzadas.

## Comercial Readiness

### Definições

Para distinguir corretamente os 4 momentos de valor em uma licitação:

| Termo | Definição | Fonte | Status |
|-------|-----------|-------|--------|
| **Valor Estimado** | Valor estimado da licitação, publicado no edital | PNCP (edital), DOM-SC | NOT_READY — dados de edital não parseados item a item |
| **Valor Homologado** | Valor da proposta vencedora, homologado no resultado | PNCP (resultado), DOM-SC | NOT_READY — tabelas de itens de proposta não populadas |
| **Valor Contratado** | Valor global do contrato assinado | PNCP Contracts (`valor_global`) | Disponivel — `vp_supplier_contracts.valor_global` |
| **Valor Pago** | Valor efetivamente empenhado/pago | Portais de transparência, TCE-SC | NOT_READY — dados de empenho nao disponiveis no escopo atual |

### Métricas

| Métrica | Status | Definição | Impeditivo |
|---------|--------|-----------|------------|
| **Preço praticado** | NOT_READY | Valor homologado por item/lote, comparavel entre orgaos | Requer dados de propostas homologadas item a item — API publica PNCP nao expoe |
| **Desagio** | NOT_READY | (valor_estimado - valor_homologado) / valor_estimado | Requer dados relacionais entre edital e resultado — nao disponiveis |
| **Win rate** | NOT_READY | propostas enviadas / propostas vencidas | Requer tracking manual de propostas enviadas pela Extra Construtora |
| **Ticket medio por concorrente** | PARCIAL | valor total contratos / qtd contratos | `v_supplier_winners` calcula ticket medio, mas nao distingue vencedores por orgao/setor |
| **Probabilidade de relicitacao** | NOT_READY | Serie historica de contratos com datas de termino e renovacoes | Modelo nao calibrado; 98% contratos sem `data_fim_vigencia` |
| **Valor global contratos** | DISPONIVEL | `v_contract_historical` com `valor_global` | Mas `valor_global` nao e preco praticado — semantica nao desambiguada |

## Métricas de Sucesso

| Métrica | Baseline (2026-07-12) | Target | Medição |
|---------|----------------------|--------|---------|
| Cobertura de entidades | 64.4% (1.093/1.697 denominador confirmado) | >=95% | `entity_coverage.is_covered = TRUE` |
| Entidades nao resolvidas | 604 (sem coordenadas) | 0 | `coverage_manifest.unresolved` |
| Falsos negativos | Nao medido | 0 | Cross-check manual periódico |
| Pipeline intel completo | Funcional (tempo nao medido) | < 120s (top 20) | Log de execução |
| Relatório PDF | < 30s (não medido) | < 30s | Log de execução |
| DataLake growth | Nao medido | < 1GB/mês | `pg_total_relation_size` |
| Uptime crawler | 100% PNCP (health_check), timers pendentes | > 99% | `ingestion_runs.status` |
| Freshness dos dados | 479 fresh, 9 stale, 605 unknown | < 24h | `MAX(ingested_at) - NOW()` |
| Entes com contratos | 404 (37%) | >=80% | `v_contract_readiness` |
| Entes com editais abertos | 220 (20.1%) | >=80% | `coverage_manifest.open_tenders` |
| Systemd timers ativos | 3/11 | 11/11 | systemctl list-timers |
| Comercial: desagio | NOT_READY | DISPONIVEL | `coverage_manifest.commercial_metrics.desagio` |
| Comercial: preço praticado | NOT_READY | DISPONIVEL | `coverage_manifest.commercial_metrics.contract_total_value` |
| Comercial: win rate | NOT_READY | DISPONIVEL | `coverage_manifest.commercial_metrics.win_rate` |

> **Nota:** O denominador conservativo (1.697) inclui apenas entes com coordenadas confirmadas dentro ou fora do raio de 200km. Os 604 unresolved estão em um "unresolved block": sem coordenadas, não é possível confirmar cobertura >=95% nem excluí-los do denominador.

## Baselines e Métricas (v2.0 — dados reais)

### Cobertura

| Métrica | Valor | Fonte |
|---------|-------|-------|
| Total entes na planilha seed | 2.085 | `coverage_manifest.universe.total_seed_rows` |
| Universo confirmado | 1.481 | `coverage_manifest.universe.confirmed_universe` |
| Universo potencial | 2.085 | `coverage_manifest.universe.potential_universe` |
| Nao resolvidos (sem coordenadas) | 604 | `coverage_manifest.universe.unresolved` |
| Dentro do raio 200km | 1.093 | `coverage_manifest.universe.within_radius` |
| Fora do raio 200km | 388 | `coverage_manifest.universe.outside_radius` |
| **Cobertura real** | **64.4%** | `coverage_manifest.coverage.percent` (threshold 95% — NAO PASSOU) |
| Numerador (cobertos) | 1.093 | `coverage_manifest.coverage.numerator` |
| Denominador conservativo | 1.697 | `coverage_manifest.coverage.denominator_conservative` |
| Denominador confirmado | 1.093 | `coverage_manifest.coverage.denominator_confirmed` |
| Entes monitorados | 1.093 | `coverage_manifest.coverage.entities_monitored` |
| Entes stale | 9 | `coverage_manifest.coverage.stale` |

### Editais Abertos

| Métrica | Valor |
|---------|-------|
| Entes com editais abertos | 220 |
| Total editais abertos | 1.694 |
| % do universo confirmado | 20.1% |

### Contratos

| Métrica | Valor |
|---------|-------|
| Entes com contratos | 404 |
| Total contratos | 423.239 |
| % do universo confirmado | 37.0% |

### Freshness

| Métrica | Valor |
|---------|-------|
| Fresh (<=90 dias) | 479 |
| Stale (>90 dias) | 9 |
| Unknown | 605 |
| Janela de freshness | 90 dias |

### Source Health (PNCP)

| Métrica | Valor |
|---------|-------|
| Entity rows checked | 1.093 |
| Successful | 1.093 |
| Failed | 0 |
| Health % | 100% |
| Last check | 2026-07-12T17:40:30Z |

### Comercial — ALL NOT_READY

| Métrica | Status | Razão |
|---------|--------|-------|
| contract_total_value | NOT_READY | "Valor global de contrato não é 'preço praticado'. Preço praticado requer comparação com propostas homologadas item a item." |
| desagio | NOT_READY | "Deságio requer dados relacionais entre valor estimado do edital e valor homologado por item/lote." |
| win_rate | NOT_READY | "Win rate requer tracking de propostas enviadas vs vencidas por CNPJ." |
| relicitacao_probability | NOT_READY | "Probabilidade de relicitação requer série histórica de contratos com datas de término e renovações." |

### Gaps

| Tipo | Quantidade |
|------|-----------|
| unresolved (sem coordenadas) | 604 |
| **Total** | **604** |

## Riscos e Mitigações

| Risco | Impacto | Probabilidade | Mitigação |
|-------|---------|--------------|-----------|
| PNCP API rate limiting | Bloqueio temporário | Média | Retry com exponential backoff, respeitar delays |
| DOM-SC mudar formato HTML | Crawler quebra | Média | Monitorar + alerta, adapter pattern |
| 604 entidades sem coordenadas nunca resolvidas | Cobertura nunca atinge 95% | Alta | Geocode via IBGE API + nome do município (Story B2G-1) |
| Volume de dados > VPS capacity | Degradação | Baixa | Purge 400 dias, manter SC apenas |
| Custo OpenAI | Budget exceed | Baixa | Usar GPT-4.1-nano (mais barato), cache respostas |
| Bloqueio IP pela PNCP | Sem coleta | Baixa | User-agent identification, respeitar rate limits |
| Comercial metrics nunca saem de NOT_READY | Plataforma sem valor diferencial | Média | Stories B2G-2 e B2G-3 endereçam preço praticado e win rate |

## Arquitetura (visão geral)

```
+------------------------------------------------------------------+
|                 Hetzner VPS (Ubuntu 24.04)                        |
|                                                                   |
|  systemd timers                                                   |
|  +-- pncp-crawl-full.timer (daily 05:00 UTC)                      |
|  +-- pncp-crawl-inc.timer (11, 17, 23 UTC)                        |
|  +-- dom-sc-crawl.timer (06, 14, 22 UTC)                          |
|  +-- pcp-crawl.timer (06:30, 14:30 UTC)                           |
|  +-- compras-gov-crawl.timer (daily 07:00 UTC)                     |
|  +-- pncp-contracts.timer (Mon/Wed/Fri 06:00)                     |
|  +-- pncp-enrich.timer (daily 08:00 UTC)                          |
|  +-- pncp-purge.timer (daily 07:00 UTC)                           |
|  +-- coverage-report.timer (daily 09:00 UTC)                      |
|  +-- pncp-report-weekly.timer (Mon 07:00 UTC)                     |
|  +-- tce-sc-crawl.timer                                           |
|                                                                   |
|  PostgreSQL 17                                                    |
|  +-- pncp_raw_bids (multi-source unificado)                       |
|  +-- pncp_supplier_contracts                                      |
|  +-- sc_public_entities (2.085 orgaos)                            |
|  +-- entity_coverage (tracking)                                   |
|  +-- enriched_entities (cache)                                    |
|  +-- ingestion_runs (audit)                                       |
|  +-- ingestion_checkpoints (resume)                               |
|                                                                   |
|  Python 3.12 + scripts/                                           |
|  +-- crawl/monitor.py (orquestrador)                              |
|  +-- intel_pipeline.py (pipeline)                                 |
|  +-- local_datalake.py (CLI)                                      |
|  +-- reports/ (panorama, sazonalidade, etc.)                      |
|  +-- ci-check.sh (quality gate automation)                        |
+------------------------------------------------------------------+
```

## Definição de Pronto (DoD)

- [ ] Cobertura >=95% dos entes no raio 200km verificada via `coverage_manifest`
- [ ] 604 entidades nao resolvidas geocodificadas (zero unresolved)
- [ ] Pipeline intel executado com sucesso para CNPJ da Extra Construtora
- [ ] Relatório panorama gerado em PDF + Excel
- [ ] Todos os systemd timers ativos e executando sem erro
- [ ] Preco praticado, desagio e win rate disponiveis no CLI
- [ ] Quality gate automatizado (ruff + mypy + pytest + bandit) bloqueia commits com CRITICAL/HIGH
- [ ] Schema unificado documentado com caminho de migracao Supabase/Hetzner
- [ ] Repositório git privado com README e documentação

## Premissas (Assumptions)

1. **PNCP API mantém contrato atual** — endpoints, rate limits e formato de resposta estáveis. Mudanças na API requerem adapter update.
2. **Hetzner VPS tem capacidade suficiente** — 4 vCPU, 8 GB RAM, 160 GB SSD estimados como suficientes para DataLake < 50 GB (SC apenas, purge 400 dias).
3. **OpenAI GPT-4.1-nano permanece disponivel** — modelo econômico para LLM gate. Fallback: GPT-4o-mini ou DeepSeek.
4. **Single user, sem concorrência** — Tiago Sasaki é o único usuário. Sem necessidade de row-level security, connection pooling agressivo, ou rate limiting interno.
5. **DOM-SC mantém estrutura HTML atual** — mudanças no layout do portal quebram o parser. Adapter pattern mitiga mas não elimina risco.
6. **Fontes municipais (PCP, Transparência) mantêm acesso** — portais municipais são instáveis por natureza. Gap-fill com TCE-SC reduz dependência.
7. **Budget OpenAI < $50/mês** — com GPT-4.1-nano e cache de respostas, custo estimado viável para volume atual.
8. **SC como escopo geográfico permanente** — sem planos de expansão para outros estados no horizonte de 12 meses.
9. **604 entidades sem coordenadas podem ser geocodificadas via IBGE API** — premissa critica para desbloquear cobertura. Se IBGE API nao resolver, necessario geocode manual ou Google Maps API (custo adicional).

## Restrições (Constraints)

| Constraint | Tipo | Detalhe |
|-----------|------|---------|
| **Budget mensal** | Financeiro | Hetzner VPS (~15EUR/mês) + OpenAI (~$30-50/mês) + Domínios/Misc (~$10/mês). Total: ~$75/mês |
| **Tempo alocado** | Recurso | Desenvolvimento part-time. Estimativa: 10-15h/semana disponíveis para coding + manutenção. |
| **Single user** | Arquitetura | Sem REST API, sem auth, sem multi-tenant. PostgreSQL acessado diretamente via psycopg2. |
| **CLI only** | Interface | Sem interface web, sem dashboard browser. TUI (Could Have C4) é o máximo de UI previsto. |
| **Hetzner VPS recursos** | Infra | 4 vCPU, 8 GB RAM, 160 GB SSD. Sem escalabilidade horizontal. Monitorar disco a trimestre. |
| **Python 3.12** | Tecnologia | Linguagem única. Sem polyglot. Bibliotecas: psycopg2, ReportLab, openpyxl, rich, httpx. |
| **SC apenas** | Geográfico | Dados de outros estados só entram se PNCP retornar (adesão voluntária). Sem crawlers específicos para outros estados. |
| **604 unresolved** | Dados | Entidades sem coordenadas não podem ser incluidas/excluídas silenciosamente. Requerem resolução ativa. |
| **API pública PNCP** | Dados | Não expõe propostas perdedoras, valores homologados item a item, nem empenhos. Limitação estrutural. |

## Fases e Timeline

### Fase 1 — Fundação (Concluída)
**Período:** Jun-Jul 2026
**Escopo:** M1, M2, M3, M4, M5, M7 (Must Have core)

- [x] 8 crawlers implementados e testados
- [x] DataLake schema (migrations)
- [x] Pipeline intel 7-stage funcional
- [x] Entity coverage (2.085 órgãos SC)
- [x] Relatório panorama PDF + Excel
- [x] CLI `local_datalake.py`
- [x] Contract Intelligence Truth v1 (views analíticas + CLI)

### Fase 2 — Automação (Em andamento)
**Período:** Jul 2026
**Escopo:** M6 (systemd timers) + baselines + quality cleanup

- [~] 3/11 systemd timers ativos
- [ ] 8 timers pendentes
- [~] Instrumentação de métricas (coverage_manifest funcional)
- [~] Limpeza de qualidade de código (TD-7.1 parcial — auto-fix concluido)
- [ ] Resolução de imports quebrados e modulos com hifen (TD-8.x)

### Fase 3 — Refinamento (Planejado)
**Período:** Jul-Ago 2026
**Escopo:** Should Have + cobertura + entidades

- [ ] S2 — Relatório sazonalidade com heatmap
- [ ] **B2G-1: Resolver 604 entidades nao resolvidas** (geocode via IBGE)
- [ ] Reprojetar coverage evidence apos resolucao
- [ ] Sistema de resume para crawlers
- [ ] Cross-check manual de falsos negativos

### Fase 4 — Analytics & Schema (Planejado)
**Período:** Ago 2026
**Escopo:** Schema final, Supabase path, Otimização

- [ ] **B2G-5: Schema final + Supabase path** (migration 006-v3 unificada)
- [ ] Otimização de performance pipeline intel
- [ ] Expansão de cobertura de testes (>=60% modulos core)
- [ ] Documentação do caminho de migração local -> Supabase/Hetzner

### Fase 5 — Comercial Metrics (Planejado)
**Período:** Ago-Set 2026
**Escopo:** Preço praticado, deságio, concorrência

- [ ] **B2G-2: Métricas comerciais — preço praticado**
- [ ] Distinguir valor_estimado, valor_homologado, valor_contratado, valor_pago
- [ ] **B2G-3: Concorrência e win rate**
- [ ] Identificar CNPJs vencedores, calcular win rate, ticket médio
- [ ] CLI `competitors` com ranking, win rate, ticket médio
- [ ] ADR-002: Decisão de arquitetura para preço praticado

### Fase 6 — Production Hardening (Planejado)
**Período:** Set 2026
**Escopo:** Quality gates, CI/CD, seguranca

- [ ] **B2G-4: Quality Gate Automation** (pre-commit hook + CI-like script)
- [ ] B2G-4a: `scripts/ci-check.sh` roda ruff + mypy + pytest + bandit
- [ ] B2G-4b: Bloquear commit se CRITICAL/HIGH findings
- [ ] ADR-003: Arquitetura Supabase self-hosted em Hetzner
- [ ] CI/CD pipeline (integração com GitHub Actions ou equivalente local)

### Fase 7 — Expansão (Backlog)
**Período:** Set 2026+
**Escopo:** Could Have

- [ ] C1 — Alertas Telegram
- [ ] C3 — DOE-SC
- [ ] C4 — Dashboard TUI com `rich`
- [ ] Expansão de setores monitorados (se demanda)
- [ ] Supabase self-hosted deployment (documentado, nao executado)

---

## ADRs Relacionados

| ADR | Título | Status | Link |
|-----|--------|--------|------|
| ADR-001 | Contract Intelligence Truth v1 | Implementado | `docs/decisions/contract-intelligence-truth-v1.md` |
| ADR-002 | Preço Praticado — Multi-source Value Semantics | Pendente | `docs/decisions/adr-002-preco-praticado.md` |
| ADR-003 | Supabase Self-Hosted em Hetzner | Pendente | `docs/decisions/adr-003-supabase-self-hosted.md` |

---

## Consolidação de Epics (v2.0)

A partir da v2.0, todos os epics anteriores (EPIC-001, EPIC-COVERAGE-100PCT, EPIC-FEAT-001, EPIC-TD-001, EPIC-TD-002, EPIC-TD-003) são consolidados em um unico **EPIC-MASTER-B2G-READINESS**. As stories existentes permanecem como referência histórica, mas o planejamento ativo usa apenas o master epic.

| Epic Anterior | Status | Destino |
|--------------|--------|---------|
| EPIC-001 (100% cobertura original) | Backlog | Historico — conteudo incorporado ao master |
| EPIC-COVERAGE-100PCT (plano mestre cobertura) | Draft | Referencia historica — stories nao executadas incorporadas ao master |
| EPIC-FEAT-001 (expansao crawlers) | Ready | Concluido (crawlers implementados) — master atualiza status |
| EPIC-TD-001 (debitos tecnicos) | Ready | Em execucao — TD-7.1 em InProgress; demais pendentes |
| EPIC-TD-002 (qualidade codigo) | — | Fundido ao EPIC-TD-001 na consolidação |
| EPIC-TD-003 (reversa remediation) | Draft | Stories incorporadas ao master |

---

*Documento gerado por Morgan (PM Agent) — Synkra AIOX v5.2.9*

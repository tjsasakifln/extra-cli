# EPIC-001: 100% Cobertura dos 2.085 Entes Públicos de SC

> **Epic:** EPIC-001
> **Autor:** Morgan (PM) — Synkra AIOX
> **Data:** 2026-07-10
> **Status:** Backlog
> **PRD:** docs/prd/PRD-consultoria-extra.md v1.1

---

## Objetivo

Atingir **100% de cobertura** dos 2.085 entes públicos de Santa Catarina listados na planilha `Extra - alvos de licitação. R-0.xlsx`. Cada ente deve ter `is_covered = TRUE` em pelo menos uma fonte de dados dentro da janela de 90 dias.

## Situação Atual

| Indicador | Valor |
|-----------|-------|
| Entes na planilha | 2.085 (296 municípios) |
| Crawlers ativos | 7 (PNCP, PNCP-ARP, PNCP-PCA, DOM-SC, PCP, ComprasGov, SC Compras) |
| Systemd timers | 3/10 implementados |
| Cobertura atual | **Não medida** (baseline pendente) |
| Agregador TCE-SC | ❌ Não implementado |
| Entity matching | Funcional (name-based), acurácia não medida |

## Análise de Gap

### Dimensão 1 — Automação (systemd timers)

Sem automação, crawlers não rodam → dados não entram → cobertura não avança.

| Timer | Crawler | Status |
|-------|---------|--------|
| pncp-crawl-full | PNCP | ✅ Ativo |
| pncp-crawl-inc | PNCP | ✅ Ativo |
| coverage-report | Coverage | ✅ Ativo |
| dom-sc-crawl | DOM-SC | ❌ Pendente |
| pcp-crawl | PCP | ❌ Pendente |
| compras-gov-crawl | ComprasGov | ❌ Pendente |
| pncp-contracts | PNCP Contracts | ❌ Pendente |
| pncp-enrich | Enricher | ❌ Pendente |
| pncp-purge | Purge | ❌ Pendente |
| pncp-report-weekly | Report | ❌ Pendente |

### Dimensão 2 — Fontes por Tipo de Ente

| Natureza | Qtd Entes | Fonte Primária | Fonte Secundária | Gap Fill |
|----------|-----------|----------------|------------------|----------|
| Municipal Executivo | 445 | DOM-SC | PCP | TCE-SC, Transparência |
| Municipal Legislativo | 299 | DOM-SC | PCP | TCE-SC |
| Município (prefeitura) | 295 | DOM-SC | PCP, PNCP | TCE-SC |
| Fundação Pública Municipal | 266 | DOM-SC | PCP | TCE-SC |
| Autarquia Municipal | 167 | DOM-SC | PCP | TCE-SC |
| Consórcio Público | 99 | DOM-SC | PNCP | TCE-SC |
| Estadual (todos) | 269 | SC Compras | PNCP, DOE-SC | TCE-SC |
| Federal (todos) | 311 | ComprasGov | PNCP | — |
| Demais | 34 | PNCP | — | — |
| **Total** | **2.085** | | | |

### Dimensão 3 — TCE-SC (Agregador)

TCE-SC e-Sfinge é o sistema de prestação de contas do Tribunal de Contas de SC. **Todos os 295 municípios** + órgãos estaduais reportam licitações e contratos ao TCE-SC. É a fonte mais completa para SC — sem ele, dependemos de:
- DOM-SC (cobertura parcial, ~280 municípios, HTML scraping frágil)
- PCP (cobertura parcial, ~100+ municípios)
- Portais de Transparência individuais (295 portais diferentes, inviável)

**TCE-SC é o acelerador crítico para 100% de cobertura.**

### Dimensão 4 — Entity Matching

`pncp_raw_bids.matched_entity_id` depende de name-matching entre `orgao_nome` da licitação e `razao_social` das 2.085 entidades. Sem matching correto, bids não acionam o trigger `update_entity_coverage()` → cobertura não sobe.

## Stories

| # | Story | Escopo | Prioridade | Dependências |
|---|-------|--------|------------|--------------|
| 001.1 | Systemd timers — 7 faltantes | Criar e ativar timers restantes | P1 | Nenhuma |
| 001.2 | TCE-SC e-Sfinge crawler | Implementar crawler do portal e-Sfinge | P1 | Nenhuma |
| 001.3 | Entity name-matching refinement | Melhorar acurácia do matched_entity_id | P1 | Nenhuma |
| 001.4 | Seed sc_public_entities | Import planilha Excel → PostgreSQL | P2 | Nenhuma |
| 001.5 | Coverage baseline + monitoring | Medir cobertura atual, dashboard de gaps | P2 | 001.1, 001.3 |
| 001.6 | Transparência gap-fill automation | Cobrir municípios sem DOM-SC nem PCP | P2 | 001.5 |
| 001.7 | Weekly coverage report | Relatório automatizado de cobertura | P3 | 001.5 |

## Métricas de Sucesso

| Métrica | Baseline | Target | Prazo |
|---------|----------|--------|-------|
| Cobertura de entes | 0% (não medido) | 100% (2.085/2.085) | 4 semanas |
| Systemd timers ativos | 3/10 | 10/10 | 1 semana |
| TCE-SC crawler | Não existe | Funcional, integrado ao monitor | 2 semanas |
| Entity matching accuracy | Não medido | > 95% | 2 semanas |
| Falsos negativos (gap) | Não medido | < 10 entes | 4 semanas |
| Tempo de ingestão | Manual | 100% automatizado | 1 semana |

## Riscos

| Risco | Mitigação |
|-------|-----------|
| TCE-SC e-Sfinge ter anti-bot (Cloudflare, CAPTCHA) | Tentar API oculta primeiro; fallback para Selenium/Playwright |
| DOM-SC mudar estrutura HTML durante implementação | Adapter pattern já existe; monitorar + alertar |
| Municípios pequenos não publicarem em nenhuma fonte digital | Marcar como "sem publicações no período" (gap legítimo, não falha) |
| Volume de dados do TCE-SC sobrecarregar VPS | Filtrar por setores engenharia + SC apenas |

---

*Epic gerado por Morgan (PM Agent) — Synkra AIOX v5.2.9*

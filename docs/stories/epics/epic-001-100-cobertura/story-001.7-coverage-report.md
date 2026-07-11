# Story 001.7: Weekly Coverage Report Automation

> **Story:** 001.7 | **Epic:** EPIC-001 | **Status:** InReview
> **Prioridade:** P3 | **Estimativa:** 4h
> **Executor:** @dev | **Quality Gate:** @architect | **Quality Gate Tools:** pytest, coderabbit, ruff

## Objetivo

Gerar relatório semanal automatizado de cobertura dos 2.085 entes, com visão executiva para o consultor Tiago Sasaki: quantos % cobertos, onde estão os gaps, tendência vs semana anterior.

## Contexto

Com os systemd timers ativos (001.1), entity matching funcionando (001.3), e baseline medida (001.5), precisamos fechar o loop com um relatório semanal que o Tiago possa consumir sem precisar rodar queries SQL manualmente.

O relatório deve ser:
- **PDF executivo** — 1-2 páginas, Big Four aesthetic, para apresentar ao decisor da construtora
- **Excel detalhado** — lista de entes descobertos, por município e natureza jurídica

## Acceptance Criteria

- [x] **AC1:** Script `scripts/reports/coverage_weekly.py` que gera:
  - PDF executivo (ReportLab, mesmo estilo do `panorama.py`)
  - Excel detalhado (openpyxl, mesmo estilo do `intel_excel.py`)
- [x] **AC2:** Conteúdo do PDF:
  - **Capa:** "Relatório de Cobertura — [data]" | "Extra Construtora"
  - **KPIs:** Cobertura total (%), Entes cobertos/descobertos, Variação vs semana anterior
  - **Gráfico:** Cobertura por fonte (bar chart horizontal, ASCII no terminal, visual no PDF)
  - **Top 10 gaps:** Municípios com mais entes descobertos
  - **Tendência:** 4-week trend (sparkline ou tabela)
  - **Ações recomendadas:** Quais fontes precisam de atenção
- [x] **AC3:** Conteúdo do Excel:
  - Aba 1: Resumo (mesmos KPIs do PDF)
  - Aba 2: Entes descobertos (razao_social, municipio, natureza_juridica, fontes disponíveis)
  - Aba 3: Cobertura por município (nome, total entes, cobertos, %)
  - Aba 4: Cobertura por natureza jurídica
- [x] **AC4:** Relatório usa dados da view `v_coverage_gaps` e `coverage_snapshots`
- [x] **AC5:** Systemd timer `coverage-report-weekly.timer` agenda geração toda segunda-feira 08:00 UTC
- [x] **AC6:** Output salvo em `output/reports/coverage/YYYY-MM-DD/` com nome padronizado:
  - `coverage-report-YYYY-MM-DD.pdf`
  - `coverage-detail-YYYY-MM-DD.xlsx`
- [x] **AC7:** Log de geração: tempo de execução, queries executadas, tamanho dos arquivos

## Layout do PDF (referência)

```
┌──────────────────────────────────────────┐
│  RELATÓRIO DE COBERTURA                  │
│  Extra Construtora — SC                  │
│  Semana 28, 2026 (07/Jul — 13/Jul)      │
│                                           │
│  ┌─────────┐  ┌─────────┐  ┌──────────┐ │
│  │ COBERT. │  │ ENTES   │  │ VARIAÇÃO │ │
│  │  87.3%  │  │1820/2085│  │  +2.1% ▲ │ │
│  └─────────┘  └─────────┘  └──────────┘ │
│                                           │
│  Cobertura por Fonte                     │
│  ████████████████ PNCP        92% (1918) │
│  ████████████ DOM-SC         73% (1522)  │
│  ██████ PCP                  42% (875)   │
│  ██████████████ ComprasGov   88% (274)   │
│  ███ SC Compras              21% (56)    │
│  █ TCE-SC (NOVO)              8% (17)    │
│                                           │
│  Top 5 Municípios com Gaps               │
│  1. Abdon Batista (12 entes)             │
│  2. Zortéa (8 entes)                     │
│  3. ...                                   │
│                                           │
│  Tendência 4 Semanas                     │
│  W25: 82.1%  W26: 84.5%  W27: 85.2%     │
│  W28: 87.3%  ▲                           │
│                                           │
│  Recomendações:                          │
│  • Ativar TCE-SC para cobrir 45 mun.     │
│  • Verificar DOM-SC em 12 municípios     │
└──────────────────────────────────────────┘
```

## File List

- `scripts/reports/coverage_weekly.py` — Gerador do relatório
- `scripts/reports/__init__.py` (*) — Atualizar exports
- `deploy/systemd/coverage-report-weekly.service` — Service (ExecStart: python3 -m scripts.reports.coverage_weekly)
- `deploy/systemd/coverage-report-weekly.timer` — Timer (Monday 08:00 UTC)
- `db/migrations/012_coverage_snapshots.sql` — Migration: coverage_snapshots + v_coverage_gaps + views (Story 001.5 pendente)

## Riscos

| Risco | Impacto | Mitigação |
|-------|---------|-----------|
| PDF quebrar com dados vazios | Relatório ilegível | Template com fallback "Dados insuficientes para o período" |
| Geração lenta (>30s) com muitas queries | Timeout, relatório atrasado | Cache de views; materialized view `mv_coverage_weekly` refresh 1x/dia |
| Dependência de `coverage_snapshots` vazia | Relatório sem tendência | Se snapshots < 2, omitir seção de tendência (não quebrar) |
| Estilo divergir do `panorama.py` | Inconsistência visual nos PDFs | Reutilizar `scripts/lib/doc_templates.py` (estilo compartilhado) |

## Dependencies

- Story 001.5 (coverage baseline + views)
- Story 001.1 (systemd timers — dados precisam estar fluindo)
- `panorama.py` (referência de estilo PDF)
- `intel_excel.py` (referência de estilo Excel)

## DoD

- [x] PDF executivo gerado com KPIs, gráficos e recomendações
- [x] Excel detalhado com 4 abas
- [x] Timer semanal ativo
- [ ] Primeiro relatório gerado e revisado pelo Tiago
- [ ] Tempo de geração < 30s (cache de views no PostgreSQL)

## 🤖 CodeRabbit Integration

- **Story Type:** Feature
- **Complexity:** Low
- **Primary Agent:** @dev
- **Self-Healing:** light mode (2 iterations, 30min, CRITICAL only)
- **Severity Behavior:**
  - CRITICAL: auto_fix
  - HIGH: auto_fix (iteration < 2), else document_as_debt
  - MEDIUM: document_as_debt
  - LOW: ignore
- **Quality Gates:**
  - [ ] Pre-Commit (@dev) — pytest, ruff, PDF generation test
  - [ ] Pre-PR (@architect) — code review, visual consistency, template reuse
- **Focus Areas:** ReportLab PDF patterns, openpyxl patterns, template reuse, SQL query performance, visual consistency

## Change Log

| Data | Versão | Mudança | Autor |
|------|--------|---------|-------|
| 2026-07-10 | 1.0.0 | Story criada — EPIC-001 | @pm |
| 2026-07-10 | 1.1.0 | Validação PO: adicionados Status, executor, riscos, CodeRabbit, Change Log | @po |
| 2026-07-10 | 1.1.0 | Validated GO (10/10) — Status: Draft → Ready | @po |
| 2026-07-10 | 2.0.0 | Implementado: coverage_weekly.py, migration 012, systemd timer, PDF+Excel; Status: Ready → InReview | @dev |

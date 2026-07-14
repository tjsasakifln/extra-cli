# Reports — Design Técnico (v2.0)

> Gerado pelo Writer em 2026-07-11T22:30:00Z | **Expandido pelo Reviewer em 2026-07-13** | doc_level: completo | Base: 249340d
> **Fontes brownfield:** plano-mestre §16 (P1-03), §22 (DoD); epic-technical-debt.md

## Interface

### Relatórios (6 artefatos)

| Relatório | Entrada | Saída | Formato | Fonte |
|-----------|---------|-------|---------|-------|
| Panorama Executivo | PostgreSQL views + universe_run_id | PDF multi-seção | ReportLab PDF | `scripts/reports/panorama.py` |
| Cobertura Semanal | coverage_evidence + freshness | PDF/CSV | ReportLab | `scripts/reports/coverage_weekly.py` |
| Coverage Gaps | coverage_evidence (state=error/blocked/stale) | Relatório de gaps | PDF/CSV | `scripts/reports/coverage_gaps.py` |
| Radar CSV (QW-01) | opportunity_intel table | CSV 34 colunas | CSV | `scripts/opportunity_intel/radar.py` |
| Readiness Manifest | consulting_readiness check | JSON | JSON | `scripts/consulting_readiness.py` |
| 🔴 build-delivery | Todos os dados + perfil + seed | Excel 14 abas + PDF | openpyxl + ReportLab | NÃO IMPLEMENTADO (P1-03) |

### Funções Core

| Símbolo | Assinatura | Retorno | Observação |
|---------|-----------|---------|------------|
| `_build_cover` | `(story, metadata)` | `None` | Capa com run_id, data, git_sha |
| `_build_executive_summary` | `(story, data)` | `None` | Sumário executivo 1 página |
| `_build_section_*` | `(story, data)` | `None` | Section Builder Pattern — cada seção é função independente |
| `run_panorama` | `(conn, profile, output_path)` | `PanoramaResult` | Pipeline completo |
| `run_coverage_weekly` | `(conn, output_path)` | `CoverageWeeklyResult` | Cobertura semanal |

## Fluxo Principal (Panorama Executivo)

1. **Load data:** PostgreSQL views → datasets normalizados (ente, contratos, editais, concorrentes) 🟢
2. **Section Builder Pattern:** cada seção = função independente → `story.extend()` → `doc.build()` 🟢
3. **Semantic Dedup:** Pass1 composite key exact → Pass2 Jaccard pairwise (UF-scoped). ≥0.85=remove, 0.75-0.85=warn, <0.75=keep 🟢
4. **PDF generation:** ReportLab com templates B2G, fontes embedadas, tabelas paginadas 🟢
5. **Output:** `output/deliveries/<run_id>/` com PDF + metadados 🟢

## Fluxo Principal (Coverage Weekly)

1. **Query evidence:** `coverage_evidence` table → estado por ente×fonte×capacidade
2. **Calculate metrics:** 7 dimensões de cobertura (plano-mestre §3)
3. **Compare:** vs semana anterior (snapshot)
4. **Generate:** PDF + CSV com trending
5. **Alert:** se coverage caiu > 5pp ou fonte ficou stale

## Fluxo Principal (🔴 build-delivery — P1-03)

1. `python -m scripts.consulting.cli build-delivery --profile extra.yaml --seed "Extra - alvos.xlsx" --period-years 3`
2. Congelar universo → verificar freshness → executar readiness → gerar datasets
3. Bloquear claims não prontos → gerar Excel 14 abas → gerar PDF
4. Emitir manifest com run_id, git_sha, seed_sha256, schema_fingerprint
5. **Status:** NÃO IMPLEMENTADO

## Dependências

| Componente | Relação | Como usa |
|------------|--------|----------|
| PostgreSQL | Hard | Views canônicas como fonte de dados |
| `scripts/coverage/` | Hard | Métricas de cobertura alimentam relatórios (Coverage Weekly, Coverage Gaps) |
| `scripts/opportunity_intel/` | Hard | Dados de editais abertos para Panorama e Radar |
| `scripts/contract_intel/` | Hard | Contratos históricos e concorrentes para Panorama |
| `scripts/lib/universe.py` | Hard | Denominador canônico para todas as métricas |
| ReportLab 4.5.1 | Hard | Geração de PDF (ADR-006) |
| openpyxl 3.1.5 | Hard | Geração de Excel |
| `config/client_profiles/extra.yaml` | Config | Perfil para filtros e scoring |

## Decisões de Design Identificadas

| Decisão | Evidência no código | Confiança |
|---------|---------------------|-----------|
| Section Builder Pattern: cada seção = função independente | `panorama.py` | 🟢 |
| PDF via ReportLab, não HTML→PDF (ADR-006) | `requirements.txt:reportlab==4.5.1`, ADR-006 | 🟢 |
| Semantic dedup em 2 passes (exact + Jaccard UF-scoped) | `panorama.py` | 🟢 |
| Big Four Design System para consistência visual | ADR-006 | 🟢 |
| PDF e Excel devem compartilhar run_id (DoD §12) | `plano-mestre §16` | 🟢 |
| 🔴 build-delivery command não implementado | `plano-mestre §16` | 🔴 |

## Riscos e Lacunas

- 🔴 **CRÍTICO:** Comando `build-delivery` (P1-03) não implementado. Sem ele, não há entrega consolidada PDF+Excel com run_id único, bloqueando DoD §12.
- 🔴 **CRÍTICO:** Reports dependem do módulo Coverage para métricas (Coverage Weekly, Coverage Gaps), mas essa dependência não está documentada nas interfaces formais — acoplamento implícito.
- 🔴 Reports dependem de views canônicas (`v_contracts_canonical`, `v_suppliers_canonical`) que ainda não foram materializadas (P0-02).
- 🟡 Semantic dedup com Jaccard pode produzir falsos positivos/negativos em objetos curtos ou muito similares.
- 🟡 Design System "Big Four" referenciado no ADR-006 mas sem spec formal de componentes visuais.

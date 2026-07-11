# Reports — Requirements

> Gerado pelo Writer em 2026-07-11T22:30:00Z | doc_level: completo | Base: e9729e1

Relatórios executivos: panorama de mercado, cobertura, proposta comercial PDF e relatório B2G (6.4K LOC, 80+ funções). Design system Big Four.

## Requisitos Funcionais

| ID | Descrição | Prioridade | Fonte |
|----|----------|-----------|-------|
| RF-R01 | Panorama: 6 seções SQL, export terminal+Excel | Must | `panorama.py:1-343` |
| RF-R02 | Coverage Weekly: PDF executivo + Excel 4 sheets, tendência, recomendações | Must | `coverage_weekly.py:1-1169` |
| RF-R03 | B2G Report: 9 seções, 80+ funções, Big Four aesthetic | Must | `generate-report-b2g.py:1-6479` |
| RF-R04 | Proposta Comercial PDF: capa, sumário, metodologia, investimento | Should | `generate-proposta-pdf.py:1-923` |
| RF-R05 | Semantic Dedup: 2-pass, Jaccard, 55 stopwords | Should | `report_dedup.py:1-189` |
| RF-R06 | Coverage Gaps: export Excel 3 sheets | Should | `coverage_gaps.py:1-213` |
| RF-R07 | Design System Big Four: INK #1B2A3D, ACCENT #8B7355, Times+Helvetica, A4 | Must | Todos os PDFs |

## Critérios de Aceitação

```gherkin
Dado dados de cobertura da semana atual e 3 semanas anteriores
Quando coverage_weekly.py é executado com --format pdf
Então PDF gerado com capa, KPIs, tabela de sources, top-10 gaps, tendência com setas, recomendações
```

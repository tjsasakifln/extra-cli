# Requirements — Módulo `reports`

> 🟢 CONFIRMADO — `scripts/reports/panorama.py`, `coverage_gaps.py`, `coverage_weekly.py`

## Funcionais

| ID | Requisito | Fonte | Confiança |
|----|-----------|-------|-----------|
| FR-R1 | Panorama de mercado: volume por modalidade, top municípios, sazonalidade, concorrência, setores | `panorama.py:51-80` | 🟢 |
| FR-R2 | Output multi-formato: terminal (Rich), Excel (openpyxl), PDF (ReportLab) | `panorama.py:11-12` | 🟢 |
| FR-R3 | Filtros: --setor, --uf, --dias, --monthly | `panorama.py:9-11` | 🟢 |
| FR-R4 | Detecção de gaps de cobertura: entidades descobertas agrupadas por município e natureza jurídica | `coverage_gaps.py` | 🟢 |
| FR-R5 | Relatório semanal: comparação 7 dias vs semana anterior (delta) | `coverage_weekly.py` | 🟢 |
| FR-R6 | Breakdown por fonte de dados no coverage report | `panorama.py` | 🟢 |

## Não Funcionais

| ID | Requisito | Evidência | Confiança |
|----|-----------|-----------|-----------|
| NFR-R1 | Queries parametrizadas (sem SQL injection) | `panorama.py:40-41` | 🟢 |
| NFR-R2 | Conexão PostgreSQL via psycopg2 com DSN do ambiente | `panorama.py:27-35` | 🟢 |

## MoSCoW

- **Must:** FR-R1, FR-R2, FR-R4
- **Should:** FR-R3, FR-R5, FR-R6

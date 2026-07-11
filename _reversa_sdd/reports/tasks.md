# Tasks — Módulo `reports`

> 🟢 CONFIRMADO

### T1: Panorama de Mercado
- **Arquivo legado:** `scripts/reports/panorama.py`
- **Confiança:** 🟢
- **Descrição:** 5 seções analíticas com queries SQL parametrizadas. Output triplo: terminal (Rich), Excel (openpyxl), PDF (ReportLab opcional).
- **Critério de pronto:** 5 seções funcionais. 3 formatos de output.

### T2: Coverage Gaps
- **Arquivo legado:** `scripts/reports/coverage_gaps.py`
- **Confiança:** 🟢
- **Descrição:** Query uncovered entities agrupadas por município e natureza jurídica. Output CSV + terminal.
- **Critério de pronto:** Gaps identificados. CSV gerado.

### T3: Coverage Weekly
- **Arquivo legado:** `scripts/reports/coverage_weekly.py`
- **Confiança:** 🟢
- **Descrição:** Query 7 dias, comparar com semana anterior. Calcular delta. Output PDF.
- **Critério de pronto:** Relatório semanal com delta funcional.

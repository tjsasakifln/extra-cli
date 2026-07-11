# Design — Módulo `reports`

> 🟢 CONFIRMADO — `panorama.py`, `coverage_gaps.py`

## Panorama de Mercado

```
panorama.py
  ├── section_volume(conn, uf, dias) → volume + valor por modalidade
  ├── section_municipios(conn, uf, dias, limit=20) → top municípios
  ├── section_sazonalidade(conn, uf, dias) → heatmap mensal
  ├── section_concorrencia(conn, uf, dias) → top fornecedores
  ├── section_setores(conn, uf, dias) → breakdown por setor
  └── Output:
      ├── Terminal: Rich table (ASCII)
      ├── Excel: openpyxl (estilizado, múltiplas abas)
      └── PDF: ReportLab (opcional, --output-pdf)
```

## Coverage Reports

```
coverage_gaps.py → Query uncovered entities → Agrupar por município/natureza → CSV
coverage_weekly.py → Query 7-day window → Comparar semana anterior → PDF
```

## Padrão de Query

Todas as queries usam parâmetros `%s` do psycopg2 (sem string interpolation). Conexão obtida via `psycopg2.connect(DSN)` com DSN do ambiente.

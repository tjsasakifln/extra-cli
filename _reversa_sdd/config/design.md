# Design — Módulo `config`

> 🟢 CONFIRMADO

## Estrutura

```
config/
├── settings.py          # Env vars → Python constants (12-factor)
├── sectors_config.yaml  # 13 setores (2.116 linhas) — fonte única de verdade
├── sectors_data.yaml    # Dados complementares de setores
├── abbreviations.yaml   # Abreviações PT-BR (extensível)
└── transparencia_config.yaml  # Portais de transparência (Betha/Ipam/E-gov)
```

## Settings (12-factor)

Toda config vem de `os.getenv()` com defaults. Sem hardcoded credentials. Categorias:
- **Paths:** PROJECT_ROOT, SCRIPTS_DIR, DATA_DIR, OUTPUT_DIR, PDF_DIR, EXCEL_DIR, LOG_DIR
- **Database:** LOCAL_DATALAKE_DSN, DATALAKE_BACKEND
- **OpenAI:** API_KEY, MODEL (gpt-4.1-nano), TIMEOUT_S (10), MAX_CONCURRENT (5)
- **APIs:** PNCP_BASE, DOM_SC_BASE, PCP_BASE, COMPRAS_GOV_BASE
- **Ingestion:** UFS, MODALIDADES, DATE_RANGE_DAYS, PAGE_SIZE, MAX_PAGES, BATCH_DELAY_S
- **Coverage:** TARGET_PCT (100.0), WINDOW_DAYS (90)
- **Enrichment:** TTL_DAYS (30)

## Sectors Config (YAML Schema)

```yaml
sectors:
  <setor>:
    cnae_prefixes: [list]
    sector_hints: [list]
    heuristic_patterns:
      strong_compat: [regex list]
      strong_incompat: [regex list]
      weak_compat: [regex list]
    cross_sector_exclusions: [list]
    competition_keywords: [list]
    weight_profile: {hab, fin, geo, prazo, comp}
    base_win_rate: float
    habilitacao: {capital_minimo_pct, atestados, certifications, fiscal}
    timeline_rules: [{max_value, min_days}]
    priority_modalidades: [list]
    cnae_gate_threshold: float
```

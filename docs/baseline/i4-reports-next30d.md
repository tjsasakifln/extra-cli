# I4 — Relatórios comerciais next-30d (PDF × Excel × ranking)

**Date:** 2026-07-16  
**Branch:** `epic/next-30d-multiagent-execution`  
**DSN:** `postgresql://test:test@127.0.0.1:5433/pncp_datalake`  
**Scope:** reconciliação PDF/Excel, ranking de órgãos com semântica explícita, baseline honesta

---

## 1. Objetivo

Garantir que artefatos comerciais (PDF executivo, Excel executivo, ranking de órgãos) sejam:

1. **Reconciliáveis** — mesmos filtros (cutoff, UF, profile version) quando o par existe  
2. **Semanticamente honestos** — CONTRATADO vs ESTIMADO rotulados, sem inventar contratos  
3. **Reprodutíveis** via CLI com DSN local de teste

---

## 2. Artefatos e scripts

| Script | Saída padrão | Papel |
|--------|--------------|-------|
| `scripts/reports/run_metadata.py` | `*.meta.json` sidecar | Schema compartilhado de run (filters, cutoff, sample_size, profile) |
| `scripts/reports/executive_report.py` | `output/reports/executivo-extra-YYYY-MM-DD.pdf` | PDF institucional |
| `scripts/reports/executive_excel.py` | `output/reports/executivo-extra-YYYY-MM-DD.xlsx` | Excel multi-sheet + Metadados |
| `scripts/reports/reconcile_pdf_excel.py` | `output/reports/reconcile-next30d.json` | Reconciliação de filtros PDF × Excel |
| `scripts/reports/org_ranking.py` | `output/reports/org-ranking-next30d.{json,csv}` | Ranking de órgãos por contagem/valor |

**Não alterados (fora de escopo deste baseline):** `scripts/golden_path.py`, `scripts/crawl/contracts_crawler.py`.

---

## 3. Reconciliação PDF × Excel

### Discovery

| Artefato | Path de discovery (default) |
|----------|-----------------------------|
| Excel | `output/excels/` (mais recente `*.xlsx`); fallback `output/reports/` |
| PDF | `output/` recursivo; preferência `output/reports/*.pdf` |
| Paths explícitos | `--pdf` / `--excel` |

### Campos críticos comparados

| Campo | Fonte metadata | Severidade |
|-------|----------------|------------|
| `cutoff.as_of_date` | sidecar / Metadados | crítica |
| `cutoff.data_window` | sidecar / Metadados | crítica |
| `filters.uf` | sidecar / Metadados | crítica |
| `filters.is_active` | sidecar / Metadados | crítica |
| `filters.table_primary` | sidecar / Metadados | crítica |
| `filters.vincendos_horizon_days` | sidecar / Metadados | crítica |
| `profile_version` | sidecar | crítica (se ambos presentes) |
| `profile_id` / `run_id` / `git_sha` | sidecar | soft |

### Exit codes

| Code | Condição |
|------|----------|
| **0** | Filtros consistentes **ou** ambos ausentes (com note) **ou** par incompleto / metadata ausente (com note) |
| **1** | Filtros conflitantes (critical mismatch) |
| **2** | Erro de I/O ou uso |

### Comando

```bash
python scripts/reports/reconcile_pdf_excel.py \
  -o output/reports/reconcile-next30d.json

# ou paths explícitos:
python scripts/reports/reconcile_pdf_excel.py \
  --pdf output/reports/executivo-extra-2026-07-16.pdf \
  --excel output/reports/executivo-extra-2026-07-16.xlsx
```

---

## 4. Ranking de órgãos (`org_ranking.py`)

### Prioridade de fonte

```
1. pncp_supplier_contracts  → valor_semantica = CONTRATADO (valor_total)
2. opportunity_intel        → valor_semantica = ESTIMADO   (valor_estimado)
3. pncp_raw_bids            → valor_semantica = ESTIMADO   (valor_total_estimado)
```

Fallback só ocorre se a tabela preferida estiver **vazia** (0 linhas ativas no filtro).  
Nunca se rotula ESTIMADO como CONTRATADO.

### Comando

```bash
LOCAL_DATALAKE_DSN=postgresql://test:test@127.0.0.1:5433/pncp_datalake \
  python scripts/reports/org_ranking.py --uf SC --limit 50
```

Saídas:

- `output/reports/org-ranking-next30d.json`
- `output/reports/org-ranking-next30d.csv`

### Baseline local (2026-07-16, DSN teste)

| Tabela | Linhas ativas (aprox.) | Uso no ranking |
|--------|------------------------:|----------------|
| `pncp_supplier_contracts` | **0** | preferida, vazia → fallback |
| `opportunity_intel` | **10** | fallback ESTIMADO se tiver órgão |
| `pncp_raw_bids` | **~2948** | fallback ESTIMADO se OI vazio/sem órgão |

**Implicação:** ranking next-30d no DSN de teste **não** afirma mercado contratado SC; status esperado `ESTIMADO` via OI ou raw_bids, sample potencialmente `MINIMAL`/`INSUFFICIENT` para claims comerciais amplos.

---

## 5. Claims permitidos / proibidos

### Permitidos

- Contagens derivadas de `opportunity_intel.is_active=true` no DSN local  
- Ranking de órgãos com `valor_semantica` explícita  
- Reconciliação PASS/CONSISTENT apenas quando filtros críticos batem  
- Sample labels INSUFFICIENT / MINIMAL / ADEQUATE  

### Proibidos

- Cobertura 95% ou readiness comercial sem evidence ledger  
- Misturar PDF e Excel de runs com filtros conflitantes sem reportar CONFLICT  
- Tratar ESTIMADO como CONTRATADO  
- Inferir contratos vincendos a partir de `pncp_raw_bids`  
- Publicar ranking como “mercado completo SC” com N pequeno  

---

## 6. Dependências de metadata

Geradores PDF/Excel devem gravar sidecar `<artifact>.meta.json` via `scripts/reports/run_metadata.py` (`build_run_metadata` + `write_sidecar`) e, no Excel, linhas de Metadados alinhadas.

Sem sidecar:

- Reconcile **não** falha com exit 1 (não há prova de conflito)  
- Emite `METADATA_ABSENT` / `METADATA_PARTIAL` com note — regenerar com `--run-id` compartilhado  

Fluxo recomendado de par:

```bash
RUN_ID="exec-$(date -u +%Y%m%d-%H%M%S)-manual"
LOCAL_DATALAKE_DSN=postgresql://test:test@127.0.0.1:5433/pncp_datalake \
  python scripts/reports/executive_report.py --run-id "$RUN_ID"
LOCAL_DATALAKE_DSN=postgresql://test:test@127.0.0.1:5433/pncp_datalake \
  python scripts/reports/executive_excel.py --run-id "$RUN_ID"
python scripts/reports/reconcile_pdf_excel.py \
  --pdf output/reports/executivo-extra-$(date -u +%Y-%m-%d).pdf \
  --excel output/reports/executivo-extra-$(date -u +%Y-%m-%d).xlsx
```

---

## 7. Verificação rápida

```bash
# Reconcile (default paths + output)
python scripts/reports/reconcile_pdf_excel.py
# → output/reports/reconcile-next30d.json ; echo $?

# Ranking
LOCAL_DATALAKE_DSN=postgresql://test:test@127.0.0.1:5433/pncp_datalake \
  python scripts/reports/org_ranking.py --uf SC
# → org-ranking-next30d.json + .csv

# Inspecionar semântica
python -c "import json; d=json.load(open('output/reports/org-ranking-next30d.json')); print(d['ranking']['source_table'], d['ranking']['valor_semantica'], d['ranking']['count'])"
```

---

## 8. Limitações honestas (next-30d)

1. **Contratos = 0** no DSN de teste → ranking CONTRATADO indisponível até backfill K3 / contracts pilot.  
2. Artefatos legados em `output/reports/executivo-extra-2026-07-16.*` podem **não** ter sidecar `.meta.json` → reconcile retorna note, não CONFLICT.  
3. Excel em `output/excels/` hoje é `panorama-SC-*.xlsx` (não executivo) — discovery default pode parear panorama × PDF executivo; use `--pdf`/`--excel` para par canônico.  
4. Profile version (`config/client_profiles/extra.yaml` → `version: 2`) só entra no reconcile se os geradores a gravam no sidecar (`profile_version`).  

---

## 9. Referências

- Perfil Extra: `docs/baseline/i4.1-extra-operational-profile.md`, `config/client_profiles/extra.yaml`  
- Semântica de valor: `docs/baseline/k3-contract-schema-semantics.md`  
- Schema audit: `docs/baseline/l1-schema-audit-next30d.md`  
- Shared metadata: `scripts/reports/run_metadata.py`  

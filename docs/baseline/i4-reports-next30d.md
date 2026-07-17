# I4 — Relatórios comerciais next-30d (PDF × Excel × ranking)

**Date:** 2026-07-17  
**Branch:** `epic/next-30d-multiagent-execution`  
**DSN:** `postgresql://test:test@127.0.0.1:5433/pncp_datalake`  
**Scope:** reconciliação PDF/Excel com `run_id` compartilhado, ranking de órgãos, stubs GO/REVIEW/NO_GO, baseline honesta  
**Commit base reports:** `c4e4561` (+ follow-up pairing executive generators)

---

## 1. Objetivo

Garantir que artefatos comerciais (PDF executivo, Excel executivo, ranking de órgãos, stubs A/E) sejam:

1. **Reconciliáveis** — mesmo `run_id` / cutoff / UF / profile quando o par existe  
2. **Semanticamente honestos** — CONTRATADO vs ESTIMADO rotulados; sample size rotulado  
3. **Reprodutíveis** via CLI com DSN local de teste  

---

## 2. Artefatos e scripts

| Script | Saída padrão | Papel |
|--------|--------------|-------|
| `scripts/reports/run_metadata.py` | `*.meta.json` sidecar | Schema compartilhado (filters, cutoff, sample_size, profile, run_id) |
| `scripts/reports/executive_report.py` | `output/reports/executivo-extra-YYYY-MM-DD.pdf` | PDF institucional + sidecar |
| `scripts/reports/executive_excel.py` | `output/reports/executivo-extra-YYYY-MM-DD.xlsx` | Excel multi-sheet + Metadados + sidecar |
| `scripts/reports/reconcile_pdf_excel.py` | `output/reports/reconcile-pdf-excel-YYYY-MM-DD.json` (ou `reconcile-next30d.json`) | Reconciliação PDF × Excel |
| `scripts/reports/org_ranking.py` | `output/reports/org-ranking-next30d.{json,csv}` | Deliverable A — ranking órgãos |
| `scripts/reports/deliverable_orgaos_ranking.py` | `output/reports/deliverable-a-e-YYYY-MM-DD.{json,xlsx}` | Deliverable A+E (+ status C) |
| `scripts/reports/panorama.py` | `output/excels/panorama-UF-date.xlsx` | Panorama (não é o par executivo) |

**Não alterados (proibido neste trabalho):** `scripts/golden_path.py`, `scripts/crawl/contracts_crawler.py`, `scripts/crawl/sc_compras_crawler.py`, `DOD.md`.

---

## 3. Reconciliação PDF × Excel

### Discovery

| Artefato | Path de discovery (default) |
|----------|-----------------------------|
| Excel | `output/excels/` (mais recente `*.xlsx`); fallback `output/reports/` |
| PDF | `output/reports/*.pdf` preferido; fallback `output/` recursivo |
| Paths explícitos | `--pdf` / `--excel` + `--no-discover` |

### Campos comparados

| Campo | Severidade |
|-------|------------|
| `cutoff.as_of_date`, `cutoff.data_window` | crítica |
| `filters.uf`, `filters.is_active`, `filters.table_primary`, `filters.vincendos_horizon_days` | crítica |
| `profile_version` | crítica (se ambos presentes) |
| `run_id` | **crítica se ambos os lados declaram run_id** (par gerado com `--run-id`) |
| `profile_id`, `git_sha` | soft |

### Exit codes

| Code | Condição |
|------|----------|
| **0** | `CONSISTENT` / `CONSISTENT_SOFT` / par incompleto / metadata ausente (com note) / ambos ausentes |
| **1** | `CONFLICT` — filtros ou run_id críticos divergentes |
| **2** | Erro de I/O |

### Comando (par canônico)

```bash
export PYTHONPATH=. LOCAL_DATALAKE_DSN=postgresql://test:test@127.0.0.1:5433/pncp_datalake
RUN_ID=$(python3 -c "from scripts.reports.run_metadata import new_run_id; print(new_run_id())")
TODAY=$(date -u +%Y-%m-%d)
python scripts/reports/executive_excel.py --run-id "$RUN_ID" --uf SC \
  -o "output/reports/executivo-extra-${TODAY}.xlsx"
python scripts/reports/executive_report.py --run-id "$RUN_ID" --uf SC \
  -o "output/reports/executivo-extra-${TODAY}.pdf"
python scripts/reports/reconcile_pdf_excel.py --no-discover \
  --pdf "output/reports/executivo-extra-${TODAY}.pdf" \
  --excel "output/reports/executivo-extra-${TODAY}.xlsx" \
  -o "output/reports/reconcile-pdf-excel-${TODAY}.json"
echo "exit=$?"
```

### Resultado real (2026-07-17)

| Campo | Valor |
|-------|-------|
| Run ID | `exec-20260717-001325-8078611a` |
| Verdict | **CONSISTENT** |
| Exit code | **0** |
| PDF | `output/reports/executivo-extra-2026-07-17.pdf` (+ `.meta.json`) |
| Excel | `output/reports/executivo-extra-2026-07-17.xlsx` (+ `.meta.json`) |
| Report | `output/reports/reconcile-pdf-excel-2026-07-17.json` |
| Sample label | **MINIMAL** (`opportunity_intel` = 10, todos REVIEW) |

---

## 4. Deliverables A / C / E (dados reais)

### A — Ranking de órgãos

```bash
LOCAL_DATALAKE_DSN=postgresql://test:test@127.0.0.1:5433/pncp_datalake \
  python scripts/reports/org_ranking.py --uf SC --limit 50
```

| Campo | Valor (2026-07-17) |
|-------|---------------------|
| Status | OK |
| Source | `pncp_supplier_contracts` |
| `valor_semantica` | **CONTRATADO** |
| Órgãos no top | 50 |
| Contratos ativos (tabela) | ~1550 |

### C — Contratos vincendos (180d)

| Campo | Valor (2026-07-17) |
|-------|---------------------|
| Status | OK (via `deliverable_orgaos_ranking.py`) |
| Count horizonte 180d | **76** (amostra 10 no JSON A/E) |
| Claim | Somente a partir de `pncp_supplier_contracts` — **não** derivar de `pncp_raw_bids` |

### E — Stubs GO / REVIEW / NO_GO

```bash
python scripts/reports/deliverable_orgaos_ranking.py --uf SC
```

| Ranking | Count |
|---------|------:|
| GO | 0 |
| REVIEW | 10 |
| NO_GO | 0 |

**Honestidade:** 100% REVIEW em fixtures/OI local — **não** relabelar como GO sem reexecutar motor de ranking.

---

## 5. Métricas DB no momento da evidência

| Métrica | Valor |
|---------|------:|
| `opportunity_intel` active | 10 |
| ranking_dist | REVIEW=10 |
| `pncp_raw_bids` SC active | ~2948 |
| `pncp_supplier_contracts` active | ~1550 |
| vincendos 180d | 76 |
| Sample label (executivo) | MINIMAL |

> Contagens flutuam conforme crawls paralelos na mesma branch. Sempre re-rodar os CLIs acima e copiar o JSON de saída.

---

## 6. Claims permitidos / proibidos

### Permitidos

- Contagens derivadas de `opportunity_intel.is_active=true` no DSN local  
- Ranking de órgãos com `valor_semantica` = CONTRATADO ou ESTIMADO explícita  
- Reconciliação CONSISTENT apenas quando filtros críticos (e run_id se ambos declaram) batem  
- Sample labels **INSUFFICIENT** / **MINIMAL** / **ADEQUATE**  
- Contratos vincendos com count real de `pncp_supplier_contracts`  

### Proibidos

- Cobertura 95% ou readiness comercial sem evidence ledger  
- Misturar PDF e Excel de runs com filtros/run_id conflitantes sem reportar CONFLICT  
- Tratar ESTIMADO como CONTRATADO  
- Inferir contratos vincendos a partir de `pncp_raw_bids`  
- Publicar ranking como “mercado completo SC” com N de editais OI &lt; 20  
- Tratar REVIEW como GO  

---

## 7. Fluxo de metadata (geradores)

1. `build_run_metadata(run_id=..., uf=..., stats=...)`  
2. Excel grava linhas Metadados (`Run ID`, `Filter UF`, `Cutoff as_of_date`, sample_*)  
3. PDF imprime bloco “Identidade do Run” na metodologia  
4. Ambos gravam `<artifact>.meta.json` via `write_sidecar`  
5. `reconcile_pdf_excel.py` lê sidecars (fallback: sheet Metadados no Excel)

Sem sidecar em ambos:

- Reconcile **não** força exit 1  
- Emite `METADATA_ABSENT` / `METADATA_PARTIAL` com note  

---

## 8. Limitações honestas (next-30d)

1. **OI = 10 / 100% REVIEW** → sample **MINIMAL**; não usar para ranking comercial de GO.  
2. Artefatos legados `executivo-extra-2026-07-16.*` **sem** sidecar → reconcile retorna note, não CONFLICT.  
3. Discovery default pode parear `output/excels/panorama-*.xlsx` × PDF executivo — use `--no-discover` + paths explícitos para o par canônico.  
4. Profile version (`extra.yaml` → `version: 2`) entra no sidecar quando PyYAML/parse disponível.  
5. Contagens de contratos/bids mudam com crawls paralelos — baseline é snapshot, não KPI de produção.

---

## 9. Referências

- Perfil Extra: `docs/baseline/i4.1-extra-operational-profile.md`, `config/client_profiles/extra.yaml`  
- Semântica de valor: `docs/baseline/k3-contract-schema-semantics.md`  
- Shared metadata: `scripts/reports/run_metadata.py`  
- Commit inicial I4 scripts: `c4e4561`  

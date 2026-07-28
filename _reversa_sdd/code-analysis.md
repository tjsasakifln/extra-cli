# Análise de Código — Extra Consultoria

> 🟢 **CONFIRMADO** — re-extração Archaeologist **2026-07-28**  
> HEAD `ffbb9608` | `doc_level`: **completo** | **38 módulos**  
> Delta vs 2026-07-17 (`d3e82ba`): +13 módulos, ops/CONFENGE/CMI, ORPT reports, dual coverage, commercial leads, budget audit, national intel, linkage, mig 055–064

---

## 1. Arquitetura lógica (as-is)

```
┌──────────────────────────────────────────────────────────────────┐
│  ops/*  — gates fail-closed, CONFENGE, CMI proofs, weekly_cycle  │
│  tools/dod_controller.py — harness DoD                           │
│  CI: ci.yml + pr-reviewability (sem || true em integridade)      │
└────────────────────────────┬─────────────────────────────────────┘
                             │
     ┌───────────────────────┼────────────────────────┐
     ▼                       ▼                        ▼
┌──────────┐         ┌──────────────┐         ┌─────────────────┐
│ crawl/*  │ registry│ source_      │         │ coverage/*      │
│ + DLQ    │◄───────►│ registry     │────────►│ dual_capability │
│ monitor  │ 11+     │ ESR gaps     │         │ contract/recall │
└────┬─────┘ fontes  └──────┬───────┘         └────────┬────────┘
     │ upsert/acts          │                          │
     ▼                      ▼                          ▼
┌──────────┐         ┌──────────────┐         ┌─────────────────┐
│ matching │ cascade │ linkage/*    │ golden  │ commercial_     │
│ official │ 3 níveis│ resolve/keys │ records │ leads + CMI     │
│ _acts    │         │ dossier      │         │ national_intel  │
└────┬─────┘         └──────┬───────┘         └────────┬────────┘
     │                      │                          │
     ▼                      ▼                          ▼
┌──────────┐         ┌──────────────┐         ┌─────────────────┐
│ opport.  │ radar   │ workspace/*  │ fila    │ reports/* ORPT  │
│ intel    │         │ today/queue  │ diária  │ PDF/Excel/CSV   │
└────┬─────┘         └──────────────┘         │ editais/valores │
     │                                        │ concorrentes    │
     └────────────────────────────────────────┴─────────────────┘
                    PostgreSQL 16 + PostGIS (system of record)
                    Evidence JSON/JSONL for campaigns (not git bulk)
```

**Padrão dominante:** CLI-first, Postgres como SoR, evidência de campanha em artefatos versionados por SHA, gates fail-closed, claims honestos (NOT_COMPUTABLE > inventar).

---

## 2. Módulo `ops` (~39K LOC, 92 .py) 🟢 — PRIORIDADE AUDITORIA

### 2.1 Propósito
Operação, gates de campanha, ciclo semanal, resiliência local, higiene de PR/artefatos, CONFENGE commercial-ready, CMI proofs.

### 2.2 Clusters funcionais

| Cluster | Arquivos-chave | LOC approx | Papel |
|---------|----------------|----------:|-------|
| **Weekly** | `weekly_cycle.py` | 1954 | Ciclo operacional canônico multi-stage |
| **CONFENGE status** | `confenge_final_status.py` | 2124 | SSoT de status terminal da campanha |
| **CONFENGE gates** | `confenge_commercial_gates.py`, `confenge_make_gates.py` | 600–1500 | campaign / RC / DoD audit fail-closed |
| **CONFENGE freeze** | `confenge_code_freeze.py`, `confenge_frozen_inputs.py` | 559–761 | Freeze de inputs imutáveis + SHA |
| **CONFENGE cycle** | `confenge_commercial_cycle.py`, `*_e2e.py`, `*_snapshot.py` | 155–450 | Pipeline comercial E2E |
| **CMI** | `cmi_item_proofs.py`, `cmi_promote_evidence.py` | 113–581 | Proofs por item DoD §10/§11 |
| **Client-ready** | `client_ready_consulting_cycle.py` | 1961 | Ciclo integrado consultoria recorrente |
| **Resilience** | `resilient_cycle.py`, `health.py` | 281–366 | Ciclo local pre-VPS + health honesto |
| **PR policy** | `check_generated_artifacts_policy.py`, `check_pr_reviewability.py` | 315–503 | Gates de reviewability |
| **Campaign gates** | `campaign_*_gate.py`, soak, verify | 100–340 | open tenders, stratified recall, linkage |
| **Migrations** | `apply_migrations.py` | 357 | Apply seguro + ledger de checksums |

### 2.3 Algoritmos / regras 🟢

1. **Fail-closed gates:** ausência de evidência, SHA dummy, inventário desalinhado → FAIL (não skip).
2. **Dual-head CONFENGE:** distingue `pr_head` vs `workflow_merge_sha` (CI env).
3. **Health honesto:** fixtures nunca “greenwash” live (`health.py`).
4. **Weekly stages:** validate config/DB → freshness → collect → match → reports (StageResult).
5. **Artifact policy:** proíbe PDF/XLSX/bulk dumps no git (com exceptions YAML).
6. **PR reviewability:** ≤60 files / ≤10k lines / single capability; HEAD SHA deve bater.

### 2.4 Dependências
Postgres DSN, git, filesystem de packages de campanha, módulos `coverage`, `commercial_leads`, `linkage`, `reports`.

---

## 3. Módulo `coverage` (~18K LOC, 26 .py) 🟢

### 3.1 Propósito
Contrato multi-métrica de cobertura, dual capability (`open_tenders` | `historical_contracts`), recall de relevância de editais, status comercial, pipeline de sessão 200 km.

### 3.2 Componentes-chave

| Arquivo | LOC | Papel |
|---------|----:|-------|
| `dual_capability_coverage.py` | 2738 | Autoridade canônica dual capability + universe identity |
| `coverage_contract.py` | 1820 | Métricas não-conflacionadas + SLA |
| `multi_source_coverage.py` | 1665 | Métricas multi-fonte baseadas em artefatos |
| `edital_relevance_recall.py` | 1505 | Recall §8.4 fail-closed + Wilson CI |
| `session_coverage_pipeline.py` | 1333 | acts → resolve → classify → recalc |
| `source_policy.py` | 772 | Política canônica de aplicabilidade por fonte |
| `recall_benchmark.py` | 738 | Benchmark estratificado com freeze de denominador |
| `commercial_status.py` | 387 | Classificador comercial determinístico |
| `states.py` | 379 | Máquina de 9 estados de coverage |

### 3.3 Algoritmo — Coverage states 🟢

9 estados: `not_applicable` (terminal), `pending`, `running`, `success_with_data`, `success_zero` (paginação completa), `partial`, `error`, `blocked`, `stale`.

**Covered** = `{success_with_data, success_zero}` apenas.  
**Regra:** presença de dados ≠ coverage; métricas independentes.

### 3.4 Algoritmo — Dual capability 🟢

- Capabilities: `open_tenders`, `historical_contracts`
- View auxiliar: `v_dual_capability_evidence_latest` (mig 058)
- `entity_coverage` é **legado/diagnóstico** — não autoridade dual (ADR-029 comentado no SQL)
- Universe identity com SHA de IDs ordenados + schema/universe stamps

### 3.5 Algoritmo — Edital relevance recall 🟢

- Corpus + labels humanos dual-blind
- `predicted_relevant` vs ground truth → confusion + Wilson CI
- Bloqueia se machine authority / synthetic records indevidos
- Campaign helpers em `scripts/campaigns/edital_relevance/`

---

## 4. Módulo `reports` (~11K LOC, 20 .py) 🟢 — ORPT

### 4.1 Propósito
Vertical de relatórios: listas operacionais, relatórios analíticos, PDF/Excel executivos, metadata unificada, export pack.

### 4.2 ORPT (PRs #159–#160)

| Camada | Arquivos | Papel |
|--------|----------|-------|
| Listas §12.2 | `operational_outputs.py` | 8 tipos de lista fail-closed |
| Relatórios §12.2 | `operational_reports.py` | contratos, concorrentes, concentração, recall… |
| Metadata | `run_metadata.py` | `run_id`, git SHA, sample size, sidecars |
| Domínio §12.1 | `editais_report`, `contratos_report`, `valores_report`, `concorrentes_report` | Golden path domain-specific |
| Executivo | `executive_report.py`, `executive_excel.py` | PDF ReportLab + openpyxl |
| Pack | `operational_export_pack.py` | CSV/Excel/PDF + source health |

### 4.3 Regras 🟢

- Queries fail-closed: tabela ausente → erro tipado (`OperationalQueryError`), não lista vazia silenciosa.
- Metadata validada e comparável entre PDF/Excel (`compare_metadata`).
- Dataset/schema hashes para rastreio.

---

## 5. Módulo `commercial_leads` (~8K LOC, 19 .py) ✨ NOVO 🟢

### 5.1 Propósito
Fila comercial de leads (fornecedores) com scoring explicável, estados comerciais, overrides humanos, supplier registry.

### 5.2 Pipeline

```
profile + snapshot → signals → scoring → rank → persist (ledger) → review/export
```

### 5.3 Algoritmo de scoring 🟢

- `LeadScore` com decomposição, signals fired/NC, offer scores multi-bucket
- Buckets: diagnóstico B2G, licitações/propostas, auditoria orçamento, acompanhamento, gestão documental, inteligência PNCP
- `SELECTION_RULE_VERSION = offer-selection-v4-multi-bucket`
- Soft mapping boost (0.15 base + 0.05/signal) — evita flip por single-signal
- Gate: `MIN_SELECTED_OFFER_MARGIN = 0.10`, `MAX_SINGLE_SIGNAL_OFFER_CHANGE_RATE = 0.50`
- **Non-claim:** score é prioridade de revisão humana, **não** probabilidade de conversão

### 5.4 Persistência (mig 062–063)

- `commercial_lead_runs`, `commercial_leads`, overrides, feedback ledger
- `supplier_registry` (CNAE canônico; missing = NOT_COMPUTABLE)

### 5.5 Estados comerciais 🟢

`NEW → REVIEWED → QUALIFIED|DISQUALIFIED → CONTACTED → … → WON|LOST|DO_NOT_CONTACT`

---

## 6. Módulo `budget_audit` (~5.4K LOC, 26 .py) ✨ NOVO 🟢

### 6.1 Propósito
Auditoria aritmética de planilhas orçamentárias (BDI, composições, materialidade) — **sem claim legal/abusivo**.

### 6.2 Componentes

| Arquivo | Papel |
|---------|-------|
| `pipeline.py` | Orquestra ingest → normalize → arithmetic → BDI → findings |
| `bdi.py` | Soma de componentes; interpreta % BR com cuidado Excel |
| `arithmetic.py` | Checks aritméticos de itens |
| `materiality.py` | Política de materialidade de diferenças |
| `gate.py` / `gate_main.py` | Gates de campanha fail-closed |
| `workbook_reader.py` + `zip_safety.py` | Leitura segura de XLSX |
| `export_safety.py` | Export sem vazar paths/secrets |

### 6.3 Algoritmo BDI 🟢

- `_as_fraction`: distingue Excel percent format vs percent points BR
- Componentes: quase sempre percent points (3 = 3%)
- Nunca trata BDI como margem; nunca classifica legal/ilegal sem revisão normativa humana

---

## 7. Módulo `edital_case` (~4.9K LOC, 14 .py) ✨ NOVO 🟢

Pipeline: `acquire → extract → classify → analyze → verify → report` com `gate` (isolation/campaign/RC).  
Modelos e store isolados; classificação de documentos com flags de review.

---

## 8. Módulo `national_intel` (~0.6K LOC, 9 .py) ✨ NOVO 🟢

Produto analítico **nacional** (não coverage operacional SC):

| Comando | Função |
|---------|--------|
| competitors | Footprint geográfico de fornecedores (views L3) |
| agencies | Perfil de órgãos contratantes (single-query) |
| benchmarks | Benchmarks de valor com gate de sample-size |

Views (mig 060): `v_intel_contracts_raw_national`, `v_intel_contracts_geo_sc`, `v_intel_supplier_geo`, `v_intel_agency_profile`.  
**Claim class:** multi-UF é fato de contratos, não “parceria”.

---

## 9. Módulo `linkage` (~1.9K LOC, 8 .py) ✨ NOVO 🟢

### 9.1 Propósito
Golden records + links auditáveis opportunity↔organ↔contract↔supplier (mig 061).

### 9.2 Algoritmo de decisão 🟢

Classificações: `exact | deterministic_composite | heuristic_reviewable | ambiguous | unresolved`  
Auto-accept: exact/deterministic + score ≥ 0.99  
Conflito de strong IDs (CNPJ14/CNPJ8/IBGE) → **refuse merge** (ambiguous)  
`claim_level`: fact | similarity | inference | none  
Dossier JSON+HTML consultivo.

---

## 10. Módulo `crawl` (~43K LOC, 108 .py) 🟢

### 10.1 Propósito
Coleta multi-fonte; `registry.py` = SSoT de fontes; `monitor.py` orquestra (orchestrator DEPRECATED).

### 10.2 Algoritmos

- **Registry:** `SourceInfo` + capabilities, authority, SLA, zero-proof, reconciliation strategy
- **Resilience/DLQ:** `DurableDLQ` + backoff; watermarks (mig 046–048 lineage)
- **Monitor:** date window → crawl_source → transform → upsert → coverage report
- Fontes: PNCP, CIGA CKAN/DOM, SC Compras, DOE, DOM, transparência, compras.gov, PCP, MIDES, selenium paths

---

## 11. Módulo `contract_intel` (~1.7K LOC) 🟢

CLI de verdade de contratos no DataLake: histórico, fornecedores, ativos, manifesto, stats.  
`target_universe` 200 km de Florianópolis (determinístico).  
CMI (competitors/values/concentration) vive em ops proofs + reports domain + DoD ACCEPTED — vertical estendida desde 07-17.

---

## 12. Módulo `source_registry` (~3K LOC) 🟢

Build ESR a partir do CSV universo + YAML applicability; discovery semi-automática; gap report nominal; sync Postgres (mig 053).  
Status operacional estrito via `is_strict_operational`.

---

## 13. Módulo `workspace` (~3K LOC) 🟢

Facade CLI do consultor: `today`, opportunities, dossier, coverage, entity, competitors, contracts, decide, report.  
`queue.py` monta fila diária multi-seção; `actions.py` side-effects (decide, scaffold edital/proposal).

---

## 14. Módulo `matching` (~2.7K LOC) 🟢

Cascade 3 níveis de entity match + `official_acts_reconcile` determinístico DOE/DOM × Compras SC × PNCP.

---

## 15. Módulo `lib` (~5.2K LOC) 🟢

| Peça | Papel |
|------|-------|
| `universe.py` | CanonicalUniverse + reconcile active IDs |
| `value_semantics.py` | Tipos de valor B2G + deságio |
| `geocode.py` | Haversine / coords SC |
| `name_normalizer.py` | Normalização de nomes de entes |

---

## 16. Módulo `schema` (~1.8K LOC) 🟢

`OfficialActsStore`, diagnostics live vs baseline, audit de SQL embutido em Python.

---

## 17. Módulo `campaigns` ✨ NOVO 🟢

`edital_relevance`: build corpus + human dual-label (blind packages/import).

---

## 18. Módulos satélite 🟢/🟡

| Módulo | Papel | Conf. |
|--------|-------|-------|
| `fix` | Repair residual, evidence, geocode | 🟢 |
| `pipeline` | Backfill multi-fonte | 🟢 |
| `clients` / `ingestion` | HTTP + ingest helpers | 🟢 |
| `buyer_intel` | Ranking compradores | 🟢 |
| `extra_ledger` | Ledger operacional | 🟢 |
| `transparencia` / `diagnose` | Portais / DOM-SC | 🟢 |
| `integrations` / `collect` / `quality` | Auxiliares | 🟡 superfície |
| `ocds_bridge` / `entity_identity` / `data_contracts` | Ponte/identidade/contratos | 🟡 superfície |
| `root_scripts` | ~50 CLIs top-level | 🟡 (alto volume) |
| `config` | settings, sectors, profiles | 🟢 |
| `db` | 69 migrations | 🟢 |
| `deploy` | 26 services / 25 timers | 🟢 |
| `tests` | ~250 arquivos | 🟢 |
| `docs` | ~529 MD | 🟡 inventário |
| `tools` | `dod_controller.py` | 🟢 |

---

## 19. Algoritmos transversais (top 15) 🟢

| # | Algoritmo | Módulo |
|---|-----------|--------|
| 1 | Dual capability coverage | coverage |
| 2 | Coverage state machine (9 estados) | coverage |
| 3 | Coverage contract multi-metric | coverage |
| 4 | Edital relevance recall + Wilson CI | coverage |
| 5 | Source policy applicability | coverage |
| 6 | Commercial lead scoring multi-bucket | commercial_leads |
| 7 | BDI arithmetic (percent points BR) | budget_audit |
| 8 | Linkage strong-key refuse-merge | linkage |
| 9 | Entity match cascade 3 níveis | matching |
| 10 | Official acts reconcile | matching |
| 11 | Source registry build/discover | source_registry |
| 12 | Weekly cycle multi-stage | ops |
| 13 | CONFENGE final status aggregation | ops |
| 14 | Operational reports fail-closed | reports |
| 15 | National intel layered views | national_intel / db |

---

## 20. Cross-cutting concerns

| Concern | Implementação |
|---------|---------------|
| Fail-closed | Gates ops/CI/coverage; sem greenwash |
| Honest claims | language_note em scores; NOT_COMPUTABLE |
| Isolation DSN | linkage, commercial_leads, national_intel, edital_case |
| Evidence ledger | coverage_evidence + campaign packages |
| Snapshot guard | mig 064 opt-in trigger em pncp_supplier_contracts |
| Migrations ledger | apply_migrations checksum |
| Logging | JsonLogger / structured where present |

---

## 21. Lacunas de escavação 🔴/🟡

| ID | Item | Conf. |
|----|------|-------|
| CA-01 | Todos os 90+ arquivos de ops não lidos linha a linha — clusters amostrados | 🟡 |
| CA-02 | Internals de cada crawler individual (só registry+monitor) | 🟡 |
| CA-03 | Runtime VPS / dumps live não inspecionados | 🔴 |
| CA-04 | Satélites ocds/quality/data_contracts só superfície | 🟡 |

---

*Archaeologist Reversa — 2026-07-28 | HEAD `ffbb9608`*

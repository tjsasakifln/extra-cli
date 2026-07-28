# Dicionário de Dados — Extra Consultoria

> 🟢 **CONFIRMADO** (schema via migrations + dataclasses) | 🟡 inferido de uso  
> Re-extração 2026-07-28 | HEAD `ffbb9608`  
> Foco: entidades novas/alteradas desde 2026-07-17 (mig 055–064) + entidades canônicas de auditoria

---

## 1. Convenções

| Marca | Significado |
|-------|-------------|
| 🟢 | Extraído de migration/SQL ou dataclass |
| 🟡 | Inferido do código de leitura/escrita |
| PK / FK / UK | Primary / Foreign / Unique key |
| JSONB | Estrutura flexível — ver campos documentados |

---

## 2. Coverage & evidence

### 2.1 `coverage_evidence` (pré-existente, autoridade dual)

| Campo | Tipo | Obrig. | Notas |
|-------|------|:------:|-------|
| id | bigserial | PK | 🟢 |
| entity_id | text/uuid | sim | 🟢 |
| source | text | sim | 🟢 |
| data_type / capability | text | | dual: open_tenders \| historical_contracts |
| applicability | text | | 🟢 |
| state | text | | 9 estados CoverageState |
| run_id | text | | 🟢 |
| counts (expected/processed/obtained/…) | int | | 🟢 |
| freshness_status | text | | 🟢 |
| error_code / error_message | text | | 🟢 |
| metadata | jsonb | | 🟢 |

### 2.2 View `v_dual_capability_evidence_latest` (mig 058) 🟢

Latest row por `(entity_id, source, COALESCE(capability, data_type))` ordenado por `completed_at DESC`.

### 2.3 `entity_coverage` (legado) 🟢

**NÃO** autoridade para dual capability. Comentário SQL ADR-029: diagnostic only.

---

## 3. National intelligence (mig 060) 🟢

Views analíticas sobre `pncp_supplier_contracts` (`is_active = TRUE`):

| View | Granularidade | scope_label |
|------|---------------|-------------|
| `v_intel_contracts_raw_national` | contrato | raw_national |
| `v_intel_contracts_geo_sc` | contrato UF=SC | geo_sc |
| `v_intel_supplier_geo` | fornecedor (cnpj8) | intel_product |
| `v_intel_agency_profile` | órgão (cnpj8) | intel_product |

Campos agregados típicos: `contract_count`, `valor_sum`, `valor_p50`, `uf_count`/`ufs`, `has_sc`, datas first/last publicação.

---

## 4. Canonical entity linkage (mig 061) 🟢

### 4.1 `canonical_organs`

| Campo | Tipo | Notas |
|-------|------|-------|
| id | bigserial PK | |
| canonical_key | text UK | cnpj14 ou cnpj8:norm_name |
| entity_kind | text | organ \| unit |
| cnpj14 / cnpj8 / ibge_code | text | strong keys |
| raw_name / normalized_name | text | |
| uf / municipio | text | |
| source | text | default pncp |
| source_record_ids | jsonb | |
| decision_history | jsonb | |
| first/last_seen_run_id | text | |

### 4.2 `canonical_suppliers`

| Campo | Tipo | Notas |
|-------|------|-------|
| id | bigserial PK | |
| canonical_key | text UK | prefer cnpj14 |
| person_kind | text | cnpj \| cpf \| unknown |
| cnpj14 / cnpj8 / cpf11 | text | UK parcial em cnpj14 |
| raw_name / normalized_name | text | |
| source_record_ids / decision_history | jsonb | |

### 4.3 Links (padrão)

Links opportunity↔organ, contract↔opportunity, contract↔supplier com:

| Campo | Notas |
|-------|-------|
| classification | exact / deterministic_composite / heuristic_reviewable / ambiguous / unresolved |
| score | float |
| reason_codes | text[]/jsonb |
| rule_version | versionamento de regras |
| run_id | idempotência |
| claim_level | fact / similarity / inference / none 🟡 (código) |

---

## 5. Commercial leads (mig 062) 🟢

### 5.1 `commercial_lead_runs`

| Campo | Tipo | Check / default |
|-------|------|-----------------|
| run_id | text PK | |
| as_of | timestamptz | now() |
| profile_id / version / hash | text | |
| snapshot_hash | text | |
| snapshot_manifest | jsonb | |
| git_sha | text | |
| status | text | RUNNING \| PASS \| BLOCKED \| FAIL |
| queue_limit | int | 20 |
| eligible/ranked_companies | int | |
| metrics / non_claims | jsonb | |
| finished_at | timestamptz | |

### 5.2 `commercial_leads`

| Campo | Tipo | Check |
|-------|------|-------|
| id | bigserial PK | |
| run_id | FK → runs | CASCADE |
| cnpj14 | text | UK (run_id, cnpj14) |
| cnpj8 | text | |
| razao_social | text | |
| score_total | numeric(12,4) | |
| priority | text | CRITICAL\|HIGH\|MEDIUM\|LOW\|WATCH |
| score_decomposition / signals_* / evidence | jsonb | |
| suggested_offer / next_human_step | text | |
| limitations | jsonb | |
| commercial_state | text | NEW…DO_NOT_CONTACT |
| rank_position | int | |

### 5.3 `commercial_lead_state_overrides`

Override humano: cnpj14, author, previous/new_state, reason, run_id.

### 5.4 `commercial_feedback_ledger`

Ledger de feedback comercial (extensão da mig 062).

---

## 6. `supplier_registry` (mig 063) 🟢

| Campo | Tipo | Notas |
|-------|------|-------|
| cnpj14 | text PK | |
| razao_social / nome_fantasia | text | |
| cnae_principal | text | index |
| cnaes_secundarios | jsonb | |
| situacao_cadastral | text | |
| data_situacao | date | |
| municipio / uf | text | |
| source / source_version / source_date | text/date | never invent |

---

## 7. Snapshot write guard (mig 064) 🟢

| Objeto | Papel |
|--------|-------|
| `prevent_pncp_snapshot_mutation()` | Trigger function |
| `trg_prevent_pncp_snapshot_mutation` | BEFORE I/U/D em `pncp_supplier_contracts` |
| `app.confenge_snapshot_guard` | GUC session: `on` ativa proteção |
| `app.allow_snapshot_mutation` | GUC LOCAL: `on` permite restore controlado |

---

## 8. FK relaxations (mig 055–056) 🟢

| Mig | Mudança |
|-----|---------|
| 055 | Drop orgao_entity FK national PNCP |
| 056 | Drop supplier_entity FK contracts |

Objetivo: permitir contratos/órgãos nacionais sem entity local obrigatória.

---

## 9. Opportunity content hash (mig 057) 🟢

Fix upsert opportunity com content hash (integridade de conteúdo).

---

## 10. Coverage evidence uniqueness (mig 059) 🟢

Unique canônico entity em coverage_evidence (hardening).

---

## 11. Dataclasses de domínio (código) 🟢

| Tipo | Módulo | Campos-chave |
|------|--------|--------------|
| `SourceInfo` | crawl/registry | name, capabilities, authority, SLA, zero_proof |
| `CoverageState` | coverage/states | 9 estados enum |
| `LeadScore` | commercial_leads/scoring | score_total, offer_scores, priority |
| `LinkDecision` | linkage/resolve | classification, score, auto_accept |
| `StrongKeys` | linkage/keys | cnpj14/8, cpf, ibge |
| `CanonicalEntity` | lib/universe | cnpj8, ibge, identity |
| `ValorSemantica` | lib/value_semantics | tipos de valor |
| `CommercialClassification` | coverage/commercial_status | status comercial |
| `MetricResult` / `CoverageContractReport` | coverage/coverage_contract | multi-métrica |
| `DualCoverageReport` | coverage/dual_capability | open_tenders + historical |
| `EntitySourceRecord` | source_registry/models | status, strategy |
| `TargetEntity` | contract_intel/target_universe | 200km |
| `StageResult` / `WeeklyCycleReport` | ops/weekly_cycle | stages |

---

## 12. Tabelas canônicas pré-existentes (referência)

| Tabela | Papel |
|--------|-------|
| `pncp_supplier_contracts` | Fatos de contratos |
| `sc_public_entities` | Universo SC |
| `opportunity_intel` | Oportunidades |
| `entity_source_registry` | ESR (053) |
| `official_acts` | Atos unificados (052) |
| `dlq_entries` / watermarks / pipeline_runs | Resilience (045–048) |
| `entity_aliases` | Matching |

---

## 13. Lacunas 🔴

| ID | Item |
|----|------|
| DD-01 | Dump live / row counts produção não medidos nesta sessão |
| DD-02 | JSONB schemas internos de metrics/evidence não formalizados em JSON Schema |
| DD-03 | commercial_feedback_ledger colunas detalhadas — ver mig 062 completa se estender |

---

*Data Dictionary — Archaeologist 2026-07-28*

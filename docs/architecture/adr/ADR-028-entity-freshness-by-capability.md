# ADR-028 — Entity Freshness by Capability

| Campo | Valor |
|-------|-------|
| **Status** | Accepted |
| **Data** | 2026-07-20 |
| **Decisores** | Architecture Squad, Data Squad, QA Squad, Product Squad |
| **Campanha** | ENTITY-FRESHNESS-01 |
| **Relacionados** | ADR-018, ADR-019, ADR-020, ADR-021 |

---

## Contexto

O DOD exige: *“Freshness coverage mensurável por entidade dentro dos SLAs.”*

Estado anterior:

- `scripts.freshness_gate` e freshness de `weekly_cycle` operam **por fonte** (MAX `ingested_at`).
- `scripts.coverage.entity_freshness` classifica entidade com status restrito (`fresh|stale|never`) e **não** separa editais vs contratos.
- `MAX(ingested_at)` global ou por fonte **não** prova freshness de cada uma das 1.093 entidades.

## Decisão

### 1. Freshness é por (entity_id, capability)

Capabilities canônicas:

| capability | Relatório | SLA default |
|------------|-----------|-------------|
| `notices_or_bids` | `output/coverage/freshness-editais.json` | `open_opportunities_hours` (24h) |
| `contracts` | `output/coverage/freshness-contracts.json` | `contracts_amendments_hours` (72h) |

### 2. List identity

Cada relatório deve conter **exatamente** `EXPECTED_UNIVERSE = 1093` `entity_id` distintos:

- `covered + uncovered = 1093`
- zero duplicatas
- 1092 ou 1094 → falha fechada

### 3. Estados permitidos

```
FRESH | STALE | NEVER | INCOMPLETE | BLOCKED | NOT_APPLICABLE | UNKNOWN
```

Regras fail-closed:

- `UNKNOWN`, `NEVER`, `BLOCKED`, `INCOMPLETE` **nunca** promovem a `FRESH`
- Linha sem proveniência (`run_id` + `content_hash` + timestamp verificável) **nunca** é `FRESH`
- `age_hours` ausente permanece `null` (não vira 0)
- Timestamp futuro → `INCOMPLETE` (não `FRESH`)
- `NOT_APPLICABLE` fora do numerador de freshness

### 4. Proveniência obrigatória por linha

Campos mínimos: `entity_id`, `capability`, `source_id` ou ausência explícita, `applicability`,
`last_attempt_at`, `last_success_at`, `last_verified_at`, `sla_id`, `sla_hours`, `age_hours`,
`freshness_status`, `run_id`, `raw_uri`/`artifact_ref`, `content_hash`, `blocker`,
`next_action`, `as_of`, `adapter_version`.

### 5. SLA versionado

`config/coverage_slas.yaml` carrega `sla_version`. Relatórios carimbam `sla_version` e `sla_id`.

### 6. ESR capability (Opção A)

Tabela `entity_source_binding` com coluna `capability` e UNIQUE
`(canonical_id, source_id, capability)`. Permite múltiplas capabilities por entidade-fonte
sem redesenhar `entity_source_registry` (053).

### 7. Path canônico

- Engine: `scripts.coverage.freshness_by_entity`
- Operacional: `scripts.ops.weekly_cycle` (strict rejeita relatórios incompletos)
- Workspace permanece fachada

## Alternativas rejeitadas

| Alternativa | Motivo |
|-------------|--------|
| Freshness só por fonte | Não atende DOD “por entidade” |
| Tabela filha `entity_source_capability` (Opção B) | Extra hop sem ganho; Opção A cobre multi-cap |
| Framework genérico / event bus | Fora do raio; YAGNI |
| Promover com MAX global | Falso positivo massivo |

## Consequências

- Relatórios nominais com gaps explícitos (blocker + next_action)
- Strict mode passa a exigir dual report completo
- Percentual observado pode ser registrado sem claim de 95%

## Critérios de aceite

- [x] Dual report 1093×2 com list identity
- [x] Status set + proveniência fail-closed
- [x] Testes adversariais
- [x] Strict rejeita incompleto
- [x] Item DOD de mensurabilidade fechado com evidência (sem 95%)

## Referências

- `docs/ops/campaigns/ENTITY-FRESHNESS-01/`
- `scripts/coverage/freshness_by_entity.py`
- `db/migrations/058_entity_source_binding_capability.sql`

# ADR-028 — Entity Freshness by Capability (Canonical Universe)

| Campo | Valor |
|-------|-------|
| **Status** | Accepted |
| **Data** | 2026-07-20 |
| **Decisores** | Architecture Squad, Data Squad, QA/DevOps Squad, Product Squad |
| **Campanha** | ENTITY-FRESHNESS-CANONICAL-ACCEPTANCE-01 |
| **Relacionados** | ADR-018, ADR-019, ADR-020, ADR-021 |
| **Base SHA** | `d6d9e1984e348d64a669546613e192e4ebf610cd` |

---

## Contexto

O DOD exige: *“Freshness coverage mensurável por entidade dentro dos SLAs.”*

Estado anterior em main:

- Freshness operacional por fonte (`MAX(ingested_at)`) não prova entidade.
- `entity_freshness` não separava editais vs contratos.
- Campanhas anteriores (ex.: PR #63 seletiva) usavam `EXPECTED_UNIVERSE=1093` e IDs do registry sem igualdade de conjuntos com a planilha canônica.
- **Mesma cardinalidade ≠ mesma identidade.**

## Decisão

### 1. População canônica exclusiva

- Denominador e `entity_id` vêm **somente** de `scripts.lib.universe.load_canonical_universe(seed).included`.
- Seed canônico: `Extra - alvos de licitação. R-0.xlsx`.
- Relatórios carimbam `seed_path`, `seed_sha256` e `canonical_ids_sha256` (hash ordenado dos IDs).
- `len == 1093` **não** é critério de aceite.

### 2. Registry = observações reconciliadas

- `data/entity_source_registry.jsonl` **não** define membership.
- Cada linha do registry é reconciliada a um `entity_id` canônico (CNPJ8 único; desambiguação nome/município).
- Fail closed: não reconciliada, duplicada, ausente ou excedente.

### 3. Dual capability

| capability | Relatório | SLA default |
|------------|-----------|-------------|
| `notices_or_bids` | `output/coverage/freshness-editais.json` | 24h |
| `contracts` | `output/coverage/freshness-contracts.json` | 72h |

Observação de editais **não** promove contratos e vice-versa.

### 4. Classificação fail-closed

```
FRESH | STALE | NEVER | INCOMPLETE | BLOCKED | NOT_APPLICABLE | UNKNOWN
```

- FRESH e STALE exigem timestamp entity-scoped + `run_id` + `content_hash`.
- Timestamp ausente → NEVER (`age_hours=null`, nunca 0).
- Sem `run_id`/`content_hash` ou timestamp futuro → INCOMPLETE.
- Ausência de observação → NEVER (não zero, não FRESH).
- Breaches listados nominalmente com `entity_id`.

### 5. Evidência (ADR-020)

- Relatórios completos em `output/coverage/` (fora do Git).
- Manifesto compacto selado em Git: `docs/ops/campaigns/ENTITY-FRESHNESS-01/evidence/acceptance-manifest.json`
  (git_sha, seed/registry/report hashes, contagens, claims).

### 6. Fora de escopo desta decisão

- Migration `058` / tabela `entity_source_binding` — **não** são spine de aceite.
- Cobertura operacional 95%, recall 95%, VPS, LOCAL_READY, PROJECT_DONE.

## Alternativas rejeitadas

| Alternativa | Motivo |
|-------------|--------|
| Denominador = registry cardinality / constante 1093 | Não prova identidade com a planilha |
| Merge wholesale PR #63 | Contamina com 058/bindings e list-identity por contagem |
| MAX(ingested_at) global | Falso positivo massivo |
| Framework genérico / event bus / dbt | Fora do raio; YAGNI |

## Path canônico

- Engine: `scripts.coverage.freshness_by_entity`
- Testes obrigatórios CI: `tests/test_freshness_by_entity.py`
- SLA: `config/coverage_slas.yaml` (`sla_version`)

## Critérios de aceite

- [x] Dual report com set equality vs `load_canonical_universe().included`
- [x] Reconciliação fail-closed registry → canônico
- [x] Classificação adversarial (FRESH/STALE/NEVER/INCOMPLETE/capability)
- [x] Teste específico no job CI crítico
- [x] Manifesto selado com hashes; tamper invalida
- [x] Sem claims de 95% / LOCAL_READY / VPS / PROJECT_DONE
- [x] Item DOD de mensurabilidade fechado com evidência canônica

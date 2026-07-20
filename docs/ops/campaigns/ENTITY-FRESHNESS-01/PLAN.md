# ENTITY-FRESHNESS-01 — Campaign Plan

| Campo | Valor |
|-------|-------|
| **ID** | ENTITY-FRESHNESS-ACCEPTANCE-SPINE-01 |
| **Base** | `origin/main` + branch `fix/weekly-strict-fail-closed` (PR #63) |
| **Objetivo único** | Tornar freshness **mensurável, reproduzível, fail-closed e nominal** para 1.093 entidades × capabilities `notices_or_bids` e `contracts` |
| **Não-objetivo** | Atingir 95% freshness / cobertura operacional / recall |

## Squad decisions (Fase Zero)

### Architecture Squad

| Decisão | Escolha | Razão |
|---------|---------|-------|
| Capability no ESR | **Opção A** — coluna `capability` em `entity_source_binding` com UNIQUE `(canonical_id, source_id, capability)` | Menor migração vs redesenho do registry 053; multi-capability por entidade-fonte; integridade relacional; sem event bus |
| Separação editais/contratos | Relatórios distintos + capability explícita por linha | DOD exige dual-metric |
| Path canônico | `scripts.ops.weekly_cycle` + engine `scripts.coverage.freshness_by_entity` | CLI-first; workspace só fachada |
| PR #63 | Reutilizar seletivamente fail-closed (já em `fix/weekly-strict-fail-closed`) | Sem merge wholesale #54–#64 |

### Data Squad

| Decisão | Escolha |
|---------|---------|
| Migration | `058_entity_source_binding_capability.sql` (additive) |
| Identity | `canonical_id` do ESR = `entity_id` nos relatórios de freshness |
| SLA versionado | `config/coverage_slas.yaml` com `sla_version` + hours por capability |
| Histórico | Registry 053 preservado; binding é tabela nova |

### QA Squad

| Decisão | Escolha |
|---------|---------|
| Testes adversariais | `tests/test_freshness_by_entity.py` (funções puras) |
| Strict false-green | `tests/test_weekly_cycle.py` (universe=0, never, contracts fail, limit=5) |
| List identity | Fail closed em 1092/1094/duplicatas |
| Evidência | `docs/ops/campaigns/ENTITY-FRESHNESS-01/evidence/` |

### Product Squad

| Decisão | Escolha |
|---------|---------|
| Item DOD | Somente linha: “Freshness coverage mensurável por entidade dentro dos SLAs.” |
| Claims | Mensurável / 1093 representadas / separado / strict fail-closed — **nunca** 95% nesta campanha |
| Outputs | `output/coverage/freshness-editais.json` e `freshness-contracts.json` (fora do Git) |

## Waves

1. **T1 Strict readiness** — `weekly_cycle` fail-closed (PR #63 base).
2. **T2 Contract/ADR** — freshness por entidade+capability.
3. **T3 ESR capability** — migration + binding.
4. **T4 Engine** — pure classification + dual reports.
5. **Integração serial** — wire + DOD + HANDOFF.

## SUCCESS criteria

- Ambos relatórios com 1.093 `entity_id` únicos
- List identity ok
- Strict rejeita incompleto
- Testes obrigatórios passam
- Somente o item de freshness do DOD marcado
- Claims forbidden respeitados

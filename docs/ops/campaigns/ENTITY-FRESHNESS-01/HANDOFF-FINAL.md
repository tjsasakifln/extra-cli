# HANDOFF-FINAL — ENTITY-FRESHNESS-01

| Campo | Valor |
|-------|-------|
| **Campanha** | ENTITY-FRESHNESS-ACCEPTANCE-SPINE-01 |
| **Status** | **SUCCESS** (mensurabilidade fechada) |
| **Data** | 2026-07-20 |
| **Branch base** | `fix/weekly-strict-fail-closed` (PR #63 fail-closed reutilizado) |
| **Migration** | `058_entity_source_binding_capability` |
| **ADR** | ADR-028 (vigente) |

## Resultado mensurável

| Artefato | entity_ids únicos | covered+uncovered | capability | Status (as_of 2026-07-20) |
|----------|-------------------|-------------------|------------|---------------------------|
| `output/coverage/freshness-editais.json` | **1093** | covered+uncovered=1093 | `notices_or_bids` | FRESH=0 · STALE=408 · NEVER=685 |
| `output/coverage/freshness-contracts.json` | **1093** | covered+uncovered=1093 | `contracts` | FRESH=365 · NEVER=728 |

- List identity: **ok** em ambos (`evidence/list-identity.json`)
- Status set: FRESH/STALE/NEVER/INCOMPLETE/BLOCKED/NOT_APPLICABLE/UNKNOWN
- Proveniência: `pipeline_evidence_promote` → `run_id` / `raw_sha256` / `last_seen_at` / `raw_uri` por entidade
- Separação observation-level: fontes `pncp` (editais) vs `pncp_contracts` (contratos) — não só label de SLA
- SLA: `coverage-sla-v1` (editais 24h / contratos 72h)
- **Sem claim de freshness ≥95%** (contratos ~33% FRESH é observação, não meta fechada)

## Decisões de squad (Fase Zero)

1. **ESR capability = Opção A** — coluna `capability` em `entity_source_binding` com UNIQUE `(canonical_id, source_id, capability)`.
2. **PR #63** reutilizada seletivamente (fail-closed weekly); sem merge wholesale #54–#64.
3. **Engine puro** em `scripts/coverage/freshness_by_entity.py` (sem DB para classificação adversarial).
4. **DOD**: apenas o item de mensurabilidade de freshness marcado.

## Aceite (checklist)

1. [x] Dois relatórios existem
2. [x] 1.093 entity_ids únicos cada
3. [x] covered + uncovered = 1.093
4. [x] Sem duplicidades
5. [x] Capability explícita
6. [x] SLA versionado
7. [x] Cálculo por entidade (não só fonte/tabela)
8. [x] `MAX(ingested_at)` global não promove entidades
9. [x] Ausência não vira zero/FRESH
10. [x] Determinístico para mesmos inputs
11. [x] Testes adversariais passam
12. [x] Strict rejeita relatórios incompletos
13. [x] Gates locais verdes (pytest/ruff/bandit/pip-audit)
14. [x] DOD/ADR/HANDOFF atualizados com evidência

## Claims

**Permitidos**

- freshness é mensurável por entidade
- 1.093 entidades estão representadas
- editais e contratos são separados
- estado observado e gaps são nominais
- modo strict falha fechado

**Proibidos (não reivindicados)**

- cobertura operacional ≥95%
- freshness ≥95%
- recall ≥95%
- LOCAL_READY / VPS_OPERATIONAL / PROJECT_DONE
- proxy de presença como cobertura operacional
- MAX(ingested_at) global como freshness das 1.093 entidades

## Comandos de verificação

```bash
python -m pytest tests/test_weekly_cycle.py -q --no-cov
python -m pytest tests/test_freshness_by_entity.py -q --no-cov
python -m pytest tests/ -k "freshness or source_registry or weekly_cycle" -q --no-cov
python -m scripts.coverage.freshness_by_entity --strict
ruff check scripts/coverage/freshness_by_entity.py scripts/source_registry/bindings.py scripts/ops/weekly_cycle.py
```

## Arquivos principais

- `scripts/coverage/freshness_by_entity.py` (engine)
- `scripts/source_registry/bindings.py` + `db/migrations/058_*.sql`
- `scripts/ops/weekly_cycle.py` (strict + dual report gate)
- `docs/architecture/adr/ADR-028-entity-freshness-by-capability.md`
- `docs/ops/campaigns/ENTITY-FRESHNESS-01/evidence/*`

## Skeptic remediation (2026-07-20 re-pass)

| Gap | Fix |
|-----|-----|
| `last_success_at` dropado sem override | `observation_from_registry_row` usa promote + fallback capability-aware |
| promote evidence não mapeada | `_extract_capability_evidence` lê run_id/raw_sha256/raw_uri/last_seen_at |
| dual report só SLA-label | filtro de `sources` por capability (pncp vs pncp_contracts) |
| migration só texto | `evidence/esr-capability-validation.json` + `{SCRATCH}/esr_capability.log` (DSN down → structural PASS honesto) |

## Próximos passos (fora desta campanha)

- Coletar/evidenciar por entidade para reduzir NEVER/STALE (sem reabrir este item como “95%”)
- Campanhas separadas para cobertura operacional 95% e recall ≥95%
- Merge da PR #63 + esta branch após review humano / CI remoto
- Aplicar migration 058 quando LOCAL_DATALAKE_DSN estiver up

## Revisão manual registrada

Implementação e gates locais executados na sessão 2026-07-20 (incl. re-pass pós-skeptic). Wave 1 fail-closed validada. Dual reports regeneráveis via CLI com proveniência real. Parar em SUCCESS — **não** iniciar trabalho de cobertura 95% nesta campanha.

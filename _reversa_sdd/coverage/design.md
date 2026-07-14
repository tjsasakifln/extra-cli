# Coverage — Design Técnico (v1.0)

> Gerado pelo Writer em 2026-07-13 | doc_level: completo | Base: 249340d

## Interface

| Símbolo | Assinatura | Retorno | Observação |
|---------|-----------|---------|------------|
| `calculate_coverage` | `(conn, universe_run_id)` | `CoverageReport` | 7 métricas independentes |
| `validate_coverage` | `(conn, source, entity_key)` | `CoverageValidation` | 34KB, validação detalhada |
| `run_matching` | `(conn, entities)` | `MatchResult` | Entity matching cascade |
| `ConsultingReadiness.check` | `(conn, profile, seed)` | `ReadinessVerdict` | 17 critérios, 88KB |
| `FreshnessGate.check` | `(conn, sources, now)` | `FreshnessVerdict` | SLA por fonte |

## Fluxo Principal (Coverage Validation)

1. **Load universe:** CanonicalUniverse com 1.093 entes 🟢
2. **Load registry:** `iter_sources()` → 8+ fontes com capabilities 🟢
3. **Check applicability:** matriz ente×fonte×capacidade 🟡 (parcial)
4. **Query evidence:** `coverage_evidence` table → estado de cada par 🟢
5. **Calculate metrics:** 7 dimensões independentes 🟢
6. **Emit manifest:** CoverageReport + blockers + recommended actions 🟢

## Fluxos Alternativos

- **Freshness gate:** Verifica `last_seen_at` vs SLA por fonte → stale se expirado
- **Readiness gate:** 17 critérios DoD → PARTIAL se qualquer um falhar
- **Measure expansion:** `measure_pncp_expansion.py` calcula ganho marginal de cobertura ao adicionar fontes

## Dependências

| Componente | Relação | Como usa |
|------------|--------|----------|
| `scripts/lib/universe.py` | Hard | Denominador canônico |
| `scripts/crawl/registry.py` | Hard | Fontes, capabilities, SLAs |
| `coverage_evidence` table | Hard | Ledger de evidência |
| `db/migrations/` | Schema | 027-029: coverage_evidence, evidence_state enum |

## Decisões de Design

| Decisão | Evidência | Confiança |
|---------|-----------|-----------|
| 7 métricas independentes, nunca índice global único | `plano-mestre §3` | 🟢 |
| Evidence states: not_applicable → pending → running → success_with_data/success_zero → partial → error → blocked → stale | ADR-013 | 🟢 |
| Gates fail-closed | ADR-014 | 🟢 |
| Semantic value stages: estimated → homologated → contracted → committed → liquidated → paid | ADR-015 | 🟢 |
| Denominador sempre inclui entes sem dados (conservador) | `plano-mestre §3.3` | 🟢 |

## Estado Interno

| Estado | Onde | Schema |
|--------|------|--------|
| Coverage evidence | `coverage_evidence` table | entity_key, capability, source, state, timestamps, error |
| Source registry | `scripts/crawl/registry.py` | YAML-like em Python |
| Applicability matrix | `config/source_applicability.yaml` | 🔴 Parcial |

## Riscos e Lacunas

- 🔴 Matriz de aplicabilidade incompleta — pares sem decisão = `unknown`
- 🔴 `consulting_readiness.py` duplica carregador de universo
- 🔴 `v_contracts_canonical` e views canônicas não materializadas
- 🟡 `measure_pncp_expansion.py` (3.5KB) parece script auxiliar, propósito exato inferido

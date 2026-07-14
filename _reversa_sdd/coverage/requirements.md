# Coverage — Requirements (v1.0)

> Gerado pelo Writer em 2026-07-13 | doc_level: completo | Base: 249340d
> **Fontes brownfield:** plano-mestre §3, §9 (P0-05); epic-technical-debt.md story 1.5; ADRs 013, 014, 015

## Visão Geral

Modelo de cobertura por fonte, ente e capacidade. Implementa as métricas definidas no plano-mestre §3 (7 dimensões de cobertura), o Coverage Truth Evidence Ledger (ADR-013), os gates fail-closed (ADR-014) e os estágios semânticos de valor (ADR-015). Separa rigorosamente data presence de operational coverage.

## Responsabilidades

- Cálculo de 7 métricas de cobertura: universe_resolution, source_applicability, capability_monitoring, data_presence, field_completeness, freshness, active_snapshot_integrity
- Evidence ledger (`coverage_evidence`) com 9 estados (not_applicable → stale)
- Registry de fontes com capabilities, authority_level, snapshot_semantics
- Matriz de aplicabilidade: par ente × fonte × capacidade
- Consulting readiness gate: 17 critérios DoD, exit code 0-3
- Freshness gate SLA configurável por fonte

## Regras de Negócio

- **Regra CV-01:** Data presence ≠ operational coverage. Ausência de dados não é falha se investigação foi completa. 🟢 `plano-mestre §3.4`
- **Regra CV-02:** `success_zero` exige: fonte aplicável, escopo completo executado, paginação concluída, período registrado, persistido como success_zero, dentro da janela de freshness. 🟢 `plano-mestre §3.3`
- **Regra CV-03:** Coverage gate fail-closed: na dúvida, assume não coberto. NUNCA assumir coberto por ausência de evidência em contrário. 🟢 ADR-014
- **Regra CV-04:** Gates CI: ruff + mypy + bandit + pytest. Bloqueiam commit se CRITICAL. 🟢 ADR-014
- **Regra CV-05:** Universe resolution gate: 100%. Valor atual: 100% (1.093/1.093). 🟢 `plano-mestre §3.1`
- **Regra CV-06:** Monitoring coverage gate por capability: ≥ 95%. 🟢 `plano-mestre §3.3`

🔴 **LACUNA (plano-mestre §9):** `coverage_evidence` existe mas matriz de aplicabilidade (par ente×fonte×capacidade) não está completa. 100% dos pares precisam ter decisão de aplicabilidade.
🔴 **LACUNA (plano-mestre §7):** `consulting_readiness.py` mantém carregador de universo duplicado. Deve usar exclusivamente `scripts/lib/universe.py`.

## Requisitos Funcionais

| ID | Requisito | Prioridade | Critério de Aceite |
|----|-----------|-----------|-------------------|
| RF-CV01 | Calcular 7 métricas de cobertura independentes | Must | Métricas desagregadas, sem índice global ambíguo |
| RF-CV02 | Evidence ledger com 9 estados e timestamps | Must | `coverage_evidence` table |
| RF-CV03 | Registry de fontes: name, capabilities, authority_level, snapshot_semantics, freshness_sla | Must | `scripts/crawl/registry.py` |
| RF-CV04 | Matriz de aplicabilidade: par ente×fonte×capacidade | Must | 🔴 100% pendente |
| RF-CV05 | Consulting readiness: 17 critérios DoD, exit code 0-3 | Must | `consulting_readiness.py` |
| RF-CV06 | Freshness gate: SLA por fonte, exit code ≠ 0 se stale | Must | `freshness_gate.py` |
| RF-CV07 | `success_zero` com prova completa de investigação | Must | 🔴 Implementação parcial |

## Requisitos Não Funcionais

| Tipo | Requisito | Evidência | Confiança |
|------|-----------|----------|-----------|
| Auditabilidade | Todo cálculo de cobertura referencia `universe_run_id` e `source_run_id` | ADR-013 | 🟢 |
| Confiabilidade | Gates fail-closed: nunca reportar "coberto" sem evidência | ADR-014 | 🟢 |

## Critérios de Aceitação

```gherkin
Dado um ente com fonte PNCP aplicável para open_tenders
Quando a execução completa retorna zero registros com paginação concluída
Então estado é `success_zero`
E capability_monitoring_coverage conta esse ente como coberto

Dado um ente com fonte PNCP não executada há 30 dias
Quando freshness gate verifica
Então estado é `stale`
E exit code ≠ 0

Dado readiness gate com 16/17 critérios DoD passando
Quando `consulting_readiness` é executado
Então exit code = 1 (data gaps)
E status = PARTIAL
```

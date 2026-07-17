---
story_id: B2G-E1.S2
title: "Calculadora M2 operational_source_coverage + identity tests"
status: InProgress
priority: P0
risk_level: STANDARD
effort: M
agent: "@dev"
epic: EPIC-B2G-OPERATIONAL-PLATFORM
vertical: E1
depends_on: [B2G-E1.S1, B2G-E2.S1]
blocks: [B2G-E1.S4, B2G-E4.S1]
adr: [ADR-018, ADR-019]
---

# Story B2G-E1.S2: Calculadora M2 operational_source_coverage

## Contexto

M2 é a métrica da **meta 95%** da proposta: entidades com ≥1 fonte aplicável e evidência `success_*` dentro do SLA. Requer ESR (E2.S1) + contrato (E1.S1).

## Valor de negócio

Medir honestamente a distância até 95% operacional; priorizar gaps.

## Escopo

**IN:** Função/CLI que calcula M2 a partir de ESR + evidence; breakdown por fonte; lista de gaps; testes.

**OUT:** Fechar os gaps (é trabalho de E2/E3); M1 recalibração de mercado.

## Acceptance Criteria

1. **Given** ESR com bindings e evidence ledger, **When** `calculate_operational_source_coverage()` roda, **Then** retorna numerator/denominator/pct + `unmeasured_reason` se dados insuficientes.
2. **Given** entidade `applicable` sem success no SLA, **When** M2 agrega, **Then** ela **não** entra no numerador.
3. **Given** entidade só `unknown`, **When** M2 agrega, **Then** não conta como coberta; aparece em gaps `unknown`.
4. **Given** output, **When** export gaps CSV/JSON, **Then** cada linha tem entity_id, missing reason, suggested source.
5. **Given** status `collected` ou evidência sem run/raw/hash/reconciliation,
   **When** M2 agrega, **Then** não conta no numerador.
6. **Given** `last_success_at` fora do SLA da fonte, **When** M2 agrega,
   **Then** não conta mesmo que o status legado seja `verified`.

## Fontes de dados

ESR, `coverage_evidence` / last_success, registry SLA hours.

## Dependências

B2G-E1.S1, B2G-E2.S1

## Riscos

Evidence ledger vazio → M2 unmeasured (honesto) vs 0% enganoso.

## Testes

Unit com fixtures ESR+evidence; identity denominator 1093.

## Evidência

`output/coverage/contract-report.json` e `output/coverage/entity-source-gaps.*`.
Resultado de 17/07/2026: M2 estrito `0/1093`; nenhum proxy legado aceito.

## DoD

- [x] AC1–6 implementados e cobertos por testes adversariais
- [x] Comando operacional e gaps nominais reproduzíveis
- [ ] CI remoto verde e QA final do PR

## Comandos de validação

```bash
python3 -m pytest tests/unit/coverage -o addopts='' -q
python3 -m scripts.coverage.coverage_contract_cli report --offline --format table
```

## Change Log

| Data | Autor | Nota |
|------|-------|------|
| 2026-07-17 | Morgan (PM) | Draft |
| 2026-07-17 | River (SM) | Validada para desenvolvimento com AC5–6 adversariais |
| 2026-07-17 | Dex (Dev) | M2 estrito implementado; 0/1093 comprovado; aguardando CI/QA final |

## File List

- `scripts/coverage/coverage_contract.py`
- `scripts/source_registry/models.py`
- `scripts/source_registry/gap_report.py`
- `tests/unit/coverage/test_coverage_contract_adversarial.py`
- `output/coverage/contract-report.json`

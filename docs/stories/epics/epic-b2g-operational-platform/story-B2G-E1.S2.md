---
story_id: B2G-E1.S2
title: "Calculadora M2 operational_source_coverage + identity tests"
status: Draft
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

## Fontes de dados

ESR, `coverage_evidence` / last_success, registry SLA hours.

## Dependências

B2G-E1.S1, B2G-E2.S1

## Riscos

Evidence ledger vazio → M2 unmeasured (honesto) vs 0% enganoso.

## Testes

Unit com fixtures ESR+evidence; identity denominator 1093.

## Evidência

JSON M2 + gaps path em output/ (não git).

## DoD

- [ ] AC1–4; pytest; docs fórmula M2

## Comandos de validação

```bash
pytest tests/ -k "operational_source_coverage or m2_" -v
# CLI esperado pós-impl:
# python -m scripts.coverage.contract m2 --as-of today
```

## Change Log

| Data | Autor | Nota |
|------|-------|------|
| 2026-07-17 | Morgan (PM) | Draft |

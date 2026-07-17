---
story_id: B2G-E1.S4
title: "Coverage gate no CI/workspace (ban single-metric headline)"
status: Draft
priority: P1
risk_level: STANDARD
effort: S
agent: "@dev"
epic: EPIC-B2G-OPERATIONAL-PLATFORM
vertical: E1
depends_on: [B2G-E1.S1, B2G-E1.S2]
blocks: []
adr: [ADR-018]
---

# Story B2G-E1.S4: Coverage gate — ban single-metric headline

## Contexto

Gates e workspace devem **falhar** se output de coverage comercial omitir dual-metric.

## Valor de negócio

Enforcement contínuo do contrato; evita regressão de overclaim.

## Acceptance Criteria

1. **Given** manifesto sem M1 ou sem M2 slot, **When** gate roda, **Then** exit ≠ 0.
2. **Given** denominador ≠ 1093 sem override documentado, **When** gate roda, **Then** fail.
3. **Given** `workspace coverage`, **When** imprime headline, **Then** ambas métricas visíveis.

## Dependências

E1.S1, E1.S2

## Testes

Unit do gate com JSON fixtures good/bad.

## DoD

- [ ] Gate integrável CI local; documentado no epic

## Comandos de validação

```bash
pytest tests/ -k "coverage_gate" -v
```

## Change Log

| Data | Autor | Nota |
|------|-------|------|
| 2026-07-17 | Morgan (PM) | Draft |

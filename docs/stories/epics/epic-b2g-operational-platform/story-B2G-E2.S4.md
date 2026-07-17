---
story_id: B2G-E2.S4
title: "ESR export + integração M2"
status: Draft
priority: P0
risk_level: STANDARD
effort: S
agent: "@dev"
epic: EPIC-B2G-OPERATIONAL-PLATFORM
vertical: E2
depends_on: [B2G-E2.S1, B2G-E1.S2]
blocks: [B2G-E1.S4]
adr: [ADR-019, ADR-018]
---

# Story B2G-E2.S4: ESR export + integração calculadora M2

## Contexto

Fechar o loop ESR → M2 para o workspace e gates.

## Acceptance Criteria

1. **Given** ESR + evidence, **When** export+M2, **Then** mesmo numerator via API calculadora e via SQL/view documentada.
2. **Given** workspace coverage, **When** chamado, **Then** consome export/API sem ler planilha ad-hoc.

## DoD

- [ ] Integração E1.S2 verificada por teste e2e leve

## Comandos de validação

```bash
pytest tests/ -k "esr_m2 or operational_source" -v
```

## Change Log

| Data | Autor | Nota |
|------|-------|------|
| 2026-07-17 | Morgan (PM) | Draft |

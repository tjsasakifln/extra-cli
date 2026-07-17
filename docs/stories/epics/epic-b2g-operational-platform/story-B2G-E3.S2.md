---
story_id: B2G-E3.S2
title: "Checkpoint/resume unificado + DLQ smoke"
status: Draft
priority: P0
risk_level: STANDARD
effort: M
agent: "@dev"
epic: EPIC-B2G-OPERATIONAL-PLATFORM
vertical: E3
depends_on: [B2G-E3.S1]
blocks: [B2G-E3.S3]
adr: [ADR-021, ADR-020]
---

# Story B2G-E3.S2: Checkpoint/resume unificado + DLQ smoke

## Contexto

Checkpoints por fonte heterogêneos; resume nem sempre testado; falhas sem DLQ clara.

## Acceptance Criteria

1. **Given** job interrompido após N páginas, **When** resume, **Then** não reprocessa fatias success já checkpointadas.
2. **Given** rate_limited, **When** resume posterior, **Then** retoma fatia pendente.
3. **Given** registro poison, **When** DLQ, **Then** job principal não trava indefinidamente; smoke test documentado.

## DoD

- [ ] Smoke resume documentado; testes unitários checkpoint

## Comandos de validação

```bash
pytest tests/ -k "checkpoint or resume or dlq" -v
```

## Change Log

| Data | Autor | Nota |
|------|-------|------|
| 2026-07-17 | Morgan (PM) | Draft |

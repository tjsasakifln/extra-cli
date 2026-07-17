---
story_id: B2G-E4.S2
title: "Freshness hard-gate + exit codes no workspace"
status: Draft
priority: P0
risk_level: STANDARD
effort: M
agent: "@dev"
epic: EPIC-B2G-OPERATIONAL-PLATFORM
vertical: E4
depends_on: [B2G-E4.S1, B2G-E3.S3]
blocks: []
adr: [ADR-017, ADR-018]
---

# Story B2G-E4.S2: Freshness hard-gate

## Contexto

Briefings com dados stale são piores que erro explícito.

## Acceptance Criteria

1. **Given** fonte P0 acima do SLA, **When** `workspace today`, **Then** exit 2 (partial) e alerta no topo.
2. **Given** todas P0/P1 ok, **When** today, **Then** exit 0.
3. **Given** falha total de leitura, **When** any command, **Then** exit 1.

## DoD

- [ ] Exit codes testados; documentados no help

## Comandos de validação

```bash
pytest tests/ -k "workspace and freshness" -v
```

## Change Log

| Data | Autor | Nota |
|------|-------|------|
| 2026-07-17 | Morgan (PM) | Draft |

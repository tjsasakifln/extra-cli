---
story_id: B2G-E2.S3
title: "Portal/unknown resolution queue + confidence"
status: Draft
priority: P1
risk_level: STANDARD
effort: M
agent: "@dev"
epic: EPIC-B2G-OPERATIONAL-PLATFORM
vertical: E2
depends_on: [B2G-E2.S1, B2G-E2.S2]
blocks: []
adr: [ADR-019]
---

# Story B2G-E2.S3: Fila de resolução unknown + confidence

## Contexto

Após bootstrap/discovery, restam unknowns e low-confidence. Precisamos de fila priorizada para resolução (transparência, DOM-SC, manual).

## Valor de negócio

Trabalho humano/automático focado nos gaps que mais movem M2.

## Acceptance Criteria

1. **Given** ESR, **When** `queue --status unknown`, **Then** lista priorizada (ex.: municípios > autarquias).
2. **Given** resolução manual/automática, **When** binding atualizado, **Then** `last_verified_at` e confidence gravados.
3. **Given** not_applicable justificado, **When** marcado, **Then** não aparece como gap de monitoring.

## Testes

Unit da priorização; integration update binding.

## DoD

- [ ] CLI queue + update; testes

## Comandos de validação

```bash
pytest tests/ -k "esr_queue" -v
```

## Change Log

| Data | Autor | Nota |
|------|-------|------|
| 2026-07-17 | Morgan (PM) | Draft |

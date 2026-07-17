---
story_id: B2G-E5.S2
title: "Triage GO/NO-GO/WATCH + explain profile-bound"
status: Draft
priority: P0
risk_level: STANDARD
effort: M
agent: "@dev"
epic: EPIC-B2G-OPERATIONAL-PLATFORM
vertical: E5
depends_on: [B2G-E5.S1, B2G-E4.S1]
blocks: [B2G-E5.S3]
adr: [ADR-022, ADR-017]
---

# Story B2G-E5.S2: Triage + explain

## Contexto

Sessão comercial já produziu GO counts; falta triage estável ligada ao profile e exposta no workspace.

## Acceptance Criteria

1. **Given** oportunidades abertas, **When** triage, **Then** cada item tem label GO|NO-GO|WATCH + razões.
2. **Given** `workspace opportunities --triage` ou flag equivalente, **When** lista, **Then** labels visíveis.
3. **Given** `explain <id>`, **When** roda, **Then** dimensões de score + profile version + fontes.

## DoD

- [ ] CLI + testes; sem inventar campos de edital sem fonte

## Comandos de validação

```bash
pytest tests/ -k "triage or ranking" -v
python scripts/opportunity_intel/cli.py list --status open --limit 20
python scripts/opportunity_intel/cli.py explain 1
```

## Change Log

| Data | Autor | Nota |
|------|-------|------|
| 2026-07-17 | Morgan (PM) | Draft |

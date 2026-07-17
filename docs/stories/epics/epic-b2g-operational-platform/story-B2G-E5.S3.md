---
story_id: B2G-E5.S3
title: "Human feedback store + override na lista"
status: Draft
priority: P1
risk_level: STANDARD
effort: M
agent: "@dev"
epic: EPIC-B2G-OPERATIONAL-PLATFORM
vertical: E5
depends_on: [B2G-E5.S1, B2G-E5.S2]
blocks: []
adr: [ADR-022]
---

# Story B2G-E5.S3: Human feedback loop

## Contexto

Sem labels do Tiago, o ranking não melhora e a lei comercial não se valida em campo.

## Acceptance Criteria

1. **Given** oportunidade, **When** `workspace feedback <id> --label GO|NO-GO|WATCH --reason ...`, **Then** persiste com profile_version + ts.
2. **Given** label humana, **When** lista opportunities, **Then** override do score automático na coluna operacional.
3. **Given** export, **When** feedback dump, **Then** usável para retune mensal de weights (processo, não auto-ML opaco).

## DoD

- [ ] Store (tabela ou JSONL ops gitignored) + CLI + testes

## Comandos de validação

```bash
pytest tests/ -k "feedback" -v
```

## Change Log

| Data | Autor | Nota |
|------|-------|------|
| 2026-07-17 | Morgan (PM) | Draft |

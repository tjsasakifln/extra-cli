---
story_id: B2G-E5.S1
title: "Client profile v1 como lei de ranking"
status: Draft
priority: P0
risk_level: STANDARD
effort: M
agent: "@dev"
epic: EPIC-B2G-OPERATIONAL-PLATFORM
vertical: E5
depends_on: []
blocks: [B2G-E5.S2, B2G-E5.S3]
adr: [ADR-022]
---

# Story B2G-E5.S1: Client profile v1

## Contexto

Ranking disperso em configs e regras. ADR-022 exige profile versionado como única lei comercial.

## Valor de negócio

Scores explicáveis; alinhamento Extra/CONFENGE; base para feedback.

## Escopo

**IN:** Arquivo profile YAML/JSON versionado; loader; validação schema; wiring no ranking opportunity_intel; hard exclusions (incl. obra física fora de escopo).

**OUT:** Multi-cliente UI; LLM como lei.

## Acceptance Criteria

1. **Given** profile v1, **When** ranking roda, **Then** weights e filtros vêm do profile (não hardcode paralelo).
2. **Given** hard_exclusion match, **When** score, **Then** veredito NO-GO.
3. **Given** `explain`, **When** executa, **Then** cita `profile_id@version`.
4. **Given** mudança de weights, **When** bump version, **Then** outputs referenciam nova versão.

## Fontes de dados

`config/sectors_config.yaml` (ADAPT); regras radar existentes (mapear, não inventar setores).

## Testes

Unit loader; exclusion → NO-GO; snapshot weights.

## DoD

- [ ] Profile no git; testes; ADR-022 ref

## Comandos de validação

```bash
pytest tests/ -k "client_profile or profile_v1" -v
python scripts/opportunity_intel/cli.py explain 1  # pós-wiring
```

## Change Log

| Data | Autor | Nota |
|------|-------|------|
| 2026-07-17 | Morgan (PM) | Draft |

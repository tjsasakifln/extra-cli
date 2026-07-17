---
story_id: B2G-E1.S3
title: "Recall benchmark sample (gold set) + relatório de gaps"
status: Draft
priority: P1
risk_level: STANDARD
effort: M
agent: "@qa"
epic: EPIC-B2G-OPERATIONAL-PLATFORM
vertical: E1
depends_on: [B2G-E1.S1]
blocks: []
adr: [ADR-018]
---

# Story B2G-E1.S3: Recall benchmark (gold set)

## Contexto

Sem gold set, “95%” e até M1 são só presença de dados internos, não recall de campo.

## Valor de negócio

Medir falsos negativos (editais que deveriam ter sido capturados).

## Escopo

**IN:** Amostra gold (N≥30 órgãos/editais) documentada; script de comparação vs datalake; relatório recall/precision amostral.

**OUT:** Expandir gold para 1093; OCR de PDF.

## Acceptance Criteria

1. **Given** gold set versionado em `tests/fixtures/` ou `docs/baseline/`, **When** benchmark roda, **Then** emite recall amostral + lista miss.
2. **Given** miss, **When** classificado, **Then** tag: source_gap | match_gap | window_gap | other.
3. **Given** relatório, **When** publicado em docs/ops stamp, **Then** não afirma 95% global a partir da amostra.

## Fontes de dados

PNCP/SC publicações manuais amostradas; DB local.

## Riscos

Amostra viesada; mitigar estratificação (capital/interior, porte).

## Testes

Smoke do runner com fixture pequena.

## DoD

- [ ] Gold set + runner + relatório exemplo

## Comandos de validação

```bash
pytest tests/ -k "recall_benchmark" -v
```

## Change Log

| Data | Autor | Nota |
|------|-------|------|
| 2026-07-17 | Morgan (PM) | Draft |

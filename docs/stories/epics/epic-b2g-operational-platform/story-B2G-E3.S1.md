---
story_id: B2G-E3.S1
title: "Adapter contract + PNCP 429 fail-closed"
status: Draft
priority: P0
risk_level: HIGH-RISK
effort: L
agent: "@dev"
epic: EPIC-B2G-OPERATIONAL-PLATFORM
vertical: E3
depends_on: []
blocks: [B2G-E3.S2, B2G-E3.S3]
adr: [ADR-021]
---

# Story B2G-E3.S1: Adapter contract + PNCP 429 fail-closed

## Contexto

PNCP e outros adapters reportam sucesso parcial sob 429; dual content_hash; status semântico inconsistente. ADR-021 define fail-closed.

## Valor de negócio

Elimina falsos “success” que inflacionam coverage e corrompem briefings.

## Escopo

**IN:** Enum `FetchResult.status`; PNCP (e preferencialmente SC Compras/CIGA) emitindo status; 429→rate_limited; teste com mock 429; unificar content_hash canônico pós-normalize.

**OUT:** Reescrever todos os 14 crawlers; VPS provision.

## Acceptance Criteria

1. **Given** resposta HTTP 429, **When** adapter PNCP fetch, **Then** `status=rate_limited` e **não** grava evidence success da fatia.
2. **Given** pages_fetched < pages_expected, **When** finaliza, **Then** `status=partial` (não success).
3. **Given** 0 records com empty confirmado pela API, **When** finaliza, **Then** `empty_confirmed` permitido.
4. **Given** normalize, **When** hash, **Then** um contrato de hash documentado (sem dual silencioso).

## Fontes de dados

PNCP API (mocks em teste).

## Riscos

HIGH — muda semântica de jobs existentes; exigir feature flag se necessário.

## Testes

Unit mocks 429/partial/empty; contract tests adapter.

## DoD

- [ ] AC1–4; pytest; nota ADR-021 no módulo

## Comandos de validação

```bash
pytest tests/ -k "pncp and (429 or rate_limit or fail_closed or FetchResult)" -v
```

## Change Log

| Data | Autor | Nota |
|------|-------|------|
| 2026-07-17 | Morgan (PM) | Draft |

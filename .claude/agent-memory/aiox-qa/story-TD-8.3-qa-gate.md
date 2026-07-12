---
name: story-td-8.3-qa-gate
description: "Story TD-8.3 QA Gate — FAIL verdict. 0/10 ACs, 3 HIGH + 3 MEDIUM issues. Story never implemented (Draft)."
metadata:
  type: project
---

# Story TD-8.3 — PNCP API v3 Migration: QA Gate FAIL

**Verdict:** FAIL

**Date:** 2026-07-11

## Summary

Story TD-8.3 was created to fix the PNCP API v3 migration but was **never implemented**. All 10 ACs have 0 completion. All 27 subtasks are unchecked. Story status was Draft.

## Key Findings

| Issue | Severity | Detail |
|-------|----------|--------|
| REQ-001 | HIGH | PNCP_BASE still `/v1` in both `config/settings.py` and `scripts/crawl/pncp_crawler_adapter.py` |
| REQ-002 | HIGH | No page size minimum validation (`tamanhoPagina >= 10`) |
| REQ-003 | HIGH | Field names mismatch: code uses `ufSigla`/`municipioNome`/`dataPublicacaoPncp`/`dataAberturaProposta` but v3 API returns `siglaUf`/`nomeMunicipio`/`dataPublicacao`/`dataAbertura` per the story spec and fixture file |
| REQ-004 | MEDIUM | Keyword filter still active, modalidades not expanded, date range not expanded |
| REQ-005 | MEDIUM | Missing `temProximaPagina` fallback for v2 pagination |
| PROC-001 | MEDIUM | Story in Draft — never went through SDC lifecycle |

## Gate File

`docs/qa/gates/td-8.3-pncp-api-v3-migration.yml`

## What was already done (in other stories, committed in 7bbd13b)

- `paginasRestantes > 0` pagination logic
- `orgaoEntidade`/`unidadeOrgao` nested object access in `_transform_record()`
- `dataInicial`/`dataFinal` URL params (camelCase)
- `codigoModalidadeContratacao` URL param

## What remains

- Change PNCP_BASE from v1 to v3
- Add page size min validation (>= 10)
- Fix field names to match actual v3 API schema
- Add v2 pagination fallback
- Remove keyword filter, expand modalidades, adjust date range
- Run live crawl tests, verify coverage

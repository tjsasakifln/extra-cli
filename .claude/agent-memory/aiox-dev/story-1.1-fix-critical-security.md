---
name: Story 1.1 Fix Critical Security
description: Implementacao completa — 6 debitos tecnicos P0 resolvidos (SEC-03, SEC-02, TD-001, SEC-01, TD-019, TD-021)
metadata:
  type: project
---

**Story:** 1.1 Fix Critical Security
**Status:** InReview (implementado, aguardando QA)
**Data:** 2026-07-13
**Executor:** @dev (Dex), modo YOLO

## O que foi feito

1. **SEC-03** (P0): Senha hardcoded `postgres:smartlic_local` removida do default em `config/settings.py`. Agora usa `DATABASE_URL` env var com fallback `LOCAL_DATALAKE_DSN`. `.env.example` documentado.
2. **SEC-02** (P0): SA JSON ja gitignored (`config/*-sa.json`). `.env.example` documentado com `GOOGLE_APPLICATION_CREDENTIALS`.
3. **TD-001** (P0): sys.path.insert adicionado em `scripts/crawl/bids_crawler.py` para `ingestion.*` imports.
4. **SEC-01** (P0): f-string `f"SELECT * FROM {upsert_fn}(%s)"` em `monitor.py` substituida por `psycopg2.sql.Identifier`. Regra `S` (bandit) adicionada ao `pyproject.toml`.
5. **TD-019** (P1): sys.path.insert adicionado em `scripts/intel_pipeline.py` para `lib.cli_validation` imports.
6. **TD-021** (P1): `.env.example` e `.env` unificados para PNCP v3.

## Pendente para @devops (@qa)
- BFG repo-cleaner para remover senha do git history (SEC-03)
- Rotacao de senha do banco apos BFG (SEC-03)
- CodeRabbit review em modo committed (pre-PR)

## Tech debt identificado
- ~20 arquivos ainda contem `postgres:smartlic_local` hardcoded (fora do escopo desta story)
- Pre-existing S603/S110 em intel_pipeline.py suprimidos via per-file-ignores

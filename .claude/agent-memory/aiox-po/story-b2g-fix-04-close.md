---
name: story-b2g-fix-04-close
description: "Story B2G-FIX-04 Schema Alignment closed. 47 migrations fresh-install green, diagnostics aligned=true, QA PASS, publication authorized."
metadata:
  type: project
---

# Story B2G-FIX-04 Close

**Status:** Done (2026-07-14)
**QA Verdict:** PASS (commit eae0b2d)
**Publication:** Authorized

**Delivered:**
- 13 migrations corrigidas para chain deterministica (013, 014, 020, 022, 023, 025a, 026, 039, 040, 041a, 041b, 042 + setup_db.sh)
- `scripts/schema/diagnostics.py` — diagnostico automatizado de schema vs baseline
- Fresh install validado: 47 migrations em PostgreSQL 16 + pgvector, aligned=true
- 3 FKs validadas (convalidated=true via migration 042)
- Idempotencia: 47 SKIP em re-execucao
- `db/current-schema.sql` e SHA256 regenerados
- Teste `EXPECTED_CONSTRAINTS` corrigido para nomes _v2

**Why:** Bloqueante para producao — schema do codigo divergia do banco em 10 tabelas fantasmas e colunas divergentes. Sem alinhamento, crawlers e pipelines falhariam em runtime com "relation does not exist".

**Next:** B2G-FIX-04 blocks B2G-DB-01 (schema canonico) e B2G-INFRA-02 (PostgreSQL). Proximo passo logico e Fase 1 (Provisioning VPS) ou B2G-DB-01.

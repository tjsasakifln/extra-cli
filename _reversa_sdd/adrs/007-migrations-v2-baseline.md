# ADR-007: Migrations v2 Baseline (Reconstrução do Zero)

**Status:** ✅ Implementado
**Data:** 2026-07-11
**Epic:** EPIC-TD-001 / Story TD-2.1
**Commit:** `e9729e1`

## Contexto

Migrations v1 (001-014) divergiram completamente do schema real do banco após meses de evolução:
- `esfera_id` era INT nas migrations, TEXT no banco real ('F','E','M','D')
- `data_publicacao` era DATE nas migrations, TIMESTAMPTZ no real
- `enriched_entities` tinha schema plano nas migrations, JSONB no real
- Migrations 009-012 nunca foram aplicadas (0 views no banco real)
- Extensão `pgvector` existia no banco mas não nas migrations

Além disso, a migration 014 introduziu uma correção HNSW que não correspondia ao banco real (sem pgvector, sem coluna `embedding`).

## Decisão

**Criar baseline v2 via `pg_dump --schema-only` do banco real**, substituindo todas as migrations v1. O arquivo `001-v2_initial_schema.sql` (840 linhas) captura o estado exato do banco em produção.

Migrations v2 subsequentes (002-005) re-aplicam as correções que deveriam ter sido feitas nas migrations 009-012, mas agora sobre o schema correto.

## Evidência

🟢 CONFIRMADO — `supabase/migrations/001-v2_initial_schema.sql` (840 linhas, `pg_dump --schema-only`).
🟢 CONFIRMADO — `supabase/docs/DB-AUDIT.md` documenta 14 débitos técnicos, DT-01 (CRITICAL) = Migrations divergentes.
🟢 CONFIRMADO — `docs/td-001/migration-rebuild.md` analisa 5 divergências D1-D5.

## Consequências

- **Positivo:** Schema documentado é fiel ao banco real. Migrations são reproduzíveis.
- **Positivo:** Baseline única elimina ambiguidade sobre qual versão de migration é canônica.
- **Negativo:** Migrations v1 são históricas, não funcionais. Manter como referência de intenção original.
- **Risco:** Se o banco real mudar sem atualizar a baseline, o problema se repete. Mitigação: `verify-schema-divergence.sh`.

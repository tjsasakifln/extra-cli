---
name: td-2-4-schema-sync
description: "Story TD-2.4 criada para corrigir schema drift entre banco local PostgreSQL e o schema esperado pelo codigo, com migration SQL de sync, reset de runs travados e analise das duas arvores de migrations"
metadata:
  type: project
---

## Schema Drift no DataLake Local

A validacao end-to-end apos TD-2.1/TD-2.2/TD-2.3 revelou 5 problemas de schema drift no banco local (postgresql://postgres:smartlic_local@127.0.0.1:54399/postgres):

1. **entity_coverage table ausente** — quebra coverage --baseline e --report-coverage
2. **v_coverage_gaps_by_municipio view ausente** — quebra coverage --gaps
3. **ingestion_runs.source column ausente** — quebra --source pncp --mode incremental
4. **3 ingestion runs (IDs 3,4,5) travados em running** desde 2026-07-02
5. **ingestion_checkpoints vazia (0 rows)**

**Por que:** Duas arvores de migrations independentes: `db/migrations/` (original, 19 migrations) vs `supabase/migrations/` (reconstruida pela TD-2.1, 5 migrations v2). O banco local rodou uma sequencia diferente da versionada.

**Resolucao:** Story TD-2.4 com migration 020 unica e idempotente.

**How to apply:** Ao trabalhar em stories de schema/migration, verificar qual banco esta sendo afetado (local vs producao) e qual arvore de migrations usar. A unificacao das duas arvores e decisao arquitetural pendente com @architect.

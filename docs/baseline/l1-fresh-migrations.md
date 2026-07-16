# L1.3 — Fresh migrations (re-prova)

**Data:** 2026-07-16  
**HEAD base:** `5355292` + fix 049

## Resultado

| Cenário | Resultado |
|---------|-----------|
| Imagem | `pgvector/pgvector:pg16` (compose) |
| DB throwaway | `fresh_mig_test` |
| Extensions | `vector` OK; `postgis` N/A na imagem (migrations 54/54 ainda OK) |
| Migrations aplicadas | **54/54 OK** |

Capture: validação técnica `gate1-fresh-migrations.log`.

## Fix 049

Causa raiz do BLOCKED anterior:

1. Views dependiam de colunas em ALTER TYPE.
2. CHECK `esfera_id = ANY (ARRAY[1,2,3,4])` (integer) impedia ALTER para TEXT (`text = integer`).

Correção em `db/migrations/049_pncp_resumable_backfill.sql`:

- `DROP VIEW` das 3 views dependentes
- `DROP CONSTRAINT chk_pncp_raw_bids_esfera_id`
- `ALTER TYPE` para TEXT/TIMESTAMPTZ
- CHECK recriado com `ARRAY['1','2','3','4']::text[]`
- Views recriadas

Aplicado também no DB operacional `pncp_datalake` (tipos confirmados: esfera_id=text, datas=timestamptz).

---
name: qa-fix-COVERAGE-2.1-mides-bigquery
description: QA fixes applied — esfera_id derivado de CNPJ, AC6/AC7 validados com crawl BigQuery 50K, dedup pncp_id
metadata:
  type: project
---

# QA Fix: COVERAGE-2.1 MiDES BigQuery

**Data:** 2026-07-11
**Status:** Fixes applied, story em InReview

## O que foi feito

### MNT-001: esfera_id fix
- Criada funcao `_infer_esfera_from_cnpj()` que deriva `esfera_id` do primeiro digito do CNPJ (1=Federal, 2=Estadual, 3=Municipal)
- Fallback para 3 (Municipal) quando CNPJ indisponivel (dados filtrados por municipio SC)
- Removido hardcoded `"MUNICIPAL"` (string) que nao era compativel com CHECK constraint INT(1,2,3,4) no DB

### REQ-001 / REQ-002: AC6 + AC7 validados
- Crawl executado contra BigQuery real com limite de 50K registros
- Pipeline end-to-end: crawl -> transform -> upsert -> entity matching
- 50.000 registros persistidos em `pncp_raw_bids` com `source='mides_bigquery'`
- 225 registros pareados via CNPJ (entity matching Level 1)

### Descobertas durante a fix
- **pncp_id dedup**: Registros com `id_empenho_bd=NULL` compartilham o mesmo composite key. Adicionado contador `#N` para evitar violacao de UNIQUE no upsert.
- **module_map key**: monitor.py normaliza `mides-bigquery` para `mides_bigquery` (replace hyphen com underscore), mas o module_map tinha `"mides-bigquery"` como chave. Fix: usar `"mides_bigquery"` no map.
- **MIDES_CRAWL_LIMIT**: Adicionado env var para limitar registros via monitor.py (que nao passa `max_records` diretamente).

## Arquivos modificados

- `scripts/crawl/mides_bigquery_crawler.py`: `_infer_esfera_from_cnpj()`, dedup pncp_id, `max_records` crawler/fetch_year, env var
- `scripts/crawl/monitor.py`: Fix module_map key `mides_bigquery`
- `tests/test_mides_bigquery_crawler.py`: +11 tests (esfera + dedup)

## Lição aprendida
A fonte e armazenada no DB como `mides_bigquery` (underscore) devido a normalizacao do monitor.py, mas o nome original da fonte e `mides-bigquery` (hyphen). Qualquer query de report que filtre por source precisa usar o nome normalizado.

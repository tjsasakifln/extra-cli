# ADR-013: Coverage Truth — Entity-Level Evidence Ledger

**Data:** 2026-07-12
**Status:** Aceito
**Autor:** Coverage Truth MVP (commits a91ccfd, 0ee490b)
**Stakeholders:** Extra Consultoria

---

## Contexto

Antes do Coverage Truth, a cobertura era inferida indiretamente (existência de registros em `pncp_raw_bids`), sem registro auditável de QUANDO e COMO cada entidade foi investigada. Problemas:

1. Impossível distinguir "entidade investigada e sem licitações" de "entidade nunca investigada"
2. Falhas de crawl eram silenciosas — sem registro de que uma fonte falhou para uma entidade
3. Métricas de cobertura não eram defensáveis em auditoria

## Decisão

Criar tabela `coverage_evidence` como fonte única de verdade sobre cobertura:

- **Enum `evidence_state` com 10 valores:** `success_with_data`, `success_zero`, `partial`, `connection_failed`, `auth_failed`, `parse_failed`, `transform_failed`, `persist_failed`, `not_applicable`, `not_investigated`
- **Granularidade:** uma row por `(entity_id, source, data_type, run_id)`
- **Mapeamento determinístico:** `monitor_status + error_code → evidence_state`
- **Imutabilidade:** rows são INSERT-only (DELETE + INSERT no mesmo run_id para idempotência)
- **Partial unique indexes** para queries otimizadas de latest evidence

## Consequências

- Toda alegação de cobertura é rastreável a uma row em `coverage_evidence`
- Evidência negativa é tão valiosa quanto positiva: `success_zero` prova que a entidade foi investigada
- `not_investigated` é o default — elimina falsos positivos de cobertura
- Schema fingerprint + git SHA registrados em cada run para auditabilidade completa

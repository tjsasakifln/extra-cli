# Data Delta: Consolidação dos Módulos de Alta Confiança

> Feature: `001-modulos-alta-confianca`
> Data: 2026-07-14
> Roadmap: `_reversa_forward/001-modulos-alta-confianca/roadmap.md`
> Base: `_reversa_sdd/erd-complete.md` + migrations v3 (001-006)

## Resumo

Feature **não introduz novas tabelas ou migrations DDL**. Todas as mudanças no modelo de dados são:
- **Aditivas**: novo `event_type` no enum `evidence_state` (ou registro em `coverage_evidence` com type string)
- **Validação em camada de aplicação**: constraint `official_url` para PRIORITARIA (Python, não DDL)
- **Arquivos novos**: `.coveragerc` com seção `[coverage_gate]`, sem impacto em schema

## Novos campos e entidades

### coverage_evidence — Novo event_type

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `event_type` | `VARCHAR(64)` | Novo valor: `'snapshot_reconciled'` |
| `payload` | `JSONB` | `{"bids_inactivated": <int>, "bids_kept": <int>, "run_id": "<uuid>", "reconciled_at": "<ISO8601>"}` |

**Nota:** `event_type` é string livre em `coverage_evidence`, não um enum PostgreSQL. Basta usar o valor `'snapshot_reconciled'` na inserção.

### .coveragerc — Nova seção [coverage_gate]

```ini
[coverage_gate]
modules =
    scripts/opportunity_intel
    scripts/coverage
    scripts/contract_intel
    scripts/pipeline
    scripts/lib/universe.py
    scripts/lib/supplier_metrics.py
    scripts/lib/price_pipeline.py
    scripts/reports
threshold = 80
```

**Nota:** Esta seção é lida por `coverage_gate.py`, não pelo pytest. pytest-cov continua usando as seções `[run]` e `[report]` padrão.

## Campos removidos

> Nenhum.

## Migrações necessárias

> Nenhuma migration DDL. Nenhuma migration de dados.

### Justificativa para ausência de migrations

1. `snapshot_reconciled` como `event_type`: `coverage_evidence.event_type` é `VARCHAR`, não enum. Inserir com novo valor não requer ALTER TABLE.
2. `official_url` constraint: aplicada em Python (`ranking.py`), não em DDL. Evita bloqueio de registros legados que não teriam URL.
3. `.coveragerc`: arquivo de configuração, não schema.

## Impacto em entidades existentes

| Entidade (tabela/view) | Tipo de impacto | Descrição |
|-------------------------|-----------------|-----------|
| `coverage_evidence` | Novos registros | INSERT com `event_type='snapshot_reconciled'` após cada reconciliação |
| `opportunity_intel` | Nenhum (schema) | Triage alterado em Python (PRIORITARIA→REVISAR), não em DDL |
| `sc_public_entities` | Nenhum | Sem alteração |
| `pncp_raw_bids` | Nenhum | Sem alteração |

## Rastreabilidade com plano mestre

| Item do plano mestre | Impacto no modelo | Status |
|----------------------|-------------------|--------|
| P0-04 (reconciliação) | `coverage_evidence` novo event_type | Esta feature |
| P0-09 (competitive intel) | Nenhum — validação apenas | Feature separada |
| P1-04 (orquestração local) | Nenhum — infra, não dados | Esta feature |
| §18 (coverage gate) | `.coveragerc` nova seção | Esta feature |

## Histórico de alterações

| Data | Alteração | Autor |
|------|-----------|-------|
| 2026-07-14 | Versão inicial gerada por `/reversa-plan` | reversa |

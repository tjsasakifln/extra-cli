# Transition Plan: Cobertura Antiga -> Nova (Story 1.5)

## Resumo

Esta story implementa a **infraestrutura de medicao** do novo modelo de cobertura.
A transicao da cobertura antiga para a nova deve ser feita em paralelo por 1 sprint
para garantir que as metricas sejam consistentes antes de desativar a infra antiga.

## Timeline

| Fase | Periodo | Acao | Risco |
|------|---------|------|-------|
| 1 — Paralelo | Sprint atual + 1 | Ambas as metricas rodam simultaneamente | Duplicidade de dados |
| 2 — Validacao | Fim da Fase 1 | Comparar metricas antigas vs novas | Inconsistencias |
| 3 — Migracao | Apos validacao | Consumidores migram para novas metricas | Quebra de dependencias |
| 4 — Remocao | Apos migracao | Remover infra antiga (entity_coverage legacy views) | Perda de historico |

## O que muda

### Infraestrutura Antiga (conviver em paralelo)

| Componente | Localizacao | Status |
|-----------|-------------|--------|
| `entity_coverage` table | `db/migrations/020-021` | Mantida (consumidores existentes) |
| `report_coverage()` | `scripts/crawl/monitor.py` | Mantida (CLI `--report-coverage`) |
| `v_coverage_summary` | Migration 021 | Mantida (consumidores existentes) |
| `v_coverage_trend` | Migration 021 | Mantida |
| `v_entities_canonical.is_covered` | Migration 030 | Mantida (usada por intel_pipeline) |

### Infraestrutura Nova (adicionada por Story 1.5)

| Componente | Localizacao | Substitui? |
|-----------|-------------|-----------|
| `coverage_evidence` (expandida) | Migration 040 | Sim, entidade principal |
| `v_coverage_evidence_expanded` | Migration 040 | View de compatibilidade |
| `v_coverage_manifest` | Migration 040 | Sim, substitui `v_coverage_summary` |
| `mv_entity_source_applicability` | Migration 040 | Novo |
| `source_applicability_rules` | Migration 040 | Novo |
| `scripts/coverage/states.py` | Novo modulo | Motor de estados |
| `scripts/coverage/manifest.py` | Novo modulo | Geracao de manifest |
| `scripts/coverage/blockers.py` | Novo modulo | Blockers com acao |
| `scripts/matching/entity_matcher.py` | Expandido | TD-027 unificado |
| `config/source_applicability.yaml` | Novo config | Regras de decisao |
| `docs/dependencies/external-dependency-risk-matrix.yaml` | Novo | TD-033 |

## Dependencias entre components

```
source_applicability_rules (DB)
    └── mv_entity_source_applicability (materializada)
        └── coverage_evidence.applicability
            └── v_coverage_evidence_expanded
                └── v_coverage_manifest
                    └── scripts/coverage/manifest.py

coverage_evidence.state (enum expandido)
    └── scripts/coverage/states.py (estados + transicoes)

entity_matcher.py (unificado)
    └── monitor.py (importa, nao duplica)
    └── run_matching.py (importa)
    └── scrape_residual_portals.py (importa)
```

## Gatilhos de migracao para consumidores

### Consumidor 1: `consulting_readiness.py`

**Atual:** Usa `v_entities_canonical.is_covered`

**Novo:** Deve usar `v_coverage_manifest` + `mv_entity_source_applicability`

**Quando migrar:** Fase 3 (apos validacao)

**Script de migracao:**
```python
# Antes
from scripts.crawl.monitor import report_coverage

# Depois
from scripts.coverage.manifest import build_manifest_from_db
manifest = build_manifest_from_db(conn)
print(manifest.to_markdown())
```

### Consumidor 2: `coverage_truth.py`

**Atual:** Usa `coverage_evidence` diretamente

**Novo:** Pode usar `v_coverage_evidence_expanded` para acesso aos novos campos

**Quando migrar:** Fase 2 (imediatamente, view e retrocompativel)

### Consumidor 3: CLI `monitor.py --report-coverage`

**Atual:** `report_coverage()` em monitor.py

**Novo:** `python -m scripts.coverage.manifest` (a ser criado como CLI)

**Quando migrar:** Fase 3

## Dados de transicao

Para preencher a matriz de aplicabilidade com dados reais:

```sql
-- Preencher aplicabilidade inicial a partir das regras
UPDATE coverage_evidence ce
SET
    applicability = m.is_applicable::TEXT,
    applicability_reason = m.reason
FROM mv_entity_source_applicability m
WHERE ce.entity_id = m.entity_id
  AND ce.source = m.source;
```

## Variaveis de feature flag

Nenhuma feature flag implementada. A convivencia e garantida por:
1. Manter tabelas/views antigas intactas
2. Nomes diferentes para os novos componentes (prefixo `v_coverage_manifest` vs `v_coverage_summary`)
3. Testes de equivalencia que comparam metricas antigas vs novas

## Testes de equivalencia

Antes de ativar as novas metricas como fonte primaria:

```python
# Teste de equivalencia: mesma consulta, mesma resposta
old_cov = report_coverage(conn)["pct"]
new_cov = build_manifest_from_db(conn).capability_monitoring_coverage_pct
assert abs(old_cov - new_cov) < 5.0, (
    f"Discrepancia > 5%: old={old_cov}%, new={new_cov}%"
)
```

## Rollback

Se as novas metricas apresentarem problemas:

1. **Migration rollback:** Reverter migration 040 (comandos no final do arquivo SQL)
2. **Registry rollback:** Reverter `scripts/crawl/registry.py` para versao anterior (git checkout)
3. **Entity matching:** monitor.py continuara importando de entity_matcher.py — a interface publica e identica

## Riscos da transicao (R5)

| Risco | Probabilidade | Impacto | Mitigacao |
|-------|--------------|---------|-----------|
| Duplicidade de metricas confunde usuarios | MEDIA | ALTO | Documentacao clara; manter ambas por 1 sprint maximo |
| Consumidores nao migram a tempo | BAIXA | MEDIO | Comunicacao proativa; deprecation warning 2 semanas antes |
| Novas metricas divergem das antigas | MEDIA | ALTO | Teste de equivalencia antes de remover metricas antigas |

## Checklist de migracao

- [ ] Fase 1: Migration 040 aplicada em producao
- [ ] Fase 1: Registry expandido deployado
- [ ] Fase 1: Testes de estado passando
- [ ] Fase 1: Todas as fontes com aplicabilidade decidida na config
- [ ] Fase 2: Comparacao old vs new < 5% de diferenca
- [ ] Fase 2: Consumidor coverage_truth.py migrado
- [ ] Fase 3: Consumidor consulting_readiness.py migrado
- [ ] Fase 3: CLI coverage manifest criada
- [ ] Fase 4: Views antigas removidas
- [ ] Fase 4: entity_coverage table removida (se sem consumidores)

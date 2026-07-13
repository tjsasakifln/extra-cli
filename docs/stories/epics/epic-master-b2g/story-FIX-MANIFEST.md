---
epic: EPIC-MASTER-B2G-READINESS
story_id: FIX-MANIFEST
title: "Corrigir manifest.py para cobertura realista (265.95% -> correto)"
status: ready
priority: P0
effort: M
agent: @dev
depends_on: [FIX-UNIVERSE]
---

# Story FIX-MANIFEST: Corrigir manifest.py para Cobertura Realista

## Problem Statement

O arquivo `opportunity-coverage-manifest.json` gerado por `manifest.py` reporta:

- **Cobertura: 265.95%** — um valor matematicamente impossivel
- **entities_with_data: 3.851** — mais entes que o universo total de Santa Catarina
- **entities_without_data: -2.403** — valor negativo
- **Universo declarado: 1.448** — nao corresponde ao canonico 1.093

**Isso viola as Regras Nao-Negociaveis #1 (definicao canonica do universo) e #2 (separar cobertura observacional de presenca de dados).**

**Root cause:** A funcao `_build_manifest()` em `manifest.py` executa query `entities_with_data` SEM filtrar `raio_200km = TRUE`, contando entes de TODO o estado de Santa Catarina (3.851). Ao subtrair do universo declarado (1.448), obtem -2.403. A divisao 3.851/1.448 produz 265.95%.

**Contradicoes documentadas na auditoria:**

| Contradicao | Valor Errado | Valor Correto |
|------------|-------------|---------------|
| total_entities | 1.448 | 1.093 |
| entities_with_data | 3.851 | ~1.093 (max) |
| entities_without_data | -2.403 | 0 |
| pct_coverage | 265.95% | 0-100% |
| source_health entity_rows | 631-1.445 | 0 (fontes bloqueadas) |
| test_batch | 5 registros | 0 (excluir de producao) |

## Acceptance Criteria

- [ ] **AC1: Query `entities_with_data` corrigida** — Adicionar filtro `WHERE raio_200km = TRUE` na query que conta entes com dados. Numerador nunca excede o denominador.
- [ ] **AC2: Universo usa `scripts.lib.universe`** — `manifest.py` importa `CANONICAL_UNIVERSE` e/ou `get_canonical_universe()` do modulo `scripts.lib.universe` (Story FIX-UNIVERSE) em vez de valor hardcoded ou query propria
- [ ] **AC3: Cobertura entre 0 e 100%** — Apos correcao, `pct_coverage` e sempre um float entre 0.0 e 100.0. Teste automatico valida este contrato.
- [ ] **AC4: Denominador = 1.093** — Teste valida que `total_entities` no manifesto gerado e sempre 1.093 (ou valor retornado por `get_canonical_universe()`)
- [ ] **AC5: Numerador entre 0 e denominador** — Teste valida que `entities_with_data` esta sempre entre 0 e `total_entities`
- [ ] **AC6: Metricas separadas** — Cobertura observacional (monitoring coverage) e separada de presenca de dados (data presence). O manifesto expoe ambas como metricas distintas.
- [ ] **AC7: `test_batch` excluido** — Dados de producao filtram `source != 'test_batch'` para evitar contaminacao por registros de teste
- [ ] **AC8: Source health realista** — Fontes sem acesso (`dom_sc`, `pcp`, `compras_gov`, etc.) sao reportadas como `BLOCKED` ou `NOT_APPLICABLE`, nao como `100% success`
- [ ] **AC9: Ruff check** — `ruff check scripts/manifest.py` retorna 0 erros
- [ ] **AC10: Testes passam** — `pytest tests/test_manifest.py -v` retorna all passed

## Technical Design

### Correcao principal em `manifest.py:_build_manifest()`

A query atual (simplificada):
```sql
SELECT COUNT(DISTINCT e.entity_id)
FROM sc_public_entities e
JOIN entity_coverage ec ON e.entity_id = ec.entity_id
```

Deve passar a ser:
```sql
SELECT COUNT(DISTINCT e.entity_id)
FROM sc_public_entities e
JOIN entity_coverage ec ON e.entity_id = ec.entity_id
WHERE e.raio_200km = TRUE
  AND ec.source != 'test_batch'
```

### Separação de metricas

No manifesto JSON, criar duas secoes distintas:

```json
{
  "universe": {
    "canonical_total": 1093,
    "denominator_source": "scripts.lib.universe.CANONICAL_UNIVERSE"
  },
  "monitoring_coverage": {
    "entities_monitored": 1093,
    "pct_coverage": 100.0,
    "description": "Entes com monitoramento ativo (qualquer fonte)"
  },
  "data_presence": {
    "entities_with_data": 488,
    "pct_with_data": 44.6,
    "description": "Entes com dados persistidos (pelo menos uma fonte com dados reais)"
  }
}
```

### Source health

Para cada fonte sem acesso via API real, substituir:
```python
# Antes (incorreto):
{"source": "dom_sc", "entity_rows": 1445, "success": "100%"}

# Depois (correto):
{"source": "dom_sc", "status": "BLOCKED", "reason": "API key required from CIGA"}
```

### Tratamento de excecoes

Substituir `except Exception` generalizados por tipos especificos (ex: `except (DatabaseError, TimeoutError)`) com logging adequado, seguindo as correcoes da Regra #6.

### Arquivos a modificar

- `scripts/manifest.py` — Correcao principal
- `scripts/opportunity_intel/manifest.py` — Mesma correcao se aplicavel
- `tests/test_manifest.py` — Novos testes

### Testes

| Teste | Descricao |
|-------|-----------|
| `test_coverage_between_0_and_100` | `pct_coverage` esta entre 0.0 e 100.0 |
| `test_denominator_is_1093` | `total_entities` == `CANONICAL_UNIVERSE` |
| `test_numerator_within_bounds` | `entities_with_data` entre 0 e `total_entities` |
| `test_no_negative_entities` | Nenhuma contagem e negativa |
| `test_no_test_batch_in_production` | Nenhum registro com `source = 'test_batch'` |
| `test_monitoring_vs_data_presence_separated` | Ambas as metricas existem e sao distintas |
| `test_source_health_blocked` | Fontes bloqueadas tem status correto |
| `test_manifest_generation_succeeds` | `_build_manifest()` executa sem excecao |

## File List

- **MODIFY** `scripts/manifest.py`
- **MODIFY** `scripts/opportunity_intel/manifest.py`
- **MODIFY** `tests/test_manifest.py`

## Dependencies

- **FIX-UNIVERSE** — Deve ser implementada primeiro, pois FIX-MANIFEST depende de `scripts.lib.universe`

## Security Considerations

- `test_batch` filtering evita contaminacao de metricas de producao com dados de teste
- Sem autenticacao adicional — apenas queries ao banco PostgreSQL local

## Tests

- `tests/test_manifest.py` — conforme tabela acima (AC3-AC5, AC7-AC8)
- `ruff check scripts/manifest.py` — 0 erros
- Validacao manual: executar `_build_manifest()` e comparar valores com auditoria Fase 0

## Definition of Done

- [ ] Codigo implementado (AC1-AC8)
- [ ] ruff check passa em scripts/manifest.py
- [ ] mypy passa (scoped) em scripts/manifest.py
- [ ] Testes unitarios passam (`pytest tests/test_manifest.py -v`)
- [ ] Testes de integracao passam (manifesto gerado contra banco real)
- [ ] Manifesto gerado mostra cobertura entre 0-100% (confirmado) 
- [ ] QA gate PASS

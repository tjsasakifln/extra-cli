# ADR-008: Refatoração monitor.py → orchestrator.py + Módulo Matching

**Status:** ✅ Implementado
**Data:** 2026-07-11
**Epic:** EPIC-TD-001 / Story TD-3.1
**Commit:** `e9729e1`

## Contexto

`monitor.py` havia crescido para 701 linhas com responsabilidades sobrepostas:
- Orquestração de 8 crawlers
- Entity matching cascade inline (3 níveis)
- Coverage reporting
- CLI argument parsing

O código de entity matching estava acoplado ao orquestrador, impedindo reuso por outros componentes e dificultando testes isolados.

## Decisão

**Extrair 3 responsabilidades de `monitor.py` em módulos independentes (SRP):**

1. **`orchestrator.py` (306 linhas):** Orquestrador puro — carrega crawlers, coordena pipeline crawl→transform→upsert→match, gerencia checkpoints. Delega entity matching para módulo externo.

2. **`matching/entity_matcher.py` (297 linhas):** Módulo dedicado de entity matching com cascade 3 níveis. Independente do orquestrador, testável isoladamente.

3. **`monitor.py` mantido (684→187 linhas?):** O código foi refatorado mas o arquivo legado permanece como fallback. A intenção é eventualmente deprecar `monitor.py` em favor de `orchestrator.py`.

## Evidência

🟢 CONFIRMADO — `orchestrator.py:1-306` implementa `crawl_source()` com checkpoint TD-5.2.
🟢 CONFIRMADO — `matching/entity_matcher.py:1-297` implementa `match_entities_cascade()` com 3 índices in-memory.
🟡 INFERIDO — `monitor.py` ainda existe com a implementação original. Coexistência indica transição em andamento, não concluída.

## Alternativas Consideradas

- **Manter tudo em monitor.py:** Rejeitado — viola SRP, dificulta teste e manutenção.
- **Migrar para arquitetura de plugins:** Rejeitado — complexidade desnecessária para 8 crawlers.
- **Eliminar monitor.py imediatamente:** Rejeitado — risco de regressão. Abordagem de transição gradual (strangler fig pattern).

## Consequências

- **Positivo:** Entity matching é testável isoladamente (test_entity_matcher.py, 402 linhas).
- **Positivo:** orchestrator.py introduz checkpoint TD-5.2, ausente no monitor.py legado.
- **Negativo:** Dois orquestradores coexistem. Sistema precisa decidir qual é canônico.
- **Risco:** Se `monitor.py` continuar sendo usado em produção, os benefícios do refactor não se materializam.

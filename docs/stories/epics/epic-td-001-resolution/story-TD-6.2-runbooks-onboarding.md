# Story TD-6.2: Runbooks e Onboarding

**Status:** Done
**Epic:** EPIC-TD-001
**Executor:** @dev
**Quality Gate:** @architect
**Quality Gate Tools:** [coderabbit, pytest]
**Fase:** 6 -- Documentacao
**Estimativa:** 3 horas
**Prioridade:** P2

## Description

Resolver o debito de estado global mutavel no cache IBGE (TD-SYS-004) e completar a documentacao de onboarding.

O cache IBGE em `enricher.py:483-484` e implementado como variavel module-level, o que causa race condition em contexto async (conforme identificado pelo QA e confirmado pelo arquiteto). Refatorar para usar uma instancia de cache encapsulada em classe.

Adicionalmente, criar guia de onboarding para novos desenvolvedores, com roteiro de aprendizado, conceitos chave do dominio de licitacoes, e links para documentacao relevante.

## Business Value

O cache IBGE module-level causa race condition em contexto async, podendo produzir dados inconsistentes em cenarios de concorrencia. A gravidade foi elevada para HIGH pelo arquiteto devido ao impacto em operacoes concorrentes. O guia de onboarding reduz o tempo de produtividade de novos desenvolvedores, contextualizando o dominio de licitacoes publicas e mapeando a documentacao existente.

## Acceptance Criteria

- [x] AC1: Dado o cache IBGE em `enricher.py:483-484`, Quando refatorado para uma classe, Entao o estado do cache nao e mais module-level e sim encapsulado em uma instancia de classe
- [x] AC2: Dado a nova classe de cache, Quando acessada concorrentemente por multiplas threads/async tasks, Entao o acesso e thread-safe (via `asyncio.Lock`)
- [x] AC3: Dado a nova implementacao do cache, Quando testada, Entao o comportamento funcional e identico ao anterior (mesma logica de expiracao e armazenamento)
- [x] AC4: Dado que a refatoracao foi concluida, Quando os testes do cache sao executados, Entao todos passam incluindo cenario de acesso concorrente
- [x] AC5: Dado o guia de onboarding em `docs/ops/onboarding.md`, Quando lido por um novo desenvolvedor, Entao ele contem: visao geral do sistema e conceitos, primeiros passos (setup, primeiro crawl, resultados esperados), explicacao do dominio de licitacoes (orgaos, modalidades, fases), e referencias para documentacao detalhada (runbook, troubleshooting, arquitetura)

## Scope

### IN
- Refatoracao do cache IBGE (module-level para classe)
- Guia de onboarding para novos devs

### OUT
- Testes de integracao para o cache
- Documentacao de codigo alem do necessario para onboarding

## Dependencies

- Bloqueado por: TD-6.1 (documentacao operacional como pre-requisito para onboarding coerente)
- Bloqueia: NONE

## Risks

| Risco | Probabilidade | Impacto | Mitigacao |
|-------|---------------|---------|-----------|
| Refatoracao do cache quebra funcionalidade existente | MEDIA | ALTO | Testes comportamentais antes e depois; coverage do cenario de uso real |
| Thread-safety adiciona overhead de performance | BAIXA | BAIXO | Usar Lock de granulosidade fina (por chave) em vez de lock global |
| Onboarding muito extenso ou desatualizado rapidamente | MEDIA | BAIXO | Manter conciso; secoes curtas com links para docs detalhadas |
| Race condition nao reproduzivel em testes | BAIXA | MEDIO | Usar stress test com multiplas threads concorrentes |

## Technical Notes

Referencia ao assessment: TD-SYS-004 (HIGH) -- Estado global mutavel (cache IBGE module-level) -- 3h
- Decisao do arquiteto: severidade elevada para HIGH porque QA identificou race condition com async Semaphore
- Solucao: encapsular cache em classe com metodo get_or_fetch()
- Sugestao: usar `threading.Lock` para acesso concorrente seguro
- Onboarding deve contextualizar o dominio de licitacoes publicas

## Definition of Done

- [x] Cache IBGE refatorado para classe thread-safe
- [x] Testes do cache passando
- [x] Comportamento funcionalmente identico
- [x] Guia de onboarding criado

## File List

- `scripts/crawl/enricher.py` (modificado -- cache IBGE refatorado para classe)
- `tests/test_cache_ibge.py` (novo -- 20 testes do cache IBGE)
- `docs/ops/onboarding.md` (novo -- guia de onboarding)
- `docs/ops/troubleshooting.md` (modificado -- secao de cache IBGE adicionada)
- `CLAUDE.md` (modificado -- comandos frequentes adicionados)

## QA Results

### Review Date: 2026-07-11

### Reviewed By: Quinn (Guardian)

### 7 Quality Checks

| Check | Result | Details |
|-------|--------|---------|
| 1. Code Review | PASS | Classe `_IBGEMunicipioCache` bem estruturada, double-check locking, fallback gracioso, `asyncio.Lock` correto para contexto async |
| 2. Unit Tests | PASS | 20/20 tests passing (init, freshness, get_or_fetch, concorrencia, singleton) em 8.48s |
| 3. Acceptance Criteria | PASS | AC1-AC5 todos implementados: cache encapsulado, thread-safe, funcionalmente identico, testes passando, onboarding completo |
| 4. No Regressions | PASS | 51/51 tests passando (test_transformer + test_cache_ibge); erro pre-existente em test_checkpoint.py (supabase_client ausente) |
| 5. Performance | PASS | asyncio.Lock nao bloqueia event loop; double-check com fast path para cache quente; TTL 7 dias adequado |
| 6. Security | PASS | Nenhum codigo sensivel modificado; sem novos imports de risco; fallback gracioso em falha de API |
| 7. Documentation | PASS | Onboarding completo (visao geral, dominio, setup, estrutura, crawlers, contribuicao); troubleshooting atualizado com secao cache IBGE |

### Issues

| ID | Severity | Category | Description | Recommendation |
|----|----------|----------|-------------|----------------|
| MNT-001 | low | docs | File List descreve CLAUDE.md como "modificado", mas e novo (untracked) | Atualizar File List para "(novo -- comandos frequentes adicionados)" |

### Gate Status

Gate: PASS -> docs/qa/gates/td-6.2-runbooks-e-onboarding-gate.yaml

## Change Log

| Data | Mudanca | Autor |
|------|---------|-------|
| 2026-07-11 | Story criada | @pm |
| 2026-07-11 | Validated GO (10/10) — adicionado Business Value, Risks, Executor, QG, Prioridade; ACs convertidas para Given/When/Then | @po |
| 2026-07-11 | Implementado: cache IBGE refatorado (classe _IBGEMunicipioCache com asyncio.Lock), 20 testes, onboarding, troubleshooting, CLAUDE.md | @dev |
| 2026-07-11 | 1.0.0 | QA Gate PASS -- Status: InReview -> Done -- 7/7 checks, 1 low issue (MNT-001) | @qa |

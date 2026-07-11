# Story TD-4.4: Corrigir Suite de Testes (14 falhas + 1 collection error)

## Community Origin

_Not applicable — internally-planned technical debt story._

---

## Status

Done

---

## Executor Assignment

executor: "@dev"
quality_gate: "@qa"
quality_gate_tools: ["pytest", "ruff"]

---

## Story

**As a** desenvolvedor mantenedor da Extra Consultoria,
**I want** corrigir as 14 falhas de teste e 1 erro de importacao na suite existente,
**so that** `pytest` retorne verde completo antes de expandir a cobertura (TD-4.1) e validar o CI/CD pipeline (TD-4.2).

---

## Acceptance Criteria

1. `pytest tests/test_compras_gov_crawler.py -v` passa com 0 falhas (2 testes corrigidos)
2. `pytest tests/test_transparencia_crawler.py -v` passa com 0 falhas (8 testes corrigidos + 4 testes de config corrigidos)
3. `pytest tests/test_cache_ibge.py -v` carrega e passa com 0 falhas (1 erro de importacao + ~15 testes corrigidos)
4. `pytest tests/ -v` retorna codigo de saida 0 com todas as suites existentes verdes (incluindo `test_transformer.py`, `test_enricher.py`, etc.)
5. Nenhuma alteracao no codigo de producao que mude comportamento funcional — apenas ajustes para manter compatibilidade com contratos existentes ou correcao de referencias

---

## Root Cause Analysis

### Grupo A: `test_compras_gov_crawler.py` — 2 falhas (KeyError: `source_id`)

| Teste | Erro | Causa Raiz |
|-------|------|------------|
| `test_transform_mock_legacy_record` | `KeyError: 'source_id'` | `_normalize_legacy()` (linha 388 do crawler) retorna dict sem campo `source_id`. O nome do orgao alimenta `pncp_id` com prefixo `cg_leg_`, mas `source_id` nunca foi adicionado ao dicionario de retorno — o `source_id` e usado como `variavel local` (linha 334) para montar o `pncp_id` mas nao e propagado ao output. |
| `test_transform_mock_14133_record` | `KeyError: 'source_id'` | Mesma causa: `_normalize_lei_14133()` (linha 419) usa `source_id` como variavel local para montar `pncp_id` mas nao inclui no retorno. |

**Arquivos afetados:**
- `scripts/crawl/compras_gov_crawler.py` (funcoes `_normalize_legacy`, `_normalize_lei_14133`)

### Grupo B: `test_transparencia_crawler.py` — 8 falhas de transform + 4 falhas de config

| Teste | Erro | Causa Raiz |
|-------|------|------------|
| `test_detect_platform_from_url` | `AttributeError` — module has no `_detect_platform_from_url` | A funcao `_detect_platform_from_url()` foi removida durante refatoracao do `detect_platform()` (linha 223). A logica de deteccao por URL agora e feita internamente dentro `detect_platform()` via `_PLATFORM_TEMPLATES`. O teste referencia uma funcao que nao existe mais. |
| `test_with_subtype_betha` | `KeyError: 'source'` | `transform()` (linha 1037-1050) produz dict **sem os campos** `source` e `source_subtype`. O campo `source` foi removido do output; `source_subtype` (derivado de `_source_subtype` dos sub-records) nao e propagado para o registro normalizado. |
| `test_with_subtype_ipam` | `KeyError: 'source_subtype'` | Mesma causa: output do `transform()` nao inclui `source_subtype`. |
| `test_with_subtype_egov` | `KeyError: 'source_subtype'` | Mesma causa. |
| `test_with_subtype_generico` | `KeyError: 'source_subtype'` | Mesma causa. |
| `test_multiple_records_in_one_municipio` | `KeyError: 'source_subtype'` | Mesma causa. |
| `test_12_municipios` | Config vazio — 0 municipios (esperado 12) | `config/transparencia_config.yaml` foi criado com `municipios: {}` (linha 51) — nunca populado com os 12 municipios mapeados. O `load_config()` retorna fielmente o que esta no YAML, que e um dicionario vazio. |
| `test_betha_municipios_present` | Config vazio | Mesma causa. |
| `test_ipam_municipios_present` | Config vazio | Mesma causa. |
| `test_egov_municipios_present` | Config vazio | Mesma causa. |
| `test_custom_municipios_present` | Config vazio | Mesma causa. |
| `test_custom_selectors_defined` | Config vazio | Mesma causa. |

**Arquivos afetados:**
- `scripts/crawl/transparencia_crawler.py` (funcoes `transform()`, remocao de `_detect_platform_from_url`)
- `config/transparencia_config.yaml` (populacao do bloco `municipios:`)

### Grupo C: `test_cache_ibge.py` — 1 collection error (ImportError)

| Erro | Causa Raiz |
|------|------------|
| `ImportError: cannot import name '_ibge_cache' from 'scripts.crawl.enricher'` | O modulo `enricher.py` foi refatorado: a classe `_IBGEMunicipioCache` e a instancia `_ibge_cache` foram substituidas por variaveis de modulo (`_IBGE_MUNICIPIOS_CACHE: dict`, `_IBGE_MUNICIPIOS_CACHE_TS: float`, linha 472-473). O arquivo de teste `test_cache_ibge.py` importa nomes que nao existem mais e precisa ser reescrito para testar o novo design baseado em dicionario com TTL. |

**Arquivos afetados:**
- `tests/test_cache_ibge.py` (reescrita completa)
- `scripts/crawl/enricher.py` (caso `_ibge_cache` precise de alias de compatibilidade)

---

## Technical Notes

### Grupo A — Estrategia de correcao

Opcao 1 (recomendada): adicionar `source_id` ao dict de retorno em ambas as funcoes `_normalize_legacy` e `_normalize_lei_14133`.

- Em `_normalize_legacy`: adicionar `"source_id": f"cg_leg_{source_id}"` ao dict result (linha 388)
- Em `_normalize_lei_14133`: adicionar `"source_id": f"cg_14133_{source_id}"` ao dict result

Isso mantem compatibilidade retroativa com os testes existentes e nao quebra consumidores que esperam o campo.

Opcao 2: Remover `source_id` dos testes. Menos recomendada porque o campo `source_id` e semanticamente util para rastreamento de origem do registro.

### Grupo B — Estrategia de correcao

**Subgrupo B1 (`_detect_platform_from_url`)**:
- Restaurar a funcao `_detect_platform_from_url()` como wrapper que extrai a logica de deteccao das `_PLATFORM_TEMPLATES` (linha 190-206)
- Alternativa: reescrever o teste para usar `detect_platform()` com mock de `_fetch_url`

**Subgrupo B2 (`source`, `source_subtype`)**:
- Adicionar `"source": "transparencia"` ao dict produzido por `transform()` (linha 1037)
- Adicionar `"source_subtype": r.get("_source_subtype", "")` ao dict, propagando o campo que os sub-records ja carregam

**Subgrupo B3 (config vazio)**:
- Popular `config/transparencia_config.yaml` com os 12 municipios mapeados. Dados necessarios por municipio: `ibge` (7 digitos), `portal_url`, `template`, e opcionalmente `selectors`.
- Os 12 municipios sao: chapeco, sao-jose, blumenau (Betha/portal_transparencia_net), itajai, criciuma, lages (Ipam), florianopolis, joinville, balneario-camboriu (E-gov/e_gov_net), tubarao, brusque, rio-do-sul (Custom).

### Grupo C — Estrategia de correcao

- Reescrever `test_cache_ibge.py` para testar o novo design baseado em `_IBGE_MUNICIPIOS_CACHE` (dict) + funcao `_fetch_ibge_municipio_lookup()` com TTL, fallback a stale cache, e concorrencia.
- Se desejado, adicionar alias de compatibilidade em `enricher.py`:
  ```python
  _ibge_cache = _IBGE_MUNICIPIOS_CACHE  # compat alias (apenas para referencia direta)
  ```
  (Nota: a instancia `_ibge_cache` era um objeto `_IBGEMunicipioCache` com metodos; o alias de dict nao teria os mesmos metodos — melhor reescrever os testes.)

---

## CodeRabbit Integration

> **CodeRabbit Integration**: Enabled
>
> CodeRabbit CLI is configured in `core-config.yaml` with self-healing enabled.

### Story Type Analysis

**Primary Type**: Bug Fix (Test Repair)
**Secondary Type(s)**: Refactor (compatibility)
**Complexity**: Medium (3 grupos independentes, 4 arquivos fonte, 2 arquivos de config)

### Specialized Agent Assignment

**Primary Agents**:
- @dev (pre-commit reviews, implementation)

**Supporting Agents**:
- @qa (post-implementation validation gate)

### Quality Gate Tasks

- [ ] Pre-Commit (@dev): Run `coderabbit --prompt-only -t uncommitted` before marking story complete
- [ ] Pre-PR (@devops): Run `coderabbit --prompt-only --base main` before creating pull request

### Self-Healing Configuration

**Expected Self-Healing**:
- Primary Agent: @dev (light mode)
- Max Iterations: 2
- Timeout: 30 minutes
- Severity Filter: CRITICAL, HIGH

**Predicted Behavior**:
- CRITICAL issues: auto_fix (up to 2 iterations)
- HIGH issues: auto_fix (iteration < 2) else document_as_debt
- MEDIUM issues: document_as_debt
- LOW issues: ignore

### CodeRabbit Focus Areas

**Primary Focus**:
- Regression risk: alteracoes em funcoes de producao (`_normalize_legacy`, `_normalize_lei_14133`, `transform()`) nao devem quebrar consumidores existentes
- Compatibilidade de contratos: campos adicionados ao schema de output (`source_id`, `source`, `source_subtype`) devem seguir o padrao `pncp_raw_bids`

**Secondary Focus**:
- Nomes de exports: verificar se `_ibge_cache` como alias de compatibilidade nao conflita com outros imports
- Config YAML: validar estrutura do YAML populado

---

## Dependencies

- Pre-requisito: TD-4.1 (Expandir cobertura de testes) — nao e bloqueante, mas a ordem logica e corrigir testes existentes antes de adicionar novos
- Dependencia informacional: conhecimento dos schemas de output de `transform()` em `compras_gov_crawler.py` e `transparencia_crawler.py`
- O CI/CD pipeline (TD-4.2) requer que esta suite esteja verde

---

## Tasks / Subtasks

- [x] Task 1: Corrigir `test_compras_gov_crawler.py` — adicionar `source_id` ao output de `_normalize_legacy` e `_normalize_lei_14133` (AC: 1)
  - [x] 1.1 Adicionar `"source_id": f"cg_leg_{source_id}"` no dict de retorno de `_normalize_legacy`
  - [x] 1.2 Adicionar `"source_id": f"cg_14133_{source_id}"` no dict de retorno de `_normalize_lei_14133`
  - [x] 1.3 Rodar `pytest tests/test_compras_gov_crawler.py -v` e validar 0 falhas

- [x] Task 2: Corrigir `test_transparencia_crawler.py` — funcoes removidas (AC: 2)
  - [x] 2.1 Decidir abordagem: restaurar `_detect_platform_from_url` OU reescrever teste para usar `detect_platform` com mock
  - [x] 2.2 Implementar correcao e rodar `pytest tests/test_transparencia_crawler.py::TestDetectPlatform::test_detect_platform_from_url -v`

- [x] Task 3: Corrigir `test_transparencia_crawler.py` — `source` e `source_subtype` faltantes (AC: 2)
  - [x] 3.1 Adicionar `"source": "transparencia"` ao dict de output em `transform()` (linha 1037)
  - [x] 3.2 Adicionar `"source_subtype": r.get("_source_subtype", "")` ao dict
  - [x] 3.3 Rodar `pytest tests/test_transparencia_crawler.py::TestTransform -v`

- [x] Task 4: Corrigir `test_transparencia_crawler.py` — config vazio (AC: 2)
  - [x] 4.1 Levantar os 12 municipios com dados de portal, template e IBGE da documentacao do projeto ou de fonte confiavel
  - [x] 4.2 Popular `config/transparencia_config.yaml` bloco `municipios:` com os 12 municipios e seus dados
  - [x] 4.3 Rodar `pytest tests/test_transparencia_crawler.py::TestLoadConfig -v`

- [x] Task 5: Corrigir `test_cache_ibge.py` — ImportError e reescrita (AC: 3)
  - [x] 5.1 Analisar o contrato atual de `enricher.py` (variaveis `_IBGE_MUNICIPIOS_CACHE`, funcao `_fetch_ibge_municipio_lookup`)
  - [x] 5.2 Reescrever `test_cache_ibge.py` para testar o novo design (cache TTL, fallback, _is_fresh equivalente)
  - [x] 5.3 Rodar `pytest tests/test_cache_ibge.py -v`

- [x] Task 6: Validacao completa da suite (AC: 4)
  - [x] 6.1 Rodar `pytest tests/ -v` e verificar codigo de saida 0
  - [x] 6.2 Registrar resultados e garantir que nenhum teste existente foi quebrado pelas alteracoes

---

## Dev Notes

### Estrutura de diretorios relevante

```
scripts/
  crawl/
    compras_gov_crawler.py          # Grupo A: funcoes _normalize_legacy, _normalize_lei_14133
    transparencia_crawler.py         # Grupo B: funcoes transform(), detect_platform(), load_config()
    enricher.py                      # Grupo C: modulo refatorado sem classe _IBGEMunicipioCache
tests/
    test_compras_gov_crawler.py      # Grupo A: TestTransform
    test_transparencia_crawler.py    # Grupo B: TestDetectPlatform, TestTransform, TestLoadConfig
    test_cache_ibge.py               # Grupo C: todo o arquivo (collection error)
config/
    transparencia_config.yaml        # Grupo B3: config com municipios {}
```

### Testes existentes (para nao quebrar)

Os seguintes arquivos de teste nao devem ser afetados pelas correcoes. Rodar no final para confirmar:
- `tests/test_transformer.py` (ja verde — testa `scripts/crawl/transformer.py`)
- `tests/test_pcp_crawler.py`
- `tests/test_contracts_crawler.py`
- `tests/test_monitor.py`
- `tests/test_enricher.py`

### Convencao: output schema de `transform()`

Todas as funcoes `transform()` nos crawlers seguem o schema `pncp_raw_bids`. Campos padrao:
```
pncp_id, objeto_compra, valor_total_estimado, modalidade_id, modalidade_nome,
esfera_id, uf, municipio, codigo_municipio_ibge, orgao_razao_social, orgao_cnpj,
data_publicacao, data_abertura, data_encerramento, link_pncp, content_hash, source_id
```

O campo `source_id` e utilizado para rastrear a origem exata do registro no sistema de origem (ex: `cg_leg_20230001`, `transparencia_chapeco`).

---

## Testing

- **Framework**: pytest com pytest-asyncio para testes async (`pytest.mark.asyncio`)
- **Mocking**: `unittest.mock.patch` para HTTP e IO
- **Cobertura**: todos os testes no escopo desta story devem passar individualmente e em suite completa
- **Comando**: `pytest tests/ -v` — codigo de saida 0 obrigatorio

---

## Change Log

| Date | Version | Description | Author |
|------|---------|-------------|--------|
| 2026-07-11 | 1.0 | Criacao inicial da story | @sm (River) |
| 2026-07-11 | 1.1 | Validated GO (9/10) — Status: Draft → Ready | @po (Pax) |
| 2026-07-11 | 1.2 | Development started (YOLO mode) — Status: Ready → InProgress | @dev |
| 2026-07-11 | 1.3 | Development complete -- Status: InProgress → InReview | @dev |
| 2026-07-11 | 1.4 | QA Gate PASS — Status: InReview → Done | @qa (Quinn) |

---

## QA Gate Report

**Reviewed by:** @qa (Quinn)
**Date:** 2026-07-11
**Verdict:** PASS

### AC Verification

| AC | Description | Result | Evidence |
|----|-------------|--------|----------|
| 1 | `test_compras_gov_crawler.py` 0 falhas | PASS | 6/6 tests passed. `source_id` presente em `_normalize_legacy` (line 404) e `_normalize_lei_14133` (line 506) |
| 2 | `test_transparencia_crawler.py` 0 falhas | PASS | 87/87 tests passed. `_detect_platform_from_url` restaurada (line 223). `source`/`source_subtype` em `transform()` (lines 1080-1086). 12 municipios populados no YAML |
| 3 | `test_cache_ibge.py` 0 falhas | PASS | 10/10 tests passed. Testes reescritos para API `_IBGE_MUNICIPIOS_CACHE`/`_fetch_ibge_municipio_lookup` |
| 4 | `pytest tests/` exit code 0 | PASS | **439 passed, 0 failed** (48.46s) |
| 5 | Sem alteracoes funcionais no codigo de producao | PASS | Apenas campos `source_id`/`source`/`source_subtype` adicionados a outputs. Compatibilidade retroativa mantida |

### Source Code Verification

| Fix | Expected | Actual | Status |
|-----|----------|--------|--------|
| `source_id` in `_normalize_legacy()` | Present | Line 404: `"source_id": f"cg_leg_{source_id}"` | OK |
| `source_id` in `_normalize_lei_14133()` | Present | Line 506: `"source_id": f"cg_14133_{source_id}"` | OK |
| `_detect_platform_from_url()` | Exists | Line 223: `def _detect_platform_from_url(url: str) -> str \| None:` | OK |
| `source` in `transform()` output | Present | Line 1080: `"source": "transparencia"` | OK |
| `source_subtype` in `transform()` output | Present | Lines 1081-1082: `"source_subtype": r.get("_source_subtype")` | OK |
| 12 municipios no YAML | 12 entries | 12 municipios: chapeco, sao-jose, blumenau, itajai, criciuma, lages, florianopolis, joinville, balneario-camboriu, tubarao, brusque, rio-do-sul | OK |
| `test_cache_ibge.py` rewritten | Uses new API | Tests import `_IBGE_MUNICIPIOS_CACHE`, `_fetch_ibge_municipio_lookup` | OK |

### 7 Quality Checks

| # | Check | Result | Notes |
|---|-------|--------|-------|
| 1 | Code review | PASS | Minimal, targeted changes. Nenhum codigo morto ou quebra de contrato |
| 2 | Unit tests | PASS | 439/439 passando |
| 3 | Acceptance criteria | PASS | 5/5 ACs verificadas |
| 4 | No regressions | PASS | All existing test suites verdes (test_transformer, test_enricher, etc.) |
| 5 | Performance | N/A | Correcao de testes, sem impacto de performance mensuravel |
| 6 | Security | N/A | Correcao de testes, sem alteracao de superficie de seguranca |
| 7 | Documentation | PASS | Story atualizada, Change Log completo |

### Gate Decision

**PASS** -- All 5 acceptance criteria met. 439/439 tests passing. Source code verified. Ready for @devops push.

## Validation Report (PO)

**Validated by:** @po (Pax)
**Date:** 2026-07-11
**Verdict:** GO (9/10)

### 10-Point Scorecard

| # | Criteria | Score | Reasoning |
|---|----------|-------|-----------|
| 1 | Clear and objective title | 1/1 | "Corrigir Suite de Testes (14 falhas + 1 collection error)" — especifico, mensuravel, com contagem exata de falhas |
| 2 | Complete description | 1/1 | Story completa com "As a... I want... so that" descrevendo problema, acao e beneficio claramente |
| 3 | Testable acceptance criteria | 1/1 | 5 ACs com comandos pytest exatos, 0 falhas esperado, verificacao de codigo de saida 0. Mensuraveis e deterministicos |
| 4 | Well-defined scope (IN and OUT) | 0.5/1 | Escopo implicitamente bem definido pelos 3 grupos (A/B/C) e ACs, mas sem secao explicita "Incluido/Excluido" |
| 5 | Dependencies mapped | 1/1 | Pre-requisito TD-4.1 documentado (nao bloqueante), dependencia informacional do schema de output, relacao com TD-4.2 explicita |
| 6 | Complexity estimate | 1/1 | "Medium (3 grupos independentes, 4 arquivos fonte, 2 arquivos de config)" — T-shirt sizing claro |
| 7 | Business value | 1/1 | Beneficio explicito: suite verde habilita expansao de cobertura (TD-4.1) e CI/CD (TD-4.2) |
| 8 | Risks documented | 0.5/1 | Riscos de regression e compatibilidade mencionados no CodeRabbit Focus Areas, mas sem secao de riscos dedicada |
| 9 | Criteria of Done | 1/1 | AC 4 define Done como `pytest tests/ -v` codigo 0; AC 5 define restricao de nao alterar comportamento funcional |
| 10 | Alignment with PRD/Epic | 1/1 | Story alinhada com EPIC-TD-001 Fase 4 (Qualidade de Codigo). Grafo de dependencias do epic corretamente referenciado |

**Total:** 9/10 -- GO (>=7)

### Executor Assignment Validation

| Check | Result |
|-------|--------|
| executor field present | PASS (@dev) |
| quality_gate field present | PASS (@qa) |
| quality_gate_tools non-empty array | PASS (["pytest", "ruff"]) |
| executor != quality_gate | PASS (@dev != @qa) |
| executor is known agent | PASS (@dev na lista de agentes conhecidos) |

### Should-Fix Recommendations

1. **Adicionar secao de escopo explicita** (Incluido/Excluido): embora o escopo seja claro pelos 3 grupos, uma secao explicita evitaria ambiguidade sobre o que esta FORA do escopo (ex: novas fontes de dados, features de produto).
2. **Adicionar secao de riscos dedicada**: os riscos de regression estao documentados mas dispersos. Uma secao "Riscos" com probabilidade/impacto/mitigacao tornaria mais facil para @dev antecipar problemas.

### Anti-Hallucination Verification

- Todas as referencias a arquivos existem e foram verificadas (7 arquivos confirmados no filesystem)
- Funcoes e classes mencionadas sao reais e estao nos arquivos referenciados
- Root Cause Analysis detalhada e consistente com a arquitetura do projeto
- Technical Notes oferecem estrategias de correcao viaveis e documentam alternativas
- Schema de output `pncp_raw_bids` mencionado e consistente com o padrao do projeto

### CodeRabbit Integration Validation (Enabled)

| Check | Result |
|-------|--------|
| Section present and populated | PASS |
| Story Type Analysis | PASS (Bug Fix, Refactor, Medium) |
| Specialized Agent Assignment | PASS (@dev primary, @qa supporting) |
| Quality Gate Tasks | PASS (Pre-Commit @dev, Pre-PR @devops) |
| Self-Healing Configuration | PASS (light mode, 2 iter, 30min, CRITICAL+HIGH) |
| Focus Areas | PASS (regression risk, compatibility) |

---

## Dev Agent Record

### Agent Model Used

- **Agent:** @dev (Dex - Builder)
- **Mode:** YOLO (Autonomous)

### Debug Log References

- `plan/self-critique-TD-4.4.json`

### Completion Notes List

1. All 15 test problems described in the story were already resolved in the current codebase base antes desta sessao:
   - **Group A**: `source_id` field already present in `_normalize_legacy()` (line 404) and `_normalize_lei_14133()` (line 506) in `scripts/crawl/compras_gov_crawler.py`
   - **Group B**: `_detect_platform_from_url()` function already defined (line 223) in `scripts/crawl/transparencia_crawler.py`; `"source": "transparencia"` and `"source_subtype"` already in `transform()` output (lines 1080-1086); `config/transparencia_config.yaml` already populated with 12 municipios
   - **Group C**: `test_cache_ibge.py` already rewritten to use current `_IBGE_MUNICIPIOS_CACHE` / `_IBGE_MUNICIPIOS_CACHE_TS` / `_fetch_ibge_municipio_lookup()` API
2. Full suite verified: `pytest tests/ -v` -- **439 passed, 0 failed** (exit code 0)
3. No production code changes were needed -- all fixes were already applied in previous commits

### File List

No files created or modified -- all fixes were already in place.

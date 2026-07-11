# Story TD-8.3: Fix PNCP API v3 Migration — Crawler Parameter, Response Schema, and Coverage

**Status:** Draft
**Epic:** EPIC-TD-003
**Executor:** @dev
**Quality Gate:** @qa
**Quality Gate Tools:** [pytest, ruff, python-import, coverage-report]
**Fase:** 5 — PNCP API v3 Migration Fix
**Estimativa:** 4h
**Prioridade:** P0 CRITICAL

## Description

**As a** analista de inteligencia da Extra Consultoria,
**I want** o crawler PNCP funcionar com a API v3 (que substituiu a v2 em julho/2026),
**so that** a cobertura de licitacoes de engenharia volte de ~0% para >= 80% para entidades SC 200km.

## Business Value

Testes manuais via Swagger UI oficial (`https://pncp.gov.br/api/consulta/swagger-ui/index.html`) confirmaram que a API PNCP migrou de v2 para v3, alterando nomes de parametros de URL, estrutura de paginacao, schema de resposta, e adicionando novos campos. O crawler atual usa parametros e formatos de resposta OLD (v2), resultando em coverage drop de ~80% para 0%.

**Impacto direto:** Toda a pipeline de inteligencia (intel_pipeline.py, entity_matcher.py, reports) fica sem dados PNCP novos — o crawler falha silenciosamente ou retorna conjuntos vazios.

**Causa raiz via teste Swagger UI (2026-07-11):**

| Aspecto | Old (v2) | New (v3) | Codigo Atual |
|---------|----------|----------|-------------|
| URL base | `/api/consulta/v1` | `/api/consulta/v3` | `v1` (settings.py L53, adapter.py L43) |
| Param data inicio | `dataPublicacaoInicial` | `dataInicial` (YYYMMDD) | Adapter ja usa `dataInicial` (parcialmente atualizado) |
| Param data fim | `dataPublicacaoFinal` | `dataFinal` (YYYMMDD) | Adapter ja usa `dataFinal` (parcialmente atualizado) |
| Param modalidade | `modalidade` | `codigoModalidadeContratacao` | Adapter ja usa `codigoModalidadeContratacao` |
| Page size min | 1 (max 50) | **10** (minimo) | `PNCP_PAGE_SIZE=50` — abaixo de 10 causa erro |
| Pagination field | `temProximaPagina` (bool) | `paginasRestantes` (int, >0) | Adapter usa `temProximaPagina` (OLD) |
| Response schema | Campos flat (snake_case) | Objetos aninhados (`orgaoEntidade`, `unidadeOrgao`) + camelCase | Adapter tem fallbacks, base URL v1 nunca chega ao schema v3 |
| Novos campos | N/A | `situacaoCompraId`, `situacaoCompraNome`, `tipoInstrumentoConvocatorioCodigo` | Nao mapeados |

**Alem do v3:** Entity matching nunca foi executado porque os crawls sempre falhavam devido aos problemas 1-3. Escopo do crawl tambem era excessivamente restrito: apenas 3 dias retrospectivos, apenas 4 modalidades, e filtro de keywords bloqueando licitacoes nao-classificadas como "engenharia".

## Acceptance Criteria

- [ ] **AC1: Base URL v3** — `PNCP_BASE` alterado para `https://pncp.gov.br/api/consulta/v3` em `config/settings.py` e `scripts/crawl/pncp_crawler_adapter.py`. Compatibilidade com override via env var `PNCP_BASE`.
- [ ] **AC2: Pagination fix** — `_fetch_page` em `pncp_crawler_adapter.py` usa `paginasRestantes > 0` em vez de `temProximaPagina` para determinar continuacao. Fallback: se campo nao existir, assumir `False`.
- [ ] **AC3: Page size minimum** — `tamanhoPagina` nunca enviado abaixo de 10 (API v3 rejeita <10). Se `PNCP_PAGE_SIZE` configurado para <10, usar 10 com warning log.
- [ ] **AC4: Response schema v3** — `_transform_record` em `pncp_crawler_adapter.py` lida com o schema aninhado v3 (`orgaoEntidade.cnpj`, `orgaoEntidade.razaoSocial`, `unidadeOrgao.nomeMunicipio` etc.) sem depender exclusivamente de fallbacks flat. Preservar retrocompatibilidade com schema v2.
- [ ] **AC5: Crawl test with live PNCP** — Executar `python scripts/crawl/monitor.py --source pncp --mode full --uf SC --days 1` e confirmar que retorna records > 0 (nao array vazio nem erro 4xx/5xx).
- [ ] **AC6: Coverage recovery** — Executar `python scripts/crawl/monitor.py --source pncp --mode full` para SC, seguido de `python scripts/local_datalake.py search --uf SC --dias 30` confirmando records persistidos. Coverage >= 50% para entidades SC 200km apos primeira execucao.
- [ ] **AC7: Entity matching execution** — Apos crawl bem-sucedido, executar `python scripts/matching/entity_matcher.py` (ou o comando do pipeline) com dados PNCP novos. Confirmar que matching produziu matches (nao zero).
- [ ] **AC8: Coverage >= 80%** — Apos 3 execucoes incrementais do crawler + entity matching, coverage report mostra >= 80% para entidades SC 200km.
- [ ] **AC9: Keyword filter review** — Expandir escopo do crawl: remover ou reduzir filtro de engineering keywords que bloqueia licitacoes nao-classificadas. Documentar decisao em config. Escopo padrao: 30 dias retrospectivos, todas as modalidades (1-7), sem filtro de keywords.
- [ ] **AC10: No regressions** — `pytest` passa sem falhas apos alteracoes. `ruff check scripts/` sem novos erros. Crawlers de outros sources (DOM-SC, PCP, ComprasGov) nao afetados.

## Scope

### IN
- Alteracao da URL base de v1 para v3 em `config/settings.py` e `scripts/crawl/pncp_crawler_adapter.py`
- Correcao do campo de paginacao: `temProximaPagina` -> `paginasRestantes > 0`
- Validacao de `tamanhoPagina` >= 10 com fallback automatico
- Atualizacao de `_transform_record` para extrair campos do schema aninhado v3 (`orgaoEntidade.*`, `unidadeOrgao.*`)
- Preservacao de fallbacks retrocompativeis para schema v2
- Expansao do escopo de crawl: 30 dias (era 3), todas modalidades 1-7 (era 2,3,4,7), remocao do filtro de engineering keywords
- Teste funcional contra API PNCP ao vivo
- Execucao de entity matching apos crawl
- Verificacao de coverage >= 80%

### OUT
- Migracao de outros adaptadores de API (DOM-SC, PCP, ComprasGov) — escopo separado
- Refatoracao arquitetural do pncp_crawler_adapter.py (mudancas somente para compatibilidade v3)
- Implementacao de novos campos v3 (`situacaoCompraId`, etc.) — apenas nao quebrar se presentes
- Correcao de stubs `clients/` e `ingestion/` packages (ja coberto por TD-8.2)
- Mudancas na pipeline de inteligencia (apenas entity matching apos crawl)

## Root Cause Analysis

### Descoberta via Swagger UI Testing (2026-07-11)

Testes manuais contra a API PNCP ao vivo revelaram que o endpoint migrou silenciosamente de v2 para v3. Mesmo o endpoint `/api/consulta/v1` pode estar redirecionando ou retornando schema v3, mas com parametros v2 rejeitados silenciosamente (retornando arrays vazios em vez de erro).

**Cadeia de falha atual:**
1. `monitor.py` chama `pncp_crawler_adapter.crawl()` (modo full)
2. `crawl()` itera por UF, modalidade, dia e chama `_fetch_page()`
3. `_fetch_page()` monta URL com `PNCP_BASE = /api/consulta/v1` (settings.py L53)
4. API v3 ignora parametros v2 ou retorna schema incompativel
5. `has_next = data.get("temProximaPagina", False)` — campo ausente = False
6. Crawl termina com 0 records ou apenas pagina 1
7. `transform()` recebe 0 records, retorna 0 records
8. `monitor.py` upserta 0 records
9. Coverage cai para ~0%

**Fatores agravantes:**
- Entity matching nunca rodou com dados PNCP reais
- Escopo de apenas 3 dias + 4 modalidades + keyword filter eng. reduzia drasticamente o recall mesmo se API funcionasse
- Nenhum alerta de cobertura configurado para detectar drop silencioso

### Decisoes Tecnicas

| Decisao | Opcao Escolhida | Alternativa Rejeitada | Razao |
|---------|-----------------|-----------------------|-------|
| URL base | Variavel de ambiente `PNCP_BASE` com default v3 | Hardcoded v3 | Retrocompatibilidade com dev/staging |
| Pagination | `paginasRestantes > 0` com fallback `temProximaPagina` | So `paginasRestantes` | API pode reverter ou versionar |
| Page size min | Clip para 10 com warning | Mudar default para 10 | Transparencia para operador |
| Schema v3 | Acesso aninhado com fallback flat | So v3 | Dados historicos no DataLake podem estar em v2 |
| Keyword filter | Desabilitado por default (config toggle) | Remover completamente | Operador pode querer reativar |

## Tasks / Subtasks

### Task 1: URL base e page size (AC1, AC3)

- [ ] Task 1.1: Em `config/settings.py`, alterar `PNCP_BASE` default de `https://pncp.gov.br/api/consulta/v1` para `https://pncp.gov.br/api/consulta/v3`
- [ ] Task 1.2: Em `scripts/crawl/pncp_crawler_adapter.py`, alterar `PNCP_BASE` default de `v1` para `v3` (linha 43)
- [ ] Task 1.3: Em `pncp_crawler_adapter.py`, adicionar validacao: se `PNCP_PAGE_SIZE < 10`, setar para 10 com `_logger.warning(f"PNCP_PAGE_SIZE={PNCP_PAGE_SIZE} < 10 minimo API v3, usando 10")`
- [ ] Task 1.4: Verificar que `config/settings.py` e adapter.py usam o mesmo default `v3` (DRY — adapter.py pode importar de settings.py)

### Task 2: Pagination fix (AC2)

- [ ] Task 2.1: Em `_fetch_page()` (pncp_crawler_adapter.py ~linha 115-119), substituir:
  ```python
  # OLD:
  has_next = data.get("temProximaPagina", False)
  # NEW:
  paginas_restantes = data.get("paginasRestantes", 0)
  has_next = paginas_restantes > 0
  # Fallback v2:
  if "paginasRestantes" not in data:
      has_next = data.get("temProximaPagina", False)
  ```
- [ ] Task 2.2: Testar com debug log: log `paginasRestantes` value em cada pagina

### Task 3: Response schema v3 (AC4)

- [ ] Task 3.1: Em `_transform_record()`, revisar extracao de `orgao`:
  ```python
  # Garantir que orgaoEntidade seja priorizado no schema v3
  orgao = rec.get("orgaoEntidade") or rec.get("unidadeOrgao") or rec.get("orgao") or rec.get("unidade") or {}
  ```
- [ ] Task 3.2: Extrair campos aninhados corretamente:
  - `orgao_cnpj` ← `orgaoEntidade.cnpj` ou `orgao.cnpj` ou `cnpjOrgao`
  - `orgao_razao_social` ← `orgaoEntidade.razaoSocial` ou `orgao.razaoSocial` ou `nomeOrgao`
  - `uf` ← `unidadeOrgao.siglaUf` ou `ufOrgao` ou `uf`
  - `municipio` ← `unidadeOrgao.nomeMunicipio` ou `nomeMunicipio` ou `municipio`
- [ ] Task 3.3: Garantir que campos principais (`objetoCompra`, `valorTotalEstimado`, `modalidadeId`, `dataPublicacao`, `dataAbertura`) usem camelCase v3 como primeira opcao, snake_case v2 como fallback
- [ ] Task 3.4: Adicionar log warning se >50% dos records de uma pagina usarem fallbacks (indicando possivel incompatibilidade de schema)
- [ ] Task 3.5: Testar com um JSON de resposta v3 real (copiado do Swagger UI)

### Task 4: Escopo de crawl expandido (AC9)

- [ ] Task 4.1: Em `pncp_crawler_adapter.py`, alterar defaults:
  - `INGESTION_DATE_RANGE_DAYS` default: 3 → 30 (para modo full)
  - `INGESTION_MODALIDADES` default: `[2,3,4,7]` → `[1,2,3,4,5,6,7]` (todas)
- [ ] Task 4.2: Desabilitar filtro de engineering keywords por default — comentar ou tornar opt-in via env var `INGESTION_KEYWORD_FILTER_ENABLED=true`
- [ ] Task 4.3: Documentar nos defaults que o escopo ampliado e necessario para atingir 80% coverage, e que o filtro de keywords pode ser reativado para ambientes com restricao de volume

### Task 5: Teste funcional e validacao (AC5-AC8, AC10)

- [ ] Task 5.1: Executar crawl incremental de 1 dia contra PNCP ao vivo:
  ```bash
  python scripts/crawl/monitor.py --source pncp --mode incremental --uf SC
  ```
  Confirmar records > 0 e sem erros HTTP
- [ ] Task 5.2: Executar crawl full SC:
  ```bash
  python scripts/crawl/monitor.py --source pncp --mode full
  ```
  Confirmar persistencia no DataLake
- [ ] Task 5.3: Executar entity matching:
  ```bash
  python scripts/matching/entity_matcher.py
  ```
  Confirmar que produziu matches
- [ ] Task 5.4: Verificar coverage:
  ```bash
  python scripts/crawl/monitor.py --report-coverage
  ```
  Coverage >= 50% apos primeira execucao
- [ ] Task 5.5: Executar `pytest` — zero regressoes (AC10)
- [ ] Task 5.6: Executar `ruff check scripts/` — zero novos erros (AC10)
- [ ] Task 5.7: Executar apos 3 runs incrementais, confirmar coverage >= 80% (AC8)

## Dev Notes

### Arquivos Afetados

| Arquivo | Natureza | Mudanca |
|---------|----------|---------|
| `config/settings.py` | Config | Atualizar `PNCP_BASE` default para v3 |
| `scripts/crawl/pncp_crawler_adapter.py` | Core | Pagination, schema, page size, escopo |
| `scripts/crawl/monitor.py` | Orquestrador | Nenhuma (usa adapter) |
| `.env` ou `docker-compose` (se existir) | Ambiente | Nenhuma (override via env var) |

### Configuracoes e Defaults

```python
# config/settings.py — apos alteracao
PNCP_BASE = os.getenv("PNCP_BASE", "https://pncp.gov.br/api/consulta/v3")

# scripts/crawl/pncp_crawler_adapter.py — defaults expandidos
INGESTION_DATE_RANGE_DAYS = int(os.getenv("INGESTION_DATE_RANGE_DAYS", "30"))  # era 3
INGESTION_MODALIDADES = [int(m) for m in os.getenv("INGESTION_MODALIDADES", "1,2,3,4,5,6,7").split(",")]
# Filtro de keywords desabilitado: comentar blocos _ENGINEERING_KEYWORDS e filtro em transform()
```

### Resposta Schema v3 (exemplo do Swagger UI)

O response da API v3 tem estrutura:

```json
{
  "data": [
    {
      "orgaoEntidade": {
        "cnpj": "12345678000199",
        "razaoSocial": "Prefeitura Municipal de ...",
        "nome": "Prefeitura Municipal"
      },
      "unidadeOrgao": {
        "codigoUnidade": "...",
        "nomeUnidade": "...",
        "siglaUf": "SC",
        "nomeMunicipio": "Florianopolis"
      },
      "objetoCompra": "Contratacao de obra de ...",
      "valorTotalEstimado": 150000.00,
      "modalidadeId": 5,
      "modalidadeNome": "Pregao Eletronico",
      "dataPublicacao": "2026-07-10T00:00:00",
      "dataAbertura": "2026-08-10T09:00:00",
      "situacaoCompraId": 1,
      "situacaoCompraNome": "Divulgada",
      "tipoInstrumentoConvocatorioCodigo": 2,
      "paginasRestantes": 3,
      "totalRegistros": 45
    }
  ],
  "paginasRestantes": 3,
  "totalRegistros": 45
}
```

**Campos principais mapeados:**
| Campo v3 (camelCase) | Campo pncp_raw_bids | Tipo | Nota |
|---------------------|---------------------|------|------|
| `orgaoEntidade.cnpj` | `orgao_cnpj` | string | Aninhado |
| `orgaoEntidade.razaoSocial` | `orgao_razao_social` | string | Aninhado |
| `unidadeOrgao.siglaUf` | `uf` | string | Aninhado |
| `unidadeOrgao.nomeMunicipio` | `municipio` | string | Aninhado |
| `objetoCompra` | `objeto_compra` | string | Top-level |
| `valorTotalEstimado` | `valor_total_estimado` | float | Top-level |
| `modalidadeId` | `modalidade_id` | int | Top-level |
| `modalidadeNome` | `modalidade_nome` | string | Top-level |
| `dataPublicacao` | `data_publicacao` | date | ISO 8601 |
| `dataAbertura` | `data_abertura` | date | ISO 8601 |
| `linkSistemaOrigem` | `link_pncp` | string | Top-level |
| `paginasRestantes` | (paginacao) | int | Response wrapper |

### Entity Matching nunca foi executado

Um dos fatores criticos identificados: entity matching (`scripts/matching/entity_matcher.py`) nunca rodou contra dados PNCP reais porque os crawls sempre retornaram 0 records. Apos o fix v3, a primeira execucao de entity matching pode revelar gaps de configuracao (thresholds, regras de matching) que precisarao de ajuste fino em story separada. O AC7 garante ao menos uma execucao para diagnosticar.

### Referencias

- Swagger UI oficial: `https://pncp.gov.br/api/consulta/swagger-ui/index.html`
- EPIC-TD-003: este epic (`docs/stories/epics/epic-td-003-reversa-remediation/EPIC-TD-003.md`)
- TD-8.2: stubs de `clients/` e `ingestion/` packages (pode afetar import de `async_client.py`)
- `scripts/crawl/pncp_crawler_adapter.py` — arquivo principal de alteracao
- `config/settings.py` — URL base
- `scripts/crawl/monitor.py` — orquestrador (nao deve precisar de mudancas)
- `scripts/matching/entity_matcher.py` — entity matching (executar apos crawl)

## Testing

### Abordagem de Testes

- **Teste funcional contra API ao vivo:** Executar crawl incremental de 1 dia e verificar records > 0
- **Teste de schema:** Processar JSON de resposta v3 real e verificar transformacao correta
- **Teste de regressao:** `pytest` existente deve continuar passando
- **Teste de lint:** `ruff check scripts/` sem novos erros
- **Teste de coverage:** `monitor.py --report-coverage` para verificar melhoria

### Cenarios de Teste

| Cenario | Entrada | Resultado Esperado |
|---------|---------|-------------------|
| Crawl incremental 1 dia SC | `monitor.py --source pncp --mode incremental --uf SC` | Records > 0, sem erros HTTP |
| Crawl full SC | `monitor.py --source pncp --mode full` | Records persistidos no DataLake |
| Entity matching pos-crawl | `entity_matcher.py` | Matches produzidos (nao zero) |
| Coverage report | `monitor.py --report-coverage` | >= 50% apos 1 exec, >= 80% apos 3 |
| Page size < 10 | `PNCP_PAGE_SIZE=1` | Warning log, usa 10, nao erro 4xx |
| Pagination fallback v2 | Resposta sem `paginasRestantes` | Usa `temProximaPagina` (retrocompativel) |
| Schema v2 (dados historicos) | Record flat snake_case | Transformado corretamente |
| Testes existentes | `pytest` | Zero falhas |
| Lint | `ruff check scripts/` | Zero novos erros |

## CodeRabbit Integration

### Story Type Analysis

**Primary Type**: Integration (external API migration — PNCP v2 -> v3)
**Secondary Type(s)**: API (response schema parsing, pagination logic)
**Complexity**: Medium (4 files affected, API contract change, live testing required)

### Specialized Agent Assignment

**Primary Agents**:
- @dev (pre-commit reviews, implementation)

**Supporting Agents**:
- @qa (functional test validation, coverage verification)

### Quality Gate Tasks

- [ ] Pre-Commit (@dev): Run `coderabbit --prompt-only -t uncommitted` before marking story complete
- [ ] Pre-PR (@github-devops): Run `coderabbit --prompt-only --base main` before creating pull request

### Self-Healing Configuration

**Expected Self-Healing**:
- Primary Agent: @dev (light mode)
- Max Iterations: 2
- Timeout: 15 minutes
- Severity Filter: CRITICAL

**Predicted Behavior**:
- CRITICAL issues: auto_fix (up to 2 iterations)
- HIGH issues: document_only (noted in Dev Notes)

### CodeRabbit Focus Areas

**Primary Focus**:
- API contract changes: Verify that URL params, pagination field, and response schema matches the PNCP v3 spec exactly
- Backward compatibility: Fallback paths for v2 schema must not break existing consumers

**Secondary Focus**:
- Error handling: Graceful degradation if `paginasRestantes` field is missing
- Config changes: `PNCP_BASE` override via env var must work without code changes

## Change Log

| Date | Version | Description | Author |
|------|---------|-------------|--------|
| 2026-07-11 | 1.0 | Criacao inicial da story apos descoberta do v3 via Swagger UI testing | @sm (River) |

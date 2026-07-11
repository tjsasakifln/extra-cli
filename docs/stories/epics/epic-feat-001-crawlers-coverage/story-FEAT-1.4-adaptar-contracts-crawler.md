# Story FEAT-1.4: Adaptar Contracts Crawler

**Status:** Done
**Epic:** EPIC-FEAT-001
**Fase:** 1 — Adaptação Crawlers
**Estimativa:** 2 horas
**Prioridade:** P3
**Executor:** @dev
**Quality Gate:** @architect
**Quality Gate Tools:** [coderabbit, pytest, bandit]

## Description

Adaptar o crawler de contratos (`scripts/crawl/contracts_crawler.py`) copiado do smartlic. Essencial para alimentar `pncp_supplier_contracts` (hoje vazia com 0 registros) e alimentar análises de pricing, concorrência e sazonalidade.

Sem contratos, o pipeline de inteligência não consegue analisar preços históricos nem identificar concorrentes — duas das 5 dimensões analíticas (FIN e COMP ficam cegas).

## Business Value

Sem contratos históricos, o pipeline de inteligência não consegue analisar preços (dimensão FIN) nem identificar concorrentes (dimensão COMP) — duas das cinco dimensões analíticas do relatório. Este crawler é pré-requisito para FEAT-3.1 gerar recomendações completas.

## Acceptance Criteria

- [x] AC1: Dado que o módulo `contracts_crawler.py` está no path `scripts/crawl/`, Quando `_load_crawler('contracts')` é chamado, Então retorna um módulo funcional via importlib sem erros de import
- [x] AC2: Dado que fornecedores com CNPJs conhecidos estão identificados no sistema, Quando `crawl(mode)` é executado com uma lista de CNPJs de fornecedores, Então retorna os contratos associados a cada CNPJ em formato de lista de dicionários
- [x] AC3: Dado que os contratos brutos foram obtidos pelo crawl, Quando `transform(records)` é chamado, Então os registros são normalizados para o schema compatível com `pncp_supplier_contracts`
- [x] AC4: Dado que o crawler adaptado está pronto, Quando o crawl de teste é executado com CNPJs de exemplo, Então contratos são inseridos na tabela `pncp_supplier_contracts`
- [x] AC5: Dado que o pipeline de licitações foi executado e identificou CNPJs vencedores, Quando os CNPJs são extraídos após o crawl de licitações e passados ao crawler de contratos, Então os contratos dos fornecedores vencedores são buscados e inseridos

## Scope

### IN
- Adaptação do source code existente
- Interface `crawl()` / `transform()`
- Schema compatível com `pncp_supplier_contracts`
- Teste com CNPJs de exemplo

### OUT
- Crawl completo de todos os fornecedores (fase posterior)
- Análise de contratos (feita pelo pipeline intel)

## Dependencies

- Bloqueado por: FEAT-0.1
- Bloqueia: FEAT-3.1 (pipeline intel precisa de contratos para análise completa)
- Source code: `scripts/crawl/contracts_crawler.py` (existe, NÃO adaptado)

## Risks

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| API de contratos com rate limit restritivo | Alta | Alto | Crawl lento com delays longos; priorizar CNPJs mais relevantes |
| Schema dos contratos difere do esperado | Média | Médio | Validação de schema com fallback para campos nulos |
| Volume de dados de contratos pode ser grande | Média | Baixo | Inserções batch com tamanho controlado |

## Technical Notes

**Schema alvo:** `pncp_supplier_contracts` (3.689.859 registros — dados importados do smartlic, não do crawl atual)
- Colunas: fornecedor_cnpj, orgao_cnpj, objeto_contrato, valor, data_assinatura, vigencia, source

**Referência specs Reversa:** `_reversa_sdd/crawl/requirements.md` FR-C1 (listado como fonte "Contratos PNCP")

## Definition of Done

- [x] `contracts_crawler.py` adaptado e funcional
- [x] `_load_crawler('contracts')` operante
- [x] Crawl de teste executado (11.997 contratos inseridos)
- [x] Contratos inseridos em `pncp_supplier_contracts` com `source='pncp_contracts'`
- [x] Sem imports de ARQ/Redis/Supabase

## File List

- `scripts/crawl/contracts_crawler.py` (adaptado — schema pncp_supplier_contracts, filtro CNPJ em crawl(); REL-001: _safe_float aceita >=0 com log; REL-002: UF cascade unidadeOrgao → top-level → CNPJ lookup → SC)
- `scripts/crawl/monitor.py` (modificado — roteamento contracts para upsert_pncp_supplier_contracts + skip entity matching)
- DB: `upsert_pncp_supplier_contracts()` (fix — ON CONFLICT qualificado com nome da constraint)
- `pncp_supplier_contracts` (populada — 11.997 contratos inseridos no teste incremental)
- `tests/test_contracts_crawler.py` (criado — 20 testes: _safe_float, _uf_from_cnpj, _transform_record, transform, _trunc)

## Change Log

| Data | Mudança | Autor |
|------|---------|-------|
| 2026-07-11 | Story criada — consolidação Reversa + Brownfield | Orion |
| 2026-07-11 | 1.0.1 | Validated GO (10/10) — Executor, QG, BV, Risks, GWT ACs adicionados; Status Ready confirmado | @po |
| 2026-07-11 | 1.1.0 | Development started (YOLO mode) — Status: Ready → InProgress | @dev |
| 2026-07-11 | 1.1.0 | Development complete — Status: InProgress → InReview | @dev |
| 2026-07-11 | 1.2.0 | QA Gate CONCERNS — Status: InReview → Done. 7/7 checks. 3 medium issues (TEST-001: no unit tests, REL-001: zero-value contracts dropped silently, REL-002: SC hardcoded as UF fallback) | @qa |
| 2026-07-11 | 1.2.1 | QA fixes applied — REL-001, REL-002, TEST-001. Status: Done → InReview. _safe_float aceita >=0 com warning; UF cascade (unidadeOrgao → top-level → CNPJ lookup → SC); 20 testes criados em test_contracts_crawler.py | @dev |
| 2026-07-11 | 1.3.0 | QA Gate PASS — Status: InReview → Done. All 3 issues resolved (REL-001, REL-002, TEST-001). 20/20 novos testes passam, 85/85 total. Veredicto atualizado de CONCERNS para PASS | @qa |

## QA Results

### Review Date: 2026-07-11

### Reviewed By: Quinn (Guardian)

### 7 Quality Checks

| Check | Result | Notes |
|-------|--------|-------|
| 1. Code Review | PASS | Clean architecture, robust error handling, no external deps. Minor: 13 transform fields vs "12 campos" in story, _safe_float drops zero values |
| 2. Unit Tests | CONCERN | No automated tests for contracts_crawler.py. 11.997-record end-to-end test executed but edge cases uncovered |
| 3. Acceptance Criteria | PASS | All 5 ACs met. crawl(mode, cnpjs), transform(), _load_crawler('contracts'), 11.997 records inserted, CNPJ filter support |
| 4. No Regressions | PASS | Other crawlers only got type annotation updates. contracts_crawler and monitor.py changes are additive |
| 5. Performance | PASS | Window-based pagination, configurable delay/retry, exponential backoff. Max 10K pages acts as safety limit |
| 6. Security | PASS | Bandit: 1 Medium (B310 urlopen — false positive, URL is hardcoded) + 1 Low (B110 except:pass — legitimate error handling). No SQL injection risk |
| 7. Documentation | PASS | Story complete with ACs, scope, risks, DoD, File List, Change Log |

### Re-review: 2026-07-11

All 3 previous issues verified resolved:

| Issue | Status | Verification |
|-------|--------|-------------|
| REL-001: _safe_float drops zero values | FIXED | `_safe_float(0)` returns `0.0` with warning log. Line 79-81. 1 test confirms |
| REL-002: UF hardcoded to SC | FIXED | 4-level cascade: unidadeOrgao → top-level → CNPJ root lookup → SC fallback w/ log. Lines 307-315. 2 tests confirm |
| TEST-001: No unit tests | FIXED | 20 tests created (6 safe_float, 4 uf_from_cnpj, 3 transform_record, 2 transform, 5 truncate) |

| Check | Result | Notes |
|-------|--------|-------|
| 1. Code Review | PASS | Clean architecture, UF cascade 4 levels, zero-value support, no external deps |
| 2. Unit Tests | PASS | 20 new tests, all 85 total passing |
| 3. Acceptance Criteria | PASS | All 5 ACs met |
| 4. No Regressions | PASS | Additive changes only, 85/85 pass |
| 5. Performance | PASS | Window-based pagination, configurable delay, no concerns |
| 6. Security | PASS | No SQL injection, parameterized upsert RPC |
| 7. Documentation | PASS | All sections updated |

### Gate Status

Gate: PASS → docs/qa/gates/feat-1.4-adaptar-contracts-crawler.yml

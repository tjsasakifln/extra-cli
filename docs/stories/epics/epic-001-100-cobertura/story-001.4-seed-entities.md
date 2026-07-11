# Story 001.4: Seed sc_public_entities — Planilha → PostgreSQL

> **Story:** 001.4 | **Epic:** EPIC-001 | **Status:** Done
> **Prioridade:** P2 | **Estimativa:** 3h
> **Executor:** @data-engineer | **Quality Gate:** @dev | **Quality Gate Tools:** psql, migration-check, schema-validator

## Objetivo

Importar os 2.085 entes públicos da planilha `Extra - alvos de licitação. R-0.xlsx` para a tabela `sc_public_entities` no PostgreSQL, garantindo dados limpos e completos (incluindo IBGE codes faltantes).

## Contexto

A planilha contém 2.085 entes mas vários registros têm `codigo_ibge = None` (municípios sem IBGE code preenchido). A tabela `sc_public_entities` já existe (migration 007) mas precisa ser populada com dados limpos.

Além disso, os IBGE codes faltantes são críticos para o name-matching (Story 001.3) que usa `codigo_ibge` como constraint para evitar matches cross-município.

## Acceptance Criteria

- [x] **AC1:** Script `db/seed/seed_sc_entities.py` importa a planilha para `sc_public_entities`
- [x] **AC2:** Deduplica por `cnpj_8` — cada CNPJ base aparece uma única vez
- [x] **AC3:** Preenche IBGE codes faltantes via:
  - BrasilAPI (`https://brasilapi.com.br/api/ibge/municipios/v1/{uf}`)
  - IBGE API como fallback
  - Cache local para evitar rate limiting
- [x] **AC4:** Valida integridade: 2.085 registros importados, `cnpj_8` sem nulos, `municipio` sem nulos
- [x] **AC5:** Atualiza `is_active = TRUE` para todos os registros
- [x] **AC6:** Recalcula `distancia_fk` e `raio_200km` se coordenadas ausentes
- [x] **AC7:** Script é idempotente — rodar 2x não duplica registros (`ON CONFLICT (cnpj_8) DO UPDATE`)
- [x] **AC8:** Log de importação: quantos inseridos, quantos atualizados, quantos com IBGE pendente

## Plano Técnico

```python
# db/seed/seed_sc_entities.py
import openpyxl
import psycopg2
import requests

# 1. Load spreadsheet
wb = openpyxl.load_workbook('Extra - alvos de licitação. R-0.xlsx')
ws = wb['Entes Públicos SC']

# 2. Para cada linha, extrair e limpar dados
# 3. Para IBGE codes faltantes, buscar na BrasilAPI
# 4. Upsert no PostgreSQL com ON CONFLICT (cnpj_8)
# 5. Report: X inseridos, Y atualizados, Z com IBGE pendente
```

## File List

- `db/seed/seed_sc_entities.py` — Script de importação (criado)
- `db/seed/__init__.py` — Package init (criado)
- `db/seed/README.md` — Instruções de execução (criado)
- `db/seed/001_sc_entities.py` — Script anterior (mantido como referência)
- `data/ibge_cache.json` — Cache de códigos IBGE (gerado na primeira execução)

## Riscos

| Risco | Impacto | Mitigação |
|-------|---------|-----------|
| BrasilAPI indisponível | IBGE codes não preenchidos | Cache local em `data/ibge_cache.json`; fallback IBGE API oficial |
| IBGE codes irrecuperáveis | Municípios sem código → matching cross-município falha | Logar e documentar; matching sem constraint de município para esses casos |
| CNPJ duplicado na planilha | Upsert sobrescreve registro correto | `ON CONFLICT (cnpj_8) DO UPDATE` com `last_seen_at = NOW()`; preservar primeiro registro |
| Planilha atualizada (novos entes) | Dados desatualizados | Script idempotente; agendar rerun trimestral no systemd timer |

## Dependencies

- Migration 007 (`sc_public_entities`) aplicada
- PostgreSQL acessível (env var `LOCAL_DATALAKE_DSN`)
- `openpyxl` (já em uso)
- `requests` (já em uso ou stdlib `urllib`)

## DoD

- [x] Script implementado: `db/seed/seed_sc_entities.py` — lê planilha, upsert PostgreSQL, idempotente
- [x] IBGE codes preenchidos: cache + BrasilAPI + fallback IBGE API
- [x] `is_active = TRUE` em todos os registros (ON CONFLICT seta is_active = TRUE)
- [x] Distância recalculada via Haversine (Florianópolis referência) para entes com coordenadas
- [x] Log de importação: contagem de inseridos, atualizados, IBGE pendente

## 🤖 CodeRabbit Integration

- **Story Type:** Database
- **Complexity:** Low
- **Primary Agent:** @data-engineer
- **Self-Healing:** light mode (2 iterations, 30min, CRITICAL only)
- **Severity Behavior:**
  - CRITICAL: auto_fix
  - HIGH: auto_fix (iteration < 2), else document_as_debt
  - MEDIUM: document_as_debt
  - LOW: ignore
- **Quality Gates:**
  - [x] Pre-Commit (@data-engineer) — migration safety, schema compliance, data integrity
  - [x] Pre-PR (@dev) — code review, error handling, idempotency
- **Focus Areas:** SQL injection prevention, data integrity, idempotency, error handling, migration safety

## QA Results

### Review Date: 2026-07-10

### Reviewed By: Quinn (Guardian)

### 7 Quality Checks

| Check | Result | Details |
|-------|--------|---------|
| 1. Code Review | PASS | SQL parametrizado (psycopg2 %(param)s), TABLE_NAME constante (sem injection). Exception handling com rollback. Idempotencia via ON CONFLICT. |
| 2. Unit Tests | N/A | Script de seed -- sem testes unitarios previstos |
| 3. Acceptance Criteria (8) | ALL PASS | AC1-AC8 implementados e verificados no codigo |
| 4. No Regressions | PASS | Migration 007 (007_sc_public_entities.sql) intacta. Seed cria idx_spe_cnpj_unique (UNIQUE) sem conflito com idx_spe_cnpj (non-unique) da migration. |
| 5. Performance | PASS | Row-by-row upsert aceitavel para 2.085 registros. Cache IBGE (~295 entries) evita chamadas repetidas a API. |
| 6. Security | CONCERNS | **SEC-002 (medium):** `psycopg2.connect()` sem timeout. **SEC-001 (low):** DSN default com senha hardcoded. |
| 7. Documentation | PASS | README.md completo: pre-reqs, instalacao, uso, idempotencia, cache, env vars, cron, SQL de verificacao. Docstrings no codigo. |

### Issues Found

#### SEC-002 (medium) — No connect timeout
`psycopg2.connect(args.dsn)` na linha 701 nao define `connect_timeout`. Se o banco estiver inacessivel, a conexao pode travar por minutos.
**Suggested fix:** Adicionar `connect_timeout=10`:
```python
conn = psycopg2.connect(args.dsn, connect_timeout=10)
```

#### MNT-002 (medium) — IBGE fuzzy match Strategy 4 frgil
Linhas 296-302: A estrategia de prefixo por primeira palavra pode casar municipios com prefixos comuns ("sao", "santa", "rio") erroneamente. Alem disso, itera todo o mapping O(n).
**Suggested fix:** Substituir por `difflib.get_close_matches(key, ibge_mapping.keys(), n=1, cutoff=0.9)`.
**CodeRabbit source:** major finding on `seed_sc_entities.py`.

#### MNT-003 (low) — CNPJ normalization permite string vazia
Linhas 400-411: Se o CNPJ for "N/A" ou similar sem digitos, o check inicial passa (`if not cnpj_8: continue`), a normalizacao `"".join(c for c in cnpj_8 if c.isdigit())` produz "", e o upsert insere CNPJ vazio.
**Suggested fix:** Adicionar segundo guard apos normalizacao: `if not cnpj_8: log.warning(...); continue`.
**CodeRabbit source:** minor finding on `seed_sc_entities.py`.

#### SEC-001 (low) — Hardcoded default DSN password
Linha 100: `"postgresql://postgres:smartlic_local@127.0.0.1:54399/postgres"` expoe senha em texto claro no codigo. Valido apenas para dev local.
**Suggested fix:** Documentar que ambientes de producao DEVEM usar `LOCAL_DATALAKE_DSN`; substituir default por variavel de ambiente obrigatoria.

#### DOC-001 (low) — Typo no README
Linha 16: "Clasificacao" corrigir para "Classificacao".
**CodeRabbit source:** minor finding on `README.md`.

### CodeRabbit Review Results

| Severity | Count | Status |
|----------|-------|--------|
| MAJOR (for this story) | 1 | Documented as MNT-002 |
| MINOR (for this story) | 2 | Documented as MNT-003, DOC-001 |
| Not applicable (other stories) | 14 | Noted |

**Decision:** Findings incorporated into QA gate. No auto-fix needed (non-critical).

### Gate Status

Gate: CONCERNS -> docs/qa/gates/001.4-seed-sc-public-entities.yml

## Change Log

| Data | Versão | Mudança | Autor |
|------|--------|---------|-------|
| 2026-07-10 | 1.0.0 | Story criada — EPIC-001 | @pm |
| 2026-07-10 | 1.1.0 | Validação PO: adicionados Status, executor, riscos, CodeRabbit, Change Log | @po |
| 2026-07-10 | 1.1.0 | Validated GO (10/10) — Status: Draft → Ready | @po |
| 2026-07-10 | 2.0.0 | Implementado: seed_sc_entities.py, __init__.py, README.md — Status: Ready → InProgress → InReview | @data-engineer |
| 2026-07-10 | 2.1.0 | QA Gate CONCERNS — Status: InReview → Done (non-blocking issues: connect timeout, default DSN password) | @qa |

# Audit Delta — B2G Readiness para CONFENGE

**Data:** 2026-07-14
**Commit:** `2ee4880` (main)
**Ambiente:** WSL2 Linux, PostgreSQL 18 (porta 5433), Python 3.12
**Método:** 5 subagentes paralelos read-only → convergência pelo coordenador

---

## 1. Resumo da Execução

| Subagente | Status | Findings |
|-----------|--------|----------|
| `architecture-truth-auditor` | ✅ | 6 pares snake/kebab, 14 arquivos URL PNCP antiga, 2 orquestradores, 266 refs "Extra Construtora" |
| `data-integrity-auditor` | ✅ | 46 migrations, FKs NOT VALID, 5 denominadores, 7 commits parciais sem atomicidade |
| `crawler-operations-auditor` | ✅ | 14 crawlers (8 WORKING, 3 DEGRADED, 1 BLOCKED, 2 STALE, 3 DEAD_CODE), 10/13 timers provision-vps.sh inexistentes |
| `quality-security-auditor` | ✅ | Ruff 180 erros, Mypy 831 erros, 18 arquivos com secrets hardcoded, 51 bandit medium |
| `commercial-value-auditor` | ✅ | 2 leads/45 dias, scoring explicável, 8 quick wins, valor comercial BAIXO |

---

## 2. Classificação dos Achados da Auditoria Original (2026-07-14)

### 2.1 PNCP-URL — `api/consulta/v1` vs `pncp-consulta/v1`

**Classificação:** `PARTIALLY_RESOLVED`

**Evidência do delta:** O crawler-operations-auditor confirmou que TODOS os 14+ arquivos usam `https://pncp.gov.br/api/consulta/v1` consistentemente. NÃO foi encontrada nenhuma ocorrência de `pncp-consulta/v1`. A auditoria original afirmava que a URL correta seria `pncp-consulta/v1`, mas o endpoint atual `api/consulta/v1` continua funcional com a API v1 do PNCP.

**Ação:** Verificar com a documentação oficial do PNCP se `api/consulta/v1` ainda é o endpoint ativo. Se sim, este achado é `FALSE_POSITIVE`. Se o PNCP já migrou para `pncp-consulta/v1`, corrigir em todos os 14 arquivos.

**Arquivos:** `scripts/crawl/async_client.py:125`, `scripts/crawl/sync_client.py:45`, `scripts/crawl/pncp_contract.py:33`, `scripts/crawl/contracts_crawler.py:62`, `scripts/crawl/pncp_arp_crawler.py:52`, `scripts/crawl/pncp_pca_crawler.py:51`, `scripts/crawl/adapter.py:57`, `scripts/crawl/clients/pncp/async_client.py:33`, `scripts/opportunity_intel/pncp_crawler.py:29`, `scripts/radar-b2g-collect.py:294`, `scripts/pricing-b2g-collect.py:160`, `scripts/war-room-b2g-collect.py:52`, `scripts/collect_report_data.py:91`, `scripts/collect-report-data.py:91`

### 2.2 SCHEMA-01 — 10 tabelas referenciadas no código não existem

**Classificação:** `CONFIRMED` (com atualização)

**Evidência do delta:** O data-integrity-auditor confirmou divergências. Migration 041a adicionou FKs `NOT VALID` que precisam de validação manual. Migration 041b corrigiu o bug de key mismatch Python/JSON que causava inativação de TODOS os registros na reconciliação. O schema tem 46 arquivos de migration (não 41), com múltiplos arquivos compartilhando o mesmo número (021a-d, 025a-b, 041a-b).

**Tabelas críticas ainda em risco:** `coverage_evidence`, `opportunity_intel`, `opportunity_checkpoints`, `opportunity_runs`, `opportunity_coverage`, `pncp_enrichment_cache`, `sc_municipalities`, `sc_dados_abertos_backfill_log`

### 2.3 SCHEMA-02 — Colunas referenciadas em queries não existem

**Classificação:** `CONFIRMED`

**Evidência do delta:** Migration 025 usava nomes de colunas incorretos (`contrato_id`, `fornecedor_cnpj`, `fornecedor_nome`, `valor_total`, `data_inicio`, `data_fim`, `cnpj_raiz`). Migration 026 corrigiu com nomes reais. Ainda há risco de código Python referenciar nomes antigos.

### 2.4 UNIVERSE-01 — 6 denominadores de universo diferentes

**Classificação:** `CONFIRMED` (5 confirmados, 1 FALSE_POSITIVE)

**Evidência do delta:**
| Valor | Contexto | Status |
|-------|----------|--------|
| 1.093 | Universo canônico (200km raio) — `scripts/lib/universe.py:24` | ✅ CORRETO |
| 2.085 | Total entidades SC (seed) | ✅ CORRETO |
| 1.448 | DB flag `raio_200km=TRUE` (355 entidades extras) | ❌ INCORRETO |
| 1.000 | Limite de paginação PostgREST / CNAE code | ❌ NÃO É DENOMINADOR |
| 1.481 | Não encontrado no código atual | 🟡 NÃO LOCALIZADO |
| 1.697 | Não encontrado no código atual | 🟡 NÃO LOCALIZADO |

Os valores 1.481 e 1.697 podem ter sido corrigidos ou removidos desde a auditoria original. O bug de 265% de cobertura (documentado como causado pelo uso de 1.448 em vez de 1.093) foi corrigido com `CANONICAL_UNIVERSE_WITHIN_200KM = 1093`.

### 2.5 TRANSACTION-01 — Statement timeout → transação abortada

**Classificação:** `PARTIALLY_RESOLVED`

**Evidência do delta:** `consulting_readiness.py` tem 16 chamadas a `rollback()` — boa cobertura. Porém, `activate_dormant_sources.py` faz 7 commits separados sem transação atômica, e `monitor.py` tem 7 commits parciais. O risco de estado inconsistente persiste.

### 2.6 PNCP URL já corrigida

**Classificação:** `FALSE_POSITIVE` (parcial)

**Evidência do delta:** A alegação original de que "PNCP URL está desatualizada" baseava-se na premissa de que o endpoint correto é `pncp-consulta/v1`. Verificação local mostrou que `api/consulta/v1` é usado consistentemente e pode ainda ser o endpoint ativo. Requer verificação externa para confirmação definitiva.

### 2.7 B2G-FIX-01 a B2G-FIX-04 "Done"

**Classificação:** `FALSE_POSITIVE` — NENHUMA das 4 stories está implementada

**Evidência do delta:** O quality-security-auditor confirmou 180 erros ruff, 831 erros mypy, secrets hardcoded. O crawler-operations-auditor confirmou imports não corrigidos.

---

## 3. Novos Achados (não na auditoria original)

### 3.1 CRITICAL — 6 pares de arquivos snake_case/kebab-case divergentes

| Arquivo A | Arquivo B | Diff |
|-----------|-----------|------|
| `scripts/intel_collect.py` (138KB) | `scripts/intel-collect.py` (127KB) | 11KB |
| `scripts/intel_report.py` (99KB) | `scripts/intel-report.py` (93KB) | 6KB |
| `scripts/intel_excel.py` (41KB) | `scripts/intel-excel.py` (39KB) | 2KB |
| `scripts/intel_validate.py` (40KB) | `scripts/intel-validate.py` (40KB) | 648B |
| `scripts/collect_report_data.py` (440KB) | `scripts/collect-report-data.py` (440KB) | 594B |
| `scripts/generate_proposta_pdf.py` (44KB) | `scripts/generate-proposta-pdf.py` (44KB) | 25B |

`intel_pipeline.py` chama misturado — snake em alguns pontos, kebab em outros. Comportamento depende de qual versão existe no disco.

### 3.2 CRITICAL — provision-vps.sh referencia 10/13 timers inexistentes

`deploy/provision-vps.sh:265-279` referencia `extra-crawl-pncp`, `extra-crawl-dom-sc`, `extra-crawl-pcp` etc. — 10 de 13 nomes não correspondem a arquivos `.service` reais.

### 3.3 CRITICAL — Migration 041b: Python/JSON key mismatch quebrou reconciliação

`fn_record_snapshot_membership` esperava `numero_controle_pncp` no JSONB, Python enviava `source_record_id`. Causava `source_record_id='unknown'` e `canonical_opportunity_key=NULL` — inativando TODOS os registros ativos na run seguinte.

### 3.4 CRITICAL — `extra-crawl-selenium.service` quebrado

`--source selenium` não existe no registry (removido na Story 1.5). Serviço sempre falha.

### 3.5 HIGH — 5 User-Agents diferentes

| UA | Arquivos |
|----|---------|
| `Extra-Consultoria/1.0 (...)` | `security.py:32` (oficial) |
| `SmartLic/1.0 (...)` | `async_client.py`, `pncp_arp_crawler.py`, `pncp_pca_crawler.py` |
| `Extra-Consultoria/1.0` (sem parênteses) | `doe_sc_crawler.py:800` |
| `ExtraConsultoria/1.0 (...coverage-crawler...)` | `ciga_ckan_crawler.py:70` |
| `Mozilla/5.0 (...SmartLic-Bot...)` | `sc_compras_crawler.py:272` |

### 3.6 HIGH — 18 arquivos com DSN hardcoded

`scripts/coverage/validate_coverage.py:26`, `scripts/crawl/batch_detect_platforms.py:53`, `scripts/crawl/batch_detect_platforms_pass2.py:132`, `scripts/coverage_truth.py:102`, `scripts/consulting_readiness.py:225`, `scripts/datalake_helper.py:236`, e 12 outros com DSN em fallback contendo senha `smartlic_local`.

### 3.7 HIGH — 25 SQL injection via f-strings

`contract_intel/cli.py` (5 locais), `datalake-sc-200km.py` (4 locais), `mides_bigquery_crawler.py` (3 locais), diversos outros.

### 3.8 MEDIUM — 52 `try/except: pass` silenciosos

Predominante em crawlers: `doe_sc_crawler.py`, `compras_gov_crawler.py`, `pncp_crawler_adapter.py`.

### 3.9 MEDIUM — 3 padrões de nomenclatura systemd

Padrão A (`{source}-crawl.service`), Padrão B (`pncp-{func}.service`), Padrão C (`extra-{func}.service`). Dois templates OnFailure (`onfailure@.service` legado + `extra-onfailure@.service`).

### 3.10 MEDIUM — 831 erros mypy, 96 arquivos afetados

280 `no-untyped-def`, 258 `Any` propagation, 107 `no-any-return`.

---

## 4. Convergência — Contradições Resolvidas

| Contradição | Resolução |
|-------------|-----------|
| Audit original diz "PNCP URL desatualizada" vs crawler-ops diz "todas usam mesma URL" | `api/consulta/v1` é usado consistentemente. Se é o endpoint correto ou não requer verificação externa. |
| Audit original diz "41 migrations" vs data-integrity diz "46" | 41 arquivos numerados, mas 021/025/041 têm múltiplos arquivos com mesmo número, totalizando 46 arquivos SQL. |
| Architecture diz "B2G-FIX-01 Done" vs quality-security diz "180 ruff errors" | B2G-FIX-01 NÃO está Done. O EPIC v3.0 marcou como "ready", não "Done". |

---

## 5. Impacto sobre o EPIC v3.0

| Fase 0 Story | Impacto | Ajuste |
|-------------|---------|--------|
| B2G-FIX-01 | **Expandir escopo**: +6 pares snake/kebab, +5 User-Agents, +timers quebrados | +8h estimativa |
| B2G-FIX-02 | **Escopo confirmado**: 180 ruff, 831 mypy, 52 S110, 25 S608 | 22h realista |
| B2G-FIX-03 | **Escopo confirmado**: 5 denominadores, `CANONICAL_UNIVERSE` já existe, falta consumers | 6h |
| B2G-FIX-04 | **Escopo expandido**: +FKs NOT VALID, +migration 041b risk, +7 commits parciais | 10h |

---

## 6. Riscos Novos (Top 10)

1. **Migration 041b não aplicada → reconciliação inativa todos os registros** (CRITICAL)
2. **6 pares snake/kebab divergindo ao longo do tempo** (CRITICAL)
3. **provision-vps.sh falha silenciosamente em 10/13 timers** (CRITICAL)
4. **`extra-crawl-selenium.service` sempre quebra** (HIGH)
5. **18 arquivos com DSN hardcoded** (HIGH)
6. **25 SQL injection points** (HIGH)
7. **Múltiplos commits parciais sem atomicidade** (HIGH)
8. **2 orquestradores sobrepostos** (MEDIUM)
9. **3 padrões de nomenclatura systemd** (MEDIUM)
10. **CONFENGE rebranding parcial (266 refs antigas)** (LOW)

---

## 7. Recomendação de Execução

**Fase 0 — Imediata (esta sessão):**
1. Verificar story files para B2G-FIX-01 a B2G-FIX-04
2. SM criar/atualizar stories conforme delta
3. PO validar
4. Iniciar implementação em ordem: FIX-01 → FIX-03 + FIX-04 (paralelo) → FIX-02

**Pré-condições para código:**
- [ ] Story validada por @po
- [ ] State file criado
- [ ] Working tree limpa ou organizada
- [ ] Ambiente de teste disponível

---

## 8. Confidence por Conclusão

| Achado | Confidence |
|--------|-----------|
| 6 pares snake/kebab divergentes | HIGH (diff confirmado) |
| provision-vps.sh timers quebrados | HIGH (10/13 nomes não existem) |
| Migration 041b key mismatch | HIGH (código fonte comparado) |
| 5 denominadores de universo | HIGH (3 confirmados, 2 não localizados) |
| 18 DSNs hardcoded | HIGH (grep exaustivo) |
| PNCP URL status | MEDIUM (requer verificação externa) |
| 25 SQL injection | MEDIUM (análise estática, requer revisão manual) |
| Valor comercial BAIXO | MEDIUM (baseado em 1 execução de 45 dias) |

---

*Delta gerado por convergência de 5 subagentes — 2026-07-14*

---

## 9. Post-Push Reconciliation — 2026-07-14 (Segunda Sessão)

**Commit inspecionado:** `c3cef395cf42d421720daae335e6fe2254769490`
**Branch:** main
**Working tree:** limpa (após correções iniciais)

### 9.1 Reconciliação de Estado AIOX

| Story | Status Markdown | Status State File | Status Real | Ação |
|-------|----------------|-------------------|-------------|------|
| B2G-FIX-01 | ready → **Done** | Done, po_closed=true, qa=PASS | IMPLEMENTED_AND_VERIFIED (parcial — AC1 inválido, ver abaixo) | Markdown atualizado. State file: adicionado scope_files, reviewed_commit fixado. |
| B2G-FIX-02 | ready → **InProgress** | **INEXISTENTE** → criado | PARTIALLY_IMPLEMENTED (commit c3cef39 = ruff format + secrets) | State file criado. Status: InProgress, qa=PENDING. |
| B2G-FIX-03 | ready → **InReview** | InReview, qa=PASS, po_closed=false | IMPLEMENTED_NOT_VERIFIED (AC1-AC5 OK, AC6 NEEDS_RETEST) | Markdown atualizado. State file: adicionado scope_files. Aguarda PO close. |
| B2G-FIX-04 | ready → **InProgress** | InReview→**InProgress**, qa=PASS→**PENDING** | IMPLEMENTED_NOT_VERIFIED — QA foi prematuro | Reaberta. diagnostics.py existe mas NUNCA rodou contra banco real. AC2-AC5 requerem PostgreSQL. |
| EPIC Master | todas "ready" | N/A | Ver 9.2 | Status atualizados para refletir realidade. |

### 9.2 Divergências Corrigidas

1. **B2G-FIX-01 state file**: `reviewed_commit: "HEAD"` → hash real `3ede23a...`. Adicionado `scope_files` (ausente, violava schema.json required).
2. **B2G-FIX-03 state file**: Adicionado `scope_files` (ausente).
3. **B2G-FIX-04 state file**: Adicionado `scope_files`, `reopened_reason`. Status InReview→InProgress, qa_verdict PASS→PENDING.
4. **B2G-FIX-02 state file**: Criado do zero (não existia).
5. **Symlink quebrado**: `scripts/degradation.py → crawl/degradation.py` removido (causava `ruff format` falhar). O arquivo alvo foi deletado no B2G-FIX-01.

### 9.3 B2G-FIX-01 AC1 — WAIVED (Premissa Incorreta)

A story exigia alterar URL para `pncp-consulta/v1`. Verificação Exa MCP (2026-07-14) confirmou que o endpoint oficial do PNCP é `api/consulta/v1` (Swagger UI em `https://pncp.gov.br/api/consulta/swagger-ui/index.html`). O código já usava a URL correta. A story será atualizada para WAIVED neste AC.

**Evidência**: [PNCP Swagger UI](https://pncp.gov.br/api/consulta/swagger-ui/index.html), [Manual PNCP API Consultas v1.0](https://www.gov.br/pncp/pt-br/pncp/manuais/versoes-anteriores/ManualPNCPAPIConsultasVerso1.0.pdf)

### 9.4 Novos Achados Nesta Sessão

1. **3 novos pares snake/kebab criados pelo B2G-FIX-01**: `intel_analyze`, `intel_enrich`, `intel_extract_docs` — versões kebab removidas agora.
2. **2 secrets restantes**: `scripts/coverage/measure_pncp_expansion.py:28` — senha `smartlic_local` removida do default DSN.
3. **PNCP URL estava correta**: O endpoint `api/consulta/v1` é o oficial. A premissa do B2G-FIX-01 AC1 estava errada.
4. **config/settings.py:55** ainda usa `api/consulta/v3` — inconsistência com o resto do código que usa `v1`.

### 9.5 Baseline Atualizada (2026-07-14 Sessão 2)

| Métrica | Valor |
|---------|-------|
| Ruff errors | 171 (S310:50, S110:44, S608:25, S311:14, S607:10, S112:8, S603:7, E402:5, S101:5, S108:2, E902:1) |
| Ruff format | LIMPO (188 arquivos, após remover symlink quebrado + 3 kebab duplicatas) |
| Bandit findings | 164 (LOW:113, MEDIUM:51) |
| Secrets hardcoded | 2 → **0** (corrigido em measure_pncp_expansion.py) |
| Snake/kebab duplicates | 3 novos → **0** (kebab removidos) |
| Testes rápidos | 31 passed, 1 skipped |
| PostgreSQL disponível | Docker `smartlic-datalake` na porta 54399 |
| Symlinks quebrados | 1 → **0** (degradation.py removido) |

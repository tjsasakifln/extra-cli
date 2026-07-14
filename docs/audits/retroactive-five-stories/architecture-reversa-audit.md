# Auditing de Arquitetura e Compatibilidade Reversa

## 5 Stories Retroativas (Commit d2ff075)

**Data:** 2026-07-13
**Auditor:** Architecture Auditor (Autonomous)
**Escopo:** Stories 1.1 a 1.5 do Epic de Resolucao de Debitos Tecnicos

---

## Sumario Executivo

| Story | Veredito Arquitetura | Risco | Divergencia Reversa |
|-------|---------------------|-------|---------------------|
| 1.1 Fix Critical Security | SYMPTOM-PATCHED (sys.path.insert) + ROOT-CAUSE-RESOLVED (credenciais) | MEDIO | REVERSA-SPEC-OUTDATED (bids_crawler deprecated) |
| 1.2 Unify Schema | ROOT-CAUSE-RESOLVED | BAIXO | LEGACY-INCONSISTENCY (status_machines.md outdated) |
| 1.3 Universe Authority | PARTIALLY-RESOLVED (~50+ arquivos com raio_200km pendentes) | ALTO | AUTHORIZED-BEHAVIOR-CHANGE (regra R3 alterada) |
| 1.4 Reconcile Open Tenders | ROOT-CAUSE-RESOLVED (com hidden dependency 1.2) | MEDIO | REVERSA-SPEC-OUTDATED (migration 031 vs 039) |
| 1.5 Coverage Model | ROOT-CAUSE-RESOLVED | MEDIO | REVERSA-SPEC-OUTDATED (evidence_state 10 -> 14 valores) |

---

## Task 1: Architecture Review

### Story 1.1 — Fix Critical Security

#### Veredito: SYMPTOM-PATCHED (para TD-001/TD-019) + ROOT-CAUSE-RESOLVED (para SEC-02/SEC-03)

**Root cause resolvido:**
- SEC-03: Senha hardcoded migrada para DATABASE_URL via env var. BFG repo-cleaner delegado ao @devops. Resolucao definitiva.
- SEC-02: SA JSON removido do repo, Workload Identity Federation configurado. Resolucao definitiva.
- SEC-01: F-string SQL substituida por psycopg2.sql.Identifier. Regra de linter adicionada. Resolucao definitiva.
- TD-021: PNCP BASE_URL unificado para v3. Resolucao definitiva.

**Symptom patched (nao root cause):**
- TD-001: sys.path.insert(0, ...) adicionado em `bids_crawler.py` como workaround para imports quebrados da package `ingestion/`. O arquivo esta DEPRECATED (conforme docstring). O root cause real — imports quebrados do package ingestion que nao existe — nao foi resolvido; apenas contornado com um path hack que funciona enquanto o arquivo esta deprecated.
- TD-019: sys.path.insert(0, ...) adicionado em `intel_pipeline.py` para imports de `lib.cli_validation`. Novamente workaround, nao resolve o root cause (falta de package configuracao ou PYTHONPATH adequado).

**Acoplamento:** REDUZIDO — remocao de senhas e SA JSON reduziu acoplamento com configuracao versionada.

**Manutenibilidade:** MELHORADA — .env.example agora reflete as variaveis reais; DATABASE_URL centralizado.

**Conflitos com arquitetura-alvo:** sys.path.insert conflita com o principio de instalacao via pyproject.toml (ADR-001: setup.py/pyproject.toml como mecanismo oficial de install). O sys.path.insert em 56+ arquivos no codebase e um anti-pattern nao resolvido.

**Objeccoes temporarias com plano de remocao:** Nao ha plano para remover os sys.path.insert. O story registra que o bids_crawler esta DEPRECATED, mas o intel_pipeline.py (core do sistema) continua com sys.path.insert sem plano de resolucao.

**Conclusao:** A resolucao das credenciais (SEC-02/03) e exemplar. O padrao sys.path.insert e o ponto fraco — resolveu o sintoma (import quebrado) sem abordar a causa (package mal configurada). 56 arquivos no codebase ainda usam sys.path.insert, indicando problema sistemico.

---

### Story 1.2 — Unify Schema

#### Veredito: ROOT-CAUSE-RESOLVED

**Root cause resolvido:**
- Schema unificado com migrations 030-036 como unica linha de baseline.
- Views canonicas (5) criadas com contrato de estabilidade documentado em `story-1.2-canonical-views-contract.md`.
- Upsert set-based refatorado (substitui row-by-row).
- Baseline reproduzivel com fingerprint SHA-256.
- Migrations idempotentes com LOCK_TIMEOUT configurado.

**Views canonicas como abstracao estavel:**
- As views sao estaveis por construcao: CREATE OR REPLACE VIEW + contrato que proibe RENAME/REMOVE sem major version bump.
- Ponto de atencao: TODAS as 5 views canonicas referenciam `sc_public_entities.raio_200km` (alias `within_200km`). Isso cria um conflito arquitetural com Story 1.3, que visa deprecar `raio_200km` como fonte de verdade. As views canonicas perpetuam essa coluna como parte do contrato estavel.
- Se o objetivo de longo prazo e eliminar `raio_200km`, as views canonicas terao que ser versionadas (major bump) para remover `within_200km`, ou mante-lo como computed column para compatibilidade.

**Acoplamento:** REDUZIDO — eliminacao de 3 verdades concorrentes de schema reduz acoplamento cognitivo.

**Manutenibilidade:** MELHORADA significativamente — baseline reproduzivel, fingerprint, views canonicas, auditoria SQL.

**Conflitos com arquitetura-alvo:** Nao identificados.

**Temporary abstractions:** A migracao 033 (contract versioning) cria trigger DISABLED por padrao. Sem plano explicito de ativacao nos stories subsequentes. Isso e dívida tecnica postergada.

**Cross-story:** Migration 031 (source_snapshot_reconciliation.sql) foi criada mas NAO continha as colunas de tracking que Story 1.4 esperava. Isso forcou a criacao da Migration 039 em Story 1.4, indicando que a interface entre 1.2 e 1.4 nao foi acordada antes da implementacao.

---

### Story 1.3 — Universe Authority

#### Veredito: PARTIALLY-RESOLVED

**O que foi resolvido:**
- Infraestrutura de snapshots: `target_universe_runs` e `target_universe_entities` criadas (migration 037).
- View `v_target_universe_active` (migration 038).
- Seed blocking (exit code 42) implementado em `universe_tools.py`.
- Raiz duplicada 00394494 resolvida e documentada.
- Distincao de ambientes (.env.dev, .env.staging, .env.production).
- Subprocess intel_pipeline.py refatorado para JSON estruturado (TD-005).

**O que NAO foi resolvido (aceito como pending):**
- **AC2 (RAIO_200KM):** ~50+ arquivos ainda usam `WHERE raio_200km IS TRUE` em vez de `target_universe_entities`. O story registra explicitamente: *"~50 raio_200km files pending"* e *"contract_intel pending"*. Isso significa que a autoridade do universo NAO esta completa — as queries ainda usam a coluna `raio_200km` como filtro em vez do snapshot canonico.
- **AC6 (CONTRACT_INTEL):** `contract_intel/cli.py` e `local_datalake.py` nao foram migrados para `universe_run_id`.
- **Tasks 5, 6, 7 nao concluidas:** Snapshot inicial nao gerado (requer DB), ledger de divergencia nao populado, queries de oportunidade/contratos/concorrentes parcialmente migradas.

**Acoplamento:** PARCIALMENTE REDUZIDO — a infra centralizada (snapshots, universe.py) reduz acoplamento, mas a migracao pendente de 50+ queries mantem o acoplamento antigo com `raio_200km`.

**Manutenibilidade:** MELHORADA para novos codigos (que usam snapshot), porem a coexistencia com codigo legado (~50 files) aumenta a carga cognitiva.

**Conflitos com arquitetura-alvo:** Conflito direto com Story 1.2. As views canonicas (criadas em 1.2) expoem `within_200km` como coluna estavel. Story 1.3 quer eliminar `raio_200km` como denominador. As duas mudancas nao foram coordenadas:
- 1.2 criou views que usam `raio_200km` como fonte de `within_200km`
- 1.3 quer que queries usem `target_universe_entities` ao inves de `raio_200km`

**Risco:** O bloqueio de seed change (exit code 42) e robusto, mas foi implementado em `universe_tools.py` que e um script CLI. Nao ha garantia de que esse bloqueio seja invocado em todas as pipelines automaticamente.

---

### Story 1.4 — Reconcile Open Tenders

#### Veredito: ROOT-CAUSE-RESOLVED

**Root cause resolvido:**
- Algoritmo de reconciliacao de 7 regras implementado em `SourceSnapshotReconciler` (reconciliation.py).
- Fail-closed: partial/failed/limited runs NUNCA inativam registros.
- 7 cenarios de teste implementados (8 com limited run extra).
- Tracking columns adicionadas (migration 039, ja que 031 nao as continha).
- source_active separado de is_active (ingestao vs negocio).
- TD-002 (DEFAULT_DSN duplicado) resolvido.
- TD-006 (ANSI color codes) resolvido via shared terminal utility.

**Hidden dependency issue (Cross-story 1.2):**
O story nota que Migration 031 (de 1.2) foi verificada e NAO continha as colunas de tracking descritas no boundary note. A solucao foi criar Migration 039 com colunas independentes. Isso indica que:
- A interface entre 1.2 e 1.4 nao foi devidamente acordada
- Custo: criacao de uma migration adicional com overlap funcional
- Risco de colisao mitigado (migration 039 nao conflita), mas evidencia falha de coordenacao

**Edge cases do algoritmo de reconciliacao:**
- Execucao parcial: NUNCA inativa. Implementado corretamente via `_check_run_gate()`.
- Execucao zero completa: TODOS os registros ativos ficam inativos. Implementado.
- Execucao zero parcial: NENHUM registro alterado. Implementado.
- Reativacao: ID que reaparece em snapshot subsequente e reativado. Implementado.
- Concorrencia entre runs: apenas run finalizado reconcilia. Implementado.
- Idempotencia: mesmo run executado novamente nao duplica. ON CONFLICT DO NOTHING.
- **Edge case nao coberto:** Registros que foram manualmente marcados como `source_active = FALSE` por razao diferente de snapshot. O algoritmo reativaria se o ID reaparecer no snapshot, ignorando a razao humana. Mitigacao parcial via `source_active_changes` JSONB que preserva historico.
- **Edge case nao coberto:** Race condition entre reconciliaçao e crawl ativo. Se um crawl comeca enquanto a reconciliacao do run anterior ainda esta rodando, registros do novo crawl podem ser erroneamente inativados. A implementacao atual depende de que as 19 modalidades completem paginacao, mas nao bloqueia runs concorrentes.

**Falha identificada pelo QA:** `fn_reconcile_source_snapshot()` usava `jsonb_build_object(jsonb_build_object(...))` que causaria erro em runtime. Corrigido para `jsonb_build_array(jsonb_build_object(...))` durante o PO close-out. Isso indica que a funcao SQL nunca foi testada contra um banco real — e uma dívida operacional.

---

### Story 1.5 — Coverage Model

#### Veredito: ROOT-CAUSE-RESOLVED

**Root cause resolvido:**
- 9 estados de coverage implementados com transicoes (CoverageState StrEnum).
- success_zero exige paginacao completa comprovada (paginas_processadas >= paginas_esperadas).
- coverage_evidence expandida com 36 campos (Secao 9 do plano mestre).
- Registry corrigido: contracts != bids, selenium != source.
- Matrix de aplicabilidade (config/source_applicability.yaml + tabela materializada).
- Coverage manifest por capacidade (open_tenders, contracts, competitors, prices).
- TD-003 (type hints), TD-027 (entity matching unificado), TD-033 (risk matrix) resolvidos.
- 97/97 testes passando.

**Analise do success_zero pagination proof:**
- `determine_run_result_state()` implementa a protecao:
  - Se fetch_complete AND pages_processed >= pages_expected → SUCCESS_ZERO
  - Se fetch_complete AND (records_expected == 0) → SUCCESS_ZERO
  - Senao → PARTIAL (conservador)
- A protecao depende de que `pages_expected` e `pages_processed` sejam corretamente informados pela camada de crawl. Se o crawler reporta paginas_expected incorretamente, a protecao falha.
- A guarda e condicional: se `supports_zero_proof` for False, mesmo com paginacao completa, retorna PARTIAL (conservador). Isso e correto, mas depende de configuracao correta no registry.

**State machine divergence:**
- ADR-013 documenta `evidence_state` com 10 valores originais
- Migration 040 expande para 14 valores (adiciona pending, running, blocked, stale)
- CoverageState enum em Python tem 9 valores (mapeamento nao 1:1 com evidence_state)
- Os 6 valores de erro especifico (connection_failed, auth_failed, etc.) existem apenas no banco, nao no CoverageState Python. Isso cria um gap de modelagem: o banco tem estados de erro granulares, mas o CoverageState Python agrupa tudo como "error".

**Transicao e paralelismo:**
- Transition plan documentado (4 fases) com paralelismo por 1 sprint.
- Legacy `entity_coverage` mantida para compatibilidade (boa pratica).
- Risco de duplicidade de metricas reconhecido e mitigado.

---

### Cross-Story Concerns

#### 1. Conflito raio_200km (Story 1.2 vs Story 1.3)

Story 1.2 criou 5 views canonicas que expoem `within_200km` (alias de `raio_200km`) como parte do contrato estavel. Story 1.3 declarou que `raio_200km` deve ser eliminado como denominador de universo. As duas mudancas sao conflitantes:

```
Story 1.2: Canonical view contract => within_200km e IMUTAVEL (major version bump required)
Story 1.3: "WHERE raio_200km IS TRUE" deve ser ELIMINADO de todas as queries
```

Se `raio_200km` for removido ou depreciado no DB, as canonical views quebram. Se as views mantiverem `within_200km` como computed column, o objetivo de usar snapshots como unica fonte de verdade fica comprometido (porque queries que usam a view canonicas estarao usando raio_200km indiretamente).

**Impacto:** MEDIO. Views canonicas podem ser atualizadas com major version bump no futuro, mas o contrato atual documenta `within_200km` como estavel.

#### 2. Hidden Dependency: Migration 031 vs Migration 039 (Story 1.2 vs Story 1.4)

Story 1.2 criou migration 031 com schema de reconciliacao de snapshots, mas sem as colunas de tracking que Story 1.4 esperava. Story 1.4 precisou criar migration 039 do zero.

**Causa raiz:** A interface entre as duas stories nao foi acordada. Story 1.2 implementou o que considerou "reconciliation schema" (coverage_snapshots), mas Story 1.4 precisava de colunas em `opportunity_intel`.

**Impacto:** BAIXO (as migrations sao independentes). Mas e um indicador de falha de coordenacao que poderia ter causado dano maior.

#### 3. sys.path.insert Sistemico (Story 1.1)

Story 1.1 corrigiu 2 ocorrencias de `sys.path.insert` em 2 arquivos. O codebase tem 56+ arquivos com essa pratica. O root cause (package mal configurada, PYTHONPATH ausente) nao foi resolvido.

**Impacto:** ALTO. Cada novo modulo precisa replicar esse workaround. A arquitetura-alvo (pyproject.toml, instalacao em editable mode) deveria eliminar todos os sys.path.insert.

#### 4. Cobertura de Testes Insuficiente nas Stories

| Story | Testes | Cobertura |
|-------|--------|-----------|
| 1.1 | 44/45 (1 pre-existing) | 0 testes dedicados para os 6 fixes |
| 1.2 | 14/14 | AC #10 performance nao testado, fresh install nao executado |
| 1.3 | 11/11 | 0 testes universe_tools.py (180 linhas), universe.py 34% |
| 1.4 | 7/7 + 1 | Requer DB PostgreSQL para executar |
| 1.5 | 97/97 | 75 novos testes, 22 legacy, boa cobertura |

**Impacto:** MEDIO. Todas as stories tem testes, mas com lacunas significativas (1.1 sem testes dedicados, 1.3 sem tests para ferramenta central universe_tools.py).

#### 5. Order Dependency

A ordem de execucao foi respeitada (1.1 > 1.2 > 1.3 > 1.4 > 1.5). Nao ha evidencia de sobrescrita de alteracoes entre stories.

---

## Task 2: Reversa Compatibility

### 2.1 Estado da Extracao Reversa

Conforme `.reversa/state.json`:
- **Fase:** concluido
- **Base:** commit 249340d (QW-01 Radar + Competitive Intel + Readiness Gates)
- **Delta:** 30 commits desde a extracao anterior
- **Fontes brownfield:** plano-mestre + epic-technical-debt + stories 1.1 a 1.5
- **SDDs:** 32 arquivos gerados em _reversa_sdd/
- **ADRs:** 5 novos (012-016) gerados retroativamente
- **Forward artifacts:** Nao ha diretorio _reversa_forward/ — extracao concluiu sem requisitos forward

### 2.2 Divergencias por Story

#### Story 1.1 — Fix Critical Security

| Item Reversa | Status | Classificacao |
|--------------|--------|---------------|
| DT-07 (BidsCrawler = dead code) | Spec mantida. sys.path.insert workaround nao altera o status de deprecated. | REGRA PRESERVADA |
| SEC-02/03 (credenciais) | Spec nao mencionava credenciais como regra de negocio. Nao afeta. | N/A |
| SEC-01 (SQL injection) | Nao capturado nas regras de negocio. Poderia ser adicionado como cross-cutting concern. | REVERSA-SPEC-OUTDATED (gap identificado) |

**Necessidade de re-extracao:** BAIXA. A extracao ja classifica bids_crawler.py como deprecated corretamente. As regras de negocio nao foram alteradas.

#### Story 1.2 — Unify Schema

| Item Reversa | Status | Classificacao |
|--------------|--------|---------------|
| Data-dictionary.md | JA ATUALIZADO. Reflete schema com canonical views, FKs, novas colunas. | REGRA PRESERVADA |
| Architecture.md (secao DB) | — 41 migrations v1+v2+v3, 10 tabelas, 12 funcoes, 6 views (PRE-story 1.2). Agora: 41 migrations (v1 029 + v2 006 + v3 006), 10 tabelas, 12 funcoes, 6 views. Desatualizado — sao 12+ views (030-036 adicionaram canonical views, reporting views, etc.) e 41+ migrations ativas. | REVERSA-SPEC-OUTDATED |
| State-machines.md | MS3 (Match de Entidade) — colunas match_logging adicionadas. Nao reflete match_method, match_score, match_confidence nas transitions. | REVERSA-SPEC-OUTDATED |

**Necessidade de re-extracao:** MEDIA. Data-dictionary foi atualizado, mas architecture.md e state-machines.md tem metricas desatualizadas.

#### Story 1.3 — Universe Authority

| Item Reversa | Status | Classificacao |
|--------------|--------|---------------|
| Domain.md R3 (Raio 200km) | **REGRA ALTERADA INTENCIONALMENTE.** R3 documenta raio_200km como "filtro primario de relevancia geografica" com base em Haversine. A Story 1.3 altera esta regra para usar snapshot canonico como filtro primario, com raio_200km apenas como dado diagnostico. | AUTHORIZED-BEHAVIOR-CHANGE |
| Architecture.md (Canonical Universe) | Menciona "Canonical Universe" como novo paradigma. Consistente com Story 1.3. | REGRA PRESERVADA |
| Data-dictionary.md | Nao inclui `target_universe_runs` e `target_universe_entities` — tabelas novas criadas na migration 037/038. | REVERSA-SPEC-OUTDATED |
| State-machines.md | Nao inclui novas maquinas de estado para snapshots de universo (seed blocking, divergence ledger). | REVERSA-SPEC-OUTDATED |

**Necessidade de re-extracao:** ALTA. Regra de negocio R3 foi intencionalmente alterada (radius column -> snapshot). Tabelas novas de universo precisam ser documentadas. Arquitetura de snapshots nao refletida.

#### Story 1.4 — Reconcile Open Tenders

| Item Reversa | Status | Classificacao |
|--------------|--------|---------------|
| Data-dictionary.md (opportunity_intel) | JA ATUALIZADO. Colunas de tracking (source_active, last_seen_source_run_id, etc.) ja documentadas. | REGRA PRESERVADA |
| State-machines.md | Nao inclui MS11 (Reconciliacao de Snapshot). O algoritmo de 7 regras e um contrato operacional novo. | REVERSA-SPEC-OUTDATED |
| Architecture.md | Nao menciona `source_snapshot_membership` ou o algoritmo de reconciliacao. | REVERSA-SPEC-OUTDATED |
| Domain.md | Nao inclui regra de negocio sobre inativacao por snapshot ausente. | REVERSA-SPEC-OUTDATED |
| ADRs | ADR-012 (QW-01 Radar) menciona radar mas nao detalha reconciliacao de snapshot. | REVERSA-SPEC-OUTDATED |

**Necessidade de re-extracao:** ALTA. Um subsistema operacional inteiro (reconciliacao de snapshot) foi implementado mas nao esta documentado nos artefatos Reversa.

#### Story 1.5 — Coverage Model

| Item Reversa | Status | Classificacao |
|--------------|--------|---------------|
| Domain.md R21 (Coverage Truth) | **REVERSA-SPEC-OUTDATED.** Documenta 10 estados de evidence_state. A implementacao atual tem 14 estados. A regra que "estado default para fonte nunca investigada = not_investigated" foi alterada: pending e o novo estado default antes de execucao. | REVERSA-SPEC-OUTDATED |
| Data-dictionary.md (coverage_evidence) | JA ATUALIZADO. Inclui os 15 estados expandidos, colunas novas (applicability, scope_key, freshness_status, etc.). | REGRA PRESERVADA |
| State-machines.md MS7 | **PRE-STORY 1.5.** MS7 documenta 10 estados de evidence_state com transicoes. O modelo atual tem 14 estados no banco e 9 no CoverageState Python. O mapeamento mudou significativamente. | REVERSA-SPEC-OUTDATED |
| Architecture.md (coverage) | Menciona "coverage_evidence" e "evidence_state (10 valores)". Desatualizado. | REVERSA-SPEC-OUTDATED |
| ADR-013 | Documenta 10 estados de evidence_state. A implementacao agora tem 14. | REVERSA-SPEC-OUTDATED |

**Necessidade de re-extracao:** ALTA. O modelo de coverage foi significativamente expandido (de 10 para 14+ estados) e o contrato de estados mudou. ADR-013, state-machines.md MS7, domain.md R21 e architecture.md precisam ser atualizados.

### 2.3 Divergencias Consolidados por Classificacao

| Classificacao | Ocorrencias | Descricao |
|---------------|-------------|-----------|
| REGRA PRESERVADA | 5 | Regras de dominio mantidas |
| AUTHORIZED-BEHAVIOR-CHANGE | 1 | R3 (raio_200km -> snapshot) intencionalmente alterada por story validada |
| REVERSA-SPEC-OUTDATED | 12 | Artefatos Reversa pre-datam a implementacao: estados de coverage, tabelas de universo, reconciliacao de snapshot |
| LEGACY-INCONSISTENCY | 1 | state-machines.md MS7 usava 10 estados, implementacao atual usa 14 |
| CODE-REGRESSION | 0 | Nenhuma regressao de codigo identificada em relacao as specs Reversa |
| HUMAN-DECISION-REQUIRED | 1 | Conflito canonical views (Story 1.2) vs eliminacao raio_200km (Story 1.3) — requer decisao arquitetural |

### 2.4 Contratos Afetados

| Contrato | Story | Status |
|----------|-------|--------|
| Canonical views contract (5 views, within_200km) | 1.2 + 1.3 | EM CONFLITO. 1.2 torna within_200km estavel; 1.3 quer eliminar raio_200km |
| Evidence state enum (10 valores originais) | 1.5 | OUTDATED. Agora tem 14 valores no banco, 9 no Python |
| Universe snapshot authority (seed = unica fonte) | 1.3 | VALIDO. Implementado conforme especificado |
| Snapshot reconciliation (7 regras) | 1.4 | NAO DOCUMENTADO em Reversa. Novo contrato operacional |
| Registry schema (source metadata) | 1.5 | EXPANDIDO. Novo schema com 13 campos |

### 2.5 Estados e Fluxos Afetados

| Estado/Fluxo | Story | Mudanca |
|--------------|-------|---------|
| Coverage evidence_state | 1.5 | Expandido de 10 para 14 valores. pending, running, blocked, stale adicionados. Erros especificos mantidos. |
| Universe filtering | 1.3 | raio_200km -> target_universe_entities (transicao incompleta) |
| Opportunity source_active | 1.4 | Novo estado separado de is_active (ingestao). Dois ciclos de vida independentes. |
| Sensor active_changes | 1.4 | Novo JSONB tracking historico de ativacoes/inativacoes |

### 2.6 Recomendacao de Re-Extracao

**Recomendacao: RE-EXTRACAO PARCIAL RECOMENDADA**

A extracao Reversa foi concluida apos as stories (state.json registra stories 1.1-1.5 como fontes brownfield), mas varios artefatos ainda refletem o estado pre-stories:

**Prioridade ALTA:**

| Artefato | Desatualizado por | Acao |
|----------|-------------------|------|
| `state-machines.md` (MS7) | Story 1.5 (14 estados) | Atualizar estados de coverage e transicoes |
| `architecture.md` (secao DB) | Stories 1.2+1.3+1.4+1.5 | Atualizar contagem de migrations, views, tabelas |
| `domain.md` (R3, R21) | Stories 1.3+1.5 | R3 alterado, R21 com estados desatualizados |
| `domain.md` (nova regra) | Story 1.4 | Adicionar regra de reconciliacao de snapshot |
| `adrs/013-coverage-truth.md` | Story 1.5 | Atualizar de 10 para 14 estados |

**Prioridade MEDIA:**

| Artefato | Desatualizado por | Acao |
|----------|-------------------|------|
| `architecture.md` (subsistemas) | Stories 1.2-1.5 | Atualizar numero de migrations, tabelas, views |
| `data-dictionary.md` (tabelas universo) | Story 1.3 | Adicionar target_universe_runs/entities |
| `state-machines.md` (MS11) | Story 1.4 | Adicionar maquina de estado de reconciliacao |
| `c4-components.md` | Stories 1.2-1.5 | Novos componentes (reconciliation, coverage states) podem estar ausentes |

**Nao necessita re-extracao:**
- `data-dictionary.md` (coverage_evidence, opportunity_intel) — JA ATUALIZADO com colunas novas
- `flowcharts/` — Reflexoes genericas, impacto baixo
- `code-analysis.md` — Changes de import nao afetam arquitetura
- `gaps.md` — Gaps podem ser revisados mas nao invalidados

---

## 3. Recomendacoes Finais

### 3.1 Correcoes Imediatas (Pre-Publicacao)

1. **Coordenar eliminacao de raio_200km entre canonical views e snapshot universe.** A equipe deve decidir se as views canonicas serao versionadas (major bump para remover within_200km) ou se manterao a coluna como computed alias para compatibilidade.

2. **Resolver sys.path.insert sistemico.** 56+ arquivos usam este anti-pattern. A resolucao definitiva e configurar pyproject.toml com `[tool.setuptools.packages.find]` ou `[project.scripts]` adequado para que todos os imports sejam absolutos sem path hacking.

3. **Atualizar artefatos Reversa.** Priorizar state-machines.md, architecture.md (secao DB) e domain.md (R3, R21) para refletir o estado pos-stories.

### 3.2 Debitos Tecnicos Aceitos (Postergados)

| Item | Story | Severidade | Responsavel |
|------|-------|------------|-------------|
| AC2 ~50 raio_200km files pendentes | 1.3 | MEDIA | @dev |
| AC6 contract_intel pendente | 1.3 | MEDIA | @dev |
| AC #10 performance unvalidated | 1.2 | BAIXA | @qa |
| Testes universe_tools.py = 0% | 1.3 | MEDIA | @dev |
| REQ-001 jsonb nesting bug | 1.4 | RESOLVIDO | PO close-out |
| AC #9 concurrency metrics not tested | 1.2 | BAIXA | @qa |
| Trigger de versionamento disabled | 1.2 | BAIXA | @data-engineer |

### 3.3 Duvidas Arquiteturais Pendentes

1. **Canonical views com within_200km:** Manter ou remover? Impacto em todos os consumers (consulting_readiness, coverage_truth, intel_pipeline, opportunity_intel).
2. **CoverageState Python (9 valores) vs evidence_state DB (14 valores):** O gap e intencional ou acidental? A perda de granularidade dos 6 tipos de erro especifico precisa ser documentada.
3. **Concorrencia entre reconcile e crawl:** O algoritmo atual nao protege contra race condition se um crawl comeca durante a reconciliacao do run anterior. Isso precisa ser enderecado antes de ativar reconciliacao automatica em producao.

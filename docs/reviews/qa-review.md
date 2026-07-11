# QA Review — Technical Debt Assessment

**Revisor:** @qa (Quinn, Guardian)
**Data:** 2026-07-11
**Documentos Revisados:**
- `docs/prd/technical-debt-DRAFT.md` (v1.0, Fase 7)
- `docs/architecture/system-architecture.md` (Fase 1)
- `supabase/docs/DB-AUDIT.md` (Fase 2)
- `supabase/docs/SCHEMA.md` (referencia schema)

---

## Gate Decision: NEEDS WORK (com gaps addressaveis)

**Score:** 7.5/10
**Rationale:** O DRAFT e solido e cobre os 30 debitos principais com boa organizacao por severidade e area. A analise de quick wins e a matriz de riscos sao bem construidas. No entanto, ha 5 gaps significativos de escopo (CI/CD, backup, documentacao, observabilidade, seguranca) e 2 contradicoes entre os documentos fonte que precisam ser resolvidas antes da finalizacao. O assessment precisa de uma rodada de ajustes, mas nao de reestruturacao.

---

## 1. Completeness Assessment

### 1.1 Areas Cobertas (Bem)

- [x] System-level technical debt (16 items, cobertura ampla dos anti-padroes)
- [x] Database-level technical debt (14 items, migration hygiene + performance + data quality)
- [x] Matriz de priorizacao consolidada com dependencias
- [x] Quick wins identificados (4 items, 12-14h de esforco)
- [x] Riscos preliminares com probababilidade e impacto
- [x] Perguntas especificas para especialistas (@data-engineer e @qa)
- [x] Cobertura estatistica por severidade e area
- [x] NFRs de seguranca (SQL injection, secrets, RLS) parcialmente cobertos

### 1.2 Gaps Identificados

| # | Gap | Severidade | Impacto | Recomendacao |
|---|-----|------------|---------|-------------|
| GAP-01 | Ausencia total de debito de CI/CD | HIGH | Sem pipeline automatizado, qualquer correcao e manual e propensa a erro. 64k linhas sem lint, sem type check, sem testes automatizados em CI. | Adicionar debito: "Ausencia de CI/CD pipeline (lint, type check, testes em PR)" como MEDIUM/HIGH. |
| GAP-02 | Sem debito de backup e disaster recovery | HIGH | 4.1 GB de dados criticos de licitacao sem estrategia documentada de backup. Uma corrupcao de banco perde todo o DataLake. | Adicionar debito: "Sem backup automatizado do PostgreSQL (4.1 GB)" como HIGH. Verificar se existe pg_dump schedule via cron/systemd. |
| GAP-03 | Sem debito de documentacao e onboarding | MEDIUM | README existe mas nao ha documentacao de setup, runbook, ou arquitetura de deploy. Qualquer novo desenvolvedor levaria dias para entender o sistema. | Adicionar debito: "Documentacao insuficiente para onboarding e operacao" como MEDIUM. |
| GAP-04 | Observabilidade limitada ao healthcheck | MEDIUM | TD-SYS-015 cobre healthcheck, mas faltam: logging estruturado com correlation IDs, metricas de cobertura historicas, alertas de falha de crawl, dashboard de status. | Expandir TD-SYS-015 para incluir logging estruturado e metricas, ou criar debito separado para observabilidade. |
| GAP-05 | Seguranca alem de secrets e SQL injection | MEDIUM | Cobertos: SQL injection (parcial), DB password hardcoded, RLS. Nao cobertos: rate limiting em APIs externas, cust exposure de API keys (OpenAI tem custo), firewall de aplicacao, audit trail de acesso. | Adicionar nota no risk assessment sobre expansao futura de seguranca ou debito MEDIUM para "Falta de security hardening em VPS". |

### 1.3 O que NAO esta no assessment mas deveria estar

1. **TD-CI-001: Ausencia de pipeline CI/CD** -- Nao ha GitHub Actions ou similar para lint (ruff), type check (mypy), ou testes automatizados. Toda mudanca e aplicada manualmente via SSH + git pull na VPS. Risco alto de regression silenciosa.
2. **TD-OPS-001: Sem backup automatizado do banco** -- 4.1 GB de dados sem backup documentado. Se a VPS perder o disco, todo o DataLake de 199K bids + 3.69M contratos e perdido.
3. **TD-DOC-001: Documentacao de setup e operacao insuficiente** -- README existe mas nao ha runbook, nem instrucoes de deploy, nem arquitetura de alto nivel para novos contribuidores.
4. **TD-OBS-001: Logging sem correlation IDs e sem agregacao centralizada** -- Atualmente usa logging basico do Python. Em caso de falha em pipeline de 7 steps, nao ha como correlacionar eventos entre scripts.
5. **TD-SEC-002: Falta de firewall de aplicacao e network hardening** -- PostgreSQL exposto em Hetzner sem firewall de aplicacao (mencionado como ATENCAO no system-architecture.md mas nao como debito formal).

---

## 2. Cross-Cutting Risks

| Risco | Areas Afetadas | Debites Relacionados | Probabilidade | Impacto | Mitigacao |
|-------|---------------|---------------------|---------------|---------|-----------|
| Refatoracao de crawler quebra producao sem testes para detectar | Crawl System, Database | TD-SYS-009, TD-SYS-011, TD-SYS-016 | ALTA | CRITICO | Criar test suite para transformer.py (funcao pura) como primeira prioridade; congelar mudancas no monitor.py ate ter testes |
| Correcao de migrations pode perder dados se mal executada | Database Schema, DataLake | TD-DB-01, TD-DB-02, TD-DB-13 | MEDIA | CRITICO | Executar `pg_dump --schema-only` primeiro; trabalhar em copia do banco; documentar rollback para cada migration corretiva |
| BidsCrawler pode ja estar quebrado em producao (imports ingestion/) | Crawl System | TD-SYS-001, TD-SYS-016 | MEDIA | ALTO | Verificar experimentalmente se o BidsCrawler executa; se nao, documentar como dead code e remover ou criar package ingestion/ |
| Duas implementacoes PNCP divergem em dados processados | Crawl System, Intel Pipeline | TD-SYS-016, TD-DB-04 | MEDIA | ALTO | Audit de resultados entre as duas implementacoes; consolidar para uma unica via antes de novas features |
| YAML de config (2.116 linhas) com erro silencioso corrompe analise setorial | Intel Pipeline, Config | TD-SYS-013 | BAIXA | ALTO | Adicionar schema validation com Pydantic ou JSON Schema ASAP |
| DELETE fisico do purge remove dados irreversivelmente | Database, Reporting | TD-DB-14 | BAIXA | ALTO | Adicionar soft-delete com retention policy antes do proximo purge agendado |
| Senha do DB hardcoded em git exposta se repositorio for comprometido | Security, Database | TD-DB-05, Seguranca | BAIXA | ALTO | Rotacionar senha imediatamente, migrar para .env, remover do historico git (ou aceitar risco para senha local) |

---

## 3. Dependency Validation

### 3.1 Ordem de Resolucao

A ordem proposta na matriz consolidada (Secao 5 do DRAFT) esta correta em linhas gerais, mas sugiro os seguintes ajustes:

| Prioridade Atual | Ajuste | Justificativa |
|-----------------|--------|---------------|
| P1: TD-SYS-001 (imports quebrados) | Manter | Independente, quick win de 4h |
| P2: TD-DB-01 (migrations divergentes) | Manter | Pre-requisito para TD-DB-02, TD-DB-13, TD-DB-09 |
| P3: TD-SYS-009 (ausencia de testes) | **Subir para P1 executando em paralelo** | Nao depende de ninguem; comecar com transformer.py e entity matching enquanto P1 e P2 sao resolvidos |
| P4: TD-DB-08 (missing GIN index) | Manter | Independente, quick win de 2h |
| P5: TD-SYS-003 (type hints) | Manter | Independente, mas baixo impacto sozinho |
| P6: TD-DB-02 (migrations 009-012) | **Depende de TD-DB-01** | Nao aplicar antes de estabilizar o schema baseline |
| P7: TD-SYS-011 (monitor.py refactor) | Manter | **Depende de TD-SYS-009** (nao refatorar 687 linhas sem testes) |
| P8: TD-SYS-016 (consolidar crawlers) | **Depende de TD-SYS-001 + TD-SYS-009** | So faz sentido apos BidsCrawler funcional e com testes |

**Ordem recomendada:**

```
FASE 0 (Quick Wins, paralelo):
  ├── TD-SYS-001 (fix imports)
  ├── TD-DB-08 (GIN index)
  ├── TD-SYS-009 (iniciar test suite com transformer.py)
  └── TD-DB-05 (mover senha para .env)

FASE 1 (Schema Stabilization):
  └── TD-DB-01 (regenerar migrations do schema real)
      └── TD-DB-02 (aplicar 009-012 adaptadas)
      └── TD-DB-13 (corrigir schema divergence)

FASE 2 (Refactoring Safe):
  └── TD-SYS-009 (expandir test suite)
      └── TD-SYS-011 (refatorar monitor.py)
      └── TD-SYS-016 (consolidar crawlers)

FASE 3 (Quality):
  ├── TD-SYS-003 (type hints)
  ├── TD-SYS-008 (constantes para settings.py)
  ├── TD-SYS-013 (schema validation YAML)
  └── TD-DB-04 (otimizar upsert row-by-row)

FASE 4 (Resilience):
  ├── TD-SYS-014 (API key renewal)
  ├── TD-SYS-015 (healthcheck + observabilidade)
  ├── TD-DB-03 (TTL enforcement)
  ├── TD-DB-14 (soft-delete purge)
  └── TD-DB-11 (HNSW expression fix)

FASE 5 (Polish):
  └── Items LOW restantes
```

### 3.2 Bloqueios Identificados

| Bloqueio | Debites Afetados | Descricao | Desbloqueio |
|----------|-----------------|-----------|-------------|
| Schema baseline precisa ser estabelecido | TD-DB-02, TD-DB-09, TD-DB-13 | Nao da para aplicar migrations 009-012 ou adicionar CHECK constraints antes de saber qual e o schema real | Executar `pg_dump --schema-only` e criar migrations v2 |
| Zero testes impedem refactoring seguro | TD-SYS-011, TD-SYS-016 | Monitor.py de 687 linhas e a consolidacao de crawlers sao operacoes de alto risco sem testes | Comecar test suite com transformer.py (funcao pura, zero dependencias) |
| BidsCrawler pode estar inoperante | TD-SYS-001, TD-SYS-016 | Se BidsCrawler nao executa, a consolidacao (TD-SYS-016) pode ser apenas remocao de dead code | Verificar experimentalmente se roda; se nao, documentar como dead code |

### 3.3 Dependencias Circulares

Nao foram identificadas dependencias circulares entre os debitos. A matriz de dependencias no DRAFT (Secao 5) esta correta e sem ciclos.

---

## 4. Test Strategy

### 4.1 Testes por Categoria de Debito

| Categoria | Tipo de Teste | Ferramenta | Criterio de Aceite |
|-----------|--------------|------------|-------------------|
| Schema/DB | Migration test (apply + rollback) | pytest + pg_dump | Migrations V2 aplicam e revertem sem perda de dados |
| Crawl (transformer) | Unit test (funcao pura) | pytest | 100% das funcoes de transform testadas com dados reais amostrados |
| Crawl (entity matching) | Unit test + Integration test | pytest + rapidfuzz | 3-level cascade testada com 100+ casos de edge (CNPJ, nome, fuzzy) |
| SQL Performance | EXPLAIN ANALYZE em staging | psql + pg_stat_statements | Zero sequential scans em tabelas > 100K registros; HNSW index confirmado via EXPLAIN |
| Seguranca | Secret scan | detect-secrets / trufflehog | Zero secrets hardcoded no repositorio |
| Config YAML | Schema validation | Pydantic + pytest | 100% dos YAMLs validados contra schema tipado |
| Regression | Smoke test end-to-end | pytest | Pipeline de crawl + intel executado em staging com dataset reduzido |

### 4.2 Metricas de Qualidade

| Metrica | Baseline Atual | Target Pos-Resolucao |
|---------|---------------|---------------------|
| Cobertura de testes (linhas) | 0% | >= 40% (core modules: transformer, entity matching, loader) |
| Debitos CRITICAL | 3 | 0 |
| Debitos HIGH | 5 | <= 2 |
| Debitos MEDIUM | 14 | <= 5 |
| Sequential scans em tabelas > 100K | 2+ (pncp_supplier_contracts, pncp_raw_bids) | 0 |
| Migrations divergentes | 12/12 | 0/12 |
| Secrets hardcoded no codigo | 1+ (smartlic_local) | 0 |
| CI/CD pipeline | Ausente | Presente (lint + type check + test) |
| Backup automatizado | Ausente | Presente (pg_dump diario) |

### 4.3 Testes de Regression (Cenarios que NAO podem quebrar)

1. **Pipeline de crawl completo:** monitor.py --source pncp --full deve completar upsert sem erros
2. **Entity matching 3-level cascade:** Matching de bids existentes deve produzir os mesmos resultados apos refatoracao
3. **Intel pipeline end-to-end:** intel_pipeline.py --cnpj X deve produzir relatorio Excel + PDF
4. **Search datalake:** search_datalake() RPC com filtros variados deve retornar resultados consistentes
5. **Dedup por content_hash:** Ingestao do mesmo registro duas vezes nao deve duplicar dados
6. **Purge com soft-delete:** Apos migrar para soft-delete, dados marcados como inativos devem ser invisiveis para queries normais

---

## 5. Severity Adjustments

| ID | Severidade DRAFT | Severidade QA | Justificativa |
|----|-----------------|--------------|---------------|
| TD-SYS-012 (fallback difflib) | LOW | **MEDIUM** | Fallback silencioso degrada qualidade do matching sem nenhum alerta. Em 2.085 orgaos, matching de baixa qualidade pode fazer o sistema perder licitacoes relevantes. Deve ao menos gerar Warning via logging. |
| TD-DB-05 (senha hardcoded) | MEDIUM | MEDIUM (mantido) | Senha "smartlic_local" parece ser apenas local dev. Se essa mesma senha for usada em producao, subiria para HIGH. Verificar com o lead. |
| TD-DB-10 (ingestion_checkpoints) | LOW | **MEDIUM**** | Tabela com 0 registros significa que crawlers NAO SAO resumeveis. Em caso de falha no meio de um crawl de 2.085 orgaos, tudo recomeca do zero. Perda de eficiencia operacional significativa. |
| TD-SYS-004 (cache IBGE module-level) | MEDIUM | **HIGH** | Estado global mutavel em modulo compartilhado entre crawlers async. Race condition com concorrencia async (Semaphore) pode corromper cache ou causar comportamento imprevisivel. |

**Nota:** As severidades revisadas aumentam o total estimado em ~2-4h adicionais para enderecar os ajustes.

---

## 6. Quality Observations

### 6.1 Documentacao

A documentacao produzida nas Fases 1-2 e de alta qualidade:

| Documento | Qualidade | Observacoes |
|-----------|-----------|-------------|
| `system-architecture.md` | EXCELENTE | Cobre arquitetura, fluxos, dependencias, seguranca, anti-padroes. 606 linhas de analise aprofundada. |
| `DB-AUDIT.md` | EXCELENTE | Audit completo de schema, seguranca, performance, migrations. Metricas claras. |
| `SCHEMA.md` | EXCELENTE | Documentacao detalhada do schema real com ER textual, indexes, triggers, funcoes. |
| `technical-debt-DRAFT.md` | BOM | Organizado e claro, mas com 5 gaps de escopo e 2 contradicoes a resolver. |

### 6.2 Consistencia (Contradicoes entre documentos fonte)

Duas contradicoes importantes entre system-architecture.md e DB-AUDIT.md que o DRAFT reconhece mas precisa resolver:

**Contradicao 1: SQL Injection Risk**
- `system-architecture.md` (sec. 10): Classifica SQL queries em monitor.py como **MEDIO** risco de SQL injection
- `DB-AUDIT.md` (sec. 2): Classifica como **Baixo risco** (queries parameterized, JSON interno)
- **Posicao QA:** Concordo com DB-AUDIT. O `%s` placeholder com JSON gerado internamente e seguro. No entanto, a funcao `_match_entities_cascade` usa f-strings na linha 67-68 para queries SQL -- isso SIM e um risco que precisa de auditoria especifica. Recomendo auditar essa funcao em particular.

**Contradicao 2: ORM vs Raw SQL**
- `system-architecture.md` (sec. 7.4): Trata ausencia de ORM como anti-padrao ("Acoplamento DB, sem type safety")
- `DB-AUDIT.md` (sec. 2): Aceita como seguro para single-user
- **Posicao QA:** Para single-user com Python puro, raw SQL com psycopg2 e aceitavel e pragmatico. Adicionar ORM (SQLAlchemy) seria um investimento significativo sem retorno claro para o cenario atual. Removeria do anti-pattern ou reclassificaria como INFORMATIVO (nao como debito).

### 6.3 Traceability

Os debitos sao rastreaveis ate sua origem nos documentos fonte:

- **TD-SYS-001 a TD-SYS-016:** Originam-se de `system-architecture.md` (secoes 7.4 Anti-Padroes e 8 Tech Debt Inventory)
- **TD-DB-01 a TD-DB-14:** Originam-se de `DB-AUDIT.md` (secoes 1 Issues, 2 Security, 3 Performance, 4 DB Debt Inventory)
- Os IDs usam nomenclatura clara (TD-SYS e TD-DB) e cada debito referencia arquivo/linha especifica
- A matriz consolidada (secao 5) mapeia dependencias entre debitos corretamente

**Melhoria sugerida:** Adicionar coluna "Documento Fonte" na matriz consolidada para rastreabilidade direta (ex: "system-architecture.md sec 8") sem precisar consultar as tabelas originais.

---

## 7. Final Recommendations

### Acoes Obrigatorias (antes de seguir para Fase 8)

1. **Resolver as 2 contradicoes** entre system-architecture.md e DB-AUDIT.md (SQL injection risk e ORM anti-pattern) -- documentar a posicao final do projeto.

2. **Adicionar os 5 novos debitos:** TD-CI-001 (CI/CD), TD-OPS-001 (backup), TD-DOC-001 (documentacao), TD-OBS-001 (logging/observabilidade), TD-SEC-002 (network hardening). Se a decisao for nao incluir, documentar explicitamente o por que na secao de riscos.

3. **Aplicar os ajustes de severidade:** TD-SYS-012 (LOW -> MEDIUM), TD-SYS-004 (MEDIUM -> HIGH), TD-DB-10 (LOW -> MEDIUM). Recalcular a matriz com as horas extras.

4. **Ajustar ordem de resolucao** para refletir a Fase 0 paralela (quick wins + comeco de test suite simultaneos) conforme secao 3.1 deste review.

5. **Auditar `_match_entities_cascade` no monitor.py** para confirmar se as f-strings SQL (linhas 67-68) sao seguras ou sao vetor de SQL injection.

### Acoes Recomendadas

6. Adicionar coluna "Documento Fonte" na matriz consolidada para rastreabilidade direta.

7. Expandir a secao de riscos para incluir os riscos de cross-cutting identificados na secao 2 deste review.

8. Atualizar estimativa de esforco total: 105-125h + ~15-25h (5 novos debitos + ajustes de severidade) = **120-150h estimados**.

---

## Resumo

| Componente | Status |
|-----------|--------|
| Cobertura de debitos de sistema | 16/16 (bom) |
| Cobertura de debitos de database | 14/14 (bom) |
| Gaps de escopo identificados | 5 novos debitos (CI/CD, backup, docs, observabilidade, network) |
| Contradicoes entre docs fonte | 2 (SQL injection, ORM) |
| Ajustes de severidade | 3 upgrades (TD-SYS-012, TD-SYS-004, TD-DB-10) |
| Dependencias circulares | 0 |
| Bloqueios identificados | 3 (schema baseline, test suite, BidsCrawler status) |
| Estimativa ajustada | 120-150h (vs 105-125h original) |
| **Gate Decision** | **NEEDS WORK** -- aprovar apos ajustes dos 5 gaps e 2 contradicoes |

**Veredicto:** O assessment e 80% completo e bem estruturado. Os 5 gaps de escopo sao enderecaveis em 1-2 horas de edicao. As 2 contradicoes entre documentos fonte precisam de resolucao de posicao. Recomendo: (1) incorporar os ajustes deste review, (2) submeter para Fase 8 (Assessment Final) com @architect, (3) garantir que os novos debitos de CI/CD e backup nao sejam esquecidos no plano de acao.

---

— Quinn, guardiao da qualidade

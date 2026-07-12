# Opportunity Intelligence Truth V1 — Plano de Execução

**Criado:** 2026-07-12
**Status:** Em execução
**Exit esperado:** PARTIAL (exit 2) — threshold 95% inalcançável sem múltiplas fontes adicionais

---

## 1. Baseline (FASE 0 — Auditoria)

### 1.1 Estado Atual do Projeto

| Dimensão | Valor |
|----------|-------|
| PostgreSQL | 254.884 bids, 3.689.859 contratos, 2.088 entes SC |
| Fontes registradas | 12 (source registry) |
| Fontes com dados reais | 4 (pncp, mides_bigquery, compras_gov, pcp) |
| Cobertura entes 200km | 39% (807/2.085 total, ~488/1.093 no raio) |
| Históricos/vencedores | 36,98% (404/1.093) |
| Vincendos (abertas) | 0% — NÃO EXISTE tracking de oportunidades abertas |
| Preço praticado | NOT_READY |
| Deságio | NOT_READY |
| Win rate | NOT_READY |
| Testes | 1.041 pass, 16 fail, 90 skipped |
| Ruff | 253 erros |
| Ruff format | 35 arquivos não formatados |
| Cobertura de código | 13% |

### 1.2 O Que Existe (Reutilizável)

| Componente | Arquivo | Status |
|-----------|---------|--------|
| Source registry | `scripts/crawl/registry.py` | 12 fontes, reutilizável |
| PNCP crawler | `scripts/crawl/pncp_crawler_adapter.py` | Funcional, API v3 |
| Contracts crawler | `scripts/crawl/contracts_crawler.py` | Funcional, PNCP contratos |
| Entity matcher | `scripts/matching/entity_matcher.py` | 3 níveis, testado |
| Evidence ledger | `db/migrations/024_coverage_evidence_ledger.sql` | Schema pronto |
| Datalake CLI | `scripts/local_datalake.py` | search, supplier, stats |
| Monitor CLI | `scripts/crawl/monitor.py` | Orquestrador multi-source |
| Consulting readiness | `scripts/consulting_readiness.py` | Manifest + gaps |
| Infrastructure | retry, circuit breaker, rate limiter, checkpoint | Reutilizável |
| DB migrations | `db/migrations/` (32 arquivos) | Base para novas migrations |
| Coverage views | `v_coverage_summary`, `v_source_health`, `v_latest_evidence` | Reutilizável |

### 1.3 O Que Falta (Opportunity Intelligence)

- **Sistema de tracking de licitações abertas** (vincendas/upcoming/open)
- **Modelo de dados de oportunidade** — status canônico, ranking, explicação
- **CLI de oportunidades** — list, show, explain, coverage, source-health, update, export
- **Deduplicação cross-source** — ID oficial, número PNCP, órgão+processo+edital
- **Ranking explicável** — GO/REVIEW/NO_GO, score 0-100, fatores, regras, confiança
- **Normalização de status** — open, upcoming, closed, suspended, revoked, annulled, failed, unknown
- **Manifestos de cobertura** — opportunity-coverage-manifest.json, gaps.csv, source-health.csv
- **Testes** — parsing, estados, dedup, paginação, cobertura, success_zero, proveniência, idempotência

---

## 2. Estratégia

### 2.1 Abordagem

**Fonte primária:** PNCP API (nacional oficial) — já crawling, expandir para tracking de status/vencimento.

**Fonte complementar SC:** DOM-SC (Diário Oficial dos Municípios de SC) — cobre editais municipais dentro do raio 200km.

**Ganho marginal:** Cada fonte adiciona entes não cobertos pela outra. PNCP cobre entes que publicam no sistema federal. DOM-SC cobre entes que só publicam no diário municipal.

### 2.2 Threshold Realista

- **95% inviável** com 2 fontes. Coverage atual de contratos históricos é 37% após 6+ fontes.
- **Meta realista:** 40-50% cobertura de oportunidades abertas com PNCP + DOM-SC.
- **Próximo passo:** Adicionar fontes incrementais (ComprasGov, SC Compras, PCP, TCE-SC).
- **Teto estimado:** ~70-80% com todas as 12 fontes ativas.

### 2.3 Decisões de Design

1. **Schema em `db/migrations/`** — seguir padrão existente, numerar como 027+
2. **Reuso de crawlers existentes** — `pncp_crawler_adapter.py`, `contracts_crawler.py`
3. **Novo módulo `scripts/opportunity_intel/`** — domínio isolado, sem acoplamento com contract_intel
4. **CLI unificada** — `scripts/opportunity_intel/cli.py` com subcomandos
5. **PostgreSQL como source of truth** — sem SQLite adicional
6. **Fail-closed** — nunca marcar open só por recência; status calculado com evidência
7. **Local-first** — sem dependência de serviços externos para operação core
8. **Exa MCP obrigatório** para pesquisa web — nunca WebSearch nativo

---

## 3. Arquitetura

### 3.1 Fluxo de Dados

```
Fonte Oficial (PNCP API / DOM-SC API)
  → Fetch (httpx, retry/backoff, rate limit, checkpoint)
  → Raw Zone (JSON em disco? Não — direto para memória)
  → Normalização (transformer: padronizar campos, status, datas)
  → PostgreSQL (upsert com content_hash)
  → Deduplicação (ID oficial → número PNCP → órgão+processo+edital)
  → Status Canônico (calcular de múltiplos campos)
  → Ranking (regras determinísticas)
  → CLI (list, show, explain, coverage, source-health, update, export)
  → Manifesto (JSON + CSV)
```

### 3.2 Schema — Nova Tabela Principal

```sql
CREATE TABLE opportunity_intel (
    id              BIGSERIAL PRIMARY KEY,
    -- Identidade
    source          TEXT NOT NULL,              -- fonte (pncp, dom_sc, etc.)
    source_id       TEXT NOT NULL,              -- ID na fonte original
    source_url      TEXT,                       -- URL original
    content_hash    TEXT NOT NULL UNIQUE,       -- dedup hash
    -- Execução
    crawl_batch_id  TEXT,                       -- batch de ingestão
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Ente/Órgão
    orgao_cnpj      TEXT,                       -- CNPJ do órgão
    orgao_nome      TEXT,                       -- Nome do órgão
    ente_federativo TEXT,                       -- União, Estado, Município
    uf              TEXT NOT NULL,              -- UF
    municipio       TEXT,                       -- Município
    codigo_ibge     TEXT,                       -- Código IBGE
    -- Processo
    numero_processo TEXT,                       -- Número do processo
    numero_edital   TEXT,                       -- Número do edital
    modalidade      TEXT,                       -- Modalidade
    modalidade_id   INTEGER,                    -- ID da modalidade
    -- Objeto
    objeto          TEXT NOT NULL,              -- Descrição do objeto
    categoria       TEXT,                       -- Categoria (obra, serviço, compra)
    -- Valor
    valor_estimado  NUMERIC(18,2),              -- Valor estimado
    valor_homologado NUMERIC(18,2),             -- Valor homologado (se disponível)
    valor_semantica TEXT,                       -- 'estimado', 'homologado', 'maximo', 'referencia'
    -- Datas
    data_publicacao TIMESTAMPTZ,                -- Data de publicação
    data_abertura   TIMESTAMPTZ,                -- Data de abertura/sessão
    data_encerramento TIMESTAMPTZ,              -- Data de encerramento
    data_homologacao TIMESTAMPTZ,               -- Data de homologação
    -- Status
    status_fonte    TEXT,                       -- Status original da fonte
    status_canonico TEXT NOT NULL,              -- open, upcoming, closed, suspended, revoked, annulled, failed, unknown
    status_motivo   TEXT,                       -- Por que este status foi atribuído
    status_data     TIMESTAMPTZ,                -- Quando o status foi determinado
    -- Documentos
    link_edital     TEXT,                       -- Link do edital
    link_anexos     TEXT[],                     -- Links de anexos
    -- Qualidade
    qualidade_score INTEGER DEFAULT 0,          -- 0-100
    qualidade_fatores JSONB DEFAULT '{}',       -- fatores positivos/negativos
    dados_ausentes  TEXT[],                     -- campos obrigatórios ausentes
    -- Ranking
    ranking         TEXT,                       -- GO, REVIEW, NO_GO
    ranking_score   INTEGER DEFAULT 0,          -- 0-100
    ranking_fatores JSONB DEFAULT '{}',         -- fatores do ranking
    ranking_regras  TEXT[],                     -- regras aplicadas
    ranking_confianca TEXT,                     -- HIGH, MEDIUM, LOW
    -- Proveniência
    proveniencia    JSONB DEFAULT '{}',         -- origem de cada campo
    -- Metadados
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    metadata        JSONB DEFAULT '{}'
);
```

### 3.3 Índices

```sql
CREATE INDEX idx_oi_source ON opportunity_intel(source);
CREATE INDEX idx_oi_orgao_cnpj ON opportunity_intel(orgao_cnpj);
CREATE INDEX idx_oi_uf ON opportunity_intel(uf);
CREATE INDEX idx_oi_municipio ON opportunity_intel(municipio);
CREATE INDEX idx_oi_codigo_ibge ON opportunity_intel(codigo_ibge);
CREATE INDEX idx_oi_status ON opportunity_intel(status_canonico);
CREATE INDEX idx_oi_data_abertura ON opportunity_intel(data_abertura);
CREATE INDEX idx_oi_data_encerramento ON opportunity_intel(data_encerramento);
CREATE INDEX idx_oi_modalidade ON opportunity_intel(modalidade);
CREATE INDEX idx_oi_ranking ON opportunity_intel(ranking);
CREATE INDEX idx_oi_numero_processo ON opportunity_intel(numero_processo);
CREATE INDEX idx_oi_numero_edital ON opportunity_intel(numero_edital);
-- Dedup: órgão + processo + edital
CREATE UNIQUE INDEX idx_oi_dedup_orgao_processo_edital
    ON opportunity_intel(orgao_cnpj, numero_processo, numero_edital)
    WHERE numero_processo IS NOT NULL AND numero_edital IS NOT NULL;
-- Full-text search
CREATE INDEX idx_oi_objeto_gin ON opportunity_intel USING gin(to_tsvector('portuguese', objeto));
```

### 3.4 Tabelas de Suporte

```sql
-- Checkpoints de paginação
CREATE TABLE opportunity_checkpoints (
    source      TEXT NOT NULL,
    scope_key   TEXT NOT NULL,
    last_page   INTEGER,
    last_date   DATE,
    last_id     TEXT,
    records_fetched INTEGER DEFAULT 0,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (source, scope_key)
);

-- Execuções de crawl
CREATE TABLE opportunity_runs (
    id              BIGSERIAL PRIMARY KEY,
    source          TEXT NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ,
    records_fetched INTEGER DEFAULT 0,
    records_new     INTEGER DEFAULT 0,
    records_updated INTEGER DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'running',
    error_message   TEXT,
    metadata        JSONB DEFAULT '{}'
);

-- Cobertura por ente/fonte (espelho do entity_coverage mas para oportunidades)
CREATE TABLE opportunity_coverage (
    entity_id       INTEGER NOT NULL REFERENCES sc_public_entities(id),
    source          TEXT NOT NULL,
    period_start    DATE,
    period_end      DATE,
    pages_expected  INTEGER,
    pages_processed INTEGER,
    last_attempt    TIMESTAMPTZ,
    result          TEXT,  -- success, success_zero, partial, error
    count_obtained  INTEGER DEFAULT 0,
    count_open      INTEGER DEFAULT 0,
    freshness       INTERVAL,
    error_message   TEXT,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (entity_id, source)
);
```

---

## 4. Fases de Execução

### Fase 1: Fundação (Schema + Infra)
- [ ] Migration 027: `opportunity_intel` + tabelas de suporte
- [ ] Migration 028: índices e constraints
- [ ] `scripts/opportunity_intel/__init__.py`
- [ ] `scripts/opportunity_intel/models.py` — dataclasses
- [ ] `scripts/opportunity_intel/transformer.py` — normalização
- [ ] `scripts/opportunity_intel/dedup.py` — deduplicação
- [ ] `scripts/opportunity_intel/status.py` — status canônico
- [ ] `scripts/opportunity_intel/ranking.py` — ranking explicável

### Fase 2: Crawlers (Adaptados + Novos)
- [ ] `scripts/opportunity_intel/crawler_base.py` — classe base com retry/backoff/rate limit/checkpoint
- [ ] Adaptar PNCP crawler para oportunidades abertas (foco: status, vencimento, modalidades abertas)
- [ ] DOM-SC crawler para editais (foco: municípios SC no raio 200km)
- [ ] Testes unitários para cada crawler

### Fase 3: Ingestão + Pipeline
- [ ] `scripts/opportunity_intel/ingest.py` — fetch → transform → upsert
- [ ] `scripts/opportunity_intel/pipeline.py` — orquestração multi-source
- [ ] Integração com evidence ledger existente
- [ ] Teste de integração PostgreSQL

### Fase 4: CLI
- [ ] `scripts/opportunity_intel/cli.py` — subcomandos list, show, explain, coverage, source-health, update, export
- [ ] Formatação rica (rich Tables)
- [ ] Export JSON/CSV

### Fase 5: Manifestos + Validação
- [ ] `scripts/opportunity_intel/manifest.py` — geração de manifestos de cobertura
- [ ] Testes completos (parsing, estados, dedup, paginação, cobertura, success_zero, proveniência, idempotência)
- [ ] Smoke test real (opt-in fetch → persistência → consulta → invariantes)
- [ ] Ruff, mypy, bandit

### Fase 6: Documentação
- [ ] Atualizar README.md
- [ ] Atualizar CLAUDE.md
- [ ] Relatório final

---

## 5. Fontes de Dados Pesquisadas

### 5.1 PNCP (fonte primária nacional)
- **API:** `https://pncp.gov.br/api/consulta/v1`
- **Endpoint:** `/contratacoes` — lista licitações com filtros
- **Cobertura:** Todas as esferas (F, E, M, D) que aderiram ao PNCP
- **Status:** Já implementado crawler base. Expandir para tracking de status e datas de vencimento.
- **Paginação:** 500/page, page-based
- **Limitações:** Só entes que aderiram. Adesão voluntária para municípios.

### 5.2 DOM-SC (fonte complementar SC)
- **API:** `https://diariomunicipal.sc.gov.br/?r=remote/list`
- **Cobertura:** Municípios de SC que usam o sistema DOM-SC
- **Status:** Crawler existente mas com 0 dados ingeridos. Requer credenciais.
- **Credenciais:** DOM_SC_CPF, DOM_SC_CNPJ, DOM_SC_API_KEY (já no .env)
- **Limitações:** Só municípios que usam DOM-SC. Não cobre estado nem federação.

---

## 6. Critérios de Aceitação

1. **Pipeline funcional:** source → fetch → raw → normalize → DB → dedup → status → CLI
2. **2 fontes ativas:** PNCP + DOM-SC com dados reais em PostgreSQL
3. **CLI funcional:** 7 subcomandos operacionais
4. **Testes:** unitários + integração + smoke
5. **Manifestos:** 3 arquivos de output gerados
6. **Exit code:** 0 se cobertura comprovada, 2 se abaixo do threshold
7. **Zero regressões:** ruff, mypy, testes existentes passando

---

## 7. Riscos

| Risco | Mitigação |
|-------|-----------|
| DOM-SC sem dados (0 histórico) | Diagnosticar crawler, verificar credenciais, fallback para scraping |
| PNCP não tem filtro por data de abertura futuro | Usar data_publicacao recente + filtrar status no pós-processamento |
| Threshold 95% inalcançável | Entregar PARTIAL com exit 2, documentar gaps e próximas fontes |
| 16 testes já quebrados | Não introduzir novas falhas; documentar falhas pré-existentes |
| Duplicação cross-source complexa | Implementar dedup conservador (4 níveis), nunca merge automático |

---

## 8. Entregas

| Artefato | Path |
|----------|------|
| Plano | `docs/workplans/opportunity-intelligence-truth-v1-plan.md` |
| Migrations | `db/migrations/027_opportunity_intel.sql`, `028_opportunity_indexes.sql` |
| Módulo Python | `scripts/opportunity_intel/` (~10 arquivos) |
| Testes | `tests/test_opportunity_*.py` (~5 arquivos) |
| Manifestos | `output/readiness/opportunity-coverage-manifest.json` |
| Gaps CSV | `output/readiness/opportunity-coverage-gaps.csv` |
| Source Health | `output/readiness/opportunity-source-health.csv` |
| Relatório Final | `docs/reports/opportunity-intelligence-truth-v1-final.md` |

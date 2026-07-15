# Cobertura PNCP por Ente-Alvo — 2026-07-15

## 1. Status da API (online/offline, endpoints)

**Banco PostgreSQL (pncp_datalake): OFFLINE**

- Host: `127.0.0.1:5433` — timeout de conexao.
- Toda analise abaixo usa artefatos em disco (manifests, checkpoints, CSVs).

**API PNCP online** (ultimo checkpoint: 2026-07-11T15:40Z)

### Endpoints PNCP conhecidos

| Endpoint | URL Base | Uso |
|----------|----------|-----|
| Publicacao (licitacoes) | `GET /api/consulta/v1/contratacoes/publicacao` | Crawler principal (`pncp_crawler_adapter.py`) |
| Proposta (abertas) | `GET /api/consulta/v1/contratacoes/proposta` | `PncpOpportunityCrawler` |
| Contratos | `GET /api/consulta/v1/contratos` | `contracts_crawler.py` |
| ARP (Atas) | `GET /api/consulta/v1/atas` | `PncpArpCrawler` |
| PCA (Planos) | `GET /api/consulta/v1/pca` | `PncpPcaCrawler` |
| Detalhes compra | `GET /api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{seq}` | `pncp_crawler_adapter.fetch_compra_detail` |
| Itens compra | `GET /api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{seq}/itens` | `pncp_crawler_adapter.fetch_compra_items` |
| Documentos | `GET /api/pncp/v1/orgaos/{cnpj}/compras/{ano}/{seq}/arquivos` | `pncp_crawler_adapter.fetch_compra_documents` |

Base padrao: `https://pncp.gov.br/api/consulta/v1` (configuravel via `PNCP_CONSULTA_BASE`)

---

## 2. Inventario de Crawlers PNCP

| Crawler | Arquivo | Source | Endpoint API | Page Size | Max Pages | Filtros | Periodicidade | Upsert Table |
|---------|---------|--------|-------------|-----------|-----------|---------|---------------|-------------|
| Licitacoes (adaptador sync) | `pncp_crawler_adapter.py` | pncp | `/contratacoes/publicacao` | 50 (max) | 200 | dataInicial/Final, modalidade, UF, municipio, CNPJ | full/incremental | `pncp_raw_bids` |
| Licitacoes abertas (async) | `pncp_crawler.py` (opportunity_intel) | pncp | `/contratacoes/proposta` | 50 | 200 | UF=SC, modalidade, data | sob demanda | `pncp_opportunities` |
| Contratos | `contracts_crawler.py` | contracts | `/contratos` | 500 | 10000 | dataInicial/Final | full/incremental/backfill_3y | `pncp_supplier_contracts` |
| ARP (Atas) | `pncp_arp_crawler.py` | pncp_arp | `/atas` | 50 | 10 | UF, data, pagina | incremental 2x/dia | `pncp_raw_atas` |
| PCA | `pncp_pca_crawler.py` | pncp_pca | `/pca` | 50 | 10 | UF, anoExercicio | semanal | `pncp_raw_pca` |

### Cliente HTTP (async)

| Arquivo | Descricao |
|---------|-----------|
| `scripts/crawl/async_client.py` | Implementacao real: `AsyncPNCPClient` com httpx, semaforo (max 10 concorrentes), rate limiting Redis+local, health canary (5s timeout), retry exponencial |
| `scripts/crawl/clients/pncp/async_client.py` | **STUB** — `raise NotImplementedError` |
| `scripts/crawl/clients/pncp/retry.py` | **STUB** — apenas definicoes de tipos |
| `scripts/crawl/clients/pncp/circuit_breaker.py` | **STUB** — `_StubCircuitBreaker` com `is_degraded: bool = False` fixo |
| `scripts/crawl/clients/pncp/_parallel_mixin.py` | **STUB** — mixin vazio |

**A instalacao real esta em `scripts/crawl/async_client.py`. Os stubs em `clients/pncp/` sao apenas para compatibilidade de imports.**

---

## 3. Analise de Paginacao e Limites

### Licitacoes (`/publicacao`)

- **Page size:** 50 (maximo permitido pela API PNCP)
- **Max pages:** 200 (configuravel via `PNCP_MAX_PAGES`)
- **Limite por query:** 50 × 200 = 10.000 registros por combinacao (modalidade + janela de datas)
- **Janela segura:** 7 dias (`PNCP_SAFE_WINDOW_DAYS`) — API PNCP retorna erro para periodos muito longos
- **Risco:** Se houver mais de 10.000 publicacoes em uma modalidade + 7 dias, dados serao truncados silenciosamente
- **Delay entre paginas:** 0.5s (`PNCP_REQUEST_DELAY`)
- **Retries:** 3 (`PNCP_MAX_RETRIES`)
- **Timeout:** 30s (`PNCP_READ_TIMEOUT`)
- **Circuit breaker:** STUB — `is_degraded` sempre `False`

### Contratos (`/contratos`)

- **Page size:** 500 (configuravel via `CONTRACTS_PAGE_SIZE`)
- **Max pages:** 10.000 (`CONTRACTS_MAX_PAGES`)
- **Limite por query:** 500 × 10.000 = 5.000.000 registros por janela
- **Janela:** 30 dias (`CONTRACTS_WINDOW_DAYS`)
- **Delay entre janelas:** 5s (`CONTRACTS_JANELA_DELAY`)
- **Risco:** Baixo — limites sao confortaveis para 3 anos de contratos SC

### ARP (`/atas`)

- **Max pages:** 10 (`INGESTION_ARP_MAX_PAGES`)
- **Janela:** 90 dias (`INGESTION_ARP_DAYS`)
- **Risco:** **Alto** — 10 pages × 50 items = 500 registros max por UF para 90 dias. Se houver mais de 500 atas no periodo, truncamento silencioso.

### PCA (`/pca`)

- **Max pages:** 10 (`INGESTION_PCA_MAX_PAGES`)
- **Ano corrente apenas**
- **Risco:** **Alto** — 10 pages × 50 items = 500 registros max por UF/ano. PCA de SC tem ~15k items/ano — cobertura dramaticamente insuficiente.

---

## 4. Campos Cobertos vs Faltantes

### Licitacoes — campos extraidos

| Campo | Presente? | Nota |
|-------|-----------|------|
| `numeroControlePNCP` | Sim | Usado como PK; quando ausente, gera synthetic_id via SHA256 |
| `orgaoEntidade.cnpj` | Sim | Normalizado para 14 digitos |
| `objetoCompra` | Sim | |
| `informacaoComplementar` | Sim | |
| `valorTotalEstimado` | Sim | |
| `modalidadeId` / `modalidadeNome` | Sim | |
| `situacaoCompraNome` | Sim | |
| `dataPublicacaoPncp` | Sim | |
| `dataAberturaProposta` | Sim | |
| `dataEncerramentoProposta` | Sim | |
| `linkSistemaOrigem` | Sim | ~86% populado |
| `unidadeOrgao.ufSigla` | Sim | Federal retorna vazio — fallback para UF consultada |
| `unidadeOrgao.municipioNome` | Sim | |
| `unidadeOrgao.codigoIbge` | Sim | |
| `linkProcessoEletronico` | **Sempre vazio** | CRIT-FLT-008 documentado |
| Anexos/documentos | **Nao baixados** | So metadados via `/arquivos` |
| Itens da compra | **Sob demanda** | So buscados via `/itens` para records com score < 80 |

### Contratos — campos extraidos

| Campo | Presente? | Nota |
|-------|-----------|------|
| `numeroControlePNCP` | Sim | PK |
| `orgaoEntidade.cnpj` | Sim | |
| `niFornecedor` | Sim | CNPJ do fornecedor vencedor |
| `objetoContrato` | Sim | Truncado em 500 caracteres |
| `valorGlobal` / `valorInicial` | Sim | |
| `dataAssinatura` | Sim | |
| `dataVigenciaInicio` | Sim | |
| `dataVigenciaFim` | **100% NULL no raio 200km** | 423.239 contratos sem data de fim — impossivel saber vigencia |
| `unidadeOrgao.ufSigla` | Sim | Fallback para CNPJ root quando vazio |

---

## 5. Matriz Ente x Publicacao

**Universo canonical** (da planilha semente):

| Categoria | Quantidade |
|-----------|-----------|
| Total linhas na planilha | 2.085 |
| Entes dentro do raio 200km | **1.093** |
| Entes fora do raio 200km | 992 |
| Nao resolvidos | 0 |
| CNPJ roots duplicados | Varios (registrados) |

**Cobertura de dados PNCP:**

| Metrica | Valor | Fonte |
|---------|-------|-------|
| Entes "monitorados" pelo PNCP | 1.093 (100%) | coverage_manifest.json |
| Entes COM dados de oportunidade | 436 (de 1.448 no gaps CSV) | opportunity-coverage-gaps.csv |
| Entes COM contratos | 404 (36,4% dos 1.093) | manifesto.json |
| Entes COM licitacoes abertas | 398 (36,4%) | coverage_manifest.json |
| Total registros de oportunidade | 96.682 | opportunity-coverage-manifest.json |
| Total licitacoes abertas | 46.555 | source-health.csv |
| Total contratos | 423.239 | coverage_manifest.json |
| Fornecedores distintos | 63.679 | manifesto.json |

**Discrepancia observada:** os CSVs de gaps listam 1.448 entes com `raio_200km=True`, mas o universo canonical diz 1.093. A diferenca (355 entes) provavelmente sao entidades com `raio_200km` flag no DB mas que estao fora do raio no universo canonical, ou entidades com coordenadas insuficientes.

---

## 6. Freshness (ultima coleta por crawler)

| Metrica | Valor |
|---------|-------|
| Entes com dados recentes (< 90 dias) | **515** (47,1%) |
| Entes com dados desatualizados (> 90 dias) | **33** (3,0%) |
| Entes com frescor desconhecido | **545** (49,9%) |
| Janela de freshness | 90 dias |

**Fonte unica:** PNCP responde por 100% dos 96.682 registros (`by_source: {pncp: {total: 96682}}`).

**Ultimo checkpoint conhecido:** 2026-07-11T15:40Z (4 dias atras) — apenas 1 CNPJ com 4 modalidades/scopes.

**Dados mais antigos:** 2022-03-15 (earliest `data_abertura` na source-health).

---

## 7. Falso Silenciosas Detectadas

### 7.1. ARP e PCA com `max_pages=10` — truncamento garantido

ARP e PCA usam `INGESTION_ARP_MAX_PAGES = 10` e `INGESTION_PCA_MAX_PAGES = 10` (stub `ingestion/config.py`). Com page size 50, cada UF pode capturar no maximo 500 registros por janela de 90 dias (ARP) ou por ano (PCA).

- PCA de SC tem ~15.000 items/ano — com 10 pages × 50 = 500, a cobertura e de apenas **~3,3%**.
- Dados parciais sao inseridos sem nenhum alerta de truncamento.

### 7.2. INGESTION_UFS = None no stub

O modulo `ingestion/config.py` define `INGESTION_UFS = None`. ARP e PCA dependem dessa variavel para saber quais UFs crawlear. Se `INGESTION_UFS` nao for definida via env var, ambos os crawlers podem falhar silenciosamente ou crawlear uma lista vazia.

### 7.3. Circuit breaker inoperante

`clients/pncp/circuit_breaker.py` e um stub: `_StubCircuitBreaker.is_degraded = False` fixo. O health canary em `async_client.py` chama `_circuit_breaker.record_failure()` em caso de falha, mas como e um stub, nao ha degradacao real — o sistema continua batendo na API mesmo quando ela esta instavel, gerando timeouts e erros 429 sem protecao.

### 7.4. 100% dos contratos no raio 200km sem data_fim_vigencia

Dos 423.239 contratos associados a entes dentro do raio 200km, **nenhum** tem `data_fim_vigencia` preenchida. Isso significa:
- Impossivel determinar contratos vigentes vs expirados
- Capacidade `expiring_contracts` tem cobertura 0%
- 48k contratos com data_fim preenchida no banco completo pertencem a entes FORA do raio 200km

### 7.5. Paginacao truncada em licitacoes (200 pages)

Com page size 50 e max pages 200, o limite e 10.000 records por modalidade+janela de 7 dias. Modalidades de alto volume (Pregao Eletronico, Dispensa) em janelas movimentadas podem exceder esse limite sem deteccao — o crawler simplesmente para de paginar.

### 7.6. Checkpoint minimalista

O unico checkpoint existente (`data/intel_pncp_checkpoint.json`) contem dados para apenas **1 CNPJ** com 4 scopes (modalidade 4, 4 datas diferentes, total 750 items). O diretorio `data/contracts_checkpoints/` esta vazio. Isso sugere que o sistema de checkpointing e reentrancia nao esta sendo utilizado de fato.

### 7.7. Cobertura declarada vs cobertura real

O manifest declara 100% de cobertura PNCP (1.093/1.093 entes "checked"). Porem:
- Apenas 436 entes tem dados reais de oportunidade
- Apenas 515 entes tem dados recentes (<90 dias)
- 545 entes tem frescor desconhecido (nunca verificados ou sem resultados)
- "Covered" no manifest significa "passou pelo pipeline de entity_coverage", nao "tem dados coletados"

### 7.8. Dependencia exclusiva de PNCP

100% dos registros de oportunidade vem de uma unica fonte (PNCP). Fontes complementares (DOM-SC, PCP, ComprasGov, SC Compras, Transparencia, TCE-SC) cobrem apenas os mesmos 459 entes (fora do raio 200km) ou nao tem dados. Isso cria um ponto unico de falha para cobertura.

---

## 8. Recomendacoes

### Imediatas (prioridade alta)

1. **Corrigir INGESTION_UFS** — Definir `INGESTION_UFS=["SC"]` (ou via env var) para ARP e PCA funcionarem. Validar que os crawlers estao produzindo dados.

2. **Aumentar max_pages de PCA e ARP** — PCA precisa de no minimo 300 pages para cobrir SC. ARP precisa de ao menos 50 pages para janelas de 90 dias.

3. **Corrigir circuito de degradacao** — Substituir o stub do circuit breaker pela implementacao real, ou pelo menos registrar falhas no health canary para alerta operacional.

### Curto prazo (ate 30 dias)

4. **Resolver data_fim_vigencia** — Investigar por que 100% dos contratos no raio 200km nao tem data de fim. Pode ser problema de normalizacao (campo errado) ou limitacao da API PNCP.

5. **Alertar paginacao truncada** — Adicionar warning quando `paginasRestantes > 0` mas `page >= PNCP_MAX_PAGES`, para identificar modalidades/janelas com dados incompletos.

6. **Diferenciar "monitored" de "has_data" no manifest** — O indicador de cobertura atual (100%) engana. Criar metricas separadas: cobertura de monitoramento vs cobertura de dados vs frescor.

7. **Instanciar checkpoint real** — Ativar checkpointing para backfill de 3 anos de contratos (diretorio vazio indica que nunca rodou).

### Medio prazo (ate 90 dias)

8. **Diversificar fontes** — Reduzir dependencia exclusiva de PNCP. Ativar DOM-SC, PCP, ComprasGov e outras fontes para entes no raio 200km.

9. **Auditar freshness** — Dos 545 entes com frescor desconhecido, investigar se nunca tiveram dados ou se os dados expiraram sem renovacao.

10. **Cobertura de ARP e PCA** — Validar se os crawlers estao produzindo dados e se as tabelas `pncp_raw_atas` e `pncp_raw_pca` estao sendo povoadas corretamente.

---

*Relatorio gerado em 2026-07-15. DB offline — baseado em artefatos de disco.*
*Auditoria: Agente C — Cobertura PNCP e Contratos.*

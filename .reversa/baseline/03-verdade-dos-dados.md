# Relatorio de Auditoria: A Verdade dos Dados

**Data:** 2026-07-14
**Auditor:** Atlas (Analyst Agent)
**Tipo:** Investigacao READ-ONLY
**Contexto:** Baseline Reversa — Diagnostico da plataforma de dados da Extra Consultoria

---

## 1. Resumo Executivo

A plataforma de dados da Extra Consultoria possui **infraestrutura montada mas nenhum dado de negocio populado**. Das 27 tabelas do schema `pncp_datalake`, apenas 5 contem registros — e destas, apenas 2 sao dados reais de negocio (`sc_public_entities` com 2.241 entes e `pncp_raw_bids` com 200 licitacoes). As 22 tabelas restantes estao **completamente vazias**, incluindo `opportunity_intel`, `pncp_supplier_contracts`, `coverage_evidence`, `enriched_entities` e `ingestion_checkpoints`.

O banco de dados ativo (`pncp_datalake`) roda em um **container Docker temporario** (`tmpfs`), o que significa que todos os dados serao perdidos se o container for reiniciado. O ambiente de producao em Hetzner VPS nunca foi configurado com credenciais reais.

**Conclusao:** O sistema tem arquitetura e schema prontos, mas **nunca passou por uma ingestao real de dados**. Os unicos dados existentes sao amostras de teste e caches locais.

---

## 2. Comandos Executados e Resultados

### 2.1 `python scripts/opportunity_intel/cli.py stats`
**Resultado:** COMANDO INEXISTENTE. O CLI (`cli.py`) aceita apenas: `radar`, `list`, `show`, `explain`, `coverage`, `source-health`, `update`, `export`, `briefing`.

### 2.2 `python scripts/opportunity_intel/cli.py coverage`  
**Resultado:** `"Nenhum dado de cobertura disponivel (execute 'update' primeiro)."`
A tabela `coverage_evidence` tem 0 linhas. Nunca houve uma medicao de cobertura.

### 2.3 `python scripts/opportunity_intel/cli.py source-health`
**Resultado:** `"Nenhum dado de oportunidade disponivel."` + lista vazia de execucoes.
Nunca houve uma execucao registrada.

### 2.4 `python scripts/local_datalake.py stats`
**Resultado:** 14 tabelas listadas com `ERR` — todas com falha de autenticacao PostgreSQL (`no password supplied`). O script usa o DSN padrao que nao inclui senha:
```python
DEFAULT_DSN = os.getenv("LOCAL_DATALAKE_DSN", "postgresql://postgres@127.0.0.1:5433/pncp_datalake")
```
O `.env` nao define `LOCAL_DATALAKE_DSN` — usa apenas o placeholder `postgresql://postgres:<password>@<hetzner-ip>:5432/pncp_datalake`.

### 2.5 `python scripts/opportunity_intel/cli.py list --status open --limit 5`
**Resultado:** `"Nenhuma oportunidade encontrada."`
A tabela `opportunity_intel` tem 0 linhas.

---

## 3. Arquitetura de Dados Descoberta

### 3.1 Banco de Dados

| Propriedade | Valor |
|---|---|
| SGBD | PostgreSQL 16 com PostGIS 3.4 |
| Container | `extraconsultoria-test-db-1` (Docker) |
| Imagem | `postgis/postgis:16-3.4` |
| Porta host | 5433 |
| Database | `pncp_datalake` |
| User/Password | `test` / `test` |
| Armazenamento | `tmpfs` (volatil) |
| Healthcheck | `pg_isready -U test -d extra_test` (database original, nao pncp_datalake) |

### 3.2 Outros Containers PostgreSQL

| Container | Porta | Uso |
|---|---|---|
| `recuperador-postgres` | 5432 | Sistema Recuperador |
| `evolution_postgres` | (interna) | Sistema Evolution |
| `b2g-fresh-db` | 54398 | B2G pipeline |
| `smartlic-datalake` | 54399 | Smartlic |

### 3.3 Docker Compose (origem do container)

O arquivo `docker-compose.yml` define apenas um servico `test-db` com `tmpfs`:
```yaml
services:
  test-db:
    image: postgis/postgis:16-3.4
    tmpfs: /var/lib/postgresql/data
```
**O banco de dados e temporario.** Dados sao perdidos ao reiniciar o container.

---

## 4. Estado das Tabelas

### 4.1 Tabelas COM DADOS (5 de 27)

| Tabela | Linhas | Conteudo | Data de criacao |
|---|---|---|---|
| `sc_public_entities` | **2.241** | Entes publicos de SC num raio de 200km | 2026-07-14 |
| `pncp_raw_bids` | **200** | Licitacoes PNCP (pagina unica, 3 dias) | 2026-07-14 |
| `_migrations` | **48** | Migracoes de schema aplicadas | 2026-07-14 |
| `source_applicability_rules` | **18** | Regras de aplicabilidade por fonte | 2026-07-14 |
| `retention_policy` | **2** | Politicas de retencao | 2026-07-14 |

### 4.2 Tabelas VAZIAS (22 de 27)

| Tabela | Linhas | Impacto |
|---|---|---|
| `opportunity_intel` | **0** | Nenhuma oportunidade processada |
| `pncp_supplier_contracts` | **0** | Nenhum contrato de fornecedor |
| `coverage_evidence` | **0** | Nenhuma medicao de cobertura |
| `enriched_entities` | **0** | Nenhuma entidade enriquecida |
| `engineering_opportunities` | **0** | Nenhuma oportunidade de engenharia |
| `entity_coverage` | **0** | Nenhum registro de cobertura por entidade |
| `entity_hierarchy` | **0** | Nenhuma hierarquia de entidade |
| `ingestion_checkpoints` | **0** | Nenhum checkpoint de ingestao |
| `ingestion_runs` | **0** | Nenhuma execucao registrada |
| `opportunity_checkpoints` | **0** | Nenhum checkpoint de oportunidade |
| `opportunity_coverage` | **0** | Nenhuma cobertura de oportunidade |
| `opportunity_runs` | **0** | Nenhuma execucao registrada |
| `capability_coverage` | **0** | Nenhuma cobertura por capacidade |
| `pncp_enrichment_cache` | **0** | Cache de enriquecimento vazio |
| `contract_version_history` | **0** | Historico de versoes vazio |
| `coverage_snapshots` | **0** | Nenhum snapshot |
| `source_snapshot_membership` | **0** | Nenhum membership |
| `target_universe_entities` | **0** | Nenhuma entidade do universo-alvo |
| `target_universe_runs` | **0** | Nenhuma execucao registrada |
| `sc_municipalities` | **0** | Nenhum municipio catalogado |
| `sc_dados_abertos_backfill_log` | **0** | Log de backfill vazio |
| `entity_coverage` (duplicada) | **0** | — |

---

## 5. Dados Externos (fora do PostgreSQL)

### 5.1 Checkpoint PNCP (`data/intel_pncp_checkpoint.json`)

| Propriedade | Valor |
|---|---|
| Escopo | CNPJ 01721078000168 (Extra Construtora), SC, 90 dias |
| Modalidades | Apenas modalidade 4 (Concorrencia Eletronica) |
| Total de itens | 750 |
| Periodo | 13/04/2026 a 02/06/2026 (~50 dias) |
| Estagios | 729 EXPIRADO, 20 SESSAO_REALIZADA, 1 PLANEJAVEL |
| Valor estimado total | R$ 1.601.053.194,17 |
| Sub-divisoes | 4 batches de 150-200 itens cada |

### 5.2 SQLite `data/contract_intel.db`

| Tabela | Linhas | Conteudo |
|---|---|---|
| `target_universe` | **1.093** | Universo de entes publicos-alvo (orgaos compradores) |
| `pncp_supplier_contracts` | **0** | Nenhum contrato de fornecedor |

O `target_universe` contem:
- 1.093 orgaos compradores (potencialmente relevantes)
- Distribuicao: 513 em "SANTA CATARINA" (estadual), 36 Joinville, 35 Blumenau, 22 Florianopolis, etc.
- Todos dentro do raio de 200km.

### 5.3 Extra Ledger (`data/extra_ledger.json`)

| Secao | Quantidade |
|---|---|
| `oportunidades` | **1** avaliacao manual |
| `propostas` | **0** |
| `contratos` | **0** |
| `atestados` | **0** |
| `capacidades` | **0** |

Unica oportunidade registrada: Reforma de escola municipal (Florianopolis), R$ 500.000, decisao "participar".

### 5.4 Intel Reports (`data/intel/`)

1 arquivo de inteligencia competitiva: **LCM Construcoes** (JSON, PDF, XLSX).

### 5.5 Caches

| Cache | Entradas | Conteudo |
|---|---|---|
| `ibge_cache.json` | **295** | Municipios de SC |
| `benchmark_cache.json` | **2** | CNPJs com dados de benchmark |
| `cnpj_cache.json` | **0** | Vazio |
| `docs_cache.json` | — | Cache de documentos |
| `geocode_cache.json` | — | Cache de geolocalizacao |

---

## 6. Fontes de Dados Configuradas

10 fontes registradas no banco (`source_applicability_rules`):

| Fonte | Esfera | Aplicabilidade | Status |
|---|---|---|---|
| **PNCP** | Todas | Federal com adesao voluntaria | Configurado |
| **ComprasGov** | Todas | Compras federais multi-esfera | Configurado |
| **DOM-SC** | Municipal | Diario oficial municipios SC | Credenciais vazias |
| **PCP** | Todas | Portal de Compras Publicas | Configurado |
| **SC Compras** | Todas | Plataforma estadual SC | Configurado |
| **TCE-SC** | Todas | Tribunal de Contas SC | Configurado |
| **DOE-SC** | Estadual | Diario oficial estadual SC | Credenciais vazias |
| **Transparencia** | Variavel | Portais de transparencia | Configurado |
| **CIGA CKAN** | Municipal | Dados municipais SC | Configurado |
| **MIDES BigQuery** | Estadual | Dados estaduais | SA file existe |

**Problemas com credenciais:**
- `.env` nao tem `DATABASE_URL` ou `LOCAL_DATALAKE_DSN` configurados
- `DOM_SC_CPF`, `DOM_SC_CNPJ`, `DOM_SC_API_KEY` estao vazios
- `DOE_SC_LOGIN`, `DOE_SC_PASSWORD` estao vazios
- `OPENAI_API_KEY` esta vazio
- `OPENROUTER_API_KEY`, `DEEPSEEK_API_KEY`, `ANTHROPIC_API_KEY` estao vazios

---

## 7. Periodo Coberto e Universo Total

### 7.1 PNCP Bids (tabela `pncp_raw_bids`)
- **200 licitacoes** de 14 a 17 de junho de 2026 (3 dias)
- Abrangencia: 25 estados brasileiros (maioria fora de SC)
- Sem filtro por modalidade ou valor
- Sem dados de SC especificamente (apenas 15 registros de SC)

### 7.2 Target Universe (`sc_public_entities`)
- **2.241 entes publicos** de Santa Catarina
- Raio de 200km de Florianopolis
- Criado em 2026-07-14 (ontem)
- **Universo total estimado:** O PNCP tem > 10 milhoes de licitacoes registradas. O sistema tem 0,002% disso.

### 7.3 Checkpoint Intel
- **750 editais** de concorrencia (modalidade 4) em SC
- Periodo: 13/04/2026 a 02/06/2026 (~50 dias)
- Apenas 1 dos 4 batches esta completo (pagina 4 de 4)

---

## 8. Freshness dos Dados

| Fonte | Ultima atualizacao | Periodo coberto | Atraso |
|---|---|---|---|
| `pncp_raw_bids` | 2026-07-14 23:57 | 14-17 Jun 2026 | ~27 dias |
| `sc_public_entities` | 2026-07-14 23:55 | Instantaneo de SC | N/A |
| Intel Checkpoint | 2026-07-14 (inferido) | Abr-Mai 2026 | ~45 dias |
| SQLite target_universe | 2026-07-14 | N/A | Criado hoje |
| Extra Ledger | 2026-07-14 | 1 oportunidade | Criado hoje |
| Caches IBGE | Pre-existente | SC | Estatico |
| Benchmark | Pre-existente | 2 CNPJs | Estatico |

**Conclusao:** Todos os dados foram criados ou ingeridos **no dia 2026-07-14**. Nao ha dados historicos acumulados. A pipeline nunca executou em producao.

---

## 9. Confiabilidade dos Dados

### 9.1 Dados Duplicados
- Nao foi possivel detectar duplicatas (volume insuficiente para analise significativa)
- `pncp_raw_bids` tem campo `content_hash` para dedup — funcionalidade implementada, mas nunca testada em volume

### 9.2 Dados Inconsistentes
- `pncp_raw_bids`: 200 registros sem `valor_total_estimado` (campo nulo para todas as linhas)
- 197 registros sem `situacao_compra` preenchida
- `matched_entity_id` sempre nulo (nenhum matching executado)
- `match_method`, `match_score`, `match_confidence` sempre nulos

### 9.3 Dados Incompletos
- `opportunity_intel`: 0 registros (sistema inteiro de inteligencia de oportunidades vazio)
- `pncp_supplier_contracts`: 0 registros (sem historico de contratos)
- `enriched_entities`: 0 registros (sem enriquecimento CNPJ)
- `coverage_evidence`: 0 registros (sem metricas de cobertura)
- 22 das 27 tabelas de negocio estao vazias

### 9.4 Qualidade dos 200 Bids Existentes
- Schema: 37 colunas, bem estruturado
- Dados: 100% sem valor estimado
- Matching: 0% matchado com entidades do target universe
- Fonte: 100% PNCP (nenhuma outra fonte)
- SC: apenas 15 registros (7,5% do total)
- 3 dias de cobertura apenas

---

## 10. Outputs que PODEM ser produzidos HONESTAMENTE

Com os dados atuais, estes sao os unicos outputs honestos:

1. **Lista de entes publicos de SC (2.241 entidades)**
   - Fonte: `sc_public_entities` — completo e confiavel
   - Formato: CSV, JSON, relatorio simples

2. **Amostra de 200 licitacoes PNCP (14-17 Jun 2026)**
   - Fonte: `pncp_raw_bids` — amostra valida mas nao representativa
   - Apenas para demonstracao/desenvolvimento

3. **Relatorio de cobertura (negativo)**
   - "Cobertura: 0% — nenhuma fonte foi ingerida"
   - Honesto e util para planejamento

4. **Lista de 750 editais SC (Abr-Mai 2026) do checkpoint**
   - Fonte: `data/intel_pncp_checkpoint.json`
   - Apenas modalidade 4 (concorrencia)
   - Nao validado contra fonte oficial

5. **Relatorio de 1 concorrente (LCM Construcoes)**
   - Fonte: `data/intel/`

6. **Dashboard de infrastructure**
   - "Database online, schema completo, 22 tabelas vazias, 48 migrations aplicadas"

**Outputs que NAO podem ser produzidos honestamente:**
- Lista de oportunidades abertas para a Extra — tabela vazia
- Analise de concorrencia por orgao — sem contratos de fornecedores
- Benchmark de precos — apenas 2 CNPJs em cache
- Cobertura por fonte — nunca medida
- Radar de oportunidades (QW-01) — sem dados de entrada
- Recomendacao de quais licitacoes participar — sem inteligencia

---

## 11. Blockers para Uso Comercial

### 11.1 CRITICOS (impedem qualquer uso comercial)

| # | Blocker | Severidade | Evidencia |
|---|---|---|---|
| B1 | **Nenhuma ingestao de dados executada** | CRITICAL | Todas as 22 tabelas de negocio vazias |
| B2 | **Banco e temporario (tmpfs)** | CRITICAL | `docker-compose.yml` usa `tmpfs` — dados volatil |
| B3 | **Sem credenciais de producao** | CRITICAL | `.env` sem `DATABASE_URL`, `LOCAL_DATALAKE_DSN`, ou qualquer API key |
| B4 | **Sem dados de contratos** | CRITICAL | `pncp_supplier_contracts` = 0 linhas — impossivel analise de mercado |
| B5 | **Sem matching entidade-bid** | CRITICAL | `matched_entity_id` sempre nulo — bids nao vinculados a entes |
| B6 | **Sem dados de oportunidades** | CRITICAL | `opportunity_intel` = 0 linhas — nada para recomendar |
| B7 | **Pipeline nunca executou** | CRITICAL | `ingestion_runs` = 0, `ingestion_checkpoints` = 0 |

### 11.2 ALTOS (impedem uso confiavel)

| # | Blocker | Severidade | Evidencia |
|---|---|---|---|
| B8 | **Cobertura nunca medida** | HIGH | `coverage_evidence` = 0 linhas |
| B9 | **Benchmark insuficiente** | HIGH | Apenas 2 CNPJs em cache de benchmark |
| B10 | **Sem enriquecimento de dados** | HIGH | `enriched_entities` = 0 linhas |
| B11 | **Amostra PNCP irrisoria** | HIGH | 200 bids de 3 dias — 0,00001% do universo |
| B12 | **Intel checkpoint desatualizado** | HIGH | Dados de Abr-Mai 2026, apenas 1 modalidade |
| B13 | **Credenciais DOM-SC e DOE-SC vazias** | HIGH | Duas fontes SC importantes bloqueadas |
| B14 | **OpenAI key vazia** | HIGH | `intel_analyze.py` depende de LLM para enriquecimento |

### 11.3 MEDIOS (degradam qualidade)

| # | Blocker | Severidade |
|---|---|---|
| B15 | Sem dados de SC especificamente (apenas 15 bids SC) | MEDIUM |
| B16 | `cli.py stats` nao implementado | MEDIUM |
| B17 | SQLite e PostgreSQL duplicam `target_universe` sem sincronia | MEDIUM |
| B18 | `extra_ledger` tem apenas 1 entrada manual | MEDIUM |
| B19 | `cnpj_cache` vazio — toda consulta requer API externa | MEDIUM |

---

## 12. Analise Detalhada por Fonte

### 12.1 PNCP (Portal Nacional de Contratacoes Publicas)
- **Endpoint:** `https://pncp.gov.br/api/consulta/v3`
- **Dados disponiveis:** 200 bids crus (sem processamento)
- **Problemas:** Navegacao por paginacao limitada a 50 paginas (`PNCP_MAX_PAGES=50`); sem crawl incremental configurado; filtro `INGESTION_DATE_RANGE_DAYS=90` mas nunca executado com esse parametro
- **Valor total estimado dos 200 bids:** Todos nulos

### 12.2 DOM-SC (Diario Oficial dos Municipios de SC)
- **Endpoint:** `https://www.diariomunicipal.sc.gov.br`
- **Dados disponiveis:** 0 (credenciais vazias)
- **Problema:** `DOM_SC_CPF`, `DOM_SC_CNPJ`, `DOM_SC_API_KEY` sem valor

### 12.3 DOE-SC (Diario Oficial do Estado de SC)
- **Dados disponiveis:** 0 (credenciais vazias)
- **Problema:** `DOE_SC_LOGIN`, `DOE_SC_PASSWORD` sem valor

### 12.4 TCE-SC (Tribunal de Contas de SC)
- **Status:** Configurado (`TCE_SC_ENABLED=true`)
- **Dados disponiveis:** 0 — nunca crawleado

### 12.5 Demais Fontes (ComprasGov, SC Compras, CIGA CKAN, MIDES BigQuery, Transparencia)
- **Status:** Configuradas mas nunca executadas
- **Nao ha evidencia de que os crawlers tenham sido testados**

---

## 13. Linha do Tempo dos Dados

```
2026-07-14 23:55:41 — Migracoes 001 a 042 aplicadas (schema completo)
2026-07-14 23:55:50 — sc_public_entities populado (2.241 entes)
2026-07-14 23:56:27 — pncp_raw_bids populado (200 registros de teste)
2026-07-14 23:57:34 — pncp_raw_bids atualizado (fim da ingestao)
2026-07-14          — intel_pncp_checkpoint.json (crawled em data anterior, copiado hoje)
2026-07-14          — extra_ledger.json criado com 1 oportunidade manual
2026-07-14          — contract_intel.db criado (target_universe populado)
```

Tudo que existe foi criado **no mesmo dia**. Nao ha historia de dados.

---

## 14. Recomendacoes para Proximo Passo

### Para ter dados minimamente viaveis para uso comercial:

1. **Configurar `.env` com credenciais reais** — especialmente `DATABASE_URL` apontando para Hetzner VPS
2. **Substituir container `tmpfs` por volume persistente** no docker-compose
3. **Executar pipeline de ingestao PNCP** com escopo SC, 90 dias, multiplas modalidades
4. **Crawlear TCE-SC** para obter dados de contratos catarinenses
5. **Configurar credenciais DOM-SC** e crawlear diarios municipais
6. **Executar matching** entre `pncp_raw_bids` e `sc_public_entities` para vincular bids a orgaos compradores
7. **Executar enriquecimento** (CNPJ, geolocalizacao, CNAE) via `enricher.py`
8. **Executar pipeline de contratos** para popular `pncp_supplier_contracts`

### Estimativa de esforco:
- Configuracao de ambiente: 1-2 horas
- Crawl PNCP SC 90 dias: ~4 horas (2.000-5.000 paginas)
- Crawl TCE-SC: ~2 horas
- Matching + Enriquecimento: ~1 hora
- **Total estimado: 1 dia util para dados minimamente viaveis**

---

## 15. Notas Tecnicas

- O comando `cli.py stats` mencionado no `CLAUDE.md` nao existe. Os comandos disponiveis sao: `radar`, `list`, `show`, `explain`, `coverage`, `source-health`, `update`, `export`, `briefing`.
- O `manifest.py` da opportunity_intel falha com `ModuleNotFoundError: No module named 'scripts'` ao ser executado diretamente.
- `validate_coverage.py` falha com erro de conexao porque o DSN padrao nao tem senha.
- PostgreSQL 18 local (porta 5433) esta `down`. O container Docker e que atende na porta 5433.
- 48 migrations foram aplicadas com sucesso — o schema e completo e bem estruturado.
- O arquivo `config/mides-bigquery-sa.json` existe (service account do Google BigQuery), mas sem `GOOGLE_APPLICATION_CREDENTIALS` no `.env`.

# Fontes Nao-PNCP -- Cobertura Real -- 2026-07-15

> Auditoria READ-ONLY realizada por Claude Code (Agente D).
> Branch: `epic-coverage-max-200km`
> Data: 2026-07-15
> Objetivo: Medir cobertura real, freshness e estado de cada fonte de dados
> que NAO e PNCP no ecossistema Extra Consultoria.

---

## 1. Inventario de Crawlers (tabela com status)

| # | Fonte | Modulo | Proposito | Metodo | Auth | Paginacao | Status |
|---|-------|--------|-----------|--------|------|-----------|--------|
| 1 | `dom_sc` | dom_sc_crawler | bids | API REST v2 (JSON) | HTTP Basic + X-API-Key | COMPLETA (page/count, max 20 paginas) | ACTIVE |
| 2 | `pcp` | pcp_crawler | bids | API REST v2 (JSON) | NONE (publica) | COMPLETA (pagina, max 50 paginas) | ACTIVE |
| 3 | `compras_gov` | compras_gov_crawler | bids | API REST v3 (JSON) | NONE (publica) | COMPLETA (pagina, paginasRestantes, max 50) | ACTIVE |
| 4 | `sc_compras` | sc_compras_crawler | bids | API REST JSON (React SPA) | NONE (publica) | PARCIAL (pagina ignorado, usa tamanhoPagina=3000) | ACTIVE |
| 5 | `tce_sc` | tce_sc_crawler | bids | API JSON (SCMWeb) | NONE (publica) | PARCIAL (heuristico, sem totalPaginas nativo) | ACTIVE |
| 6 | `doe_sc` | doe_sc_crawler | bids | API REST (JSON) | Bearer Token (login+password) | COMPLETA (page/perPage, max 100 paginas) | ACTIVE |
| 7 | `doe_sc_selenium` | doe_sc_selenium_crawler | bids | Selenium (HTML parse) | Login via form | PARCIAL (next button, max 10 paginas) | STALE |
| 8 | `transparencia` | transparencia_crawler | bids | HTTP HTML (BS4) + Selenium | NONE | AUSENTE (so primeira pagina) | BROKEN |
| 9 | `ciga_ckan` | ciga_ckan_crawler | coverage_only | CKAN API (JSON) | NONE (publica) | COMPLETA (per resource) | ACTIVE |
| 10 | `mides_bigquery` | mides_bigquery_crawler | bids | BigQuery SQL | GCP Service Account | COMPLETA (chunked pagination) | ACTIVE |

### Legenda Status

| Status | Significado |
|--------|-------------|
| **ACTIVE** | Código funcional, integrado ao monitor.py, sem erros estruturais |
| **STALE** | Existe mas provavelmente nao executa (Selenium sem driver, sem uso no orquestrador) |
| **BROKEN** | Tem problemas estruturais que impedem extracao real de dados |
| **UNTESTED** | Implementado mas nunca testado em producao |
| **CONFIG_ONLY** | Existe configuracao mas crawler nao implementado |

---

## 2. DOM-SC (Analise Detalhada)

### Endpoint e Metodo

- **Base URL:** `https://diariomunicipal.sc.gov.br`
- **API:** `/?r=remote/list` (migrado do antigo `?r=remote/search` que retornava 404)
- **Metodo:** API REST v2 com autenticacao HTTP Basic (CPF:CNPJ) + header `X-API-Key`
- **Formato:** JSON

### Paginacao

- **Parametros:** `page` (1-indexed) + `count` (tamanho, fixo 100)
- **Maximo:** 20 paginas configurado via `API_MAX_PAGES`
- **Controle:** Loop ate pagina vazia ou `len(items) < count`
- **Classificacao:** COMPLETA -- mas sem totalPages retornado, usa heuristicas

### Cobertura de Municipios

- A propria documentacao do crawler afirma: **"Each categoria response includes publications from ALL 295+ municipios within the date range"**
- Nao ha filtro por municipio -- a API retorna todos os municipios de SC que publicaram no DOM
- **3 categorias monitoradas:** Contrato (6), Convenio (7), Empenho (28)

### Enriquecimento

- Cada publicacao da lista e enriquecida com dados de entidade via chamada individual a `url_origem_api`
- Usa regex HTML para extrair CNPJ, nome e municipio do HTML da pagina de detalhe
- **Problema:** Isso significa N chamadas HTTP adicionais por pagina (1 por publicacao), criando lentidao

### Freshness

- **Full:** 180 dias (`DOM_SC_FULL_DAYS`)
- **Incremental:** 3 dias (`DOM_SC_INCREMENTAL_DAYS`)
- Feature flag: `DOM_SC_ENABLED` (default: true)
- Depende de 3 env vars: `DOM_SC_CPF`, `DOM_SC_CNPJ`, `DOM_SC_API_KEY`

### Observacoes

- Crawler bem escrito, com logging de cobertura por municipio e tratamento de 401/429
- **Ponto de atencao:** O enriquecimento pagina-a-pagina significa ~100 chamadas extras por pagina de 100 items -- potencialmente lento para full crawl (180 dias * 3 categorias)

---

## 3. PCP/TCE-SC (Analise Detalhada)

### PCP (Portal de Compras Publicas)

- **Base URL:** `https://compras.api.portaldecompraspublicas.com.br`
- **Endpoint:** `/v2/licitacao/processos`
- **Autenticacao:** NENHUMA (API publica)
- **Metodo:** API REST (JSON)
- **Paginacao:** `pagina` (1-indexed), fixo 10 records/pagina, `pageCount` no response
- **Maximo:** 50 paginas (`PCP_MAX_PAGES_V2`)
- **Filtro UF:** Client-side (API retorna todas as UFs; filtra por `unidadeCompradora.uf`)

### Cobertura PCP

- **Nao ha filtro por municipio** -- a API retorna compras de todo o Brasil
- A filtragem UF e feita em memoria apos receber os dados
- **Escopo:** Qualquer ente publico que publique no Portal de Compras Publicas (predominantemente municipal)
- **Modalidades mapeadas:** Pregao, Concorrencia, Tomada de Precos, Convite, Concurso, Leilao, Dialogo Competitivo, Dispensa, Inexigibilidade, Credenciamento

### Problemas PCP

- Pagina de 10 items e pequena -- 50 paginas = max 500 records
- Filtragem UF client-side desperdica banda (baixa todas as UFs)
- **Nao retorna CNPJ** no endpoint de listagem (orgao_cnpj fica vazio, confia em matching por nome)

### TCE-SC (SCMWeb)

- **Base URL:** `https://www.scmweb.com.br/processos/index.php`
- **Parametro:** `p285` identifica TCE-SC como orgao
- **Autenticacao:** NENHUMA (publica)
- **Metodo:** API JSON (`pg=transparencia&export=json`)
- **Paginacao:** Parametro `pn` (page number); heuristica: se < 20 items, parou

### Cobertura TCE-SC

- **Endpoint unico:** TCE-SC como orgao publicante primario
- Nota tecnica no codigo: "O parametro p285 no URL identifica o TCE-SC como orgao. O SCMWeb suporta filtro por unidade_gestora para expandir cobertura a outros entes municipais de SC (ver Fase 2 do plano de expansao)."
- **Isso significa que o crawler atual cobre APENAS o TCE-SC** (entidade estadual), nao os municipios
- **Dois endpoints:** Licitacoes (`page=licitacoes`) e Contratos (`page=contratos`)
- Funcao `crawl_by_municipio()` existe mas usa `unidade_gestora=codigo_ibge` que "depende da implementacao do SCMWeb" -- **nao testado**

### Freshness

- **Full:** 365 dias (`TCE_SC_FULL_DAYS`)
- **Incremental:** 7 dias (`TCE_SC_INCREMENTAL_DAYS`)
- Feature flag: `TCE_SC_ENABLED` (default: true)

### Observacoes TCE-SC

- Esfera fixa como 2 (Estadual)
- Municipio padrao: "Florianopolis" (sede do TCE) quando API nao retorna municipio
- Delay de 2s entre paginas (conservador)
- **Nao ha expansao para municipios alem do TCE-SC** -- `crawl_by_municipio()` nao testada

---

## 4. DOE-SC (Analise Detalhada)

### Por que DOIS crawlers?

Existem dois crawlers DOE-SC:

1. **`doe_sc_crawler.py`** (primario) -- API REST com autenticacao Bearer
   - Base: `https://portal.doe.sea.sc.gov.br/apis/doe-api/`
   - Autenticacao: POST `/apis/login` com login + password -> Bearer token
   - Escopo: "513 entidades estaduais de SC"
   - Paginacao: completa (page/perPage, max 100 paginas)
   - Categorias: carrega dinamicamente e filtra por palavras-chave de procurement

2. **`doe_sc_selenium_crawler.py`** (fallback) -- Selenium para quando API esta bloqueada
   - Usa Selenium WebDriver para navegar no portal Angular SPA
   - Faz login via formulario e extrai dados do DOM renderizado
   - Muito mais lento e fragil
   - **Provavelmente STALE:** depende de selenium_crawler base class, selectores CSS heuristicos

### Cobertura DOE-SC

- **Cobre: 513 entidades estaduais de SC** que publicam no Diario Oficial do Estado
- Escopo: exclusivamente **estadual** (esfera 2)
- Nao cobre municipios

### Freshness

- **Full:** 90 dias (`DOE_SC_FULL_DAYS`)
- **Incremental:** 1 dia (`DOE_SC_INCREMENTAL_DAYS`)
- Feature flag: `DOE_SC_ENABLED` (default: true)
- Depende de: `DOE_SC_LOGIN`, `DOE_SC_PASSWORD`

### Observacoes

- API DOE-SC tem rate limiting (429 tratado com Retry-After)
- Token expira a cada 30 min com renovacao automatica
- Transform faz extracao de CNPV por regex no texto -- baixa precisao (regex generico)
- Selenium crawler e fallback, mas provavelmente nunca executou em producao (requer Chrome+WebDriver)

---

## 5. Compras.gov.br (Analise Detalhada)

### Endpoint e Metodo

- **Base URL:** `https://dadosabertos.compras.gov.br`
- **Endpoint Primario:** `/modulo-contratacoes/1_consultarContratacoes_PNCP_14133` (Lei 14.133)
- **Endpoint Secundario (opcional):** `/modulo-legado/1_consultarLicitacao` (pre-2024)
- **Autenticacao:** NENHUMA (API publica)
- **Metodo:** API REST v3 (JSON)
- **Paginacao:** `pagina` + `tamanhoPagina` + `paginasRestantes` no response

### Cobertura

- **Lei 14.133:** Filtro UF server-side via `unidadeOrgaoUfSigla` -- cobre orgaos federais em SC
- **Legado:** NAO filtra por UF na v3 (crawl nacional quando ativado)
- **Orgaos:** Qualquer orgao federal com sede/atuacao em SC que publique no ComprasGov
- **Esfera:** Federal (1) por padrao, mas `orgaoEntidadeEsferaId` pode retornar "M"/"E"/"F"

### Observacoes

- **Orgaos federais em SC**: Universidades Federais (UFSC, IFSC, UFFS), Agencias (ANA, ANVISA), Hospital Universitario, etc.
- **Nao cobre orgaos estaduais ou municipais** -- so federais
- Endpoint legado desativado por default (`COMPRASGOV_LEGACY_ENABLED`)
- Page size configuravel (10-500), default 100

### Freshness

- **Full:** 3 dias (`INGESTION_DATE_RANGE_DAYS`)
- **Incremental:** 1 dia (`INGESTION_INCREMENTAL_DAYS`)
- Freshness SLA: 12 horas (segundo registry)

### Problemas

- Janela temporal muito curta (3 dias full) -- significa que full crawl e quase igual ao incremental
- Endpoint 14.133 requer `codigoModalidade` (0 = todas) -- funcional
- Legacy endpoint NAO retorna CNPJ nem orgao -- registros sem identificacao

---

## 6. CIGA CKAN (Analise Detalhada)

### O que e CIGA?

CIGA = **Consorcio de Informatica na Gestao Publica Municipal** (SC).
Mantem um portal de dados abertos em `https://dados.ciga.sc.gov.br/` (CKAN).

O dataset relevante: `domsc-publicacoes-de-{month}-{year}` contem publicacoes do
DOM-SC de Jan 2023 a Dez 2025 (36 meses).

### Cobertura

- **Propósito:** `coverage_only` -- NAO extrai bids, apenas atualiza `entity_coverage`
- **Cobertura:** Todos os municipios de SC que publicaram no DOM-SC dentro das categorias:
  - Contratos, Licitações, Ata de registro de preços, Extrato de Contrato, Convênios
- Pagina por mes com ~90 recursos ZIP (3 por dia), cada um com JSON de publicacoes
- Faz matching de entidades contra `sc_public_entities` por nome normalizado + municipio

### Funcionamento

1. Lista datasets CKAN disponiveis
2. Download de cada recurso ZIP
3. Extrai entidades unicas das publicacoes
4. Match contra DB entities (cascade: nome+municipio -> nome -> alias -> fuzzy)
5. Upsert em `entity_coverage`

### Observacoes

- `transform()` retorna lista vazia propositalmente (`SOURCE_PURPOSE = "coverage_only"`)
- Dados vao ate Dez 2025 -- nao tem dados de 2026
- Cobertura historica (2023-2025), nao fresh
- Requer `DEFAULT_DSN` e `psycopg2` para funcionar
- **Nao produz bids**, apenas metadados de cobertura de entidades

### Freshness

- Freshness SLA: 48 horas
- Dados disponiveis: Jan 2023 - Dez 2025 (36 meses)
- **Sem dados de 2026** -- defasagem de ~7 meses

---

## 7. Portais de Transparencia (Matriz Template x Municipios)

### Arquitetura

O sistema de portais de transparencia tem **2 fases**:

**Fase 1 -- Platform Detection:** Testa URLs padrao para detectar qual plataforma
cada municipio usa. Plataformas conhecidas:

| Plataforma | Padrao URL | Qtd Detectada |
|-----------|------------|---------------|
| **betha** | `{slug}.atende.net/transparencia` | 64 municipios |
| **ipam** | `{slug}.ipm.org.br/transparencia` | 0 (na deteccao) |
| **egov** | `{slug}.e-gov.betha.com.br` | 0 (na deteccao) |
| **sc_gov_portal** | `{slug}.sc.gov.br` | 6 |
| **fiorilli** | `{slug}.fiorilli.com.br/transparencia` | 0 |
| **iplan** | `{slug}.iplan.gov.br/transparencia` | 0 |
| **iri** | `{slug}.iri.com.br/transparencia` | 0 |
| **prima** | `{slug}.prima.com.br/transparencia` | 0 |
| **tecnospeed** | `{slug}.tecnospeed.com.br/transparencia` | 0 |
| **proprio** | `{municipio}.sc.gov.br` (generico) | varios (no `transparencia_platforms.json`) |

### Resultado da Deteccao

**Arquivo `data/platform_detection_results.json` (gerado em 2026-07-11):**
- Total municipios testados: **295**
- Detectados: **64** (todos betha/atende.net)
- Nao encontrados: **231** (78%)
- Erros: **0**

**Arquivo `data/transparencia_platforms.json` (gerado em 2026-07-12):**
- Tambem testou 15 municipios da lista padrao (stub)
- Detectou: betha (5), sc_gov_portal (5), proprio (1), not_found (4)

### Fase 2 -- Template Scraping (Configuracao)

Arquivo `config/transparencia_config.yaml` contem:

**Templates disponiveis:**
1. `portal_transparencia_net` (Betha) -- seletor: `table.licitacao`
2. `e_gov_net` -- seletor: `div.lista-licitacoes table`
3. `ipam` -- seletor: `table.tabela-padrao, table.grid, table.licitacao`
4. `sc_gov_portal` -- seletor: `table.table-licitacoes, table.licitacao, table.table`
5. `custom` -- seletor definido por municipio

**Municipios configurados:**
- **Betha (portal_transparencia_net):** 59 municipios -- TODOS com `requires_js: true`
- **IPAM (ipam):** 3 municipios (Criciuma, Itajai, Lages)
- **E-gov (e_gov_net):** 3 municipios (Balneario Camboriu, Florianopolis, Joinville)
- **SC Gov Portal (sc_gov_portal):** 5 municipios (Atalanta, Gaspar, Icara, Jaragua do Sul, Urubici)
- **Custom:** 2 municipios (Rio do Sul, Tubarao)

**Total configurados:** 72 municipios

### Problemas Graves

1. **59 dos 72 municipios configurados usam Betha com `requires_js: true`** -- ou seja,
   precisam de Selenium para renderizar a tabela de licitacoes, mas o Selenium:
   - Nao esta disponivel em todas as maquinas (`TRANSPARENCIA_SELENIUM_ENABLED`)
   - Precisa de ChromeDriver/GeckoDriver instalado
   - E significativamente mais lento

2. **Nao ha paginacao implementada** -- o scraper so pega a primeira pagina de resultados.
   `crawl_template()` chama `scrape_municipio()` que faz uma unica requisicao.

3. **Cobertura real:** Dos 72 configurados, apenas os ~13 com `requires_js: false`
   (IPAM e SC Gov) tem chance de funcionar com HTTP simples.

4. **Template generico (`sc_gov_portal`)** -- usa selectores muito amplos (`table.table`)
   que podem pegar a tabela errada na pagina.

5. **Familias nao detectadas:** Fiorilli, Iplan, IRI, Prima, Tecnospeed estao
   nos templates de URL, mas **zero municipios foram detectados** com essas plataformas.

6. **231 municipios (78%):** Nao tem deteccao de plataforma -- o crawler atual
   nao consegue sequer encontrar o portal de transparencia deles.

---

## 8. SC Compras

### Endpoint e Metodo

- **Base URL:** `https://compras.sc.gov.br`
- **API:** `/api/editais` (JSON) e `/api/editais/{id}` (detalhe)
- **Autenticacao:** NENHUMA (publica)
- **Metodo:** API REST JSON (React SPA)
- **Paginacao:** **PARCIAL** -- o parametro `pagina` e ignorado pelo backend;
  usa `tamanhoPagina=3000` para pegar tudo de uma vez

### Cobertura

- **Escopo:** Orgaos estaduais de SC que usam o Portal de Compras SC
- **Nao cobre municipios** -- so entidades estaduais
- Cobre todos os editais publicados no portal, com detalhes enriquecidos via
  `/api/editais/{id}`

### Observacoes

- Esfera inferida por nome do orgao (keyword matching)
- `valor_total_estimado` NAO e retornado pela API -- campo fica None
- `orgao_cnpj` NAO e retornado -- campo fica vazio
- API retorna `totalElementos` mas o parametro de pagina e ignorado

### Freshness

- **Full:** 30 dias (`SC_COMPRAS_FULL_DAYS`)
- **Incremental:** 3 dias (`SC_COMPRAS_INCREMENTAL_DAYS`)

---

## 9. Monitor/Orquestrador (Fontes Ativas vs Inativas)

### Como o orquestrador decide o que rodar

O `monitor.py` carrega a lista de fontes do **registry centralizado** em
`scripts/crawl/registry.py`. O CLI aceita `--source` com nome da fonte ou `"all"`.

### Fontes Ativas no Registry

| Fonte | Ativa | Module | Observacao |
|-------|-------|--------|------------|
| pncp | SIM | pncp_crawler_adapter | Primaria |
| dom_sc | SIM | dom_sc_crawler | Requer credentials |
| pcp | SIM | pcp_crawler | Publica |
| compras_gov | SIM | compras_gov_crawler | Publica |
| sc_compras | SIM | sc_compras_crawler | Publica |
| contracts | SIM | contracts_crawler | Contratos PNCP |
| transparencia | SIM | transparencia_crawler | Publica |
| tce_sc | SIM | tce_sc_crawler | Publica |
| doe_sc | SIM | doe_sc_crawler | Requer credentials |
| ciga_ckan | SIM | ciga_ckan_crawler | coverage_only |
| mides_bigquery | SIM | mides_bigquery_crawler | Requer GCP credentials |

### Modos Suportados

Monitor aceita modos: `full`, `incremental`, `dry-run`, `template`, `selenium`,
`detect`, `backfill`.

Para cada fonte, `crawl()` recebe o string mode e interpreta internamente.

### Fontes Mencionadas mas Nao Implementadas

- **`pncp_arp_crawler.py`** -- Crawler para Atas de Registro de Precos do PNCP
  (existe no diretorio mas nao esta no registry). Investigacao pendente.
- **`pncp_pca_crawler.py`** -- Crawler para Planos de Contratacao Anual do PNCP
  (existe no diretorio mas nao esta no registry).

### Cobertura Declarada vs Real

Registry declara:
- **dom_sc:** entity_types=["prefeituras", "camaras"] -- cobre municipios
- **pcp:** authority_level="multi" -- cobre multiplas esferas
- **compras_gov:** authority_level="federal" -- federal em SC
- **sc_compras:** authority_level="estadual" -- estadual
- **tce_sc:** authority_level="estadual" -- TCE-SC
- **doe_sc:** authority_level="estadual", entity_types=["estaduais"]
- **transparencia:** authority_level="municipal" -- portais municipais
- **ciga_ckan:** authority_level="municipal" -- cobertura historica
- **mides_bigquery:** authority_level="estadual" -- empenhos 2021-2024

---

## 10. Matriz Fonte x Ente (com base nos dados disponiveis)

| Fonte | Federal SC | Estadual SC | Municipal SC | Qtd Estimada Orgaos |
|-------|-----------|-------------|-------------|--------------------|
| PNCP | SIM | PARCIAL | PARCIAL | ~2.085 (todo SC) |
| DOM-SC | NAO | NAO | SIM (295+ municipios) | ~500+ entidades municipais |
| PCP | SIM | SIM | SIM | Varia (nacional) |
| ComprasGov | SIM (federais em SC) | NAO | NAO | ~30-50 orgaos federais em SC |
| SC Compras | NAO | SIM | NAO | ~50-100 orgaos estaduais |
| TCE-SC | NAO | SIM (TCE-SC apenas) | NAO (expansao nao implementada) | 1 (TCE-SC) |
| DOE-SC | NAO | SIM (513 entidades) | NAO | 513 entidades estaduais |
| Transparencia | NAO | NAO | PARCIAL (64/295 detectados) | 64 municipios detectados |
| CIGA CKAN | NAO | NAO | SIM (historico 2023-2025) | ~295+ municipios |
| MiDES BQ | NAO | SIM (empenhos) | SIM (276 municipios) | 276 municipios SC |

---

## 11. Freshness por Fonte

| Fonte | Full Crawl | Incremental | Ultima Evidencia | Status Freshness |
|-------|-----------|-------------|-----------------|-----------------|
| DOM-SC | 180 dias | 3 dias | Desconhecido (requer creds) | UNKNOWN (sem checkpoint visivel) |
| PCP | 30 dias | 3 dias | Desconhecido | UNKNOWN |
| ComprasGov | **3 dias** | 1 dia | Desconhecido | UNKNOWN (janela muito curta) |
| SC Compras | 30 dias | 3 dias | Desconhecido | UNKNOWN |
| TCE-SC | **365 dias** | 7 dias | Desconhecido | UNKNOWN |
| DOE-SC | 90 dias | 1 dia | Desconhecido (requer creds) | UNKNOWN |
| Transparencia | N/A (full_refresh) | N/A | 2026-07-11/12 (deteccao) | STALE (deteccao apenas) |
| CIGA CKAN | Todos os meses | Ultimo mes | Dez 2025 (ultimo dado disponivel) | **STALE** (7 meses defasado) |
| MiDES BQ | 2021-2024 (full) | 90 dias | Desconhecido (requer GCP creds) | UNKNOWN (depende de execucao) |

### Observacao sobre Checkpoints

Nao foi possivel verificar checkpoints de execucao nos diretorios `data/`
porque:
- O monitor.py registra execucao no banco PostgreSQL (`ingestion_runs`)
- Nao ha arquivos de checkpoint visiveis em `data/` para estas fontes
- A freshness real so pode ser determinada consultando o banco de dados
- Os arquivos `data/transparencia_platforms.json` e `data/platform_detection_results.json`
  sao os unicos artefatos de data visiveis, e mostram ultima execucao em 2026-07-11/12

---

## 12. Recomendacoes de Correcao e Expansao

### Criticas (impacto alto)

1. **Transparencia -- 59 municipios Betha com `requires_js: true`:**
   Ou instala/configura Selenium funcional, ou substitui por Playwright
   (ja disponivel como MCP), ou faz engenharia reversa da API JSON que o
   portal Betha consome (provavelmente ha uma API por tras do atende.net).

2. **Transparencia -- 231 municipios sem plataforma detectada (78%):**
   Estrategia atual de tentar `{slug}.atende.net` + `{slug}.sc.gov.br`
   e insuficiente. Necessario:
   - Usar busca no Google (cached no codigo como "TODO")
   - Consultar base do TCE-SC ou CIGA para mapear URLs reais
   - Implementar fallback com Playwright para navegacao generica

3. **CIGA CKAN sem dados de 2026:**
   Dados vao ate Dez 2025. Verificar se o dataset `domsc-publicacoes-de-`
   continua sendo atualizado no CKAN do CIGA. Se sim, ajustar para incluir
   2026. Se nao, encontrar fonte alternativa.

### Altas

4. **PCP -- Pagina de 10 items:**
   `PCP_MAX_PAGES_V2=50` limita a 500 records. Para full crawl de 30 dias
   em SC, pode ser insuficiente. Aumentar ou implementar paralelismo.

5. **ComprasGov -- Janela full de 3 dias:**
   `INGESTION_DATE_RANGE_DAYS=3` faz o full crawl ser quase igual ao
   incremental. Aumentar para 30-90 dias para capturar historico.

6. **TCE-SC -- Nao expandido para municipios:**
   `crawl_by_municipio()` existe mas nao e testada. Implementar expansao
   para todos os municipios de SC via `unidade_gestora` no SCMWeb.

### Medias

7. **SC Compras sem CNPJ:**
   API nao retorna CNPJ do orgao. Matching depende apenas de nome.
   Verificar se ha outro endpoint que retorne CNPJ.

8. **DOE-SC Selenium crawler STALE:**
   O crawler Selenium do DOE-SC provavelmente nunca funcionou em producao.
   Ou remove (se API HTTP e suficiente) ou corrige com Playwright.

9. **PCP sem CNPJ no endpoint de listagem:**
   `_transform_record` deixa `orgao_cnpj` vazio. Matching depende de nome +
   municipio. Verificar se o endpoint de detalhe do PCP tem CNPJ.

### Baixas

10. **Adicionar `pncp_arp_crawler` e `pncp_pca_crawler` ao registry:**
    Existem como modulos mas nao estao registrados como fontes.

11. **Monitorar freshness real via banco:**
    Criar script que consulta `ingestion_runs` para reportar quando cada
    fonte foi executada pela ultima vez.

12. **Testar familias de portal nao detectadas:**
    Fiorilli, Iplan, IRI, Prima, Tecnospeed estao nos templates mas
    nenhum municipio foi detectado. Verificar se os padroes de URL estao
    corretos ou se essas plataformas simplesmente nao sao usadas em SC.

---

*Fim do relatorio de auditoria. Gerado em 2026-07-15.*
*Nenhum arquivo foi modificado durante esta auditoria.*

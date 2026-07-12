# EPIC-COVERAGE-100PCT: Plano Mestre para 100% de Cobertura das 2.085 Entidades Públicas de SC

**Epic ID:** EPIC-COVERAGE-100PCT (Master Coordination Epic)
**Criado por:** River (SM) — Synkra AIOX
**Data:** 2026-07-11
**Status:** Draft
**Baseado em:** Resultado de FEAT-0.1 (PNCP coverage 10.6%), FEAT-1.x/2.x (8 crawlers implementados), TD-8.3 (PNCP v3), coverage report atual (47%)
**Fontes:** EXA research multi-source, Swagger UI tests, coverage-gaps analysis

---

## Sumário Executivo

Das 2.085 entidades públicas de Santa Catarina, **972 (47%) têm dados reais** em pelo menos uma fonte (PNCP, DOM-SC, PCP, ComprasGov, Contracts). **1.113 (53%) estão descobertas.**

Este plano mestre coordena a expansão de cobertura dos 47% atuais para **100%**, utilizando 12 fontes de dados organizadas em 3 fases de complexidade crescente. O plano prioriza fontes sem necessidade de autenticacao (Phase 1) para maximizar ganhos rapidos, avanca para fontes que necessitam credenciais (Phase 2), e finaliza com scraping pesado para os casos residuais (Phase 3).

**Estimativa total:** 10-15 dias de execucao paralelizavel
**Fontes viáveis:** 12 fontes (8 ja com codigo, 4 precisam criacao/integracao)
**Fontes inviáveis:** 1 (TCE-SC e-Sfinge via ICP-Brasil)

---

## 1. Situacao Atual (Baseline)

### Cobertura por Fonte

| Fonte | Entidades Cobertas | Status do Crawler | Observacao |
|-------|-------------------|-------------------|------------|
| PNCP API v3 | ~972 (todas fontes combinadas) | Funcional (TD-8.3 corrigiu v3) | Cobertura parcial — nem toda entidade publica no PNCP |
| DOM-SC | ~280 municipios | Funcional (FEAT-1.1) | HTML scraping, frágil a mudancas de layout |
| PCP v2 | ~100+ municipios | Funcional (FEAT-1.2) | Complementar ao DOM-SC |
| ComprasGov | ~101 entidades federais em SC | Funcional (FEAT-1.3) | So cobre orgaos federais |
| Contracts | ~variavel | Funcional (FEAT-1.4) | Dados de contratos, nao editais |
| TCE-SC | 0 | Criado (FEAT-2.1), nunca executado com sucesso | Portal e-Sfinge requer ICP-Brasil — INVIAVEL |
| Portal Transparencia | ~0 | Criado (FEAT-2.2), batch detect_platform nao executado | 8 plataformas (Betha, Ipam, E-gov, etc.) |
| DOE-SC | 0 | Criado (FEAT-2.3) | Cobre ~513 entidades estaduais — NAO EXECUTADO |
| Selenium | 0 | Criado (FEAT-2.4) | Para portais JS-rendered |
| SC Compras | ~0 | Funcional (crawler existe) | So cobre governo estadual |
| CIGA CKAN | 0 | NAO CRIADO — nova fonte descoberta | 317 municipios SC, 2022-2026, sem autenticacao |
| MiDES BigQuery | 0 | NAO INTEGRADO | 276 municipios SC, 2021-2024, requer BigQuery account |

### Gap por Natureza Juridica (1.113 entidades descobertas)

| Natureza Juridica | Qtd Estimada | Fontes Promissoras |
|-------------------|-------------|-------------------|
| Orgao Publico do Poder Executivo Municipal | ~180 | CIGA CKAN, DOM-SC, Portal Transparencia |
| Orgao Publico do Poder Legislativo Municipal | ~100 | CIGA CKAN, Portal Transparencia |
| Fundacao Publica de Direito Publico Municipal | ~120 | CIGA CKAN, PCP |
| Orgao Publico do Poder Executivo Estadual ou DF | ~100 | SC Compras, DOE-SC |
| Orgao Publico do Poder Judiciario Estadual | ~80 | PNCP, Portal Transparencia |
| Fundo Publico da Adm. Direta Estadual ou DF | ~65 | SC Compras, DOE-SC |
| Autarquia Municipal | ~60 | CIGA CKAN, Portal Transparencia |
| Sociedade de Economia Mista | ~60 | PNCP, ComprasGov |
| Autarquia Federal | ~50 | ComprasGov |
| Consorcio Publico | ~40 | CIGA CKAN, PCP |
| Municipio (prefeitura) | ~40 | DOM-SC, CIGA CKAN |
| Demais (25+ tipos) | ~218 | Multiplas fontes |

---

## 2. Inventario de Fontes (VIABLE vs INVIABLE)

### 2.1 Fontes VIATEIS (podem ser integradas)

| # | Fonte | Tipo Acesso | Autenticacao | Potencial Novas Entidades | Esforco | Risco |
|---|-------|------------|-------------|--------------------------|---------|-------|
| 1 | **CIGA CKAN** | API REST publica | Nenhuma | 200-300 | 2-4h | Baixo |
| 2 | **Entity Matching Melhoria** | Algoritmo local | Nenhuma | 150-200 | 2-3h | Medio |
| 3 | **PNCP v3 (expansao)** | API REST publica | Nenhuma | +50 | 1h | Baixo |
| 4 | **Portal Transparencia (batch)** | Multi-plataforma | Nenhuma | 100-150 | 3-5h | Medio |
| 5 | **DOM-SC (expansao)** | HTML scraping | Nenhuma | +50-100 | 2-3h | Medio |
| 6 | **SC Compras** | Website scraping | Nenhuma | +50-100 | 3-5h | Medio |
| 7 | **DOE-SC** | Website scraping | Nenhuma | +50-100 | 3-5h | Medio-Alto |
| 8 | **PCP (expansao)** | API/Website | Nenhuma | +30-50 | 1-2h | Baixo |
| 9 | **MiDES BigQuery** | BigQuery SQL | BigQuery account | 200-276 | 4-8h | Medio |
| 10 | **Selenium Crawler (JS)** | Browser automation | Nenhuma | 50-100 | 4-8h | Alto |
| 11 | **DOM-SC API (oficial)** | API REST | API Key | 280+ (redundante) | 2-4h | Medio (sem credencial) |
| 12 | **Portal Transparencia (individual)** | Scraping individual | Nenhuma | +30-50 | 8-16h | Muito Alto |

### 2.2 Fontes INVIAVEIS

| Fonte | Motivo | Alternativa |
|-------|--------|-------------|
| **TCE-SC e-Sfinge via API oficial** | Exige certificado ICP-Brasil A1/A3 (R$ 300-800/ano), emitido por AC credenciada, instalado fisicamente no servidor. Sem ICP-Brasil, o portal e-Sfinge redireciona para pagina de erro 403. | Usar CIGA CKAN + Portal Transparencia como substitutos para cobertura municipal |
| **DOM-SC API (sem API Key)** | API key e fornecida mediante cadastro e contrato com o Consorcio de Municipios (CIGA). Sem a key, o endpoint retorna 401. | Usar DOM-SC HTML scraping (ja funcional) |
| **Portais Transparencia individuais (295)** | Cada municipio tem seu proprio portal, muitos em plataformas diferentes. Scraping individual de 295 portais e inviavel em prazo viavel. | Usar batch detect_platform + templates (FEAT-2.2) que cobre ~8 plataformas = ~280 municipios |

---

## 3. Estrategia de Cobertura por Tipo de Ente

### Entes Municipais (executivo + legislativo + fundacoes + autarquias)
**Total:** ~900 entidades (400-500 cobertas, 400-500 descobertas)
**Estrategia:** CIGA CKAN como fonte primaria (+200-300) + Portal Transparencia batch (+100-150) + DOM-SC expansao (+50)
**Resultado esperado:** ~80-90% dos entes municipais cobertos

### Entes Estaduais (secretarias, fundos, autarquias, judiciario)
**Total:** ~513 entidades (200-250 cobertas, 250-300 descobertas)
**Estrategia:** DOE-SC (+50-100) + SC Compras (+50-100) + PNCP expansao
**Resultado esperado:** ~85-95% dos entes estaduais cobertos

### Entes Federais (autarquias, orgaos, empresas publicas)
**Total:** ~311 entidades (200-250 cobertas, 60-100 descobertas)
**Estrategia:** ComprasGov (ja funcional) + PNCP v3
**Resultado esperado:** ~95-100% dos entes federais cobertos

### Consorcios Publicos e Demais
**Total:** ~133 entidades (50-70 cobertas, 60-80 descobertas)
**Estrategia:** CIGA CKAN + PCP expansao
**Resultado esperado:** ~70-80% cobertos

---

## 4. Fases do Plano

### Fase 1: Fontes Sem Autenticacao (Dias 1-2) — GANHOS RAPIDOS

**Estimativa:** 2 dias, 6-10 stories paralelizaveis
**Ganho esperado:** 47% -> 60-70% (+350-500 novas entidades)

#### Story COVERAGE-1.1: Entity Matching Enhancement
**Prioridade:** P0 (desbloqueia todas as outras)
**Executor:** @analyst + @dev
**Descricao:** Melhorar o algoritmo de entity matching para capturar mais entidades ja existentes nas bases mas que nao estao sendo vinculadas por diferencas de nome (fuzzy matching, siglas vs nomes completos, variacoes de razao social).
**ACs:**
- [ ] AC1: Taxa de matching atual medida (baseline) para cada fonte
- [ ] AC2: Algoritmo de fuzzy matching implementado com threshold configurável (0.7-0.95)
- [ ] AC3: Matching por siglas implementado (ex: "PMF" ≈ "Prefeitura Municipal de Florianopolis")
- [ ] AC4: Matching por CNPJ 8 digitos priorizado (ja existe, verificar coverage)
- [ ] AC5: Fallback cascade: CNPJ 8 -> razao_social normalizada -> fuzzy name -> sigla
- [ ] AC6: Teste com amostra de 100 entidades descobertas confirmando matches adicionais
- [ ] AC7: Resultado documentado com ganho de cobertura pos-melhoria
- [ ] AC8: Sem regressao nos matches existentes (pelo menos os mesmos 972 cobertos)
**Comandos:**
```bash
# Baseline atual
python scripts/crawl/monitor.py --report-coverage

# Executar matching aprimorado
python scripts/matching/entity_matcher.py --method cascade --threshold 0.8

# Verificar ganho
python scripts/crawl/monitor.py --report-coverage
```
**Fallback:** Se fuzzy matching nao gerar ganhos significativos (< 50 novas entidades), pular para CIGA CKAN diretamente.

#### Story COVERAGE-1.2: CIGA CKAN Crawler (NOVO)
**Prioridade:** P0 (maior potencial de ganho)
**Executor:** @dev
**Descricao:** O CIGA (Consorcio de Informatica na Gestao Publica Municipal) mantem um portal CKAN aberto com dados de licitacoes de 317 municipios catarinenses, periodo 2022-2026. API CKAN e padrao, RESTful, sem autenticacao. Criar crawler dedicado.
**ACs:**
- [ ] AC1: API CKAN do CIGA mapeada: endpoint packages, resources, datastore_search
- [ ] AC2: Crawler criado em `scripts/crawl/ciga_ckan_crawler.py` seguindo padrao adapter.py
- [ ] AC3: Crawler integrado ao `monitor.py --source ciga-ckan` e ao orchestrator
- [ ] AC4: Crawl full executado para SC — >0 records persistidos em `pncp_raw_bids`
- [ ] AC5: Entity matching executado — novas entidades cobertas documentadas
- [ ] AC6: Schema de dados mapeado e transformado para formato padrao do pipeline
- [ ] AC7: Systemd timer opcional criado para crawl incremental semanal
- [ ] AC8: `pytest` passa sem falhas; ruff check sem erros
**Comandos (estimados — dependem da URL exata do CKAN):**
```bash
# Crawl completo
python scripts/crawl/monitor.py --source ciga-ckan --mode full --uf SC

# Coverage apos
python scripts/crawl/monitor.py --report-coverage
```
**Pesquisa pre-requisito:** URL exata do CKAN, dataset IDs, schema dos recursos. Usar Exa MCP `web_search` com "CIGA CKAN API licitacoes SC" + Playwright para explorar `http://ckan.ciga.sc.gov.br`.
**Fallback:** Se CKAN nao tiver dados de licitacoes (apenas dados de gestao), pivotar para Portal Transparencia batch como prioridade maxima.

#### Story COVERAGE-1.3: Portal Transparencia — Batch Detect Platform
**Prioridade:** P0
**Executor:** @dev
**Descricao:** Executar o batch detect_platform (criado em FEAT-2.2, nunca executado) para detectar automaticamente qual plataforma de transparencia cada municipio usa entre as 8 suportadas (Betha, Ipam, E-gov, Fiorilli, Iplan, IRI, Prima, Tecnospeed). Apos deteccao, executar crawler para cada plataforma.
**ACs:**
- [ ] AC1: Script detect_platform executado para todos os 295 municipios SC
- [ ] AC2: Distribuicao de plataformas documentada (quantos municipios por plataforma)
- [ ] AC3: Crawler batch executado para cada plataforma detectada
- [ ] AC4: Dados transformados e persistidos em `pncp_raw_bids`
- [ ] AC5: Entity matching executado — cobertura adicional medida
- [ ] AC6: Municipios sem plataforma detectada documentados para Fase 3
- [ ] AC7: Resultado documentado em `docs/research/transparencia-coverage.md`
**Comandos:**
```bash
# Detectar plataformas
python scripts/crawl/monitor.py --source transparencia --detect-platforms

# Crawl todas as detectadas
python scripts/crawl/monitor.py --source transparencia --mode full

# Verificar cobertura
python scripts/crawl/monitor.py --report-coverage
```
**Fallback:** Se detect_platform tiver taxa de sucesso < 50%, usar lista pre-definida de plataformas por municipio (pesquisa Exa para mapear).

#### Story COVERAGE-1.4: PNCP v3 Coverage Expansion
**Prioridade:** P1
**Executor:** @dev
**Descricao:** Expandir escopo do crawl PNCP v3 para capturar entidades que publicam em modalidades/periodos nao cobertos pelo crawl padrao atual. Configurar crawl multi-modalidade (1-7), periodo 90 dias, sem filtro de keywords.
**ACs:**
- [ ] AC1: Crawl PNCP v3 configurado com modalidades 1-7 (nao apenas engenharia)
- [ ] AC2: Periodo expandido para 90 dias (era 30)
- [ ] AC3: Remocao/configuracao do filtro `_ENGINEERING_KEYWORDS` (descoberto em FEAT-0.1)
- [ ] AC4: Crawl full executado sem erros
- [ ] AC5: Novas entidades cobertas medidas (estimado +30-50)
- [ ] AC6: Sem sobrecarga na API (rate limit respeitado, delay de 0.3s entre requests)
**Comandos:**
```bash
export INGESTION_MODALIDADES="1,2,3,4,5,6,7"
export INGESTION_DATE_RANGE_DAYS=90
export INGESTION_KEYWORDS=""  # Sem filtro
python scripts/crawl/monitor.py --source pncp --mode full
python scripts/crawl/monitor.py --report-coverage
```
**Fallback:** Se API rate limit for alcancado (429), reduzir para 30 dias com 0.5s delay e modo incremental.

#### Story COVERAGE-1.5: DOM-SC Crawler Expansion
**Prioridade:** P1
**Executor:** @dev
**Descricao:** Expandir o DOM-SC crawler existente para capturar entidades que estao sendo perdidas por mudancas de layout do HTML scraping ou por limitacoes do parser atual.
**ACs:**
- [ ] AC1: Testar DOM-SC crawler atual contra entidades conhecidas mas nao cobertas
- [ ] AC2: Diagnosticar causas de falha (layout HTML alterado? parser quebrado? paginacao?)
- [ ] AC3: Corrigir parser se necessario
- [ ] AC4: Testar com amostra de 50 municipios nao cobertos
- [ ] AC5: Crawl full executado
- [ ] AC6: Ganho de cobertura documentado
**Comandos:**
```bash
# Diagnostico
python scripts/crawl/monitor.py --source dom-sc --dry-run --uf SC --days 7

# Crawl completo
python scripts/crawl/monitor.py --source dom-sc --mode full
```
**Fallback:** Se DOM-SC HTML scraping estiver quebrado por mudanca no site, tentar DOM-SC API oficial (se API key estiver disponivel) ou substituir por CIGA CKAN.

#### Story COVERAGE-1.6: PCP Coverage Expansion
**Prioridade:** P2
**Executor:** @dev
**Descricao:** Expandir o PCP crawler existente para cobrir mais municipios. Incluir configuracao de escopo geografico ampliado e tratamento de paginacao para batches maiores.
**ACs:**
- [ ] AC1: PCP crawler testado com escopo SC completo (nao apenas subset)
- [ ] AC2: Paginacao ampliada para batches de 100 registros
- [ ] AC3: Crawl full executado sem erros
- [ ] AC4: Novas entidades cobertas medidas
**Comandos:**
```bash
python scripts/crawl/monitor.py --source pcp --mode full --uf SC
```
**Fallback:** PCP e complementar; se nao gerar ganhos significativos (< 20 entidades), documentar e arquivar.

#### Story COVERAGE-1.7: Coverage Gap Analysis & Report
**Prioridade:** P1
**Executor:** @analyst
**Descricao:** Apos execucao das stories 1.1-1.6, gerar relatorio consolidado de cobertura mostrando o gap restante detalhado por municipio, natureza juridica, e fonte. Este relatorio guia a priorizacao da Fase 2.
**ACs:**
- [ ] AC1: Script `scripts/reports/coverage_gaps.py` executado com dados atualizados
- [ ] AC2: Relatorio gerado em `docs/epic-coverage/gap-analysis-fase1.md`
- [ ] AC3: Top 50 entidades descobertas prioritarias listadas
- [ ] AC4: Recomendacao de fontes para Fase 2 baseada nos gaps reais
- [ ] AC5: Dashboard visual de cobertura (opcional, via `coverage_weekly.py`)
**Comandos:**
```bash
python scripts/crawl/monitor.py --report-coverage
python scripts/reports/coverage_gaps.py --output /tmp/gaps-fase1.xlsx
python scripts/reports/coverage_weekly.py
```

---

### Fase 2: Fontes com Credenciais/Setup (Dias 3-6) — APROFUNDAMENTO

**Estimativa:** 4 dias, 4-6 stories
**Ganho esperado:** 60-70% -> 80-90% (+300-400 novas entidades)

#### Story COVERAGE-2.1: MiDES BigQuery Integration
**Prioridade:** P0 (se BigQuery account estiver disponivel)
**Executor:** @data-engineer
**Descricao:** O Ministerio da Defesa (MiDES) mantem dados de licitacoes no BigQuery publico com dados de 276 municipios SC, periodo 2021-2024. Integrar consultas SQL ao pipeline de extracao.
**Pre-requisito:** Conta Google Cloud com BigQuery ativada (free tier suficiente)
**ACs:**
- [ ] AC1: Conexao BigQuery estabelecida via `google-cloud-bigquery` Python SDK
- [ ] AC2: Query de extracao para dados SC: municipios, modalidades, valores, orgaos
- [ ] AC3: Schema mapeado para `pncp_raw_bids`
- [ ] AC4: Pipeline de extracao integrado ao `monitor.py --source mides-bigquery`
- [ ] AC5: Crawl full executado — dados persistidos
- [ ] AC6: Entity matching executado — novas entidades cobertas documentadas
- [ ] AC7: Sem custos inesperados (free tier: 1TB/mes de queries)
**Comandos:**
```bash
# Export credenciais GCP
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account.json"

# Executar extracao
python scripts/crawl/monitor.py --source mides-bigquery --mode full

# Coverage
python scripts/crawl/monitor.py --report-coverage
```
**Fallback:** Se BigQuery account nao estiver disponivel, pular para SC Compras + DOE-SC como prioridade.

#### Story COVERAGE-2.2: SC Compras Crawler Activation
**Prioridade:** P1
**Executor:** @dev
**Descricao:** Ativar e validar o crawler SC Compras existente (`sc_compras_crawler.py`). Fazer crawl completo do portal de compras do governo estadual de Santa Catarina, que cobre ~513 entidades estaduais.
**ACs:**
- [ ] AC1: SC Compras crawler testado contra endpoint atual
- [ ] AC2: Crawl full executado para todas as modalidades
- [ ] AC3: Dados transformados e persistidos em `pncp_raw_bids`
- [ ] AC4: Entity matching executado
- [ ] AC5: Novas entidades cobertas documentadas
- [ ] AC6: Systemd timer configurado para crawl incremental semanal
**Comandos:**
```bash
python scripts/crawl/monitor.py --source sc-compras --mode full
python scripts/crawl/monitor.py --report-coverage
```
**Fallback:** Se SC Compras tiver anti-bot (Cloudflare), tentar modo Selenium.

#### Story COVERAGE-2.3: DOE-SC Crawler Activation
**Prioridade:** P1
**Executor:** @dev
**Descricao:** Ativar e validar o crawler DOE-SC existente (`doe_sc_crawler.py`). O Diario Oficial do Estado de Santa Catarina publica atos de todas as entidades estaduais. Crawler criado em FEAT-2.3 mas nunca executado com sucesso.
**ACs:**
- [ ] AC1: DOE-SC crawler testado e diagnostico de falhas feito
- [ ] AC2: Corrigir parser se layout do DOE-SC mudou desde a criacao
- [ ] AC3: Crawl full executado para SC
- [ ] AC4: Dados persistidos e matching executado
- [ ] AC5: Novas entidades cobertas documentadas
- [ ] AC6: Systemd timer configurado
**Comandos:**
```bash
# Teste
python scripts/crawl/monitor.py --source doe-sc --dry-run --days 7

# Crawl completo
python scripts/crawl/monitor.py --source doe-sc --mode full
```
**Fallback:** Se DOE-SC estiver com Cloudflare ou anti-bot, tentar Selenium crawler. Se falhar, aceitar cobertura parcial via SC Compras + PNCP.

#### Story COVERAGE-2.4: Entity Coverage Rebuild
**Prioridade:** P1
**Executor:** @dev + @data-engineer
**Descricao:** Reconstruir a view `entity_coverage` no PostgreSQL para refletir corretamente a cobertura de todas as fontes apos as expansoes da Fase 1 e 2. Corrigir possiveis inconsistencias no trigger `update_entity_coverage()`.
**ACs:**
- [ ] AC1: View `entity_coverage` rebuild com dados frescos de todas as fontes
- [ ] AC2: Trigger `update_entity_coverage()` verificado e corrigido se necessario
- [ ] AC3: Inconsistencias identificadas (entidades com dados mas sem cobertura)
- [ ] AC4: Refresh completo executado
- [ ] AC5: Coverage report mostra dados consistentes
**Comandos:**
```bash
# Rebuild coverage
python scripts/local_datalake.py rebuild-coverage

# Verificar consistencia
python scripts/crawl/monitor.py --report-coverage

# Query de verificacao
psql -d pncp_datalake -c "SELECT COUNT(*) FROM entity_coverage WHERE is_covered = TRUE;"
```

---

### Fase 3: Scraping Pesado e Casos Residuais (Dias 7-11) — COBERTURA FINAL

**Estimativa:** 5 dias, 3-5 stories
**Ganho esperado:** 80-90% -> 95-100% (+100-250 novas entidades)

#### Story COVERAGE-3.1: Selenium Crawler for JS-Rendered Portals
**Prioridade:** P0 (para portais que exigem JavaScript)
**Executor:** @dev
**Descricao:** Portais de transparencia que renderizam dados via JavaScript (React, Angular, Vue) nao sao capturados pelos crawlers HTTP tradicionais. Usar Selenium crawler criado em FEAT-2.4 para capturar dados desses portais.
**ACs:**
- [ ] AC1: Identificar portais JS-rendered nao cobertos (via detect_platform + diagnostico)
- [ ] AC2: Selenium crawler configurado com headless Chrome
- [ ] AC3: Crawler executado para cada portal JS-rendered identificado
- [ ] AC4: Dados extraidos e persistidos
- [ ] AC5: Entity matching executado
- [ ] AC6: Novas entidades cobertas documentadas
**Comandos:**
```bash
# Modo Selenium para portal especifico
python scripts/crawl/monitor.py --source selenium --target "https://...--mode full

# Batch para todos portais JS
python scripts/crawl/monitor.py --source selenium --mode full --auto-detect
```
**Fallback:** Se Selenium falhar para portais com CAPTCHA, documentar entidades como "bloqueadas por anti-bot" e tentar DOM-SC como alternativa.

#### Story COVERAGE-3.2: Portal Transparencia — Individual Scraping (Residual)
**Prioridade:** P1
**Executor:** @dev
**Descricao:** Para municipios nao cobertos pelo batch detect_platform (plataforma desconhecida ou nao suportada), tentar scraping individual com templates customizados.
**ACs:**
- [ ] AC1: Listar municipios residuais apos detect_platform (estimado 20-40)
- [ ] AC2: Para cada municipio, identificar URL do portal de transparencia
- [ ] AC3: Tentar template generico de extracao
- [ ] AC4: Se template falhar, tentar Selenium com deteccao automatica de elementos
- [ ] AC5: Entidades cobertas documentadas
- [ ] AC6: Municipios efetivamente inviaveis documentados com motivo
**Comandos:**
```bash
# Scraping individual com template
python scripts/crawl/monitor.py --source transparencia --municipio "Municipio-X"

# Usar Selenium como fallback
python scripts/crawl/monitor.py --source selenium --target "https://transparencia.municipio-x.sc.gov.br"
```
**Fallback:** Se um municipio especifico for inviavel (CAPTCHA, site offline, sem dados publicos), documentar e aceitar cobertura parcial.

#### Story COVERAGE-3.3: Multi-Source Backfill Pipeline
**Prioridade:** P1
**Executor:** @dev + @data-engineer
**Descricao:** Executar pipeline de backfill multi-source para todos os crawlers (Fases 1-3) em sequencia, com entity matching apos cada execucao, ate que a cobertura estabilize ou todas as fontes tenham sido esgotadas.
**ACs:**
- [ ] AC1: Script de backfill criado que executa todos os crawlers em sequencia
- [ ] AC2: Entity matching executado apos cada crawler finalizado
- [ ] AC3: Loop ate estabilizacao (2 execucoes consecutivas sem novas entidades)
- [ ] AC4: Relatorio de cobertura final gerado
- [ ] AC5: Lista de entidades residualmente descobertas documentada
**Comandos:**
```bash
# Backfill completo multi-source
python scripts/pipeline/backfill_multi_source.py --all-sources

# Ou manualmente:
for source in pncp dom-sc pcp compras-gov ciga-ckan transparencia sc-compras doe-sc; do
  python scripts/crawl/monitor.py --source $source --mode full
  python scripts/matching/entity_matcher.py
done

# Relatorio final
python scripts/crawl/monitor.py --report-coverage
```
**Fallback:** Se algum crawler falhar, marcar como SKIPPED e continuar com os demais. Nao bloquear o pipeline inteiro.

#### Story COVERAGE-3.4: Coverage Validation & Residual Documentation
**Prioridade:** P1
**Executor:** @analyst
**Descricao:** Validacao final de cobertura. Para cada entidade ainda descoberta, investigar causa raiz e documentar. O plano aceita cobertura < 100% para entidades comprovadamente inalcancaveis (ex: ICP-Brasil necessario, site offline permanente, sem obrigacao legal de publicar).
**ACs:**
- [ ] AC1: Entidades descobertas apos backfill total listadas
- [ ] AC2: Para cada entidade descoberta, causa raiz investigada (max 5 min por entidade)
- [ ] AC3: Entidades agrupadas por causa raiz (ICP-Brasil, sem dados publicos, offline, etc.)
- [ ] AC4: Relatorio final de cobertura gerado em `docs/epic-coverage/coverage-final.md`
- [ ] AC5: Dashboard de cobertura final gerado
- [ ] AC6: Recomendacoes para melhoria futura documentadas
**Comandos:**
```bash
# Listar residuais
python scripts/local_datalake.py stats

# Relatorio final
python scripts/reports/coverage_weekly.py --output-html

# Gaps detalhados
python scripts/reports/coverage_gaps.py --output /tmp/coverage-final-gaps.xlsx
```

---

## 5. Matriz de Execucao Paralela

```
Dia 1:  [COVERAGE-1.1 Entity Matching] [COVERAGE-1.2 CIGA CKAN] [COVERAGE-1.3 Portal Transparencia detect]
        [COVERAGE-1.4 PNCP Expansion]   [Pesquisa CIGA CKAN URL]
Dia 2:  [COVERAGE-1.5 DOM-SC]          [COVERAGE-1.6 PCP]          [COVERAGE-1.7 Gap Analysis]
        [COVERAGE-1.2 cont.]            [COVERAGE-1.3 cont.]
--- Gate: Fase 1 Completa ---

Dia 3:  [COVERAGE-2.1 MiDES BigQuery]   [COVERAGE-2.2 SC Compras]   [COVERAGE-2.3 DOE-SC]
        [Setup BigQuery account]         [Diagnostico SC Compras]     [Diagnostico DOE-SC]
Dia 4:  [COVERAGE-2.1 cont.]            [COVERAGE-2.2 cont.]        [COVERAGE-2.3 cont.]
        [Crawl + Matching]               [Crawl + Matching]           [Crawl + Matching]
Dia 5:  [COVERAGE-2.4 Coverage Rebuild] [Integracao resultados]
        [Refresh views + triggers]       [Validacao consistencia]
--- Gate: Fase 2 Completa ---

Dia 6:  [COVERAGE-3.1 Selenium]         [COVERAGE-3.2 Portal Indiv.] [Pesquisa residuais]
        [Identificar portais JS]         [Scraping individuais]       [Preparar targets]
Dia 7:  [COVERAGE-3.1 cont.]            [COVERAGE-3.2 cont.]
        [Selenium full exec]             [Fallbacks + templates]
Dia 8:  [COVERAGE-3.3 Multi-source Backfill]
        [Pipeline completo sequencial com matching apos cada passo]
Dia 9:  [COVERAGE-3.4 Validacao Final]  [Documentacao residual]
        [Investigacao causa raiz]         [Relatorio final + dashboard]
--- Gate: Fase 3 Completa ---
```

---

## 6. Dependencias e Bloqueios

### Dependencias Tecnicas

| Dependencia | Bloqueia | Alternativa se nao disponivel |
|-------------|----------|-------------------------------|
| PostgreSQL local porta 5433 | Todas as stories | Usar DSN via env var |
| PNCP API v3 funcional | COVERAGE-1.4 | Pular (ja corrigido em TD-8.3) |
| Selenium + ChromeDriver | COVERAGE-3.1 | Usar Playwright como alternativa |
| CIGA CKAN URL/API | COVERAGE-1.2 | Pesquisar via Exa antes de comecar |
| BigQuery account | COVERAGE-2.1 | Pular, usar SC Compras + DOE-SC |
| DOM-SC HTML scraping funcional | COVERAGE-1.5 | Tentar DOM-SC API (se API key disponivel) |
| SC Compras endpoint ativo | COVERAGE-2.2 | Tentar via browser/Selenium |
| DOE-SC endpoint ativo | COVERAGE-2.3 | Tentar via browser/Selenium |

### Dependencias de Dados

| Pre-requisito | Para | Nota |
|--------------|------|------|
| Entity matching funcional | Todas as stories de cobertura | Matching cascade precisa estar operacional |
| sc_public_entities populada | Medir cobertura | Planilha Excel ja importada (FEAT-0.1) |
| entity_coverage view atualizada | Medir progresso | Trigger update_entity_coverage() precisa estar ativo |

---

## 7. Criterios de Sucesso

### Por Fase

| Fase | Cobertura Minima | Cobertura Alvo | Prazo Maximo |
|------|-----------------|----------------|-------------|
| Fase 1 (apos entity matching + CIGA + Transparencia + PNCP expandido) | 60% | 65-70% | 2 dias |
| Fase 2 (apos BigQuery + SC Compras + DOE-SC + rebuild) | 80% | 85-90% | 6 dias |
| Fase 3 (apos Selenium + residuais + backfill) | 95% | 98-100% | 11 dias |

### Cobertura por Tipo de Ente (Alvo Final)

| Tipo | Total | Alvo Cobertos | Alvo % |
|------|-------|--------------|--------|
| Municipal Executivo | ~445 | 430+ | 97% |
| Municipal Legislativo | ~299 | 280+ | 94% |
| Fundacao Publica Municipal | ~266 | 250+ | 94% |
| Autarquia Municipal | ~167 | 155+ | 93% |
| Consorcio Publico | ~99 | 80+ | 81% |
| Estadual (todos) | ~269 | 250+ | 93% |
| Federal (todos) | ~311 | 300+ | 96% |
| Demais | ~229 | 180+ | 79% |
| **Total** | **2.085** | **1.925+** | **92%+** |

### Metricas de Qualidade

| Metrica | Target | Medicao |
|---------|--------|---------|
| Entidades com is_covered = TRUE | 1.925+ (92%+) | `SELECT COUNT(*) FROM entity_coverage WHERE is_covered = TRUE` |
| Falsos positivos de matching | < 5% | Auditoria manual de 50 matches aleatorios |
| Tempo do pipeline de backfill | < 4h | Duracao total da execucao |
| Testes de regressao | 100% passando | `pytest` apos cada alteracao |
| Lint | Sem novos erros | `ruff check scripts/` |
| Cobertura de codigo dos crawlers | >= 60% | `pytest --cov=scripts` |

---

## 8. Riscos e Mitigacao

| Risco | Probabilidade | Impacto | Mitigacao |
|-------|--------------|---------|-----------|
| CIGA CKAN nao ter dados de licitacoes | Media | Alto | Pesquisar antes de comecar; fallback para Portal Transparencia |
| DOM-SC HTML scraping quebrado por mudanca de layout | Media | Medio | Deteccao automatica de falha; fallback DOM-SC API |
| BigQuery account nao disponivel | Alta | Medio | Pular para Fase 2 sem BigQuery; cobertura cai ~5% |
| DOE-SC com Cloudflare/CAPTCHA | Alta | Medio | Selenium como fallback; aceitar cobertura parcial |
| Entity matching nao captura entidades (falsos negativos) | Media | Alto | Testar com amostra de 100 entidades antes do backfill full |
| SC Compras site alterado/offline | Media | Medio | Cache de ultimo crawl funcional; tentar Selenium |
| Selenium lento para 50+ portais | Alta | Baixo | Executar overnight; timeout de 5 min por portal |
| Cobertura estabiliza em < 90% | Media | Alto | Investigar causas raiz; escalar para fontes adicionais nao planejadas |
| Crawlers consomem banda/recursos do VPS | Baixa | Baixo | Monitorar via systemd; limitar concorrencia |
| Mudanca na legislacao afeta disponibilidade dos dados | Baixa | Alto | Documentar data da medicao; plano de reavaliacao periodica |

---

## 9. Recursos Necessarios

### Credenciais e Acessos

| Recurso | Para | Status | Onde Obter |
|---------|------|--------|------------|
| CIGA CKAN URL | COVERAGE-1.2 | Precisa pesquisa | Exa MCP + Playwright |
| Google Cloud BigQuery | COVERAGE-2.1 | NAO DISPONIVEL | Criar conta gratuita + service account |
| DOM-SC API Key | COVERAGE-1.5 fallback | NAO DISPONIVEL | Contato CIGA |
| ChromeDriver/geckodriver | COVERAGE-3.1 | NAO VERIFICADO | `apt install chromium-driver` |

### Armazenamento

| Recurso | Uso | Estimativa |
|---------|-----|------------|
| PostgreSQL `pncp_datalake` | Dados brutos de licitacoes | ~500MB adicional |
| `pncp_raw_bids` | Records de todas as fontes | ~50K novas linhas |
| `entity_coverage` | Estado de cobertura | ~2.085 linhas |

---

## 10. INVIABILIDADES DOCUMENTADAS

### Inviavel por Barreira Tecnica

| Item | Causa | Impacto |
|------|-------|---------|
| TCE-SC e-Sfinge (API oficial) | Exige certificado ICP-Brasil A1/R$ 300-800/ano | Perda da fonte agregadora mais completa de SC (~96% entidades) |
| TCE-SC e-Sfinge (web scraping) | Portal requer certificado para qualquer consulta; sem ICP-Brasil retorna 403 | Crawler FEAT-2.1 criado mas inviavel sem certificado |
| DOM-SC API Oficial sem API Key | API key exige contrato CIGA | Crawler HTML scraping funcional (mas mais fragil) |

### Inviavel por Escopo

| Item | Causa | Impacto |
|------|-------|---------|
| 295 portais de transparencia individuais | Cada municipio tem seu proprio sistema; batch detect_platform cobre ~8 plataformas | ~20-40 municipios podem ficar com cobertura parcial (plataformas exoticas) |
| Scraping de sites com CAPTCHA avancado | reCAPTCHA v3, hCaptcha — exigem resolucao manual ou servico pago | Aceitar cobertura parcial para estes casos |

### Cobertura Limitada (Esperada)

| Item | Motivo | Entidades Afetadas |
|------|--------|-------------------|
| Consorcios Publicos | Nem todos publicam licitacoes em portais acessiveis | ~10-20 dos 99 consorcios |
| Fundacoes e Associacoes | Natureza juridica hibrida, algumas sem obrigacao de publicar | ~30-50 entidades |

---

## 11. Story List Consolidada

| ID | Story | Fase | Executor | Horas | Prioridade | Depende de |
|----|-------|------|----------|-------|------------|------------|
| COVERAGE-1.1 | Entity Matching Enhancement | 1 | @analyst + @dev | 2-3h | P0 | Nenhuma |
| COVERAGE-1.2 | CIGA CKAN Crawler (NOVO) | 1 | @dev | 3-5h | P0 | Pesquisa CIGA URL |
| COVERAGE-1.3 | Portal Transparencia Batch Detect | 1 | @dev | 3-5h | P1 | Nenhuma |
| COVERAGE-1.4 | PNCP v3 Coverage Expansion | 1 | @dev | 1-2h | P1 | PNCP v3 funcional |
| COVERAGE-1.5 | DOM-SC Crawler Expansion | 1 | @dev | 2-3h | P1 | Nenhuma |
| COVERAGE-1.6 | PCP Coverage Expansion | 1 | @dev | 1-2h | P2 | Nenhuma |
| COVERAGE-1.7 | Gap Analysis Report | 1 | @analyst | 1-2h | P1 | 1.1 a 1.6 executadas |
| **COVERAGE-1.8** 🆕 | **Match Hierárquico Secretaria → Prefeitura** | 1 | @data-engineer | 2-3h | **P0** | Nenhuma |
| **COVERAGE-1.9** 🆕 | **SC Dados Abertos Municipality Fix** | 1 | @data-engineer | 1-2h | P1 | Nenhuma |
| **COVERAGE-1.10** 🆕 | **PCP Diagnostic & Fix** | 1 | @dev | 1-2h | P1 | Nenhuma |
| **COVERAGE-1.11** 🆕 | **Geocoding 604 Entes Sem Coordenadas** | 1 | @dev | 1-2h | P1 | Nenhuma |
| COVERAGE-2.1 | MiDES BigQuery Integration | 2 | @data-engineer | 4-8h | P0/PULAR | BigQuery account |
| COVERAGE-2.2 | SC Compras Crawler Activation | 2 | @dev | 3-5h | P1 | Nenhuma |
| COVERAGE-2.3 | DOE-SC Crawler Activation | 2 | @dev | 3-5h | P1 | Nenhuma |
| COVERAGE-2.4 | Entity Coverage Rebuild | 2 | @dev + @data-engineer | 1-2h | P1 | 2.1-2.3 executadas |
| COVERAGE-3.1 | Selenium Crawler for JS Portals | 3 | @dev | 4-8h | P0 | ChromeDriver |
| COVERAGE-3.2 | Portal Transparencia Individual | 3 | @dev | 4-6h | P1 | 1.3 resultados |
| COVERAGE-3.3 | Multi-Source Backfill Pipeline | 3 | @dev + @data-engineer | 3-5h | P1 | 1.1 a 3.2 executadas |
| COVERAGE-3.4 | Coverage Validation & Documentation | 3 | @analyst | 2-4h | P1 | 3.3 executada |

---

## 12. Ordem de Execucao Recomendada

### Fluxo Paralelo
```
DIA 1:
  @analyst: COVERAGE-1.1 (Entity Matching Enhancement)
  @dev:     COVERAGE-1.2 (Pesquisa CIGA CKAN + inicio crawler)
  @dev:     COVERAGE-1.3 (Portal Transparencia detect_platform)
  @data-engineer: COVERAGE-1.8 (Match Hierárquico — QUICK WIN +400 entes)

DIA 2:
  @analyst: COVERAGE-1.1 (conclui + resultados)
  @dev:     COVERAGE-1.2 (conclui ciga ckan)
  @dev:     COVERAGE-1.3 (conclui transparencia batch)
  @dev:     COVERAGE-1.4 (PNCP expansion)
  @dev:     COVERAGE-1.5 (DOM-SC expansion)
  @dev:     COVERAGE-1.10 (PCP Diagnostic)
  @dev:     COVERAGE-1.11 (Geocoding — desbloqueia 1.8)
  @data-engineer: COVERAGE-1.9 (SC Dados Abertos fix)
  @analyst: COVERAGE-1.7 (Gap Analysis)

DIA 3-4:
  @dev:             COVERAGE-2.2 (SC Compras)
  @dev:             COVERAGE-2.3 (DOE-SC)
  @data-engineer:   COVERAGE-2.1 (BigQuery) [SE account disponivel]

DIA 5:
  @dev + @data-engineer: COVERAGE-2.4 (Coverage Rebuild)

DIA 6-7:
  @dev: COVERAGE-3.1 (Selenium)
  @dev: COVERAGE-3.2 (Transparencia Individual)

DIA 8:
  @dev + @data-engineer: COVERAGE-3.3 (Backfill)

DIA 9:
  @analyst: COVERAGE-3.4 (Validacao Final + Documentacao)
```

---

## 13. Anexos e Referencias

### Documentos Relacionados

| Documento | Localizacao | Relevancia |
|-----------|-------------|------------|
| PNCP Coverage Report | `docs/research/coverage-pncp-real.md` | Baseline de cobertura PNCP (10.6%) |
| EPIC-FEAT-001 | `docs/stories/epics/epic-feat-001-crawlers-coverage/EPIC-FEAT-001.md` | 8 crawlers implementados |
| EPIC-TD-003 | `docs/stories/epics/epic-td-003-reversa-remediation/EPIC-TD-003.md` | PNCP v3 migration (TD-8.3) |
| TD-8.3 Story | `docs/stories/epics/epic-td-003-reversa-remediation/story-TD-8.3-pncp-api-v3-migration.md` | Fix detalhado da API v3 |
| FEAT-0.1 Story | `docs/stories/epics/epic-feat-001-crawlers-coverage/story-FEAT-0.1-validar-cobertura-pncp.md` | Validacao de cobertura original |
| Transparencia Platforms | `data/transparencia_platforms.json` | Plataformas detectadas por municipio |
| Coverage Gaps Script | `scripts/reports/coverage_gaps.py` | Script de exportacao de gaps |
| Coverage Weekly Script | `scripts/reports/coverage_weekly.py` | Relatorio semanal automatizado |

### Crawlers Existentes

| Crawler | Arquivo | Fonte | Status |
|---------|---------|-------|--------|
| PNCP | `scripts/crawl/pncp_crawler_adapter.py` | PNCP API v3 | Funcional |
| DOM-SC | `scripts/crawl/dom_sc_crawler.py` | DOM-SC HTML | Funcional |
| PCP | `scripts/crawl/pcp_crawler.py` | PCP v2 | Funcional |
| ComprasGov | `scripts/crawl/compras_gov_crawler.py` | ComprasGov v3 | Funcional |
| Contracts | `scripts/crawl/contracts_crawler.py` | PNCP Contracts | Funcional |
| TCE-SC | `scripts/crawl/tce_sc_crawler.py` | TCE-SC e-Sfinge | INVIAVEL (ICP-Brasil) |
| Portal Transparencia | `scripts/crawl/transparencia_crawler.py` | Multi-plataforma | Criado, nao executado |
| DOE-SC | `scripts/crawl/doe_sc_crawler.py` | DOE-SC | Criado, nao executado |
| Selenium | `scripts/crawl/selenium_crawler.py` | JS Portals | Criado, nao executado |
| SC Compras | `scripts/crawl/sc_compras_crawler.py` | SC Compras | Criado, nao executado |
| CIGA CKAN | NOVO | CIGA CKAN API | NAO CRIADO |

---

## 14. Cobertura Projetada (Curva de Avancos)

```
100% |                                             F3: 95-100%
 90% |                                   F2: 85-90%
 80% |                         F2: 80-85%
 70% |               F1: 65-70%
 60% |     F1: 60-65%
 50% |   (atual)
 40% |
 30% |
 20% |
 10% |
  0% +----|--------|--------|--------|--------|--------|--------|
         D0      D2      D4      D6      D8      D10     D12
              F1      F1      F2      F2      F3      F3
              gate    fim     gate    fim     gate    fim
```

Legenda:
- D0: 47% (972/2.085) — baseline atual
- D1 (COVERAGE-1.8 + 1.11): 62-66% (+350-400 entes) — match hierárquico (zero crawl adicional)
- D2 (Fim Fase 1): 65-75% (+150-300 entes) — CIGA CKAN + Transparencia batch + SC Dados Abertos + PNCP expandido
- D6 (Fim Fase 2): 80-90% (+300-400 entes) — BigQuery + SC Compras + DOE-SC + coverage rebuild
- D11 (Fim Fase 3): 95-100% (+100-250 entes) — Selenium + residuais + backfill + validacao

---

## Change Log

| Data | Versao | Descricao | Autor |
|------|--------|-----------|-------|
| 2026-07-11 | 1.0 | Criacao do Plano Mestre de Cobertura 100% | River (SM) |
| 2026-07-11 | 1.1 | Adicionadas 4 stories (1.8-1.11) baseadas em cross-ref real planilha × PostgreSQL: match hierárquico (+400 entes), SC Dados Abertos fix (75K contratos), PCP diagnostic (72 bids), geocoding (604 entes sem coordenadas) | River (SM) |

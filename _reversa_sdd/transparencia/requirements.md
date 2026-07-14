# Transparencia — Requisitos Funcionais e Regras de Negocio (v2.0)

> Gerado pelo Writer em 2026-07-13 | Base: 249340d
> Fontes: `scripts/crawl/transparencia_crawler.py` (1510 linhas), `scripts/crawl/transparencia_templates/` (6 modulos, ~890 linhas), `scripts/transparencia/run_detect_all.py` (407 linhas), `scripts/crawl/generate_transparencia_config.py` (284 linhas), `config/transparencia_config.yaml` (79 municipios), ADR-011

## Visao Geral

Sistema de deteccao e extracao de licitacoes de portais de transparencia municipais de Santa Catarina. A arquitetura e template-driven (ADR-011), com deteccao automatica de plataforma, extracao via seletores CSS configuraveis, e fallback generico heuristico em 3 niveis.

## Arquitetura do Pipeline

```
[295+ municipios SC] 
    |
    v
[Fase 1 — Deteccao de Plataforma]
    | detect_platform(slug, municipio) em transparencia_crawler.py:318-409
    | 9 padroes de URL + fallback dominio proprio
    | ThreadPoolExecutor 30 workers (run_detect_all.py:149)
    v
[Fase 2 — Extracao Template-Driven]
    | crawl_template() em transparencia_crawler.py:868-985
    | Resolve seletores CSS via config YAML (transparencia_config.yaml)
    | 4 templates especializados + 1 Selenium para JS
    v
[Fase 3 — Normalizacao]
    | transform() em transparencia_crawler.py:1375-1432
    | Mapeia para schema pncp_raw_bids
    v
[Data Lake]
    | transparencia_scrape_results.json
    | transparencia_platforms.json
```

---

## Requisitos Funcionais

### RF-TR01 — Deteccao Automatica de Plataforma
**Prioridade:** MUST | **Fonte:** `transparencia_crawler.py:318-409` | **Confianca:** 🟢

O sistema deve detectar automaticamente a plataforma de portal de transparencia de um municipio testando URLs conhecidas em ordem de especificidade.

**Cenario de teste (Gherkin):**
```gherkin
Dado um municipio com slug "chapeco"
Quando detect_platform("chapeco", municipio="Chapeco") e chamado
Entao o sistema deve testar URLs nesta ordem:
  | https://chapeco.atende.net/transparencia        (betha)
  | https://chapeco.ipm.org.br/transparencia         (ipam)
  | https://chapeco.e-gov.betha.com.br               (egov)
  | https://chapeco.sc.gov.br                        (sc_gov_portal)
  | https://chapeco.fiorilli.com.br/transparencia    (fiorilli)
  | https://chapeco.iplan.gov.br/transparencia       (iplan)
  | https://chapeco.iri.com.br/transparencia         (iri)
  | https://chapeco.prima.com.br/transparencia       (prima)
  | https://chapeco.tecnospeed.com.br/transparencia  (tecnospeed)
E o sistema deve retornar a primeira URL que responde HTTP 200
E o corpo HTML deve ser verificado contra a funcao check() da template
```

**Plataformas suportadas (definidas em `_PLATFORM_TEMPLATES` linha 205-251):**

| Plataforma | URL Pattern | Check Body | Municipios SC | Confianca |
|------------|------------|------------|---------------|-----------|
| Betha | `{slug}.atende.net/transparencia` | `atende.net` ou `betha` no body | ~80 | 🟢 |
| Ipam | `{slug}.ipm.org.br/transparencia` | `ipm` no body | ~50 | 🟢 |
| E-gov Betha | `{slug}.e-gov.betha.com.br` | `e-gov` ou `betha` no body | ~40 | 🟢 |
| SC Gov Portal | `{slug}.sc.gov.br` | `transpar` ou `licita` no body | ~15 | 🟡 |
| Fiorilli | `{slug}.fiorilli.com.br/transparencia` | `fiorilli` no body | ~5 | 🟡 |
| Iplan | `{slug}.iplan.gov.br/transparencia` | `iplan` no body | ~5 | 🟡 |
| IRI | `{slug}.iri.com.br/transparencia` | `iri` no body | ~5 | 🟡 |
| Prima | `{slug}.prima.com.br/transparencia` | `prima` no body | ~5 | 🟡 |
| Tecnospeed | `{slug}.tecnospeed.com.br/transparencia` | `tecnospeed` no body | ~5 | 🟡 |

### RF-TR02 — Fallback por Dominio Proprio
**Prioridade:** MUST | **Fonte:** `transparencia_crawler.py:374-404` | **Confianca:** 🟡

Quando nenhuma plataforma conhecida e detectada, o sistema deve tentar:
1. `https://{slug}.sc.gov.br`
2. `https://www.{slug}.sc.gov.br`
3. `https://{slug}.gov.br`

E verificar a presenca de keywords de transparencia no body: "transparencia", "licitacao", "edital", "pregao", "portal da transparencia" (definidas em `_GENERIC_KEYWORDS` linha 253-264).

```gherkin
Dado um municipio sem plataforma conhecida, com slug "urubici"
Quando detect_platform("urubici", municipio="Urubici") e chamado
E todas as 9 URLs de plataforma falham
Entao o sistema deve tentar https://urubici.sc.gov.br
E se HTTP 200 e body contiver keyword de transparencia
Entao deve retornar platform="proprio", status="detected"
```

### RF-TR03 — Extracao Template-Driven com Seletores CSS
**Prioridade:** MUST | **Fonte:** `transparencia_crawler.py:519-648`, `config/transparencia_config.yaml` | **Confianca:** 🟢

O sistema deve extrair dados de licitacao usando seletores CSS definidos em configuracao YAML por template.

**Campos extraidos por linha da tabela** (codigo `_extract_row()` linha 651-728):
- `modalidade` — tipo da licitacao (Pregao, Concorrencia, Dispensa, etc.)
- `data_publicacao` — data de publicacao (formato brasileiro DD/MM/YYYY)
- `objeto` — descricao do objeto da licitacao
- `orgao` — orgao responsavel (opcional, ausente em e-gov)
- `valor` — valor em formato brasileiro R$ 1.234,56 (opcional)
- `link` — URL do detalhe (se houver link na linha)

```gherkin
Dado um portal Betha com HTML <table class="licitacao">
Quando scrape_municipio() e chamado com selectors do template portal_transparencia_net
Entao cada linha <tr> deve ser extraida com:
  | data       | td:nth-child(1) |
  | modalidade | td:nth-child(2) |
  | objeto     | td:nth-child(3) |
  | orgao      | td:nth-child(4) |
  | valor      | td:nth-child(5) |
  | link       | a               |
E cada registro deve receber um content_hash MD5(modalidade|objeto|data|valor)
```

### RF-TR04 — Resolucao de Seletores em Cascata
**Prioridade:** MUST | **Fonte:** `transparencia_crawler.py:468-494` | **Confianca:** 🟢

O sistema deve resolver seletores CSS para cada municipio na seguinte ordem de prioridade:
1. Seletores custom definidos no bloco `selectors:` do municipio (template: custom)
2. Seletores do template referenciado em `template:` (portal_transparencia_net, e_gov_net)
3. Retornar None se nenhum seletor for encontrado

```gherkin
Dado um municipio "tubarao" com template "custom" e selectors proprios
Quando _resolve_selectors(cfg, config) e chamado
Entao os seletores do municipio devem ter prioridade sobre os do template

Dado um municipio "chapeco" com template "portal_transparencia_net"
E sem selectors custom
Quando _resolve_selectors(cfg, config) e chamado
Entao os seletores do template devem ser usados
```

### RF-TR05 — 4 Templates de Plataforma Especializados
**Prioridade:** MUST | **Fonte:** `scripts/crawl/transparencia_templates/` | **Confianca:** 🟢

O sistema deve ter implementacao especializada para cada plataforma:

| Template | Arquivo | Linhas | Estrategia de Parsing |
|----------|---------|--------|----------------------|
| Betha | `betha.py` | 155 | 8 seletores de tabela (ordem de especificidade) + fallback div |
| Ipam | `ipam.py` | 153 | 7 seletores de tabela + fallback generico |
| E-gov | `egov.py` | 179 | 5 seletores de container + table/div + fallback |
| Generico | `generico.py` | 256 | 3 estrategias: keyword scoring, div, any-table |
| Selenium Base | `selenium_base.py` | 242 | Table extraction + div + generic + selectors de paginacao |

**Interface comum** (definida em `__init__.py` linha 1-65):
```python
PLATFORM   # str: identificador da plataforma
NAME       # str: nome legivel
DESCRIPTION # str: descricao
URL_PATTERNS # list[str]: padroes de URL para deteccao
SELECTORS   # dict: seletores CSS default
parse_page(soup, url, slug, ibge) -> list[dict]  # funcao de parsing
```

### RF-TR06 — Template Generico com Scoring por Keywords
**Prioridade:** MUST | **Fonte:** `transparencia_templates/generico.py:56-208` | **Confianca:** 🟢

Para portais nao identificados, o sistema deve usar o template generico com 3 estrategias em cascata:

**Estrategia 1 — Keyword Scoring (linhas 95-133):**
- Encontrar todas as tabelas `<table>` no HTML
- Pontuar cada tabela por presenca de 14 keywords de licitacao (linhas 37-55)
- Bonus por ter mais de 1 linha
- Ordenar por pontuacao decrescente
- Parsear a tabela de maior pontuacao

**Keywords de scoring** (definidas em `_LICITACAO_KEYWORDS` linha 37-55):
licitação, licitacao, edital, pregao, modalidade, objeto, data de publicacao, data limite, concorrencia, tomada de preco, convite, dispensa, inexigibilidade

**Estrategia 2 — Div-Based Extraction (linhas 211-258):**
8 padroes CSS de containers: `div[id*='licitacao']`, `div[class*='edital']`, `section[class*='licitacao']`, etc.

**Estrategia 3 — Any-Table (linhas 261-271):**
Qualquer tabela com 3+ linhas e 2+ colunas.

**Atribuicao de colunas** conforme numero de `<td>` por linha (linhas 159-192):
- 5 colunas: modalidade, data, objeto, orgao, valor
- 4 colunas: data, modalidade, objeto, valor
- 3 colunas: data, modalidade, objeto
- 2 colunas: modalidade, objeto (key-value)

### RF-TR07 — Suporte a Portais JS-Rendered (Selenium)
**Prioridade:** SHOULD | **Fonte:** `transparencia_crawler.py:993-1190`, `selenium_base.py` | **Confianca:** 🟡

O sistema deve detectar portais que requerem JavaScript (`requires_js: true` no config) e usar Selenium para renderizacao antes do parsing.

**Comportamento:**
- Gate por env var `TRANSPARENCIA_SELENIUM_ENABLED` (linha 81-82)
- Gate por config por municipio `requires_js: true/false`
- Fallback automatico para HTTP se Selenium nao estiver disponivel (linhas 1019-1023)
- Timeout configuravel via `SELENIUM_TIMEOUT` (default 30s, linha 87)
- User-Agent rotation (selenium_crawler.py)
- Rate limiting entre requisicoes (`SELENIUM_REQUEST_DELAY`, default 5s, linha 90)

**Suporte a paginacao** em `selenium_base.py` linha 52-63:
10 seletores de "next page": `a.next`, `a[rel='next']`, `.pagination .next a`, ligaico*proxima*, etc.

### RF-TR08 — Batch Detection para 295+ Municipios SC
**Prioridade:** MUST | **Fonte:** `scripts/transparencia/run_detect_all.py:1-406` | **Confianca:** 🟢

O sistema deve suportar deteccao em lote para todos os municipios de Santa Catarina.

```gherkin
Dado que existem 295+ municipios cadastrados no banco
Quando run_batch_detection() e chamado
Entao o sistema deve usar ThreadPoolExecutor com 30 workers concorrentes (linha 149)
E aplicar REQUEST_DELAY de 0.5s entre requests ao mesmo dominio (linha 44)
E gerar relatorio com distribuicao de plataformas (linhas 184-215)
E salvar resultados em transparencia_platforms.json (linhas 218-249)
E gerar lista de municipios residuais para Fase 3 (linhas 252-297)
E produzir blocos YAML prontos para copiar ao config (linhas 376-402)
```

### RF-TR09 — Persistencia de Resultados com Merge Incremental
**Prioridade:** MUST | **Fonte:** `transparencia_crawler.py:806-860, 1277-1372` | **Confianca:** 🟢

O sistema deve persistir resultados de deteccao e scraping em arquivos JSON com suporte a merge incremental.

**Arquivos:**
| Arquivo | Formato | Funcao |
|---------|---------|--------|
| `data/transparencia_platforms.json` | `{"detected": [...], "metadata": {...}}` | `_save_results()` / `_load_existing_results()` |
| `data/transparencia_scrape_results.json` | `{"municipios": [...], "metadata": {...}}` | `_save_scrape_results()` |
| `data/transparencia_residual_municipios.json` | `{"residual": [...], ...}` | `save_residual_municipios()` |

**Logica de merge** (linhas 1336-1347):
- Resultados novos sobrescrevem slugs existentes
- Slugs nao re-verificados sao preservados do arquivo anterior
- Metadata inclui versionamento (version: 1 ou 2)

### RF-TR10 — 5 Modos de Crawl com Semantica Clara
**Prioridade:** MUST | **Fonte:** `transparencia_crawler.py:1198-1274` | **Confianca:** 🟢

```gherkin
Dado o sistema de crawl
Quando o modo "detect" e selecionado
Entao apenas a deteccao de plataforma deve rodar
E resultados salvos em transparencia_platforms.json

Quando o modo "template" e selecionado
Entao apenas scraping template-driven deve rodar (config YAML)
E resultados salvos em transparencia_scrape_results.json

Quando o modo "selenium" e selecionado
Entao portais requires_js usam Selenium, demais usam HTTP

Quando o modo "full" e selecionado
Entao detect + template scrape sao executados em sequencia

Quando o modo "incremental" e selecionado
Entao municipios ja detectados em execucoes anteriores sao pulados
```

### RF-TR11 — Normalizacao para Schema pncp_raw_bids
**Prioridade:** MUST | **Fonte:** `transparencia_crawler.py:1375-1432` | **Confianca:** 🟢

O sistema deve normalizar registros extraidos para o schema padrao do data lake.

**Mapeamento de campos** (linhas 1400-1424):
| Campo Schema | Fonte | Transformacao |
|-------------|-------|---------------|
| pncp_id | `content_hash` | Direto |
| objeto_compra | `objeto` | Direto |
| valor_total_estimado | `valor` | `_parse_valor()` (linhas 1435-1452) |
| modalidade_nome | `modalidade` | Direto |
| uf | — | Hardcoded `"SC"` |
| municipio | `municipio` | Direto |
| codigo_municipio_ibge | `codigo_municipio_ibge` | Direto |
| orgao_razao_social | `orgao` | Direto |
| data_publicacao | `data_publicacao` | `_parse_date()` (linhas 1455-1476) |
| link_pncp | `link` | Direto |
| content_hash | `content_hash` | MD5 |
| source | — | `"transparencia"` |
| source_subtype | `_source_subtype` / `template_module` / fallback `"generico"` |
| source_id | — | `"transparencia_{slug}"` |
| method | `method` | http / selenium / http_fallback |

### RF-TR12 — Health Check com HEAD Request
**Prioridade:** SHOULD | **Fonte:** `transparencia_crawler.py:502-517` | **Confianca:** 🟢

Antes de scrapear um portal, o sistema deve verificar sua disponibilidade via HEAD request.

```gherkin
Dado um portal_url "https://chapeco.atende.net/transparencia"
Quando health_check() e chamado
Entao deve fazer HEAD request com timeout TRANSPARENCIA_TIMEOUT (default 5s)
E retornar HTTP status code ou 0 se unreachable
E scrape_municipio() deve retornar status="unreachable" se health check falhar
```

### RF-TR13 — Rate Limiting e Configuracoes por Env Var
**Prioridade:** SHOULD | **Fonte:** `transparencia_crawler.py:51-92` | **Confianca:** 🟢

Todas as configuracoes de timing devem ser ajustaveis via variaveis de ambiente com prefixo `TRANSPARENCIA_`.

| Variavel | Default | Descricao |
|----------|---------|-----------|
| TRANSPARENCIA_TIMEOUT | 5 | Timeout HTTP em segundos |
| TRANSPARENCIA_REQUEST_DELAY | 0.5 | Delay entre requests mesmo dominio |
| TRANSPARENCIA_DELAY | 5.0 | Delay entre portais diferentes |
| TRANSPARENCIA_MAX_RETRIES | 1 | Retentativas por URL |
| TRANSPARENCIA_SELENIUM_ENABLED | false | Habilita Selenium |
| SELENIUM_TIMEOUT | 30 | Timeout renderizacao JS |
| SELENIUM_REQUEST_DELAY | 5.0 | Delay entre requests Selenium |
| SELENIUM_HEADLESS | true | Modo headless do Selenium |

### RF-TR14 — Geracao Automatica de Config YAML
**Prioridade:** SHOULD | **Fonte:** `scripts/crawl/generate_transparencia_config.py:1-283` | **Confianca:** 🟢

O sistema deve gerar o arquivo `transparencia_config.yaml` a partir dos resultados de deteccao em lote, preservando entradas manuais pre-existentes.

**Fontes de dados mescladas** (linhas 41-147):
1. Pass 1 — Municipios Betha detectados (64+)
2. Pass 2 — Municipios Proprio verificados manualmente (valid_proprio com 10 entries, linha 57-68)
3. Manual keep — Entradas pre-existentes nao sobrescritas (6 entries, linhas 88-142)

**Template mapping** (linhas 34-38):
| Platform | Config Template |
|----------|----------------|
| betha | portal_transparencia_net |
| ipam | portal_transparencia_net |
| egov | e_gov_net |
| proprio | custom |

### RF-TR15 — Supporte a Configuracao de 79+ Municipios
**Prioridade:** MUST | **Fonte:** `config/transparencia_config.yaml` (validado em `test_transparencia_crawler.py:484-488`) | **Confianca:** 🟢

O sistema deve operar com configuracao atualizada contendo 79 municipios mapeados.

**Distribuicao atual por template** (testado linha 488):
- `portal_transparencia_net` — ~64 municipios Betha
- `e_gov_net` — ~3 municipios (Florianopolis, Joinville, Balneario Camboriu)
- `custom` — ~12 municipios (dominio proprio, requer selectors individuais)

**Campos por municipio no config:**
```yaml
municipio_slug:
  nome: "Nome do Municipio"
  ibge: "4200000"        # 7 digitos, obrigatorio (testado linha 544-548)
  portal_url: "https://..."
  template: "portal_transparencia_net"  # ou e_gov_net, custom, ipam
  requires_js: true       # bool, obrigatorio (testado linha 1100-1107)
  wait_for: "..."         # seletor para espera, apenas se requires_js
  selectors: {...}        # apenas se template: custom
  ativo: true             # bool, permite desabilitar sem remover
```

---

## Regras de Negocio

### RN-TR01 — Template-Driven, Nao Codigo
**Confianca:** 🟢 | **Fonte:** ADR-011, `__init__.py`

Novo portal = novo YAML, nao novo codigo Python. A adicao de uma nova plataforma requer:
1. Novo arquivo em `transparencia_templates/{plataforma}.py` com `parse_page()`
2. Registro em `transparencia_templates/__init__.py:get_template()` (linha 42-47)
3. Pattern em `_PLATFORM_TEMPLATES` no crawler (linhas 205-251)
4. (Opcional) Novos seletores em `transparencia_config.yaml`

### RN-TR02 — Ordem de Deteccao por Especificidade
**Confianca:** 🟢 | **Fonte:** `transparencia_crawler.py:205-251`

Plataformas sao testadas em ordem da mais especifica para a mais generica. Betha (atende.net) antes de E-gov (e-gov.betha.com.br) pois E-gov e um subproduto Betha.

### RN-TR03 — Fallback Graceful em 3 Niveis
**Confianca:** 🟢 | **Fonte:** `transparencia_crawler.py`, `generico.py`

- Se Fase 1 (deteccao) falha, tentar dominio proprio
- Se Fase 2 (template scraping) nao encontra dados, tentar template generico
- Se Selenium falha, fazer fallback automatico para HTTP

### RN-TR04 — Content Hash para Deduplicacao
**Confianca:** 🟢 | **Fonte:** `base.py:81-83`, `betha.py:112-113`, `egov.py:106-107`, etc.

Cada registro recebe um hash MD5 de `modalidade|objeto|data_publicacao|valor`. O hash ignora slug, ibge e portal_url — permitindo comparacao entre diferentes municipios que publicam a mesma licitacao.

### RN-TR05 — Registros Sem Dados Sao Ignorados
**Confianca:** 🟢 | **Fonte:** `base.py:66-67`, `transparencia_crawler.py:721-722`

Se uma linha nao contiver pelo menos `modalidade`, `objeto` ou `data_publicacao`, o registro e descartado (`make_record()` retorna None).

### RN-TR06 — Validacao de IBGE de 7 Digitos
**Confianca:** 🟢 | **Fonte:** validado em `test_transparencia_crawler.py:544-548`

Cada municipio configurado deve ter IBGE de exatamente 7 digitos numericos.

---

## Metricas de Cobertura Atual

| Metrica | Valor | Confianca |
|---------|-------|-----------|
| Total municipios SC | 295 | 🟢 |
| Municipios com template configurado | 79 (27%) | 🟢 |
| Plataformas conhecidas | 9 | 🟢 |
| Templates especializados | 4 (+1 Selenium) | 🟢 |
| Linhas de producao | ~1700 | 🟢 |
| Cobertura de testes | ~1316 linhas de teste | 🟢 |
| Testes de deteccao por plataforma | 8 (betha, ipam, egov, fiorilli, iplan, iri, prima, tecnospeed) | 🟢 |
| Teste de config (79 municipios) | 1 | 🟢 |
| Teste de entity loading | 3 | 🟢 |

## Referencias

- ADR-011: `_reversa_sdd/adrs/011-template-transparencia-crawler.md`
- Codigo: `scripts/crawl/transparencia_crawler.py`
- Templates: `scripts/crawl/transparencia_templates/`
- Batch detect: `scripts/transparencia/run_detect_all.py`
- Config generator: `scripts/crawl/generate_transparencia_config.py`
- Config: `config/transparencia_config.yaml`
- Testes: `tests/test_transparencia_crawler.py`
- Deploy: `deploy/systemd/transparencia-crawl.{service,timer}`

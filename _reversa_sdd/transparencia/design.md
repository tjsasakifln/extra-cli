# Transparencia — Design Tecnico (v2.0)

> Gerado pelo Writer em 2026-07-13 | Base: 249340d
> Fontes: `scripts/crawl/transparencia_crawler.py` (1625 linhas), `scripts/crawl/transparencia_templates/` (6 modulos, ~890 linhas), `scripts/transparencia/run_detect_all.py` (407 linhas), `scripts/crawl/generate_transparencia_config.py` (284 linhas)

## Visao Arquitetural

```
                    +---------------------+
                    |   monitor.py        |
                    | crawl() interface   |
                    +----------+----------+
                               |
              +----------------+-----------------+
              |                |                  |
     +--------v-------+ +-----v------+  +--------v--------+
     | detect_platform| |crawl_      |  | crawl_selenium  |
     | (Fase 1)       | |template()  |  | (Fase 2 - JS)  |
     | 1625:318-409   | | 1625:868-  |  | 1625:993-1190  |
     |                | | 985        |  |                 |
     +--------+-------+ +-----+------+  +--------+--------+
              |                |                  |
              v                v                  v
     +--------+-------+ +-----+------+  +--------+--------+
     | _PLATFORM_     | | Config     |  | SeleniumCrawler |
     | TEMPLATES      | | YAML       |  | selenium_       |
     | (9 patterns)   | | 79 munics  |  | crawler.py      |
     +----------------+ +-----+------+  +--------+--------+
                               |                  |
                               v                  v
                      +--------+-------+  +--------+--------+
                      | Template       |  | Selenium Base   |
                      | Modules        |  | Template        |
                      | betha.py       |  | selenium_base.py|
                      | ipam.py        |  | (JS rendered)  |
                      | egov.py        |  | + pagination    |
                      | generico.py    |  +-----------------+
                      +--------+-------+
                               |
                      +--------v-------+
                      | base.py        |
                      | extract_text,  |
                      | extract_link,  |
                      | make_record,   |
                      | parse_table_   |
                      | rows,          |
                      | parse_div_list |
                      +----------------+
                               |
                               v
                      +--------+--------+
                      | transform()     |
                      | 1625:1375-1432  |
                      | -> pncp_raw_bids|
                      +-----------------+
```

---

## 1. Deteccao de Plataforma (Fase 1)

### 1.1 Algoritmo de Deteccao

```
Funcao detect_platform(slug, municipio):
    1. Para cada template em _PLATFORM_TEMPLATES (ordenado por especificidade):
        a. Montar URL: tmpl["url"].format(slug=slug)
        b. Fazer GET via _fetch_url(url, timeout=TRANSPARENCIA_TIMEOUT)
        c. Se HTTP 200:
            i. Opcionalmente verificar body com tmpl["check"](body)
            ii. Retornar {platform, url, status: "detected"}
        d. Caso contrario: aguardar TRANSPARENCIA_REQUEST_DELAY e tentar proximo
    2. Se nenhum template match:
        a. Tentar dominio proprio: {slug}.sc.gov.br, www.{slug}.sc.gov.br, {slug}.gov.br
        b. Verificar _GENERIC_KEYWORDS no body
        c. Se match: retornar platform="proprio", status="detected"
    3. Se nada funcionou: retornar status="not_found"
```

**Localizacao:** `transparencia_crawler.py:318-409`
**Lista de templates:** `transparencia_crawler.py:205-251`
**Keywords genericas:** `transparencia_crawler.py:253-264`

### 1.2 Tabela de Plataformas

```python
_PLATFORM_TEMPLATES = [
    {"platform": "betha",      "url": "https://{slug}.atende.net/transparencia",       "check": check_betha},
    {"platform": "ipam",       "url": "https://{slug}.ipm.org.br/transparencia",        "check": check_ipam},
    {"platform": "egov",       "url": "https://{slug}.e-gov.betha.com.br",              "check": check_egov},
    {"platform": "sc_gov_portal", "url": "https://{slug}.sc.gov.br",                   "check": check_sc_gov},
    {"platform": "fiorilli",   "url": "https://{slug}.fiorilli.com.br/transparencia",   "check": check_fiorilli},
    {"platform": "iplan",      "url": "https://{slug}.iplan.gov.br/transparencia",      "check": check_iplan},
    {"platform": "iri",        "url": "https://{slug}.iri.com.br/transparencia",        "check": check_iri},
    {"platform": "prima",      "url": "https://{slug}.prima.com.br/transparencia",      "check": check_prima},
    {"platform": "tecnospeed", "url": "https://{slug}.tecnospeed.com.br/transparencia", "check": check_tecnospeed},
]
```

### 1.3 Funcao Auxiliar para Deteccao por URL

`_detect_platform_from_url(url)` (linhas 267-315) — analisa URL por substrings e retorna o nome da plataforma. Usada por testes e por logica de transformacao quando o campo `template_module` nao esta presente.

---

## 2. Templates Especializados

### 2.1 Interface Comum

Cada modulo de template exporta:
```python
PLATFORM: str          # "betha" | "ipam" | "egov" | "generico" | "selenium_base"
NAME: str              # Nome legivel
DESCRIPTION: str       # Descricao curta
URL_PATTERNS: list     # Padroes de URL com placeholder {slug}
SELECTORS: dict        # Seletores CSS default
parse_page(soup, url="", slug="", ibge="") -> list[dict]
```

**Registro:** `__init__.py:42-47` mapeia nome da plataforma para path do modulo.

### 2.2 Template Betha (`betha.py`)

**URL:** `{slug}.atende.net/transparencia` — ~80 municipios SC
**Estrategia de parsing** (linhas 64-123):
1. Tentar 8 seletores de tabela em ordem: `table.licitacao`, `table.tabela-licitacoes`, `table.table.table-striped`, `table.table`, `table[id*='licitacao']`, `table[id*='Licitacao']`, `table[id*='grid']`, `table`
2. Para cada tabela, extrair linhas com:
   - `td:nth-child(1)` -> data
   - `td:nth-child(2)` -> modalidade
   - `td:nth-child(3)` -> objeto
   - `td:nth-child(4)` -> orgao
   - `td:nth-child(5)` -> valor
   - `a[href]` -> link
3. Deduplicar por content_hash
4. Se nenhuma tabela funcionar (linhas 127-155): fallback div-based com 3 seletores de container e seletores de classe (`[class*='modalidade']`, `[class*='data']`, etc.)

### 2.3 Template Ipam (`ipam.py`)

**URL:** `{slug}.ipm.org.br/transparencia` — ~50 municipios SC
**Estrategia de parsing** (linhas 62-123):
1. Tentar 7 seletores de tabela: `table.tabela-padrao`, `table.grid`, `table.table.table-bordered`, `table.table`, `table[id*='grid']`, `table[id*='GridView']`, `table`
2. Extrair com acesso direto por indice de `td`: `tds[0]` a `tds[4]`
3. Colunas: modalidade, data, objeto, orgao, valor
4. Fallback generico (linhas 127-153): qualquer tabela com 2+ linhas

### 2.4 Template E-gov (`egov.py`)

**URL:** `{slug}.e-gov.betha.com.br` — ~40 municipios SC
**Estrategia de parsing** (linhas 63-146):
1. Buscar container com 5 seletores: `div.lista-licitacoes`, `div#lista-licitacoes`, `div.conteudo-licitacoes`, `div.resultado-licitacoes`, `section.licitacoes`
2. Dentro do container, tentar `<table>` — extrair linhas com `td:nth-child(1-4)`
3. Se nao achar tabela, tentar `<div>` items com classes: `[class*='modalidade']`, `[class*='data']`, etc.
4. Diferenca do Betha: colunas sao modalidade, data, objeto, valor (4 colunas, sem orgao)
5. Fallback generico (linhas 149-178): qualquer tabela na pagina

### 2.5 Template Generico (`generico.py`)

**Uso:** Portais nao identificados — ~125 municipios SC
**Tres estrategias em cascata** (linhas 74-92):

```
parse_page()
    -> _score_and_parse_tables()    # Estrategia 1
    -> _div_based_extraction()      # Estrategia 2
    -> _any_table_extraction()      # Estrategia 3
```

**Estrategia 1 — Keyword Scoring** (linhas 95-133):
- 14 keywords de licitacao
- Cada keyword vale 2 pontos
- Tabelas com 2+ linhas ganham bonus de 1 ponto
- Ordenacao: (-score, -row_count) — maior score, mais linhas primeiro

**Estrategia 2 — Div-Based** (linhas 211-258):
- 8 padroes CSS de container
- Items dentro de cada container
- Fallback de texto completo como objeto se `[class*='objeto']` nao existir

**Estrategia 3 — Any-Table** (linhas 261-271):
- Qualquer tabela com 4+ linhas e 2+ colunas

### 2.6 Template Selenium Base (`selenium_base.py`)

**Uso:** Portais JS-rendered (`requires_js: true`)
**Estrategia** (linhas 86-104):
1. `_table_extraction()` — tenta cada seletor da `lista_licitacoes` separadamente (split por virgula)
2. `_div_extraction()` — 8 padroes de container div
3. `_generic_table_fallback()` — qualquer tabela com 2+ colunas

**Suporte a paginacao** (linhas 52-63):
```python
_NEXT_PAGE_SELECTORS = [
    "a.next", "a[rel='next']", ".pagination .next a",
    ".pagination a:last-child", "button.next",
    "button[aria-label='Next']", "a[class*='proxima']",
    "a[class*='next']", "[class*='paginacao'] a:last-child", "li.next a",
]
```

---

## 3. Utilitarios Compartilhados (`base.py`)

### 3.1 `extract_text(element, selector="")` (linhas 16-32)
Extrai texto de um elemento. Se `selector` for vazio, usa o proprio elemento. Tratamento de `None` retorna `""`.

### 3.2 `extract_link(element, selector, base_url)` (linhas 34-47)
Extrai href de elemento `<a>`, resolvendo URLs relativas contra `base_url`.

### 3.3 `make_record(slug, ibge, portal_url, ...)` (linhas 50-84)
Factory de registro com: validacao (pelo menos modalidade, objeto ou data), geracao de `content_hash` MD5.

### 3.4 `parse_table_rows(soup, table_selector, ...)` (linhas 87-143)
Parsing generico de tabelas HTML — encontra tabela, itera `<tr>`, extrai celulas com seletores CSS, opcao de pular header.

### 3.5 `parse_div_list(soup, container_selector, ...)` (linhas 146-190)
Parsing generico de layouts div-based — encontra container, seleciona items, extrai campos.

---

## 4. Configuracao e Seletores

### 4.1 Schema YAML

```yaml
templates:
  portal_transparencia_net:
    name: "Portal Transparencia .NET"
    description: "..."
    selectors:
      lista_licitacoes: "table.licitacao"
      modalidade: "td:nth-child(2)"
      data: "td:nth-child(1)"
      objeto: "td:nth-child(3)"
      orgao: "td:nth-child(4)"
      valor: "td:nth-child(5)"
      link: "a"

municipios:
  chapeco:
    nome: "Chapeco"
    ibge: "4204202"
    portal_url: "https://chapeco.atende.net/transparencia"
    template: "portal_transparencia_net"   # referencia ao template
    requires_js: false
    ativo: true
```

### 4.2 Resolucao de Seletores

`_resolve_selectors()` (linhas 468-494) implementa a cascata:
1. Se `cfg.selectors` existe e tem `lista_licitacoes` -> devolver seletores custom
2. Se `cfg.template` existe e nao e "custom" -> buscar em `config.templates[tmpl].selectors`
3. Caso contrario -> None

### 4.3 Templates no Config YAML (4 definidos)

| Template Slug | Usado Por | Seletores |
|--------------|-----------|-----------|
| `portal_transparencia_net` | Betha (64 mun.) | 7 seletores |
| `e_gov_net` | E-gov (3 mun.) | 6 seletores (sem orgao) |
| `ipam` | Ipam (3 mun.) | 7 seletores (igual betha) |
| `custom` | Proprio (12 mun.) | Selectors por municipio |

---

## 5. Pipeline de Execucao

### 5.1 Crawl Interface (`crawl()`)

```
crawl(mode):
    "detect"     -> _crawl_detect("full")
    "incremental"-> _crawl_detect("incremental")  # skip existing
    "template"   -> crawl_template()
    "selenium"   -> crawl_selenium()
    "full"       -> _crawl_detect() + crawl_template()  # sequencial
```

### 5.2 Template Scraping (`crawl_template()`)

Para cada municipio no config:
1. Verificar `ativo: true`
2. Resolver seletores via `_resolve_selectors()`
3. Health check (HEAD)
4. Fetch HTML (GET)
5. Parse com BeautifulSoup
6. Extrair linhas com seletores
7. Delay TRANSPARENCIA_DELAY entre portais
8. Log de efetividade

### 5.3 Selenium Scraping (`crawl_selenium()`)

Igual ao template scraping, mas:
- Gate por `TRANSPARENCIA_SELENIUM_ENABLED`
- Gate por `requires_js` no config
- Usa `SeleniumCrawler.scrape()` que renderiza JS
- Fallback HTTP se Selenium nao disponivel

### 5.4 Batch Detection (`run_detect_all.py`)

1. Buscar todos os municipios SC do banco (`sc_public_entities`)
2. ThreadPoolExecutor com 30 workers
3. Cada worker chama `detect_platform()`
4. Delay de 0.5s entre requests
5. Gerar relatorio de distribuicao
6. Salvar resultados + municipios residuais

---

## 6. Normalizacao (`transform()`)

**Entrada:** Lista de records do crawl (com `portal_url`, `records`, `method`)
**Saida:** Lista normalizada para schema `pncp_raw_bids`

`_parse_valor()` — trata formato brasileiro: "R$ 1.234,56" -> 1234.56, aceita 5 formatos
`_parse_date()` — trata 3 formatos de data: DD/MM/YYYY, DD-MM-YYYY, YYYY-MM-DD

---

## 7. Fluxo de Dados

```
monitor.py:crawl("full")
    |
    v
transparencia_crawler.py:crawl("full")
    |
    +-> _crawl_detect("full")
    |       |
    |       +-> _load_entities()       -> data/municipios_sc.json ou stub
    |       +-> _load_existing_results() -> data/transparencia_platforms.json
    |       +-> detect_platform() para cada entidade
    |       +-> _save_results()        -> data/transparencia_platforms.json
    |
    +-> crawl_template()
            |
            +-> load_config()           -> config/transparencia_config.yaml
            +-> Para cada municipio:
            |       +-> health_check()  (HEAD)
            |       +-> _fetch_url()    (GET)
            |       +-> BeautifulSoup parse
            |       +-> _extract_row()  com selectors CSS
            |       +-> delay
            +-> _save_scrape_results() -> data/transparencia_scrape_results.json
    |
    v
transparencia_crawler.py:transform()
    |
    v
pncp_raw_bids upsert (via monitor.py)
```

---

## 8. Dependencias

| Dependencia | Uso | Obrigatoria? |
|------------|-----|--------------|
| Python 3.10+ | Runtime | Sim |
| `urllib` (stdlib) | HTTP requests | Sim |
| `json` (stdlib) | Persistencia | Sim |
| `hashlib` (stdlib) | Content hash | Sim |
| `re` (stdlib) | Parsing | Sim |
| `unicodedata` (stdlib) | Slugify | Sim |
| `concurrent.futures` (stdlib) | Batch detect | Sim |
| BeautifulSoup4 (`bs4`) | HTML parsing | Sim |
| PyYAML (`yaml`) | Config file | Sim |
| Selenium + webdriver | JS rendering | Opcional (env var) |
| psycopg2 | Banco dados batch | Opcional (run_detect_all) |

---

## 9. Metricas e Observabilidade

### Log de Efetividade

Ao final de `crawl_template()` (linhas 962-972):
```python
[OK] Chapeco              |  120 licitacoes | ok
[OK] Blumenau             |   85 licitacoes | ok
[XX] Cidade-exemplo       |    0 licitacoes | unreachable
---------------------------------------------------------
Total: 79 municipios | 65 ok | 14 erros | 5423 licitacoes
```

### Variaveis de Configuracao

| Variavel | Default | Escopo |
|----------|---------|--------|
| TRANSPARENCIA_TIMEOUT | 5 | Global |
| TRANSPARENCIA_REQUEST_DELAY | 0.5 | Global |
| TRANSPARENCIA_DELAY | 5.0 | crawl_template/crawl_selenium |
| TRANSPARENCIA_MAX_RETRIES | 1 | Global |
| TRANSPARENCIA_ENTITIES_FILE | data/municipios_sc.json | detect |
| TRANSPARENCIA_OUTPUT_DIR | data/ | detect+scrape |
| TRANSPARENCIA_CONFIG | config/transparencia_config.yaml | template+selenium |
| TRANSPARENCIA_SELENIUM_ENABLED | false | selenium |
| SELENIUM_TIMEOUT | 30 | selenium |
| SELENIUM_REQUEST_DELAY | 5.0 | selenium |
| SELENIUM_HEADLESS | true | selenium |

---

## 10. Riscos e Mitigacoes

| Risco | Probabilidade | Impacto | Mitigacao |
|-------|--------------|---------|-----------|
| Layout HTML muda no portal | Alta | Alto (seletores quebram) | Fallback generico, 3 niveis de parsing |
| Portal fora do ar | Media | Medio (perda da coleta) | Health check pre-scrape, log de efetividade |
| Selenium indisponivel | Baixa | Medio (sem JS) | Fallback HTTP automatico |
| Keyword scoring falso positivo | Media | Baixo (dados errados) | Content hash + dedup |
| Config YAML com 79+ entradas | Baixa | Baixo | Validacao nos testes (IBGE 7 dig, requires_js bool) |
| Novo municipio sem plataforma conhecida | Alta | Baixo | Fallback dominio proprio + template generico |

---

## 11. Referencias

- ADR-011: `_reversa_sdd/adrs/011-template-transparencia-crawler.md`
- Codigo principal: `scripts/crawl/transparencia_crawler.py`
- Templates: `scripts/crawl/transparencia_templates/` (base.py, betha.py, ipam.py, egov.py, generico.py, selenium_base.py, __init__.py)
- Batch detect: `scripts/transparencia/run_detect_all.py`
- Config generator: `scripts/crawl/generate_transparencia_config.py`
- Config: `config/transparencia_config.yaml`
- Testes: `tests/test_transparencia_crawler.py`
- Dados: `data/transparencia_platforms.json`, `data/transparencia_scrape_results.json`
- Deploy: `deploy/systemd/transparencia-crawl.{service,timer}`
- Sistema de arquivos: `scripts/crawl/`

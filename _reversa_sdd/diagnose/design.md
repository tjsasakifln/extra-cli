# Diagnose DOM-SC — Design Tecnico Detalhado (v2.0)

> Gerado pelo Writer em 2026-07-13 | doc_level: completo | Base: 249340d
> Arquivo fonte: `scripts/diagnose/dom_sc_diagnostic.py` (651 LOC)

## Visao Arquitetural

O modulo de diagnostico e um **script standalone** que executa 6 fases sequenciais
de verificacao, cada uma produzindo um fragmento do relatorio final. Nao ha estado
compartilhado entre fases — cada fase e uma funcao pura que recebe parametros e
retorna um dict.

```
┌──────────────────────────────────────────────────────────┐
│                    dom_sc_diagnostic.py                    │
│                                                           │
│  main() ──► parse_args()                                  │
│              │                                            │
│              ▼                                            │
│         run_diagnostic(sample_size, days)                  │
│              │                                            │
│              ├──► _check_credential_status()  ──► dict    │
│              ├──► _test_site_accessibility()  ──► dict    │
│              ├──► _test_all_categorias()      ──► dict    │
│              │       └── _api_request()  (helper)          │
│              ├──► _check_pagination_api()     ──► dict    │
│              ├──► _test_html_scraping_fallback() ──► dict │
│              └──► _load_uncovered_entities()  ──► list    │
│                                                           │
│              ▼                                            │
│         results = {dict}  ←─ agregado em run_diagnostic   │
│              │                                            │
│              ├──► print_diagnostic_report()  (terminal)   │
│              ├──► generate_markdown_report()  (.md file)  │
│              └──► json.dumps()  (--json flag)             │
└──────────────────────────────────────────────────────────┘
```

## Pipeline de Deteccao

### Algoritmo de Diagnostico

```
Entrada: sample_size (int, default 0), days (int, default 90)
Saida: dict com 7 chaves (diagnostic_date, lookback_days, date_from, date_to,
       credentials, site_accessibility, api_categorias, pagination,
       html_scraping, uncovered_entities, summary)

1.  date_to = today()
2.  date_from = date_to - timedelta(days=days)
3.  credentials ← enumerate 3 env vars, check non-empty
4.  site_accessibility ← HTTP GET 3 endpoints, capture status/bytes/content-type
5.  api_categorias ← for each in [6, 7, 28]:
      response = _api_request(remote/search, {categoria, data_inicio, data_fim, com_metadados})
      extract: total_publicacoes, total_municipios, total_orgaos_8, top5, has_metadados
6.  pagination ← for categoria=6:
      test 5 request variants: no-page, pagina=1, pagina=2, offset=0, offset=100
      classify pagination_supported ∈ {YES, PARTIAL, NO}
      classify offset_supported ∈ {YES, NO}
7.  html_scraping ← HTTP GET 2 HTML endpoints, check for captcha/form/html-structure
8.  uncovered_entities ← if sample_size > 0: SQL query sc_public_entities LEFT JOIN entity_coverage
9.  summary ← aggregate all results into verdict struct
10. return results dict
```

### Tratamento de Erros por Fase

Cada funcao e responsavel por capturar suas proprias excecoes e retornar um dict
com chave `_error` ou estrutura equivalente. O chamador (`run_diagnostic`) nunca
recebe excecoes nao tratadas das fases individuais.

```
Fase 1 (_check_credential_status):
  - Nao lanca excecoes (so le env vars)

Fase 2 (_test_site_accessibility):
  - HTTPError → retorna {"status": exc.code, "error": str(exc)}
  - URLError → retorna {"status": "ERROR", "error": str(exc)}
  - Exception → retorna {"status": "ERROR", "error": str(exc)}

Fase 3 (_api_request):
  - HTTPError 401 → retorna {"_error": "HTTP 401", "_detail": corpo}
  - HTTPError 429 → retorna {"_error": "HTTP 429", "_detail": corpo}
  - HTTPError other → retorna {"_error": "HTTP {code}", "_detail": corpo}
  - URLError → retorna {"_error": "URLError", "_detail": reason}
  - Exception → retorna {"_error": type.__name__, "_detail": str(exc)}

Fase 4 (_check_pagination_api):
  - Delega chamadas HTTP para _api_request (ja tratado)
  - Se API nao disponivel, retorna {"pagination_supported": "UNKNOWN", "error": msg}

Fase 5 (_test_html_scraping_fallback):
  - Mesmo tratamento de Fase 2

Fase 6 (_load_uncovered_entities):
  - psycopg2.Error → log.warning + retorna []
  - Exception → log.warning + retorna []
```

## Formatos de Dados

### Estrutura do Resultado (dict raiz)

```python
{
    "diagnostic_date": "2026-07-13",          # str, ISO date
    "lookback_days": 90,                       # int
    "date_from": "2026-04-14",                 # str, ISO date
    "date_to": "2026-07-13",                   # str, ISO date
    "credentials": {                           # dict[str, str]
        "DOM_SC_CPF": "OK (11 chars)",
        "DOM_SC_CNPJ": "OK (14 chars)",
        "DOM_SC_API_KEY": "MISSING"
    },
    "site_accessibility": {                    # dict[str, dict]
        "homepage": {
            "status": 200,                     # int | str ("ERROR")
            "bytes": 12345,                    # int
            "content_type": "text/html"        # str
        },
        "api_docs": { ... },
        "site_login": { ... }
    },
    "api_categorias": {                        # dict[str, dict]
        "categoria_6": {
            "status": "OK",                    # str: "OK" | "FAIL" | "ERROR"
            "nome": "Contrato",
            "total_publicacoes": 1500,
            "total_municipios": 293,
            "total_orgaos_8": 450,
            "top5_municipios": [
                ["Florianopolis", 230],
                ["Joinville", 180],
                ...
            ],
            "has_metadados": True,
            "sample_municipios": ["Abdon Batista", "Abelardo Luz", ...]
        },
        "categoria_7": { ... },
        "categoria_28": { ... }
    },
    "pagination": {                             # dict
        "total_sem_paginacao": 1500,
        "total_com_pagina_1": 100,
        "total_com_pagina_2": 100,
        "total_com_offset_0": 1500,
        "total_com_offset_100": 1400,
        "pagination_supported": "YES",          # str: "YES" | "PARTIAL" | "NO" | "UNKNOWN"
        "offset_supported": "YES",              # str: "YES" | "NO"
        "observations": [
            "Pagination via 'pagina' parameter IS supported by the API"
        ]
    },
    "html_scraping": {                          # dict[str, dict]
        "public_search": {
            "status": 200,
            "bytes": 35000,
            "has_html": True,
            "has_captcha": False,
            "has_form": True,
            "sample": "<!DOCTYPE html>..."
        },
        "advanced_search": { ... }
    },
    "uncovered_entities": {                     # dict
        "total": 0 | int,
        "sample": [],
        "municipios": []
    },
    "summary": {                                # dict
        "categorias_ok": 3,
        "categorias_fail": 0,
        "total_categorias": 3,
        "site_acessivel": True,
        "pagination_supported": "YES",
        "credentials_ok": True
    }
}
```

### Formato do Relatorio Markdown

8 secoes, cada uma mapeando diretamente a uma fase do diagnostico:

1. Credentials Status — Tabela `| Variable | Status |`
2. Site Accessibility — Tabela `| Endpoint | Status | Details |`
3. API per Categoria — Tabela `| Categoria | Status | Publicacoes | Municipios | Orgaos(8) |`
4. Pagination Support — Lista com valores por parametro
5. HTML Scraping Fallback Viability — Tabela `| Endpoint | Status | Size | Captcha | Form |`
6. Uncovered Entities Analysis — Lista com totais e amostra
7. Summary — Lista de metrica: valor
8. Recommendations — Lista priorizada com tags `[HIGH]`, `[DONE]`, `[ACTION]`

### Formato de Saida Terminal

Secoes numeradas (1. a 6.) com indentacao fixa de 5 espacos.
Icones: `OK` / `FAIL` / `WARN` com codigo de cores ASCII (via terminal, semANSI explicito).
Summary final com barra de `=` (72 chars).

## Dependencias

### Internas (do projeto)

| Dependencia | Path | Uso | Linhas |
|-------------|------|-----|--------|
| `scripts.crawl.security.USER_AGENT` | `scripts/crawl/security.py` | User-Agent header para requests HTTP | 63, 103, 247 |
| `scripts.crawl.security.sanitize_url_param` | `scripts/crawl/security.py` | Sanitizacao de parametros URL | 63, 65 |
| `config.settings.DEFAULT_DSN` | `config/settings.py` | DSN do banco de dados PostgreSQL | 278 |

### Externas (stdlib)

| Dependencia | Modulo | Uso | Linhas |
|-------------|--------|-----|--------|
| `urllib.request` | stdlib | HTTP GET requests (3 usos distintos) | 56, 92-93, 244-245 |
| `urllib.error` | stdlib | Tratamento de erros HTTP/URL | 55-57, 91-93, 243-245 |
| `base64` | stdlib | Codificacao Basic Auth | 55, 69 |
| `json` | stdlib | Parsing de resposta API e output --json | 16, 79-80, 630 |
| `argparse` | stdlib | Parsing de argumentos CLI | 15, 605-611 |
| `logging` | stdlib | Logger estruturado | 17, 30, 300 |
| `os` | stdlib | Acesso a env vars | 18, 59-61, 308-309 |
| `sys` | stdlib | Path insert, exit code | 19, 27-28, 651 |
| `collections.Counter` | stdlib | Top5 municipios | 20, 140-141 |
| `datetime.date, timedelta` | stdlib | Janela temporal | 21, 327-328 |
| `pathlib.Path` | stdlib | Manipulacao de path de output | 22, 637-640 |
| `typing.Any` | stdlib | Type hints genericos | 23, 50 |

### Opcionais (try/except)

| Dependencia | Uso | Fallback | Linhas |
|-------------|-----|----------|--------|
| `psycopg2` | Conexao com PostgreSQL para consultar entidades nao cobertas | Retorna `[]` com warning | 280-281, 299-301 |

## Algoritmos de Pattern Matching

### Algoritmo 1: Classificacao de Paginacao

```
Entrada: total_sem_pagina, total_p1, total_p2, total_o0, total_o100 (ints >= 0)
Saida: dict { pagination_supported, offset_supported, observations }

SE total_p1 > 0 E total_p2 >= 0 E total_p1 != total_p2:
    pagination_supported = "YES"
SENAO SE total_p1 > 0:
    pagination_supported = "PARTIAL"
SENAO:
    pagination_supported = "NO"

SE total_o0 > 0 E total_o100 >= 0 E total_o0 != total_o100:
    offset_supported = "YES"
SENAO:
    offset_supported = "NO"

SE total_sem_pagina > 1000 E pagination_supported != "YES":
    observation = "WARN: mais de 1000 records sem paginacao — truncamento possivel"

SE pagination_supported == "YES" AND offset_supported == "NO":
    observation = "Usar 'pagina' no crawler (offset nao funciona)"
```

OBS: A condicao `total_p1 != total_p2` pode ser falsa mesmo com paginacao funcional
se houver exatamente 100 registros (tamanho de pagina fixo) — e uma limitacao
conhecida do algoritmo. Nesse caso ambos retornam 100 e o diagnostico conclui
"PARTIAL". (Linhas 211-217)

### Algoritmo 2: Deteccao de CAPTCHA em HTML

```
Entrada: body (str) — HTML bruto
Saida: has_captcha (bool)

SE "captcha" in body.lower() OU "recaptcha" in body.lower():
    has_captcha = True
SENAO:
    has_captcha = False
```

Deteccao simples por substring — nao usa heuristica de DOM ou regex.
Falsos positivos possiveis se "captcha" aparecer em texto informativo.
(Linha 264)

### Algoritmo 3: Agregacao de Summary

```
Entrada: results dict completo
Saida: summary dict { categorias_ok, categorias_fail, total_categorias,
                      site_acessivel, pagination_supported, credentials_ok }

categorias_ok = count(v in api_categorias where v.status == "OK")
categorias_fail = count(v in api_categorias where v.status != "OK")
site_acessivel = any(v in site_accessibility where v.status == 200)
credentials_ok = all(v in credentials where v.startswith("OK"))
```

(Linhas 363-377)

## Mapa de Funcoes

| Funcao | Visibilidade | Parametros | Retorno | Linhas | Complexidade Ciclomatica |
|--------|-------------|------------|---------|--------|-------------------------|
| `_api_request` | privada | url: str, params: dict | dict \| None | 50-86 | 5 (try internos) |
| `_test_site_accessibility` | privada | (nenhum) | dict | 89-117 | 4 (3 endpoints + except) |
| `_test_all_categorias` | privada | date_from, date_to | dict | 120-160 | 4 (3 categorias + tratamento) |
| `_check_pagination_api` | privada | date_from, date_to | dict | 163-234 | 6 (5 requests + condicoes) |
| `_test_html_scraping_fallback` | privada | (nenhum) | dict | 237-273 | 3 (2 endpoints + except) |
| `_load_uncovered_entities` | privada | (nenhum) | list[dict] | 276-301 | 3 (try/except) |
| `_check_credential_status` | privada | (nenhum) | dict | 304-314 | 1 (loop simples) |
| `run_diagnostic` | publica | sample_size, days | dict | 317-379 | 2 (if sample > 0) |
| `print_diagnostic_report` | publica | results: dict | None | 382-479 | 6 (6 secoes) |
| `generate_markdown_report` | publica | results: dict | str | 482-602 | 5 (6 secoes + recomendacoes) |
| `parse_args` | publica | (nenhum) | Namespace | 605-611 | 1 |
| `main` | publica | (nenhum) | int | 614-651 | 4 (args, json, output, exit) |

## Decisoes de Design

### D1 — Diagnostico separado do crawler operacional 🟢

**Decisao:** O diagnostico e um script standalone, nao um modo do crawler.

**Justificativa:**
- Independencia: se o crawler quebrar, o diagnostico ainda funciona
- Isolamento de configuracao: diagnostico pode testar variacoes de parametros sem afetar estado do crawler
- Seguranca: diagnostico nao escreve no banco de dados

**Risco:** Duplicacao de constantes (`BASE_URL`, `CATEGORIAS`, etc.) pode divergir.
**Mitigacao:** Documentar que diagnostic constants devem ser atualizadas manualmente quando o crawler mudar.

### D2 — Reimplementacao propria do HTTP client 🟢

**Decisao:** O diagnostico reimplementa `_api_request` em vez de importar a do crawler.

**Justificativa:**
- Isolamento de bugs: se o crawler tiver um bug de autenticacao, o diagnostico deve detecta-lo
- Simplicidade: sem dependencia de classe abstrata ou interface

**Risco:** Duas implementacoes para manter.
**Mitigacao:** A implementacao do diagnostico e significativamente mais simples (sem retry, sem caching).

### D3 — Sem testes automatizados 🔴

**Decisao:** Nao ha testes unitarios para o diagnostico.

**Risco:** 🔴 Alto — 12 funcoes sem cobertura, refatoracao perigosa.
**Mitigacao:** Criar suite de testes com mock de `urllib.request` e `psycopg2`.

### D4 — Script unico monolítico 🟡

**Decisao:** 651 LOC em 1 arquivo.

**Justificativa:** Script de diagnostico e ferramenta de engenharia reversa, raramente modificado.
Tamanho atual (651 LOC) e gerenravel — nao justifica decomposicao.

**Risco:** Se crescer para > 1500 LOC, extrair `_api_request` e formatadores para modulos separados.

### D5 — Saida em 3 formatos 🟢

**Decisao:** Terminal (human-readable), Markdown (documentacao), JSON (integracao).

**Justificativa:**
- Terminal: uso interativo rapido
- Markdown: versionamento em docs/research/
- JSON: consumo por ferramentas externas e pipelines

## Riscos e Lacunas

| Risco | Probabilidade | Impacto | Confianca | Mitigacao |
|-------|--------------|---------|-----------|-----------|
| API DOM-SC muda endpoint ou formato de resposta | Alta | Alto | 🔴 | Diagnostico detecta a quebra imediatamente; HTML fallback como alternativa |
| Credenciais expiradas sem aviso | Media | Alto | 🟡 | Diagnostico valida antes de cada crawl operacional |
| Portal adiciona CAPTCHA/JS Challenge | Media | Alto | 🟡 | Diagnostico detecta via `has_captcha`; viabiliza fallback por API |
| Banco de dados indisponivel para consulta de cobertura | Baixa | Baixo | 🟢 | Falha graciosa com `[]` — diagnostico continua |
| Pagina 1 e pagina 2 retornam mesmo resultado (dados estaticos) | Baixa | Medio | 🟡 | Algoritmo classifica como PARTIAL — requer inspecao manual |
| Constantes divergirem do crawler apos refatoracao | Media | Medio | 🟡 | Sync manual; idealmente centralizar constantes compartilhadas |

## Confianca

| Item | Confianca | Justificativa |
|------|-----------|---------------|
| Precisao do design | 🟢 | Mapa completo de funcoes, formatos e fluxo de execucao |
| Algoritmos de deteccao | 🟡 | Algoritmo de paginacao tem limitacao conhecida (pagina unica) |
| Tratamento de erros | 🟢 | Cada fase captura proprios erros, nenhuma excecao propaga |
| Formatos de saida | 🟢 | 3 formatos documentados com estrutura exata dos dicts |
| Dependencias | 🟢 | Mapa completo com linhas de origem e fallbacks de opcionais |
| Cobertura de testes | 🔴 | Zero testes — maior lacuna tecnica do modulo |

# Diagnose DOM-SC — Requisitos Detalhados (v2.0)

> Gerado pelo Writer em 2026-07-13 | doc_level: completo | Base: 249340d
> Arquivo fonte: `scripts/diagnose/dom_sc_diagnostic.py` (651 LOC, 12 funcoes)
> Crawler integrado: `scripts/crawl/dom_sc_crawler.py` (603 LOC)

## Visao Geral

Modulo de diagnostico autonomo do crawler DOM-SC. Nao e um pipeline operacional --
e uma ferramenta de engenharia reversa e troubleshooting para investigar falhas de
cobertura, quebras de API, autenticacao e paginacao no portal do Diario Oficial dos
Municipios de Santa Catarina (https://diariomunicipal.sc.gov.br).

Executado sob demanda (nao por scheduler). Seus reports alimentam decisoes de
configuracao do crawler operacional e identificam municipios com lacunas de cobertura.

## Responsabilidades

- Diagnostico autonomo de conectividade e autenticacao do portal DOM-SC
- Deteccao de parametros de paginacao suportados pela API REST
- Validacao de coverage por categoria (Contrato, Convenio, Empenho)
- Analise de viabilidade de HTML scraping como fallback
- Identificacao de entidades nao cobertas no banco de dados
- Geracao de relatorio estruturado (terminal + markdown + JSON)

## Arquitetura de Deteccao em Fases

O diagnostico executa 6 fases sequenciais, cada uma dependendo da anterior:

```
Fase 1: Credenciais     →  Fase 2: Acessibilidade Site
                                    ↓
Fase 3: API por Categoria  →  Fase 4: Paginacao
                                    ↓
Fase 5: HTML Scraping Fallback  →  Fase 6: Entidades Nao Cobertas
```

Cada fase e independente (nao bloqueia as seguintes em caso de falha), mas os
resultados sao agregados no sumario final.

## Requisitos Funcionais

### Fase 1 — Validacao de Credenciais

| ID | Requisito | Prioridade | Fonte | Linhas |
|----|-----------|-----------|-------|--------|
| RF-DG01 | Ler e validar as 3 variaveis de ambiente obrigatorias: `DOM_SC_CPF`, `DOM_SC_CNPJ`, `DOM_SC_API_KEY` | Must | `_check_credential_status()` | 304-314 |
| RF-DG02 | Reportar individualmente cada variavel como `OK (N chars)` ou `MISSING` | Must | `_check_credential_status()` | 306-313 |
| RF-DG03 | Agregar status no sumario: `credentials_ok: true/false` | Must | `run_diagnostic()` summary | 376 |

**Criterios de aceite:**
- [ ] RF-DG01: Se qualquer variavel estiver vazia, o diagnostico continua mas o sumario reflete `credentials_ok: false`
- [ ] RF-DG02: A saida mostra cada variavel com seu status individual
- [ ] RF-DG03: O codigo de saida do script e 1 se credenciais estiverem incompletas

### Fase 2 — Acessibilidade do Site

| ID | Requisito | Prioridade | Fonte | Linhas |
|----|-----------|-----------|-------|--------|
| RF-DG04 | Testar acesso HTTP a 3 endpoints: homepage (`/`), docs API (`/?r=site/page&view=integracao`), login (`/?r=site/login`) | Must | `_test_site_accessibility()` | 89-117 |
| RF-DG05 | Para cada endpoint, capturar: status code, bytes retornados, content-type | Must | `_test_site_accessibility()` | 106-116 |
| RF-DG06 | Tratar erros HTTP (4xx, 5xx) e excecoes de rede sem abortar o diagnostico | Must | `_test_site_accessibility()` | 113-116 |
| RF-DG07 | Usar `User-Agent` customizado de `scripts.crawl.security.USER_AGENT` para evitar bloqueios | Must | `_test_site_accessibility()` | 103, 105 |

**Criterios de aceite:**
- [ ] RF-DG04: Testa exatamente os 3 endpoints listados, com timeout de 15s cada
- [ ] RF-DG05: O resultado inclui `status` (int), `bytes` (int), `content_type` (str)
- [ ] RF-DG06: Erro HTTP retorna dict com `status` e `error` — nunca `None` ou excecao nao tratada
- [ ] RF-DG07: O header `User-Agent` e sempre o mesmo do crawler operacional

### Fase 3 — API por Categoria

| ID | Requisito | Prioridade | Fonte | Linhas |
|----|-----------|-----------|-------|--------|
| RF-DG08 | Consultar API `/remote/search` para cada categoria (6=Contrato, 7=Convenio, 28=Empenho) com janela temporal configuravel | Must | `_test_all_categorias()` | 120-160 |
| RF-DG09 | Para cada categoria, extrair: total de publicacoes, total de municipios, total de orgaos (CNPJ 8), top5 municipios | Must | `_test_all_categorias()` | 150-158 |
| RF-DG10 | Verificar presenca de metadados nas primeiras 50 publicacoes de cada categoria | Should | `_test_all_categorias()` | 157 |
| RF-DG11 | Usar autenticacao Basic Auth + X-API-Key + User-Agent na chamada | Must | `_api_request()` | 50-86 |
| RF-DG12 | Retornar erro estruturado se a API nao responder (timeout, HTTP erro, excecao) | Must | `_api_request()` | 81-86 |

**Criterios de aceite:**
- [ ] RF-DG08: A janela temporal padrao e 90 dias, mas aceita parametro `--days`
- [ ] RF-DG09: `top5_municipios` e uma lista de tuplas `(municipio, count)` ordenada por frequencia descendente
- [ ] RF-DG10: `has_metadados` e `true` se qualquer publicacao entre as primeiras 50 tiver campo `metadados` preenchido
- [ ] RF-DG11: A requisicao inclui exatamente os 3 headers de autenticacao + Accept JSON
- [ ] RF-DG12: Erro HTTP inclui codigo + corpo da resposta (truncado em 500 chars)

### Fase 4 — Deteccao de Paginacao

| ID | Requisito | Prioridade | Fonte | Linhas |
|----|-----------|-----------|-------|--------|
| RF-DG13 | Testar se o parametro `pagina` e suportado pela API, comparando pagina 1 vs pagina 2 | Must | `_check_pagination_api()` | 163-234 |
| RF-DG14 | Testar se o parametro `offset` e suportado, comparando offset=0 vs offset=100 | Should | `_check_pagination_api()` | 196-202 |
| RF-DG15 | Classificar suporte como `YES`, `PARTIAL` ou `NO` com base nos resultados | Must | `_check_pagination_api()` | 211-217 |
| RF-DG16 | Gerar observacoes textuais sobre truncamento (mais de 1000 records sem paginacao) | Should | `_check_pagination_api()` | 224-232 |

**Criterios de aceite:**
- [ ] RF-DG13: `pagination_supported = YES` se pagina 1 e pagina 2 retornam resultados diferentes (positivos)
- [ ] RF-DG14: `offset_supported = YES` se offset=0 e offset=100 retornam resultados diferentes
- [ ] RF-DG15: `PARTIAL` significa que pagina 1 funciona mas pagina 2 retorna 0 (ou igual a pagina 1)
- [ ] RF-DG16: A observacao de truncamento so aparece se o total sem paginacao > 1000

### Fase 5 — HTML Scraping Fallback

| ID | Requisito | Prioridade | Fonte | Linhas |
|----|-----------|-----------|-------|--------|
| RF-DG17 | Testar acesso a pagina publica de search (`/remote/search`) e advanced search (`/advancedSearch`) | Must | `_test_html_scraping_fallback()` | 237-273 |
| RF-DG18 | Detectar presenca de CAPTCHA no HTML retornado | Must | `_test_html_scraping_fallback()` | 264 |
| RF-DG19 | Verificar se o HTML contem formulario (`<form>`) viavel | Should | `_test_html_scraping_fallback()` | 265 |
| RF-DG20 | Validar que o HTML retornado e valido (contem `<html>` ou `<!doctype>`) | Should | `_test_html_scraping_fallback()` | 263 |

**Criterios de aceite:**
- [ ] RF-DG17: Cada endpoint e testado com timeout de 15s e User-Agent customizado
- [ ] RF-DG18: `has_captcha` e `true` se o HTML contiver "captcha" ou "recaptcha" (case-insensitive)
- [ ] RF-DG19: `has_form` e `true` se o HTML contiver `<form`
- [ ] RF-DG20: `has_html` e `true` se o HTML comecar com tag html ou doctype

### Fase 6 — Analise de Entidades Nao Cobertas

| ID | Requisito | Prioridade | Fonte | Linhas |
|----|-----------|-----------|-------|--------|
| RF-DG21 | Consultar banco de dados por entidades ativas (`sc_public_entities.is_active = true`) sem cobertura registrada (`entity_coverage.is_covered = true`) | Should | `_load_uncovered_entities()` | 276-301 |
| RF-DG22 | Retornar amostra limitada pelo parametro `--sample` para analise direcionada | Should | `_load_uncovered_entities()` + `run_diagnostic()` | 353-359 |
| RF-DG23 | Agrupar entidades nao cobertas por municipio para planejamento de crawl | Should | `_load_uncovered_entities()` (ORDER BY municipio) + `run_diagnostic()` | 358 |
| RF-DG24 | Falhar graciosamente se o banco de dados estiver indisponivel (log warning, retornar lista vazia) | Must | `_load_uncovered_entities()` | 299-301 |

**Criterios de aceite:**
- [ ] RF-DG21: A query SQL usa LEFT JOIN / NOT IN entre `sc_public_entities` e `entity_coverage`
- [ ] RF-DG22: `--sample 0` (padrao) pula a consulta ao banco — nao causa erro de conexao
- [ ] RF-DG23: A lista de municipios e deduplicada e ordenada alfabeticamente
- [ ] RF-DG24: Se `psycopg2` nao estiver instalado ou `DEFAULT_DSN` for invalido, retorna `[]` sem abortar

### Fase 7 — Geracao de Relatorio

| ID | Requisito | Prioridade | Fonte | Linhas |
|----|-----------|-----------|-------|--------|
| RF-DG25 | Gerar relatorio legivel em terminal com todas as 6 fases formatadas | Must | `print_diagnostic_report()` | 382-479 |
| RF-DG26 | Gerar relatorio em markdown para exportacao a `docs/research/` | Should | `generate_markdown_report()` | 482-602 |
| RF-DG27 | Suportar saida JSON raw via flag `--json` para consumo por ferramentas | Should | `main()` | 629-630 |
| RF-DG28 | Incluir secao de recomendacoes acionaveis no relatorio markdown | Should | `generate_markdown_report()` | 584-600 |

**Criterios de aceite:**
- [ ] RF-DG25: O terminal mostra icones OK/FAIL/WARN com indentacao de 5 espacos
- [ ] RF-DG26: O markdown e salvo no path especificado por `--output`; se omitido, gera mas nao salva
- [ ] RF-DG27: `--json` printa JSON puro no stdout e **não** printa o relatorio texto
- [ ] RF-DG28: Recomendacoes sao categorizadas como `[HIGH]`, `[DONE]`, `[ACTION]` conforme urgencia

## Regras de Negocio

### RN-DG01 — Diagnostico nao e pipeline operacional
Diagnostico e exploratorio, rodado sob demanda. Nunca agendado em scheduler.
Sua execucao nao altera estado do banco de dados nem do crawler.

### RN-DG02 — Independencia entre fases
Cada fase de diagnostico trata seus proprios erros. Falha em Fase 1 (credenciais)
nao impede Fase 2 (acessibilidade) — embora Fase 3 (API) certamente falhe sem
credenciais, o erro sera capturado individualmente por categoria.

### RN-DG03 — Mirror do crawler, nao duplicacao
O diagnostico reimplementa `_api_request` de forma independente do crawler para
isolar problemas. As constantes (`BASE_URL`, `CATEGORIAS`, `HTTP_TIMEOUT`) sao
copiadas intencionalmente — se o crawler tiver um bug de configuracao, o diagnostico
deve detecta-lo.

### RN-DG04 — Janela temporal compativel com crawler
O padrao de 90 dias reflete a janela operacional do crawler. O parametro `--days`
permite estender para 180 ou 365 dias para diagnosticos de cobertura historica.

### RN-DG05 — Categorias fixas
Apenas 3 categorias sao diagnosticadas: 6 (Contrato), 7 (Convenio), 28 (Empenho).
Estas sao as categorias com metadados estruturados obrigatorios no DOM-SC.

## Criterios de Aceite Gherkin

```gherkin
Cenario: Diagnostico completo com credenciais validas
  Dado que as variaveis DOM_SC_CPF, DOM_SC_CNPJ, DOM_SC_API_KEY estao definidas
  E o site diariomunicipal.sc.gov.br esta acessivel
  Quando executo "python scripts/diagnose/dom_sc_diagnostic.py --days 30"
  Entao o codigo de saida e 0
  E o relatorio mostra "OK" para todas as 3 categorias
  E o relatorio mostra suporte de paginacao (YES, PARTIAL ou NO)

Cenario: Diagnostico com credenciais faltando
  Dado que DOM_SC_API_KEY nao esta definida
  Quando executo "python scripts/diagnose/dom_sc_diagnostic.py"
  Entao o codigo de saida e 1
  E o relatorio marca DOM_SC_API_KEY como "MISSING"
  E as categorias aparecem como "FAIL"

Cenario: Diagnostico com sample de entidades
  Dado que o banco de dados esta acessivel
  E existem entidades sem cobertura registrada
  Quando executo "python scripts/diagnose/dom_sc_diagnostic.py --sample 10"
  Entao a secao 6 do relatorio mostra "Uncovered Entities: N" (N > 0)
  E lista ate 10 entidades nao cobertas

Cenario: Saida JSON
  Dado que o diagnostico executa com sucesso
  Quando executo "python scripts/diagnose/dom_sc_diagnostic.py --json"
  Entao a saida stdout e um JSON valido
  E contem as chaves: credentials, site_accessibility, api_categorias, pagination, html_scraping, summary

Cenario: Diagnostico com site fora do ar
  Dado que diariomunicipal.sc.gov.br retorna 503
  Quando executo "python scripts/diagnose/dom_sc_diagnostic.py"
  Entao o relatorio mostra "FAIL" nos endpoints de acessibilidade
  E as categorias aparecem como "FAIL"
  E o codigo de saida e 1

Cenario: Exportacao do relatorio markdown
  Dado que o diagnostico executa com sucesso
  Quando executo "python scripts/diagnose/dom_sc_diagnostic.py --output /tmp/diag.md"
  Entao o arquivo /tmp/diag.md e criado
  E contem as 8 secoes (Credenciais a Recomendacoes)
```

## Matriz de Rastreabilidade

| RF ID | Fase | Funcao | Linhas | Testavel? | Prioridade |
|-------|------|--------|--------|-----------|------------|
| RF-DG01 | 1 | `_check_credential_status` | 304-314 | Sim (mock env vars) | Must |
| RF-DG02 | 1 | `_check_credential_status` | 306-313 | Sim | Must |
| RF-DG03 | 1 | `run_diagnostic` summary | 376 | Sim | Must |
| RF-DG04 | 2 | `_test_site_accessibility` | 89-117 | Sim (mock urllib) | Must |
| RF-DG05 | 2 | `_test_site_accessibility` | 106-116 | Sim | Must |
| RF-DG06 | 2 | `_test_site_accessibility` | 113-116 | Sim | Must |
| RF-DG07 | 2 | `_test_site_accessibility` | 103, 105 | Sim | Must |
| RF-DG08 | 3 | `_test_all_categorias` | 120-160 | Parcial (requer API real) | Must |
| RF-DG09 | 3 | `_test_all_categorias` | 150-158 | Parcial | Must |
| RF-DG10 | 3 | `_test_all_categorias` | 157 | Parcial | Should |
| RF-DG11 | 3 | `_api_request` | 50-86 | Sim | Must |
| RF-DG12 | 3 | `_api_request` | 81-86 | Sim | Must |
| RF-DG13 | 4 | `_check_pagination_api` | 163-234 | Parcial | Must |
| RF-DG14 | 4 | `_check_pagination_api` | 196-202 | Parcial | Should |
| RF-DG15 | 4 | `_check_pagination_api` | 211-217 | Parcial | Must |
| RF-DG16 | 4 | `_check_pagination_api` | 224-232 | Parcial | Should |
| RF-DG17 | 5 | `_test_html_scraping_fallback` | 237-273 | Sim (mock urllib) | Must |
| RF-DG18 | 5 | `_test_html_scraping_fallback` | 264 | Sim | Must |
| RF-DG19 | 5 | `_test_html_scraping_fallback` | 265 | Sim | Should |
| RF-DG20 | 5 | `_test_html_scraping_fallback` | 263 | Sim | Should |
| RF-DG21 | 6 | `_load_uncovered_entities` | 276-301 | Parcial (requer DB) | Should |
| RF-DG22 | 6 | `_load_uncovered_entities` + `run_diagnostic` | 353-359 | Parcial | Should |
| RF-DG23 | 6 | `_load_uncovered_entities` | 358 | Parcial | Should |
| RF-DG24 | 6 | `_load_uncovered_entities` | 299-301 | Sim (mock psycopg2) | Must |
| RF-DG25 | 7 | `print_diagnostic_report` | 382-479 | Sim (capture stdout) | Must |
| RF-DG26 | 7 | `generate_markdown_report` | 482-602 | Sim | Should |
| RF-DG27 | 7 | `main` | 629-630 | Sim | Should |
| RF-DG28 | 7 | `generate_markdown_report` | 584-600 | Sim | Should |

## Glossario

| Termo | Definicao |
|-------|-----------|
| DOM-SC | Diario Oficial dos Municipios de Santa Catarina |
| Categoria 6 | Contratos — atos com metadados estruturados obrigatorios |
| Categoria 7 | Convenios — atos com metadados estruturados obrigatorios |
| Categoria 28 | Empenhos — atos com metadados estruturados obrigatorios |
| Entity Coverage | Tabela `entity_coverage` no banco que registra se uma entidade ja foi coberta pelo crawler |
| CNPJ 8 | Primeiros 8 digitos do CNPJ (identificador do orgao/empresa, sem filial) |
| HTML Scraping Fallback | Estrategia alternativa quando a API REST nao esta disponivel |

## Confianca

| Item | Confianca | Justificativa |
|------|-----------|---------------|
| Cobertura de requisitos | 🟢 | 28 RFs mapeados, todos com linha de fonte e criterios de aceite |
| Precisao de LOC | 🟢 | Arquivo fonte tem 651 LOC (verificado), nao ~25K como documentacao anterior indicava |
| Completude funcional | 🟢 | Todas as 12 funcoes publicas/privadas mapeadas a requisitos |
| Testabilidade | 🟡 | RFs de Fase 3 e 4 dependem de API externa — requerem fixtures HTTP para testes deterministicos |
| Integracao com crawler | 🟡 | Crawler operacional (`dom_sc_crawler.py`) tem 603 LOC — diagnostico e independente mas espelha constantes |

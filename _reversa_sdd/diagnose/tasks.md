# Diagnose DOM-SC — Plano de Execucao (v2.0)

> Gerado pelo Writer em 2026-07-13 | doc_level: completo | Base: 249340d
> Arquivo fonte: `scripts/diagnose/dom_sc_diagnostic.py` (651 LOC, 12 funcoes)
> Complexidade: SIMPLES (8 pontos — 1 arquivo, sem dependencias externas obrigatorias)
> Workflow: Spec Pipeline → SDC (YOLO mode)

## Estrategia de Execucao

O arquivo atual tem 651 LOC — **nao recomendo decomposicao**. E gerenravel no
tamanho atual. As tarefas abaixo focam em:

1. Testes (prioridade maxima — cobertura atual: 0%)
2. Documentacao (ja parcialmente coberta por este spec)
3. Melhorias incrementais no diagnostico
4. Integracao com o crawler operacional

## Tarefas

| # | Tarefa | Esforco | Confianca | Depende de |
|---|--------|---------|-----------|------------|
| T-DG01 | Suite de testes: mock HTTP para Fase 2 e 5 | 4h | 🟢 | — |
| T-DG02 | Suite de testes: mock API para Fase 3 | 4h | 🟢 | — |
| T-DG03 | Suite de testes: paginacao (Fase 4) | 3h | 🟢 | — |
| T-DG04 | Suite de testes: entidades nao cobertas (Fase 6) | 3h | 🟡 | — |
| T-DG05 | Suite de testes: formatadores de relatorio | 3h | 🟢 | — |
| T-DG06 | Suite de testes: integracao (end-to-end) | 4h | 🟡 | T-DG01 a T-DG05 |
| T-DG07 | Adicionar deteccao de categoria adicional (ex: 29 = Licitação) | 2h | 🟡 | — |
| T-DG08 | Adicionar flag `--include-sample-html` para salvar amostra HTML | 2h | 🟢 | — |
| T-DG09 | Extrair constantes compartilhadas para modulo comum com crawler | 2h | 🟡 | — |
| T-DG10 | Integrar diagnostico como modo `--diagnose` no crawler CLI | 4h | 🟡 | T-DG01 a T-DG06 |
| T-DG11 | Validar CEPs e enderecos nas publicacoes (enriquecimento) | 3h | 🔴 | — |
| T-DG12 | Adicionar deteccao de taxa de erro por municipio | 3h | 🟡 | T-DG06 |

**Estimativa total:** 37h (5 dias) — inclui testes, melhorias e integracao.

---

## Detalhamento das Tarefas

### T-DG01 — Suite de testes: mock HTTP para Fase 2 e 5

**Descricao:** Criar testes unitarios para `_test_site_accessibility()` e
`_test_html_scraping_fallback()` usando mock de `urllib.request.urlopen`.

**Arquivos:**
- `tests/diagnose/test_dom_sc_diagnostic.py` (novo)
- `scripts/diagnose/dom_sc_diagnostic.py` (sem alteracoes — usa `unittest.mock`)

**Cenarios de teste:**
1. Homepage retorna 200 com HTML valido
2. Endpoint retorna 404 → capturado como `{"status": 404, "error": "..."}`
3. Endpoint retorna timeout → `URLError` capturado
4. HTML com CAPTCHA → `has_captcha = True`
5. HTML sem formulario → `has_form = False`
6. Conteudo binario (nao HTML) → `has_html = False`

**Criterios de aceite:**
- [ ] 6+ cenarios implementados com `@patch('urllib.request.urlopen')`
- [ ] Testes nao fazem requisicoes reais
- [ ] Mock de `urllib.error.HTTPError` usa `add_side_effect`
- [ ] `pytest tests/diagnose/test_dom_sc_diagnostic.py -v` passa
- [ ] Cobertura das funcoes >= 90%

---

### T-DG02 — Suite de testes: mock API para Fase 3

**Descricao:** Testar `_test_all_categorias()` e `_api_request()` com
respostas mockadas da API DOM-SC.

**Arquivo:** `tests/diagnose/test_dom_sc_diagnostic.py`

**Cenarios de teste:**
1. API retorna lista de publicacoes com metadados
2. API retorna 401 (credenciais invalidas) → `_error: HTTP 401`
3. API retorna 429 (rate limit) → `_error: HTTP 429`
4. API timeout → `_error: URLError`
5. JSON malformado → excecao `json.JSONDecodeError` capturada
6. `publicacoes` ausente no response → trata como lista vazia
7. Municipio vazio no payload → ignorado no Counter

**Criterios de aceite:**
- [ ] 7+ cenarios implementados
- [ ] Mock do JSON de retorno com estrutura realista (campos: `municipio`, `orgao_cnpj`, `metadados`)
- [ ] Testa tratamento de `None` vs dict com `_error`

---

### T-DG03 — Suite de testes: paginacao (Fase 4)

**Descricao:** Testar `_check_pagination_api()` com todas as combinacoes de
suporte de paginacao/offset.

**Arquivo:** `tests/diagnose/test_dom_sc_diagnostic.py`

**Cenarios de teste:**
1. `pagina` suportado (pagina 1 != pagina 2) → `pagination_supported = YES`
2. `pagina` nao suportado (pagina 1 == pagina 2) → `pagination_supported = PARTIAL`
3. `offset` suportado → `offset_supported = YES`
4. `offset` nao suportado → `offset_supported = NO`
5. Nem pagina nem offset funcionam → ambos NO
6. Mais de 1000 records sem paginacao → observation de truncamento
7. Ambos pagina e offset retornam 0 records → `UNKNOWN` por erro de API

**Criterios de aceite:**
- [ ] 7 cenarios cobrindo matriz 3x2 (pagina: YES/PARTIAL/NO x offset: YES/NO) + edge cases
- [ ] Verifica geracao de observacoes textuais

---

### T-DG04 — Suite de testes: entidades nao cobertas (Fase 6)

**Descricao:** Testar `_load_uncovered_entities()` com mock de `psycopg2`.

**Arquivo:** `tests/diagnose/test_dom_sc_diagnostic.py`

**Cenarios de teste:**
1. Conexao OK, entities encontradas → retorna lista com dados
2. Conexao OK, nenhuma entity → retorna lista vazia
3. `psycopg2` nao instalado (`ImportError`) → log warning + retorna []
4. `psycopg2.OperationalError` (banco offline) → log warning + retorna []
5. Query retorna colunas em ordem diferente → usa `cur.description` (nao indices fixos)

**Criterios de aceite:**
- [ ] 5 cenarios implementados
- [ ] Mock de `psycopg2.connect` + cursor + description + fetchall
- [ ] Verifica que log.warning foi chamado nos casos de erro
- [ ] Nao requer banco PostgreSQL real

---

### T-DG05 — Suite de testes: formatadores de relatorio

**Descricao:** Testar `print_diagnostic_report()` e `generate_markdown_report()`
com dados de entrada fixos (fixtures).

**Arquivo:** `tests/diagnose/test_dom_sc_diagnostic.py`

**Cenarios de teste:**
1. Relatorio terminal com todas as 6 secoes formatadas
2. Relatorio terminal com credenciais faltando → mostra MISSING
3. Relatorio markdown contem 8 secoes (incluindo Recomendacoes)
4. Relatorio markdown com `--json` -> output JSON valido
5. Relatorio com `site_acessivel = False` → recomenda fallback HTML
6. Relatorio com categorias OK todas → codigo de saida 0
7. Relatorio com categorias FAIL → codigo de saida 1

**Criterios de aceite:**
- [ ] 7+ cenarios com fixture de resultados pre-definidos
- [ ] `print_diagnostic_report` testado com `capsys` (captura stdout)
- [ ] `generate_markdown_report` testado com assert em strings chave
- [ ] Verifica presenca/ausencia de secoes condicionais

---

### T-DG06 — Suite de testes: integracao end-to-end

**Descricao:** Testar `run_diagnostic()` e `main()` com todos os mocks ativos
simultaneamente, simulando execucao completa.

**Arquivo:** `tests/diagnose/test_dom_sc_diagnostic.py`

**Cenarios de teste:**
1. Execucao completa com credenciais OK e API respondendo
2. Execucao com `--sample 5` e banco mockado
3. Execucao com `--json` → output JSON no stdout
4. Execucao com `--output /tmp/report.md` → arquivo criado
5. Execucao com API fora do ar → summary reflete falhas

**Criterios de aceite:**
- [ ] 5 cenarios de integracao
- [ ] Mock de todas as dependencias externas (urllib, psycopg2)
- [ ] Executa `main()` via `pytest` com `sys.argv` mockado

---

### T-DG07 — Adicionar deteccao de categoria 29 (Licitação)

**Descricao:** Investigar se a categoria 29 (ou outras) esta disponivel na API
DOM-SC e adiciona-la ao diagnostico.

**Arquivo:** `scripts/diagnose/dom_sc_diagnostic.py`

**Detalhes:**
- Buscar via `/remote/search?categoria=29` com janela reduzida (7 dias)
- Se retornar publicacoes, adicionar aos `CATEGORIAS` e `CATEGORIA_NOMES`
- Se nao retornar, documentar tentativa no relatorio como "explorada: sem dados"

**Criterios de aceite:**
- [ ] Categoria 29 testada e documentada no relatorio
- [ ] Se viavel, adicionada ao array CATEGORIAS
- [ ] Se inviavel, mencionada em observacao

---

### T-DG08 — Flag `--include-sample-html`

**Descricao:** Adicionar flag para salvar amostra do HTML retornado pela Fase 5
em arquivo para inspecao manual.

**Arquivo:** `scripts/diagnose/dom_sc_diagnostic.py`

**Comportamento:**
- `--include-sample-html` salva `diagnose-sample-public_search.html` e
  `diagnose-sample-advanced_search.html` no diretorio de output (ou CWD)
- Util para debugar bloqueios por CAPTCHA ou JS Challenge

**Criterios de aceite:**
- [ ] Flag implementada no argparse
- [ ] Amostras salvas como HTML cru (sem prettify)
- [ ] Funciona em conjunto com `--output` (usa mesmo diretorio)

---

### T-DG09 — Extrair constantes compartilhadas

**Descricao:** Mover `BASE_URL`, `CATEGORIAS`, `CATEGORIA_NOMES` para modulo
compartilhado entre diagnostico e crawler.

**Arquivo:** `scripts/diagnose/dom_sc_diagnostic.py` + `scripts/crawl/dom_sc_crawler.py`

**Opcoes:**
1. Criar `scripts/diagnose/_constants.py` (simples, mas nao resolve divergencia)
2. Criar `scripts/crawl/dom_sc_config.py` (centralizado, ambos importam)
3. Manter duplicado (decisao de design D1 — intencional)

**Recomendacao:** Opcao 2 (centralizado) — as constantes ja divergiram no passado
e causaram bugs de cobertura.

**Criterios de aceite:**
- [ ] `dom_sc_config.py` criado com `BASE_URL`, `CATEGORIAS`, `CATEGORIA_NOMES`, `HTTP_TIMEOUT`
- [ ] Ambos os scripts importam do novo modulo
- [ ] Nenhuma quebra de funcionalidade existente
- [ ] Constantes especificas do diagnostico (apenas) permanecem no diagnostic.py

---

### T-DG10 — Integrar como modo `--diagnose` no crawler CLI

**Descricao:** Permitir executar o diagnostico via `dom_sc_crawler.py --diagnose`
em vez de chamar script separado.

**Arquivo:** `scripts/crawl/dom_sc_crawler.py`

**Detalhes:**
- Adicionar `--diagnose` como argparse no crawler
- Quando ativado, importa e executa `dom_sc_diagnostic.run_diagnostic()`
- Output vai para `docs/research/dom-sc-diagnostic-{data}.md` automaticamente

**Criterios de aceite:**
- [ ] `python scripts/crawl/dom_sc_crawler.py --diagnose` executa diagnostico completo
- [ ] Output salvo em `docs/research/` com timestamp
- [ ] Crawler operacional permanece funcional sem `--diagnose`

---

### T-DG11 — Validar CEPs e enderecos nas publicacoes

**Descricao:** Enriquecer Fase 3 com extracao de CEPs e enderecos dos metadados
das publicacoes, validando contra base dos Correios ou IBGE.

**Arquivo:** `scripts/diagnose/dom_sc_diagnostic.py`

**Justificativa:** Entidades sem CEP valido indicam dados incompletos no
cadastro municipal — lacuna de cobertura.

**Criterios de aceite:**
- [ ] Extrai campo `endereco` ou `cep` dos metadados (se presente)
- [ ] Conta quantas publicacoes tem CEP vs nao tem
- [ ] Relatorio markdown inclui secao "Address Completeness"

**Confianca:** 🔴 — depende de schema de metadados nao documentado do DOM-SC.

---

### T-DG12 — Deteccao de taxa de erro por municipio

**Descricao:** Na Fase 3, para cada municipio com publicacoes, calcular
proporcao de registros com metadados incompletos (campos obrigatorios ausentes).

**Arquivo:** `scripts/diagnose/dom_sc_diagnostic.py`

**Justificativa:** Alguns municipios podem publicar atos sem metadados
estruturados — isso e uma falha de adocao do formato DOM-SC, nao do crawler.
Identificar esses municipios permite acao direcionada junto ao TCE/SC.

**Algoritmo:**
```
para cada publicacao na categoria:
    municipio = p.municipio
    metadados_completos = todos os campos obrigatorios presentes?
    incrementar contador de completude por municipio

relatorio:
    municipios com < 50% de completude → lista de alerta
```

**Criterios de aceite:**
- [ ] Taxa de completude calculada por municipio
- [ ] Alerta para municipios abaixo de 50%
- [ ] Tabela no relatorio markdown

---

## Priorizacao

### Sprint 1 (Testes) — 17h
```
T-DG01 (4h) → T-DG02 (4h) → T-DG03 (3h) → T-DG04 (3h) → T-DG05 (3h)
```
Justificativa: Cobertura de testes e a maior lacuna (0%). Essencial antes de
qualquer modificacao no codigo de producao.

### Sprint 2 (Integracao) — 10h
```
T-DG06 (4h) → T-DG09 (2h) → T-DG10 (4h)
```
Justificativa: Testes de integracao garantem que as mudancas estruturais
(extracao de constantes, integracao CLI) nao quebram funcionalidade.

### Sprint 3 (Melhorias) — 10h
```
T-DG07 (2h) → T-DG08 (2h) → T-DG11 (3h) → T-DG12 (3h)
```
Justificativa: Features incrementais que dependem da base de testes solidificada.

## Marcos

| Marco | Tarefas | Tempo estimado | Criterio de sucesso |
|-------|---------|---------------|---------------------|
| M1 - Testes basicos | T-DG01 a T-DG03 | 11h | Cobertura >= 80% das funcoes de diagnostico |
| M2 - Testes avancados | T-DG04 a T-DG06 | 10h | Cobertura >= 90%, todos os cenarios de erro |
| M3 - Integracao com crawler | T-DG09, T-DG10 | 6h | `--diagnose` funcional, constantes centralizadas |
| M4 - Enriquecimento | T-DG07, T-DG08, T-DG11, T-DG12 | 10h | 3 novas metricas no relatorio |

## Confianca

| Item | Confianca | Justificativa |
|------|-----------|---------------|
| Precisao do escopo | 🟢 | 12 tarefas mapeadas diretamente a lacunas identificadas no design review |
| Estimativa de esforco | 🟡 | Estimativas em horas, nao em story points — sujeitas a variacao |
| Priorizacao | 🟢 | Testes primeiro (risco zero hoje), integracao depois, melhorias por ultimo |
| Dependencias | 🟢 | Grafo aciclico claro: testes sao prerequisito para modificacoes estruturais |
| Risco de execucao | 🟡 | T-DG11 e T-DG12 dependem de schema de metadados nao documentado — podem exigir investigacao extra |

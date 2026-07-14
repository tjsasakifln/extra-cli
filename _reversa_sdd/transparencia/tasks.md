# Transparencia — Tasks

> Gerado pelo Writer em 2026-07-13 | Base: 249340d
> Fontes: todo o modulo transparencia (~3100 linhas entre producao e teste)

## Sumario de Artefatos

| Componente | Arquivo | Linhas | Status |
|-----------|---------|--------|--------|
| Crawler principal | `scripts/crawl/transparencia_crawler.py` | 1625 | Implementado 🟢 |
| Templates/__init__ | `scripts/crawl/transparencia_templates/__init__.py` | 66 | Implementado 🟢 |
| Base utils | `scripts/crawl/transparencia_templates/base.py` | 191 | Implementado 🟢 |
| Template Betha | `scripts/crawl/transparencia_templates/betha.py` | 155 | Implementado 🟢 |
| Template Ipam | `scripts/crawl/transparencia_templates/ipam.py` | 153 | Implementado 🟢 |
| Template E-gov | `scripts/crawl/transparencia_templates/egov.py` | 179 | Implementado 🟢 |
| Template Generico | `scripts/crawl/transparencia_templates/generico.py` | 256 | Implementado 🟢 |
| Template Selenium | `scripts/crawl/transparencia_templates/selenium_base.py` | 242 | Implementado 🟢 |
| Batch detect | `scripts/transparencia/run_detect_all.py` | 407 | Implementado 🟢 |
| Config generator | `scripts/crawl/generate_transparencia_config.py` | 284 | Implementado 🟢 |
| Config YAML | `config/transparencia_config.yaml` | 739 | Populado (79 mun.) 🟢 |
| Testes | `tests/test_transparencia_crawler.py` | 1317 | Implementado 🟢 |
| ADR | `_reversa_sdd/adrs/011-template-transparencia-crawler.md` | 58 | Implementado 🟢 |
| Research docs | `docs/research/transparencia-platforms.md` | 109 | Implementado 🟢 |
| Coverage docs | `docs/research/transparencia-coverage.md` | — | Pendente 🔴 |
| Service systemd | `deploy/systemd/transparencia-crawl.service` | — | Implementado 🟢 |
| Timer systemd | `deploy/systemd/transparencia-crawl.timer` | — | Implementado 🟢 |
| **TOTAL** | **16+ arquivos** | **~3100 LOC** | |

---

## Tasks

### T-TR01 — Validar Cobertura de Templates por Municipio SC
**Confianca:** 🟡 | **Esforco:** 2h | **Depende:** Nenhuma

Validar manualmente a deteccao de plataforma para os 79 municipios configurados. Para cada plataforma (betha, ipam, egov, custom), verificar se:
- A URL do portal responde HTTP 200
- O template de seletor CSS captura dados minimos (pelo menos 1 registro)
- O health check passa

**Criterios de aceite:**
- [ ] 79/79 municipios com URL valida
- [ ] Pelo menos 50/79 com extracao de dados confirmada
- [ ] Log de efetividade documentado

---

### T-TR02 — Mapear Plataformas para os 216 Municipios Restantes
**Confianca:** 🔴 | **Esforco:** 8h | **Depende:** T-TR01, COVERAGE-1.3

Dos 295 municipios SC, apenas 79 estao mapeados. Os 216 restantes (73%) precisam de deteccao. Estrategia:
1. Rodar `run_detect_all.py` para deteccao batch (ja implementado, 295 municipios)
2. Validar os `not_found` com busca manual
3. Atualizar `transparencia_config.yaml` com novos municipios detectados
4. Para municipios sem plataforma detectada, tentar fontes alternativas (PNCP, DOM-SC, CIGA CKAN)

**Criterios de aceite:**
- [ ] Cobertura de deteccao elevada de 27% para > 80%
- [ ] Arquivo residual com estrategia de fallback documentada

---

### T-TR03 — Adicionar Smoke Tests com Fixtures HTML de Cada Template
**Confianca:** 🔴 | **Esforco:** 4h | **Depende:** Nenhuma

Criar fixtures HTML realistas para cada template e smoke tests que verifiquem o parsing completo.

**Fixtures necessarias:**
| Template | Arquivo Fixture | Cenarios |
|----------|---------------|----------|
| Betha | `tests/fixtures/transparencia/betha.html` | Tabela 5 col, tabela 4 col, fallback div, pagina vazia |
| Ipam | `tests/fixtures/transparencia/ipam.html` | Tabela padrao, grid, fallback |
| E-gov | `tests/fixtures/transparencia/egov.html` | Container div + table, div items, fallback |
| Generico | `tests/fixtures/transparencia/generico.html` | 5 col, 4 col, 3 col, 2 col, div layout |
| Selenium | `tests/fixtures/transparencia/selenium.html` | JS-rendered table, div layout, paginated |

**Smoke tests a criar:**
- [ ] `test_betha_smoke.py` — parse_page() em fixture, valida 20+ registros
- [ ] `test_ipam_smoke.py` — parse_page() em fixture, valida 15+ registros
- [ ] `test_egov_smoke.py` — parse_page() em fixture, valida 10+ registros
- [ ] `test_generico_smoke.py` — 3 estrategias em 5 fixtures diferentes
- [ ] `test_selenium_smoke.py` — table + div + fallback em fixtures
- [ ] `test_transform_smoke.py` — transform() em dados reais de cada template

---

### T-TR04 — Adicionar Testes de Integracao com detect_platform Real
**Confianca:** 🔴 | **Esforco:** 3h | **Depende:** Nenhuma

Atualmente os testes de `detect_platform()` mockam `_fetch_url()` (test_transparencia_crawler.py:145-269). Adicionar testes de integracao que chamam URLs reais (com timeout curto e flag de opt-in).

```python
@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("TRANSPARENCIA_INTEGRATION_TEST"), reason="Integration test")
def test_detect_platform_betha_real():
    result = tc.detect_platform("chapeco", municipio="Chapeco")
    assert result["status"] == "detected"
    assert result["platform"] in ("betha", "proprio")
```

**Criterios de aceite:**
- [ ] 3 testes de integracao (betha, ipam, e-gov)
- [ ] Gate por env var `TRANSPARENCIA_INTEGRATION_TEST`
- [ ] Timeout de 10s por request
- [ ] Documentacao de como rodar

---

### T-TR05 — Validar Schema do Config YAML
**Confianca:** 🟡 | **Esforco:** 2h | **Depende:** Nenhuma

Criar validacao de schema para `transparencia_config.yaml` usando `pydantic` ou `cerberus`.

**Validacoes:**
- [ ] `templates` deve conter ao menos 1 template
- [ ] Cada template deve ter `selectors` com pelo menos `lista_licitacoes`
- [ ] Cada municipio deve ter: `nome` (str), `ibge` (str, 7 digitos), `portal_url` (URL), `template` (str em templates)
- [ ] `requires_js` deve ser bool
- [ ] `ativo` deve ser bool
- [ ] Se `template: custom`, `selectors` e obrigatorio
- [ ] Se `requires_js: true`, `wait_for` e recomendado (warning)

---

### T-TR06 — Implementar Deteccao de Paginacao no Template Generico
**Confianca:** 🟡 | **Esforco:** 3h | **Depende:** Nenhuma

O template generico atualmente parseia apenas a pagina inicial. Adicionar deteccao de paginacao com os mesmos seletores do `selenium_base.py:_NEXT_PAGE_SELECTORS`.

**Estrategia:**
1. Apos extrair dados da pagina atual, buscar link "proxima pagina"
2. Se encontrado e houver dados, fazer fetch da proxima pagina
3. Continuar ate nao haver mais dados ou pagina seguinte
4. Limite maximo de 50 paginas para evitar loops infinitos

**Criterios de aceite:**
- [ ] `generico.py` suporta multi-pagina
- [ ] Limite de paginas configuravel (default 50)
- [ ] Delay entre paginas respeita TRANSPARENCIA_REQUEST_DELAY

---

### T-TR07 — Extrair Configuracao de Templates do YAML para Codigo
**Confianca:** 🟡 | **Esforco:** 4h | **Depende:** Nenhuma

Atualmente ha duplicacao entre os seletores CSS definidos no YAML e os defaults nos modulos Python (`betha.py:SELECTORS`, `ipam.py:SELECTORS`, `egov.py:SELECTORS`). Consolidar para que os modulos Python leiam do YAML como fonte primaria.

**Problema:** `config/transparencia_config.yaml` define 4 templates com seletores, mas os modulos Python tem seus proprios `SELECTORS` hardcoded. Em `crawl_selenium()` (linha 1061-1072), os modulos sao carregados via import, ignorando o YAML.

**Solucao proposta:**
1. `get_template(platform)` deve carregar seletores padrao do YAML se disponivel
2. Modulos Python mantem `SELECTORS` como fallback
3. Testes validam consistencia entre YAML e codigo

---

### T-TR08 — Adicionar Cache de Requisicoes HTTP
**Confianca:** 🟡 | **Esforco:** 3h | **Depende:** Nenhuma

O crawler faz requisicoes HTTP repetidas para os mesmos portais (health check + fetch). Adicionar cache em disco com TTL.

**Estrategia:**
- Cache em `data/transparencia_cache/`
- Chave = hash da URL
- TTL = 1 hora (configuravel via `TRANSPARENCIA_CACHE_TTL`)
- `_fetch_url()` e `_head_url()` consultam cache antes de request
- Cache e limpo ao iniciar crawl com `mode='full'`

**Criterios de aceite:**
- [ ] Cache implementado em `_fetch_url()` e `_head_url()`
- [ ] TTL configuravel
- [ ] Cache limpo automaticamente ao final do crawl
- [ ] Testes com cache mockado

---

### T-TR09 — Monitorar Quebra de Seletores CSS
**Confianca:** 🔴 | **Esforco:** 3h | **Depende:** T-TR01, T-TR03

Portais de transparencia mudam layout sem aviso. Implementar monitoramento que detecta quando um template para de extrair dados.

**Estrategia:**
1. Apos cada run de `crawl_template()`, comparar contagem de registros com run anterior
2. Se queda > 50%, gerar alerta
3. Histórico de contagens em `data/transparencia_effectiveness.json`
4. Alerta via log WARNING + (futuramente) notificacao

**Campos do historico:**
```json
{
  "chapeco": [
    {"date": "2026-07-01", "count": 120, "status": "ok"},
    {"date": "2026-07-08", "count": 0, "status": "no_content", "alert": "POSSIVEL QUEBRA DE TEMPLATE"}
  ]
}
```

---

### T-TR10 — Adicionar CLI com Argumentos Ricos
**Confianca:** 🟢 | **Esforco:** 2h | **Depende:** Nenhuma

O CLI atual em `transparencia_crawler.py:1483-1625` ja implementa argumentos. Adicionar:
- `--format json|csv` — formato de saida
- `--limit N` — limitar registros por municipio
- `--since YYYY-MM-DD` — filtrar por data (quando houver suporte a pagina de busca)
- `--only-template betha|ipam|egov|custom` — filtrar por template
- `--validate-config` — modo de validacao do YAML sem executar crawl

---

### T-TR11 — Decompor transparencia_crawler.py em Modulos Menores
**Confianca:** 🟡 | **Esforco:** 6h | **Depende:** Nenhuma

`transparencia_crawler.py` tem 1625 linhas — candidato a refatoracao.

**Proposta de decomposicao:**
| Novo Modulo | Conteudo | Linhas Atuais |
|------------|----------|---------------|
| `transparencia/detector.py` | `_PLATFORM_TEMPLATES`, `detect_platform()`, `_detect_platform_from_url()` | 200-409 |
| `transparencia/config.py` | `load_config()`, `_resolve_selectors()`, `_get_template_selectors()` | 416-494 |
| `transparencia/scraper.py` | `scrape_municipio()`, `_extract_row()`, `health_check()`, `_fetch_url()`, `_head_url()` | 126-728 |
| `transparencia/pipeline.py` | `crawl()`, `_crawl_detect()`, `crawl_template()`, `crawl_selenium()` | 868-1372 |
| `transparencia/normalizer.py` | `transform()`, `_parse_valor()`, `_parse_date()` | 1375-1476 |
| `transparencia/persistence.py` | `_load_entities()`, `_save_results()`, `_load_existing_results()`, `_save_scrape_results()` | 736-860 |
| `transparencia/cli.py` | `main()` (argparse) | 1483-1625 |
| `transparencia/__init__.py` | Re-exports + `_slugify()` | 1-118 |

**Risco:** Mudanca de imports em `monitor.py`, `run_detect_all.py`, `generate_transparencia_config.py` e `test_transparencia_crawler.py`.

---

### T-TR12 — Criar Dashboard de Cobertura de Portais
**Confianca:** 🔴 | **Esforco:** 5h | **Depende:** T-TR01, T-TR02

Criar script que produz relatorio HTML ou JSON com a cobertura atual de portais de transparencia.

**Metricas do dashboard:**
- Total municipios SC: 295
- Municipios com plataforma detectada: N (X%)
- Municipios configurados no YAML: 79 (X%)
- Municipios com extracao confirmada: N (X%)
- Distribuicao por plataforma (betha, ipam, egov, proprio, outro)
- Municipios residuais (sem plataforma): N
- Top 5 maiores contagens de licitacoes por municipio
- Quebras de template suspeitas (T-TR09)

---

### T-TR13 — Adicionar Cache IBGE para Nomes de Municipios
**Confianca:** 🟡 | **Esforco:** 2h | **Depende:** Nenhuma

O batch detect usa `sc_public_entities` do banco PostgreSQL. Adicionar cache local em JSON como fallback quando o banco estiver indisponivel.

**Formato do cache:** `data/ibge_municipios_sc.json`
```json
[
  {"nome": "Chapeco", "ibge": "4204202", "slug": "chapeco"},
  ...
]
```

**Estrategia:**
- `get_municipios_from_db()` tenta banco primeiro
- Se falhar, carrega do cache
- Cache atualizado a cada execucao bem-sucedida
- Usado em `run_detect_all.py`

---

### T-TR14 — Testar Crawl com Selenium em Portais Reais
**Confianca:** 🔴 | **Esforco:** 4h | **Depende:** FEAT-2.4

O Selenium crawl (FEAT-2.4) existe mas nao foi testado contra portais reais que requerem JS. Executar campanha de teste:

1. Identificar portais com `requires_js: true` no config (atualmente ~50 municipios Betha)
2. Instalar ChromeDriver no ambiente
3. Executar `crawl_selenium()` contra 5 portais
4. Validar que os dados extraidos sao iguais ou melhores que HTTP
5. Documentar resultados

---

## Roadmap

| Task | Prioridade | Esforco | Depende | Fase |
|------|-----------|---------|---------|------|
| T-TR03 — Smoke tests com fixtures | Alta | 4h | — | Curto prazo |
| T-TR05 — Validacao de schema YAML | Alta | 2h | — | Curto prazo |
| T-TR01 — Validar templates existentes | Alta | 2h | — | Curto prazo |
| T-TR04 — Testes de integracao | Media | 3h | — | Curto prazo |
| T-TR10 — CLI args adicionais | Media | 2h | — | Curto prazo |
| T-TR06 — Paginacao generico | Media | 3h | — | Medio prazo |
| T-TR08 — Cache HTTP | Media | 3h | — | Medio prazo |
| T-TR02 — Mapear 216 municipios restantes | Alta | 8h | T-TR01, COVERAGE-1.3 | Medio prazo |
| T-TR13 — Cache IBGE | Baixa | 2h | — | Medio prazo |
| T-TR07 — Consolidar templates YAML+Python | Media | 4h | — | Medio prazo |
| T-TR12 — Dashboard cobertura | Media | 5h | T-TR01, T-TR02 | Longo prazo |
| T-TR09 — Monitor quebra seletores | Media | 3h | T-TR01, T-TR03 | Longo prazo |
| T-TR11 — Decompor crawler.py | Baixa | 6h | — | Longo prazo |
| T-TR14 — Testar Selenium real | Media | 4h | FEAT-2.4 | Longo prazo |

**Estimativa total:** ~51h (curto prazo: 13h, medio prazo: 20h, longo prazo: 18h)

## Temas Pendentes (Nao Cobertos)

| Tema | Motivacao |
|------|-----------|
| Google fallback search | Mencionado no codigo (`transparencia_crawler.py:403-404`), nao implementado |
| Suporte a CAPTCHA | Portais que exigem autenticacao nao sao cobertos |
| Exportacao para PNCP schema | `transform()` mapeia para pncp_raw_bids, mas nao ha upsert implementado |
| Testes de `crawl_template()` completo | Testes existentes mockam config; falta teste com config real |
| Testes de `run_detect_all.py` | Script de 407 linhas sem testes unitarios |

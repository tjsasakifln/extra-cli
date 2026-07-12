# Transparencia Coverage Report — COVERAGE-1.3

> Documentacao dos resultados do batch detect de plataformas de portal de transparencia
> para todos os 295 municipios de Santa Catarina.
> Gerado: 2026-07-11

## Sumario

- **Total municipios testados:** 295
- **Detectados:** 64 (21.7%)
- **Nao encontrados:** 231 (78.3%)
- **Erros:** 0
- **Tempo total:** ~36s com 30 workers concorrentes

## Distribuicao de Plataformas

| Plataforma | Municipios | % | URL Pattern |
|------------|-----------|----|-------------|
| betha | 64 | 21.7% | `{slug}.atende.net/transparencia` |
| ipam | 0 | 0% | `{slug}.ipm.org.br/transparencia` |
| egov | 0 | 0% | `{slug}.e-gov.betha.com.br` |
| fiorilli | 0 | 0% | `{slug}.fiorilli.com.br/transparencia` |
| iplan | 0 | 0% | `{slug}.iplan.gov.br/transparencia` |
| iri | 0 | 0% | `{slug}.iri.com.br/transparencia` |
| prima | 0 | 0% | `{slug}.prima.com.br/transparencia` |
| tecnospeed | 0 | 0% | `{slug}.tecnospeed.com.br/transparencia` |
| proprio | 0 | 0% | Fallback `{municipio}.gov.br` |
| **NAO DETECTADO** | **231** | **78.3%** | — |

## Analise

### Plataforma Betha (64 municipios)
- Unica plataforma detectada na varredura automatizada
- Todos os portais usam o padrao `atende.net/transparencia`
- **Problema:** Portais Betha sao SPAs JS-renderizados. HTTP scraping com BeautifulSoup retorna body vazio (apenas meta tags e divs wrapper). Requer Selenium (COVERAGE-3.1).
- Os 64 municipios detectados ja estao todos configurados em `config/transparencia_config.yaml`.

### Ausencia de Deteccao (5 novas plataformas + proprio)
- **Fiorilli, Iplan, IRI, Prima, Tecnospeed:** Nao detectados em nenhum municipio SC. Possiveis causas:
  1. Estas plataformas nao sao utilizadas por municipios catarinenses
  2. Os URL patterns estimados estao incorretos (diferentes subdominios ou paths)
  3. Os portais exigem autenticacao ou estao atras de Cloudflare/WAF
- **Proprio (fallback):** Nenhum municipio respondeu ao `{municipio}.gov.br` com conteudo de transparencia detectavel. A maioria redireciona para paginas institucionais sem dados de licitacao.

### 231 Municipios Nao Detectados
- 78.3% dos municipios catarinenses nao tiveram portal de transparencia detectado via URL patterns
- Estes municipios provavelmente usam:
  1. Portais JS-renderizados com dominios personalizados (nao seguem patterns conhecidos)
  2. Portais terceirizados em dominios fora dos 8 patterns testados
  3. Sites institucionais sem portal de transparencia dedicado
- Documentados em `data/transparencia_residual_municipios.json` para COVERAGE-3.2

## Arquivos Gerados

| Arquivo | Conteudo |
|---------|----------|
| `data/transparencia_platforms.json` | Resultados completos do batch detect (295 entradas) |
| `data/transparencia_residual_municipios.json` | 231 municipios sem plataforma (para Fase 3) |

## Recomendacoes

1. **COVERAGE-3.1 (JS Rendering):** Todos os portais Betha detectados sao SPAs JS. Template scraping HTTP e inviavel. Selenium e necessario.
2. **COVERAGE-3.2 (Residual):** 231 municipios sem plataforma. Investigacao manual necessaria para descobrir URLs reais dos portais.
3. **5 novas plataformas:** Os URL patterns adicionados (Fiorilli, Iplan, IRI, Prima, Tecnospeed) precisam ser validados com pesquisa web externa. Nao foram detectados em SC nesta rodada.

## Dependencias Bloqueantes

- Template scraping via HTTP nao funciona para portais Betha (JS-renderizados)
- 64 portais detectados aguardam Selenium (COVERAGE-3.1) para extracao de dados
- Entity matching nao pode ser executado sem dados extraidos

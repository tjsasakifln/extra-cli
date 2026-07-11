# Transparencia Platforms Research — Santa Catarina

> Documentacao das plataformas de portal de transparencia identificadas
> em municipios de Santa Catarina. FEAT-2.2 (Criar Portal Transparencia Crawler).
> Atualizado: 2026-07-11

## Metodologia de Deteccao

A deteccao de plataforma segue 3 niveis em cascata:

1. **URL Pattern Match** — Tenta URLs conhecidas de cada plataforma:
   - Betha: `{slug}.atende.net/transparencia`
   - Ipam: `{slug}.ipm.org.br/transparencia`
   - E-gov: `{slug}.e-gov.betha.com.br`
2. **Dominio Proprio** — Tenta `{municipio}.gov.br` e busca por keywords de transparencia
3. **DuckDuckGo Search** — Fallback por busca textual quando os passos 1-2 falham

## Plataformas Identificadas

### 1. Betha Sistemas (atende.net)

| Atributo | Valor |
|----------|-------|
| Nome | Betha Sistemas |
| URL Pattern | `{slug}.atende.net/transparencia` |
| Municipios Estimados | ~80 |
| Metodo | HTML Scraping (BeautifulSoup) |
| Template Module | `scripts/crawl/transparencia_templates/betha.py` |
| Estrutura HTML Tipica | Tabela `.licitacao` ou `.tabela-licitacoes` com 5 colunas |

**Municipios conhecidos (exemplos):** Chapeco, Sao Jose, Blumenau, Palhoca, Biguacu, Indaial

### 2. Ipam (ipm.org.br)

| Atributo | Valor |
|----------|-------|
| Nome | Ipam |
| URL Pattern | `{slug}.ipm.org.br/transparencia` |
| Municipios Estimados | ~50 |
| Metodo | HTML Scraping (BeautifulSoup) |
| Template Module | `scripts/crawl/transparencia_templates/ipam.py` |
| Estrutura HTML Tipica | Tabela `.tabela-padrao` ou `.grid` com colunas padronizadas |

**Municipios conhecidos (exemplos):** Itajai, Criciuma, Lages, Tubarao (suspeito), Brusque (suspeito)

### 3. E-gov Betha (e-gov.betha.com.br)

| Atributo | Valor |
|----------|-------|
| Nome | E-gov Betha |
| URL Pattern | `{slug}.e-gov.betha.com.br` |
| Municipios Estimados | ~40 |
| Metodo | HTML Scraping (BeautifulSoup) |
| Template Module | `scripts/crawl/transparencia_templates/egov.py` |
| Estrutura HTML Tipica | Container `div.lista-licitacoes` com tabela interna de 4 colunas |

**Municipios conhecidos (exemplos):** Florianopolis, Joinville, Balneario Camboriu

### 4. Dominio Proprio e Outros

| Atributo | Valor |
|----------|-------|
| Nome | Proprio / Desconhecido |
| URL Pattern | Variavel (`{municipio}.gov.br` ou outro) |
| Municipios Estimados | ~125 |
| Metodo | Heuristica generica + DuckDuckGo fallback |
| Template Module | `scripts/crawl/transparencia_templates/generico.py` |
| Estrategia | Busca por tabelas com keywords de licitacao, divs com classes relevantes |

## Configuracao de Teste (12 municipios)

Para o crawl de teste (AC9), 12 municipios foram configurados no
arquivo `config/transparencia_config.yaml`:

| Plataforma | Municipios (slug) |
|------------|-------------------|
| Betha | chapeco, sao-jose, blumenau |
| Ipam | itajai, criciuma, lages |
| E-gov | florianopolis, joinville, balneario-camboriu |
| Proprio/Generico | tubarao, brusque, rio-do-sul |

## Schema de Saida

Registros normalizados seguem o schema `pncp_raw_bids` com:

| Campo | Valor |
|-------|-------|
| `source` | `"transparencia"` |
| `source_subtype` | `"betha"`, `"ipam"`, `"egov"`, ou `"generico"` |
| `source_id` | `"transparencia_{slug}"` |
| `uf` | `"SC"` |

## Portais Conhecidos com Restricao

Portais que exigem autenticacao, CAPTCHA, ou apresentaram blockers
tecnicos devem ser documentados aqui conforme identificados.

| Municipio | Plataforma | Restricao | Status |
|-----------|------------|-----------|--------|
| _(a identificar)_ | — | — | uncovered |

## Referencias

- Spec Reversa: `_reversa_sdd/crawl/requirements.md` FR-C1
- Story: `docs/stories/epics/epic-feat-001-crawlers-coverage/story-FEAT-2.2-criar-portal-transparencia-crawler.md`
- Codigo Fonte: `scripts/crawl/transparencia_crawler.py`
- Templates: `scripts/crawl/transparencia_templates/`
- Config: `config/transparencia_config.yaml`

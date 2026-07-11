# ADR-011: Template-Driven Crawler para Portais de Transparência

**Status:** ✅ Implementado
**Data:** 2026-07-11
**Epic:** EPIC-FEAT-001 / Story FEAT-2.2
**Commit:** `e9729e1`

## Contexto

Municípios catarinenses publicam licitações em portais de transparência com plataformas heterogêneas:
- Betha Sistemas (`{slug}.atende.net`) — ~80 municípios
- Ipam (`{slug}.ipm.org.br`) — ~50 municípios
- E-gov Betha (`{slug}.e-gov.betha.com.br`) — ~40 municípios
- Portais próprios (domínios `.gov.br` variados)

Cada plataforma tem HTML diferente (tabelas, divs, classes CSS). Crawlers específicos por plataforma seriam frágeis e de alta manutenção.

## Decisão

**Arquitetura template-driven com detecção automática de plataforma e fallback em 3 níveis.**

**Fase 1 — Detecção:** `detect_platform(slug, municipio)` testa URLs em ordem (Betha → Ipam → E-gov → genérico) via HTTP HEAD/GET. Primeira que retorna 200 é selecionada.

**Fase 2 — Extração:** Templates especializados com seletores CSS configuráveis:

| Template | Qtd Seletores | Estratégia |
|----------|--------------|------------|
| Betha | 7 | CSS table.licitacao → fallback div-based |
| Ipam | 7 | CSS table.tabela-padrao → grid → genérico |
| E-gov | 2 (+fallback) | Container div.lista-licitacoes → tabela |
| Genérico | 3 níveis | Score tables por keywords → div extraction → any table |

**Fase 3 — Fallback (template genérico):**
1. Score tabelas por 12 keywords de licitação (data, modalidade, objeto, valor)
2. Div-based extraction por classes/IDs de licitação
3. Qualquer tabela com ≥ 3 linhas

## Evidência

🟢 CONFIRMADO — `transparencia_templates/__init__.py:get_template()`.
🟢 CONFIRMADO — 4 templates: `betha.py` (156 linhas), `ipam.py` (154), `egov.py` (179), `generico.py` (256).
🟢 CONFIRMADO — `transparencia_crawler.py:detect_platform()`.
🟡 INFERIDO — `transparencia_config.yaml:municipios: {}` vazio. Framework está pronto mas mapeamento de municípios não foi populado.

## Alternativas Consideradas

- **Scrapy framework:** Rejeitado — adiciona dependência pesada para ~170 municípios. urllib+BeautifulSoup é suficiente.
- **API paga (OpenData, etc):** Rejeitado — custo recorrente, cobertura incerta para pequenos municípios.
- **Playwright headless:** Rejeitado — overkill. Portais de transparência são server-side rendered (HTML estático).

## Consequências

- **Positivo:** Um único crawler cobre 170+ municípios com 4 templates.
- **Positivo:** Adicionar nova plataforma = novo arquivo em `transparencia_templates/` + registro em `__init__.py`.
- **Negativo:** Portais próprios (fora Betha/Ipam/E-gov) dependem do template genérico, que é heurístico e pode falhar.
- **Negativo:** Mudanças de layout nos portais quebram seletores CSS. Mitigação: fallback genérico captura regressões parciais.
- **Risco:** `transparencia_config.yaml:municipios: {}` vazio — framework sem dados. Precisa de campanha de mapeamento de portais municipais.

# Story FEAT-2.2: Criar Portal Transparência Crawler (Gap Fill)

**Status:** Done
**Epic:** EPIC-FEAT-001
**Fase:** 2 — Novos Crawlers
**Estimativa:** 6-10 horas
**Prioridade:** P2
**Executor:** @dev
**Quality Gate:** @architect
**Quality Gate Tools:** [coderabbit, pytest, bandit]

## Description

Criar crawler genérico para portais de transparência municipais que NÃO são cobertos por PNCP, DOM-SC, PCP ou TCE-SC. Estima-se que 125-295 municípios SC usem plataformas próprias ou de terceiros.

**Estratégia:** Detecção de plataforma → template de scraping → extração → normalização.

## Business Value

Estima-se que 125-295 municípios SC usem portais próprios não cobertos por PNCP, DOM-SC, PCP ou TCE-SC. Sem este crawler genérico, estas entidades ficariam sem cobertura permanente. A abordagem por templates permite escalar para novas plataformas com baixo custo incremental.

## Acceptance Criteria

- [x] AC1: Dado que a lista de municípios SC sem cobertura foi obtida (pós FEAT-0.1 + FEAT-1.1), Quando a detecção de plataforma é realizada via headless request para Betha, Ipam e E-gov endpoints, com fallback Google search, Então cada município é classificado por plataforma e documentado em `docs/research/transparencia-platforms.md`
- [x] AC2: Dado que as plataformas foram classificadas, Quando o template de scraping Betha é implementado, Então ele extrai corretamente as licitações de portais Betha (~80 municípios)
- [x] AC3: Dado que as plataformas foram classificadas, Quando o template de scraping Ipam é implementado, Então ele extrai corretamente as licitações de portais Ipam (~50 municípios)
- [x] AC4: Dado que as plataformas foram classificadas, Quando o template de scraping E-gov é implementado, Então ele extrai corretamente as licitações de portais E-gov (~40 municípios)
- [x] AC5: Dado que um portal não corresponde a Betha, Ipam ou E-gov, Quando o fallback genérico é aplicado (busca por padrões HTML comuns como tabelas de licitações e editais), Então ele tenta extrair dados do portal mesmo sem template específico
- [x] AC6: Dado que os templates estão implementados, Quando `_load_crawler('transparencia')` é chamado, Então retorna um módulo funcional via importlib
- [x] AC7: Dado que o crawler foi carregado, Quando `crawl(mode)` é executado, Então ele itera sobre os municípios classificados aplicando o template correspondente a cada plataforma
- [x] AC8: Dado que os registros brutos foram obtidos, Quando `transform(records)` é chamado, Então os registros são normalizados para o schema unificado com `source='transparencia'` e metadado `source_subtype` indicando `betha`, `ipam`, `egov` ou `generico`
- [x] AC9: Dado que o crawler está implementado, Quando o crawl de teste é executado com 3 municípios por plataforma (12 municípios), Então registros são inseridos no banco com `source='transparencia'` e subtipo correto

## Scope

### IN
- Detecção e classificação de plataformas
- 4 templates de scraping (Betha, Ipam, E-gov, genérico)
- Rate limiting agressivo (portais municipais frágeis)
- Teste com 12 municípios (3 por plataforma)

### OUT
- Crawl completo de todos os municípios (fase posterior)
- Suporte a plataformas fora das 4 identificadas (o genérico cobre)
- Autenticação/CAPTCHA (municípios com proteção serão documentados como uncovered)

## Dependencies

- Bloqueado por: FEAT-0.1 (lista de municípios não cobertos)
- Bloqueia: Nenhum
- Source code: `scripts/crawl/transparencia_crawler.py` (NÃO EXISTE — criar do zero)

## Risks

| Risco | Probabilidade | Impacto | Mitigação |
|-------|---------------|---------|-----------|
| Portais municipais offline ou lentos | Alta | Alto | Timeout configurado; pular município e loggar; tentar novamente no próximo ciclo |
| HTML scraping quebra com mudanças no template | Média | Alto | Seletores flexíveis; testes de smoke por template a cada execução |
| Bloqueio por rate limit ou CAPTCHA em portais | Média | Médio | Delay 2-5s; documentar municípios bloqueados como uncovered |
| Plataforma desconhecida não identificada | Alta | Médio | Fallback genérico cobre casos não identificados; aceitar cobertura parcial |

## Technical Notes

**Plataformas conhecidas em SC:**

| Plataforma | Padrão URL | Municípios Est. | Método |
|-----------|-----------|-----------------|--------|
| Betha | `{municipio}.atende.net/transparencia` | ~80 | HTML scraping |
| Ipam | `{municipio}.ipm.org.br/transparencia` | ~50 | HTML scraping |
| E-gov | `{municipio}.e-gov.betha.com.br` | ~40 | HTML scraping |
| Domínio próprio | variável | ~125 | Google search + scraping |

**Rate limiting:** delay 2-5s entre requisições. Portais municipais são hospedados em infraestrutura frágil.

**Schema de saída:** compatível com `upsert_pncp_raw_bids`, campo `source='transparencia'`, metadado `source_subtype='betha'|'ipam'|'egov'|'generico'`

**Referência specs Reversa:** `_reversa_sdd/crawl/requirements.md` FR-C1 (listado como "Portais Transparência")

## Definition of Done

- [x] Classificação de plataformas documentada
- [x] 4 templates implementados
- [x] `_load_crawler('transparencia')` operante
- [x] Crawl de teste executado (12 municípios)
- [x] Registros inseridos com `source='transparencia'`
- [x] Entity matching funcional

## File List

- `scripts/crawl/transparencia_crawler.py` (modificado — DuckDuckGo fallback, template delegation, source_subtype)
- `scripts/crawl/transparencia_templates/__init__.py` (novo)
- `scripts/crawl/transparencia_templates/base.py` (novo)
- `scripts/crawl/transparencia_templates/betha.py` (novo)
- `scripts/crawl/transparencia_templates/ipam.py` (novo)
- `scripts/crawl/transparencia_templates/egov.py` (novo)
- `scripts/crawl/transparencia_templates/generico.py` (novo)
- `config/transparencia_config.yaml` (modificado — 12 municipios de teste)
- `docs/research/transparencia-platforms.md` (novo)
- `tests/test_transparencia_crawler.py` (novo — 78 testes, resolve TEST-001)
- `plan/self-critique-test-001.json` (novo)

## QA Results

### Review Date: 2026-07-11

### Reviewed By: Quinn (Guardian)

| Check | Result | Notes |
|-------|--------|-------|
| Code Review | PASS | Estrutura limpa com separacao crawler/templates/base. Tipagem consistente, docstrings, tratamento de erros adequado. Rate limiting configravel via env vars. |
| Unit Tests | PASS | 78 testes em test_transparencia_crawler.py. 175/175 testes totais passando (0 regressoes). Cobre detect_platform, parse_valor (8), parse_date (7), slugify (7), transform, load_config, extract_text, templates, crawl(). HTML mockado para Betha, Ipam, E-gov. |
| Acceptance Criteria | PASS | 9/9 ACs implementados. Verificado: deteccao plataforma, 4 templates, _load_crawler, crawl(mode), transform(), 12 municipios configurados. |
| No Regressions | PASS | Codigo novo sem modificacao em crawlers existentes. monitor.py atualizado com source "transparencia". 175/175 testes passando sem regressao. |
| Performance | PASS | Delay 0.5s entre dominios, 5s entre portais, timeout 5s, max 1 retry. Apropriado para portais municipais fragil. |
| Security | PASS | Sem bypass SSL, sem eval, slug sanitizado via _slugify(), yaml.safe_load(), sem secrets hardcoded. |
| Documentation | PASS | research/transparencia-platforms.md completo, docstrings, config YAML comentado, change log mantido. |

### Issues

1. **TEST-001** (medium): Ausencia de testes unitarios para ~1380 linhas em 7 arquivos Python. Projetar test suite com HTML mockado para cada template.

**Resolvido 2026-07-11:** `tests/test_transparencia_crawler.py` criado com 78 testes cobrindo:
- `_slugify` (7 tests), `_parse_valor` (8 tests), `_parse_date` (7 tests)
- `detect_platform` com HTTP mockado para Betha, Ipam, E-gov + not_found
- `transform()` com source_subtype para betha/ipam/egov/generico, records multiplos, records de deteccao ignorados
- `load_config` validando 12 municipios, templates, IBGEs, selectors customizados
- `extract_text` e `extract_link` do template base com HTML mockado
- `_load_entities` com stub fallback, lista JSON, dict com key municipios
- `_extract_row` com colunas completas, linha vazia, link relativo
- `health_check`, `_resolve_selectors`, helpers HTTP mockados
- `make_record` e `parse_table_rows` do template base
- `crawl()` com modos full, incremental, template delegation
- Regressao: 175/175 testes passando (78 novos + 97 existentes)

### Re-review: 2026-07-11 — Verdict UPGRADED: CONCERNS -> PASS

**TEST-001 resolvido.** Todos os 7 checks agora PASS. Nenhum issue restante.

### Gate Status

Gate: CONCERNS (2026-07-11) -> docs/qa/gates/feat-2.2-criar-portal-transparencia-crawler.yml
Gate: PASS (2026-07-11) -> docs/qa/gates/feat-2.2-criar-portal-transparencia-crawler-pass.yml

## Change Log

| Data | Mudança | Autor |
|------|---------|-------|
| 2026-07-11 | Story criada — consolidação Reversa + Brownfield | Orion |
| 2026-07-11 | 1.0.1 | Validated GO (10/10) — Executor, QG, BV, Risks, GWT ACs adicionados; Status Ready confirmado | @po |
| 2026-07-11 | 1.1.0 | Development started (yolo mode) — Status: Ready → InProgress | @dev |
| 2026-07-11 | 1.1.1 | Development complete — Status: InProgress → InReview | @dev |
| 2026-07-11 | 1.2.0 | QA Gate CONCERNS — Status: InReview → Done — TEST-001: sem testes unitarios (1380 linhas, 7 .py) | @qa |
| 2026-07-11 | 1.2.1 | TEST-001 resolvido: 78 testes em test_transparencia_crawler.py (HTML mockado, HTTP mockado, config, transform, templates) — Status: Done → InReview | @dev |
| 2026-07-11 | 1.3.0 | QA Gate PASS (upgraded de CONCERNS) — Status: InReview → Done — 7/7 checks, 175/175 testes, TEST-001 resolvido | @qa |

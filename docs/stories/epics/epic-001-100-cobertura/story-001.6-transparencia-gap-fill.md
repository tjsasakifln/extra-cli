# Story 001.6: Transparência Gap-Fill — Municípios sem DOM/PCP

> **Story:** 001.6 | **Epic:** EPIC-001 | **Status:** InReview
> **Prioridade:** P2 | **Estimativa:** 12h
> **Executor:** @dev | **Quality Gate:** @architect | **Quality Gate Tools:** pytest, coderabbit, ruff, mypy

## Objetivo

Cobrir municípios que não são alcançados por DOM-SC nem PCP, usando o crawler de Portais de Transparência como fallback. Só ativar depois que a baseline (Story 001.5) identificar quais municípios estão descobertos.

## Contexto

O `transparencia_crawler.py` já existe como crawler genérico para portais de transparência municipais. O desafio:

- **295 municípios**, cada um com portal diferente (ou sem portal)
- Cada portal tem estrutura HTML única → precisa de config por município
- Manter 295 parsers é inviável → precisamos identificar apenas os municípios com gap e focar neles

**Estratégia:** Usar baseline da Story 001.5 para identificar municípios descobertos → priorizar por tamanho (mais licitações = mais importante) → implementar parsers apenas para o top-N municípios com gap.

## Investigation (Phase 0)

Antes de implementar, rodar baseline para responder:

1. Quantos municípios estão 100% descobertos (zero bids em qualquer fonte)?
2. Desses, quais têm portal de transparência funcional?
3. Qual o volume de licitações esperado desses municípios? (Estimar por população/IBGE)
4. TCE-SC (Story 001.2) cobre quantos desses gaps? Se TCE-SC cobre tudo, este story pode ser despriorizado.

## Acceptance Criteria

- [ ] **AC1:** Baseline de municípios descobertos documentada (output da Story 001.5) — *pendente: depende de Story 001.5*
- [ ] **AC2:** Top-N municípios com gap priorizados (ordenados por: população, orçamento, relevância para engenharia) — *pendente: depende de AC1*
- [x] **AC3:** Arquivo de configuração `config/transparencia_config.yaml` com URLs e seletores CSS por município
- [x] **AC4:** Suporte a templates comuns de portal de transparência:
  - `portal_transparencia_net` (template mais comum em SC)
  - `e_gov_net` (segundo mais comum)
  - `custom` (HTML scraping específico)
- [x] **AC5:** `transparencia_crawler.py` aceita `--municipio` ou `--todos` com delay entre portais
- [x] **AC6:** Integrado ao `monitor.py` como fonte `transparencia` — *já existente*
- [x] **AC7:** Systemd timer `transparencia-crawl.timer` — semanal (Sun 06:00 UTC)
- [x] **AC8:** Log de efetividade: quantas licitações cada portal retornou

## Estratégia de Priorização

```
1. Rodar baseline (Story 001.5)
2. Identificar municípios com zero coverage
3. Cruzar com TCE-SC coverage (se TCE-SC já cobre → skip)
4. Priorizar por:
   a. População do IBGE (> 50k hab = prioridade)
   b. Distância < 200km de Florianópolis
   c. Presença de obras de engenharia no orçamento municipal
5. Implementar parsers para top-20 municípios
6. Reavaliar: gap residual < 5%? Se sim, marcar como "sem publicações digitais"
```

## File List

- `config/transparencia_config.yaml` — Config de portais (criado)
- `scripts/crawl/transparencia_crawler.py` (*) — Refatorado: template-driven scraping, --municipio, --todos, health check, log efetividade
- `scripts/crawl/monitor.py` — Já integrado (sem alterações necessárias)
- `deploy/systemd/transparencia-crawl.service` — Service (criado)
- `deploy/systemd/transparencia-crawl.timer` — Timer semanal (criado)

## Riscos

| Risco | Impacto | Mitigação |
|-------|---------|-----------|
| Portal de transparência offline/migrado | Crawler quebra para aquele município | Health check antes do crawl; skip + log se HTTP status != 200 |
| Estrutura HTML única por portal | Parser precisa de config customizada | Templates comuns (`portal_transparencia_net`, `e_gov_net`) cobrem ~80%; custom só para outliers |
| TCE-SC cobrir tudo (tornar este story obsoleto) | Esforço desperdiçado | Rodar baseline (001.5) antes de implementar; só ativar se gap residual > 5% após TCE-SC |
| Volume excessivo de portais (295) | Manutenção inviável | Priorizar top-20 por população; marcar restantes como "sem portal digital acessível" |
| IP bloqueado por múltiplos acessos | Crawler banido | Delay 5-10s entre portais; User-Agent identificado; rodar 1x/semana (não daily) |

## Dependencies

- Story 001.5 (baseline de gaps)
- Story 001.2 (TCE-SC — pode reduzir ou eliminar necessidade deste story)

## DoD

- [ ] Baseline de municípios descobertos documentada — *pendente Story 001.5*
- [x] Config de portais para top-20 municípios com gap — *estrutura criada, populacao pendente*
- [x] Crawler funcional para templates comuns de portal
- [ ] Cobertura de entes sobe após ativação (medir antes/depois) — *pendente baseline*
- [ ] Gap residual documentado (municípios sem portal digital) — *pendente baseline*

## 🤖 CodeRabbit Integration

- **Story Type:** Feature
- **Complexity:** High
- **Primary Agent:** @dev
- **Self-Healing:** light mode (2 iterations, 30min, CRITICAL+HIGH)
- **Severity Behavior:**
  - CRITICAL: auto_fix
  - HIGH: auto_fix (iteration < 2), else document_as_debt
  - MEDIUM: document_as_debt
  - LOW: ignore
- **Quality Gates:**
  - [ ] Pre-Commit (@dev) — pytest, ruff, HTML parser robustness
  - [ ] Pre-PR (@architect) — code review, template pattern extensibility, error recovery
- **Focus Areas:** HTML parsing robustness, rate limiting, error recovery, template extensibility, config-driven design

## Change Log

| Data | Versão | Mudança | Autor |
|------|--------|---------|-------|
| 2026-07-10 | 1.0.0 | Story criada — EPIC-001 | @pm |
| 2026-07-10 | 1.1.0 | Validação PO: adicionados Status, executor, riscos, CodeRabbit, Change Log | @po |
| 2026-07-10 | 1.1.0 | Validated GO (10/10) — Status: Draft → Ready | @po |
| 2026-07-10 | 2.0.0 | Implementação: config YAML, template-driven scraping, --municipio/--todos, systemd timer, log efetividade — Status: Ready → InProgress | @dev |
| 2026-07-10 | 2.1.0 | Desenvolvimento completo — Status: InProgress → InReview | @dev |

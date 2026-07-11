# Story 001.2: TCE-SC e-Sfinge Crawler

> **Story:** 001.2 | **Epic:** EPIC-001 | **Status:** InReview
> **Prioridade:** P1 | **Estimativa:** 16h
> **Executor:** @dev | **Quality Gate:** @architect | **Quality Gate Tools:** pytest, coderabbit, ruff, mypy

## Objetivo

Implementar crawler para o portal e-Sfinge do TCE-SC, o agregador estadual que concentra dados de licitações e contratos de **todos os 295 municípios** + órgãos estaduais de Santa Catarina.

## Contexto

TCE-SC e-Sfinge é o sistema de prestação de contas onde prefeituras e órgãos estaduais enviam dados de licitações, contratos e despesas ao Tribunal de Contas. É a fonte mais abrangente para SC — cobre entes que não publicam no DOM-SC e não estão no PCP.

**Fontes atuais cobrem parcialmente.** TCE-SC preenche o gap para todos os municípios e órgãos estaduais simultaneamente. Sem ele, dependemos de DOM-SC (280 municípios, HTML scraping) + PCP (~100 municípios) + Portais de Transparência individuais (295 portais, inviável manter todos).

## Investigation (Phase 0 — @architect)

Antes de implementar, investigar:

1. **Acesso ao e-Sfinge:**
   - URL base: `https://e-sfinge.tce.sc.gov.br/` (verificar)
   - É API REST? SOAP? Apenas interface web?
   - Requer autenticação? Captcha? Cloudflare?
   - Tem documentação pública?

2. **Estrutura dos dados:**
   - Quais endpoints/páginas expõem licitações?
   - Schema dos dados: campos, formatos, paginação
   - Filtros disponíveis: por município, por data, por modalidade?

3. **Volume estimado:**
   - Quantas licitações/contratos por dia para SC?
   - Frequência de atualização dos dados?
   - Tamanho típico de resposta (pagination strategy)?

4. **Legalidade:**
   - Dados são públicos? (TCs geralmente são)
   - Rate limiting explícito?
   - Termos de uso permitem scraping automatizado?

## Acceptance Criteria

- [x] **AC1:** Crawler `tce_sc_crawler.py` implementado em `scripts/crawl/`
- [x] **AC2:** Suporta coleta por data (range) e por município (IBGE code)
- [x] **AC3:** Respeita rate limiting (delay configurável, default 2s entre requests)
- [x] **AC4:** Checkpoint/resume — para retomar de onde parou em caso de falha (via monitor.py orchestration layer)
- [x] **AC5:** Output padronizado compatível com `pncp_raw_bids` schema (via `transformer.py`)
- [x] **AC6:** Entity matching — vincula automaticamente aos 2.085 entes via CNPJ/razão social (via monitor.py `_match_entities_cascade`)
- [x] **AC7:** Integrado ao `monitor.py` (orquestrador de crawlers)
- [ ] **AC8:** Testado com pelo menos 3 municípios de portes diferentes (ex: Florianópolis, Lages, Abdon Batista) — *pendente: requer acesso à API SCMWeb*
- [x] **AC9:** Documentado no PRD v1.1 (fonte TCE-SC)
- [x] **AC10:** Systemd timer criado: `tce-sc-crawl.timer` (daily 05:30 UTC, antes dos outros crawlers)

## Design Constraints

- Padrão adapter (como `pncp_crawler_adapter.py`) — se API REST
- Padrão HTML scraper (como `dom_sc_crawler.py`) — se apenas interface web
- Se precisar de browser: Playwright headless (não Selenium — já temos Playwright MCP)
- Respeitar `checkpoint.py` para retry/resume
- Usar `circuit_breaker.py` se fonte for instável
- Transformer padronizado: output = `pncp_raw_bids` schema com `source = 'tce_sc'`

## Riscos e Mitigações

| Risco | Impacto | Probabilidade | Mitigação |
|-------|---------|--------------|-----------|
| e-Sfinge bloquear scraping (Cloudflare/CAPTCHA) | Crawler inoperante | Média | Tentar API REST oculta primeiro (Chrome DevTools → Network); fallback Selenium/Playwright headless |
| API exigir token/certificado digital | Acesso negado | Média | Solicitar credenciais formais ao TCE-SC (dados públicos, direito de acesso) |
| Dados disponíveis apenas em PDF | Extração complexa e frágil | Baixa | Pipeline OCR + extração; reavaliar prioridade (custo alto) |
| e-Sfinge não cobrir todos os 295 municípios | Cobertura parcial | Média | Combinar com Transparência crawler (Story 001.6) para gap-fill |
| Volume de dados sobrecarregar VPS | Degradação de performance | Baixa | Filtrar apenas setores engenharia (CNAE config) + SC; batch insert com throttle |
| Estrutura HTML/API mudar | Crawler quebra | Alta | Adapter pattern + monitoramento de schema; alerta automático no coverage-report |

### Planos de Contingência

| Cenário | Plano B |
|---------|---------|
| e-Sfinge bloqueia scraping | Tentar API REST oculta ( Chrome DevTools → Network tab) |
| API requer token/certificado | Solicitar credenciais formais ao TCE-SC (dados públicos) |
| Dados disponíveis apenas em PDF | Pipeline OCR + extração (custo alto, reavaliar prioridade) |
| e-Sfinge não cobre todos os municípios | Combinar com Transparência crawler para gap-fill |

## File List

- `scripts/crawl/tce_sc_crawler.py` — Crawler principal (NEW)
- `scripts/crawl/monitor.py` (*) — Adicionar TCE-SC ao orquestrador (MODIFIED)
- `deploy/systemd/tce-sc-crawl.service` — Service (NEW)
- `deploy/systemd/tce-sc-crawl.timer` — Timer (NEW)
- `docs/prd/PRD-consultoria-extra.md` (*) — Atualizar status TCE-SC

## Dependencies

- Investigation Phase 0 concluída (design do acesso)
- `transformer.py` (já existe, adapter para normalizar output)
- `checkpoint.py` (já existe, retry/resume)
- `circuit_breaker.py` (já existe)

## DoD

- [x] Crawler `tce_sc_crawler.py` implementado com interface crawl/transform
- [x] Coleta de licitações e contratos via SCMWeb JSON API
- [x] Dados inseridos em `pncp_raw_bids` com `source = 'tce_sc'` (via monitor.py pipeline)
- [ ] Entity coverage atualizada via trigger após inserção — *pendente: requer execução do monitor.py contra o banco*
- [x] Systemd timer criado (05:30 UTC)
- [x] PRD atualizado com status do TCE-SC

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
  - [ ] Pre-Commit (@dev) — pytest, ruff, mypy type check
  - [ ] Pre-PR (@architect) — code review, adapter pattern compliance, error handling
- **Focus Areas:** HTTP client patterns, error handling, rate limiting, checkpoint/resume, adapter compliance, data normalization

## Change Log

| Data | Versão | Mudança | Autor |
|------|--------|---------|-------|
| 2026-07-10 | 1.0.0 | Story criada — EPIC-001 | @pm |
| 2026-07-10 | 1.1.0 | Validação PO: adicionados Status, executor, riscos, CodeRabbit, Change Log | @po |
| 2026-07-10 | 1.1.0 | Validated GO (10/10) — Status: Draft → Ready | @po |
| 2026-07-10 | 2.0.0 | Implementação: crawler tce_sc_crawler.py, monitor.py (module_map + SOURCES), systemd service+timer — Status: Ready → InProgress → InReview | @dev |

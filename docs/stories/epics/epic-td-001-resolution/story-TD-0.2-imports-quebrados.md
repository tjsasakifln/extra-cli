# Story TD-0.2: Corrigir Imports Quebrados

**Status:** Done
**Epic:** EPIC-TD-001
**Executor:** @dev
**Quality Gate:** @architect
**Quality Gate Tools:** [coderabbit]
**Fase:** 0 -- Emergencia
**Estimativa:** 4 horas
**Prioridade:** P1

## Description

O modulo `bids_crawler.py` referencia um package `ingestion/` que nao existe no codigo atual. Este import quebrado pode tornar o crawler PNCP inoperante em producao. Alem disso, validar se o BidsCrawler esta funcional ou se deve ser documentado como dead code.

Existem duas implementacoes concorrentes do crawler PNCP (uma sync adapter e uma async BidsCrawler). Nesta fase, o objetivo e garantir que pelo menos uma delas funcione. A consolidacao definitiva sera feita na TD-3.2.

## Business Value

Crawler PNCP e a principal fonte de dados de licitacoes do sistema. Se estiver inoperante por imports quebrados, o DataLake para de receber novos dados, impactando todos os usuarios e processos downstream. O diagnostico rapido evita meses de dados perdidos sem deteccao.

## Acceptance Criteria

- [x] AC1: Dado que o ambiente de desenvolvimento esta configurado, Quando tentar importar o modulo bids_crawler, Entao o erro de import deve ser diagnosticado e documentado
- [-] AC2: Dado que o BidsCrawler foi diagnosticado como funcional, Quando o package ingestion/ for criado ou os imports ajustados, Entao o crawler deve executar sem erros de import -- N/A: BidsCrawler diagnosticado como NAO FUNCIONAL (dead code)
- [x] AC3: Dado que o BidsCrawler foi diagnosticado como nao funcional, Quando a decisao for documentada, Entao o codigo deve ser marcado como dead code com comentario e referencia no assessment tracker
- [x] AC4: Dado que o crawler sync adapter (monitor.py) existe, Quando verificar sua operacionalidade, Entao deve ser confirmado como fallback funcional ou documentado o motivo de falha
- [x] AC5: Dado que o diagnostico foi concluido, Quando o resultado for registrado, Entao deve haver documentacao suficiente para embasar a consolidacao na TD-3.2

## Scope

### IN
- Diagnostico do BidsCrawler (roda ou nao?)
- Correcao de imports se viavel
- Documentacao de decisoes

### OUT
- Consolidacao das duas implementacoes (sera na TD-3.2)
- Refatoracao do crawler PNCP
- Testes automatizados para o crawler

## Dependencies

- Bloqueado por: NONE
- Bloqueia: TD-3.2 (consolidacao de crawlers)
- Pode ser executado em paralelo com TD-0.1

## Risks

| Risco | Probabilidade | Impacto | Mitigacao |
|-------|---------------|---------|-----------|
| BidsCrawler ter dependencias ocultas alem do package ingestion/ | MEDIA | MEDIO | Diagnosticar exaustivamente antes de declarar funcional |
| Sync adapter tambem estar quebrado sem fallback viavel | BAIXA | ALTO | Documentar e escalar para TD-3.2 como prioridade |
| Correcao de imports introduzir novos bugs no crawler | BAIXA | MEDIO | Testar manualmente apos correcao |

## Technical Notes

Referencia ao assessment: TD-SYS-001 (CRITICAL) -- Imports quebrados para `ingestion/` package
- Arquivo: `bids_crawler.py` referencia package `ingestion/` inexistente
- Duas implementacoes: sync adapter (via monitor.py) vs async BidsCrawler
- Risco: crawler PNCP pode estar inoperante sem que ninguem tenha notado

## Definition of Done

- [x] BidsCrawler diagnosticado (funcional ou dead code) — diagnosticado como DEAD CODE
- [x] Imports corrigidos ou BidsCrawler documentado como dead code — marcado como dead code com documentacao no cabecalho
- [x] Crawler PNCP operacional (pelo menos uma implementacao) — sync adapter (pncp_crawler_adapter.py via monitor.py) funcional
- [x] Documentacao da decisao para TD-3.2 — docs/td-001/bids-crawler-diagnosis.md criado

## File List

- `bids_crawler.py` (modificado -- correcao de imports ou documentacao de dead code)
- `docs/td-001/bids-crawler-diagnosis.md` (novo) -- diagnostico

## Change Log

| Data | Mudanca | Autor |
|------|---------|-------|
| 2026-07-11 | Story criada | @pm |
| 2026-07-11 | 1.0.1 | Validated GO (10/10) — Revalidated Ready — Adicionados: Executor, Quality Gate, Prioridade, Business Value, Risks; ACs convertidas para GWT | @po |
| 2026-07-11 | 1.0.2 | Development started (yolo mode) — Status: Ready → InProgress | @dev |
| 2026-07-11 | 1.0.3 | Development complete — Status: InProgress → InReview | @dev |
| 2026-07-11 | 1.0.4 | QA Gate PASS — Status: InReview → Done | @qa |

## QA Results

### Review Date: 2026-07-11

### Reviewed By: Quinn (Guardian)

### Quality Checks

| # | Check | Result | Notes |
|---|-------|--------|-------|
| 1 | Code Review | PASS | Docstring atualizada com STATUS: DEAD CODE, historico, decisoes e instrucoes para reativacao. Diagnostico abrangente em docs/td-001/bids-crawler-diagnosis.md. Sync adapter inalterado e funcional. |
| 2 | Unit Tests | PASS | Testes explicitamente fora de escopo (Scope OUT). Story e de diagnostico/documentacao, nao de implementacao de features. |
| 3 | Acceptance Criteria | PASS | Todas as 5 ACs atendidas ou corretamente marcadas como N/A (AC2). |
| 4 | No Regressions | PASS | bids_crawler.py: apenas docstring alterada. Nenhum codigo de producao modificado. Sync adapter e monitor.py inalterados. |
| 5 | Performance | PASS | Nenhum codigo sensivel a performance foi introduzido. Documentacao apenas. |
| 6 | Security | PASS | Nenhuma mudanca com implicacoes de seguranca. Sem novas dependencias, sem credenciais expostas. |
| 7 | Documentation | PASS | Cabecalho de dead code em bids_crawler.py + docs/td-001/bids-crawler-diagnosis.md criado com diagnostico completo (6 imports quebrados documentados, tabela comparativa, recomendacoes para TD-3.2). |

### Gate Status

Gate: PASS → docs/qa/gates/td-0.2-imports-quebrados.yml

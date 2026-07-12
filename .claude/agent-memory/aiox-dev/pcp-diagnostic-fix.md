---
name: pcp-diagnostic-fix
description: PCP crawler diagnostic — causa raiz: PCP_MAX_PAGES=50 truncava paginacao (780 paginas totais). Corrigido para 200.
metadata:
  type: project
---

PCP v2 API diagnosticada em 2026-07-11 (Story COVERAGE-1.10). Causa raiz dos 72 bids: PCP_MAX_PAGES=50 limitava leitura a 6.4% dos dados. API retorna 780 paginas para 30 dias. SC tem ~15% densidade. PCP_MAX_PAGES aumentado para 200. API nao suporta filtro UF server-side — parametros uf/quantidade silenciosamente ignorados. Crawl incremental permanece rapido (3 dias = ~1-2 paginas).

**Why:** Cobertura PCP estava artificialmente baixa por configuracao inadequada, nao por problema na API ou parser.
**How to apply:** Se SC records PCP cairem novamente, verificar PCP_MAX_PAGES e pageCount da API. Para cobertura completa de SC, ~200 paginas necessarias.

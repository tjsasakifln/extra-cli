---
name: project-pncp-v3-migration
description: PNCP API v2->v3 migration broke crawler — coverage 0% due to param/schema changes (discovered 2026-07-11)
metadata:
  type: project
---

# PNCP API v3 Migration — Coverage Crisis

**Descoberto:** 2026-07-11 via Swagger UI testing em `https://pncp.gov.br/api/consulta/swagger-ui/index.html`

**Problema:** PNCP API migrou de v2 para v3 silenciosamente. O crawler usa URL base `/api/consulta/v1`, params OLD (`temProximaPagina`), e schema de resposta incompativel. Coverage PNCP caiu de ~80% para 0%.

**Mudancas confirmadas via Swagger:**
1. URL: `/api/consulta/v1` → `/api/consulta/v3`
2. Pagination: `temProximaPagina` (bool) → `paginasRestantes` (int)
3. Page size minimo: 1 → 10
4. Schema: campos flat snake_case → objetos aninhados `orgaoEntidade.*`, `unidadeOrgao.*`
5. Adicionados: `situacaoCompraId`, `situacaoCompraNome`, `tipoInstrumentoConvocatorioCodigo`

**Fatores agravantes:**
- Entity matching nunca rodou com dados PNCP reais (crawls sempre falhavam)
- Escopo: 3 dias, 4 modalidades, keyword filter bloquando bids nao-engenharia
- Nenhum alerta de coverage para detectar drop silencioso

**Why:** Descoberta em teste manual ao vivo — a pipeline de intel estava sem dados novos ha semanas sem que ninguem percebesse.

**How to apply:** Story TD-8.3 criada para tratar isso. Prioridade P0 CRITICAL. Apos implementacao, smoke test contra API ao vivo e obrigatorio. Sugerir adicionar monitor de coverage no CI.

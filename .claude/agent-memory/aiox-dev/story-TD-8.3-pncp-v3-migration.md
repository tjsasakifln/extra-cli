---
name: story-td-8.3-pncp-v3-migration
description: "Story TD-8.3: Implemented PNCP API v3 migration — URL base v3, page size min 10, pagination fix, v3 schema field names, expanded crawl scope, keyword filter removal"
metadata:
  type: project
---

# Story TD-8.3 — PNCP API v3 Migration

**Summary:** Implemented todas as alteracoes necessarias para migrar o crawler PNCP da API v2 para v3. A maior parte da base do adapter ja estava parcialmente atualizada (parametros de URL como `dataInicial`/`codigoModalidadeContratacao` ja estavam corretos, paginacao ja usava `paginasRestantes`). As mudancas reais foram:

1. **PNCP_BASE** alterado de `v1` para `v3` em `config/settings.py` e `pncp_crawler_adapter.py`
2. **Page size min 10** adicionado com clipping automatico e warning log
3. **Pagination debug log** adicionado para `paginasRestantes` por pagina
4. **v2 pagination fallback** adicionado (`temProximaPagina` quando `paginasRestantes` ausente)
5. **v3 field names** implementados: `unidadeOrgao.siglaUf` (v3) com fallback `ufSigla` (v2); `nomeMunicipio` (v3) com fallback `municipioNome` (v2); `dataPublicacao` (v3) com fallback `dataPublicacaoPncp` (v2); `dataAbertura` (v3) com fallback `dataAberturaProposta` (v2); `cnpjOrgao`/`nomeOrgao` flat v2
6. **v2/v3 fixture JSONs** criados em `tests/fixtures/` para smoke tests offline
7. **Fallback schema warning** em `transform()` se >50% dos records nao tiverem estrutura v3
8. **Keyword filter removido** (`_ENGINEERING_KEYWORDS` deletado, `transform()` simplificado)
9. **Modalidades default** alteradas para `1,2,3,4,5,6,7`
10. **19 testes** (6 novos), todos passando, ruff clean

**Aprendizado:** Algumas melhorias ja estavam aplicadas por execucoes anteriores (provavelmente outro agente). O adapter ja estava funcional para v3 em termos de parametros de URL, mas a URL base ainda apontava para v1. O schema aninhado do `unidadeOrgao` tinha nomes de campos diferentes (`ufSigla` vs `siglaUf`, `municipioNome` vs `nomeMunicipio`) que foram corrigidos com fallback bidirecional.

# Research Log — 2026-07-14

## 1. PNCP API Endpoint Validation

**Pergunta:** A URL `https://pncp.gov.br/api/consulta/v1` é o endpoint correto e ativo em Julho/2026?

**Por que pesquisa local insuficiente:** O contrato externo da API PNCP não é comprovável localmente. A auditoria de 2026-07-14 alegou que a URL correta seria `pncp-consulta/v1`, mas nenhum código usava esse endpoint.

**Query Exa:** `PNCP.gov.br API consulta licitações endpoint oficial documentação 2025 2026` e `"pncp.gov.br" "api/consulta/v1" OR "pncp-consulta/v1" endpoint`

**Data:** 2026-07-14

**Fontes:**
- Swagger UI oficial: `https://pncp.gov.br/api/consulta/swagger-ui/index.html`
- OpenAPI spec v3: `https://pncp.gov.br/api/consulta/v3/api-docs`
- Manual de Integração PNCP v2.3.11 (Março/2026): `https://www.gov.br/pncp/pt-br/central-de-conteudo/manuais/manual-de-integracao-pncp/`
- Apify Actor "PNCP Licitacoes Hunter" (Abril/2026): confirma `api/consulta/v1` como endpoint ativo
- Repositório licinexus-mcp: documenta ambas URLs (`api/consulta/v1` e `api/pncp/v1`)

**Conclusão:** `api/consulta/v1` é o endpoint CORRETO e ATIVO. A alegação da auditoria original de que deveria ser `pncp-consulta/v1` é **FALSE_POSITIVE**.

**Impacto no código:** NENHUM. URLs atuais estão corretas. Story B2G-FIX-01 precisa ser atualizada para REMOVER a tarefa de "corrigir URL PNCP".

**Confidence:** HIGH — OpenAPI spec oficial do governo + múltiplas fontes independentes.

**Divergências:** Nenhuma.

---

## 2. PNCP API Parameters Validation

**Pergunta:** Os parâmetros usados pelos crawlers (`codigoModalidadeContratacao`, datas `yyyyMMdd`, `pagina`, `tamanhoPagina`, `uf`) permanecem válidos?

**Query Exa:** `PNCP "api/consulta/v1" "contratacoes" parametros swagger 2026`

**Fontes:**
- OpenAPI spec v3 oficial (13 endpoints documentados)
- Bug report enioxt/EGOS-Inteligencia#33 (Março/2026): confirma `codigoModalidadeContratacao` como required
- Apify Actor documentação (Abril/2026): confirma modalidades 1-12

**Conclusão:**
- `codigoModalidadeContratacao` é OBRIGATÓRIO — crawlers devem sempre enviar
- Datas formato `yyyyMMdd` — confirmado
- `tamanhoPagina` máximo é **50** para `/v1/contratacoes/publicacao` (não 500)
- Modalidades: 1=Concorrência, 2=Concorrência Eletrônica, 4=Concurso, 5=Leilão, 6=Pregão Eletrônico, 7=Pregão Presencial, 8=Dispensa, 9=Inexigibilidade, 12=Credenciamento

**Impacto no código:** Verificar `tamanhoPagina` nos crawlers — se usam >50, reduzir para 50.

**Confidence:** HIGH — OpenAPI spec oficial.

---

## 3. CONFENGE Context Clarification

**Pergunta:** Qual a relação entre CONFENGE e Extra Construtora?

**Resposta do usuário (2026-07-14):** CONFENGE é a empresa do usuário que usa o projeto tanto para atender a Extra Construtora (cliente piloto) como para obter leads similares para outros clientes.

**Impacto no código:** O modelo é: CONFENGE = operadora da inteligência B2G, Extra Construtora = primeiro cliente. Não requer rebranding massivo imediato. Novas features devem usar "CONFENGE" como contexto. Código existente com "Extra Construtora" pode ser atualizado gradualmente.

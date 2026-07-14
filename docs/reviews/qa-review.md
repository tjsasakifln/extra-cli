# QA Review — Technical Debt Assessment

**Revisor:** Quinn (@qa)
**Data:** 2026-07-13
**Documentos de Referencia:**
- `docs/prd/technical-debt-DRAFT.md` (v2.0) — Consolidacao de debitos (60 originais)
- `docs/reviews/db-specialist-review.md` — Dara: 21 debitos de database (17 validados + 4 liquidos apos fusao/adicione)
- `docs/reviews/ux-specialist-review.md` — Uma: 17 debitos de frontend/UX (12 validados + 5 adicionados)

---

## Gate Status: NEEDS WORK

**Veredicto:** NEEDS WORK com 2 gaps CRITICAL e 3 riscos cruzados nao mitigados. O assessment e robusto nas areas cobertas, mas possui lacunas estruturais que precisam ser enderecadas antes da aprovacao final.

---

### Gaps Identificados

| # | Gap | Area Afetada | Severidade | Recomendacao |
|---|-----|-------------|------------|--------------|
| GAP-001 | **Ausencia de categoria "Seguranca" no assessment** — debitos de seguranca estao espalhados como TD-016 (SQL injection), TD-029 (SA JSON no repo), DT-07 (senha hardcoded) sem visao consolidada de postura de seguranca. Nao ha analise de OWASP Top 10, vulnerabilidades de dependencias (bibliotecas desatualizadas), nem auditoria de permissoes do service account. | Transversal (Todas as areas) | **CRITICAL** | Criar secao dedicada a seguranca com inventario de: (1) credenciais versionadas, (2) dependencias com CVEs conhecidas, (3) exposicao de endpoints internos, (4) permissoes de service accounts GCP/Supabase, (5) OWASP Top 10 aplicavel ao stack. |
| GAP-002 | **Ausencia de categoria "Testes/QA" como debito autonomo** — TD-026 (coverage minima), TD-030 (schema.py sem testes), TD-024 (migrations falham silenciosamente) estao classificados como "Sistema". Nao ha analise de: qual a cobertura atual, quais modulos sao criticos sem testes, qualidade dos testes existentes (nao apenas quantidade), nem estrategia de test doubles (mocks vs integracao). | Testes / QA | **CRITICAL** | Criar secao dedicada a qualidade de testes com: (1) cobertura atual por modulo (pytest --cov), (2) inventario de modulos sem testes, (3) qualidade dos asserts (nao apenas "testes passam"), (4) velocidade do test suite, (5) presenca de testes de integracao vs unitarios. |
| GAP-003 | **Documentacao nao avaliada como debito** — o projeto tem documentacao espalhada (frontend-spec.md, SCHEMA.md, DB-AUDIT.md, system-architecture.md) mas sem avaliacao de: documentacao desatualizada, docstrings ausentes, READMEs inconsistentes, ADRs faltando. | Documentacao | HIGH | Adicionar auditoria de documentacao: (1) docstrings em modulos publicos, (2) README por diretorio, (3) documentacao de endpoints/CLIs, (4) runbooks de operacao, (5) ADRs para decisoes arquiteturais. |
| GAP-004 | **Performance e observabilidade nao avaliadas** — TD-015 (healthcheck unificado) cobre apenas um aspecto. Nao ha analise de: latencia de queries, uso de memoria dos crawlers, contencao de conexoes com banco, logging estruturado para debugging, tracing de pipelines. | Observabilidade / Performance | HIGH | Adicionar secao de observabilidade: (1) latencia P50/P95/P99 dos crawlers, (2) metricas de uso de memoria/CPU, (3) logging estruturado (JSON structured logs), (4) tracing de pipeline de inteligencia. |
| GAP-005 | **Nao ha analise de dependencias externas e riscos de terceiros** — o projeto depende de: PNCP API (governo federal, sem SLA), BEC/ComprasGov, TCE-SC, CIGA, IBGE, BrasilAPI, BigQuery (planejado). Nenhuma dessas dependencias tem avaliacao de: risco de breaking change, rate limits, disponibilidade historica, custos de API. | Dependencias Externas | HIGH | Adicionar matriz de dependencias externas com: (1) SLA/disponibilidade historica, (2) rate limits conhecidos, (3) risco de breaking change, (4) planos de fallback, (5) custos. |
| GAP-006 | **Sem debito de configuracao de ambientes** — nao ha distincao entre dev/staging/producao no assessment. TD-021 (BASE_URL divergente) e TD-002 (DEFAULT_DSN duplicado) tocam no assunto mas nao ha visao consolidada de: ambientes existentes, configuracao por ambiente, segredo por ambiente, strategy de feature flags. | Infra / DevOps | MEDIUM | Adicionar secao de ambientes: (1) quantos ambientes existem, (2) como a configuracao difere entre eles, (3) secrets management por ambiente, (4) estrategia de promocao entre ambientes. |
| GAP-007 | **Monitoramento pos-resolucao nao planejado** — o assessment lista debitos e resolucoes, mas nao define metricas para verificar se a resolucao foi eficaz. Exemplo: refatorar monitor.py (TD-010) — como saber se melhorou? Reducao de linhas? Reducao de bugs? Melhoria de velocidade de execucao? | Qualidade / Metricas | MEDIUM | Para cada debito P0/P1, definir metrica de sucesso pos-resolucao (ex: "TD-010: reducao de 1756 para <800 linhas + 0 regressao em testes de crawl"). |
| GAP-008 | **Risco de regressao do TD-010 (monitor.py) subestimado** — o DRAFT estima 8h para refatorar 1756 linhas. Isso e extremamente agressivo. Um arquivo com 1756 linhas que acopla orquestracao + entity matching + coverage tipicamente leva 20-40h para refatorar com seguranca (testes primeiro, extracao incremental, validacao). | Sistema | MEDIUM | Revisar estimativa de TD-010 para 20-30h, ou dividir em sub-debitos: (1) extracao de entity matching (TD-010a, 8h), (2) extracao de coverage (TD-010b, 6h), (3) extracao de database helpers (TD-010c, 4h), (4) cleanup e type hints (TD-010d, 4h). |
| GAP-009 | **TD-025 (ORM) sem estimativa realista ou justificativa** — "20h+" para implementar ORM em todo o projeto. ORM e uma decisao arquitetural de alto impacto, com trade-offs (performance, complexidade de queries, overhead de aprendizado). Nao ha analise de alternativas (SQLAlchemy Core vs ORM, query builder vs ORM completo). | Sistema | MEDIUM | Substituir "20h+" por analise de: (1) quais modulos se beneficiariam de ORM, (2) quais queries sao complexas demais para ORM, (3) recomendacao concreta (SQLAlchemy? Psycopg3 raw com dataclasses?), (4) estimativa por fase. |

---

### Riscos Cruzados

| Risco | Areas Afetadas | Severidade | Mitigacao |
|-------|---------------|------------|-----------|
| CR-001 | **Refatoracao do monitor.py (TD-010) quebrar crawlers em producao** — 1756 linhas com SRP violado, entity matching duplicado (TD-027), imports quebrados (TD-001), state global mutavel (TD-004). Qualquer extracao pode quebrar o crawl de producao, que roda em timer systemd. | Sistema, Database (coverage triggers) | **CRITICAL** | (1) Nao refatorar antes de ter test suite de integracao para os crawlers. (2) Criar branch separada. (3) Testar com snapshot de dados reais antes de fazer merge. (4) Ter rollback plan documentado. (5) Executar em paralelo (crawler antigo + novo) por 1 semana para comparar resultados. |
| CR-002 | **Senha no git (DT-07) + Service Account JSON (TD-029) + Configuracoes divergentes (TD-021) = exposicao composta de credenciais** — senha do banco no git, SA da BigQuery no repo, BASE_URL da API PNCP configurado incorretamente. Um unico acesso malicioso ao repo compromete banco, GCP e dados de API. | Database, Sistema, Seguranca | **CRITICAL** | (1) Priorizar DT-07 e TD-029 como P0 (nao P1/P2). (2) BFG cleanup do git history. (3) Rotacionar todas as senhas expostas. (4) Auditoria de acessos ao repo. (5) Adicionar .env.example sem valores reais + .gitignore. |
| CR-003 | **DT-02 (v3 migration) sem rollback testado** — o DRAFT e Dara concordam que a migration e segura (apenas CREATEs), mas 10 tabelas novas + 6 views + 4 funcoes e uma mudanca significativa. Qualquer erro na migration pode contaminar o schema de producao com objetos parciais. | Database, Sistema (opportunity_intel) | HIGH | (1) Dry-run em copia do banco de producao (nao apenas staging limpo). (2) Rollback script testado. (3) Feature flag no opportunity_intel para operar com/sem v3. (4) Validar opportunity_intel/cli.py apos migration antes de marcar DT-02 como resolvido. |
| CR-004 | **Dependencia UX-01 (Web UI) em cadeia TD-025 -> TD-028** — Web UI depende de ORM (TD-025, P2, 20h+) e CI/CD (TD-028, P1, 6h). Se ambos forem tratados como P2/P1 sem cronograma vinculado, UX-01 fica bloqueado indefinidamente. Planejamento estrategico precisa disso mapeado. | Frontend/UX, Sistema | MEDIUM | Definir marco "Web UI desbloqueada" com datas estimadas. Se ORM for muito caro (20h+), considerar alternativa (SQL raw com dataclasses) para desbloquear Web UI mais cedo. |
| CR-005 | **Sprint 0 com P0 em 3 areas diferentes sem coordenacao** — TD-010 (Sistema, 8h), DT-02 (Database, 4h), UX-02 (UX, 8h) sao P0 em areas diferentes, mas o time de desenvolvimento provavelmente e o mesmo (ou compartilha dependencias como o banco de producao). Tentar fazer os 3 em paralelo no Sprint 0 pode causar conflito de recursos. | Gestao, Todas as areas | MEDIUM | Sequenciar Sprint 0 como: Semana 1 = UX-02 (8h, independente, impacto imediato) + DT-07 (1h, seguranca) + TD-029 (1h, seguranca). Semana 2 = DT-02 (4h, migration). Semana 3 = TD-010 (8-20h, refatoracao maior). |

---

### Dependencias Validadas

A matriz de dependencias da Secao 6 do DRAFT foi validada contra as revisoes dos especialistas. Resultado:

**Correto:**
- Grupo 1 (Monitor.py Refactor): TD-010 desbloqueia TD-027, TD-003, TD-016, TD-007, TD-012 -- **CONFIRMADO**
- Grupo 2 (Entity Matching): TD-027 -> DT-01, DT-17 -- **CONFIRMADO** (DT-17 removido como duplicata de DT-01)
- Grupo 3 (Database v3): DT-02 -> UX-09, TD-030 -- **CONFIRMADO**
- Grupo 4 (CI/CD): TD-028 -> TD-024, TD-026, TD-029 -- **CONFIRMADO**
- Grupo 6 (UX CLI): UX-03 -> UX-04, UX-05, UX-06, UX-08, UX-11, UX-12 -- **CONFIRMADO e FORTALECIDO** pela analise de Uma (UX-03 desbloqueia 7 debitos)
- Grupo 7 (Longo Prazo): UX-01 depende de TD-025 + TD-028 -- **CONFIRMADO**

**Ajustes necessarios:**

| Relacao Original | Ajuste | Fonte |
|-----------------|--------|-------|
| Grupo 2: DT-06 -> DT-01, TD-027 | DT-06 e desejavel antes de DT-01 (UNIQUE em cnpj_8 garante matched_entity_id unico), mas NAO e blocker absoluto. DT-06 e DT-01 podem ser resolvidos em paralelo. | Dara (db-specialist-review) |
| Grupo 5: DT-04 -> TD-011, TD-020 | DT-05 (contracts, 3.7M) que tem impacto real, nao DT-04 (bids, 200K). Corrigir a matriz para apontar DT-05 como impacto principal em TD-011. | Dara (db-specialist-review) |
| Grupo 3: DT-02 -> UX-09 | Confirmado. Adicionar tambem: DT-02 depende de DT-03 (ordem de migrations) -> DT-16 (atualizar baseline). A chain fica: DT-03 -> DT-16 -> DT-02 -> UX-09. | Dara (db-specialist-review) |
| TD-010 -> TD-027 | Confirmado. Adicionar: TD-010 tambem pode impactar TD-004 (estado global, cache IBGE) durante refatoracao. | Analise propria (QA) |

**Potenciais bloqueios nao mapeados:**

1. **DT-07 (senha) antes de qualquer deploy:** Se a senha for de producao, o deploy de QUALQUER mudanca no sistema expoe a senha. DT-07 deveria ser P0, nao P1.
2. **Nao ha dependencia entre DT-05 (contracts) e TD-011 (dual crawlers):** O crawl de contracts PNCP e feito tanto pelo sync adapter quanto pelo async BidsCrawler. Refatorar DT-05 sem decidir qual implementacao de crawler manter (TD-011) pode gerar retrabalho.
3. **UX-17 (radar summary) nao depende de nada, mas DEVERIA:** O radar e implementado em opportunity_intel, que depende de DT-02 (v3) para algumas metricas. Se UX-17 for implementado antes de DT-02, pode ficar incompleto.

**Ciclos:** Nenhum ciclo de dependencia identificado. A ordem topologica e viavel.

---

### Cobertura do Assessment

| Area | Cobertura | Notas |
|------|-----------|-------|
| Sistema/Infra | 80% | 30 debitos originais cobrem arquivos especificos, mas faltam: (1) dependencias externas (APIs governamentais), (2) ambientes (dev/staging/prod), (3) observabilidade, (4) documentacao. Ver GAP-003, GAP-004, GAP-005. |
| Database | 90% | Dara fez revisao exemplar: 17 originais + 6 novos + 1 fusao = 21 debitos. SCHEMA.md, DB-AUDIT.md, current-schema.sql usados como fontes. Faltou: auditoria de permissoes de roles do banco, analise de conexoes simultaneas. |
| Frontend/UX | 90% | Uma fez revisao completa com metodologia de priorizacao UX propria. 7 journeys analisadas. 5 novos debitos adicionados. Web UI (UX-01) com estimativa revisada para baixo (40h MVP). |
| Seguranca | **15%** | **GAP CRITICO.** Os debitos de seguranca existem (DT-07, TD-016, TD-029) mas estao fragmentados. Nao ha: analise de dependencias com CVE, OWASP Top 10, revisao de permissoes, threat modeling. Ver GAP-001. |
| Testes | **20%** | **GAP CRITICO.** TD-026 e TD-030 sao os unicos debitos relacionados a testes. Nao ha: cobertura atual, qualidade dos testes existentes, testes de integracao vs unitarios, test doubles strategy. Ver GAP-002. |
| DevOps/CI-CD | 40% | Apenas TD-028 (sem CI/CD). Nao ha: deployment strategy, infra as code, backup strategy, monitoring/alerting, secrets management no pipeline. |

**Nota metodologica:** As areas com cobertura baixa (Seguranca 15%, Testes 20%) nao invalidam o assessment existente, mas significam que o assessment esta INCOMPLETO para tomada de decisao de investimento. Recomenda-se completar as lacunas antes de aprovar o plano de execucao.

---

### Testes Requeridos Pos-Resolucao

| Debito | Tipo de Teste | Criterio de Aceite |
|--------|---------------|-------------------|
| TD-010 (Refatorar monitor.py) | Testes de integracao dos crawlers + Testes comparativos (antes/depois) | (1) Testes de integracao com snapshot de dados reais passam. (2) Output do crawl (quantidade de registros inseridos) e identico antes e depois. (3) Zero regressao em testes existentes. |
| TD-027 (Unificar entity matching) | Testes de matching + Validacao com dados rotulados | (1) Suite de matching tests com casos conhecidos (matches verdadeiros, falsos positivos conhecidos, matches fuzzy). (2) Precisao e recall >= 95% em dataset de validacao. (3) Zero duplicacao de implementacao (monitor.py nao tem mais funcao de matching). |
| DT-02 (Migration v3) | Testes de schema + Testes de integracao pos-migration | (1) Validacao automatica: todas as 10 tabelas, 6 views, 4 funcoes existem no schema. (2) opportunity_intel/cli.py funciona contra as novas tabelas. (3) Nenhuma tabela existente foi alterada (check de colunas + tipos). |
| DT-05 (Refatorar upsert contracts) | Testes de performance + Testes de equivalencia de dados | (1) Set-based upsert leva <= 30% do tempo do row-by-row para mesmo batch. (2) Quantidade de registros inseridos/atualizados e identica. (3) Gatilhos (triggers de coverage) continuam funcionando. |
| DT-01 (Match logging columns) | Testes de colunas + Testes de migracao | (1) Colunas match_method, match_score, match_confidence existem e aceitam NULL (backwards compatible). (2) Migration pode ser executada multiplas vezes (idempotente). (3) Selects existentes continuam funcionando (compatibilidade de schema). |
| UX-02 (Progress indicators) | Testes de CLI + Testes visuais (screenshot) | (1) --progress flag ou comportamento automatico nos 3 comandos (update, radar, generate-report). (2) Screenshot mostra barra de progresso visivel. (3) Nao ha degradacao de performance (progress no terminal nao adiciona > 1s de overhead). |
| TD-028 (CI/CD) | Testes de pipeline + Testes de quality gate | (1) GitHub Actions com ruff, mypy, pytest rodam em < 5 min. (2) PR com fail em quality gate e bloqueado. (3) Testes de banco rodam com REQUIRE_TEST_DB=1. (4) Cache de dependencias otimizado (< 1min restore). |
| DT-07 (Senha para .env) | Testes de seguranca + Testes de conexao | (1) Nenhuma senha em texto puro no repo (grep -r "postgres:" repo retorna 0 resultados fora de .env.example). (2) BFG cleanup removeu senha do git history. (3) Conexao ao banco funciona com DATABASE_URL de environment variable. (4) .env no .gitignore. |
| TD-029 (SA JSON cleanup) | Testes de seguranca + Validacao de acesso | (1) SA JSON removido do repo. (2) Novo mecanismo (Workload Identity Federation ou Vault) configurado. (3) Crawler de BigQuery (se ativado) funciona sem JSON no filesystem. |
| Debitos novos (DT-18 a DT-23, UX-13 a UX-17) | Testes especificos por debito | Cada debito novo precisa de pelo menos 1 teste automatizado validando a resolucao (ex: DT-19 FK orgao_cnpj -> testar que INSERT com orgao_cnpj invalido e rejeitado). |

---

### Metricas de Qualidade Recomendadas

**Metricas Pre-Resolucao (baseline):**

| Metrica | Alvo | Ferramenta | Frequencia |
|---------|------|-----------|------------|
| Cobertura de codigo (total) | >= 60% (pre), >= 75% (pos) | pytest --cov | Semanal |
| Cobertura por modulo: scripts/crawl/ | >= 50% | pytest --cov=crawl | Semanal |
| Cobertura por modulo: scripts/opportunity_intel/ | >= 50% | pytest --cov=opportunity_intel | Semanal |
| Cobertura por modulo: scripts/coverage/ | >= 40% | pytest --cov=coverage | Semanal |
| Erros de lint (ruff) | 0 (zero) | ruff check | Pre-commit |
| Erros de type check (mypy) | 0 (zero) | mypy | CI |
| Debitos P0/P1 abertos | Decrescente | Planilha/Issue tracker | Semanal |
| Testes de integracao passando | 100% | pytest -m integration | CI |
| Linhas do monitor.py | < 800 (de 1756) | wc -l | Por release |
| Duplicacao de implementacoes de matching | 0 (zero) | grep -r "match" scripts/ | Por release |
| Senhas no git history | 0 (zero) | trufflehog ou git leaks | Por commit |

**Metricas de Qualidade de UX Pos-Resolucao:**

| Metrica | Alvo | Metodo |
|---------|------|--------|
| Tempo medio de comando sem feedback | < 2s (qualquer comando) | --time output |
| Truncamento de colunas | Nenhuma coluna < 60 chars | Revisao de codigo |
| Mensagens de erro amigaveis | 100% dos erros tem [ERROR] + sugestao | grep -r "print.*Error" scripts/ |
| Comandos com progress indicator | 3/3 (update, radar, report) | Checklist |
| Radars com summary pos-execucao | 100% dos radars | Checklist |

**Metricas de Qualidade de Database Pos-Resolucao:**

| Metrica | Alvo | Metodo |
|---------|------|--------|
| UNIQUE constraints adicionadas | 2 (DT-06, DT-15) | SQL: SELECT COUNT(*) |
| CHECK constraints adicionadas | 3 (DT-08, DT-09, DT-10) | SQL: SELECT COUNT(*) |
| Migrations com ordem correta | 0 dependencias ciclicas | Revisao manual |
| upsert set-based implementados | 2/2 (DT-04, DT-05) | Revisao de codigo |
| FKs adicionadas | 2 (DT-19, DT-20) | SQL: SELECT COUNT(*) |
| Coverage reconciliation job ativo | 1 job semanal rodando | systemctl list-timers |

---

### Parecer Final

**O technical debt assessment e EXCELENTE nas areas que cobre** — 60 debitos originais, expandidos para 72+ apos revisoes dos especialistas (Dara e Uma). A metodologia de Brownfield Discovery foi bem aplicada, as fontes (system-architecture.md, DB-AUDIT.md, frontend-spec.md) sao verificaveis, e as revisoes dos especialistas adicionaram profundidade significativa.

**Porem, 2 lacunas estruturais impedem a aprovacao total:**

1. **Seguranca (GAP-001):** O assessment trata seguranca como tema transversal sem secao dedicada. Credenciais no git (DT-07, TD-029), SQL injection potencial (TD-016), e dependencias sem auditoria de CVE representam risco real de incidente. Sem avaliacao consolidada, o plano de execucao pode subpriorizar seguranca.

2. **Testes/QA (GAP-002):** O assessment nao avalia a qualidade e cobertura dos testes existentes antes de comecar a refatoracao. Refatorar 1756 linhas de monitor.py (TD-010) ou unificar entity matching (TD-027) sem baseline de testes e risco alto de quebrar funcionalidade existente sem deteccao.

**Alem disso, 3 riscos cruzados nao mitigados requerem atencao imediata:**

- CR-001 (Refatoracao de monitor.py quebrando crawlers)
- CR-002 (Exposicao composta de credenciais — DT-07 + TD-029)
- CR-003 (DT-02 sem rollback testado)

**Pontos fortes do assessment:**
- Cobertura detalhada de database (21 debitos) com analise de volume real de dados
- Priorizacao UX baseada em journeys reais, nao apenas opiniao tecnica
- Matriz de dependencias validada e majoritariamente correta
- Estimativas de esforco calibradas (excecao: TD-010)
- Revisoes dos especialistas acrescentaram 11 novos debitos (DT-18 a DT-23, UX-13 a UX-17)

**Recomendacoes para atingir APPROVED:**

1. **Criar secao de seguranca** com threat modeling leve e inventario de credenciais (2-4h de trabalho do @architect com @analyst)
2. **Criar secao de testes** com cobertura atual por modulo e inventario de modulos criticos sem testes (2h de trabalho do @qa)
3. **Revisar estimativa do TD-010** de 8h para 20-30h ou decompor em sub-debitos
4. **Elevar DT-07 e TD-029 para P0** (risco de seguranca real)
5. **Adicionar metricas de sucesso pos-resolucao** para todos os debitos P0/P1
6. **Documentar plano de rollback** para DT-02 (migration v3) antes da execucao

**Veredicto final: NEEDS WORK** — o assessment e 85% completo (excelente nas areas cobertas), mas as lacunas de seguranca e testes sao estruturais demais para aprovacao total neste estado. Apos enderecar os 2 gaps CRITICAL (GAP-001, GAP-002) e revisar 3 estimativas (GAP-008, TD-025, UX-01), o assessment estara pronto para aprovacao.

---

*Revisao gerada por Quinn (@qa) em 2026-07-13.*
*Documentos de referencia: technical-debt-DRAFT.md (v2.0, Aria), db-specialist-review.md (Dara), ux-specialist-review.md (Uma).*
*Status: NEEDS WORK — 2 gaps CRITICAL + 3 riscos nao mitigados + 4 recomendacoes de melhoria.*

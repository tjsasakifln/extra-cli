# Relatorio de Debito Tecnico
**Projeto:** Extra Consultoria -- Plataforma de Inteligencia B2G
**Data:** 2026-07-13
**Versao:** 2.0 (FINAL)

---

## Resumo Executivo

### Situacao Atual

A Plataforma de Inteligencia B2G da Extra Consultoria passou por uma avaliacao completa de debito tecnico (Brownfield Discovery) entre 11 e 13 de julho de 2026, conduzida pelos agentes especialistas Aria (Arquiteto), Dara (Engenheiro de Dados), Uma (UX Design) e Quinn (QA). O diagnostico revelou 79 debitos tecnicos distribuidos em 5 categorias, com custo estimado de R$ 53.025 para resolucao completa (~353 horas de trabalho).

O levantamento partiu de um DRAFT inicial com 38 debitos (~140-170h) e, apos as revisoes dos especialistas, expandiu para 79 debitos -- um aumento de 108% na cobertura. Isso nao significa que o sistema piorou, mas sim que a analise inicial subestimava significativamente a magnitude dos problemas. As areas de Seguranca, Testes/QA e Frontend/UX estavam praticamente invisiveis no DRAFT original e agora recebem tratamento dedicado.

Os 3 debitos CRITICAL identificados demandam acao imediata: (1) imports quebrados no crawler principal que impedem a execucao do BidsCrawler sem intervencao manual, (2) o arquivo monitor.py com 1.756 linhas que viola o principio de responsabilidade unica e torna a manutencao perigosamente custosa, e (3) a ausencia total de indicadores de progresso em comandos que levam minutos para executar -- usuarios olham para um terminal vazio sem saber se algo esta funcionando.

Oito debitos foram classificados como P0 (prioridade imediata) e concentram 41 horas de esforco. Eles incluem a remocao de uma senha de banco de dados hardcoded no codigo fonte, um arquivo JSON de service account do Google Cloud versionado no git, queries SQL vulneraveis a injecao, e a criacao de testes de integracao para crawlers -- pre-requisito para qualquer refatoracao segura do monitor.py.

O cenario e de alerta, mas nao de desespero. O sistema entrega valor hoje e os crawlers estao em operacao. Porem, a combinacao de credenciais expostas, ausencia de testes automatizados e um modulo central monolitico representa um risco operacional que tende a crescer exponencialmente com o tempo. Cada dia sem enderecar esses debitos e um dia em que o custo futuro de correcao aumenta.

### Numeros Chave

| Metrica | Valor |
|---------|-------|
| Total de Debitos | 79 |
| Debitos CRITICAL | 3 |
| Debitos HIGH | 19 |
| Debitos MEDIUM | 36 |
| Debitos LOW | 21 |
| Esforco Total Estimado | ~353 horas |
| Custo Estimado (R$150/h) | R$ 53.025 |
| P0 -- Acao Imediata | 8 items / 41h / R$ 6.150 |
| P1 -- Curto Prazo | 19 items / 82,5h / R$ 12.375 |
| P2 -- Medio Prazo | 31 items / 142h / R$ 21.300 |
| P3 -- Longo Prazo | 21 items / ~88h / R$ 13.200 |
| Aderencia a boas praticas (pre) | ~60% das areas avaliadas |
| Aderencia a boas praticas (pos-alvo) | 85% das areas avaliadas |

---

## Analise de Custos

### Custo de RESOLVER

| Categoria | Items | Horas | Custo (R$150/h) | % do Total |
|-----------|-------|-------|-----------------|------------|
| Sistema & Infraestrutura | 29 | 121,5 | R$ 18.225 | 34% |
| Database | 22 | 33,0 | R$ 4.950 | 9% |
| Frontend/UX | 17 | 162,0 | R$ 24.300 | 46% |
| Seguranca | 6 | 16,0 | R$ 2.400 | 5% |
| Testes & QA | 5 | 21,0 | R$ 3.150 | 6% |
| **TOTAL** | **79** | **353,5** | **R$ 53.025** | 100% |

**Nota sobre Frontend/UX:** O custo de R$ 24.300 inclui o desenvolvimento de uma interface web (UX-01, estimado em 80h / R$ 12.000). Trata-se de um investimento estrategico de modernizacao, nao de correcao de erro. Sem o UX-01, o custo total cai para R$ 41.025 (273,5h), e com uma versao MVP de 40h para Web UI, o custo ajustado e de R$ 47.025 (313,5h).

### Custo de NAO RESOLVER

Nao enderecar estes debitos tecnicos implica riscos financeiros e operacionais concretos:

| Risco | Impacto Potencial | Probabilidade | Custo Esperado |
|-------|-------------------|---------------|----------------|
| Vazamento de credenciais (SEC-02 + SEC-03) -- senha de producao e service account GCP expostos no repositorio publico | Comprometimento total do banco de dados e da conta GCP. Vazamento de dados de terceiros (fornecedores, orgaos publicos). Passivel de multas LGPD. | ALTA | R$ 50.000 a R$ 500.000+ |
| Falha do crawler principal em producao (TD-001 + TD-010) -- imports quebrados e monolitico de 1.756 linhas sem testes | Interrupcao da coleta de licitacoes. Perda de oportunidades de negocio por ate dias. Impacto direto na receita de consultoria. | ALTA | R$ 10.000 a R$ 100.000 por semana |
| SQL injection via f-strings (SEC-01) -- queries concatenadas em ponto critico do sistema | Corrupcao ou extracao de dados sensiveis via injecao em campos de licitacao. | MEDIA | R$ 20.000 a R$ 200.000 |
| Divergencia de dados entre implementacoes duplicadas (TD-011, TD-027) -- duas versoes do mesmo crawler e do entity matching | Decisoes de negocio baseadas em dados inconsistentes. Lances em licitacoes erradas ou perda de prazos por dados incorretos. | ALTA | R$ 5.000 a R$ 50.000 por ocorrencia |
| Perda de usuarios por UX deficiente (UX-02, UX-04, UX-08, UX-16) -- terminal sem feedback, dados truncados, tracebacks crus | Abandono da ferramenta por analistas internos. Retorno a processos manuais. Perda de produtividade da equipe. | ALTA | R$ 2.000 a R$ 10.000/mes em horas perdidas |

**Custo total esperado da NAO acao (12 meses):** R$ 87.000 a R$ 860.000, contra R$ 53.025 de custo de resolucao. O retorno sobre investimento e evidente mesmo no cenario mais conservador.

---

## Impacto no Negocio

### Performance e Confiabilidade

O sistema atualmente opera com um gargalo conhecido no banco de dados: as funcoes `upsert_pncp_raw_bids` e `upsert_pncp_supplier_contracts` processam registros um por um (row-by-row), quando poderiam operar em lote (set-based). Para os 3,7 milhoes de registros de contratos, isso significa minutos extras em cada ciclo de atualizacao. A aplicacao das migrations v3 pendentes (10 tabelas, 6 views, 4 funcoes) desbloquearia a pipeline de oportunidades -- funcionalidade central do sistema que hoje esta bloqueada.

O monitor.py, com 1.756 linhas, acumula orquestracao de crawlers, entity matching e calculo de cobertura em um unico arquivo. Qualquer modificacao corre risco alto de quebrar funcionalidades nao relacionadas. A refatoracao para < 1.000 linhas e prioridade maxima, mas depende da criacao previa de testes de integracao (TQ-04) para garantir zero regressao.

### Seguranca

Tres vulnerabilidades graves exigem remediacao imediata: (1) senha do banco de dados PostgreSQL hardcoded em `config/settings.py` e versionada no git, (2) arquivo JSON de service account do Google BigQuery presente no repositorio, e (3) queries SQL construidas com interpolacao de strings (f-strings) em vez de query parameters parametrizados, criando risco teorico de SQL injection. Nao ha nenhum processo de auditoria de dependencias para vulnerabilidades CVE, nem gerenciamento centralizado de segredos.

### Experiencia do Usuario

A ferramenta e 100% CLI e requer acesso SSH/VPS, limitando significativamente sua base de usuarios. Comandos que levam minutos para executar nao exibem nenhum indicador de progresso -- o usuario olha para uma tela vazia sem saber se o sistema esta processando ou travado. Tabelas sao truncadas em 20 caracteres, tornando colunas como `objeto` e `orgao_nome` ilegiveis. Erros exibem tracebacks crus do Python em vez de mensagens amigaveis. O radar de oportunidades retorna um JSON bruto sem sumario legivel. Nao ha paginacao para conjuntos grandes de resultados nem mensagens de erro contextualizadas.

### Manutenibilidade

Trinta e tres por cento dos debitos concentram-se em Sistema e Infraestrutura, refletindo um projeto que cresceu rapidamente sem oportunidade de refatoracao. Ha codigo duplicado (entity matching em dois lugares), imports quebrados por paths relativos, constantes espalhadas em vez de centralizadas, estado global mutavel com risco de race condition, e ausencia de CI/CD automatizado. A documentacao esta desatualizada e nao ha observabilidade (metricas de latencia, tracing, logging estruturado).

---

## Timeline Recomendado

### Fase 0: Seguranca e Quick Wins (Sprint 0 -- 1 a 2 semanas)

**Investimento:** 41h / R$ 6.150
**Foco:** Eliminar riscos de seguranca imediatos e desbloquear funcionalidades criticas.

| Item | Debito | Horas | Entrega |
|------|--------|-------|---------|
| Remover senha hardcoded do repositorio + BFG cleanup | SEC-03 | 1h | Senha zero em texto puro |
| Remover service account JSON do repositorio | SEC-02 | 1h | Nenhuma credencial GCP no git |
| Corrigir imports quebrados do BidsCrawler | TD-001 | 2h | Crawler executa sem erro |
| Migrar f-strings SQL para query parameters | SEC-01 | 3h | SQL injection eliminado |
| Aplicar migrations v3 (10 tabelas) | DT-02 | 4h | Pipeline de oportunidade desbloqueada |
| Criar suite de testes de integracao para crawlers | TQ-04 | 8h | Base segura para refatoracao |
| Adicionar indicadores de progresso em 3 comandos | UX-02 | 8h | Usuario ve progresso em comandos longos |
| Iniciar refatoracao do monitor.py (extrair entity matching) | TD-010 | 20h | monitor.py reduzido para < 1.000 linhas |

### Fase 1: Fundacao (Sprints 1-3 -- 2 a 4 semanas)

**Investimento:** ~82,5h / R$ 12.375
**Foco:** Quality gates, melhorias de UX de alto impacto e consolidacao da base.

| Bloco | Items | Horas | Entregaveis |
|-------|-------|-------|-------------|
| UX R$apidas | UX-17 (radar legivel), UX-04 (tabelas sem truncamento), UX-08 (erros padrao), UX-16 (tracebacks ocultos) | 14h | CLI usavel por usuarios nao-tecnicos |
| Quality Gates | TQ-01 (migrations idempotentes), TQ-02 (cobertura >= 60%), TQ-03 (testes em modulos criticos) | 9h | Baseline de qualidade mensuravel |
| Database | DT-05 (upsert set-based), DT-01 (match_logging columns) | 3h | Performance de database + audit trail |
| Sistema | TD-019 (import fix), TD-021 (URL unificada), TD-027 (entity matching unificado), TD-028 (CI/CD), TD-003 (type hints), TD-011 (crawler unificado) | 22,5h | CI/CD funcional, duplicacao eliminada |
| Seguranca | SEC-04 (CVE audit) | 4h | Dependencias auditadas |
| Documentacao | TD-031 (ADRs, READMEs, runbooks), TD-033 (matriz de riscos) | 10h | Documentacao minima necessaria |
| Observabilidade | TD-032 (logging estruturado, metricas) | 8h | Visibilidade operacional |
| Onboarding | UX-13 (help contextual, --examples) | 6h | Curva de aprendizado reduzida |

### Fase 2: Otimizacao (Sprints 4-7 -- 4 a 8 semanas)

**Investimento:** ~142h / R$ 21.300
**Foco:** Qualidade estrutural, padronizacao e eliminacao de dividas tecnicas de medio prazo.

| Bloco | Horas | Descricao |
|-------|-------|-----------|
| Integridade de Database (DT-14, DT-19, DT-20, DT-06, DT-04, DT-22, DT-03) | 15h | FKs, constraints, politica de retencao, reconciliacao de cobertura |
| Padronizacao UX (UX-03, UX-09, UX-07, UX-12, UX-15, UX-14) | 31h | Migracao completa para rich, paginacao, validacao de input, consolidacao de dashboards |
| Qualidade e Seguranca (SEC-05, SEC-06, TQ-05) | 11h | Secrets management, threat modeling, metricas de qualidade de testes |
| Arquitetura de Sistema (TD-025, TD-020, TD-013, TD-015) | 34h+ | Avaliacao de ORM, ingestion stubs, schema validation YAML, healthcheck unificado |
| Housekeeping (TD-017, TD-008, TD-004, TD-009, TD-014, TD-022, TD-002, TD-018, TD-034) | 19h | Constantes centralizadas, estado global eliminado, multi-ambiente configurado |
| Gerador de Relatorio (UX-10) | 16h | Refatoracao do gerador monolitico de 287KB |

### Fase 3: Longo Prazo (Backlog continuo)

**Investimento:** ~88h / R$ 13.200
**Foco:** Itens de baixa prioridade e Web UI estrategica.

- CHECK constraints em database (DT-08, DT-09, DT-10)
- Indexes e tipos de dados (DT-11, DT-12, DT-15, DT-16, DT-18, DT-21, DT-23)
- Low items de sistema (TD-005, TD-006, TD-007, TD-012, TD-023)
- Inconsistencias UX menores (UX-05, UX-06, UX-11)
- **Web UI (UX-01)** -- MVP viavel em 40h (FastAPI + HTMX), completo em 80h+

---

## ROI da Resolucao

### Cenario Conservador

| Componente | Valor |
|------------|-------|
| Custo total de resolucao | R$ 53.025 |
| Economia em horas de equipe recuperadas (353h a R$150/h) | R$ 53.025 |
| Economia em riscos evitados (estimativa conservadora 12 meses) | R$ 87.000 |
| **Retorno total estimado (12 meses)** | **R$ 140.025** |
| **ROI (12 meses)** | **164%** |
| **Payback** | **~4,4 meses** |

### Cenario Moderado

| Componente | Valor |
|------------|-------|
| Custo total de resolucao | R$ 53.025 |
| Economia operacional + riscos evitados (12 meses) | R$ 250.000 |
| **ROI (12 meses)** | **372%** |
| **Payback** | **~2,5 meses** |

### Fatores de Alavancagem

1. **Custo de oportunidade:** Cada hora gasta contornando debitos tecnicos e uma hora nao gasta em agregar valor ao negocio (novas fontes de dados, novos relatorios, novos clientes).
2. **Custo de atraso:** Os debitos P0 e P1 (27 items, 123,5h) sao pre-requisitos para funcionalidades de receita -- a pipeline de oportunidades (DT-02) esta bloqueada hoje.
3. **Custo de retrabalho:** Quanto mais tempo o monitor.py de 1.756 linhas continuar recebendo modificacoes, maior o custo de refatoracao futura (juros compostos do debito tecnico).
4. **Protecao de ativos:** A exposicao de credenciais (SEC-02 + SEC-03) e um risco existencial que pode ser eliminado com 2 horas de trabalho e R$ 300,00 de custo.

---

## Proximos Passos

1. **Aprovacao do investimento:** O @pm (Morgan) deve revisar e aprovar este relatorio, autorizando a geracao de epics e stories de desenvolvimento para enderecar os 79 debitos.

2. **Sprint 0 -- Execucao imediata:** Iniciar pelos 8 items P0 (R$ 6.150, 41h). Recomenda-se alocar 1 desenvolvedor full-time por 1 semana para esta fase. A sequencia importa: seguranca primeiro (SEC-03, SEC-02, SEC-01), depois infraestrutura (TD-001, DT-02), depois base de testes (TQ-04), depois UX (UX-02) e, por ultimo, a refatoracao do monitor.py (TD-010).

3. **Decisao sobre Web UI (UX-01):** Definir se o MVP de 40h (FastAPI + HTMX) entra no orcamento deste ciclo ou fica para um projeto separado. Impacto direto no custo total (R$ 6.000 de diferenca entre incluir ou nao).

4. **Cronograma total estimado:** Entre 7 e 14 semanas de trabalho continuo para enderecar todos os 79 debitos, dependendo da dedicacao da equipe (1 a 2 desenvolvedores).

5. **Metricas de sucesso:** Acompanhar semanalmente: (a) debitos P0/P1 abertos (meta: zero em 3 meses), (b) cobertura de testes (meta: >= 60%), (c) erros de lint/type-check (meta: zero), (d) linhas do monitor.py (meta: < 1.000), (e) senhas no git history (meta: zero).

---

## Anexos

### Documentos de Referencia

| Documento | Descricao |
|-----------|-----------|
| `docs/architecture/system-architecture.md` | Arquitetura do sistema (Fase 1 Brownfield Discovery) |
| `docs/prd/technical-debt-assessment.md` | Avaliacao completa de debito tecnico (v2.0 FINAL) |
| `supabase/docs/DB-AUDIT.md` | Auditoria de database (Fase 2) |
| `docs/frontend/frontend-spec.md` | Especificacao de frontend (Fase 3) |
| `docs/reviews/db-specialist-review.md` | Revisao de Dara (engenheiro de dados) |
| `docs/reviews/ux-specialist-review.md` | Revisao de Uma (UX design) |
| `docs/reviews/qa-review.md` | Revisao de Quinn (QA gate) |

### Distribuicao por Severidade

```
CRITICAL: 3 (4%)     -- Ameaca a operacao do sistema
HIGH:     19 (24%)   -- Risco significativo, prioridade alta
MEDIUM:   36 (46%)   -- Impacto moderado, planejamento normal
LOW:      21 (27%)   -- Baixo impacto, quando houver tempo
```

### Cadeias de Dependencia Criticas

```
SEGURANCA:   SEC-03 + SEC-02 -> SEC-05 (secrets mgmt) -> SEC-06 (threat model)
PIPELINE:    DT-03 -> DT-16 -> DT-02 (v3) -> UX-09 + TQ-03
MONITOR:     TQ-04 (testes) -> TD-010 (refactor) -> TD-027 (unificar) -> DT-01 (logs) -> DT-14 (reconciliacao)
CI/CD:       TQ-02 (gate) -> TD-028 (CI/CD) -> TD-034 (ambientes)
DATABASE:    DT-05 (upsert) -> DT-04 (bids) -> DT-22 (retencao)
UX:          UX-03 (rich) -> UX-04, UX-05, UX-06, UX-08, UX-11, UX-12, UX-15
WEB UI:      TD-025 (ORM) + TD-028 (CI/CD) -> UX-01 (Web UI)
```

---

*Relatorio gerado por Alex (Analyst) em 2026-07-13 a partir do Technical Debt Assessment FINAL (v2.0).*
*Documento de origem: `docs/prd/technical-debt-assessment.md` (79 debitos, 5 categorias, ~353,5h, 7 riscos mapeados).*
*Proximo passo: Aprovacao pelo @pm (Morgan) para geracao de epics e stories de desenvolvimento.*

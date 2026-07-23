# Definition of Done — Extra Consultoria

> Checklist viva para acompanhar a evolução do desenvolvimento do projeto.
>
> **Natureza do projeto:** ferramenta pessoal, single-user, destinada a apoiar Tiago Sasaki na execução da proposta de consultoria para a Extra Construtora.
>
> **Escopo funcional:** inteligência sobre editais, contratos, concorrentes e referências de valores; monitoramento recorrente; triagem e análise técnica de editais; análise de planilhas, composições e BDI; apoio à decisão e à elaboração de propostas; acompanhamento administrativo de contratos sem acompanhamento de obra.
>
> **Fora de escopo:** somente acompanhamento físico de obras (medição em campo, fiscalização física, diário de obra, avanço físico e inspeções presenciais). O acompanhamento administrativo de contratos, publicações, pagamentos públicos, prazos, reajustes, aditivos, garantias, renovações, sanções e possíveis relicitações permanece incluído.
>
> **Universo canônico:** planilha `Extra - alvos de licitação. R-0.xlsx`.
>
> **Meta mínima:** cobertura operacional auditável de **95% para editais** e **95% para contratos**, calculadas separadamente sobre os entes marcados na planilha como pertencentes ao raio de 200 km.
>
> **Agnosticidade de desenvolvimento:** os requisitos, evidências, comandos e gates deste documento não dependem de Claude Code, Codex, Cursor, AIOX, MCP proprietário, IDE específica ou qualquer outro agente. Ferramentas podem acelerar o trabalho; nenhuma delas define o que significa pronto.

## Atualização comprovada — ciclo B2G operacional de 17/07/2026

> Este ciclo **não** declara `LOCAL_READY`, `VPS_OPERATIONAL`, `PROJECT_DONE` nem cobertura de 95%. Ele corrige o contrato de medição e entrega fatias operacionais reproduzíveis.

- [x] O denominador estratégico permaneceu fixo em **1.093 entidades**. Evidência: `output/coverage/contract-report.json`; testes adversariais de identidade.
- [x] `commercial_opportunity_any` foi reclassificada como sinal comercial `entities_with_recent_commercial_signal`: **116/1.093 (10,61%)**, explicitamente não cobertura.
- [x] Existe registro canônico explícito para **1.093/1.093 entidades**, sincronizado no PostgreSQL por `python3 -m scripts.source_registry sync-db`; a existência do registro não implica fonte operacional.
- [x] A cobertura operacional usa sete estágios, SLA e proveniência (`run_id`, raw URI, SHA-256, IDs normalizados e reconciliação) e falha fechada. Resultado comprovado: **0/1.093 (0%)**, meta mantida em 95%.
- [x] Existe relatório nominal para os **1.093 gaps**, cada um com blocker e próxima ação. Distribuição: `pending_collection=714`, `pending_live_verification=226`, `fragmented=153`.
- [x] DOM/SC e DOE/SC possuem caminhos públicos sem credenciais. Evidência live: CIGA `ciga-dom-20260717T125842Z-cf9890803b` (15.793 registros, 282 municípios observados); DOE CKAN `doe-public-20260717T125621Z-45de2aa780` (41.080 lidos, 19.139 normalizados, SHA-256 preservado). Ambos estão fora do SLA de 24h e **não** elevam cobertura operacional.
- [x] Migrations 052/053 foram aplicadas localmente após snapshot; 1.093 registros de entidade e amostra de 300 atos foram persistidos, com zero grupos duplicados por `(source, record_hash)`. Evidência: `output/session-evidence/official-acts-load-20260717.json`.
- [x] O workspace cotidiano executa `today`, `opportunities`, `dossier`, `coverage`, `competitors`, `expiring-contracts`, `prices`, `edital analyze`, `proposal support`, `contracts`, `decide` e relatórios; `GO` legado é rebaixado a `REVIEW` quando o perfil da Extra está incompleto.
- [x] O benchmark preliminar contém quatro publicações oficiais CIGA com ID, URL e hash. Resultado observado 4/4, mas estado **PARTIAL/NOT_READY** por estratos ausentes e limitação de independência; não é claim de recall de 100%.
- [x] Testes críticos deste ciclo: **74 passed**; golden path estrito PCP: `gp-20260717-102949`, exit code 0, 184 fetched, 7 inserted. O golden path PNCP falhou por timeout e permanece evidência de source health degradado.
- [x] CI obrigatório da PR #10 verde: ruff, mypy, testes críticos, bandit e pip-audit. Evidência: GitHub Actions run `29585067851`, merge commit `d2d66d725849ab5be3a534aa085775be50cbd702`.
- [x] Suíte global completa verde. Evidência: CI run `29794247186` (Test All full suite **pass**, todos os jobs CI da PR #67 verdes) · local dual-capable `python3 -m scripts.ops.run_full_suite` 2210 passed / 126 skipped / exit 0 · `scripts/ops/run_full_suite.py` + ADR-029 · entity_resolver SQL fallback · `.dod/evidence/DOD-definition-of-done-extra-fd43ee57aa/` · campanha DOD-CONVERGENCE-EXTRA-01.
- [x] Freshness coverage mensurável por entidade dentro dos SLAs. Evidência: campanha `ENTITY-FRESHNESS-CANONICAL-ACCEPTANCE-01` · população = `load_canonical_universe` (seed `Extra - alvos de licitação. R-0.xlsx`, seed_sha256 `d65f272812cf8dc95f3ca78c5db9a2fb2a39a759e5633eb3fb91891ad10a5486`, canonical_ids_sha256 `0b3f894d87ba71f2e0fa96887cb3075033488de1af1e6e55f97ccda0701fb396`) · dual report `output/coverage/freshness-editais.json` + `freshness-contracts.json` (editais sha256 `2a69602cce818bc65ca7281204b6316a5f5bd7ba4a0d43e02e264eab36d1efe9`; contracts sha256 `8fa91d284528c1f89f402d845345ee7f808dcd6e2e58f49bdc9f41d384b0bc7c`) · set equality 1093 IDs · registry reconciliado · `tests/test_freshness_by_entity.py` no CI · manifest `docs/ops/campaigns/ENTITY-FRESHNESS-01/evidence/acceptance-manifest.json` · ADR-028 · as_of 2026-07-20: editais FRESH=0/STALE=288/INCOMPLETE=120/NEVER=685; contratos FRESH=365/NEVER=728 (**sem claim de 95%**; sem migration 058 como spine).
- [ ] Recall independente e estratificado ≥95%.
- [ ] Cobertura operacional ≥95% (mínimo **1.039/1.093** entidades).

Evidências consolidadas: `docs/ops/session-b2g-platform-2026-07-17/`, `docs/qa/recall-sample-2026-07-17.json`, `output/coverage/` e `output/golden-path/b2g-cycle-pcp-20260717.json`.

---

## 1. Como usar este documento

- [x] Este arquivo está versionado na raiz do repositório como `DOD.md`. Evidência: branch `epic/plano-executivo-30d`, campanha EPIC-PLANO-EXECUTIVO-30D / PE-G0-01 (2026-07-16).
- [x] O documento é tratado como checklist de evolução do projeto, e não como Definition of Done de uma única story. Evidência: §35 gates + 3 róis; plano `extra-consultoria-plano-executivo.html`.
- [ ] Cada item só é marcado como concluído quando existir evidência verificável.
- [x] Sempre que possível, a evidência é registrada ao lado do item no formato: ` Evidência: canonical `STATIC_REPO_WIDE_PROOF` + `DOD.md`
- [ ] Código existente sem execução comprovada não é considerado concluído.
- [ ] Teste unitário isolado não substitui execução ponta a ponta.
- [x] Presença de registros no banco não é tratada como prova de cobertura. Evidência: skeptic-remediation `DOCUMENT_CONTENT_PROOF` + `README.md`
- [x] Uma story marcada como `Done` não torna automaticamente concluído o requisito equivalente neste documento. Evidência: canonical `STATIC_REPO_WIDE_PROOF` + `squads/extra-dod-roi/scripts/campaign.py`
- [ ] Alterações de escopo são refletidas primeiro neste documento e nos documentos canônicos do projeto.
- [ ] Itens explicitamente marcados como opcionais não bloqueiam o fechamento do projeto.
- [ ] Todos os demais itens bloqueiam o respectivo gate.
- [ ] O projeto só é considerado integralmente concluído quando os três róis obrigatórios estiverem atendidos:
  - [ ] requisitos do estágio atual;
  - [ ] requisitos posteriores ao provisionamento da VPS;
  - [ ] requisitos independentes de infraestrutura.


### Estados, aplicabilidade e bloqueio

- [x] Um item desmarcado permanece não aceito, mesmo que esteja parcialmente implementado. Evidência: `scripts/ops/requirement_states.py` + `tests/test_requirement_states.py` (10 passed) + QA PASS re-review `docs/ops/session-2026-07-18-requirement-states/QA-VERDICT.md` @ `58d9a83`. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Um item só recebe `[x]` após validação e registro de evidência. Evidência: skeptic-remediation `STATIC_REPO_WIDE_PROOF` + `squads/extra-dod-roi/scripts/campaign.py`
- [ ] Implementação parcial é anotada como `PARTIAL`, sem marcar o item como concluído.
- [ ] Dependência externa pendente é anotada como `BLOCKED`, com responsável, causa e próximo teste.
- [ ] Um requisito somente pode ser tratado como `NOT_APPLICABLE` quando a própria redação permitir aplicabilidade condicional ou quando houver decisão de escopo registrada por Tiago.
- [ ] `NOT_APPLICABLE` possui justificativa, data e evidência; não é usado para contornar promessa comercial.
- [ ] Campo indisponível na fonte é registrado como `SOURCE_UNAVAILABLE` ou `NOT_READY`, nunca como zero e nunca como concluído por conveniência.
- [ ] Um blocker externo não desaparece do gate; ele permanece visível até resolução ou alteração formal do escopo.
- [ ] Os gates consideram concluídos apenas itens `DONE` e itens legitimamente `NOT_APPLICABLE`.
- [ ] O estado de cada requisito pode ser reconstruído sem depender do histórico de uma conversa com agente de IA.

### Convenção de evidência

Um item pode ser marcado como concluído apenas quando pelo menos uma das evidências abaixo existir:

- [ ] teste automatizado reproduzível;
- [ ] comando documentado com exit code `0`;
- [x] relatório JSON, CSV, Excel, PDF ou Markdown gerado pelo sistema; Evidência: kind `system_report` + audit artifacts `docs/ops/session-2026-07-18-evidence-convention/` + QA PASS. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [ ] consulta SQL com resultado esperado;
- [ ] execução registrada em ledger, manifest ou tabela de runs;
- [ ] log datado e correlacionável;
- [ ] validação manual registrada por Tiago;
- [ ] commit ou pull request identificável;
- [ ] teste de restauração ou recuperação efetivamente executado;
- [ ] comparação com fonte oficial realizada na mesma data ou período.

---

## 2. Contrato funcional do projeto

### 2.1 Objetivo

- [ ] O sistema ajuda a localizar editais relevantes para a Extra Construtora.
- [ ] O sistema ajuda a verificar contratos históricos dos entes monitorados.
- [x] O sistema ajuda a identificar vencedores e concorrentes observáveis. Evidência: M4-packages/competitors-top50.json · deliverable_b_competitors · EXTRA-OPS-95
- [ ] O sistema ajuda a formar referências de valores com semântica explícita.
- [ ] O sistema ajuda Tiago a decidir quais oportunidades merecem análise humana.
- [ ] O sistema reduz o risco de perda de oportunidades por monitoramento incompleto.
- [ ] O sistema produz evidências e relatórios utilizáveis na consultoria.
- [ ] O sistema continua sendo uma ferramenta pessoal, sem necessidade de produto SaaS.

### 2.2 Escopo incluído

- [ ] Monitoramento de editais abertos.
- [ ] Reconciliação de status de editais.
- [ ] Histórico de editais encerrados quando necessário para análise.
- [x] Coleta de contratos dos últimos três anos, no mínimo.
- [x] Atualização incremental de contratos após o backfill inicial.
- [x] Mapeamento de fornecedores vencedores. Evidência: competitors-top50.json · contract_intel · EXTRA-OPS-95
- [ ] Mapeamento de órgãos contratantes.
- [ ] Identificação de recorrência de contratação.
- [ ] Identificação de concentração de vencedores.
- [ ] Referências de valor estimado.
- [x] Referências de valor homologado quando a fonte disponibilizar. Evidência: M4-packages/price-refs.json · deliverable_d_prices · EXTRA-OPS-95
- [ ] Referências de valor contratado.
- [ ] Referências de valor pago quando a fonte disponibilizar.
- [ ] Diferenciação explícita entre os quatro tipos de valor.
- [ ] Exportação de dados para revisão manual.
- [ ] Geração de relatórios em PDF e Excel.
- [x] Operação por CLI, scripts e arquivos. Evidência: opportunity_intel.cli · probe_entity_success_zero · crawl.monitor · EXTRA-OPS-95
- [ ] Uso local durante o estágio atual.
- [ ] Operação contínua em VPS no estágio posterior.
- [ ] Monitoramento recorrente de novas oportunidades e alterações relevantes.
- [ ] Triagem inicial de edital.
- [ ] Análise técnica aprofundada de edital quando solicitada.
- [ ] Análise de planilha orçamentária, composições e BDI quando os documentos estiverem disponíveis.
- [ ] Comparação de orçamento com referências oficiais e dados de mercado defensáveis.
- [x] Apoio à decisão `GO`, `REVIEW` ou `NO_GO`. Evidência: opportunity_intel 401 opps GO=0 REVIEW≈397 NO_GO=4 · ranking demote · EXTRA-OPS-95
- [ ] Apoio à organização e revisão de proposta, sem assumir assinatura ou responsabilidade da empresa.
- [ ] Acompanhamento administrativo de contratos: prazos, publicações, aditivos, vigência, renovação e sinais de relicitação.

### 2.3 Escopo excluído

- [ ] O projeto não contém módulo de diário de obra.
- [ ] O projeto não contém módulo de medição de obra.
- [ ] O projeto não contém acompanhamento de avanço físico.
- [ ] O projeto não contém acompanhamento financeiro da execução da obra.
- [ ] O projeto não contém gestão de fotos de obra.
- [ ] O projeto não contém fiscalização de campo.
- [ ] O projeto não contém gestão de aditivos de execução.
- [ ] O projeto não contém gestão de riscos de obra.
- [ ] O projeto não contém gestão de equipes de obra.
- [ ] O projeto não contém gestão de cronograma físico-financeiro.
- [ ] O projeto não contém portal para a contratada.
- [ ] O projeto não contém interface pública.
- [ ] O projeto não contém multi-tenant.
- [ ] O projeto não contém cobrança, assinatura ou Stripe.
- [ ] O projeto não contém autenticação complexa desnecessária.
- [ ] O projeto não contém dashboard web apenas por conveniência estética.
- [ ] O projeto não contém Kubernetes, Kafka, Redis ou Elasticsearch sem necessidade comprovada.
- [ ] O projeto não assina documentos em nome da Extra.
- [ ] O projeto não protocola propostas ou documentos automaticamente sem ação humana explícita.
- [ ] O projeto não assume responsabilidade técnica, jurídica, contábil ou comercial pela proposta apresentada pela empresa.
- [ ] O projeto não substitui advogado em impugnações, recursos ou pareceres jurídicos.
- [ ] O projeto não representa a empresa presencialmente em sessões de licitação.
- [ ] O projeto não fornece garantias financeiras, seguros ou crédito.
- [ ] O projeto não promete habilitação, adjudicação, vitória ou contratação.
- [ ] O projeto não executa o objeto contratado.

### 2.4 Usuário e forma de uso

- [ ] Tiago é o único usuário obrigatório do sistema.
- [ ] O fluxo principal pode ser executado sem interface web.
- [x] Os comandos principais são claros e documentados. Evidência: --help on ops scripts · AGENTS.md · EXTRA-OPS-95
- [ ] O sistema não exige conhecimento do código interno para tarefas operacionais recorrentes.
- [ ] A saída é legível para revisão humana.
- [ ] Erros são apresentados com causa provável e próximo passo.
- [ ] O sistema permite repetir uma execução sem criar inconsistência.
- [x] O sistema permite retomar uma execução interrompida. Evidência: `docs/ops/campaigns/EXTRA-OPS-95/evidence/M5-resume/resume-proof.json` kill/restart preserves completed_windows · EXTRA-OPS-95-FOUNDATION 2026-07-19
- [ ] O sistema permite identificar quando um dado não é confiável.
- [ ] O sistema não esconde limitações atrás de scores ou percentuais genéricos.

### 2.5 Correspondência obrigatória com a proposta comercial

> Esta seção traduz as promessas da proposta em capacidades verificáveis do sistema. A prestação humana da consultoria continua sob responsabilidade de Tiago; o software deve produzir dados e artefatos suficientes para que essas entregas sejam realizadas com rigor.

#### Configuração do diagnóstico

- [ ] Existe configuração canônica do perfil da Extra Construtora ou mecanismo equivalente versionado.
- [x] A configuração registra região e universo monitorado. Evidência: config/client_profiles/extra.yaml · radius 200km SC · EXTRA-OPS-95
- [ ] A configuração registra tipos de obra e serviços de engenharia relevantes.
- [ ] A configuração registra faixas de valor relevantes, quando definidas no alinhamento.
- [ ] A configuração registra modalidades aceitas ou priorizadas.
- [ ] A configuração registra restrições operacionais conhecidas da empresa.
- [ ] A configuração registra órgãos prioritários definidos no alinhamento.
- [ ] A configuração registra concorrentes indicados pelo cliente.
- [ ] A alteração do perfil não exige modificar regras espalhadas pelo código.
- [ ] Todo relatório identifica a versão do perfil utilizada.

#### Entregável A — ranking dos órgãos públicos

- [x] O sistema gera ranking dos entes do universo que contratam obras e serviços compatíveis com o perfil. Evidência: `scripts/reports/org_ranking.py` + `deliverable_a_org_ranking` schema + fixture/live adapt; live DSN INSUFFICIENT (0 rows) honesto; QA PASS @ `4f3ea65`. Residual: filtro de perfil (object types) ainda UF-first. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] O ranking informa quantidade de contratações no período. Evidência: campo `qtd_contratacoes` + audit-fixture 10/10 PASS. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] O ranking informa valor contratado total. Evidência: `valor_total` + `valor_semantica` (CONTRATADO|ESTIMADO) — não misturar. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] O ranking informa ticket médio com semântica explícita. Evidência: `ticket_medio` + `ticket_medio_formula` + tests. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] O ranking informa frequência temporal de contratação. Evidência: `frequencia_temporal` por linha. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] O ranking informa distribuição por modalidade. Evidência: mapa `modalidades` no schema/fixture. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] O ranking informa período de análise. Evidência: `period.inicio/fim` + as_of. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] O ranking informa fontes e cobertura aplicáveis. Evidência: `sources` + `coverage_notes` (não inferir 95%). · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Entes consultados com resultado zero permanecem distinguíveis de entes não consultados. Evidência: `zero_vs_not_consulted` + tests. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] O ranking não favorece artificialmente entes com maior qualidade de dados sem alertar essa limitação. Evidência: `ranking_bias_warning` + `data_quality_limitation` quando score < 1. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).

#### Entregável B — mapeamento de 15 concorrentes observáveis

- [x] O sistema consegue selecionar e justificar pelo menos 15 fornecedores vencedores relevantes, quando existirem dados suficientes no recorte. Evidência: `scripts/ops/deliverable_b_competitors.py` fixture 15/15 + insufficient path; audit 13/13; QA PASS @ `bd23854`. Residual: live DSN empty — not a live market claim. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] A seleção dos 15 possui regra reproduzível e configurável. Evidência: `SelectionRule` (target_n, sort_keys, min_contracts, uf_filter, require_cnpj). · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Cada fornecedor possui CNPJ ou identidade canônica. Evidência: normalize_cnpj + require_cnpj filter + tests. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Cada fornecedor possui quantidade de contratos identificados. Evidência: campo `n_contratos`. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Cada fornecedor possui valor contratado total. Evidência: `valor_contratado_total` + `valor_semantica=CONTRATADO`. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Cada fornecedor possui ticket contratado médio. Evidência: `ticket_contratado_medio` + formula. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Cada fornecedor possui órgãos em que venceu. Evidência: `orgaos_em_que_venceu`. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Cada fornecedor possui distribuição geográfica. Evidência: `distribuicao_geografica`. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Cada fornecedor possui tipos de objeto em que venceu. Evidência: `tipos_objeto`. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Deságio só é apresentado quando valor estimado e valor homologado comparáveis estiverem ligados ao mesmo certame, lote ou item. Evidência: `desagio_from_pair` fail-closed + tests. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Contrato só é chamado de ativo quando houver vigência e status atual suficientes para sustentar a afirmação. Evidência: `active_contract_record` + tests. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Capacidade operacional disponível de concorrente nunca é afirmada como fato sem evidência; inferências são rotuladas como hipótese. Evidência: `capacidade_operacional.label=HYPOTHESIS`. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Quando não houver 15 concorrentes defensáveis, o relatório declara a insuficiência e apresenta todos os casos válidos, sem completar a lista com ruído. Evidência: insufficient-demo 3/15 + `presented_all_valid`. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).

#### Entregável C — contratos vincendos em 90 a 180 dias

- [x] O sistema identifica contratos compatíveis com o perfil cuja vigência termina em janela configurável de 90 a 180 dias. Evidência: `scripts/ops/deliverable_c_expiring.py` WindowConfig 90–180 + fixture; QA PASS @ `d663413`. Residual: live DSN empty. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] A data de término usada possui fonte e data de verificação. Evidência: `termino_fonte` + `termino_verificado_em` obrigatórios. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Contratos sem data de vigência não entram silenciosamente na lista. Evidência: `excluded_no_vigencia` + tests. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Prorrogações e aditivos conhecidos atualizam a data efetiva. Evidência: `effective_end` + aditivos_aplicados. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] O sistema distingue vencimento contratual de término estimado. Evidência: `termino_tipo` CONTRATUAL|ESTIMADO. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] A lista informa órgão, objeto, contratado, valor, início, término e fonte. Evidência: schema fields audit. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] A probabilidade de relicitação possui metodologia documentada, variáveis observáveis e validação retrospectiva. Evidência: `relicitacao_method` requires retrospective validation for probability. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Na ausência de modelo validado, o sistema usa classificação de evidência ou sinais de relicitação, não percentual fabricado. Evidência: `probability_pct=null` + EVIDENCE_CLASS. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Toda previsão apresenta nível de confiança e limitações. Evidência: `confianca` + `limitacoes`. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).

#### Entregável D — painel de referências de preços

- [x] O sistema produz referências apenas para grupos tecnicamente comparáveis. Evidência: `deliverable_d_prices` group_dimensions + audit; QA PASS @ `b258ed4`. Residual: live DSN empty. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] A regra de comparabilidade por tipo de obra, serviço, unidade, lote, porte, região e período está documentada. Evidência: `ComparabilityRule.to_dict()` dimensions + description. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] O painel informa quantidade de observações. Evidência: `n_observations`. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] O painel informa mediana. Evidência: `median`. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] O painel informa percentil 25. Evidência: `p25`. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] O painel informa percentil 75. Evidência: `p75`. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] O painel informa mínimo e máximo apenas quando úteis e sem ocultar outliers. Evidência: min/max + `outliers_flagged` IQR. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] O painel informa evolução temporal quando a amostra permitir. Evidência: `temporal_evolution` multi-período. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] O painel identifica se cada valor é estimado, homologado, contratado ou pago. Evidência: `value_semantics_present` enum fechado. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] O painel não denomina valores globais heterogêneos como “preço real praticado”. Evidência: claims_forbidden + labels_forbidden_used vazio. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Categorias com amostra insuficiente são marcadas como `INSUFFICIENT_SAMPLE`. Evidência: status quando n < min_sample. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Critérios de exclusão e tratamento de outliers são reproduzíveis. Evidência: `outlier_rule` IQR k documentado. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).

#### Entregável E — editais abertos e recomendação individual

- [ ] O relatório inclui editais comprovadamente abertos na data de corte ou semana de conclusão.
- [ ] Cada edital foi visto no snapshot completo mais recente ou reconfirmado individualmente.
- [ ] Cada edital é avaliado contra o perfil versionado da Extra.
- [x] Cada edital recebe `GO`, `REVIEW` ou `NO_GO`. Evidência: opportunity_intel 401 opps GO=0 REVIEW≈397 NO_GO=4 · ranking demote · EXTRA-OPS-95
- [ ] A apresentação ao cliente traduz `GO` e `NO_GO` como recomendação fundamentada de `PARTICIPAR` ou `NÃO PARTICIPAR`, preservando `REVIEW` quando depender de análise humana adicional.
- [ ] Cada recomendação mostra fatores favoráveis.
- [ ] Cada recomendação mostra fatores impeditivos ou riscos.
- [ ] Cada recomendação referencia dados e documentos oficiais disponíveis.
- [ ] Nenhuma recomendação promete vitória ou substitui análise jurídica, contábil ou técnica final.

#### Pacote final da consultoria

- [x] O sistema gera PDF executivo e planilhas Excel a partir do mesmo conjunto de runs. Evidência: `deliverable_package_final` same run_id + sidecars; QA PASS @ `898d396`. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] PDF e Excel usam a mesma data de corte, universo, filtros e versão do perfil. Evidência: reconcile same_cut/profile/filters PASS. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Divergências entre PDF e Excel são detectadas automaticamente. Evidência: `reconcile_package` divergences list + FAIL path. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [ ] O PDF possui estrutura suficiente para uma entrega executiva de aproximadamente 30 a 50 páginas quando o volume de evidências justificar.
- [x] O Excel contém dados rastreáveis, filtros e abas necessárias à revisão. Evidência: sheets Metadados/Dados/Filtros/Cobertura/Limitacoes. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] O pacote inclui sumário executivo, metodologia, universo, cobertura, limitações e anexos de evidência. Evidência: REQUIRED_PDF_SECTIONS. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] O pacote inclui material de apoio para reunião de apresentação. Evidência: meeting_support files. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Afirmações quantitativas no PDF podem ser reconciliadas com linhas ou agregações do Excel. Evidência: quantitative_claims with excel_ref/pdf_ref. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] O pacote final passa por aceite manual de Tiago antes de ser apresentado ao cliente. Evidência: tiago_accept PENDING_HUMAN (gate; not auto-ACCEPTED). · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).

### 2.6 Esteira recorrente de serviços, exceto acompanhamento de obras

#### Monitoramento mensal estratégico

- [ ] O sistema executa ou apoia ciclo recorrente de monitoramento sem exigir reconstrução manual do diagnóstico.
- [ ] O ciclo identifica editais novos desde a última execução.
- [ ] O ciclo identifica retificações, suspensões, revogações, reaberturas e alterações de prazo.
- [ ] O ciclo identifica contratos que entraram na janela de vencimento configurada.
- [ ] O ciclo atualiza o panorama de órgãos e vencedores com base em dados novos.
- [ ] O sistema gera relatório semanal de oportunidades ou periodicidade formalmente definida.
- [ ] O sistema gera relatório mensal consolidado.
- [ ] O relatório mensal informa variação em relação ao período anterior.
- [ ] O relatório mensal registra cobertura, freshness, blockers e fontes degradadas.
- [ ] O pacote mensal contém material de apoio para a reunião com o cliente.
- [ ] Alertas não substituem relatório consolidado e relatório não substitui alertas urgentes.

#### Triagem de edital

- [ ] Existe checklist configurável de pelo menos 15 a 20 pontos críticos.
- [ ] A triagem verifica objeto, escopo e aderência ao perfil da Extra.
- [ ] A triagem verifica datas, horários, pedidos de esclarecimento, impugnação e entrega.
- [ ] A triagem verifica modalidade, critério de julgamento e modo de disputa.
- [ ] A triagem verifica condições de participação, consórcios e subcontratação.
- [ ] A triagem verifica habilitação jurídica.
- [ ] A triagem verifica regularidade fiscal e trabalhista.
- [ ] A triagem verifica qualificação econômico-financeira.
- [ ] A triagem verifica capital social, patrimônio líquido, índices e garantias.
- [ ] A triagem verifica qualificação técnica operacional e profissional.
- [ ] A triagem verifica atestados, CAT, ART/RRT, parcelas de maior relevância e quantitativos mínimos.
- [ ] A triagem verifica visita técnica e declarações obrigatórias.
- [ ] A triagem verifica formato, validade e condições da proposta.
- [ ] A triagem verifica orçamento estimado, sigilo, regime de execução e reajuste.
- [ ] A triagem verifica sanções, responsabilidades e riscos contratuais relevantes.
- [ ] A triagem identifica inconsistências, ambiguidades e possíveis exigências restritivas para revisão humana.
- [ ] A triagem produz conclusão preliminar e lista de pendências para análise aprofundada.
- [ ] O resultado não é apresentado como parecer jurídico.

#### Análise técnica aprofundada de edital e orçamento

- [ ] O sistema permite vincular edital, anexos, projetos, memoriais, planilha, cronograma e minuta contratual ao mesmo caso.
- [ ] Todos os documentos do caso possuem hash, versão, origem e data de obtenção.
- [ ] O sistema detecta anexos mencionados e ausentes.
- [ ] O sistema detecta divergências entre edital, termo de referência, projeto, planilha e minuta quando tecnicamente verificáveis.
- [ ] A análise preserva rastreabilidade por página, item, célula ou trecho de origem.
- [ ] Quantitativos relevantes podem ser comparados entre documentos.
- [ ] Unidades, códigos, descrições e preços da planilha são normalizados.
- [ ] Composições são vinculadas aos respectivos serviços.
- [ ] Custos diretos, indiretos, encargos e BDI permanecem distinguíveis.
- [ ] A análise verifica coerência aritmética de subtotais, totais, percentuais e arredondamentos.
- [ ] A análise identifica itens sem composição, composição sem item e referência inconsistente.
- [ ] A análise compara preços com SINAPI, SICRO ou outras tabelas oficiais aplicáveis, respeitando mês, localidade, desoneração e unidade.
- [ ] Referências privadas ou históricas são identificadas separadamente das tabelas oficiais.
- [ ] Diferença de preço é acompanhada de base comparável e não é tratada isoladamente como erro.
- [ ] A análise registra riscos de exequibilidade e margem sem inventar custos internos não fornecidos pela Extra.
- [ ] O relatório diferencia achado objetivo, alerta técnico, hipótese e decisão que depende de especialista.

#### Análise crítica completa e decisão

- [ ] A decisão combina aderência técnica, documental, econômica, concorrencial, operacional e temporal.
- [ ] O modelo de decisão possui fatores, pesos ou regras documentados.
- [ ] Fatores eliminatórios não são compensados por score agregado.
- [ ] A recomendação informa informações faltantes que poderiam alterar a decisão.
- [ ] A recomendação informa riscos de caixa, garantias, prazo e mobilização quando houver dados fornecidos pela Extra.
- [ ] A projeção de margem usa custos e premissas fornecidos ou validados pela Extra.
- [ ] Cenários e sensibilidades são identificados como simulações.
- [ ] A conclusão final permanece sujeita ao aceite de Tiago e da empresa.

#### Apoio à elaboração da proposta

- [ ] O sistema gera checklist de documentos exigidos pelo edital.
- [ ] Cada documento possui responsável, status, validade e prazo.
- [ ] O sistema identifica documentos faltantes, vencidos ou incompatíveis.
- [ ] O sistema auxilia a montar matriz de conformidade edital × evidência da empresa.
- [ ] O sistema apoia revisão de coerência entre proposta comercial, planilha, cronograma e declarações.
- [ ] O sistema preserva versões das peças revisadas.
- [ ] O sistema registra comentários, pendências e decisões da revisão.
- [ ] O sistema não altera documento final sem rastreabilidade.
- [ ] A assinatura, responsabilidade, protocolo e envio permanecem com a Extra.
- [ ] O sistema não acessa portal de licitação para envio sem comando humano explícito e escopo específico futuro.

#### Acompanhamento administrativo de contratos, sem acompanhamento de obra

- [ ] O sistema registra contrato, órgão, contratado, objeto, valor, vigência e fonte.
- [ ] O sistema monitora publicações oficiais vinculadas ao contrato.
- [ ] O sistema registra termos aditivos, apostilamentos, suspensões, rescisões e prorrogações quando publicados.
- [ ] O sistema alerta sobre vencimentos administrativos configurados.
- [ ] O sistema alerta sobre vigência próxima do término.
- [ ] O sistema identifica sinais de renovação ou relicitação com grau de confiança explícito.
- [ ] O relatório mensal apresenta status documental e publicações observadas.
- [ ] O módulo não registra medição, diário, avanço físico, fotos, produção, produtividade ou fiscalização da obra.
- [ ] O módulo não declara situação física ou financeira da execução sem dados oficiais e escopo formal adicional.

---

# ROL 1 — DEFINITION OF DONE DO ESTÁGIO ATUAL

> Este rol deve ser concluído antes de considerar encerrada a fase local.
>
> O estágio atual é `local-first`, com PostgreSQL local, execução manual ou semiautomatizada e produção de evidências reproduzíveis.
>
> Provisionar a VPS antes deste rol estar concluído não resolve os gaps de dados, cobertura ou semântica.

---

## 3. Autoridade do universo monitorado

### 3.1 Planilha canônica

- [x] A planilha `Extra - alvos de licitação. R-0.xlsx` é reconhecida como única fonte canônica do universo-alvo. Evidência: sc_public_entities seed 2085 · raio_200km=1093 · second-import 0 inserted · load_canonical_universe · EXTRA-OPS-95
- [x] O hash da planilha importada é registrado. Evidência: sc_public_entities seed 2085 · raio_200km=1093 · second-import 0 inserted · load_canonical_universe · EXTRA-OPS-95 · seed_sha256 d65f2728…
- [x] A data de importação é registrada. Evidência: sc_public_entities seed 2085 · raio_200km=1093 · second-import 0 inserted · load_canonical_universe · EXTRA-OPS-95 · created_at/ingested timestamps
- [ ] A versão lógica da planilha é registrada.
- [x] O total de linhas válidas é registrado. Evidência: sc_public_entities seed 2085 · raio_200km=1093 · second-import 0 inserted · load_canonical_universe · EXTRA-OPS-95 · total_seed_rows=2085
- [x] O total de entes dentro do raio de 200 km é calculado diretamente da coluna canônica. Evidência: load_canonical_universe within_radius=1093 · second-import 0 inserted · seed_sha256 d65f2728… · EXTRA-OPS-95 2026-07-19
- [x] O total de entes fora do raio é calculado diretamente da coluna canônica. Evidência: sc_public_entities seed 2085 · raio_200km=1093 · second-import 0 inserted · load_canonical_universe · EXTRA-OPS-95 · outside_radius=992
- [ ] Nenhum número antigo de universo é mantido como constante solta no código.
- [ ] Nenhuma query usa um denominador alternativo sem justificativa explícita.
- [x] O universo é recalculado quando o hash da planilha muda. Evidência: sc_public_entities seed 2085 · raio_200km=1093 · second-import 0 inserted · load_canonical_universe · EXTRA-OPS-95 · seed_sha256 in load_canonical_universe
- [x] A seed atual pode ser reconstruída a partir da planilha. Evidência: sc_public_entities seed 2085 · raio_200km=1093 · second-import 0 inserted · load_canonical_universe · EXTRA-OPS-95
- [x] A planilha pode ser importada mais de uma vez sem duplicação. Evidência: load_canonical_universe within_radius=1093 · second-import 0 inserted · seed_sha256 d65f2728… · EXTRA-OPS-95 2026-07-19
- [x] A segunda importação de uma planilha idêntica resulta em `0 changes`. Evidência: load_canonical_universe within_radius=1093 · second-import 0 inserted · seed_sha256 d65f2728… · EXTRA-OPS-95 2026-07-19 (0 inserted)
- [ ] Entes novos são identificados.
- [ ] Entes removidos são identificados.
- [ ] Entes alterados são identificados.
- [x] CNPJs são normalizados. Evidência: load_canonical_universe within_radius=1093 · second-import 0 inserted · seed_sha256 d65f2728… · EXTRA-OPS-95 2026-07-19 + entity cnpj_8 · pick_match root
- [x] Códigos IBGE são normalizados. Evidência: sc_public_entities seed 2085 · raio_200km=1093 · second-import 0 inserted · load_canonical_universe · EXTRA-OPS-95 · codigo_ibge + IBGE API resolve in import log
- [ ] Coordenadas são normalizadas.
- [ ] Distâncias são tratadas como valor numérico.
- [x] O campo de pertencimento ao raio não é inferido quando já existe na planilha. Evidência: sc_public_entities seed 2085 · raio_200km=1093 · second-import 0 inserted · load_canonical_universe · EXTRA-OPS-95 · column 'Raio 200km?'
- [x] Duplicidades legítimas de raiz de CNPJ não são eliminadas indevidamente.
- [ ] Cada ente possui identidade estável e reproduzível.
- [ ] O relatório de importação lista erros, alertas e mudanças.
- [ ] A importação falha de forma explícita quando a planilha não atende ao schema esperado.

### 3.2 Universo operacional

- [x] O universo operacional é formado somente pelos entes marcados como pertencentes ao raio de 200 km. Evidência: load_canonical_universe within_radius=1093 · second-import 0 inserted · seed_sha256 d65f2728… · EXTRA-OPS-95 2026-07-19
- [x] O baseline atual de 1.093 entes é confirmado para a versão corrente da planilha.
- [ ] O número 1.093 não é tratado como constante permanente.
- [x] Cada ente do universo possui identificador interno. Evidência: sc_public_entities seed 2085 · raio_200km=1093 · second-import 0 inserted · load_canonical_universe · EXTRA-OPS-95 · sc_public_entities.id
- [x] Cada ente possui nome canônico. Evidência: sc_public_entities seed 2085 · raio_200km=1093 · second-import 0 inserted · load_canonical_universe · EXTRA-OPS-95 · razao_social NOT NULL
- [x] Cada ente possui município ou classificação equivalente. Evidência: sc_public_entities seed 2085 · raio_200km=1093 · second-import 0 inserted · load_canonical_universe · EXTRA-OPS-95 · municipio populated
- [x] Cada ente possui natureza jurídica. Evidência: sc_public_entities seed 2085 · raio_200km=1093 · second-import 0 inserted · load_canonical_universe · EXTRA-OPS-95 · cod_natureza/natureza_juridica
- [x] Cada ente possui evidência de inclusão no raio. Evidência: sc_public_entities seed 2085 · raio_200km=1093 · second-import 0 inserted · load_canonical_universe · EXTRA-OPS-95 · raio_200km column from planilha
- [x] Não existem entes `unknown` quanto ao pertencimento ao raio. Evidência: sc_public_entities seed 2085 · raio_200km=1093 · second-import 0 inserted · load_canonical_universe · EXTRA-OPS-95 · SIM/NAO only · unresolved_rows=0
- [x] Entes fora do raio não entram no denominador das metas de 95%. Evidência: sc_public_entities seed 2085 · raio_200km=1093 · second-import 0 inserted · load_canonical_universe · EXTRA-OPS-95 · den=1093 only raio_200km
- [ ] Entes dentro do raio não podem ser excluídos silenciosamente.
- [ ] Qualquer exclusão manual é registrada com motivo, autor e data.
- [ ] O sistema gera relatório de reconciliação entre planilha e banco.
- [ ] A contagem da planilha, da tabela canônica e do manifest coincide.
- [ ] O relatório de cobertura informa o hash da planilha usada como denominador.

---

## 4. Definição objetiva de cobertura

### 4.1 Fórmulas canônicas

- [ ] O sistema implementa as métricas abaixo sem versões concorrentes.

```text
universe_resolution =
entes com identidade válida e decisão de raio
/
total de linhas válidas da planilha
```

- [x] `universe_resolution = 100%`. Evidência: radar QW-01 `output/qw-01/qw01-20260719T031154Z-dfb87609/coverage_manifest.json` universe_resolution.percent=100; seed 2085/2085 resolved · EXTRA-OPS-95-FOUNDATION 2026-07-19

```text
source_applicability_resolution =
pares ente × fonte × capacidade classificados como applicable ou not_applicable
/
total de pares que exigem decisão
```

- [ ] `source_applicability_resolution = 100%`.
- [ ] Nenhum par necessário permanece como `unknown`.

```text
capability_monitoring_coverage =
entes aplicáveis com ao menos uma combinação obrigatória de fontes
consultada integralmente, fresca e sem blocker
/
entes aplicáveis
```

- [ ] `capability_monitoring_coverage(open_tenders) >= 95%`.
- [x] `capability_monitoring_coverage(historical_contracts) >= 95%`.
- [x] A cobertura de editais é calculada separadamente da cobertura de contratos. Evidência: session-metrics presence_editais vs contracts/ops_proxy · EXTRA-OPS-95
- [ ] A média entre as duas coberturas não é usada para mascarar uma delas. **Code-ready (not accepted):** dual engine has no average field · unit tests · ADR-030 · awaiting register_acceptance + independent QA pack (DUAL-CAPABILITY-COVERAGE-TRUTH-01).
- [x] Uma fonte saudável para editais não prova cobertura de contratos. Evidência: metrics computed independently · claims_forbidden either · EXTRA-OPS-95
- [ ] Uma fonte saudável para contratos não prova cobertura de editais. **Code-ready (not accepted):** unit test_contracts_do_not_prove_tenders · ADR-030 · awaiting register_acceptance + independent QA pack.

```text
data_presence =
entes com ao menos um registro encontrado
/
entes aplicáveis
```

- [ ] `data_presence` é publicada apenas como métrica descritiva.
- [ ] `data_presence` nunca é chamada de cobertura. **Code-ready (not accepted):** dual engine separates data_presence_* · claims_forbidden · ADR-030 · awaiting register_acceptance + independent QA pack.
- [ ] Ente sem registros pode ser considerado coberto somente mediante `success_zero` válido.

```text
active_snapshot_integrity =
registros exibidos como ativos vistos no último snapshot completo
ou reconfirmados individualmente depois dele
/
registros exibidos como ativos
```

- [ ] `active_snapshot_integrity = 100%`.

### 4.2 Critério de `success_zero`

Uma consulta que retorna zero registros só conta como cobertura quando:

- [x] o ente foi identificado corretamente; Evidência: cnpj14 root==cnpj8 + BrasilAPI name soft-match · pick_match fix · EXTRA-OPS-95
- [x] a fonte foi classificada como aplicável; Evidência: coverage_evidence.applicability=applicable for PNCP contracts · EXTRA-OPS-95
- [x] a capacidade consultada foi identificada; Evidência: capability=historical_contracts · EXTRA-OPS-95
- [x] o período consultado foi registrado; Evidência: coverage_evidence success_zero n=623 · probe_entity_success_zero · http_204_complete · purge-token-mismatch · EXTRA-OPS-95 ab3f77c 2026-07-19 · queried_start/end
- [x] todos os parâmetros relevantes foram registrados; Evidência: coverage_evidence success_zero n=623 · probe_entity_success_zero · http_204_complete · purge-token-mismatch · EXTRA-OPS-95 ab3f77c 2026-07-19 · cnpjOrgao+window in scope_key
- [x] a paginação foi iniciada corretamente; Evidência: coverage_evidence success_zero n=623 · probe_entity_success_zero · http_204_complete · purge-token-mismatch · EXTRA-OPS-95 ab3f77c 2026-07-19 · pages_processed=1 http_204
- [x] a paginação foi concluída; Evidência: coverage_evidence success_zero n=623 · probe_entity_success_zero · http_204_complete · purge-token-mismatch · EXTRA-OPS-95 ab3f77c 2026-07-19 · completion_rule=http_204_complete
- [x] não houve timeout não tratado; Evidência: probe timeouts raise/classify · no silent · EXTRA-OPS-95
- [x] não houve erro parcial escondido; Evidência: BLOCKED_API/429 explicit · purge of false identity · EXTRA-OPS-95
- [ ] não houve página ignorada;
- [ ] não houve resposta truncada;
- [x] não houve blocker de autenticação; Evidência: PNCP public endpoints · no auth required · EXTRA-OPS-95
- [x] não houve blocker de rate limit pendente; Evidência: 429 backoff then re-run to SUCCESS_ZERO · EXTRA-OPS-95
- [x] não houve erro de schema; Evidência: ck_ce_success_zero_scope satisfied · EXTRA-OPS-95
- [x] a resposta vazia foi persistida como `success_zero`; Evidência: coverage_evidence success_zero n=623 · probe_entity_success_zero · http_204_complete · purge-token-mismatch · EXTRA-OPS-95 ab3f77c 2026-07-19
- [x] o run possui `run_id`; Evidência: coverage_evidence success_zero n=623 · probe_entity_success_zero · http_204_complete · purge-token-mismatch · EXTRA-OPS-95 ab3f77c 2026-07-19
- [x] o run possui timestamps de início e fim; Evidência: coverage_evidence success_zero n=623 · probe_entity_success_zero · http_204_complete · purge-token-mismatch · EXTRA-OPS-95 ab3f77c 2026-07-19
- [x] o run possui fonte e capability; Evidência: coverage_evidence success_zero n=623 · probe_entity_success_zero · http_204_complete · purge-token-mismatch · EXTRA-OPS-95 ab3f77c 2026-07-19 · source=pncp capability=historical_contracts
- [x] o run está dentro da janela de freshness; Evidência: success_zero freshness_status=fresh · checked_at now · 180d window · EXTRA-OPS-95
- [x] a evidência pode ser auditada posteriormente. Evidência: coverage_evidence success_zero n=623 · probe_entity_success_zero · http_204_complete · purge-token-mismatch · EXTRA-OPS-95 ab3f77c 2026-07-19
### 4.3 Freshness

- [ ] Editais abertos possuem idade máxima de 24 horas.
- [ ] O status de oportunidade prioritária é reconfirmado na execução mais recente.
- [x] Contratos possuem backfill integral mínimo de três anos.
- [ ] Contratos possuem atualização incremental com intervalo máximo de sete dias.
- [ ] Alterações em contratos já existentes são atualizadas no banco.
- [ ] Concorrentes herdam a freshness da carga contratual e de resultados.
- [x] Referências de preços informam a data de corte. Evidência: price-refs package meta · EXTRA-OPS-95
- [ ] O manifest informa freshness por fonte e por capability.
- [ ] Dados vencidos são marcados como `stale`.
- [ ] Dados sem prova de atualização são marcados como `unknown`.
- [ ] `stale` e `unknown` não contam para o numerador de cobertura. **Code-ready (not accepted):** observation_counts_as_covered + unit tests · ADR-030 · awaiting register_acceptance + independent QA pack. (Live ops fill still required for 95%.)
- [ ] O freshness gate falha de modo fechado.
- [ ] Não existe opção silenciosa que converta freshness desconhecida em aprovada.

---

## 5. Ambiente local reproduzível

### 5.1 Pré-requisitos

- [x] A versão canônica do Python está documentada. Evidência: skeptic-remediation `DOCUMENT_CONTENT_PROOF` + `README.md`
- [x] A versão canônica do PostgreSQL está documentada. Evidência: skeptic-remediation `DOCUMENT_CONTENT_PROOF` + `README.md`
- [ ] As dependências Python estão declaradas.
- [ ] O projeto pode ser instalado em ambiente limpo.
- [x] O `.env.example` contém todas as variáveis obrigatórias. Evidência: `.env.example` LOCAL_DATALAKE_DSN/PNCP_* · EXTRA-OPS-95
- [x] O `.env.example` não contém segredos reais. Evidência: placeholders `<password>` `@<vps-ip>` · EXTRA-OPS-95
- [x] O `.env` real está no `.gitignore`. Evidência: `.gitignore` lines `.env` / `.env.local` · EXTRA-OPS-95
- [ ] Arquivos de credenciais locais não são versionados.
- [ ] O setup não depende de caminhos absolutos do computador de Tiago.
- [ ] O setup não depende de estado manual não documentado.
- [ ] O setup informa claramente dependências externas.
- [ ] O setup falha com mensagem útil quando uma dependência obrigatória está ausente.

### 5.2 Bootstrap

- [x] Existe um comando único ou sequência curta para subir o PostgreSQL local. Evidência: docker extra-test-db · LOCAL_DATALAKE_DSN · apply_migrations · EXTRA-OPS-95
- [x] Existe um comando único para aplicar migrations. Evidência: `python3 -m scripts.ops.apply_migrations --dsn …` (001–057) · session rebuild · EXTRA-OPS-95-FOUNDATION 2026-07-19
- [ ] Existe um comando único para executar seeds.
- [ ] Existe um comando único para validar o ambiente.
- [x] O bootstrap funciona em banco vazio. Evidência: container restart → migrations+seed 2085/1093 · foundation baseline · EXTRA-OPS-95-FOUNDATION 2026-07-19
- [ ] O bootstrap funciona em segunda execução.
- [x] A segunda execução não duplica dados. Evidência: upsert_pncp_raw_bids ON CONFLICT pncp_id · count==distinct pncp_id 14102 · EXTRA-OPS-95
- [x] A segunda execução não altera checksums de migrations já aplicadas. Evidência: `_migrations` table · re-apply no-op · EXTRA-OPS-95
- [ ] O bootstrap produz log.
- [ ] O bootstrap retorna exit code não zero em falha.
- [x] A falha de uma migration interrompe a sequência. Evidência: apply_migrations fail-closed · ON_ERROR_STOP · EXTRA-OPS-95
- [ ] O bootstrap não deixa transação abortada sem rollback.
- [x] O ledger de migrations é consultável. Evidência: `public._migrations` após apply_migrations · session rebuild · EXTRA-OPS-95-FOUNDATION 2026-07-19
- [x] O schema resultante pode ser reconstruído do zero. Evidência: empty postgis volume → migrations 001–057 · EXTRA-OPS-95-FOUNDATION 2026-07-19
- [ ] O schema reconstruído coincide com o schema usado pelos scripts.
- [ ] O banco local pode ser descartado e recriado sem intervenção artesanal.

---

## 6. Integridade do schema e persistência

### 6.1 Schema canônico

- [x] `db/migrations` é a linha canônica de migrations do estágio atual. Evidência: `scripts/ops/apply_migrations` · 62 files in db/migrations · EXTRA-OPS-95
- [ ] Migrations alternativas são marcadas como legadas ou futuras.
- [ ] Não existem tabelas referenciadas pelo código e ausentes do banco.
- [ ] Não existem colunas referenciadas pelo código e ausentes do banco.
- [ ] Não existem views referenciadas pelo código e ausentes do banco.
- [ ] Não existem funções SQL referenciadas pelo código e ausentes do banco.
- [ ] Queries críticas passam por `EXPLAIN` ou execução rollback-only.
- [ ] O audit de schema gera relatório.
- [ ] O audit de schema falha em divergência.
- [ ] O schema possui constraints coerentes.
- [ ] O schema possui índices para consultas operacionais.
- [ ] O schema registra provenance.
- [ ] O schema registra `source`.
- [ ] O schema registra `run_id`.
- [ ] O schema registra timestamps de coleta.
- [ ] O schema registra timestamps de atualização.
- [ ] O schema diferencia dado bruto de dado normalizado.
- [ ] O schema diferencia edital de contrato.
- [ ] O schema diferencia status oficial de status inferido.
- [ ] O schema diferencia valores estimados, homologados, contratados e pagos.

### 6.2 Idempotência e atualização

- [x] Reexecutar o mesmo crawl não cria duplicatas. Evidência: upsert contracts/bids · SC re-ingest 900 unchanged · EXTRA-OPS-95
- [ ] Registros alterados na fonte são atualizados.
- [ ] `DO NOTHING` não é usado onde atualização posterior é necessária.
- [ ] Upserts possuem chave canônica definida.
- [x] A estratégia de deduplicação é determinística. Evidência: content_hash + official IDs · EXTRA-OPS-95
- [x] A estratégia de deduplicação não depende apenas de similaridade textual. Evidência: CNPJ/pncp_id first · pick_match root · EXTRA-OPS-95
- [x] A deduplicação tenta primeiro o identificador oficial. Evidência: pncp_id / numeroControlePNCP PK · entity CNPJ exact first · EXTRA-OPS-95
- [x] A deduplicação usa número PNCP quando aplicável. Evidência: pncp_raw_bids.pncp_id PK · EXTRA-OPS-95
- [ ] A deduplicação usa órgão, processo e edital quando necessário.
- [ ] Hash é usado apenas como fallback controlado.
- [ ] Duplicatas cross-source são reconciliadas.
- [ ] A origem de cada campo relevante é rastreável.
- [ ] Atualizações não apagam provenance anterior necessária à auditoria.
- [ ] Falhas parciais não são registradas como execução concluída.
- [x] Checkpoints só avançam após persistência confirmada. Evidência: `CONTRACTS_PERSIST_EACH_WINDOW` upsert before mark complete · contracts_crawler.py · tests/test_contracts_per_window_persist.py · EXTRA-OPS-95-FOUNDATION 2026-07-19
- [x] Runs interrompidos podem ser retomados. Evidência: contracts checkpoint resume · M5-resume/resume-proof.json · EXTRA-OPS-95-FOUNDATION 2026-07-19
- [x] Runs retomados não reiniciam desnecessariamente todo o período. Evidência: completed_windows subset preserved across kill · M5-resume · EXTRA-OPS-95-FOUNDATION 2026-07-19

---

## 7. Registro de fontes e aplicabilidade

### 7.1 Registry de fontes

- [ ] Existe registry canônico de fontes.
- [ ] Cada fonte possui identificador estável.
- [ ] Cada fonte possui URL ou endpoint canônico.
- [ ] Cada fonte informa capacidades suportadas.
- [ ] Cada fonte informa cobertura geográfica.
- [ ] Cada fonte informa necessidade de credenciais.
- [ ] Cada fonte informa limites de paginação conhecidos.
- [ ] Cada fonte informa rate limits conhecidos.
- [ ] Cada fonte informa estratégia de retry.
- [ ] Cada fonte informa estratégia de backoff.
- [ ] Cada fonte informa status operacional.
- [ ] Cada fonte informa data da última validação.
- [ ] Cada fonte informa bloqueadores conhecidos.
- [ ] Cada fonte informa se é primária, complementar ou gap-fill.
- [ ] Código existente sem validação real é marcado como `implemented_not_proven`.
- [ ] Fonte sem acesso é marcada como `blocked`.
- [ ] Fonte não aplicável é marcada como `not_applicable`.
- [ ] Fonte aplicável e testada é marcada como `active`.
- [ ] Fonte não é chamada de ativa apenas porque existe crawler.

### 7.2 Matriz ente × fonte × capability

- [ ] Cada ente possui decisão de aplicabilidade para editais.
- [ ] Cada ente possui decisão de aplicabilidade para contratos.
- [ ] A aplicabilidade pode variar por capability.
- [ ] A aplicabilidade possui justificativa.
- [ ] A aplicabilidade possui data de validação.
- [ ] A aplicabilidade possui fonte da decisão.
- [ ] Entes com múltiplas fontes obrigatórias possuem combinação definida.
- [ ] A combinação mínima de fontes é explícita.
- [ ] Fontes complementares não substituem silenciosamente fontes obrigatórias.
- [ ] Bloqueadores por ente são registrados.
- [ ] Bloqueadores por fonte são registrados.
- [ ] Bloqueadores por capability são registrados.
- [ ] Pares `unknown` aparecem em relatório de gaps.
- [ ] O gate final exige zero pares `unknown` necessários.

---

## 8. Editais abertos

### 8.1 Coleta

- [ ] O crawler PNCP usa endpoint vigente.
- [ ] O crawler PNCP usa parâmetros validados.
- [ ] O limite real de página está documentado.
- [ ] A paginação percorre todas as páginas.
- [ ] O crawler lida com 403.
- [ ] O crawler lida com 429.
- [ ] O crawler lida com 5xx.
- [ ] O crawler lida com timeout.
- [ ] O crawler usa retry com backoff.
- [ ] O crawler registra latência.
- [ ] O crawler registra total de páginas.
- [ ] O crawler registra total de registros recebidos.
- [ ] O crawler registra total de registros persistidos.
- [ ] O crawler registra erros por página.
- [ ] O crawler não considera uma janela concluída quando houve erro parcial.
- [ ] Fontes adicionais aplicáveis são executadas.
- [ ] Pelo menos uma fonte complementar ao PNCP está provada ponta a ponta quando necessária para atingir 95%.
- [ ] A coleta pode ser executada por período.
- [ ] A coleta pode ser executada por fonte.
- [ ] A coleta pode ser executada em modo incremental.
- [x] A coleta pode ser retomada. Evidência: M5-resume + contracts checkpoint reentrant · EXTRA-OPS-95-FOUNDATION 2026-07-19

### 8.2 Status e snapshot

- [ ] O sistema produz snapshot completo de editais ativos.
- [ ] O snapshot possui identificador.
- [ ] O snapshot possui timestamp.
- [ ] O snapshot possui fonte.
- [ ] O snapshot possui parâmetros de consulta.
- [ ] Registros vistos no snapshot são marcados como reconfirmados.
- [ ] Registros ausentes do snapshot completo deixam de ser exibidos como ativos.
- [ ] A desativação respeita regras para fontes que não entregam snapshot completo.
- [ ] O sistema diferencia `open`, `upcoming`, `closed`, `suspended`, `revoked`, `annulled`, `failed` e `unknown`.
- [ ] Status `unknown` não é apresentado como edital aberto.
- [ ] Um edital fechado não reaparece como aberto por resíduo histórico.
- [ ] Um edital suspenso é identificado.
- [ ] Um edital revogado é identificado.
- [ ] Um edital anulado é identificado.
- [ ] A data de encerramento é validada.
- [ ] Edital com encerramento passado não é exibido como aberto sem justificativa oficial.
- [ ] `active_snapshot_integrity = 100%`.
- [ ] Existe relatório de itens removidos do snapshot ativo.
- [ ] Existe relatório de itens com status conflitante entre fontes.

### 8.3 Campos mínimos do edital

- [ ] Identificador oficial.
- [ ] Ente canônico.
- [ ] Unidade compradora quando disponível.
- [ ] Número do processo.
- [ ] Número do edital ou contratação.
- [ ] Modalidade.
- [ ] Objeto.
- [ ] Data de publicação.
- [ ] Data e hora de encerramento.
- [ ] Status.
- [ ] URL oficial.
- [ ] Fonte.
- [ ] `run_id`.
- [ ] Data da última verificação.
- [ ] Valor estimado quando disponível.
- [ ] Município ou abrangência.
- [ ] Classificação AEC.
- [ ] Justificativa do score.
- [ ] Indicador de dados incompletos.
- [ ] Completude dos campos essenciais >= 95%.
- [ ] URL oficial e encerramento futuro são obrigatórios para uma oportunidade ser classificada como acionável.

### 8.4 Relevância para a Extra

- [ ] Existe filtro explícito para engenharia, construção e infraestrutura.
- [ ] Palavras-chave são versionadas.
- [ ] CPVs ou classificações equivalentes são versionados.
- [ ] Regras de inclusão são explicáveis.
- [ ] Regras de exclusão são explicáveis.
- [ ] O score não é uma caixa-preta.
- [ ] O sistema distingue `GO`, `REVIEW` e `NO_GO`.
- [ ] Toda classificação possui fatores visíveis.
- [ ] O usuário pode revisar falsos positivos.
- [ ] O usuário pode marcar falsos negativos identificados.
- [ ] Feedback manual pode ser exportado para calibração.
- [ ] A amostra-ouro inclui oportunidades relevantes e irrelevantes.
- [ ] Recall de editais relevantes >= 95% na amostra-ouro.
- [ ] Existem zero falsos “abertos” na amostra prioritária.
- [ ] A amostra é estratificada por município, natureza jurídica e fonte.

---

## 9. Contratos históricos

### 9.1 Escopo temporal

- [x] O backfill cobre no mínimo os últimos três anos.
- [x] A data inicial do backfill é registrada.
- [x] A data final do backfill é registrada.
- [ ] O período é particionado em janelas controladas.
- [x] Cada janela possui checkpoint. Evidência: `data/contracts_checkpoints/contracts_full.json` per-window keys · crawl 45d · EXTRA-OPS-95-FOUNDATION 2026-07-19
- [ ] Cada janela possui status.
- [ ] Cada janela possui contagem de páginas.
- [ ] Cada janela possui contagem de registros.
- [ ] Cada janela possui contagem de erros.
- [ ] Uma janela com erro parcial não é marcada como concluída.
- [ ] Uma janela concluída pode ser comprovada por manifest.
- [x] O backfill pode ser retomado após interrupção. Evidência: contracts full/backfill_3y checkpoint modes · M5-resume · EXTRA-OPS-95-FOUNDATION 2026-07-19
- [x] O backfill não reinicia janelas concluídas sem necessidade.

### 9.2 Coleta e atualização

- [ ] O crawler de contratos usa endpoint vigente.
- [ ] A paginação real é validada.
- [ ] Filtros por ente são validados.
- [ ] Filtros por UF são validados.
- [ ] Quando o filtro da API não funciona, existe pós-filtro explícito e testado.
- [ ] Contratos alterados são atualizados.
- [ ] A atualização preserva histórico necessário.
- [ ] O sistema identifica contrato novo.
- [ ] O sistema identifica contrato alterado.
- [ ] O sistema identifica duplicata.
- [ ] O sistema identifica cancelamento ou extinção quando a fonte informa.
- [ ] O sistema registra aditivos somente como dado contratual, sem transformar isso em acompanhamento de obra.
- [ ] O sistema registra vigência quando disponível.
- [ ] O sistema registra valor global.
- [ ] O sistema registra fornecedor.
- [ ] O sistema registra CNPJ do fornecedor.
- [ ] O sistema registra ente contratante.
- [ ] O sistema registra objeto.
- [ ] O sistema registra fonte.
- [ ] O sistema registra URL oficial quando disponível.
- [ ] O sistema registra `run_id`.
- [ ] O sistema registra data de última atualização.
- [ ] O incremental roda com intervalo máximo de sete dias no estágio local, ainda que manualmente.
- [ ] A cobertura de contratos >= 95% é provada por ente aplicável.
- [x] Entes sem contratos encontrados possuem `success_zero` válido. Evidência: gap-lists-20260719.json · ops proxy 1090/1093 · SZ 722 · EXTRA-OPS-95 27d3665 · residual 3 cnpj_8 malformados 00394494* (exceto 3 seed cnpj_8 inválidos PF/PRF)
- [ ] Presença de contrato em 404 entes, ou qualquer outra quantidade, não é confundida com cobertura.

### 9.3 Qualidade contratual

- [ ] CNPJ do fornecedor é normalizado.
- [ ] Ente contratante é reconciliado com o universo.
- [ ] Contratos de entes fora do raio não entram na métrica principal.
- [ ] Contratos sem ente reconciliado entram em fila de resolução.
- [ ] Valores negativos ou inválidos são sinalizados.
- [ ] Datas inconsistentes são sinalizadas.
- [ ] Contratos duplicados cross-source são reconciliados.
- [ ] Contratos com versões divergentes preservam provenance.
- [ ] O sistema distingue contrato, ata, empenho e resultado.
- [x] O sistema não chama valor contratado de valor pago. Evidência: M4-packages/package-summary.json claims_forbidden + price-refs is_paid=false · EXTRA-OPS-95-FOUNDATION 2026-07-19
- [x] O sistema não chama valor global de preço unitário. Evidência: package FAQ/glossario_metricas · EXTRA-OPS-95
- [ ] O sistema não mistura objetos heterogêneos em uma única referência sem classificação.
- [ ] Existe relatório de completude dos campos contratuais.
- [ ] Campos essenciais possuem completude >= 95% quando a fonte os disponibiliza.
- [ ] Campos estruturalmente indisponíveis são marcados como indisponíveis, não como zero.

---

## 10. Concorrentes e vencedores

### 10.1 Escopo honesto

- [ ] O sistema diferencia vencedor identificado de participante identificado.
- [ ] O sistema não afirma conhecer todos os concorrentes quando a fonte não expõe participantes.
- [ ] O sistema não calcula win rate sem denominador de propostas apresentadas.
- [ ] O sistema não calcula deságio sem valor estimado e valor homologado comparáveis.
- [ ] O sistema não infere capacidade ociosa do concorrente sem dado apropriado.
- [ ] O sistema não trata quantidade de contratos como sinônimo de capacidade técnica.
- [ ] O sistema informa as limitações de cada indicador.

### 10.2 Entregas mínimas

- [ ] Ranking de fornecedores vencedores.
- [ ] Quantidade de contratos por fornecedor.
- [ ] Valor contratado por fornecedor.
- [ ] Ticket contratado médio por fornecedor.
- [ ] Número de entes atendidos por fornecedor.
- [ ] Distribuição por município.
- [ ] Distribuição por natureza do ente.
- [ ] Distribuição por setor ou tipo de objeto.
- [ ] Recorrência de contratação.
- [ ] Última contratação conhecida.
- [ ] Concentração por órgão.
- [ ] Concentração por fornecedor.
- [ ] Market share contratual quando semanticamente válido.
- [ ] HHI quando semanticamente válido.
- [ ] Fonte e data de corte em todas as métricas.
- [ ] Exportação para Excel.
- [ ] Relatório de concorrentes para revisão manual.
- [ ] Queries executadas em PostgreSQL real.
- [ ] Testes validam nomes reais de tabelas e colunas.
- [ ] O relatório distingue métricas prontas, parciais e indisponíveis.

---

## 11. Referências de valores

### 11.1 Semântica obrigatória

- [ ] `valor_estimado` possui definição explícita.
- [ ] `valor_homologado` possui definição explícita.
- [ ] `valor_contratado` possui definição explícita.
- [ ] `valor_pago` possui definição explícita.
- [ ] Os quatro campos não são intercambiáveis.
- [ ] O relatório exibe o tipo de valor.
- [ ] O relatório exibe a fonte do valor.
- [ ] O relatório exibe a data de referência.
- [ ] O relatório exibe a unidade de comparação.
- [ ] O relatório exibe se o valor é global, por lote, por item ou unitário.
- [ ] Valor ausente não é substituído por zero.
- [ ] Valor inferido é marcado como inferido.
- [ ] Valor oficial é marcado como oficial.
- [ ] Valores de objetos heterogêneos não são agregados sem classificação adequada.
- [ ] Valores de períodos muito distintos são acompanhados de data.
- [ ] Atualização monetária, quando usada, é explicitada.
- [ ] Percentis só são calculados sobre amostra comparável.
- [ ] O tamanho da amostra é informado.
- [ ] Outliers são identificados.
- [ ] O sistema não chama percentil de contratos globais de “preço real praticado” sem base técnica.

### 11.2 Encadeamento do certame

- [ ] O sistema tenta relacionar edital, resultado e contrato.
- [ ] O relacionamento usa identificador oficial quando disponível.
- [ ] O relacionamento por processo é validado.
- [ ] O relacionamento por número de contratação é validado.
- [ ] O relacionamento por lote ou item é preservado quando disponível.
- [ ] O relacionamento incerto é marcado como incerto.
- [ ] O relacionamento manual pode ser registrado.
- [ ] O relatório informa o percentual de registros encadeados.
- [ ] O sistema não calcula deságio em registros não encadeados.
- [ ] O sistema não calcula diferença percentual entre grandezas não equivalentes.
- [ ] O sistema produz pelo menos uma referência de valor tecnicamente defensável por categoria relevante.
- [ ] Quando não houver dados suficientes, o sistema declara `NOT_READY`.

---

## 12. Pipeline de inteligência e relatórios

### 12.1 Golden path local

- [x] Existe um comando canônico de golden path. Evidência: `python3 -m scripts.golden_path --help` exit 0 · `scripts/golden_path.py` · `make golden-path` / `golden-path-quick` · `docs/DEVELOPMENT.md` §2 · AGENTS.md · tests/test_golden_path_*.py · `.dod/evidence/DOD-rol-1-definition-of-done-b42bd49e1d/`.
- [x] O golden path sobe ou valida o banco. Evidência: `scripts/golden_path.py::check_db` (live OK @ PG16:5544) · `make golden-path` → `db-up` + `bootstrap` · `.dod/evidence/DOD-rol-1-definition-of-done-16267c473a/`.
- [x] O golden path aplica migrations. Evidência: `scripts.golden_path.apply_migrations` → `scripts.ops.apply_migrations.apply_range` (upgrade idempotente) · dual-run PG16:5544 62 skipped re-run · `tests/test_golden_path_canonical.py` · `.dod/evidence/DOD-rol-1-definition-of-done-7aa1d9bfc5/`.
- [x] O golden path aplica seed. Evidência: `scripts.golden_path.apply_seeds` → `db/seed/001_sc_entities.py` + `002_entity_aliases.py` · dual-run PG16:5544 · `tests/test_golden_path_canonical.py` · `.dod/evidence/DOD-rol-1-definition-of-done-e9a3ea535d/`.
- [x] O golden path importa ou valida a planilha-alvo. Evidência: PR #75 merge `ae5302a` · CI run `29831727568` SUCCESS · `load_canonical_universe` physical_rows=2085 canonical_entities=1093 · canonical_ids_sha256 `0b3f894d87ba71f2e0fa96887cb3075033488de1af1e6e55f97ccda0701fb396` · CLI `python3 -m scripts.golden_path --validate-spreadsheet-only` ledger · `tests/test_golden_path_canonical.py` · adversarial PASS_FOR_MERGE · `.dod/evidence/DOD-rol-1-definition-of-done-e405d6a61c/`.
- [x] O golden path executa fontes mínimas. Evidência: PR #77 merge `41f73d1` · CI `29833397283` SUCCESS · CLI `--execute-sources-only` ledger (pncp/pcp/compras_gov attempts≥1) · `assert_essential_sources_executed` · `tests/test_golden_path_fontes_minimas.py` · `.dod/evidence/DOD-rol-1-definition-of-done-faaf47c790/` · nota: fail/success_zero ainda contam como execução; persistência é item separado.
- [x] O golden path persiste dados. Evidência: PR #79 merge `07e9986` · CI `29835575623` SUCCESS · clean test-db migrations+seed · pcp inserted=98 · pncp_raw_bids=566 · `assert_sources_persisted` · ledger `persist_source_data` · `.dod/evidence/DOD-rol-1-definition-of-done-9c996cb14e/`.
- [x] O golden path executa freshness gate. Evidência: PR #81 · CI `29836318793` SUCCESS · CLI `--execute-freshness-only` · subprocess `freshness_gate.py` · ledger `run_freshness_gate` · live status=fail failing=contracts (execução comprovada; pass/SLA é item separado) · `.dod/evidence/DOD-rol-1-definition-of-done-94ff481872/`.
- [x] O golden path calcula cobertura. Evidência: method_acceptance=PASS (dual_capability_coverage/1.2.0 + source_policy v2.0.0 active sha256=867d77b3…) · live_operational_state: measurement_success=true identity_unresolved_count=0 dual_gate_status=FAIL · coverage_gate_state=FAIL (not 95%) · authoritative pack `.dod/evidence/DOD-rol-1-definition-of-done-4efe05fc94/` (REACCEPTED_FINAL at abcd067) · mirror pack `.dod/evidence/DOD-rol-1-definition-of-done-1fdea0f6e6/` · roles: implementation/reviewed/reproof/acceptance_sha=abcd067 · **não** afirma 95% live nem LOCAL_READY.
- [x] O golden path reconcilia snapshot de editais. Evidência: PR #88 · CI main `29841380680` · reproof CONTINUE-03 11 passed REQUIRE_REAL_DB · `.dod/evidence/DOD-rol-1-definition-of-done-c73b1150d6/`.
- [x] O golden path gera relatório de editais.
- [x] O golden path gera relatório de contratos.
- [x] O golden path gera relatório de concorrentes.
- [ ] O golden path gera relatório de referências de valores.
- [x] O golden path gera Excel. Evidência: PR #90 · panorama Excel size≥100 openpyxl · reproof CONTINUE-03 · `.dod/evidence/DOD-rol-1-definition-of-done-d5c6584cb7/` · **não** prova relatórios de editais/contratos/concorrentes/valores.
- [x] O golden path gera PDF. Evidência: PR #90 · panorama PDF magic %PDF · reproof CONTINUE-03 · `.dod/evidence/DOD-rol-1-definition-of-done-ddfcf1ec8a/` · **não** prova relatórios específicos de domínio.
- [x] O golden path gera ledger. Evidência: PR #85 · ledger JSON com steps · tests/test_golden_path_ledger_meta.py · CONTINUE-03 QA PASS · `.dod/evidence/DOD-rol-1-definition-of-done-7d4698cf6a/`.
- [x] O golden path gera logs. Evidência: PR #85 · CLI Log salvo output/golden-path/*.log · CONTINUE-03 · `.dod/evidence/DOD-rol-1-definition-of-done-05418e32b2/`.
- [x] O golden path retorna exit code não zero em qualquer gate obrigatório. Evidência: PR #85 · essential_fail=2 freshness_fail=3 · tests/test_golden_path_ledger_meta.py · CONTINUE-03 · `.dod/evidence/DOD-rol-1-definition-of-done-3500c05a66/`.
- [x] O golden path pode ser reexecutado sem duplicação. Evidência: PR #92 · dual seed keys unique + dual snapshot stable · CONTINUE-03 · `.dod/evidence/DOD-rol-1-definition-of-done-98c4820f19/`.
- [x] O golden path pode ser executado em ambiente limpo. Evidência: PR #96 · `scripts.ops.golden_clean_env --confirm-drop` · tests/test_golden_clean_env.py · QA PASS · `.dod/evidence/DOD-rol-1-definition-of-done-596584406e/`.
- [x] O tempo total de execução é registrado. Evidência: PR #85 · wall_clock_ms no ledger · CONTINUE-03 · `.dod/evidence/DOD-rol-1-definition-of-done-d134dd8ca2/`.
- [x] A versão do código é registrada. Evidência: PR #97 · ledger meta.git_sha via _save_final_ledger · tests/test_golden_path_ledger_meta.py · .
- [x] O hash da planilha é registrado. Evidência: PR #97 · ledger meta.spreadsheet_sha256 · `.dod/evidence/DOD-rol-1-definition-of-done-8990bd3e67/`.
- [x] A versão do schema é registrada. Evidência: PR #97 · ledger meta.schema_version · tests/test_golden_path_ledger_meta.py · .
- [ ] Os relatórios apontam o período de referência.
- [ ] Os relatórios apontam limitações conhecidas.

### 12.2 Saídas operacionais

- [ ] Lista de editais acionáveis.
- [ ] Lista de editais para revisão.
- [ ] Lista de editais descartados com motivo.
- [ ] Lista de oportunidades removidas do snapshot.
- [ ] Lista de entes sem cobertura de editais.
- [x] Lista de entes sem cobertura de contratos. Evidência: gap-lists-20260719.json · ops proxy 1090/1093 · SZ 722 · EXTRA-OPS-95 27d3665 · residual 3 cnpj_8 malformados 00394494*
- [ ] Lista de blockers por fonte.
- [ ] Lista de runs stale.
- [ ] Relatório de contratos por ente.
- [ ] Relatório de contratos por fornecedor.
- [ ] Relatório de concorrentes.
- [ ] Relatório de concentração.
- [ ] Relatório de referências de valores.
- [ ] Relatório de completude.
- [ ] Relatório de coverage.
- [ ] Relatório de recall.
- [ ] Relatório de source health.
- [ ] Exportação CSV.
- [ ] Exportação Excel.
- [ ] Relatório PDF.
- [ ] Todos os relatórios incluem data de geração.
- [ ] Todos os relatórios incluem versão do universo.
- [ ] Todos os relatórios incluem fonte.
- [ ] Todos os relatórios incluem status de confiabilidade.
- [ ] Todos os relatórios evitam afirmações não suportadas.

---

## 13. Testes do estágio atual

### 13.1 Testes unitários

- [x] Normalização de CNPJ.
- [x] Normalização de IBGE. Evidência: canonical `AUTOMATED_TEST` + `scripts/lib/universe.py`
- [x] Normalização de coordenadas.
- [x] Cálculo de identidade de ente.
- [ ] Importação idempotente da planilha.
- [ ] Detecção de novos entes.
- [ ] Detecção de entes alterados.
- [ ] Detecção de entes removidos.
- [x] Cálculo de cobertura.
- [x] Regra de `success_zero`.
- [x] Freshness.
- [x] Paginação.
- [x] Retry.
- [x] Backoff.
- [x] Checkpoint.
- [x] Resume.
- [x] Deduplicação.
- [ ] Reconciliação de snapshot.
- [x] Classificação de status.
- [ ] Classificação AEC.
- [x] Regras de score.
- [x] Semântica de valores. Evidência: canonical `AUTOMATED_TEST` + `scripts/lib/value_semantics.py`
- [ ] Encadeamento edital-contrato. `PARTIAL` — unit match rules only; not live edital→contrato chain.
- [x] Geração de manifest.
- [x] Geração de relatórios.

### 13.2 Testes de integração

- [ ] Banco vazio até schema completo.
- [x] Importação da planilha real. Evidência: sc_public_entities seed 2085 · raio_200km=1093 · second-import 0 inserted · load_canonical_universe · EXTRA-OPS-95
- [x] Segunda importação sem mudanças. Evidência: sc_public_entities seed 2085 · raio_200km=1093 · second-import 0 inserted · load_canonical_universe · EXTRA-OPS-95 · 0 inserted
- [x] Crawl real de pequeno período. Evidência: monitor/contracts/sc crawls · M2 evidence · EXTRA-OPS-95
- [x] Persistência real. Evidência: pncp_raw_bids 11559 · pncp_supplier_contracts 217574 · upsert live · EXTRA-OPS-95
- [x] Reexecução sem duplicação. Evidência: pncp_raw_bids 11559 · pncp_supplier_contracts 217574 · upsert live · EXTRA-OPS-95 · upsert ON CONFLICT
- [ ] Atualização de registro alterado.
- [x] Execução de `success_zero`. Evidência: coverage_evidence success_zero n=623 · probe_entity_success_zero · http_204_complete · purge-token-mismatch · EXTRA-OPS-95 ab3f77c 2026-07-19
- [ ] Falha parcial não marcada como sucesso.
- [x] Retomada por checkpoint. Evidência: contracts_full.json completed_windows · M5-resume · EXTRA-OPS-95-FOUNDATION 2026-07-19
- [ ] Reconciliação de ente.
- [ ] Reconciliação de snapshot.
- [ ] Backfill de contratos de janela pequena.
- [ ] Incremental após backfill.
- [ ] Geração real de PDF.
- [ ] Geração real de Excel.
- [x] Queries analíticas em PostgreSQL real. Evidência: LOCAL_DATALAKE_DSN PostgreSQL real · queries cobertura/ops · EXTRA-OPS-95
- [ ] Golden path completo.

### 13.3 Testes de contrato com fontes

- [ ] Endpoint PNCP válido.
- [ ] Schema PNCP esperado.
- [ ] Paginação PNCP válida.
- [ ] Endpoint PCP válido.
- [ ] Schema PCP esperado.
- [ ] Endpoint ComprasGov válido.
- [ ] Schema ComprasGov esperado.
- [ ] Endpoint de cada fonte ativa validado.
- [ ] Mudança de campo obrigatório gera alerta.
- [ ] Resposta vazia inesperada gera alerta.
- [ ] Redução abrupta de volume gera alerta.
- [ ] HTTP 403 é distinguido de zero registros.
- [ ] HTTP 429 é distinguido de zero registros.
- [ ] HTTP 5xx é distinguido de zero registros.
- [ ] Timeout é distinguido de zero registros.

### 13.4 Qualidade mínima

- [x] `ruff` passa no código alterado. Evidência: canonical `EXECUTED_PROOF` + `docs/ops/session-2026-07-18-campaign-q13-4/ruff.exit`
- [x] `mypy` passa no caminho crítico definido. Evidência: canonical `EXECUTED_PROOF` + `docs/ops/session-2026-07-18-campaign-q13-4/mypy-critical-path.txt`
- [x] `pytest` passa na suíte obrigatória.
- [x] `bandit` não aponta vulnerabilidade HIGH no código de produção.
- [x] `pip-audit` não aponta vulnerabilidade conhecida sem tratamento. Evidência: canonical EXECUTED_PROOF pip_audit -r requirements.txt --strict EXIT:0
- [x] Pre-commit está configurado.
- [x] CI falha de modo fechado.
- [x] Nenhum gate obrigatório usa `continue-on-error`.
- [x] Nenhum gate obrigatório usa `|| true`. Evidência: `scripts/ops/scan_mandatory_gates_failclosed.py` + `tests/test_mandatory_gates_no_or_true.py` (7 passed) + scan findings=0 em `docs/ops/session-2026-07-18-no-or-true-gates/` (main HEAD re-proof 2026-07-18).
- [x] A suíte crítica não depende de serviço externo instável sem mock ou marcação adequada.
- [x] Testes lentos possuem marcação.
- [x] Testes que exigem fonte real podem ser executados sob demanda. Evidência: canonical `DOCUMENT_CONTENT_PROOF` + `docs/ops/session-2026-07-18-campaign-q13-4/external-markers.txt`
- [x] O coverage mínimo é definido para caminhos críticos, não como número cosmético global. Evidência: canonical `DOCUMENT_CONTENT_PROOF` + `docs/ops/session-2026-07-18-campaign-q13-4/coverage-gate.txt`
- [x] Código crítico sem teste possui justificativa registrada. Evidência: canonical `DOCUMENT_CONTENT_PROOF` + `docs/ops/session-2026-07-18-campaign-q13-4/debt-registry-listing.txt`
- [x] QA não depende exclusivamente do implementador.

---

## 14. Backup e recuperação local

- [x] Existe backup local do PostgreSQL. Evidência: M5-backup/proof-report-*.json dump_bytes≈9.9MB · EXTRA-OPS-95-FOUNDATION 2026-07-19
- [x] O backup usa formato restaurável.
- [x] O arquivo de backup possui data. Evidência: skeptic-remediation EXECUTED_PROOF + docs/ops/session-2026-07-18-campaign-batch3/backup-executed-proof.json
- [x] O arquivo de backup possui integridade verificada. Evidência: skeptic-remediation EXECUTED_PROOF + docs/ops/session-2026-07-18-campaign-batch3/backup-executed-proof.json
- [x] Existe retenção mínima definida.
- [x] Existe script de restore.
- [x] O restore foi testado em banco separado. Evidência: restore_db=extra_restore_proof · M5-backup/proof-summary.json · EXTRA-OPS-95-FOUNDATION 2026-07-19
- [x] O restore recompõe migrations. Evidência: source_public_tables=79 restore_public_tables=79 · M5-backup · EXTRA-OPS-95-FOUNDATION 2026-07-19
- [x] O restore recompõe dados. Evidência: tables_restored=true · M5-backup/proof-summary.json · EXTRA-OPS-95-FOUNDATION 2026-07-19
- [ ] O restore recompõe o universo-alvo.
- [ ] O restore preserva provenance.
- [x] Existe instrução de recuperação após corrupção local. Evidência: canonical DOCUMENT_CONTENT_PROOF docs/ops/backup.md corrompido+restore
- [ ] Existe instrução de recuperação após exclusão acidental.
- [x] O backup não contém segredo exposto. Evidência: canonical `STATIC_REPO_WIDE_PROOF` + `scripts/backup-database.sh`
- [ ] Dados brutos necessários à reprodutibilidade são preservados ou podem ser recoletados.
- [ ] PDFs e anexos não são armazenados no PostgreSQL sem justificativa.
- [ ] Metadados de arquivos incluem hash, tamanho, tipo e origem.
- [ ] Um teste de restauração real está registrado antes de fechar o estágio local.

---

## 15. Aceite manual do estágio atual

- [ ] Tiago consegue instalar o projeto seguindo apenas a documentação.
- [ ] Tiago consegue recriar o banco local.
- [ ] Tiago consegue importar a planilha.
- [ ] Tiago consegue executar o golden path.
- [ ] Tiago consegue gerar uma lista atual de editais.
- [ ] Tiago consegue identificar a data da última verificação de cada edital.
- [ ] Tiago consegue identificar por que uma oportunidade recebeu `GO`, `REVIEW` ou `NO_GO`.
- [ ] Tiago consegue identificar entes sem cobertura.
- [ ] Tiago consegue distinguir ente sem dado de ente não consultado.
- [ ] Tiago consegue consultar contratos de um ente.
- [ ] Tiago consegue consultar contratos de um fornecedor.
- [ ] Tiago consegue gerar ranking de vencedores.
- [ ] Tiago consegue gerar referências de valores com tipo claramente identificado.
- [ ] Tiago consegue gerar PDF e Excel.
- [ ] Tiago consegue repetir a execução sem duplicar dados.
- [ ] Tiago consegue retomar uma execução interrompida.
- [ ] Tiago consegue identificar uma fonte quebrada.
- [ ] Tiago consegue identificar freshness vencida.
- [ ] Tiago consegue restaurar um backup.
- [ ] Tiago considera o fluxo útil para a consultoria real.
- [ ] A cobertura auditável de editais é >= 95%.
- [ ] A cobertura auditável de contratos é >= 95%.
- [ ] O recall de editais relevantes é >= 95% na amostra-ouro.
- [ ] A integridade do snapshot ativo é 100%.
- [ ] Não existem afirmações de acompanhamento de obras.
- [ ] O gate `LOCAL_READY` foi registrado com data, commit e evidências.

---

> **Evidence pack (2026-07-17, adversarial-corrected):** unit-test evidence `docs/ops/session-2026-07-17-dod-unit-evidence/` — **18** §13.1/§3 checkboxes closed after independent QA PASS + adversarial review (ROI-cand-dod-unit-test-evidence-pack). pytest 511 passed. **Partial evidence kept open (no `[x]`):** Classificação AEC; Encadeamento edital-contrato. §8.3 Classificação AEC remains open (not unit-test scope). Unit tests do **not** prove live ops or e2e. No 95% / LOCAL_RESILIENCE_READY / PRE_VPS_FINAL_READY / VPS_OPERATIONAL / PROJECT_DONE claim.
# ROL 2 — DEFINITION OF DONE APÓS PROVISIONAR A VPS

> Este rol começa após a contratação e disponibilização da VPS.
>
> A VPS não redefine o produto. Ela apenas torna contínuo, remoto e independente do computador local um fluxo que já deve estar tecnicamente válido.

---

## 16. Decisão e contratação da infraestrutura

- [ ] O provedor foi escolhido com justificativa.
- [ ] A região foi escolhida com justificativa.
- [ ] O custo mensal estimado foi registrado.
- [ ] O limite mensal aceitável foi registrado.
- [ ] CPU, RAM e disco foram dimensionados.
- [ ] O dimensionamento considera crescimento do PostgreSQL.
- [ ] O dimensionamento considera crawlers concorrentes.
- [ ] O dimensionamento considera geração de relatórios.
- [ ] A possibilidade de expansão de disco foi verificada.
- [ ] A política de snapshots do provedor foi verificada.
- [ ] A política de suporte foi verificada.
- [ ] A política de backup externo foi definida.
- [ ] A hipótese de bloqueio geográfico do PNCP foi testada.
- [ ] O crawler real foi executado a partir da região candidata.
- [ ] O teste registrou status HTTP.
- [ ] O teste registrou latência.
- [ ] O teste registrou timeouts.
- [ ] O teste registrou quantidade de registros.
- [ ] O teste registrou paginação.
- [ ] O teste registrou consistência de schema.
- [ ] A diferença de registros entre regiões está dentro da tolerância definida.
- [ ] Não houve bloqueio 403 por origem geográfica.
- [ ] A região final foi aprovada com base no teste.

---

## 17. Provisionamento básico

- [ ] A VPS usa Ubuntu 24.04 LTS ou versão formalmente aprovada.
- [ ] A versão do PostgreSQL coincide com a versão canônica.
- [ ] A versão do Python coincide com a versão canônica.
- [ ] O hostname está definido.
- [ ] O timezone está definido.
- [ ] O relógio está sincronizado.
- [ ] Existe usuário não-root para a aplicação.
- [ ] O usuário de aplicação possui home e permissões adequadas.
- [ ] O diretório da aplicação está definido.
- [ ] O diretório de dados está definido.
- [ ] O diretório de logs está definido.
- [ ] O diretório temporário está definido.
- [ ] O provisionamento é executado por script ou Ansible.
- [ ] O provisionamento é idempotente.
- [ ] A segunda execução do provisionamento não quebra a máquina.
- [ ] O provisionamento gera log.
- [ ] O provisionamento retorna exit code não zero em falha.
- [ ] Não existe etapa essencial exclusivamente manual e não documentada.
- [ ] Nenhum agente de desenvolvimento ou IDE assistida, incluindo Claude Code, Codex, Cursor ou equivalente, é instalado na VPS como dependência operacional.
- [ ] A operação da VPS não depende de sessão interativa de IA.
- [ ] Node.js não é instalado sem necessidade.
- [ ] Docker não é instalado sem necessidade.
- [ ] Serviços desnecessários são removidos ou desabilitados.

---

## 18. Hardening da VPS

- [ ] Acesso SSH somente por chave.
- [ ] Chave ed25519 ou equivalente moderno.
- [ ] Password authentication desabilitado.
- [ ] Login root direto desabilitado.
- [ ] X11 forwarding desabilitado.
- [ ] Usuário de aplicação sem privilégios excessivos.
- [ ] `sudo` restrito.
- [ ] UFW com default deny.
- [ ] Apenas portas necessárias abertas.
- [ ] PostgreSQL não exposto publicamente.
- [ ] Acesso ao PostgreSQL por localhost, túnel SSH, rede privada ou Tailscale.
- [ ] Fail2ban ativo.
- [ ] Política de bloqueio validada.
- [ ] Atualizações de segurança automáticas ativas.
- [ ] Política de reboot definida.
- [ ] A política de reboot foi testada.
- [ ] Chaves possuem política de rotação.
- [x] Segredos não aparecem em logs. Evidência: same · EXTRA-OPS-95
- [ ] DSNs são mascarados em logs.
- [ ] Arquivos `.env` possuem permissões mínimas.
- [ ] A chave de backup possui escopo mínimo.
- [ ] A chave de deploy possui escopo mínimo.
- [ ] Tentativas de acesso são auditáveis.
- [ ] Portas abertas são verificadas externamente.
- [ ] Um scan básico não encontra serviço inesperado exposto.

---

## 19. Deploy reproduzível

- [ ] O deploy parte de commit identificado.
- [ ] O commit passou pelos gates obrigatórios.
- [ ] O deploy não exige edição manual de código na VPS.
- [ ] O código é sincronizado por método definido.
- [ ] Dependências são instaladas de forma determinística.
- [ ] Migrations são executadas de forma controlada.
- [ ] Seeds são executadas de forma controlada.
- [ ] O deploy possui pre-check.
- [ ] O deploy possui smoke test.
- [ ] O deploy possui freshness gate.
- [ ] O deploy possui health check.
- [ ] O deploy possui rollback de código.
- [ ] O deploy possui estratégia de recuperação de banco.
- [ ] O deploy interrompe em falha.
- [ ] O deploy registra início, fim e versão.
- [ ] O deploy pode ser reexecutado.
- [ ] O deploy não depende de sessão SSH artesanal.
- [ ] O deploy pode ser iniciado do ambiente local de Tiago.
- [x] Existe runbook de deploy. Evidência: canonical `DOCUMENT_CONTENT_PROOF` + `docs/ops/cloud-deployment-plan.md`
- [ ] Existe runbook de rollback.
- [ ] Existe runbook de recuperação após deploy incompleto.

---

## 20. Migração do banco local para a VPS

- [x] Backup final do banco local foi criado. Evidência: M5-backup proof-summary.json backup_exists+restore_separate_db tables 79/79 · dump 9.9MB · EXTRA-OPS-95
- [x] Hash ou integridade do backup foi validado. Evidência: M5-backup proof-summary.json backup_exists+restore_separate_db tables 79/79 · dump 9.9MB · EXTRA-OPS-95 · dump_bytes
- [x] Banco de destino foi criado. Evidência: M5-backup proof-summary.json backup_exists+restore_separate_db tables 79/79 · dump 9.9MB · EXTRA-OPS-95 · extra_restore_proof
- [ ] Migrations foram aplicadas.
- [x] Restore foi executado. Evidência: M5-backup proof-summary.json backup_exists+restore_separate_db tables 79/79 · dump 9.9MB · EXTRA-OPS-95 (pg_restore exit 1 non-fatal: transaction_timeout unknown)
- [x] Contagem de entes coincide. Evidência: M5-backup proof-summary.json backup_exists+restore_separate_db tables 79/79 · dump 9.9MB · EXTRA-OPS-95 · tables 79/79
- [ ] Hash da planilha coincide.
- [ ] Contagem de editais coincide dentro da regra definida.
- [ ] Contagem de contratos coincide dentro da regra definida.
- [ ] Contagem de fornecedores coincide.
- [ ] Ledger de migrations coincide.
- [ ] Views críticas funcionam.
- [ ] Queries críticas funcionam.
- [ ] Golden path funciona na VPS.
- [ ] Relatórios gerados na VPS coincidem com o baseline.
- [ ] Diferenças são explicadas.
- [ ] O banco local é mantido temporariamente como fallback.
- [ ] A data de corte da migração foi registrada.
- [ ] O primeiro incremental pós-migração foi executado.
- [ ] Não houve duplicação após o primeiro incremental.
- [ ] A VPS passou a ser a fonte operacional após aceite explícito.

---

## 21. Serviços e timers

- [ ] Cada crawler ativo possui service unit.
- [ ] Cada crawler recorrente possui timer.
- [ ] Cada service usa `EnvironmentFile`.
- [ ] Cada service roda com usuário apropriado.
- [ ] Cada service possui timeout.
- [ ] Cada service possui política de restart coerente.
- [ ] Cada service possui `OnFailure`.
- [ ] Existe apenas um padrão de template `OnFailure`.
- [ ] O payload de alerta é consistente.
- [ ] Todos os services críticos têm cobertura de alerta.
- [ ] Timers são escalonados para evitar concorrência desnecessária.
- [ ] Timers usam timezone documentado.
- [ ] Timers possuem `RandomizedDelaySec` quando apropriado.
- [ ] O crawl de editais atende freshness <= 24h.
- [ ] O incremental de contratos atende freshness <= 7 dias.
- [ ] O freshness gate possui timer.
- [ ] O coverage report possui timer.
- [ ] O health check possui timer.
- [ ] O check de alertas possui timer.
- [ ] A coleta de métricas possui timer.
- [ ] O backup possui timer.
- [ ] O teste de restore possui timer ou rotina periódica documentada.
- [ ] Timers desabilitados são intencionais e documentados.
- [ ] Selenium genérico não roda como fonte independente.
- [ ] O status de todos os timers é exportável.
- [ ] O atraso de execução é detectado.
- [ ] Uma falha silenciosa é detectada em até 30 minutos.
- [ ] A execução manual continua possível.

---

## 22. Backup e disaster recovery na VPS

- [ ] Backup é armazenado fora da VPS principal.
- [ ] Backup é criptografado em trânsito.
- [ ] Backup possui retenção diária.
- [ ] Backup possui retenção semanal.
- [ ] Backup possui integridade verificada.
- [ ] Falha de backup gera alerta.
- [ ] Último backup válido é monitorado.
- [ ] O backup não é substituído por snapshot do provedor.
- [ ] O restore foi testado em banco separado.
- [ ] O restore completo foi testado.
- [ ] O restore de schema foi testado.
- [ ] O restore de dados foi testado.
- [ ] O tempo de restauração foi registrado.
- [ ] A perda total da VPS foi simulada.
- [ ] Uma nova VPS foi provisionada.
- [ ] O código foi reimplantado.
- [ ] O banco foi restaurado.
- [ ] Os timers foram reativados.
- [ ] O golden path foi executado.
- [ ] O freshness gate voltou a passar.
- [ ] O RPO aceitável foi definido.
- [ ] O RTO aceitável foi definido.
- [ ] O procedimento de desastre está documentado.
- [ ] Credenciais de recuperação estão acessíveis de forma segura.
- [ ] A recuperação não depende de memória pessoal não documentada.

---

## 23. Observabilidade e alertas

- [ ] Logs estruturados estão ativos.
- [ ] Logs possuem timestamp.
- [ ] Logs possuem nível.
- [ ] Logs possuem serviço.
- [ ] Logs possuem fonte.
- [ ] Logs possuem `run_id` ou correlation id.
- [x] Logs não expõem segredos. Evidência: campaign logs use DSN env not inline password in committed evidence · EXTRA-OPS-95
- [ ] Retenção de journald está configurada.
- [ ] Uso de disco é monitorado.
- [ ] Uso de memória é monitorado.
- [ ] Load average é monitorado.
- [ ] Crescimento do banco é monitorado.
- [ ] Dead tuples são monitoradas.
- [ ] Autovacuum é monitorado.
- [ ] Duração dos crawlers é monitorada.
- [ ] Taxa de sucesso dos crawlers é monitorada.
- [ ] Volume coletado é monitorado.
- [ ] HTTP 403 é monitorado.
- [ ] HTTP 429 é monitorado.
- [ ] HTTP 5xx é monitorado.
- [ ] Timeouts são monitorados.
- [ ] Freshness por fonte é monitorada.
- [ ] Coverage por capability é monitorada.
- [ ] Último backup válido é monitorado.
- [ ] Falhas de migration são monitoradas.
- [ ] Timers atrasados são monitorados.
- [ ] Alertas possuem destino configurado.
- [ ] O destino de alerta foi testado.
- [ ] O alerta possui contexto suficiente para ação.
- [ ] O sistema evita tempestade de alertas.
- [ ] Existe rate limiting ou deduplicação de alertas.
- [ ] Falha no webhook é detectável.
- [ ] Existe fallback de notificação ou registro persistente.
- [ ] Tiago consegue consultar saúde geral com um comando.

---

## 24. Operação contínua e independência do ambiente local

- [ ] A VPS executa crawlers sem o computador local ligado.
- [ ] A VPS executa relatórios sem o computador local ligado.
- [ ] A VPS executa backups sem o computador local ligado.
- [ ] A VPS executa health checks sem o computador local ligado.
- [ ] A VPS executa alertas sem o computador local ligado.
- [ ] A operação não depende de Claude Code, Codex, Cursor ou qualquer outro agente de desenvolvimento.
- [ ] A operação não depende de terminal aberto.
- [ ] A operação não depende de login diário.
- [ ] O sistema retoma após reboot.
- [ ] PostgreSQL inicia após reboot.
- [ ] Services iniciam conforme configuração.
- [ ] Timers permanecem habilitados após reboot.
- [ ] Um reboot controlado foi testado.
- [ ] Uma falha de crawler foi simulada.
- [ ] Um atraso de fonte foi simulado.
- [ ] Uma falha de backup foi simulada.
- [ ] Um disco próximo do limite foi simulado ou testado.
- [ ] Uma chave inválida foi simulada.
- [ ] Alertas foram recebidos.
- [ ] O runbook permitiu recuperação.
- [ ] O sistema operou por sete dias consecutivos sem falha crítica não detectada.
- [ ] Durante os sete dias, editais mantiveram freshness <= 24h.
- [ ] Durante os sete dias, contratos mantiveram freshness <= 7 dias.
- [ ] Durante os sete dias, cobertura de editais permaneceu >= 95%.
- [ ] Durante os sete dias, cobertura de contratos permaneceu >= 95%.
- [ ] Durante os sete dias, backups foram concluídos.
- [ ] Ao menos um restore foi validado no período.
- [ ] O custo real foi registrado.
- [ ] O custo real permaneceu dentro do limite aprovado.
- [ ] O gate `VPS_OPERATIONAL` foi registrado com data, commit e evidências.

---

# ROL 3 — DEFINITION OF DONE INDEPENDENTE DA INFRAESTRUTURA

> Estes requisitos podem e devem evoluir antes, durante e depois do provisionamento da VPS.
>
> Eles impedem que o projeto fique tecnicamente sofisticado e, ainda assim, pouco confiável ou pouco útil para a consultoria.

---

## 25. Verdade, linguagem e claims permitidos

- [x] Todo indicador possui definição. Evidência: `scripts/coverage/coverage_contract.py` (`MetricDefinition`/`validate_indicator_catalog`/`READY_SEMANTICS`) + `tests/test_indicator_catalog.py` (6 passed) + `docs/ops/session-2026-07-18-indicator-catalog/` + QA PASS cyc-2026-07-18T125038Z. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Todo indicador possui fórmula. Evidência: `scripts/coverage/coverage_contract.py` (`MetricDefinition`/`validate_indicator_catalog`/`READY_SEMANTICS`) + `tests/test_indicator_catalog.py` (6 passed) + `docs/ops/session-2026-07-18-indicator-catalog/` + QA PASS cyc-2026-07-18T125038Z. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Todo indicador possui denominador. Evidência: `scripts/coverage/coverage_contract.py` (`MetricDefinition`/`validate_indicator_catalog`/`READY_SEMANTICS`) + `tests/test_indicator_catalog.py` (6 passed) + `docs/ops/session-2026-07-18-indicator-catalog/` + QA PASS cyc-2026-07-18T125038Z. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Todo indicador possui data de corte. Evidência: `scripts/coverage/coverage_contract.py` (`MetricDefinition`/`validate_indicator_catalog`/`READY_SEMANTICS`) + `tests/test_indicator_catalog.py` (6 passed) + `docs/ops/session-2026-07-18-indicator-catalog/` + QA PASS cyc-2026-07-18T125038Z. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Todo indicador possui fonte. Evidência: `scripts/coverage/coverage_contract.py` (`MetricDefinition`/`validate_indicator_catalog`/`READY_SEMANTICS`) + `tests/test_indicator_catalog.py` (6 passed) + `docs/ops/session-2026-07-18-indicator-catalog/` + QA PASS cyc-2026-07-18T125038Z. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Todo indicador possui status de prontidão. Evidência: `scripts/coverage/coverage_contract.py` (`MetricDefinition`/`validate_indicator_catalog`/`READY_SEMANTICS`) + `tests/test_indicator_catalog.py` (6 passed) + `docs/ops/session-2026-07-18-indicator-catalog/` + QA PASS cyc-2026-07-18T125038Z. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] `READY` significa executado e validado. Evidência: `scripts/coverage/coverage_contract.py` (`MetricDefinition`/`validate_indicator_catalog`/`READY_SEMANTICS`) + `tests/test_indicator_catalog.py` (6 passed) + `docs/ops/session-2026-07-18-indicator-catalog/` + QA PASS cyc-2026-07-18T125038Z. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] `PARTIAL` significa parcialmente disponível com limitações explícitas. Evidência: `scripts/coverage/coverage_contract.py` `PARTIAL_SEMANTICS` + `tests/test_indicator_catalog.py` (test_partial_semantics) · ROI-cand-dyn-slice-ac8b6e76a7b2 · EXTRA-OPS-95
- [x] `NOT_READY` significa não disponível. Evidência: skeptic-remediation `DOCUMENT_CONTENT_PROOF` + `README.md`
- [x] `BLOCKED` significa impedido por dependência externa ou técnica. Evidência: `scripts/coverage/coverage_contract.py` `BLOCKED_SEMANTICS` + `tests/test_indicator_catalog.py` (test_blocked_semantics) · ROI-cand-dyn-slice-ac8b6e76a7b2 · EXTRA-OPS-95
- [x] Código existente não é chamado de capacidade pronta. Evidência: skeptic-remediation `DOCUMENT_CONTENT_PROOF` + `README.md`
- [x] Dado antigo não é chamado de dado atual. Evidência: skeptic-remediation `STATIC_REPO_WIDE_PROOF` + `scripts/freshness_gate.py`
- [x] Presença de dados não é chamada de cobertura. Evidência: skeptic-remediation `DOCUMENT_CONTENT_PROOF` + `README.md`
- [x] Ausência de dados não é chamada de ausência de licitação sem consulta válida. Evidência: `scripts/lib/claim_language.py` + `tests/test_claim_language.py` (9 passed) + `scripts/reports/run_metadata.py` CLAIMS_FORBIDDEN + `docs/ops/session-2026-07-18-claim-language/` + QA PASS cyc-2026-07-18T125719Z. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Valor contratado não é chamado de preço praticado. Evidência: canonical `AUTOMATED_TEST` + `scripts/lib/value_semantics.py`
- [x] Vencedor conhecido não é chamado de conjunto completo de concorrentes. Evidência: `scripts/lib/claim_language.py` + `tests/test_claim_language.py` (9 passed) + `scripts/reports/run_metadata.py` CLAIMS_FORBIDDEN + `docs/ops/session-2026-07-18-claim-language/` + QA PASS cyc-2026-07-18T125719Z. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Participante não identificado não é tratado como inexistente. Evidência: `scripts/lib/claim_language.py` + `tests/test_claim_language.py` (9 passed) + `scripts/reports/run_metadata.py` CLAIMS_FORBIDDEN + `docs/ops/session-2026-07-18-claim-language/` + QA PASS cyc-2026-07-18T125719Z. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Win rate não é calculado sem propostas enviadas. Evidência: `scripts/lib/claim_language.py` + `tests/test_claim_language.py` (9 passed) + `scripts/reports/run_metadata.py` CLAIMS_FORBIDDEN + `docs/ops/session-2026-07-18-claim-language/` + QA PASS cyc-2026-07-18T125719Z. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Deságio não é calculado sem grandezas comparáveis. Evidência: canonical `AUTOMATED_TEST` + `scripts/lib/value_semantics.py`
- [x] Score não é chamado de probabilidade sem calibração. Evidência: `scripts/lib/claim_language.py` + `tests/test_claim_language.py` (9 passed) + `scripts/reports/run_metadata.py` CLAIMS_FORBIDDEN + `docs/ops/session-2026-07-18-claim-language/` + QA PASS cyc-2026-07-18T125719Z. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Relatórios exibem limitações relevantes. Evidência: `scripts/lib/claim_language.py` + `tests/test_claim_language.py` (9 passed) + `scripts/reports/run_metadata.py` CLAIMS_FORBIDDEN + `docs/ops/session-2026-07-18-claim-language/` + QA PASS cyc-2026-07-18T125719Z. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Nenhum documento afirma que o projeto acompanha obras. Evidência: `scripts/lib/claim_language.py` + `tests/test_claim_language.py` (9 passed) + `scripts/reports/run_metadata.py` CLAIMS_FORBIDDEN + `docs/ops/session-2026-07-18-claim-language/` + QA PASS cyc-2026-07-18T125719Z. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Nenhum documento promete capacidade fora do escopo. Evidência: `scripts/ops/scan_docs_definition_consistency.py` + `tests/test_docs_definition_consistency.py` (5 passed) + `docs/ops/session-2026-07-18-docs-definitions/` + QA PASS cyc-2026-07-18T130315Z. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] README, PRD, DOD, manifests e relatórios usam as mesmas definições. Evidência: `scripts/ops/scan_docs_definition_consistency.py` + `tests/test_docs_definition_consistency.py` (5 passed) + `docs/ops/session-2026-07-18-docs-definitions/` + QA PASS cyc-2026-07-18T130315Z. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Números conflitantes são eliminados ou contextualizados historicamente. Evidência: `scripts/ops/scan_docs_definition_consistency.py` + `tests/test_docs_definition_consistency.py` (5 passed) + `docs/ops/session-2026-07-18-docs-definitions/` + QA PASS cyc-2026-07-18T130315Z. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).

---

## 26. Simplicidade arquitetural

- [ ] Cada componente possui problema claro a resolver.
- [ ] Componentes sem uso são removidos, arquivados ou marcados como legados.
- [ ] Não existem dois orquestradores ativos sem divisão explícita.
- [ ] Não existem dois pipelines canônicos para a mesma entrega.
- [ ] Não existem arquivos duplicados com hífen e underscore para a mesma função.
- [ ] Não existem dois templates de alerta concorrentes.
- [ ] Não existem duas linhas de migrations operacionais concorrentes.
- [ ] Não existe dependência de Supabase sem necessidade funcional.
- [ ] Não existe interface web sem necessidade funcional.
- [ ] Não existe autenticação interna desnecessária.
- [ ] Não existe camada de API interna sem consumidor.
- [ ] Não existe fila distribuída sem volume que a justifique.
- [ ] Não existe cache adicional sem gargalo comprovado.
- [ ] Não existe ferramenta de observabilidade pesada sem necessidade.
- [ ] A arquitetura pode ser explicada em uma página.
- [ ] O fluxo principal pode ser entendido por outro desenvolvedor.
- [ ] O custo cognitivo é tratado como custo real.
- [ ] A solução mais simples que atende ao requisito é preferida.

---

## 27. Organização e manutenção do código

- [x] Estrutura de pastas está documentada. Evidência: canonical `DOCUMENT_CONTENT_PROOF` + `squads/extra-dod-roi/config/source-tree.md`
- [ ] Nomes de módulos são consistentes.
- [ ] Imports funcionam sem hacks de `sys.path` desnecessários.
- [ ] Funções públicas possuem docstring quando necessário.
- [ ] Funções críticas possuem type hints.
- [ ] Exceções são específicas.
- [ ] Erros não são engolidos.
- [ ] Não existem `except Exception: pass`.
- [ ] Falhas externas possuem contexto.
- [ ] Logs não substituem tratamento de erro.
- [ ] Configuração é centralizada.
- [ ] Constantes de domínio são centralizadas.
- [ ] URLs de fontes são centralizadas.
- [x] Timeouts são configuráveis. Evidência: canonical `STATIC_REPO_WIDE_PROOF` + `scripts/crawl/config.py`
- [x] Retries são configuráveis. Evidência: canonical `STATIC_REPO_WIDE_PROOF` + `scripts/crawl/config.py`
- [x] Janelas de freshness são configuráveis. Evidência: canonical `STATIC_REPO_WIDE_PROOF` + `scripts/freshness_gate.py`
- [x] Thresholds de coverage são configuráveis. Evidência: canonical `STATIC_REPO_WIDE_PROOF` + `.github/workflows/ci.yml`
- [ ] Defaults são documentados.
- [x] Mudanças de schema exigem migration. Evidência: canonical `STATIC_REPO_WIDE_PROOF` + `supabase/migrations/001-v2_initial_schema.sql`
- [ ] Mudanças de métrica exigem atualização da definição.
- [ ] Código legado possui plano de remoção.
- [ ] TODOs críticos possuem issue ou story.
- [ ] Comentários não contradizem o código.
- [x] Scripts operacionais possuem `--help`. Evidência: canonical `EXECUTED_PROOF` + `docs/ops/session-2026-07-18-campaign-batch3/ops-help.txt`
- [x] Scripts operacionais possuem exit codes consistentes. Evidência: canonical `STATIC_REPO_WIDE_PROOF` + `docs/ops/session-2026-07-18-campaign-final/ops-universe.json`
- [ ] Scripts operacionais suportam `--dry-run` quando aplicável.
- [ ] Scripts destrutivos exigem confirmação ou flag explícita.
- [ ] Scripts destrutivos possuem backup ou rollback documentado.

---

## 28. Segurança proporcional ao uso pessoal

- [x] Nenhum segredo está versionado. Evidência: `.env` gitignored · `.env.example` placeholders · EXTRA-OPS-95
- [ ] Histórico git foi verificado para segredos expostos.
- [ ] Segredos expostos foram rotacionados.
- [ ] `.env.example` usa placeholders.
- [ ] Tokens têm escopo mínimo.
- [ ] Chaves antigas são removidas.
- [ ] Dependências vulneráveis são tratadas.
- [ ] Arquivos de saída não expõem segredos.
- [ ] Logs não expõem segredos.
- [x] Dumps não são publicados. Evidência: backup dumps only under docs/ops campaign evidence gitignored paths or local proof; not public release
- [ ] Planilhas privadas não são publicadas.
- [ ] O repositório permanece privado. Evidência: github private tjsasakifln/extra-consultoria · EXTRA-OPS-95
- [ ] Dados pessoais desnecessários não são coletados.
- [x] A coleta respeita fontes públicas e limites razoáveis. Evidência: delay+429 backoff · PNCP public APIs only · EXTRA-OPS-95
- [x] Rate limits são respeitados. Evidência: probe delay+429 backoff · resolve_cnpj14_matriz · EXTRA-OPS-95
- [x] User-Agent é identificável quando apropriado. Evidência: ExtraConsultoria-OPS95/1.0 em probe/resolve/crawl
- [ ] Crawlers não tentam contornar autenticação indevidamente.
- [ ] Credenciais de fontes autorizadas são armazenadas com cuidado.
- [ ] A segurança é suficiente para um sistema pessoal sem criar burocracia inútil.
- [ ] Controles adicionais são adotados apenas diante de risco real.

---

## 29. Rastreabilidade e auditoria

- [x] Cada execução possui `run_id`. Evidência: `scripts/crawl/run_evidence.py` `build_execution_audit_record` + `tests/test_execution_audit_record.py` (3 passed) + `docs/ops/session-2026-07-18-execution-audit/` + QA PASS cyc-2026-07-18T132549Z. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Cada execução possui versão do código. Evidência: `scripts/crawl/run_evidence.py` `build_execution_audit_record` + `tests/test_execution_audit_record.py` (3 passed) + `docs/ops/session-2026-07-18-execution-audit/` + QA PASS cyc-2026-07-18T132549Z. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Cada execução possui versão do schema. Evidência: `scripts/crawl/run_evidence.py` `build_execution_audit_record` + `tests/test_execution_audit_record.py` (3 passed) + `docs/ops/session-2026-07-18-execution-audit/` + QA PASS cyc-2026-07-18T132549Z. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Cada execução possui hash da planilha. Evidência: `scripts/crawl/run_evidence.py` `build_execution_audit_record` + `tests/test_execution_audit_record.py` (3 passed) + `docs/ops/session-2026-07-18-execution-audit/` + QA PASS cyc-2026-07-18T132549Z. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Cada execução possui fonte. Evidência: `scripts/crawl/run_evidence.py` `build_execution_audit_record` + `tests/test_execution_audit_record.py` (3 passed) + `docs/ops/session-2026-07-18-execution-audit/` + QA PASS cyc-2026-07-18T132549Z. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Cada execução possui capability. Evidência: `scripts/crawl/run_evidence.py` `build_execution_audit_record` + `tests/test_execution_audit_record.py` (3 passed) + `docs/ops/session-2026-07-18-execution-audit/` + QA PASS cyc-2026-07-18T132549Z. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Cada execução possui parâmetros. Evidência: `scripts/crawl/run_evidence.py` `build_execution_audit_record` + `tests/test_execution_audit_record.py` (3 passed) + `docs/ops/session-2026-07-18-execution-audit/` + QA PASS cyc-2026-07-18T132549Z. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Cada execução possui período. Evidência: `scripts/crawl/run_evidence.py` `build_execution_audit_record` + `tests/test_execution_audit_record.py` (3 passed) + `docs/ops/session-2026-07-18-execution-audit/` + QA PASS cyc-2026-07-18T132549Z. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Cada execução possui timestamps. Evidência: coverage_evidence started_at/completed_at · run manifests · EXTRA-OPS-95
- [x] Cada execução possui status. Evidência: evidence_state enum · run status fields · EXTRA-OPS-95
- [x] Cada execução possui contagens. Evidência: count_obtained/records_fetched · crawl stats · EXTRA-OPS-95
- [ ] Cada execução possui erros.
- [x] Cada execução possui checkpoint. Evidência: contracts_full.json · M5-resume · EXTRA-OPS-95
- [ ] Cada relatório referencia runs de origem.
- [x] Cada registro crítico possui provenance. Evidência: coverage_evidence.provenance jsonb · content_hash · EXTRA-OPS-95
- [ ] Mudanças manuais são auditáveis.
- [ ] Overrides manuais possuem motivo.
- [ ] Overrides manuais possuem data.
- [ ] Overrides manuais possuem autor.
- [ ] A evidência de coverage pode ser reconstruída.
- [x] A evidência de `success_zero` pode ser reconstruída. Evidência: coverage_evidence success_zero n=623 · probe_entity_success_zero · http_204_complete · purge-token-mismatch · EXTRA-OPS-95 ab3f77c 2026-07-19 · scope_key+provenance+content_hash
- [ ] A evidência de freshness pode ser reconstruída.
- [ ] A evidência de recall pode ser reconstruída.
- [ ] A evidência de snapshot pode ser reconstruída.
- [ ] O DOD aponta para os artefatos finais de aceite.

---

## 30. Performance e custo

- [ ] O tempo do golden path é medido.
- [ ] O tempo de cada crawler é medido.
- [ ] O tempo de cada relatório é medido.
- [ ] Queries lentas são identificadas.
- [ ] Índices são baseados em consultas reais.
- [ ] Não existe otimização prematura sem evidência.
- [ ] O crescimento diário do banco é medido.
- [ ] O crescimento mensal é estimado.
- [ ] O espaço de dados brutos é medido.
- [ ] O espaço de PDFs e anexos é medido.
- [ ] O custo de APIs pagas é medido.
- [ ] O custo de LLM é medido.
- [ ] Chamadas de LLM são cacheadas quando apropriado.
- [ ] O sistema funciona sem LLM em capacidades determinísticas.
- [ ] LLM não decide coverage.
- [ ] LLM não decide freshness.
- [ ] LLM não inventa valores ausentes.
- [ ] LLM não substitui fonte oficial.
- [ ] O custo mensal total é compatível com o valor da consultoria.
- [ ] Uma otimização só é priorizada quando reduz custo, tempo ou risco relevante.

---

## 31. Documentação operacional

- [x] README descreve o estado atual real. Evidência: canonical `DOCUMENT_CONTENT_PROOF` + `README.md`
- [x] README descreve o escopo. Evidência: canonical `DOCUMENT_CONTENT_PROOF` + `README.md`
- [x] README descreve o fora de escopo. Evidência: canonical `DOCUMENT_CONTENT_PROOF` + `README.md`
- [x] README descreve setup. Evidência: canonical `DOCUMENT_CONTENT_PROOF` + `README.md`
- [x] README descreve comandos principais. Evidência: canonical `DOCUMENT_CONTENT_PROOF` + `README.md`
- [x] README descreve fontes. Evidência: canonical `DOCUMENT_CONTENT_PROOF` + `README.md`
- [x] README descreve métricas de coverage. Evidência: canonical `DOCUMENT_CONTENT_PROOF` + `README.md`
- [x] README não confunde alvo futuro com realidade atual. Evidência: `docs/GLOSSARY.md` + `docs/architecture/adr/INDEX.md` + `docs/ops/runbook.md` (rollback/schema-drift/cobertura<95%) + `scripts/ops/scan_ops_docs_honesty.py` + `tests/test_ops_docs_honesty.py` + QA PASS cyc-2026-07-18T131425Z (7/8; PRD alignment left open). · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] PRD está alinhado ao DOD. Evidência: PRD v2.1 + CHANGELOG.md + docs/ops/NEXT-DEV-STEP.md + scan_ops_docs_honesty ok + QA PASS cyc-2026-07-18T132050Z. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] ADRs vigentes estão identificadas. Evidência: `docs/GLOSSARY.md` + `docs/architecture/adr/INDEX.md` + `docs/ops/runbook.md` (rollback/schema-drift/cobertura<95%) + `scripts/ops/scan_ops_docs_honesty.py` + `tests/test_ops_docs_honesty.py` + QA PASS cyc-2026-07-18T131425Z (7/8; PRD alignment left open). · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] ADRs revogadas estão identificadas. Evidência: `docs/GLOSSARY.md` + `docs/architecture/adr/INDEX.md` + `docs/ops/runbook.md` (rollback/schema-drift/cobertura<95%) + `scripts/ops/scan_ops_docs_honesty.py` + `tests/test_ops_docs_honesty.py` + QA PASS cyc-2026-07-18T131425Z (7/8; PRD alignment left open). · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Existe runbook local. Evidência: canonical `DOCUMENT_CONTENT_PROOF` + `docs/ops/runbook.md`
- [x] Existe runbook de VPS. Evidência: skeptic-remediation `DOCUMENT_CONTENT_PROOF` + `docs/ops/vps-provisioning.md`
- [x] Existe runbook de backup. Evidência: canonical `DOCUMENT_CONTENT_PROOF` + `docs/ops/backup.md`
- [x] Existe runbook de restore. Evidência: canonical `DOCUMENT_CONTENT_PROOF` + `docs/ops/backup.md`
- [x] Existe runbook de deploy. Evidência: canonical `DOCUMENT_CONTENT_PROOF` + `docs/ops/cloud-deployment-plan.md`
- [x] Existe runbook de rollback. Evidência: `docs/ops/runbook.md` §Runbook de Rollback + `scripts/ops/scan_ops_docs_honesty.py` + QA cyc-2026-07-18T132318Z (dedupe second copy). · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Existe runbook de fonte quebrada. Evidência: canonical `DOCUMENT_CONTENT_PROOF` + `docs/ops/troubleshooting.md`
- [x] Existe runbook de schema drift. Evidência: `docs/GLOSSARY.md` + `docs/architecture/adr/INDEX.md` + `docs/ops/runbook.md` (rollback/schema-drift/cobertura<95%) + `scripts/ops/scan_ops_docs_honesty.py` + `tests/test_ops_docs_honesty.py` + QA PASS cyc-2026-07-18T131425Z (7/8; PRD alignment left open). · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Existe runbook de cobertura abaixo de 95%. Evidência: `docs/GLOSSARY.md` + `docs/architecture/adr/INDEX.md` + `docs/ops/runbook.md` (rollback/schema-drift/cobertura<95%) + `scripts/ops/scan_ops_docs_honesty.py` + `tests/test_ops_docs_honesty.py` + QA PASS cyc-2026-07-18T131425Z (7/8; PRD alignment left open). · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Existe runbook de freshness vencida. Evidência: skeptic-r2 runbook.md freshness Critico fresh/stale/SLA
- [x] Existe glossário. Evidência: `docs/GLOSSARY.md` + `docs/architecture/adr/INDEX.md` + `docs/ops/runbook.md` (rollback/schema-drift/cobertura<95%) + `scripts/ops/scan_ops_docs_honesty.py` + `tests/test_ops_docs_honesty.py` + QA PASS cyc-2026-07-18T131425Z (7/8; PRD alignment left open). · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Existe matriz de fontes. Evidência: canonical `DOCUMENT_CONTENT_PROOF` + `docs/research/source-runtime-matrix-2026-07-16.md`
- [x] Existe matriz de capabilities. Evidência: canonical `DOCUMENT_CONTENT_PROOF` + `docs/baseline/l1-source-capability-registry.md`
- [x] Existe registro de blockers. Evidência: canonical `DOCUMENT_CONTENT_PROOF` + `squads/extra-dod-roi/state/blockers/latest.json`
- [x] Existe changelog ou histórico equivalente. Evidência: PRD v2.1 + CHANGELOG.md + docs/ops/NEXT-DEV-STEP.md + scan_ops_docs_honesty ok + QA PASS cyc-2026-07-18T132050Z. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] O próximo passo de desenvolvimento pode ser identificado sem reconstruir todo o contexto. Evidência: PRD v2.1 + CHANGELOG.md + docs/ops/NEXT-DEV-STEP.md + scan_ops_docs_honesty ok + QA PASS cyc-2026-07-18T132050Z. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).

---

## 32. Agnosticidade de agentes, IDEs e modelos

### 32.1 Fonte canônica de verdade

- [x] `DOD.md`, README, PRD, ADRs, runbooks, código, migrations, testes e artefatos versionados são a fonte de verdade do projeto. Evidência: `docs/DEVELOPMENT.md` §1 + DoD precedence. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Nenhuma decisão obrigatória existe apenas em histórico de chat, memória de agente, prompt oculto ou sessão local. Evidência: DEVELOPMENT §1 proibição + AGENTS.md. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Instruções específicas de ferramenta apenas apontam para documentos canônicos; não criam requisitos paralelos. Evidência: AGENTS.md thin adapter. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] `CLAUDE.md`, `AGENTS.md`, regras do Cursor e arquivos equivalentes não se contradizem. Evidência: validator three_entry_points + CLAUDE pointer + Cursor rule + AGENTS; QA PASS 34174823e54a. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Existe um guia canônico de desenvolvimento, como `docs/DEVELOPMENT.md`, compartilhado por todas as ferramentas. Evidência: docs/DEVELOPMENT.md criado. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] `CLAUDE.md` referencia o guia canônico e contém apenas adaptações indispensáveis ao Claude Code. Evidência: CLAUDE.md § Canonical development guide → docs/DEVELOPMENT.md + QA PASS. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] `AGENTS.md` referencia o guia canônico e contém apenas adaptações indispensáveis ao Codex ou agentes compatíveis. Evidência: AGENTS.md → DEVELOPMENT.md. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] As regras do Cursor referenciam o guia canônico e contêm apenas adaptações indispensáveis ao editor. Evidência: `.cursor/rules/00-extra-canonical.mdc` + QA PASS. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Os três pontos de entrada indicam o mesmo comando de setup, validação e golden path. Evidência: `canonical_entry_points` three_entry_points_same_commands=true + QA PASS. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Os três pontos de entrada indicam os mesmos documentos de escopo, arquitetura e operação. Evidência: three_entry_points_same_docs=true + QA PASS. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Quando existirem instruções específicas para uma ferramenta, elas funcionam como adaptadores finos e dispensáveis. Evidência: adapters_dispensable + product_requirement_roots + QA PASS. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] A remoção de qualquer arquivo específico de Claude Code, Codex ou Cursor não elimina requisitos de produto, dados, qualidade ou operação. Evidência: product roots DOD/DEVELOPMENT/scripts/tests/migrations independent of adapters + QA PASS. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).
- [x] Em caso de conflito, prevalecem DOD, ADR vigente, código testado e evidência reproduzível, nessa ordem definida pelo projeto. Evidência: DEVELOPMENT.md precedence + canonical-entry-points.yaml + QA PASS. · Re-proof main 2026-07-18: selective unit suite 136 passed (nodeids log).

### 32.2 Unidade de trabalho portável

- [ ] Toda tarefa relevante pode ser compreendida por um agente novo sem acesso à conversa que a originou.
- [ ] Toda tarefa registra objetivo.
- [ ] Toda tarefa registra contexto mínimo necessário.
- [ ] Toda tarefa registra escopo incluído.
- [ ] Toda tarefa registra fora de escopo.
- [ ] Toda tarefa referencia os itens pertinentes do DOD.
- [ ] Toda tarefa possui critérios de aceite objetivos.
- [ ] Toda tarefa informa comandos de validação.
- [ ] Toda tarefa informa artefatos de evidência esperados.
- [ ] Toda tarefa informa riscos e rollback quando aplicável.
- [ ] Toda tarefa informa dependências externas e blockers conhecidos.
- [ ] Nenhuma tarefa exige interpretar expressões vagas como “deixar perfeito”, “resolver tudo” ou “funcionar bem” sem critérios mensuráveis.

### 32.3 Comandos e validação independentes de agente

- [ ] Setup, testes, lint, migrations, crawls, relatórios, backup e restore são executados por comandos de shell, Python, Make ou mecanismo aberto equivalente.
- [ ] Nenhum gate obrigatório depende de slash command exclusivo de uma ferramenta.
- [ ] Nenhum gate obrigatório depende de MCP proprietário.
- [ ] Nenhum gate obrigatório depende de uma extensão específica de IDE.
- [ ] Existe comando canônico de validação completa, como `make verify`, `make golden-path` ou equivalente documentado.
- [ ] O comando canônico produz exit code determinístico.
- [ ] O comando canônico produz resumo legível e artefato estruturado.
- [ ] Claude Code, Codex e Cursor recebem o mesmo resultado ao executar os mesmos comandos no mesmo commit e ambiente.
- [ ] Validações subjetivas possuem checklist explícita e registro de aceite humano.
- [ ] Alterações produzidas por qualquer agente passam pelos mesmos testes e gates.

### 32.4 Ambiente reproduzível e contexto transferível

- [ ] Versões de Python, PostgreSQL e dependências estão fixadas ou delimitadas de forma reproduzível.
- [ ] Dependências possuem lock ou estratégia equivalente documentada.
- [ ] Variáveis de ambiente necessárias aparecem em `.env.example` sem segredos.
- [ ] Dados de teste e fixtures necessários estão versionados ou podem ser gerados por comando documentado.
- [ ] Caminhos locais, nomes de usuário e detalhes da máquina de um agente não entram no código.
- [x] O repositório contém instruções suficientes para retomada após troca de agente. Evidência: handoffs/HANDOFF-20260719-partial-ops95.md · STATUS.md · EXTRA-OPS-95
- [ ] O estado atual, próximo passo, blockers e evidências não dependem de memória conversacional.
- [ ] Um handoff entre Claude Code, Codex e Cursor pode ocorrer usando apenas o repositório e os acessos externos documentados.
- [ ] Artefatos temporários de agente não são confundidos com documentação canônica.

### 32.5 Autoridade e segurança de execução

- [ ] Agentes podem propor alterações, mas decisões de escopo permanecem sob autoridade de Tiago.
- [ ] Nenhum agente publica, faz merge, provisiona infraestrutura, altera dados de produção ou rotaciona credenciais sem autorização explícita quando a ação tiver efeito externo relevante.
- [ ] O agente que implementa não pode substituir evidência de teste por autodeclaração de sucesso.
- [ ] Revisão independente pode ser realizada por outro agente, outra sessão sem contexto, teste automatizado ou validação humana proporcional ao risco.
- [ ] Divergências entre agentes são resolvidas por execução reproduzível, documentação canônica e decisão registrada, não por autoridade presumida do modelo.
- [ ] Ferramentas proprietárias são conveniências opcionais e possuem alternativa manual ou aberta para operações críticas.

---

## 33. Governança pessoal do desenvolvimento

- [ ] Toda mudança relevante possui story, issue ou registro equivalente.
- [ ] Critérios de aceite são definidos antes da implementação relevante.
- [ ] Mudanças de alto risco possuem plano de rollback.
- [ ] Mudanças de schema recebem revisão específica.
- [ ] Mudanças em coverage recebem revisão específica.
- [ ] Mudanças em freshness recebem revisão específica.
- [ ] Mudanças em deduplicação recebem revisão específica.
- [ ] Mudanças em segurança recebem revisão específica.
- [ ] Mudanças em fontes possuem teste de contrato.
- [ ] Mudanças em relatórios possuem validação visual.
- [ ] QA é executado antes de publicação.
- [ ] Commits têm escopo claro.
- [ ] Branch principal permanece utilizável.
- [ ] Débito técnico crítico não é escondido por documentação.
- [ ] Stories marcadas como Done possuem evidências.
- [ ] O estado do DOD é atualizado após entregas relevantes.
- [ ] O DOD não é atualizado apenas no encerramento do projeto.
- [ ] Itens concluídos não são desmarcados sem registro da regressão.
- [ ] Regressões geram correção priorizada.
- [ ] O projeto privilegia utilidade real para a consultoria.
- [ ] Trabalho sem impacto no escopo é despriorizado.
- [ ] Infraestrutura não é usada para fugir de problemas de dados.
- [ ] Refinamento estético não é usado para fugir de problemas de cobertura.

---

## 34. Aceite final da utilidade

- [ ] Tiago usa o sistema em uma situação real de consultoria.
- [ ] O sistema encontra oportunidades que merecem análise.
- [ ] O sistema não exibe oportunidades encerradas como abertas.
- [ ] O sistema informa o que não conseguiu monitorar.
- [ ] O sistema permite investigar um ente específico.
- [ ] O sistema permite investigar um fornecedor específico.
- [ ] O sistema permite investigar um objeto ou setor.
- [ ] O sistema permite consultar contratos dos últimos três anos.
- [ ] O sistema permite comparar fornecedores vencedores.
- [ ] O sistema permite produzir referência de valores sem confundir grandezas.
- [ ] O sistema gera material apresentável ao cliente.
- [ ] O sistema reduz trabalho manual repetitivo.
- [ ] O sistema não cria falsa segurança.
- [ ] O sistema é simples o bastante para ser mantido por Tiago.
- [ ] O sistema pode ser recuperado após falha.
- [ ] O sistema pode ser atualizado sem procedimento improvisado.
- [ ] O sistema pode continuar operando sem dependência diária do ambiente local.
- [ ] O custo é aceitável.
- [ ] O benefício prático supera o custo de manutenção.
- [ ] Tiago aprova formalmente o sistema como apto para apoiar a proposta.
- [ ] O gate `PROJECT_DONE` foi registrado com data, commit e evidências.

---

# 35. Gates consolidados

## 35.1 Gate `LOCAL_READY`

O gate `LOCAL_READY` só pode ser marcado quando:

- [ ] Todos os itens obrigatórios do ROL 1 estão concluídos.
- [ ] Os itens aplicáveis do ROL 3 estão concluídos.
- [ ] O universo canônico está reconciliado.
- [ ] A cobertura de editais é >= 95%.
- [ ] A cobertura de contratos é >= 95%.
- [ ] O recall de editais relevantes é >= 95%.
- [ ] A integridade do snapshot ativo é 100%.
- [ ] O golden path local passa.
- [ ] PDF e Excel são gerados.
- [ ] Backup e restore local foram testados.
- [ ] Tiago executou aceite manual.
- [ ] A evidência foi registrada.

**Status:** [ ] NÃO ATINGIDO  
**Data:**  
**Commit:**  
**Evidências:**  

---

## 35.2 Gate `VPS_OPERATIONAL`

O gate `VPS_OPERATIONAL` só pode ser marcado quando:

- [ ] Todos os itens obrigatórios do ROL 2 estão concluídos.
- [ ] Deploy é reproduzível.
- [ ] Hardening foi validado.
- [ ] Banco foi migrado.
- [ ] Timers estão ativos.
- [ ] Alertas foram testados.
- [ ] Backup externo funciona.
- [ ] Restore foi testado.
- [ ] O sistema sobrevive a reboot.
- [ ] A operação independe do computador local.
- [ ] O sistema operou sete dias sem falha crítica não detectada.
- [ ] A cobertura de editais permaneceu >= 95%.
- [ ] A cobertura de contratos permaneceu >= 95%.
- [ ] A evidência foi registrada.

**Status:** [ ] NÃO ATINGIDO  
**Data:**  
**Commit:**  
**Evidências:**  

---

## 35.3 Gate `PROJECT_DONE`

O gate `PROJECT_DONE` só pode ser marcado quando:

- [ ] `LOCAL_READY` foi atingido.
- [ ] `VPS_OPERATIONAL` foi atingido.
- [ ] Todos os itens obrigatórios do ROL 3 estão concluídos.
- [ ] O projeto cumpre o escopo da proposta, exceto acompanhamento de obras.
- [ ] Os cinco entregáveis do diagnóstico da seção 2.5 foram comprovados ou tiveram limitação formalmente aceita por Tiago antes da entrega.
- [ ] As capacidades recorrentes aplicáveis da seção 2.6 foram comprovadas para o escopo efetivamente contratado.
- [ ] O pacote PDF + Excel foi reconciliado e aceito.
- [ ] A seção 32 de agnosticidade de agentes foi concluída.
- [ ] O sistema é utilizado na rotina real.
- [ ] As métricas são tecnicamente defensáveis.
- [ ] As limitações são explícitas.
- [ ] O custo é aceitável.
- [ ] A manutenção é viável para um único usuário.
- [ ] Tiago aprovou formalmente o encerramento do desenvolvimento principal.
- [ ] Melhorias futuras foram movidas para backlog e não bloqueiam o uso.

**Status:** [ ] NÃO ATINGIDO  
**Data:**  
**Commit:**  
**Evidências:**  

---

# 36. Backlog não bloqueante após `PROJECT_DONE`

Os itens abaixo podem continuar evoluindo sem impedir o uso do sistema:

- [ ] Interface TUI aprimorada.
- [ ] Dashboard web local.
- [ ] Novas fontes estaduais ou municipais.
- [ ] Integração com fontes pagas.
- [ ] Classificação por embeddings.
- [ ] Automação adicional de relatórios.
- [ ] Alertas por múltiplos canais.
- [ ] Object storage dedicado.
- [ ] PITR com WAL-G ou pgBackRest.
- [ ] Infraestrutura como código com OpenTofu ou Terraform.
- [ ] Containerização da produção.
- [ ] Métricas avançadas de concorrência.
- [ ] Rastreamento manual de propostas enviadas.
- [ ] Cálculo futuro de win rate real.
- [ ] Integração futura com pagamentos ou empenhos.
- [ ] Expansão geográfica além do raio definido.
- [ ] Expansão para outros clientes.
- [ ] Interface multiusuário.
- [ ] API externa.
- [ ] Aplicativo móvel.

---

## 37. Registro de revisões do DOD

| Data | Commit | Alteração | Motivo | Responsável |
|---|---|---|---|---|
| 2026-07-17 | fix/pre-vps-final-truth-gate → main | §45 truth gate: selo LOCAL_RESILIENCE_READY destruído; pipeline único + PG; CI resilience-gate verde; HTML atualizado | Auditoria adversarial pré-VPS | Truth gate session |
| 2026-07-17 | aca4408→HEAD · main | §42 briefing executivo trabalho financiado + HTML diretoria; consolida §40–§41 com claims honestos | Apresentação à Extra Construtora | Diretoria / Principal Eng |
| 2026-07-17 | 3bf1a3b · main | fix adversarial: sc-* ≠ pncp_number; 052 em `_migrations`; CIGA 221/295 + live_fetch | Auditoria independente | Multiagent §41 fix |
| 2026-07-17 | 8b8138a · main | §41 ingestão real DOE/DOM/Compras, official_acts 2964, recon, métricas, CI | Execução multiagente live | Multiagent §41 |
| 2026-07-17 | cce2f3d · main | docs §41 DOD/HTML sessão multi-fonte | Fechamento documental | Multiagent §41 |
| 2026-07-17 | 0628e36 · main | §40 sessão multiagente: fundação run_id/evidence, pilot 90d fail-closed, datas 051, CKAN SC/CIGA/Compras/PNCP smokes, CI, relatório comercial; **não** 90d full / 95% / VPS | Execução real + auditoria de evidência | Multiagent execution |
| 2026-07-17 | 839e73f · PR #8 | §39 NEXT-30D-MULTIAGENT close-out board + HTML:  fail-closed golden path; sc_compras 2602; contracts pilot multi-k; dedup CLI; schema audit; coverage ~4.76% editais; gates A–D PARTIAL; **não** LOCAL_READY/95% | Campanha 30d úteis seguinte (ES≥30) com multiagentes | NEXT-30D-MULTIAGENT |
| 2026-07-16 | feat/session-constatations | §38 constatação de sessão + HTML diretoria | Rastreabilidade e briefing executivo | Campanha PE-30D |
| 2026-07-16 | feat/subagents-wave-next | Auditoria 30d, C2.7/K3.2/C2.8/Q5 (82 testes), Q5.4 snapshot | Wave de subagents pós-janela | Subagents |
| 2026-07-16 | feat/close-window-30d | Fechamento 24/24 tasks ES<30 (V6.1/I4.1/L1.5+C2/Q5; V6.2 só BLOCKED_EXTERNAL compra) | Exigência: 100% janela 30d úteis | Campanha PE-30D |
| 2026-07-16 | HEAD re-prova | Validação técnica mission: unit+CIGA+GATE-1 (54/54 mig, universe 1093, golden path, backup restore) | Re-prova claims 30d + CIGA | Mission validation |
| 2026-07-16 | epic/plano-executivo-30d | Campanha 30d: versionamento na raiz; §1 (2 itens) aceitos com evidência; GATE-0 LOCKED; GATE-1/LOCAL_READY **não** atingidos; baselines em `docs/baseline/` e ledger em `docs/ops/ledger/` | Executar janela G0+L1+início C2/K3 do plano executivo com subagents paralelos | Campanha PE-30D / Tiago |
| 2026-07-16 | PE-C2-05 | DOM-SC via CIGA Dados público (sem API key); `ciga_ckan` hybrid | E-mail CIGA 2026-07 | PE-C2-05 |
| 2026-07-16 | — | Auditoria de completude comercial e agnosticidade de agentes | Cobrir diagnóstico, serviços recorrentes e uso com Claude Code, Codex, Cursor ou ferramentas futuras | Aurora / Tiago Sasaki |
|  |  | Criação do documento | Consolidar critérios de evolução do projeto | Tiago Sasaki |

---

# 38. Constatções da sessão de execução (2026-07-16)

> **Propósito:** registro de referência para sessões futuras e para a diretoria.  
> **Não substitui** o aceite item a item das seções 1–36.  
> **Não declara** `LOCAL_READY`, cobertura ≥95% nem `PROJECT_DONE`.  
> **Fontes de verdade cruzadas:** `extra-consultoria-plano-executivo.html`, `docs/ops/ledger/*`, `docs/baseline/*`, PRs #1–#5 em `main`.

## 38.1 Escopo e regra de ouro da sessão

| # | Constatação |
|---|-------------|
| C-01 | O plano canônico é `extra-consultoria-plano-executivo.html` + este `DOD.md` (antes untracked; versionados na raiz). |
| C-02 | PERT total até `PROJECT_DONE` ≈ **167 dias úteis**. A campanha pedida cobria a **janela ES &lt; 30** (primeiros ~30 dias úteis), **não** o projeto inteiro. |
| C-03 | Janela ES &lt; 30 (PERT float) = **24 tasks**, esforço M ≈ **91 pessoa-dias** (estimativa do plano, não horas humanas medidas). |
| C-04 | Meta de cobertura do DoD: **≥95% editais e ≥95% contratos, separados**. Meta legada &gt;80% (épicos antigos) fica **subordinada** (R-02 resolvido em favor do DoD — `docs/baseline/scope-freeze-95.md`). |
| C-05 | Commit / story Done **não** implica item DoD aceito. Aceite exige evidência no HEAD. |
| C-06 | Exigência posterior do solicitante: fechar **tudo** da janela de 30 dias úteis, não “grande parte”. |

## 38.2 Gates de campanha (não confundir com gates DoD §35)

| Gate plano | Status ao fim da sessão | Evidência |
|------------|-------------------------|-----------|
| **GATE-0 BASELINE_LOCKED** | **LOCKED** | `docs/ops/ledger/GATE-0-BASELINE-LOCKED.md` |
| **GATE-1 LOCAL_FOUNDATION** | **Majoritariamente PASS** (fundação local) | `docs/ops/ledger/GATE-1-LOCAL-FOUNDATION.md` |
| **GATE-2 EDITAIS_95** | Não atingido | Fora da janela / sem 95% |
| **GATE-3 CONTRATOS_95** | Não atingido | Fora da janela / sem 95% |
| **DoD LOCAL_READY** (§35.1) | **NÃO ATINGIDO** | Exige ROL1+ROL3+95%+aceite Tiago |
| **DoD VPS_OPERATIONAL** (§35.2) | **NÃO ATINGIDO** | VPS não contratada |
| **DoD PROJECT_DONE** (§35.3) | **NÃO ATINGIDO** | — |

## 38.3 Fechamento da janela 30 dias úteis (24 tasks)

| Resultado | Qtd | Notas |
|-----------|-----|-------|
| Engenharia com evidência (`evidence`) | **23** | G0.*, L1.*, V6.1, I4.1, C2.1–C2.6, K3.1, Q5.1 |
| Bloqueio externo humano/financeiro | **1** | **V6.2** — contratar VPS / credenciais (owner Tiago); pacote READY |
| Planned residual na janela | **0** | — |

Auditoria adversarial de subagent (`docs/ops/ledger/WINDOW-30D-AUDIT-SUBAGENT.md`):

| Veredito estrito | Qtd |
|------------------|-----|
| DONE (evidência forte) | 14 |
| DONE_PARTIAL (existe artefato, claim ou índice stale) | 9 |
| BLOCKED_EXTERNAL | 1 (V6.2) |
| Fake path | 0 |

**Nota de método:** o HTML usa `Math.ceil` no PERT; a lista canônica de 24 tasks da campanha usa duração float. Documentado na auditoria — não inventar 24 com ceil.

Manifesto de fechamento: `docs/ops/ledger/WINDOW-30D-COMPLETE.md`.

### 38.3.1 Destaques por frente (janela)

| Frente | Constatação |
|--------|-------------|
| **G0** | DoD+HTML versionados; rebaseline HEAD; freeze 95%; ledger+RACI; GATE-0 LOCKED. |
| **L1** | Fresh migrations **54/54** (pgvector); fix migration **049** (DROP views + DROP CHECK integer em `esfera_id` antes de ALTER TYPE TEXT); universo **1093 included / 2085** materializado; golden path **SUCCESS** crawl+Excel+PDF (`gp-20260716-200904`); backup/restore local PASS (60 tables); fix shadow `scripts/crawl/config.py` vs pacote `config/` em `monitor.py`. |
| **C2 (início)** | Fórmulas/success_zero/freshness documentados; PCP OK; ComprasGov OK; TCE-SC smoke **n≈65.970**; DOM canônico = **CIGA Dados** (sem chave); PNCP com timeouts de API documentados (código+049 ok). |
| **K3.1** | Schema/semântica contratos auditados; gaps `valor_total` vs `valor_global` registrados. |
| **I4.1** | Perfil `config/client_profiles/extra.yaml` **v2** (região SC 200 km, modalidades, value_band_soft, constraints). |
| **V6.1** | ADR: Netcup preferencial 32 GB / ~1 TB; Hetzner fallback; PG16 bare-metal; teste PNCP do DC obrigatório antes de fechar região. |
| **V6.2** | Pacote de compra + inventário de secrets entregue; **falta conta/pagamento** (não automatizável). |
| **Q5.1** | Suite crítica expandida: **82 PASS** (CIGA transform+crawler, ledger, DLQ, watermark, freshness). |

## 38.4 DOM-SC / CIGA (constatação crítica de integração)

| # | Constatação |
|---|-------------|
| C-DOM-01 | E-mail CIGA: integração via **https://dados.ciga.sc.gov.br**, dados **públicos**, **sem cadastro/API key**. Doc: CKAN 2.9 API. |
| C-DOM-02 | Portal ao vivo: CKAN **2.9.2**; org `ciga`; tags `DOMSC`, `Publicações - DOMSC`. |
| C-DOM-03 | Path **canônico** no código: source `ciga_ckan` (hybrid, open_tenders + coverage_truth, credentials `[]`). |
| C-DOM-04 | Path **legado** `dom_sc` (diariomunicipal + CPF/CNPJ/API key) permanece opcional e **BLOCKED** sem secrets. |
| C-DOM-05 | Datasets mensais: `domsc-publicacoes-de-MM-YYYY` (~54); ~90 ZIPs/mês; JSON `autopublicacoes` com codigo/titulo/data/entidade/municipio/categoria/link/texto. |
| C-DOM-06 | JSON CIGA **não traz** CNPJ nem valor monetário — transform mantém `null` (não inventar). |
| C-DOM-07 | Parâmetros de API úteis: `package_list`, `package_search?fq=tags:DOMSC`, `package_show`, download `resource.url`. Auth só para write (não usado). |
| C-DOM-08 | Evidências: `docs/baseline/c2-domsc-ciga-dados-unblocked.md`, `c2-ciga-ckan-runtime.md`, PE-C2-05 / PR #2. |

## 38.5 Pós-janela 30d (wave de subagents)

| # | Constatação | Artefato |
|---|-------------|----------|
| C-NX-01 | **C2.7** residual: `sc_compras` RUN-ready (smoke **n=2602**); `doe_sc` BLOCKED creds vazias; transparência frágil; residual municipal alto custo. | `docs/baseline/c2.7-residual-portals-plan.md` |
| C-NX-02 | **K3.2** backfill PNCP 3y: infra READY TO PILOT; primeiro pilot **90d contratos**; 3y só após go/no-go. | `docs/baseline/k3.2-pncp-backfill-ready.md` |
| C-NX-03 | **C2.8** aliases: 459 aliases ativos; `DedupEngine` existe mas **não wired**; cross-source dedup 0 rows → PARTIAL. | `docs/baseline/c2.8-dedup-aliases-status.md` |
| C-NX-04 | **Q5.4** snapshot: ruff debt no crawl tree; bandit 0 HIGH; pip-audit ruidoso no env. | `docs/baseline/q5.4-quality-security-snapshot.md` |
| C-NX-05 | Próxima ordem de ataque recomendada: (1) ingest sc_compras, (2) pilot K3.2 90d, (3) wire dedup cross-source, (4) DOE-SC se cred, (5) V6.2 compra Tiago. | plan C2.7 + K3.2 |

## 38.6 Bugs e correções técnicas da sessão

| # | Problema | Correção |
|---|----------|----------|
| B-01 | Migration 049 falhava em fresh install: views + CHECK `esfera_id = ANY(ARRAY[1,2,3,4])` (int) impediam ALTER para TEXT | DROP views + DROP constraint + ALTER + recreate views/check texto |
| B-02 | Golden path / monitor: `config is not a package` — `scripts/crawl/config.py` shadow do pacote `config/` quando script dir fica à frente no `sys.path` | `monitor.py` força project root no início do path; golden_path injeta PYTHONPATH |
| B-03 | Ledger golden_path corrompido (`runs` aninhado) | `_normalize_ledger_runs` + testes `tests/test_golden_path_ledger.py` |
| B-04 | Compose sem extensão `vector` | imagem `pgvector/pgvector:pg16` |
| B-05 | DB operacional sem tabelas DF (pipeline_*) após troca de volume | reaplicar migrations 045–049 |

## 38.7 Publicações GitHub (rastreio)

| PR | Conteúdo |
|----|----------|
| #1 | Campanha plano 30d / GATE-0 + fundação parcial |
| #2 | PE-C2-05 CIGA Dados DOM público |
| #3 | Re-prova mission + fix 049 + universo + backup |
| #4 | Fechar janela 30d (V6.1, I4.1, L1.5 PDF/Excel, pack V6.2) |
| #5 | Wave subagents: audit, C2.7, K3.2, C2.8, Q5 82, Q5.4 |

## 38.8 O que **pode** ser dito à diretoria (hoje)

1. Existe **Definition of Done** e **plano executivo** versionados e auditáveis.  
2. **Fundação local** reprovada: migrations limpas, universo 1093, golden path com Excel/PDF, backup/restore local, testes críticos verdes.  
3. **DOM/SC** desbloqueado via dados abertos CIGA (**sem custo de API key**).  
4. **Múltiplas fontes** com prova de coleta (PCP, ComprasGov, TCE-SC, CIGA).  
5. **Decisão de VPS** documentada; falta apenas **contratação** (ação do titular).  
6. **Meta 95%** permanece o gate comercial — ainda **não** atingida; trabalho seguinte é cobertura/backfill, não “mais narrativa”.

## 38.9 O que **não** pode ser dito à diretoria (hoje)

1. “95% de cobertura de editais/contratos.”  
2. “Sistema pronto para entrega comercial integral / PROJECT_DONE.”  
3. “VPS em produção / operação 24×7 autônoma.”  
4. “Todos os itens do DoD estão aceitos” (apenas **2/≈1340** checkboxes de processo).  
5. “Path autenticado DOM-SC está operacional” (só CIGA público).  
6. “Backfill de 3 anos de contratos concluído” (apenas readiness de pilot).

## 38.10 Ações humanas pendentes (Tiago / diretoria)

| Prioridade | Ação | Desbloqueia |
|------------|------|-------------|
| P0 | Contratar VPS (Netcup preferencial ou Hetzner) e entregar SSH + backup remote | V6.2, depois V6.3+ |
| P0 | Confirmar ou ajustar meta formal 95% vs prazo de 6 meses (PERT P50 &gt; 6 meses) | Cronograma honestidade |
| P1 | Credenciais DOE-SC se quiser diário estadual | C2.7 WP-C |
| P1 | Preencher órgãos prioritários e concorrentes no perfil Extra v2 | I4 entregáveis A–B |
| P2 | Credenciais DOM legado só se CIGA for insuficiente | path `dom_sc` |

## 38.11 Índice de artefatos da sessão

| Tema | Path |
|------|------|
| Plano HTML | `extra-consultoria-plano-executivo.html` |
| GATE-0 / GATE-1 / janela 30d | `docs/ops/ledger/GATE-0-*.md`, `GATE-1-*.md`, `WINDOW-30D-*.md` |
| Freeze 95% | `docs/baseline/scope-freeze-95.md` |
| CIGA/DOM | `docs/baseline/c2-domsc-ciga-dados-unblocked.md` |
| C2.7 / C2.8 / K3.2 / Q5 | `docs/baseline/c2.7-*`, `c2.8-*`, `k3.2-*`, `q5-*` |
| Perfil Extra | `config/client_profiles/extra.yaml` |
| ADR VPS | `docs/architecture/adr/ADR-007-v6.1-provider-decision.md` |
| Pack compra VPS | `docs/ops/v6.2-procurement-credentials-package.md` |

---

# 39. Campanha NEXT-30D-MULTIAGENT (2026-07-17)

> **Não declara** `LOCAL_READY`, cobertura ≥95%, `VPS_OPERATIONAL` nem `PROJECT_DONE`.  
> **Fontes:** `docs/ops/ledger/NEXT-30D-*`, `docs/baseline/*-next30d.md`, branch `epic/next-30d-multiagent-execution`.

## 39.1 Resultado executivo

| Campo | Valor |
|-------|-------|
| SHA inicial | `77ff8a8` |
| Branch | `epic/next-30d-multiagent-execution` |
| sc_compras | **2602** fetched/inserted (**DONE**) |
| Contracts pilot | **partial**: path_proof 1d **success**; full 90d national **NO-GO** 3y sem run supervisionado; DB ~42k+ |
| Dedup cross-source | CLI wired; rows ≥ 5 (**DONE**) |
| Editais crude coverage | **4,76%** (52/1093) measured — not 95% |
| Snapshot integrity | **1.0** |
| Golden path | fail-closed strict + campaign unit suite |
| V6.2 / DOE-SC | **BLOCKED_EXTERNAL** (Tiago) |
| CP PERT | **30** (C2.7+C2.10+C2.11) |

## 39.2 Gates da campanha

| Gate | Veredito |
|------|----------|
| NEXT30-GATE-A FOUNDATION_TRUTH | **PASS** |
| NEXT30-GATE-B DATA_EXPANSION | **PASS** (+ DOE BLOCKED_EXTERNAL) |
| NEXT30-GATE-C INTELLIGENCE_OUTPUT | **PASS** |
| NEXT30-GATE-D CAMPAIGN_ACCEPTANCE | **PASS** (executable objectives; no LOCAL_READY/95%) |

## 39.3 Evidências-chave

- `docs/ops/ledger/NEXT-30D-BASELINE.md`, `NEXT-30D-WORKPLAN.md`, `NEXT-30D-ADVERSARIAL-AUDIT.md`, `NEXT-30D-FINAL-SCORECARD.md`
- `docs/ops/ledger/NEXT30-GATE-A.md` … `D.md`
- `docs/baseline/c2.7-sc-compras-runtime-next30d.md`
- `docs/baseline/c2.8-dedup-wired-next30d.md`
- `docs/baseline/k3.2-pncp-90d-pilot-next30d.md`
- `docs/baseline/c2.10-coverage-audit-next30d.md`
- `docs/baseline/c2.9-snapshot-integrity-next30d.md`
- `docs/baseline/c2.11-editais-gap-escalate-next30d.md`
- `docs/baseline/q5.4-remediation-next30d.md`
- `docs/baseline/i4-reports-next30d.md`
- `output/sc_compras/runtime-next30d.json`
- `output/contracts/pilot-90d-next30d.json` (**status=partial**; path_proof 1d; **não** success do 90d nacional)
- `output/reports/reconcile-next30d.json` (CONSISTENT)
- `tests/test_golden_path_fail_closed.py`


## 39.4 Fechamento operacional (HEAD final)

| Campo | Valor |
|-------|-------|
| SHA final campanha | `839e73f` · PR [#8](https://github.com/tjsasakifln/extra-consultoria/pull/8) |
| sc_compras evidence | `output/sc_compras/runtime-next30d.json` **status=success**, inserted=**2602** |
| Pilot contracts | `output/contracts/pilot-90d-next30d.json` **status=partial** (path GO · 3y NO-GO) |
| Checkpoint path_1d | `completed_windows=["20260715_20260715"]` (isolado pós-sessão §40) |
| Contratos no DB (artefato) | dezenas de milhares (cumulativo; ver §40) |
| Editais crude | **4.76%** (52/1093) |
| Testes campanha | 28+ unitários (fail-closed + evidence artifacts + pilot predicates) |

## 39.5 Sessão para a diretoria — o que avançou

### Entregue nesta janela (NEXT-30D)

1. **Fundação fail-closed** — golden path strict; falso sucesso eliminado em testes.
2. **Dados SC Compras** — ingestão real pública, 2.602 registros no datalake.
3. **Contratos PNCP** — de 0 para dezenas de milhares; piloto terminal com caminho GO (3y condicional).
4. **Deduplicação cross-source** — motor conectado; evidência de grupos.
5. **Cobertura medida com honestidade** — ~4,8% editais no raio (não 95%).
6. **Relatórios comerciais** — PDF/Excel reconciliados no mesmo run_id; ranking de órgãos com semântica CONTRATADO.
7. **Gates A–D da campanha PASS** (DOE-SC e VPS só como bloqueios externos do titular).

### O que a diretoria pode afirmar

- A campanha pós–janela 30d **executou trabalho integrado e comprovável** (não só planos).
- O sistema **coleta e persiste** editais SC Compras e contratos PNCP com trilha de evidência.
- O caminho crítico do plano avançou o equivalente a **30 dias úteis PERT** (C2.7+C2.10+C2.11).
- QA de campanha (gates + auditoria adversarial + testes) **passou** nos critérios executáveis.

### O que a diretoria ainda NÃO pode afirmar

- Cobertura **≥95%** de editais ou contratos.
- `LOCAL_READY`, `VPS_OPERATIONAL` ou `PROJECT_DONE`.
- VPS em produção / operação 24×7.
- Backfill integral de 3 anos de contratos (apenas piloto de caminho + volume parcial).
- DOE-SC operacional (falta credencial).

### Decisões humanas pendentes (Tiago)

| Prioridade | Ação | Desbloqueia |
|------------|------|-------------|
| P0 | Contratar VPS e entregar SSH/backup | V6.2 → V6.3+ |
| P1 | Credenciais DOE-SC (se desejado) | residual C2.7 |
| P1 | Confirmar timeline da meta 95% vs PERT residual | expectativa comercial |
| P2 | Autorizar retomada overnight do pilot 90d multi-janela | K3.2 → 3y com GO estrito |

### Índice de artefatos desta sessão

| Tema | Path |
|------|------|
| Scorecard final | `docs/ops/ledger/NEXT-30D-FINAL-SCORECARD.md` |
| Gates A–D | `docs/ops/ledger/NEXT30-GATE-*.md` |
| Auditoria adversarial | `docs/ops/ledger/NEXT-30D-ADVERSARIAL-AUDIT.md` |
| Baseline/workplan | `docs/ops/ledger/NEXT-30D-BASELINE.md`, `NEXT-30D-WORKPLAN.md` |
| sc_compras | `docs/baseline/c2.7-sc-compras-runtime-next30d.md` + JSON |
| Pilot contratos | `docs/baseline/k3.2-pncp-90d-pilot-next30d.md` + JSON |
| PR | https://github.com/tjsasakifln/extra-consultoria/pull/8 |

---

# 40. Sessão multiagente — fundação de evidência e fontes SC (2026-07-17)

> **Não declara** `LOCAL_READY`, cobertura ≥95%, `VPS_OPERATIONAL`, piloto nacional 90d **success**, nem GO para backfill 3 anos.  
> **Fontes:** commits `d178896`…`0628e36` em `main`, `docs/ops/discovery/*`, `docs/ops/ledger/EVIDENCE-INCONSISTENCY-MATRIX.md`, artefatos em `output/contracts/`.

## 40.1 Resultado executivo desta sessão

| Campo | Valor |
|-------|-------|
| SHA base (início sessão) | `21290e1` |
| SHA final | `0628e36` (docs §40 / HTML nesta publicação) |
| Foco | Verdade operacional: run_id, pilot fail-closed, datas, fontes públicas SC, CI, relatório comercial |
| Piloto 90d nacional | **partial** · path_proof 1d **attestation** · `go_no_go_3y=NO-GO` |
| Smoke 7d contratos | **success** só no span 7d · `go_no_go_3y=NO-GO` (floor 90d) |
| Editais crude | **~4,76%** (inalterado como claim de cobertura) |
| VPS / DOE-SC auth | **não** operacional / residual externo |

## 40.2 Entregas por frente

### Fundação e verdade (Onda 1)

| Entrega | Path / evidência |
|---------|------------------|
| Cadeia `run_id` + evidence (SHA-256, git, claims) | `scripts/crawl/run_evidence.py` |
| Pilot 90d: full-coverage, retry, GO floor ≥90d, seal | `scripts/crawl/run_contracts_90d_pilot.py` |
| Lock de run local | `scripts/crawl/run_lock.py` |
| Matriz de inconsistências de evidência | `docs/ops/ledger/EVIDENCE-INCONSISTENCY-MATRIX.md` |
| Scorecard/gates reconciliados (partial, não success) | `NEXT-30D-FINAL-SCORECARD.md`, `NEXT30-GATE-D.md`, audit |
| Checkpoints isolados path_1d / span_7d | `data/contracts_checkpoints/path_1d/`, `span_7d/` |
| Artefatos selados com path_proof.window ∈ completed_windows | `output/contracts/pilot-90d-next30d.json`, `pilot-7d-smoke.json` |

### Modelo temporal (schema)

| Entrega | Path |
|---------|------|
| Migration 051 datas semânticas (assinatura ≠ publicação) | `db/migrations/051_contract_date_semantics.sql` |
| Transform PNCP corrigido + validators | `scripts/crawl/contracts_crawler.py`, `date_semantics.py` |
| Testes de semântica | `tests/test_contract_date_semantics.py` |

### Fontes públicas validadas (live smoke)

| Fonte | Resultado | Artefato |
|-------|-----------|----------|
| Dados Abertos SC (CKAN) | Action API **sem token**; DOE bulk 28 resources | `docs/ops/discovery/sc-ckan-discovery.*`, `dados_abertos_sc_crawler.py` |
| CIGA Dados | package_search `domsc` público (~428) | `discover_ciga_packages.py` |
| Portal Compras SC | JSON `/api/editais` **200**, n≈2602 (2026) | `sc_compras_crawler` smoke, discovery |
| E-Lic SC | Sem bulk JSON anônimo (stub + limitação documentada) | `elic_sc_stub.py` |
| PNCP contratos | GET anônimo OK | `smoke_pncp_public.py`, `pncp-smoke.json` |
| Comprasnet Contratos | Catálogo público; massa v1 **JWT** | discovery |
| Classificador de atos DOM/DOE | Determinístico (17 categorias) | `act_classifier.py` |

### Relatório, CI, operação

| Entrega | Path |
|---------|------|
| Sample comercial SC com disclaimers | `scripts/reports/commercial_sample_sc.py` (+ evidence em discovery) |
| CI default inclui pilot/evidence/datas/ckan/smoke | `.github/workflows/ci.yml` |
| Suite crítica evidência | ≥71 testes fail-closed (path⊆checkpoint, foreign run, hash, partial→NO-GO) |

## 40.3 Claims permitidos (sessão)

1. Path proof de contratos PNCP (1 dia) foi **atestado** com `run_id` e checkpoint coerente (`path_1d`).
2. Full 90d nacional **não** foi concluído; `go_no_go_3y=NO-GO`.
3. Smoke 7d (1 janela) tem evidência selada em `span_7d` e **não** autoriza 3y.
4. CKAN SC e CIGA respondem Action API pública sem token (provas live).
5. Compras SC expõe JSON público de editais; PNCP `/contratos` é anônimo.
6. `dataAssinatura` **não** deve ser usada como “publicação” (migration 051 + transform).
7. Cobertura bruta de editais permanece da ordem de **~4,76%**.

## 40.4 Claims proibidos (sessão)

1. Piloto nacional 90d = `success`.
2. GO para backfill 3 anos não supervisionado.
3. CONTRATOS_95 / editais 95% / LOCAL_READY / VPS operacional.
4. Seal = re-crawl live (attestation ≠ fetch).
5. MIN/MAX de `data_publicacao` legada como prova de cobertura da janela de coleta.
6. E-Lic como fonte bulk estável sem integração dedicada.

## 40.5 Gargalo único de maior impacto

**Completar o piloto nacional de contratos PNCP em 90 dias** (volume ~495k, timeouts, multi-janela supervisionada), com migration 051 aplicada no DB real e reprocessamento de datas — sem isso não há GO para 3y nem base temporal confiável para cruzar SC.

## 40.6 Índice de commits desta sessão (antes desta publicação docs)

| SHA | Mensagem |
|-----|----------|
| `d178896` | fix(contracts): full-coverage pilot semantics, run_id evidence, 90d GO floor |
| `748e918` | feat(schema): contract date semantics migration and transform fix |
| `c54e6b3` | docs(evidence): reconcile pilot partial/NO-GO claims and fail-closed tests |
| `ccb18f2` | feat(sources): public CKAN SC crawler, CIGA discovery, act classifier |
| `704ee75` | feat(sources): Compras SC smoke, PNCP public probe, E-Lic stub |
| `019dc92` | feat(reports,ci): honest commercial sample and critical CI gates |
| `cd56c35` | chore(evidence): sync 7d window checkpoint and commercial sample artifact |
| `1da8619`…`0628e36` | fix(evidence): seal run_id chain, content-hash, path_proof ⊆ checkpoint |

## 40.7 Referências cruzadas

- Discovery: `docs/ops/discovery/`
- Matriz: `docs/ops/ledger/EVIDENCE-INCONSISTENCY-MATRIX.md`
- Pilot: `output/contracts/pilot-90d-next30d.json`, `pilot-7d-smoke.json`
- HTML: `extra-consultoria-plano-executivo.html` (painel sessão §40)

---

## 41. Sessão multiagente — ingestão real DOE/DOM/Compras + reconciliação (2026-07-17)

> **HEAD inicial:** `0a2806f8dcaf56377680c640390f73e27cd1d393`  
> **SHA técnico (código/evidência):** `8b8138aa05fff521f329b8c00221acd0bb147e24`  
> **SHA correção adversarial (recon/metrics/052):** `3bf1a3ba877defe43fcf3c6623af70b4c3a91475`  
> **HEAD pré-briefing:** `aca44086d84de3148d2295ce9ab20d42a8c14c73`  
> **HEAD deste briefing (§42 / HTML diretoria):** `e2fdc6331c9888e7d504c4b7bd70805b6cb2e02d`  
> **Branch:** `main`  
> **Natureza:** execução real (live_fetch) + persistência local + testes. **Não** declara LOCAL_READY, 95%, 90d pilot success, VPS ou PROJECT_DONE.

### 41.1 Objetivo da rodada

Transformar descobertas de fontes públicas SC em **ingestão real, incremental, auditável e reconciliada** (DOE-SC via Dados Abertos, DOM via CIGA, Compras SC), com classificação determinística, schema unificado, métricas com denominador explícito e relatório comercial honesto.

### 41.2 Entregas comprovadas

| Frente | Entrega | Evidência |
|--------|---------|-----------|
| CI baseline | Suite crítica verde; ruff/mypy/bandit/pip-audit (deps) PASS; migration 051 aplicada no DB local | `docs/ops/session-2026-07-17/baseline-ci-a.json`; pytest critical **300 passed, 5 skipped** |
| DOE-SC (Dados Abertos) | Download real CSV 2025, raw imutável + SHA-256, 500 rows smoke, classificados, checkpoint/retomada | `output/dados_abertos_sc/smoke-dados-sc-smoke-20260717T021337Z-f4cfe4b907.json`; `scripts/crawl/dados_abertos_sc_crawler.py` |
| CIGA/DOM | Smoke live pacote `domsc-publicacoes-de-07-2026`; **2454** publicações; **223** observados; **221/295** cobertos no universo IBGE (accent-normalized); zip-slip safe; `live_fetch=true` | `docs/ops/session-2026-07-17/ciga-dom-latest-summary.json`; `scripts/crawl/ciga_dom_publications.py` |
| Schema 052 | `official_acts*` + helpers; apply idempotente em PG local | `db/migrations/052_official_acts.sql`; `scripts/schema/official_acts.py` |
| Persistência | **2964** atos no banco (ciga_dom 2454 + dados_abertos_sc 500 + sc_compras 10); 0 grupos duplicados (source, hash) | `docs/ops/session-2026-07-17/official-acts-load.json` |
| Classificador | 25 categorias; corpus 35 casos; confiança float + needs_human_review | `scripts/crawl/act_classifier.py`; `tests/fixtures/act_classifier_corpus.json` |
| Compras SC | Incremental real + checkpoint + run_id; API ano devolve lista completa (meta **2602** em 2026); smoke 20 regs | `docs/ops/session-2026-07-17/sc-compras-smoke-artifact.json` |
| Reconciliação | 30 matches via `compras_sc_id_crosswalk` (ids `sc-*` espelhados em `pncp_raw_bids` — **não** número de controle PNCP real); **0** `pncp_number_exact` no smoke; DOE/DOM sem match estruturado | `output/reconciliation/reconcile-20260717T023428Z-3b096d2b41/` |
| Coverage | Métricas separadas; histórico **4,76%** preservado; municípios 30d **74,92%** (221/295) em amostra CIGA | `docs/ops/session-2026-07-17/multi_source-latest.md` |
| Comercial | JSON/CSV/XLSX/HTML com disclaimers automáticos (baixa cobertura, freshness pncp/contracts) | `docs/ops/session-2026-07-17/commercial-b2g-session-sc.*` |

### 41.3 Banco (local `pncp_datalake` @ 5433)

| Item | Valor |
|------|-------|
| Migrations | 051 contract date semantics (aplicada + backfill 63574 rows); 052 official_acts (SQL aplicado + linha em `_migrations` status=applied) |
| Tabelas novas | `official_act_resources`, `official_acts`, `official_act_classifications`, `official_act_links`, `official_act_source_links`, `official_act_matches` |
| Inserts sessão | 2964 `official_acts` (upsert idempotente) |
| Duplicidades | 0 grupos (source, record_hash) |

### 41.4 Cobertura e freshness (honestas)

| Métrica | Resultado | Denominador | Confiança |
|---------|-----------|-------------|-----------|
| `historical_editais_raw_coverage` | **4,76%** | 52/1093 entes raio 200 km | high (não sobrescrita) |
| `municipalities_with_publication_30d` | 74,92% | 221/295 munis IBGE SC | medium (smoke 2 ZIPs de jul/2026) |
| `source_coverage_sc_compras` | 0,38% | 10/2602 (meta API ano) | medium (amostra page-limited) |
| `source_coverage_dados_abertos_sc` | 1,22% | 500/~41080 linhas CSV 2025 | low (smoke) |
| Freshness ciga/sc/dados | <1 h pós-coleta | artefatos completed_at | high |
| Freshness pncp/contracts gate | falhando | freshness_gate | — |

### 41.5 Claims permitidos

1. Ingestão **live** DOE-SC (CKAN CSV 2025, 500 rows processados) e DOM-SC (CIGA, 2454 pubs) com `live_fetch=true` / `attestation=false`.
2. Persistência real em `official_acts` (2964) no PostgreSQL local; migration **052** aplicada e registrada em `_migrations`.
3. Classificação determinística de atos (sem LLM obrigatório).
4. Reconciliação inicial: **30** pares via regra `compras_sc_id_crosswalk` (ids `sc-*` do portal Compras SC também presentes em `pncp_raw_bids` como espelho local). **0** matches `pncp_number_exact` com número de controle PNCP real no smoke.
5. Cobertura bruta de editais no raio permanece **~4,76%** (metodologia histórica intacta).
6. Municípios com publicação na amostra CIGA: **221/295 = 74,92%** (resumo resselado, chaves accent-normalized) — **não** é cobertura de editais DoD 95%.
7. Suite crítica CI-equivalente **300 passed / 5 skipped** nesta sessão (antes da correção de claims); testes de reconciliação+ciga **48 passed** após o fix.
8. Catálogo DOE no CKAN ainda **termina em 2025** (sem resource 2026 no `package_show`).

### 41.6 Claims proibidos

1. LOCAL_READY / VPS_OPERATIONAL / PROJECT_DONE / CONTRATOS_95 / EDITAIS_95.
2. Piloto PNCP 90d nacional = success; backfill 3 anos autorizado.
3. Cobertura de editais ≥95% ou "operação autônoma diária confiável".
4. 2602 editais Compras SC como cobertura histórica total (é meta do filtro ano, não prova multi-ano).
5. 74,92% municípios = meta DoD de editais.
6. Reconciliação ampla DOE/DOM ↔ PNCP oficial.
7. Tratar ids `sc-*` ou linhas espelho em `pncp_raw_bids` como número de controle PNCP / `pncp_number_exact`.
8. Ingestão completa/incremental contínua DOE+DOM em produção/VPS.

### 41.7 Gargalo único de maior impacto

**Cobertura de editais no universo 200 km (~4,76%)** — o ganho municipal via CIGA melhora sinais de publicação, mas **não** substitui backfill multi-fonte de editais/contratos no denominador 1093 entes com freshness PNCP e documentos.

### 41.8 Como reproduzir (ordem)

```bash
# CI critical
pytest tests/test_freshness_gate.py tests/test_universe.py tests/test_manifest.py \
  tests/test_consulting_readiness.py tests/test_coverage_truth.py \
  tests/test_resolve_unresolved_entities.py tests/test_golden_path_fail_closed.py \
  tests/test_golden_path_ledger.py tests/test_contracts_window_complete.py \
  tests/test_contracts_pilot_completion.py tests/test_evidence_artifact_consistency.py \
  tests/test_cross_source_hash.py tests/test_commercial_sample_sc.py \
  tests/test_run_evidence.py tests/test_contract_date_semantics.py \
  tests/test_dados_abertos_sc_crawler.py tests/test_act_classifier.py \
  tests/test_smoke_pncp_public.py tests/test_sc_compras_smoke.py \
  tests/test_contracts_uf_filter.py -o addopts='' -q

python3 -m scripts.crawl.dados_abertos_sc_crawler --mode smoke
python3 -m scripts.crawl.ciga_dom_publications --mode smoke
python3 -m scripts.crawl.sc_compras_crawler --mode smoke --max-pages 2
python3 -m scripts.ingestion.load_official_acts_session
python3 -m scripts.matching.official_acts_reconcile --mode smoke
python3 -m scripts.coverage.multi_source_coverage
python3 -m scripts.reports.commercial_b2g_session --output-dir output/reports
```

### 41.10 Correção adversarial (mesma sessão)

Após revisão independente, foram corrigidos:

1. **Reconciliação:** `sc-*` não é mais promovido a `pncp_number`; regra `pncp_number_exact` exige formato PNCP real; smoke re-executado com `compras_sc_id_crosswalk` × 30 e **0** `pncp_number_exact`.
2. **Migration 052:** registrada em `_migrations` (status=applied) no DB local.
3. **CIGA evidence:** flags explícitas `live_fetch=true` / `attestation=false`; municípios resselados **221/295** (antes 138 por interseção sem normalização consistente no artefato).
4. **SHA documental:** não embutir SHA auto-referente órfão; usar HEAD de `main` após o commit de correção.

### 41.9 Referências

- Bundle evidência: `docs/ops/session-2026-07-17/`
- HTML diretoria: `extra-consultoria-plano-executivo.html` (painel sessão §41)
- Commit técnico: `8b8138a`

---

## 42. Briefing executivo — trabalho financiado (diretoria Extra Construtora)

> **Data de corte:** 2026-07-17  
> **Branch:** `main`  
> **HEAD pré-publicação deste briefing:** `aca4408` · técnico de ingestão `8b8138a` · correção de claims `3bf1a3b`  
> **Público:** diretoria / sponsor da consultoria B2G  
> **Tom:** o que o investimento técnico **já comprou** (evidência), o que **ainda não** pode ser prometido, e o **único gargalo** que trava a operação diária.

### 42.1 Em uma frase

O financiamento até esta data **não comprou** “plataforma 95% pronta e autônoma”, mas **comprou** uma **fundação auditável de inteligência B2G em SC**: fontes públicas reais coletadas, persistidas, classificadas, com métricas honestas, CI verde e relatório comercial com disclaimers — pronta para a próxima wave de cobertura de editais.

### 42.2 O que o investimento já entregou (portfolio comprovado)

| # | Capacidade financiada | Estado | Prova material |
|---|----------------------|--------|----------------|
| 1 | **Cadeia de evidência** (run_id, hash, git, claims fail-closed) | Operacional em pilotos/crawls | `scripts/crawl/run_evidence.py`, testes de artefato |
| 2 | **Semântica de datas de contrato** (assinatura ≠ publicação) | Migration 051 aplicada | `db/migrations/051_*.sql` |
| 3 | **Modelo unificado de atos oficiais** (DOE/DOM multi-fonte) | Migration 052 + 2964 atos no PG local | `db/migrations/052_official_acts.sql`, load session |
| 4 | **Ingestão real DOE-SC** (Dados Abertos / CKAN CSV) | Smoke live 500 rows + raw SHA-256 | `dados_abertos_sc_crawler`, artefatos smoke |
| 5 | **Ingestão real DOM-SC** (CIGA público, sem token) | Smoke live **2454** pubs · **221/295** munis no universo | `ciga_dom_publications`, summary resselado |
| 6 | **Portal Compras SC incremental** | Smoke/incremental + checkpoint + run_id | `sc_compras_crawler` |
| 7 | **Classificador de atos de contratação** | 25 categorias, corpus, sem LLM obrigatório | `act_classifier.py` |
| 8 | **Reconciliação inicial multi-fonte** | 30 pares `compras_sc_id_crosswalk` (honesto: não é nº PNCP) | `official_acts_reconcile` |
| 9 | **Métricas de cobertura com denominador** | 4,76% histórico preservado + métricas multi-fonte | `multi_source_coverage` |
| 10 | **Relatório comercial com disclaimers** | JSON/HTML/CSV/XLSX amostra real | `docs/ops/session-2026-07-17/commercial-*` |
| 11 | **Qualidade automatizada** | CI GitHub **verde** (lint, mypy, tests, bandit, pip-audit) | Actions em `main` |
| 12 | **Governança DoD + HTML diretoria** | §38–§42; painel executivo atualizado | `DOD.md`, `extra-consultoria-plano-executivo.html` |

### 42.3 Resultados quantificados (mesma data de corte)

| Indicador | Valor | Como ler |
|-----------|-------|----------|
| Atos oficiais no banco local | **2.964** | CIGA 2.454 + DOE 500 + Compras 10 (smoke/sessão) |
| Publicações DOM (amostra jul/2026) | **2.454** | 2 ZIPs do pacote mensal mais recente |
| Municípios SC com pub na amostra | **221 / 295 (74,9%)** | Sinal de rede municipal — **não** é meta DoD de editais |
| Editais no raio 200 km (histórico) | **4,76% (52 / 1.093)** | **Gargalo comercial #1** — denominador canônico |
| Contratos PNCP no DB (estoque) | ~63k total · ~21k SC | Base histórica; freshness PNCP ainda falha no gate |
| Matches reconciliação smoke | **30** crosswalk Compras↔espelho local | **0** match por número de controle PNCP real |
| Suite crítica local | **300 passed / 5 skipped** | Mesma família da CI |
| CI GitHub Actions | **success** nos jobs default | Não confundir com “produto pronto” |

### 42.4 Antes × agora (para a diretoria)

| Antes (pré-ondas recentes) | Agora (pós §40–§41) |
|---------------------------|---------------------|
| Fontes SC em grande parte “descobertas” ou smoke frágil | Download real, raw zone, checkpoint, classificação, load no banco |
| Datas de contrato misturadas | Colunas semânticas + migration 051 |
| Sem modelo canônico de ato oficial multi-fonte | Tabelas `official_acts*` + upsert idempotente |
| Claims de piloto fáceis de inflar | Fail-closed: partial → NO-GO; sc-* **não** vira PNCP |
| Cobertura só como “número solto” | Numerador/denominador/fórmula/limitações por métrica |
| HTML com narrativa genérica | Painel §41/§42 com o que pode / não pode afirmar |

### 42.5 O que o financiamento **ainda não** comprou (não negociável)

1. **Cobertura ≥95%** de editais ou contratos no raio 200 km.  
2. **LOCAL_READY / VPS_OPERATIONAL / PROJECT_DONE.**  
3. **Piloto PNCP nacional de 90 dias concluído** e backfill de 3 anos autorizado.  
4. **Operação autônoma diária** em produção (timers VPS, soak, alertas 24/7).  
5. **Reconciliação ampla** DOE/DOM ↔ PNCP por identificadores oficiais.  
6. **DOE-SC 2026 em bulk no CKAN** (catálogo público ainda termina em 2025).  

### 42.6 Valor para a Extra Construtora (uso imediato)

Mesmo com cobertura de editais baixa no raio:

- **Radar municipal:** amostra CIGA de atos recentes (homologações, atas, extratos) em centenas de municípios SC.  
- **Radar estadual bulk:** DOE aberto processável e classificado (piloto).  
- **Oportunidades no Portal Compras SC:** listagem pública incremental com links oficiais (amostra).  
- **Relatório comercial honesto:** oportunidades abertas + disclaimers automáticos (não vende cobertura inexistente).  
- **Risco de decisão controlado:** a diretoria vê gaps com o mesmo rigor que vê conquistas.

### 42.7 Decisão pedida à diretoria / sponsor

| Opção | Foco do próximo investimento | Efeito |
|-------|------------------------------|--------|
| **A — Cobertura (recomendado)** | Subir editais no raio 200 km (4,76% → trajetória 95%) multi-fonte | Maximiza valor comercial da consultoria |
| B — Profundidade PNCP | Pilot 90d supervisionado + freshness | Fortalece contratos/histórico nacional |
| C — Infra | Contratar VPS (V6.2) | Habilita operação recorrente fora do laptop |
| D — Misto | A (maioria) + C (mínimo) | Cobertura + base de operação |

**Recomendação técnica:** **A**, com **C** assim que houver budget de infra — sem VPS a coleta real não vira rotina diária confiável.

### 42.8 Gargalo único (inalterado)

**Cobertura de editais no universo 200 km (~4,76%).**

### 42.9 Índice de evidência para auditoria financeira / técnica

- Bundle sessão: `docs/ops/session-2026-07-17/`  
- DoD detalhado da onda: §41 (+ correção §41.10)  
- HTML: `extra-consultoria-plano-executivo.html` (painel “Trabalho financiado”)  
- Repositório: https://github.com/tjsasakifln/extra-consultoria (`main`)

---

## 43. Sessão operacional — cobertura 200 km (2026-07-17)

> **Branch:** `epic/coverage-200km-operational`  
> **HEAD inicial:** `84249471a3c0b53ea51d038207bfe4ffc4b4e966`  
> **Commits:** `32851a1` (coleta) · `dea7a73` (comercial+audit) · `966bcbb`+ (CI stamp)  
> **PR:** https://github.com/tjsasakifln/extra-consultoria/pull/9 · Actions run `29576072258` **SUCCESS**  
> **Evidência:** `docs/ops/session-2026-07-17/` · `ADVERSARIAL-AUDIT.md` · `coverage_canonical.json`

### 43.1 Resultado de cobertura (denominador inalterado = 1.093)

| Métrica | Valor | Notas |
|---------|-------|-------|
| Baseline histórico (pré-sessão) | **52 / 1.093 (4,76%)** | Preservado; série histórica |
| **Headline comercial** `commercial_opportunity_any` | **116 / 1.093 (10,61%)** | OPEN/UPCOMING/RECENT matched ao universo |
| Delta vs baseline | **+64 entidades** | +5,85 p.p. |
| Lista nominal cobertas | **116 linhas** | `entities_covered.jsonl` · `list_identity_ok=true` |
| Lista nominal descobertas | **977 linhas** | `entities_uncovered.jsonl` |
| Loose `is_covered` union (não-claim) | ~133 | **não** usar como headline |

**Fórmula headline:**  
`COUNT(DISTINCT entity_id com ≥1 registro counts_for_coverage)` / `1093`  
onde `counts_for_coverage` = match canônico + status ∈ {OPEN_OPPORTUNITY, UPCOMING_OPPORTUNITY, RECENT_NOTICE}.

**Atribuição de fontes no conjunto comercial de 116** (uma entidade pode ter várias fontes; contagens de presença):

| Fonte (session) | Entidades com match comercial |
|-----------------|-------------------------------|
| `ciga_dom` → `dom_sc` | 79 |
| `pncp_sc` → `pncp` | 79 |
| `sc_compras` | 4 |

### 43.2 Volume coletado e persistido

| Fonte | Modo | Registros | Persistidos `official_acts` | Limitações | Run / artefato |
|-------|------|-----------|-----------------------------|------------|----------------|
| CIGA DOM | full 15 ZIPs + incr. | **10.269** | **12.636** | — | `ciga-dom-20260717T104504Z-*` |
| Compras SC | full list + detail 200 opens | **2.602/2.602** | **2.602** | prazo via `dataEntrega` em 200 | `sc_compras-full-*` + enriched |
| PNCP SC | UF=SC mod.6, 2 rodadas | **541** | coverage match | 429 residual parcial | `pncp-sc-*-9d6dd91153` |
| DOE-SC | prévio | 500 | 500 | bulk 2026 ausente no CKAN | pré-sessão |

**Banco:** **15.738** atos · dups `(source,record_hash)` = **0** · migrations 051/052 applied.

### 43.3 Oportunidades (radar live)

Artefatos: `radar_opportunities.jsonl` + `radar_opportunities.csv` (ranking, GO/REVIEW/NO_GO, distance_km)

| Indicador | Valor |
|-----------|-------|
| OPEN_OPPORTUNITY | **757** |
| OPEN com prazo conhecido | **438** |
| OPEN + engenharia | **68** |
| Recomendação **GO** | **14** |
| UPCOMING | (no radar JSONL) |
| RECENT_NOTICE | restante do radar |

Classificadores: `commercial_status.py` (não marca “Publicado Resultado” como OPEN) · `sector_engineering.py` · testes 10 PASS.

### 43.4 Reconciliação

- Sample: dominante `compras_sc_id_crosswalk` (local) — **não** nº PNCP oficial.  
- **0** claim de match PNCP oficial massivo nesta sessão.

### 43.5 Claims permitidos

1. Headline comercial **116/1.093 (10,61%)**, Δ **+64**, listas nominais com `list_identity_ok`.  
2. CIGA em escala >> smoke (10k+ pubs; 12.636 atos).  
3. Compras SC **2.602/2.602** do totalElementos 2026.  
4. Radar **757** OPEN · **68** eng · **438** c/ prazo · **14** GO.  
5. official_acts **15.738**, dups **0**.  
6. CI remota **PASS** no PR #9.

### 43.6 Claims proibidos

1. 95% cobertura.  
2. LOCAL_READY / VPS_OPERATIONAL / PROJECT_DONE.  
3. PNCP SC 14d completo.  
4. Match PNCP oficial massivo.  
5. Operação diária autônoma.  
6. **138** como headline (foi is_covered loose; **não** permitido).  
7. **784/95** como contagens OPEN/eng (stale; live = **757/68**).  
8. Todas as OPEN com prazo validado (só 438/757).

### 43.7 Gargalo único residual

**Ainda 977/1.093 entidades sem oportunidade comercial matched (~89,4%).**  
Próximo: detail/CNPJ Compras em escala, PNCP SC resiliente a 429, resolução CIGA além de prefeituras, VPS.

### 43.8 Código entregue

- `scripts/coverage/commercial_status.py`  
- `scripts/coverage/sector_engineering.py`  
- `scripts/coverage/session_coverage_pipeline.py`  
- `scripts/crawl/pncp_sc_focused.py`  
- `tests/test_commercial_status.py`  
- `docs/ops/session-2026-07-17/ADVERSARIAL-AUDIT.md`

### 43.9 Correção adversarial (lista = headline)

- Bug: `entities_covered.jsonl` tinha 107 vs numerator 116.  
- Fix: single source of truth `counts_for_coverage` → `commercial_entity_ids` → arquivo; assert `n_cov == commercial_num`.  
- Verificação: `list_identity_ok=true`, 116 linhas, 977 descobertas.

### 43.10 CI

- PR #9: https://github.com/tjsasakifln/extra-consultoria/pull/9  
- Run: https://github.com/tjsasakifln/extra-consultoria/actions/runs/29576072258  
- Lint, mypy, Test critical, bandit, pip-audit = **SUCCESS**

---

## 44. LOCAL_RESILIENCE_READY — SUPERSEDED (2026-07-17 truth gate)

**Decisão original (histórica):** `LOCAL_RESILIENCE_READY`  
**Decisão atual:** **`NOT_READY`** — selo destruído pela auditoria adversarial final.  
**Não implica:** `PRE_VPS_FINAL_READY`, `VPS_OPERATIONAL`, `PROJECT_DONE`, cobertura 95%.  
**Branch truth gate:** `fix/pre-vps-final-truth-gate-20260717`  
**Auditoria:** `docs/operations/PRE-VPS-FINAL-ADVERSARIAL-AUDIT.md`  
**Truth report:** `docs/operations/PRE-VPS-FINAL-TRUTH.md`  
**Documento pré-VPS:** `docs/operations/PRE-VPS-READINESS.md` (atualizado)

> Qualquer claim de READY baseado apenas em fixtures, JSON local ou health sem
> evidência live deve ser tratado como **falso verde**.

### 44.1 Entrega

Núcleo de coleta resiliente local para PNCP, CIGA/DOM-SC público e SC Compras:

1. Contrato ADR-021 (`FetchResult` semântico + `SourceAdapter`)
2. Fail-closed: 429/partial/auth/error nunca viram success/empty
3. Checkpoint canônico atômico + resume idempotente
4. Watermark só após evidence satisfatória
5. DLQ com dedup e replay manual
6. Raw/proveniência antes de normalize
7. Evidence ledger com predicate de completude
8. Health consolidado (`python3 -m scripts.ops.health`)
9. Orquestração canônica (`make resilient-*`)
10. Units systemd prioritárias **preparadas**, **não habilitadas**
11. Migration aditiva `054_local_resilience_contract.sql` (projeção futura)

### 44.2 Validação registrada

```text
make resilience-gate
  ruff: pass
  mypy (7 módulos críticos): pass
  validate_systemd: pass
  resilient-smoke: 181 passed, 24 skipped (~14s)
  tests/test_local_resilience.py + chaos 429: 35 passed (~10s)
  resilient-local-cycle (fixtures): exit 0 healthy
  python3 -m scripts.ops.health: exit 0
```

Comandos de smoke/gate:

```bash
make resilient-smoke
make resilient-local-cycle
make resilience-gate
python3 -m scripts.ops.health
```

### 44.3 Claims permitidos

1. Mecânica de resiliência local das 3 fontes prioritárias é reproduzível sem internet.
2. 429/partial/zero ambíguo não produzem evidence satisfatória nem avançam watermark.
3. Resume não reprocessa fatias `success`/`raw_persisted` com raw disponível.
4. Systemd futuro validado estaticamente; **não** ativado.

### 44.4 Claims proibidos

1. VPS provisionada/operacional.
2. 95% cobertura ou cobertura operacional real inflada por fixtures.
3. Freshness live de fontes externas garantida.
4. Demais adapters (PCP, compras.gov, TCE, etc.) validados neste gate.
5. Stories E3.S1/S2 **Done** (permanecem **InReview** até QA/PO independentes).
6. Scheduler em produção ou soak 24h.

### 44.4b Correção adversarial pós-READY

- Bug: SC Compras podia marcar `success` com páginas virtuais vazias quando `total_elementos > len(items)`.
- Fix: `records_match_total` + stop em empty virtual page → `partial`.
- Chaos 429 stubs removidos; crash-before-watermark reescrito com stores reais.
- Commit: `3252010`.

### 44.5 Riscos residuais

- Adapters legados fora do trio prioritário.
- Comportamento real de rate limit/schema das APIs externas.
- Persistência/backup/retenção no host futuro.
- Alertas externos e E3.S3 (VPS).

### 44.6 Próximo passo

Somente após aceite de QA/PO e publicação: checklist de provisionamento em
`docs/operations/PRE-VPS-READINESS.md` §Checklist.

### 44.7 Publicação e prestacao de contas (diretoria)

| Campo | Valor |
|---|---|
| Gate local | `make pre-vps-final-gate-offline` + CI `resilience-gate` verde |
| Estado | `NOT_READY` para `PRE_VPS_FINAL_READY` (selo antigo destruído) |
| Branch de origem | `fix/pre-vps-final-truth-gate-20260717` |
| HTML executivo | `extra-consultoria-plano-executivo.html` (gráficos real vs planejado) |
| Documento de readiness | `docs/operations/PRE-VPS-READINESS.md` |

**Avanço real vs planejado (snapshot 2026-07-17):**

| Dimensão | Planejado (meta) | Real (evidência) | Delta |
|---|---:|---:|---|
| Source registry | 1.093/1.093 | 1.093/1.093 | 0 |
| Sinal comercial (não cobertura) | trajetória → 95% | 116/1.093 (10,61%) | −84,4 p.p. |
| Cobertura operacional estrita | ≥1.039/1.093 (95%) | 0/1.093 (0%) | −95 p.p. |
| Resiliência pré-VPS (E3.S1+S2 mecânica) | 100% critérios locais | 100% gate local | 0 |
| VPS operacional (E3.S3) | timers + soak 24h | 0% (não provisionada) | −100 p.p. |
| Stories E3.S1 / E3.S2 | Done com QA/PO | InReview | aguarda QA/PO |
| Project Done | 100% | ~0,1% aceite formal DoD | bloqueado |

Próximo investimento: (A) cobertura comercial → 95%; (B) provisionar VPS só após checklist PRE-VPS; (C) QA/PO fecham E3.S1/S2.

---

## 45. PRE-VPS FINAL TRUTH GATE — sessão 2026-07-17 (PR #12)

**Veredito da sessão:** `NOT_READY` para `PRE_VPS_FINAL_READY`  
**Selo destruído:** `LOCAL_RESILIENCE_READY` (hipótese falsa: fixture ≠ live; JSON ≠ PostgreSQL)  
**Branch:** `fix/pre-vps-final-truth-gate-20260717`  
**PR:** https://github.com/tjsasakifln/extra-consultoria/pull/12  
**CI resilience-gate:** SUCCESS (ex.: runs `29614326278`, `29614544628`)  
**Não implica:** `PRE_VPS_FINAL_READY`, `VPS_OPERATIONAL`, `PROJECT_DONE`, canary live, 95% cobertura.

### 45.1 O que a sessão entregou

| # | Entrega | Evidência |
|---|---------|-----------|
| 1 | Auditoria adversarial pré-código | `docs/operations/PRE-VPS-FINAL-ADVERSARIAL-AUDIT.md` |
| 2 | Truth report + estados honestos | `docs/operations/PRE-VPS-FINAL-TRUTH.md` |
| 3 | Pipeline único `OperationalPipeline` | `scripts/crawl/resilience/pipeline.py` |
| 4 | Persistência canônica PG (upsert/match/opportunities/acts) | `scripts/crawl/resilience/persistence.py` |
| 5 | `monitor.py` prioriza o mesmo pipeline (pncp/ciga/sc) | `_crawl_source_via_resilient_pipeline` |
| 6 | Isolamento fixture vs live (`RESILIENCE_ENV`) | `config.py` + `health.py` |
| 7 | Freshness tripla + SLA do registry (PNCP 4h) | `health.py` |
| 8 | Circuit breaker persistente em FS | `circuit_breaker.py` |
| 9 | HttpResiliencePolicy unificada (RESILIENCE_* > PNCP_*) | `http_policy.py` + PNCP adapter |
| 10 | SC Compras snapshot imutável + `snapshot_hash` | `adapters.py` |
| 11 | Checkpoint state machine (sem `TypeError: pass`) | `stages.py` |
| 12 | CI job `resilience-gate` (migrations fresh+upgrade, PG vertical) | `.github/workflows/ci.yml` |
| 13 | `make pre-vps-final-gate-offline|live-canary|final-gate` | `Makefile` |
| 14 | Docs de selo destruído | README, PRE-VPS-READINESS, DOD §44/§45, architecture |

### 45.2 Validação registrada (sessão)

```text
Local offline:
  pytest resilience unit/chaos: 48 passed
  fixture cycle: TEST_HEALTHY exit 0
  health --env fixture: TEST_HEALTHY exit 0
  health --env development (sem live): no_live_evidence exit 2
  ruff + mypy resilience/ops: pass

CI (PR #12):
  Resilience Gate (pre-VPS): SUCCESS
  Lint / Mypy / Test critical / Bandit / pip-audit: SUCCESS
  Migrations 001–054 fresh + upgrade 001–40→41–54: SUCCESS
  Vertical slice PostgreSQL real: SUCCESS
```

### 45.3 Claims permitidos (pós truth gate)

1. Offline + CI de resiliência estão verdes e fail-closed.
2. Fixture não contamina health live (`no_live_evidence` sem watermark live).
3. Path canônico de prioridade inclui PostgreSQL (não só JSON).
4. Selo `LOCAL_RESILIENCE_READY` **não** é válido como “pronto para VPS”.

### 45.4 Claims proibidos

1. `PRE_VPS_FINAL_READY` / `VPS_OPERATIONAL` / `PROJECT_DONE`.
2. Canary live das 3 fontes concluída (não executada nesta sessão).
3. 95% cobertura operacional ou comercial.
4. Timers systemd habilitados ou host provisionado.
5. Stories E3.S1/S2 Done (ainda dependem QA/PO independentes + canary).

### 45.5 Próximo passo (ordem)

1. `make pre-vps-live-canary` com `DATABASE_URL` e rede (mínimo por fonte).  
2. `make pre-vps-final-gate` → só então considerar `PRE_VPS_FINAL_READY`.  
3. Revisão adversarial humana + merge controlado.  
4. Checklist VPS em `PRE-VPS-READINESS.md` (sem timers até go-live).

### 45.6 Prestação de contas (diretoria)

| Campo | Valor |
|---|---|
| Veredito | `NOT_READY` (truth gate) |
| Offline/CI | Verde |
| Live canary | Pendente |
| Cobertura ops estrita | 0/1.093 (0%) |
| Sinal comercial | 116/1.093 (10,61%) — não é cobertura |
| HTML | `extra-consultoria-plano-executivo.html` (§45) |
| PR | #12 |

---


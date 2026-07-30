# CANDIDATES — DOD-LOW-HANGING-BOUNDARIES-AND-EVIDENCE-01

## Decision counts

```json
{
  "REJECTED_NOT_LOW_HANGING": 1308,
  "SELECTED": 59,
  "REJECTED_HUMAN": 39,
  "REJECTED_PARALLEL_CONFLICT": 20,
  "REJECTED_INSUFFICIENT_EVIDENCE": 33,
  "REJECTED_LIVE_DEPENDENCY": 3
}
```

## SELECTED

- `DOD-definition-of-done-extra-a362715e4d` [A_GOVERNANCE] L45: Cada item só é marcado como concluído quando existir evidência verificável.
- `DOD-definition-of-done-extra-75164c86da` [A_GOVERNANCE] L47: Código existente sem execução comprovada não é considerado concluído.
- `DOD-definition-of-done-extra-59ea375492` [A_GOVERNANCE] L48: Teste unitário isolado não substitui execução ponta a ponta.
- `DOD-definition-of-done-extra-d3db8c3907` [A_GOVERNANCE] L51: Alterações de escopo são refletidas primeiro neste documento e nos documentos canônicos do projeto.
- `DOD-definition-of-done-extra-cb23ed5034` [A_GOVERNANCE] L52: Itens explicitamente marcados como opcionais não bloqueiam o fechamento do projeto.
- `DOD-definition-of-done-extra-c94d735e7c` [A_GOVERNANCE] L53: Todos os demais itens bloqueiam o respectivo gate.
- `DOD-definition-of-done-extra-aa0cc46c52` [A_GOVERNANCE] L54: O projeto só é considerado integralmente concluído quando os três róis obrigatórios estiverem atendi
- `DOD-definition-of-done-extra-f0f41447dd` [A_GOVERNANCE] L55: requisitos do estágio atual;
- `DOD-definition-of-done-extra-b5522727b0` [A_GOVERNANCE] L56: requisitos posteriores ao provisionamento da VPS;
- `DOD-definition-of-done-extra-107a7ac4da` [A_GOVERNANCE] L57: requisitos independentes de infraestrutura.
- `DOD-definition-of-done-extra-f96c0779f9` [A_GOVERNANCE] L64: Implementação parcial é anotada como `PARTIAL`, sem marcar o item como concluído.
- `DOD-definition-of-done-extra-793fb2e8b5` [A_GOVERNANCE] L65: Dependência externa pendente é anotada como `BLOCKED`, com responsável, causa e próximo teste.
- `DOD-definition-of-done-extra-a6aa7190ac` [A_GOVERNANCE] L68: Campo indisponível na fonte é registrado como `SOURCE_UNAVAILABLE` ou `NOT_READY`, nunca como zero e
- `DOD-definition-of-done-extra-794600a043` [A_GOVERNANCE] L69: Um blocker externo não desaparece do gate; ele permanece visível até resolução ou alteração formal d
- `DOD-definition-of-done-extra-fa4a690d5c` [A_GOVERNANCE] L70: Os gates consideram concluídos apenas itens `DONE` e itens legitimamente `NOT_APPLICABLE`.
- `DOD-definition-of-done-extra-5865b9f10c` [A_GOVERNANCE] L71: O estado de cada requisito pode ser reconstruído sem depender do histórico de uma conversa com agent
- `DOD-definition-of-done-extra-5fd54bbd01` [A_GOVERNANCE] L77: teste automatizado reproduzível;
- `DOD-definition-of-done-extra-56586465e9` [A_GOVERNANCE] L78: comando documentado com exit code `0`;
- `DOD-definition-of-done-extra-374c5965bd` [A_GOVERNANCE] L81: execução registrada em ledger, manifest ou tabela de runs;
- `DOD-definition-of-done-extra-3104de3131` [A_GOVERNANCE] L82: log datado e correlacionável;
- `DOD-definition-of-done-extra-349bb54c8f` [A_GOVERNANCE] L84: commit ou pull request identificável;
- `DOD-definition-of-done-extra-7e08df417e` [B_SCOPE_EXCLUDED] L138: O projeto não contém módulo de diário de obra.
- `DOD-definition-of-done-extra-d1bf197b8b` [B_SCOPE_EXCLUDED] L139: O projeto não contém módulo de medição de obra.
- `DOD-definition-of-done-extra-1d08d2599c` [B_SCOPE_EXCLUDED] L140: O projeto não contém acompanhamento de avanço físico.
- `DOD-definition-of-done-extra-eafbfd4a1f` [B_SCOPE_EXCLUDED] L141: O projeto não contém acompanhamento financeiro da execução da obra.
- `DOD-definition-of-done-extra-361d74f7ba` [B_SCOPE_EXCLUDED] L142: O projeto não contém gestão de fotos de obra.
- `DOD-definition-of-done-extra-10726ba9b9` [B_SCOPE_EXCLUDED] L143: O projeto não contém fiscalização de campo.
- `DOD-definition-of-done-extra-9075dfdd96` [B_SCOPE_EXCLUDED] L144: O projeto não contém gestão de aditivos de execução.
- `DOD-definition-of-done-extra-20ded85333` [B_SCOPE_EXCLUDED] L145: O projeto não contém gestão de riscos de obra.
- `DOD-definition-of-done-extra-642f0c1b05` [B_SCOPE_EXCLUDED] L146: O projeto não contém gestão de equipes de obra.
- `DOD-definition-of-done-extra-ab71db3f6e` [B_SCOPE_EXCLUDED] L147: O projeto não contém gestão de cronograma físico-financeiro.
- `DOD-definition-of-done-extra-ddd9c4fb86` [B_SCOPE_EXCLUDED] L148: O projeto não contém portal para a contratada.
- `DOD-definition-of-done-extra-0fe4fb2225` [B_SCOPE_EXCLUDED] L149: O projeto não contém interface pública.
- `DOD-definition-of-done-extra-e3fab7341c` [B_SCOPE_EXCLUDED] L150: O projeto não contém multi-tenant.
- `DOD-definition-of-done-extra-1b8854e33b` [B_SCOPE_EXCLUDED] L151: O projeto não contém cobrança, assinatura ou Stripe.
- `DOD-definition-of-done-extra-5d877d2ba4` [B_SCOPE_EXCLUDED] L152: O projeto não contém autenticação complexa desnecessária.
- `DOD-definition-of-done-extra-17f49981f1` [B_SCOPE_EXCLUDED] L153: O projeto não contém dashboard web apenas por conveniência estética.
- `DOD-definition-of-done-extra-07fdce3052` [B_SCOPE_EXCLUDED] L154: O projeto não contém Kubernetes, Kafka, Redis ou Elasticsearch sem necessidade comprovada.
- `DOD-definition-of-done-extra-c5144849e4` [B_SCOPE_EXCLUDED] L155: O projeto não assina documentos em nome da Extra.
- `DOD-definition-of-done-extra-f2dfcdb3e4` [B_SCOPE_EXCLUDED] L156: O projeto não protocola propostas ou documentos automaticamente sem ação humana explícita.
- `DOD-definition-of-done-extra-4bd8d3ef1a` [B_SCOPE_EXCLUDED] L158: O projeto não substitui advogado em impugnações, recursos ou pareceres jurídicos.
- `DOD-definition-of-done-extra-0903b01d4b` [B_SCOPE_EXCLUDED] L159: O projeto não representa a empresa presencialmente em sessões de licitação.
- `DOD-definition-of-done-extra-7b21a39253` [B_SCOPE_EXCLUDED] L160: O projeto não fornece garantias financeiras, seguros ou crédito.
- `DOD-definition-of-done-extra-90a192a188` [B_SCOPE_EXCLUDED] L161: O projeto não promete habilitação, adjudicação, vitória ou contratação.
- `DOD-definition-of-done-extra-825967b2c1` [B_SCOPE_EXCLUDED] L162: O projeto não executa o objeto contratado.
- `DOD-definition-of-done-extra-fc3bf86724` [C_CLI_UX] L167: O fluxo principal pode ser executado sem interface web.
- `DOD-definition-of-done-extra-bcceab4099` [C_CLI_UX] L169: O sistema não exige conhecimento do código interno para tarefas operacionais recorrentes.
- `DOD-definition-of-done-extra-3c79408c03` [C_CLI_UX] L170: A saída é legível para revisão humana.
- `DOD-definition-of-done-extra-383035c911` [C_CLI_UX] L171: Erros são apresentados com causa provável e próximo passo.
- `DOD-definition-of-done-extra-ea60d7c534` [C_CLI_UX] L172: O sistema permite repetir uma execução sem criar inconsistência.
- `DOD-definition-of-done-extra-ef20844eb2` [C_CLI_UX] L174: O sistema permite identificar quando um dado não é confiável.
- `DOD-definition-of-done-extra-38c4c0fe6f` [C_CLI_UX] L175: O sistema não esconde limitações atrás de scores ou percentuais genéricos.
- `DOD-rol-1-definition-of-done-5412da3ad7` [D_COVERAGE_TRUTH] L546: A média entre as duas coberturas não é usada para mascarar uma delas. **Code-ready (not accepted):**
- `DOD-rol-1-definition-of-done-5eca319947` [D_COVERAGE_TRUTH] L548: Uma fonte saudável para contratos não prova cobertura de editais. **Code-ready (not accepted):** uni
- `DOD-rol-1-definition-of-done-bb9d5de811` [D_COVERAGE_TRUTH] L557: `data_presence` é publicada apenas como métrica descritiva.
- `DOD-rol-1-definition-of-done-0c828cadb4` [D_COVERAGE_TRUTH] L558: `data_presence` nunca é chamada de cobertura. **Code-ready (not accepted):** dual engine separates d
- `DOD-rol-1-definition-of-done-3fb8978ae7` [D_COVERAGE_TRUTH] L461: A média entre as duas coberturas não é usada para mascarar uma delas.
- `DOD-rol-1-definition-of-done-b9c4d94a8e` [D_COVERAGE_TRUTH] L463: Uma fonte saudável para contratos não prova cobertura de editais.
- `DOD-rol-1-definition-of-done-90c4a972f6` [D_COVERAGE_TRUTH] L473: `data_presence` nunca é chamada de cobertura.

## Rejected samples (≤8 per reason)

### REJECTED_NOT_LOW_HANGING (total in counts)
- `DOD-definition-of-done-extra-934b7e1a8d`: already_accepted_or_checked — O denominador estratégico permaneceu fixo em **1.093 entidades**. Evid
- `DOD-definition-of-done-extra-3291212c84`: already_accepted_or_checked — `commercial_opportunity_any` foi reclassificada como sinal comercial `
- `DOD-definition-of-done-extra-ea8d68c1d0`: already_accepted_or_checked — Existe registro canônico explícito para **1.093/1.093 entidades**, sin
- `DOD-definition-of-done-extra-30700f5da5`: already_accepted_or_checked — A cobertura operacional usa sete estágios, SLA e proveniência (`run_id
- `DOD-definition-of-done-extra-b66ffceb51`: already_accepted_or_checked — Existe relatório nominal para os **1.093 gaps**, cada um com blocker e
- `DOD-definition-of-done-extra-7249b8dd2b`: already_accepted_or_checked — DOM/SC e DOE/SC possuem caminhos públicos sem credenciais. Evidência l
- `DOD-definition-of-done-extra-066ad585f6`: already_accepted_or_checked — Migrations 052/053 foram aplicadas localmente após snapshot; 1.093 reg
- `DOD-definition-of-done-extra-aa33c98608`: already_accepted_or_checked — O workspace cotidiano executa `today`, `opportunities`, `dossier`, `co

### REJECTED_HUMAN (total in counts)
- `DOD-definition-of-done-extra-2974cd669a`: human_eval_required — Um requisito somente pode ser tratado como `NOT_APPLICABLE` quando a p
- `DOD-definition-of-done-extra-e21af5fe47`: human_eval_required — validação manual registrada por Tiago;
- `DOD-definition-of-done-extra-b207150950`: human_eval_required — O sistema ajuda Tiago a decidir quais oportunidades merecem análise hu
- `DOD-definition-of-done-extra-8268a89973`: human_eval_required — Tiago é o único usuário obrigatório do sistema.
- `DOD-definition-of-done-extra-2e6f8b0d22`: human_eval_required — A conclusão final permanece sujeita ao aceite de Tiago e da empresa.
- `DOD-definition-of-done-extra-26b93711d5`: human_eval_required — Os top-20, ou todos os casos quando houver menos, passam por revisão m
- `DOD-definition-of-done-extra-c1ec59e4b7`: human_eval_required — O primeiro ciclo de uso real registra decisões de Tiago, contatos real
- `DOD-definition-of-done-extra-3690db41e4`: human_eval_required — Tiago aceita formalmente a fila como utilizável para iniciar a prospec

### REJECTED_PARALLEL_CONFLICT (total in counts)
- `DOD-definition-of-done-extra-75d4c221ed`: commercial_or_confenge:comercial — `NOT_APPLICABLE` possui justificativa, data e evidência; não é usado p
- `DOD-definition-of-done-extra-ad80befdaa`: commercial_or_confenge:confenge — O sistema ajuda a CONFENGE a identificar, no dataset de contratos, emp
- `DOD-definition-of-done-extra-716fd4472f`: commercial_surface — O sistema transforma sinais comerciais em uma fila pequena, explicável
- `DOD-definition-of-done-extra-8736745636`: commercial_or_confenge:confenge — Prospecção orientada por dados para a CONFENGE a partir de sinais obse
- `DOD-definition-of-done-extra-d27b80d991`: commercial_or_confenge:comercial — O projeto não assume responsabilidade técnica, jurídica, contábil ou c
- `DOD-definition-of-done-extra-e492baef47`: commercial_or_confenge:comercial — O sistema apoia revisão de coerência entre proposta comercial, planilh
- `DOD-definition-of-done-extra-8f3fb664b7`: commercial_or_confenge:confenge — Existe perfil comercial versionado da CONFENGE com serviços ofertados,
- `DOD-definition-of-done-extra-132d68ad15`: commercial_or_confenge:confenge — Órgãos públicos, pessoas físicas e registros sem relação com uma ofert

### REJECTED_INSUFFICIENT_EVIDENCE (total in counts)
- `DOD-definition-of-done-extra-013f5531a8`: sql_evidence_type_catalog_only — consulta SQL com resultado esperado;
- `DOD-definition-of-done-extra-da009871ae`: requires_real_execution_evidence — teste de restauração ou recuperação efetivamente executado;
- `DOD-definition-of-done-extra-21fbe7122d`: requires_real_execution_evidence — comparação com fonte oficial realizada na mesma data ou período.
- `DOD-rol-1-definition-of-done-7340e14412`: backup_requires_preexisting_complete_evidence_optional_family — O restore recompõe o universo-alvo.
- `DOD-rol-1-definition-of-done-ab49bd5c44`: backup_requires_preexisting_complete_evidence_optional_family — O restore preserva provenance.
- `DOD-rol-1-definition-of-done-7377c5510d`: backup_requires_preexisting_complete_evidence_optional_family — Um teste de restauração real está registrado antes de fechar o estágio
- `DOD-rol-2-definition-of-done-7be0deecf4`: backup_requires_preexisting_complete_evidence_optional_family — A política de backup externo foi definida.
- `DOD-rol-2-definition-of-done-4535689766`: backup_requires_preexisting_complete_evidence_optional_family — A chave de backup possui escopo mínimo.

### REJECTED_LIVE_DEPENDENCY (total in counts)
- `DOD-rol-1-definition-of-done-05358c643a`: needs_live_source — `stale` e `unknown` não contam para o numerador de cobertura. **Code-r
- `DOD-rol-1-definition-of-done-743cbec198`: needs_live_source — Pelo menos uma fonte complementar ao PNCP está provada ponta a ponta q
- `DOD-rol-1-definition-of-done-837df35edc`: needs_live_source — Encadeamento edital-contrato. `PARTIAL` — unit match rules only; not l


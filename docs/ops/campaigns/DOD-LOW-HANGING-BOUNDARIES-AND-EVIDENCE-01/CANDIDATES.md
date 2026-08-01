# CANDIDATES — DOD-LOW-HANGING-BOUNDARIES-AND-EVIDENCE-01

Generated: 2026-08-01T00:25:29.823297+00:00

## Decision counts

```json
{
  "REJECTED_NOT_LOW_HANGING": 1345,
  "SELECTED": 22,
  "REJECTED_HUMAN": 39,
  "REJECTED_PARALLEL_CONFLICT": 20,
  "REJECTED_INSUFFICIENT_EVIDENCE": 33,
  "REJECTED_LIVE_DEPENDENCY": 3
}
```

## SELECTED

- `DOD-definition-of-done-extra-75164c86da` [A_GOVERNANCE] L47: Código existente sem execução comprovada não é considerado concluído.
- `DOD-definition-of-done-extra-59ea375492` [A_GOVERNANCE] L48: Teste unitário isolado não substitui execução ponta a ponta.
- `DOD-definition-of-done-extra-d3db8c3907` [A_GOVERNANCE] L51: Alterações de escopo são refletidas primeiro neste documento e nos documentos canônicos do projeto.
- `DOD-definition-of-done-extra-cb23ed5034` [A_GOVERNANCE] L52: Itens explicitamente marcados como opcionais não bloqueiam o fechamento do projeto.
- `DOD-definition-of-done-extra-f0f41447dd` [A_GOVERNANCE] L55: requisitos do estágio atual;
- `DOD-definition-of-done-extra-b5522727b0` [A_GOVERNANCE] L56: requisitos posteriores ao provisionamento da VPS;
- `DOD-definition-of-done-extra-107a7ac4da` [A_GOVERNANCE] L57: requisitos independentes de infraestrutura.
- `DOD-definition-of-done-extra-5fd54bbd01` [A_GOVERNANCE] L77: teste automatizado reproduzível;
- `DOD-definition-of-done-extra-56586465e9` [A_GOVERNANCE] L78: comando documentado com exit code `0`;
- `DOD-definition-of-done-extra-374c5965bd` [A_GOVERNANCE] L81: execução registrada em ledger, manifest ou tabela de runs;
- `DOD-definition-of-done-extra-3104de3131` [A_GOVERNANCE] L82: log datado e correlacionável;
- `DOD-definition-of-done-extra-349bb54c8f` [A_GOVERNANCE] L84: commit ou pull request identificável;
- `DOD-definition-of-done-extra-07fdce3052` [B_SCOPE_EXCLUDED] L154: O projeto não contém Kubernetes, Kafka, Redis ou Elasticsearch sem necessidade comprovada.
- `DOD-definition-of-done-extra-383035c911` [C_CLI_UX] L171: Erros são apresentados com causa provável e próximo passo.
- `DOD-definition-of-done-extra-ea60d7c534` [C_CLI_UX] L172: O sistema permite repetir uma execução sem criar inconsistência.
- `DOD-definition-of-done-extra-ef20844eb2` [C_CLI_UX] L174: O sistema permite identificar quando um dado não é confiável.
- `DOD-rol-1-definition-of-done-5412da3ad7` [D_COVERAGE_TRUTH] L546: A média entre as duas coberturas não é usada para mascarar uma delas. **Code-ready (not accepted):** dual engine has no 
- `DOD-rol-1-definition-of-done-5eca319947` [D_COVERAGE_TRUTH] L548: Uma fonte saudável para contratos não prova cobertura de editais. **Code-ready (not accepted):** unit test_contracts_do_
- `DOD-rol-1-definition-of-done-0c828cadb4` [D_COVERAGE_TRUTH] L558: `data_presence` nunca é chamada de cobertura. **Code-ready (not accepted):** dual engine separates data_presence_* · cla
- `DOD-rol-1-definition-of-done-3fb8978ae7` [D_COVERAGE_TRUTH] L461: A média entre as duas coberturas não é usada para mascarar uma delas.
- `DOD-rol-1-definition-of-done-b9c4d94a8e` [D_COVERAGE_TRUTH] L463: Uma fonte saudável para contratos não prova cobertura de editais.
- `DOD-rol-1-definition-of-done-90c4a972f6` [D_COVERAGE_TRUTH] L473: `data_presence` nunca é chamada de cobertura.

## Rejected (sample by reason)

### REJECTED_HUMAN (39)
- `DOD-definition-of-done-extra-2974cd669a`: human_eval_required — Um requisito somente pode ser tratado como `NOT_APPLICABLE` quando a própria red
- `DOD-definition-of-done-extra-e21af5fe47`: human_eval_required — validação manual registrada por Tiago;
- `DOD-definition-of-done-extra-b207150950`: human_eval_required — O sistema ajuda Tiago a decidir quais oportunidades merecem análise humana.
- `DOD-definition-of-done-extra-8268a89973`: human_eval_required — Tiago é o único usuário obrigatório do sistema.
- `DOD-definition-of-done-extra-2e6f8b0d22`: human_eval_required — A conclusão final permanece sujeita ao aceite de Tiago e da empresa.
- `DOD-definition-of-done-extra-26b93711d5`: human_eval_required — Os top-20, ou todos os casos quando houver menos, passam por revisão manual inic
- `DOD-definition-of-done-extra-c1ec59e4b7`: human_eval_required — O primeiro ciclo de uso real registra decisões de Tiago, contatos realizados e r
- `DOD-definition-of-done-extra-3690db41e4`: human_eval_required — Tiago aceita formalmente a fila como utilizável para iniciar a prospecção da CON
- `DOD-rol-1-definition-of-done-5f4e1f06b7`: human_eval_required — O setup não depende de caminhos absolutos do computador de Tiago.
- `DOD-rol-1-definition-of-done-a669911ea1`: human_eval_required — Tiago consegue instalar o projeto seguindo apenas a documentação.
- `DOD-rol-1-definition-of-done-67e9108d7f`: human_eval_required — Tiago consegue recriar o banco local.
- `DOD-rol-1-definition-of-done-309bff987f`: human_eval_required — Tiago consegue importar a planilha.
- `DOD-rol-1-definition-of-done-277f48e159`: human_eval_required — Tiago consegue executar o golden path.
- `DOD-rol-1-definition-of-done-4ecdf34272`: human_eval_required — Tiago consegue gerar uma lista atual de editais.
- `DOD-rol-1-definition-of-done-b794bfe776`: human_eval_required — Tiago consegue identificar a data da última verificação de cada edital.

### REJECTED_INSUFFICIENT_EVIDENCE (33)
- `DOD-definition-of-done-extra-013f5531a8`: sql_evidence_type_catalog_only — consulta SQL com resultado esperado;
- `DOD-definition-of-done-extra-da009871ae`: requires_real_execution_evidence — teste de restauração ou recuperação efetivamente executado;
- `DOD-definition-of-done-extra-21fbe7122d`: requires_real_execution_evidence — comparação com fonte oficial realizada na mesma data ou período.
- `DOD-rol-1-definition-of-done-7340e14412`: backup_requires_preexisting_complete_evidence_optional_family — O restore recompõe o universo-alvo.
- `DOD-rol-1-definition-of-done-ab49bd5c44`: backup_requires_preexisting_complete_evidence_optional_family — O restore preserva provenance.
- `DOD-rol-1-definition-of-done-7377c5510d`: backup_requires_preexisting_complete_evidence_optional_family — Um teste de restauração real está registrado antes de fechar o estágio local.
- `DOD-rol-2-definition-of-done-7be0deecf4`: backup_requires_preexisting_complete_evidence_optional_family — A política de backup externo foi definida.
- `DOD-rol-2-definition-of-done-4535689766`: backup_requires_preexisting_complete_evidence_optional_family — A chave de backup possui escopo mínimo.
- `DOD-rol-2-definition-of-done-7e136797e8`: backup_requires_preexisting_complete_evidence_optional_family — O backup possui timer.
- `DOD-rol-2-definition-of-done-c76b3eab51`: backup_requires_preexisting_complete_evidence_optional_family — O teste de restore possui timer ou rotina periódica documentada.
- `DOD-rol-2-definition-of-done-ff04f58609`: backup_requires_preexisting_complete_evidence_optional_family — Backup é armazenado fora da VPS principal.
- `DOD-rol-2-definition-of-done-15e9773b0b`: backup_requires_preexisting_complete_evidence_optional_family — Backup é criptografado em trânsito.
- `DOD-rol-2-definition-of-done-dbb0b717b9`: backup_requires_preexisting_complete_evidence_optional_family — Backup possui retenção diária.
- `DOD-rol-2-definition-of-done-1d81ae208e`: backup_requires_preexisting_complete_evidence_optional_family — Backup possui retenção semanal.
- `DOD-rol-2-definition-of-done-f2da9df964`: backup_requires_preexisting_complete_evidence_optional_family — Backup possui integridade verificada.

### REJECTED_LIVE_DEPENDENCY (3)
- `DOD-rol-1-definition-of-done-05358c643a`: needs_live_source — `stale` e `unknown` não contam para o numerador de cobertura. **Code-ready (not 
- `DOD-rol-1-definition-of-done-743cbec198`: needs_live_source — Pelo menos uma fonte complementar ao PNCP está provada ponta a ponta quando nece
- `DOD-rol-1-definition-of-done-837df35edc`: needs_live_source — Encadeamento edital-contrato. `PARTIAL` — unit match rules only; not live edital

### REJECTED_NOT_LOW_HANGING (1345)
- `DOD-definition-of-done-extra-934b7e1a8d`: already_accepted_or_checked — O denominador estratégico permaneceu fixo em **1.093 entidades**. Evidência: `ou
- `DOD-definition-of-done-extra-3291212c84`: already_accepted_or_checked — `commercial_opportunity_any` foi reclassificada como sinal comercial `entities_w
- `DOD-definition-of-done-extra-ea8d68c1d0`: already_accepted_or_checked — Existe registro canônico explícito para **1.093/1.093 entidades**, sincronizado 
- `DOD-definition-of-done-extra-30700f5da5`: already_accepted_or_checked — A cobertura operacional usa sete estágios, SLA e proveniência (`run_id`, raw URI
- `DOD-definition-of-done-extra-b66ffceb51`: already_accepted_or_checked — Existe relatório nominal para os **1.093 gaps**, cada um com blocker e próxima a
- `DOD-definition-of-done-extra-7249b8dd2b`: already_accepted_or_checked — DOM/SC e DOE/SC possuem caminhos públicos sem credenciais. Evidência live: CIGA 
- `DOD-definition-of-done-extra-066ad585f6`: already_accepted_or_checked — Migrations 052/053 foram aplicadas localmente após snapshot; 1.093 registros de 
- `DOD-definition-of-done-extra-aa33c98608`: already_accepted_or_checked — O workspace cotidiano executa `today`, `opportunities`, `dossier`, `coverage`, `
- `DOD-definition-of-done-extra-84020f8bef`: already_accepted_or_checked — O benchmark preliminar contém quatro publicações oficiais CIGA com ID, URL e has
- `DOD-definition-of-done-extra-a66931160b`: already_accepted_or_checked — Testes críticos deste ciclo: **74 passed**; golden path estrito PCP: `gp-2026071
- `DOD-definition-of-done-extra-852912a5cd`: already_accepted_or_checked — CI obrigatório da PR #10 verde: ruff, mypy, testes críticos, bandit e pip-audit.
- `DOD-definition-of-done-extra-5dc9c98e70`: already_accepted_or_checked — Suíte global completa verde. Evidência: CI run `29794247186` (Test All full suit
- `DOD-definition-of-done-extra-ef7e127720`: already_accepted_or_checked — Freshness coverage mensurável por entidade dentro dos SLAs. Evidência: campanha 
- `DOD-definition-of-done-extra-908bae4c12`: forbidden_theme:recall independente — Recall independente e estratificado ≥95%.
- `DOD-definition-of-done-extra-12c05bb055`: forbidden_theme:cobertura operacional ≥95 — Cobertura operacional ≥95% (mínimo **1.039/1.093** entidades).

### REJECTED_PARALLEL_CONFLICT (20)
- `DOD-definition-of-done-extra-75d4c221ed`: commercial_or_confenge:comercial — `NOT_APPLICABLE` possui justificativa, data e evidência; não é usado para contor
- `DOD-definition-of-done-extra-ad80befdaa`: commercial_or_confenge:confenge — O sistema ajuda a CONFENGE a identificar, no dataset de contratos, empresas com 
- `DOD-definition-of-done-extra-716fd4472f`: commercial_surface — O sistema transforma sinais comerciais em uma fila pequena, explicável e acionáv
- `DOD-definition-of-done-extra-8736745636`: commercial_or_confenge:confenge — Prospecção orientada por dados para a CONFENGE a partir de sinais observáveis em
- `DOD-definition-of-done-extra-d27b80d991`: commercial_or_confenge:comercial — O projeto não assume responsabilidade técnica, jurídica, contábil ou comercial p
- `DOD-definition-of-done-extra-e492baef47`: commercial_or_confenge:comercial — O sistema apoia revisão de coerência entre proposta comercial, planilha, cronogr
- `DOD-definition-of-done-extra-8f3fb664b7`: commercial_or_confenge:confenge — Existe perfil comercial versionado da CONFENGE com serviços ofertados, segmentos
- `DOD-definition-of-done-extra-132d68ad15`: commercial_or_confenge:confenge — Órgãos públicos, pessoas físicas e registros sem relação com uma oferta da CONFE
- `DOD-definition-of-done-extra-722c073639`: commercial_or_confenge:comercial — Fatores de confiança e qualidade dos dados não são confundidos com interesse com
- `DOD-definition-of-done-extra-9ec4a43c9e`: commercial_or_confenge:comercial — Cada item possui estado comercial controlado: `NEW`, `REVIEWED`, `QUALIFIED`, `D
- `DOD-definition-of-done-extra-b63d83f1d0`: commercial_or_confenge:confenge — A fila informa uma ação humana concreta e uma mensagem de valor compatível com o
- `DOD-definition-of-done-extra-8eff83344b`: commercial_or_confenge:outcome — “Propensão” ou probabilidade de compra só pode ser publicada depois de amostra s
- `DOD-definition-of-done-extra-8379cd9d79`: commercial_or_confenge:comercial — O perfil comercial e o catálogo de sinais estão versionados.
- `DOD-definition-of-done-extra-5717654d5f`: commercial_or_confenge:outcome — A fila registra estado, próximo passo, feedback e outcomes comerciais.
- `DOD-rol-3-definition-of-done-f9d55d3a7c`: commercial_or_confenge:confenge — PRD está alinhado ao DOD. `REGRESSION` em 2026-07-25: o PRD v2.1 ainda não incor


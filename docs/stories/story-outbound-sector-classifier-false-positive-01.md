# Story: Corrigir falso positivo do classificador de setor/ICP que confirmou Sistema S e instituições parafiscais como alvo comercial B2G

## Status

**Done** — **FECHADA pelo @po (Pax) em 2026-09-01.** `po_closed: true` · `publication_authorized: false` · próxima etapa: **@devops** executa a Task 7 (2 PRs).

> ## ⇒ Fechamento formal por @po (Pax) em 2026-09-01 — story FECHADA, status preservado em `Done`
>
> Veredito **CONCERNS** aceito. **Âncora de revisão reconferida antes de qualquer escrita: 15/15 sha256 MATCH.** Chave de fechamento registrada no Change Log (linha 0.8.0), que é o artefato autoritativo.
>
> **REQ-003 resolvido por evidência, não estreitado:** a conta do incidente é a raiz **`27364462`** (SEBRAE-ES), não `27080530` (que é o **órgão comprador** do identificador de contrato). Ela está na shadow como `TARGET_CONFIRMED`, tem 185 contratos como fornecedora, **não** pertence à coorte das 1.448, e **é suprimida pelo gate desta story** (marcador `sebrae` casa em 13 variantes de `fornecedor_nome`). Não há terceira via de entrada.
>
> **`MNT-003-REVISED`: o gatilho da minha Ratificação nº 5 DISPAROU e foi emendado por escrito**, não aceito em silêncio — a premissa ("2 call sites") era falsa, o propósito segue satisfeito por discriminante melhor e falsificável. Fica como **dívida com draft próprio, owner e prazo**, não como linha de tabela. **`PROC-001`, `DOC-001`, `MNT-001`, `MNT-002`, `MNT-004`** também fechados com destino nomeado.
>
> **Contenção manual verificada read-only:** 14 contas com `do_not_contact`/`blocked` — **band-aid**; a causa raiz é resolvida pelo **deploy** desta correção.
>
> **AC 17, AC 20 e AC 25(b) permanecem diferidos ao @devops por desenho.** Ver **Fechamento do @po** e **Handoff para @devops**.

> ## ⇒ QA Gate iteração 2 por @qa (Quinn) em 2026-09-01 — **CONCERNS** — `InReview` → `Done`
>
> A lacuna que causou o FAIL da iteração 1 está **fechada e verificada de forma independente pelo caminho mais forte disponível**: chamei `loader.load_company_input` — o mesmo que `worker.py:144` chama — contra a base viva em modo somente leitura, em vez de reimplementar a projeção. **4 de 4 raízes Sistema S saem de `TARGET_CONFIRMED` para `TARGET_OUT_OF_SCOPE`** com `n_exec` 6/3/3/0 preservado. Blast radius reproduzido **exatamente**: 68 raízes de 8.667, **zero construtoras**, 1 fronteiriça (FEESC, já declarada). Suíte: **187 IDs no HEAD × 188 na working tree**, o único delta passa isolado nos dois lados — **zero regressão real**.
>
> **CONCERNS, não PASS, por dois motivos:** (i) **`MNT-003` é mais amplo do que a story descreve** — além dos 2 call sites que o @po nomeou (ambos `True`), existem **3 que omitem o argumento** e herdam o default `False`; 67 das 68 raízes voltariam por esse ramo. **Não é bloqueante** porque os comandos que **constroem o feed** passam `True` nos dois pontos de entrada, enquanto os que herdam `False` apenas **enriquecem contato** — não publicam feed nem disparam e-mail. *(Não uso "agendado" como argumento: conferi que `extra-confenge-contact-cycle.timer` e `extra-confenge-feed-cycle.timer` estão **disabled** — os dois ciclos são disparados a mão.)*; (ii) **`publish.py` — arquivo congelado — tem 35 linhas não commitadas de outra story**, não declaradas por ninguém. O AC 25(a) foi provado **independente** delas (passa contra o `publish.py` do HEAD).
>
> **Âncora de revisão:** a working tree é compartilhada com um agente concorrente **ativo**. Os **sha256 dos 15 arquivos revisados** estão no gate file (`devops_pr1_separation.reviewed_sha256`). **@devops: conferir antes de abrir o PR 1** — divergência significa que o arquivo mudou depois do gate e o veredito não o cobre.
>
> **AC 17, AC 20 e AC 25(b) são pendências do @devops por desenho e não rebaixam o veredito.** `MNT-003-REVISED` e `PROC-001` ficam como itens de fechamento do @po.
>
> Gate: `docs/qa/gates/outbound-sector-classifier-false-positive-01.yml`

> ## ⇒ Iteração 2 implementada por @dev (Dex) em 2026-09-01 — `InProgress` → `InReview`
>
> **T9.1 a T9.8 concluídas.** Defesa primária implementada onde ela alcança o caminho de produção: gate parafiscal **incondicional** em `classify_target_fit`, sobre a superfície de nome C4, com fonte única em `scripts/confenge_universe/parafiscal.py` e drift de `classifier_sha()`.
>
> **Validação empírica reproduzida por medição própria (não herdada):** com 1.552 contratos reais de produção (read-only), **4 de 4 raízes Sistema S saem de `TARGET_CONFIRMED` → `TARGET_OUT_OF_SCOPE`**, com `n_exec` 6/3/3/0 preservado e auditável (AC 21). Números convergentes com o @architect (D.3).
>
> **Suíte completa:** 5.457 passed / 134 failed / 53 errors contra 5.370 / 134 / 53 no HEAD — **conjuntos de IDs de falha idênticos**. Zero delta em todos os gates já verdes. Ruff limpo.
>
> **Pendente do @qa no re-review:** AC 17 (medição pós-deploy), AC 20 (@devops), AC 25(b) (@devops, build real), e a verificação do `MNT-003` que o @po atribuiu explicitamente ao @qa. Ver **Dev Agent Record — Iteração 2**.

> ## ⇒ Ready for Dev Loop Iteration 2 — PO Ratified
>
> **@po (Pax), 2026-09-01.** Story **LIBERADA para o @dev** reimplementar (iteração 2 do QA loop). Status permanece `InProgress` — não há transição de status nesta ratificação.
>
> **O que foi ratificado:** desenho (c) do @architect; **ACs 21, 22, 23 ratificados como propostos**; **AC 24 REESCRITO pelo @po** (o texto do @architect era vacuoso — ver Ratificação nº 1); **AC 25 ACRESCENTADO pelo @po** (completude de revogações em `publish.py`); **AC 11 rebaixado a defesa em profundidade** (asserção inalterada, papel alterado); **AC 17 reescrito** (denominador 4→0, SQL corrigido, ressalva SHADOW desinvertida); **AC 20(a) corrigido pela terceira vez** — o rebind do PR 2 é de **5 caminhos congelados**, não 4: `parafiscal.py` **É congelado** por fechamento transitivo de imports (verificado empiricamente pelo @po; a afirmação contrária em D.2/C1 é falsa).
>
> **Escopo do @dev:** T9.1 a T9.8 do D.11, com as correções desta ratificação. **Não reabrir** ACs 1-16, 18, 19 — verificados independentemente pelo @qa.
>
> **REQ-003 permanece ABERTO e vira gate de fechamento** (não bloqueia a implementação). Ver Ratificação nº 4.
>
> Detalhamento completo: seção **Ratificação do @po — Architect Revision (iteração 2)**, no final deste documento.

> **Revisão de arquitetura concluída por @architect (Aria) em 2026-09-01 — story PRONTA para @dev reimplementar (QA loop, iteração 2).** O achado bloqueante REQ-001 era lacuna do meu desenho, não da implementação: a exclusão parafiscal foi colocada em `resolve_identity`, que o caminho de produção nunca consulta. O novo desenho, os ACs 21-24 propostos e a **validação empírica das 4 raízes Sistema S saindo de `TARGET_CONFIRMED`** estão na seção **Architect Revision — Ready for Dev Loop Iteration 2**, no final deste documento. Status permanece `InProgress`.

> Retornada a `InProgress` por @qa (Quinn) em 2026-09-01 — **QA Gate FAIL**. Medição direta em produção falsifica o AC 17 e o Estado-alvo: 3 das 4 raízes Sistema S em `TARGET_CONFIRMED` permanecem confirmadas após a mudança. Ver **QA Results**. O item bloqueante (REQ-001) é lacuna de design, não defeito de implementação — deve ser escalado a @architect + @sm, não corrigido diretamente pelo @dev.

> Implementada por @dev (Dex) em 2026-09-01. Transições: `Ready → InProgress → InReview`. Veredito de qualidade pendente do gate sistêmico conjunto @architect + @qa (obrigatório por HIGH-RISK). Ver **Dev Agent Record**.

> Validada por @po (Pax) em 2026-09-01 com veredito **GO — 9/10**. Status transicionado explicitamente de `Draft` para `Ready`. Os 6 pontos deixados em aberto pelo @sm foram decididos e estão registrados na seção **Decisões do @po** abaixo. Nenhuma questão permanece em aberto para o @dev.

## Risk Level

**HIGH-RISK** — confirmado por @architect por 3 motivos independentes e concorrentes:

1. Efeito externo já materializado e irreversível em produção — governa o disparo real de e-mail comercial (e-mail já enviado a `contato.sebrae@es.sebrae.com.br` em 2026-09-01 12:00 UTC).
2. Altera inputs protegidos pelo code-freeze de campanha (`contract_relevance.py`, `target_fit.py`, `pipeline.py` estão CONGELADOS; `identity.py` não está).
3. Mudança sistêmica de classificador com ~15 call sites reais em 8 módulos, incluindo fingerprints de versão de regra e a cadeia até `publish.py`.

Fluxo aplicável: @architect (concluído) → @sm (este documento) → @po → @dev → @qa aprofundado → gate sistêmico → @po → @devops.

## Executor Assignment

executor: "@dev"
quality_gate: "@architect + @qa (gate sistêmico conjunto, obrigatório para HIGH-RISK)"
quality_gate_tools: ["pytest", "eval_contract_relevance_holdout", "eval_contract_relevance_real_holdout", "coderabbit", "confenge_make_gates"]

## Story

**Como** founder responsável pela ativação do outbound B2G da CONFENGE,
**quero** que o classificador de setor/ICP de construção deixe de confirmar Sistema S, dioceses, fundações educacionais e universidades como `TARGET_CONFIRMED`,
**para que** o pipeline de outbound comercial nunca mais dispare e-mail comercial real para entidades que não são clientes potenciais de execução de obra/construção civil.

## Contexto e autoridade

- Incidente confirmado por auditoria adversarial com dados reais de produção nesta mesma sessão (@architect). Não é hipótese: houve envio real de e-mail comercial ao SEBRAE-ES em 2026-09-01 12:00 UTC, contrato de origem `27080530000143-2-000648/2024`, objeto real: "...contratação do serviço de locação de estande com espaço personalizado e exclusivo na ES CONSTRUÇÃO BRASIL 2024 – FEIRA DA CONSTRUÇÃO CIVIL...".
- A causa raiz tem duas faces que se reforçam: (a) o classificador de relevância de contrato/target-fit trata presença física em evento de construção civil (estande, feira, patrocínio) e menção genérica ao token `"fundacao"` como evidência de execução de obra; (b) o identificador de entidade não possui taxonomia de exclusão para Sistema S / serviço social autônomo / entidades religiosas / entidades de ensino fundacional — hoje essas entidades passam pela identidade sem bloqueio e, combinadas com (a), acumulam falso positivo suficiente para `TARGET_CONFIRMED`.
- Contenção imediata de produção (setar `do_not_contact=true` nas ~14 contas Sistema S na tabela `outreach_accounts` do warmbly) é uma ação operacional direta em produção, **fora do ciclo desta story de código**, e requer autorização explícita do usuário e execução pelo operador/@devops antes ou em paralelo ao ciclo de dev. Esta story apenas referencia essa necessidade — não a executa.
- Design técnico completo já produzido por @architect nesta sessão (arquivos, mudanças, ACs, resultados empíricos e mapa de regressão) é a fonte de verdade para o escopo abaixo. Nada neste documento foi inventado além do que @architect determinou; onde @architect apontou lacuna, está registrado como abertura para o @po, não como AC fechado.

## Scope

**IN:**
- Correção de precisão no classificador de relevância de contrato (`contract_relevance.py`) e no `target_fit.py`, incluindo mecanismo de "neutralização de evidência" para pessoa jurídica `Fundação <qualificador>` e para presença física em evento de construção civil.
- Correção de recall inversa em `identity.py`: `"fundacao"` hoje causa falso NEGATIVO em `DEFAULT_ORGAN_MARKERS` para empresas privadas de engenharia legítimas (ex.: "FUNDAÇÃO ENGENHARIA E CONSTRUÇÕES LTDA").
- Nova taxonomia de exclusão `PARAFISCAL_INSTITUTIONAL` em `identity.py` cobrindo Sistema S, entidades religiosas e entidades de ensino fundacional.
- Correção do prefiltro SQL posicional em `pipeline.py` que quebraria silenciosamente o recall de contratos legítimos de fundação profunda ao remover `"fundacao"` das tuplas sem desacoplar o prefiltro.
- Bump de `RULE_VERSION`/`TARGET_FIT_VERSION` e recomputação de fingerprints em `confenge_sector/store.py` e `confenge_target_fit/compute.py`.
- Revalidação dos ~15 call sites reais listados no mapa de regressão do @architect.
- Sequência de re-freeze em 2 PRs: PR de código primeiro (os **6 arquivos de código** do File List, não 4 — ver correção do @po no AC 20) → PR separado artifact-only atualizando o binding/hash do freeze de campanha.
- Planejamento de deploy e reclassificação pós-deploy em produção (comandos, não execução autônoma sem autorização).

**IN — acrescentado pelo @po na iteração 2 (é a mudança mais importante da story e estava ausente do Scope):**

- **Gate parafiscal incondicional dentro de `classify_target_fit`** (`scripts/confenge_universe/target_fit.py`), colocado após o loop de contratos e antes de todo path de confirmação, avaliando a superfície de nome completa (`razao_social` + `nome_fantasia` + todo `fornecedor_nome` distinto em `contracts`), **sem cláusula `n_exec == 0`**. É esta a defesa primária do caminho que governa o outbound; a exclusão em `identity.py` passa a defesa em profundidade.
- **Novo módulo `scripts/confenge_universe/parafiscal.py`** como fonte única da taxonomia parafiscal, importado por `identity.py` e por `compute.py`. Fica **congelado** por fechamento transitivo de imports — entrada nova no manifesto de freeze.
- **`classifier_sha()` em `scripts/confenge_target_fit/compute.py` passa a hashear `parafiscal.py`**, para que alteração futura da taxonomia continue disparando reenfileiramento no `reconcile`.
- **Passo manual e explícito de rerun do universe builder** no plano de deploy (não há timer systemd — não acontece sozinho).

**OUT (registrado com justificativa, decisão do @architect):**
- Gap de proveniência de 1.448 contas `TARGET_CONFIRMED` com `contracts_json` vazio no warmbly + 27 contas "UNKNOWN". Story separada — depende de denominador estável pós-fix e tem perfil de risco de disponibilidade/degradação, não de precisão. Ponto de entrada: `scripts/confenge_activation/publish.py::_validate_authoritative_manifest` (linha ~434), gancho `party_roles.buyer_supplier_conflict_fails_closed` (linhas ~468-470).
- Exclusão de capacitação/treinamento do ICP (termos `capacitacao`, `treinamento`, `curso de`, `palestra`). Testado pelo @architect e comprovado que quebra recall legítimo. Decisão de política comercial, não de precisão — abertura para o @po.
- 3 divergências remanescentes do conjunto adversarial (curso de engenharia civil, bloco didático, estande de tiro) já eram `False` ANTES da mudança — gap de recall pré-existente, não regressão introduzida por esta story. Follow-up separado.
- Guarda de word-boundary para `"estande"` vs `"estande de tiro"` **não é** story separada — está incluída como parte da implementação do AC 1 desta story.
- Contenção operacional imediata (`do_not_contact=true` no warmbly) — ação direta em produção fora do ciclo de código, requer autorização explícita do usuário.

## Dependencies and sizing

- Depende da conclusão do design técnico do @architect (já entregue, incorporado integralmente neste documento).
- Depende da liberação/replanejamento do code-freeze de campanha: código primeiro, depois re-freeze artifact-only separado.
- ~~Depende de decisão do @po sobre contenção e mecanismo de reclassificação.~~ **RESOLVIDO** — ver seção "Decisões do @po" (nº 1 e nº 2). Restam apenas: (a) autorização humana explícita do usuário para a contenção em produção (fora do poder do @po); (b) execução do Task 8.0 pelo @dev.
- T-shirt size: **L** (**atualizado pelo @po na iteração 2 — o tamanho não muda, o conteúdo sim**). Diff moderado em **7 arquivos de código** (5 da iteração 1 + `parafiscal.py` novo + `compute.py`), mas superfície de regressão ampla (15 call sites, 8 módulos), gate sistêmico obrigatório e sequência de 2 PRs de re-freeze cobrindo **5 caminhos congelados** (4 rebinds + 1 entrada nova). O diff adicional da iteração 2 é pequeno e concentrado; o que cresceu foi o escopo de re-freeze e o de medição pós-deploy (2 superfícies, não 1).

## Risks and mitigations

- Regressão silenciosa no prefiltro SQL (`pipeline.py`) — mitigado pelo AC 14 (teste comparando cláusulas ILIKE antes/depois) e pela constante nomeada `SQL_PREFILTER_SEEDS` desacoplada da ordem das tuplas.
- Falso positivo residual em outras entidades parafiscais não listadas — mitigado por reclassificação do corpus real de 1076 objetos como teste de não-regressão formal (AC 16) e por medição direta da população Sistema S em produção (AC 17).
- Quebra de recall legítimo (fundação profunda, empreitada, capacitação) — mitigado pelos ACs 6-10 com fixtures nomeadas e pelo gate de holdout rotulado (AC 15).
- Redução de população `TARGET_CONFIRMED` confundida com incidente novo no deploy — mitigado por antecipar o delta no plano de execução (Dev Notes) e por vincular explicitamente a `_assert_membership_deactivation_delta`/`MEMBERSHIP_DROP_REASON` em `publish.py` como comportamento esperado.
- Sequência de re-freeze incorreta (código e binding no mesmo PR) — mitigado pelo AC 20, que exige 2 PRs distintos e `verify_confenge_artifact_binding` (ou script equivalente a localizar) PASS após o segundo.
- Reincidência de contato comercial com Sistema S enquanto o fix não está publicado — mitigado pela contenção imediata (`do_not_contact=true`), fora desta story de código mas referenciada como pré-requisito operacional.

## Baseline (estado atual, medido pelo @architect)

- Gate rotulado (P≥0.95 / R≥0.90), n=44: P=1.0 R=1.0.
- Corpus real n=1076 contratos: `relevance PASS` = 222; `is_execution` = 100.
- 6 casos adversariais-alvo hoje classificados incorretamente como `execution=True` (estande em feira, patrocínio em congresso, Fundação Municipal de Cultura, Fundação de Apoio, Fundação Educacional, inscrição em seminário).
- 3 divergências pré-existentes já `False` hoje (curso de engenharia civil, bloco didático, estande de tiro) — não fazem parte do escopo de correção.
- Produção: 14 entidades Sistema S atualmente em `TARGET_CONFIRMED` — **correção de camada do @po (iteração 2): este "14" é da tabela `outreach_accounts` do warmbly, NÃO da camada target-fit.** Na camada que governa o outbound (`confenge_target_fit_shadow`) são **4** raízes Sistema S em `TARGET_CONFIRMED`, 7 em `PROBABLE` e 1 já em `OUT_OF_SCOPE` — medição independente e convergente do @qa e do @architect. A população parafiscal total (não só Sistema S) na base de fornecedores é de **568** raízes, todas materializadas na shadow (376 INSUFFICIENT + 88 PROBABLE + 68 CONFIRMED + 36 já OUT). Confundir as duas camadas foi a causa direta do AC 17 insatisfazível na iteração 1.

## Estado-alvo

**Reescrito pelo @po em 2026-09-01 (iteração 2).** O Estado-alvo anterior foi **falsificado em produção** pelo @qa e é a segunda metade do achado bloqueante REQ-001: ele nomeava a camada errada ("14 → 0" é `outreach_accounts` do warmbly) e atribuía a defesa primária a `resolve_identity`, que o caminho de outbound nunca consulta. Estado-alvo corrigido:

- Os 6 casos adversariais-alvo passam a `execution=False` sem afetar o gate rotulado nem o corpus real (zero regressão medida fora dos 6 casos-alvo). **[já atingido — verificado pelo @qa]**
- **DEFESA PRIMÁRIA:** `classify_target_fit` aplica gate parafiscal incondicional; as **4** raízes Sistema S em `TARGET_CONFIRMED` na `confenge_target_fit_shadow` passam a `TARGET_OUT_OF_SCOPE` (**4 → 0** nesta camada). `TARGET_CONFIRMED` total cai **68** (8.667 → ~8.599); o reason code aparece em ~**568** linhas; ~**532** transições de classe.
- **DEFESA EM PROFUNDIDADE:** `resolve_identity` bloqueia Sistema S, entidades religiosas e entidades de ensino fundacional com `exclusion_code == "PARAFISCAL_INSTITUTIONAL"`, e `eligibility.py` mapeia para `NOT_CONSTRUCTION` — protegendo o caminho universe builder → `planner.py`/`publish.py`. **Não** protege o feed contínuo (que lê a shadow sem join de universo).
- `resolve_identity` deixa de bloquear incorretamente empresas privadas de engenharia com "fundação" no nome, **e o mesmo vale na camada `classify_target_fit`** (AC 24a).
- Prefiltro SQL permanece amplo (superconjunto estrito do atual), preservando recall antes da camada de precisão em Python.
- A publicação **não é recusada** por completude: as 68 revogações viajam declaradas com `MEMBERSHIP_DROP_REASON` (AC 25).
- Fingerprints de regra e binding do freeze de campanha atualizados de forma rastreável, em 2 PRs sequenciais (**5 caminhos congelados** no PR 2, sendo 1 entrada nova).
- ~~**NÃO declarado como atingido:** a cadeia do incidente concreto (SEBRAE-ES, raiz `27080530`) — ver REQ-003 / Ratificação nº 4. Esta story previne a **classe** do erro nas duas superfícies mapeadas; a via de entrada daquela conta específica no warmbly permanece não explicada e é gate de fechamento, não de implementação.~~
- **SUPERADO no fechamento (@po, 2026-09-01) — a cadeia do incidente está EXPLICADA e coberta.** A raiz `27080530` **não é a conta**: é o **órgão comprador** dentro do identificador de contrato `27080530000143-2-000648/2024`. A conta que recebeu o e-mail é a raiz **`27364462`** (SEBRAE-ES, `27364462000144`), presente em `confenge_target_fit_shadow` como `TARGET_CONFIRMED`/`confenge-target-fit-v2`, com **185 contratos como fornecedora** e `contracts_json` **não vazio** no warmbly. Entrou pela **superfície primária já mapeada** (shadow → feed), e suas 13 variantes de `fornecedor_nome` **casam o marcador `sebrae`** em `match_parafiscal_in_names` — logo é **suprimida pelo gate do AC 21**. Esta story previne a classe do erro **e** cobre o caso concreto. Evidência completa em **Fechamento do @po — item 6**.

## Acceptance Criteria

**Precisão — objetos que devem deixar de qualificar como execução:**

1. **Given** o texto `"...LOCAÇÃO DE ESTANDE...FEIRA DA CONSTRUÇÃO CIVIL..."`, **when** `_object_is_execution` é avaliado, **then** o resultado é `False`. A implementação deve usar guarda de word-boundary para `"estande"` (não substring nua), para não colidir com `"estande de tiro"` (obra real).
2. **Given** o texto `"PATROCÍNIO DE ESPAÇO EM CONGRESSO DE CONSTRUÇÃO CIVIL"`, **when** avaliado, **then** `_object_is_execution == False`.
3. **Given** o texto `"REPASSE A FUNDAÇÃO MUNICIPAL DE CULTURA PARA APOIO ADMINISTRATIVO"`, **when** avaliado, **then** `False`.
4. **Given** o texto `"CONTRATO COM A FUNDAÇÃO DE APOIO AO DESENVOLVIMENTO DA PESQUISA"`, **when** avaliado, **then** `False`.
5. **Given** o objeto de contrato real do incidente SEBRAE (fixture nomeada obrigatória em teste, contrato `27080530000143-2-000648/2024`, objeto contendo "...contratação do serviço de locação de estande com espaço personalizado e exclusivo na ES CONSTRUÇÃO BRASIL 2024 – FEIRA DA CONSTRUÇÃO CIVIL..."), **when** avaliado, **then** `False`.
    - **Nota de proveniência do @po (verificada):** o contrato `27080530000143` **não está** no corpus versionado — `grep -l "27080530000143" evals/commercial_leads/**/*.jsonl` não retorna nada, e `architect-exp3-baseline.py` contém apenas uma variante sintética (`"...LOCACAO DE ESTANDE NA FEIRA DA CONSTRUCAO CIVIL DE VITORIA"`), não o registro real. Portanto: **o fragmento citado acima É a fixture aceita** para o AC 5, com o identificador do contrato no nome/docstring do teste para rastreabilidade. O objeto integral não é recuperável a partir do repositório e **não deve ser exigido pelo @qa**. O fragmento carrega os tokens discriminantes (`locação de estande`, `feira da construção civil`), que é o que o AC precisa exercitar.

**Recall — objetos que devem continuar qualificando:**

6. **Given** `"EXECUÇÃO DE FUNDAÇÃO PROFUNDA COM ESTAQUEAMENTO..."`, **when** avaliado, **then** `True`.
7. **Given** `"SERVIÇOS DE FUNDAÇÃO E ESTRUTURA EM CONCRETO ARMADO"`, **when** avaliado, **then** `True`.
8. **Given** `"EXECUÇÃO DE OBRA DE ENGENHARIA COM FUNDAÇÃO EM SAPATA CORRIDA"`, **when** avaliado, **then** `True`.
9. **Given** `"EMPREITADA GLOBAL PARA CONSTRUÇÃO CIVIL DO GINÁSIO"`, **when** avaliado, **then** `True`.
10. **Given** `"CONSTRUÇÃO DE CENTRO DE CAPACITAÇÃO PROFISSIONAL EM ALVENARIA ESTRUTURAL"`, **when** avaliado, **then** `True` (capacitação NÃO é excluída do ICP nesta story — ver Out of Scope).

**Identidade:**

11. **Given** `resolve_identity(cnpj, "SEBRAE ES ...")` (e equivalentes para SENAI, SESI, SESC, SENAC, "MITRA DIOCESANA DE ..."), **when** avaliado, **then** `valid=False` e `exclusion_code == "PARAFISCAL_INSTITUTIONAL"`.
    - **Rebaixamento de papel ratificado pelo @po em 2026-09-01 (iteração 2).** A asserção continua **literalmente a mesma** e continua verde — não há mudança no que este AC verifica. Muda apenas o **papel**: este AC deixa de ser a defesa primária contra Sistema S no outbound e passa a ser **defesa em profundidade** do caminho `aggregate.py`/universe builder → `eligibility.py` → ativação/`publish.py`. A defesa primária do caminho que governa o outbound (`reconcile` → `compute` → `classify_target_fit` → `confenge_target_fit_shadow` → feed) passa a ser o **AC 21**. Motivo: medição do @qa provou que `classify_target_fit` nunca consulta `resolve_identity` (único call site: `aggregate.py:336`).
12. **Given** `resolve_identity(cnpj, "FUNDAÇÃO ENGENHARIA E CONSTRUÇÕES LTDA")`, **when** avaliado, **then** `valid=True` (regressão inversa corrigida).
13. **Given** `resolve_identity(cnpj, "CONSTRUTORA ALFA ENGENHARIA LTDA")`, **when** avaliado, **then** `valid=True` (sanity check, inalterado).

**Não-regressão sistêmica:**

14. **Given** a lista de cláusulas ILIKE geradas pelo prefiltro SQL de `pipeline.py` antes da mudança, **when** comparada com a lista após a mudança, **then** a nova lista é igual ou superconjunto estrito da atual (nunca um subconjunto). Teste dedicado obrigatório.
15. **Given** o gate `eval_contract_relevance_holdout` existente, **when** executado após a mudança, **then** mantém P≥0.95 e R≥0.90 (reutilizar o gate existente, não recriar).
16. **Given** o corpus real de 1076 objetos usado pelo @architect, **when** reclassificado após a mudança, **then** zero transições `execution True→False` fora dos 6 casos-alvo do item de precisão acima. O script de baseline do @architect foi **persistido pelo @po** em caminho durável no repositório: `docs/stories/assets/story-outbound-sector-classifier-false-positive-01/architect-exp3-baseline.py`. O @dev deve portá-lo para `tests/` como teste formal de não-regressão. **NÃO usar o caminho de scratchpad `/tmp/claude-1000/...` — é efêmero e some entre sessões.**
    - **Fonte do corpus verificada pelo @po:** o script lê `evals/commercial_leads/real/*.jsonl` (corpus real) e `evals/commercial_leads/*.jsonl` (corpus rotulado). Ambos são **arquivos versionados no git** — não há dependência de banco de produção. O teste portado é portanto executável em CI sem credenciais. `evals/commercial_leads/real/` é `EVIDENCE_LAG_PREFIX` no `confenge_frozen_inputs.py`, logo não bloqueia o freeze. **`wc -l evals/commercial_leads/real/*.jsonl` = 1076**, confirmando o n=1076 da seção Baseline.
    - **Requisito de portabilidade (obrigatório ao portar):** `architect-exp3-baseline.py` contém `sys.path.insert(0, "/home/tjsasakifln/code/confenge/extra-cli")` e globs com caminho absoluto. O teste portado **deve** usar caminhos relativos ao repositório (ex.: via `pathlib.Path(__file__).parents[N]`), caso contrário não roda em CI — que é exatamente onde o AC 16 precisa passar.
17. **REESCRITO pelo @po em 2026-09-01 (iteração 2) — substitui integralmente o texto anterior.** **Given** a população parafiscal em `confenge_target_fit_shadow` (a tabela que de fato governa o outbound; produção está em `TARGET_FIT_ASYNC_MODE=SHADOW` e `confenge_company_target_fit_current` tem 0 linhas), **when** reclassificada após deploy pelo `reconcile` (drift de `classifier_sha`/`TARGET_FIT_VERSION`, mecanismo do Task 8.0 — ratificado como suficiente **desde que** o gate do AC 21 exista), **then**:
    - (a) **zero** linhas com `shadow_class = 'TARGET_CONFIRMED'` carregando `parafiscal_institutional_hard_out`;
    - (b) as **4 raízes** Sistema S hoje em `TARGET_CONFIRMED` (`03575238` SESC-RS, `03709814` SENAC, `03776284` SENAI, `16589137` SEBRAE/MG) passam a `TARGET_OUT_OF_SCOPE` — denominador **4 → 0** nesta camada;
    - (c) `TARGET_CONFIRMED` total cai **68** raízes (8.667 → ~8.599) e o reason code aparece em **~568** linhas (~532 transições de classe). Valores medidos pelo @architect em D.4, não estimados. Desvio material desses números é sinal de que a taxonomia mudou e exige nova medição de blast radius antes da publicação.

    ```sql
    -- (a) Deve retornar ZERO linhas apos a reclassificacao:
    SELECT cnpj_raiz, shadow_class
      FROM confenge_target_fit_shadow
     WHERE reason_codes::text LIKE '%parafiscal_institutional_hard_out%'
       AND shadow_class = 'TARGET_CONFIRMED';

    -- (c) Contagem esperada de linhas carregando o reason code (referencia medida: 568):
    SELECT count(*) FROM confenge_target_fit_shadow
     WHERE reason_codes::text LIKE '%parafiscal_institutional_hard_out%';
    ```

    - **Três defeitos do texto anterior, corrigidos com evidência (não repetir):** (i) o denominador **"14" era da camada errada** — refere-se a `outreach_accounts` do warmbly; nesta camada são **4** raízes (medição independente do @qa e do @architect, convergentes); (ii) o SQL anterior apontava para `confenge_company_target_fit_current` (**vazia**) e selecionava `razao_social`, **coluna inexistente** nessa tabela; (iii) a ressalva SHADOW da story estava **invertida** — a shadow **é** a tabela que governa o feed (`continuous_from_target_fit.py:111`), logo o reconcile em modo SHADOW opera na tabela certa. Predicado `reason_codes::text LIKE` verificado em produção antes de entrar aqui (jsonb; 5.614 hits para um código existente, 0 para o novo).
    - **Registro histórico (permanece verdadeiro):** `reclassify_shadow_probable_without_evidence` continua **não** satisfazendo este AC — `reclassify_insufficient.py:125` filtra por `(TARGET_PROBABLE_RESEARCH,)`. O mecanismo correto é o `reconcile`.
18. **Given** as mudanças de regra, **when** publicadas, **then** `RULE_VERSION` (`contract_relevance.py`) e `TARGET_FIT_VERSION` (`target_fit.py`) estão incrementados e os fingerprints em `confenge_sector/store.py` e `confenge_target_fit/compute.py` estão recomputados.
19. **Given** `tests/commercial_leads/test_anti_overfitting.py`, **when** executado após a mudança, **then** continua passando — nenhum CNPJ ou nome de empresa específico hardcoded na lógica de produção, apenas em fixtures de teste.
20. **Given** a política de code-freeze de campanha, **when** o código é publicado, **then** segue a sequência de 2 PRs abaixo, **na ordem exata**, e `python3 -m scripts.ops.verify_confenge_artifact_binding` retorna PASS após o segundo PR.

    **(a) REESCRITO pelo @po em 2026-09-01 (iteração 2) — terceira e definitiva versão. Escopo real do rebind do PR 2 = 5 caminhos congelados.**

    O texto anterior do @po ("6 arquivos") assumia que `store.py` e `compute.py` seriam **editados**. O @dev não os editou (desvio nº 2) e o @qa confirmou por sha256 contra `frozen-inputs-manifest.json`: `store.py` e `compute.py` estavam **MATCH byte-idêntico**. Na iteração 2 o desenho do @architect (C5) **passa a editar `compute.py`**, e acrescenta um módulo novo. Estado final, com o status de freeze de cada caminho:

    | Caminho | Freeze | Situação na iteração 2 |
    |---|---|---|
    | `scripts/commercial_leads/contract_relevance.py` | **CONGELADO** | DRIFT — rebind |
    | `scripts/commercial_leads/pipeline.py` | **CONGELADO** | DRIFT — rebind |
    | `scripts/confenge_universe/target_fit.py` | **CONGELADO** | DRIFT (gate C3) — rebind |
    | `scripts/confenge_target_fit/compute.py` | **CONGELADO** | passa a DRIFT (C5, `classifier_sha` hasheia `parafiscal.py`) — rebind |
    | `scripts/confenge_universe/parafiscal.py` | **CONGELADO — arquivo NOVO** | **entrada NOVA no manifesto**, não um rebind de entrada existente |
    | `scripts/confenge_sector/store.py` | **CONGELADO** | **MATCH — não editar, OUT do rebind** (D.2) |
    | `scripts/confenge_universe/identity.py` | livre | editado, fora do freeze |
    | `scripts/confenge_universe/eligibility.py` | livre | editado, fora do freeze |

    **Correção material ao desenho do @architect (verificada pelo @po, não inferida):** D.2/C1 afirma que `parafiscal.py` é "arquivo NOVO, portanto **não congelado**". **Isso é falso.** `discover_frozen_input_paths` (`scripts/ops/confenge_frozen_inputs.py:278-318`) faz **fechamento transitivo de imports locais** a partir dos seeds — sua própria docstring declara "expands transitive local imports under `scripts/`". Reproduzi o cenário em cópia descartável da árvore `scripts/` (com `parafiscal.py` criado e importado por `target_fit.py` e `compute.py`, ambos congelados) e a discovery **retornou `scripts/confenge_universe/parafiscal.py` no conjunto congelado**. Consequência operacional: o PR 2 não é "rebind de 4"; é **rebind de 4 + inserção de 1 entrada nova** no `frozen-inputs-manifest.json`. **@devops: um rebind escopado para 4 caminhos deixa os gates vermelhos.** Isto não altera o desenho (congelar não impede editar — impede editar *sem rebind*), apenas o escopo do PR 2.

    **(b) O script de verificação existe e está localizado — não é tarefa do @dev descobrir.** Caminho: `scripts/ops/verify_confenge_artifact_binding.py`. Assinatura de CLI: `--result` (default `result.json` sob o diretório de artefatos da campanha), `--queue-summary` (default `queue-summary.json`), `--head`, `--out`. Ele lê as cinco chaves `*_git_sha` de `result.json`/`queue-summary.json`.

    **(c) O PR 2 precisa regenerar DUAS coisas, não uma.** Regenerar **as marcas de freeze** E o build `confenge_final_status`. As cinco chaves `*_git_sha` que `verify_confenge_artifact_binding` lê são escritas **somente** pelo `confenge_final_status`. Regenerar apenas as marcas de freeze deixa o AC 20 inatingível.

    **(d) Proibido squash-merge em ambos os PRs.** Squash orfana o SHA de freeze — causa recorrente de main vermelha neste repositório. Usar merge commit.

    **(e) Main fica vermelha entre o merge do PR 1 e o merge do PR 2.** Isso é esperado e não é incidente novo. O PR 2 deve ser aberto **imediatamente** após o merge do PR 1. Precedente: commit `57d5efbb` (#457 após #456).

**Alcance real da defesa (ACs 21-25) — ratificados e formalizados pelo @po em 2026-09-01, iteração 2 do QA loop.**

Origem: rascunho do @architect em D.7, com **AC 24 reescrito pelo @po** e **AC 25 acrescentado pelo @po**. Estes ACs existem porque os ACs 1-16/18-19 são verificáveis em laboratório mas **não alcançavam o caminho de produção** — falha comprovada pelo @qa (REQ-001).

21. **O gate alcança o caminho real.** **Given** as razões sociais e os contratos reais das 4 raízes Sistema S hoje em `TARGET_CONFIRMED` (`03575238`, `03709814`, `03776284`, `16589137`), **when** `classify_target_fit` é executada com a projeção de `loader.load_company_input`, **then** as 4 retornam `target_fit_class == "TARGET_OUT_OF_SCOPE"` com `"parafiscal_institutional_hard_out"` em `target_fit_reason_codes`, **independentemente de `relevant_execution_contract_count`**. Teste obrigatório com fixture derivada de contratos reais — objetos podem ser abreviados; os **nomes de fornecedor não**. O `relevant_execution_contract_count` verdadeiro (6, 3, 3, 0) deve permanecer registrado e auditável no resultado, não zerado pelo gate.
22. **O gate é incondicional e determinístico quanto ao nome.** **Given** uma entidade cujo `razao_social` **não** casa nenhum marcador (ex.: `"SESCRS - ADM REG RS"`, `"SEBRAEMG"`, `"SERVICO DE APOIO AS MICRO E PEQUENAS EM"` truncado) mas cuja lista de `contracts` contém ao menos um `fornecedor_nome` que casa, **when** avaliada, **then** o resultado é `TARGET_OUT_OF_SCOPE`. **E:** **given** uma entidade parafiscal com `relevant_execution_contract_count >= 3`, **then** o resultado continua `TARGET_OUT_OF_SCOPE` — o gate **não** tem cláusula `n_exec == 0`. A superfície de nome avaliada é `razao_social` + `nome_fantasia` + **todo `fornecedor_nome` distinto** presente em `contracts`; basta um casar.
23. **Fonte única e drift de classificador.** **Given** a taxonomia parafiscal vivendo em `scripts/confenge_universe/parafiscal.py`, **then** (a) `identity.py` a importa e os ACs 11-13 continuam verdes **sem duplicação de lista**; (b) `classifier_sha()` em `compute.py` inclui `parafiscal.py` no `inspect.getsource`; (c) existe teste que prova que **acrescentar um marcador altera `classifier_sha()`** — isto é, que o `reconcile` volta a enfileirar. `store.py::sector_classifier_sha256` permanece **inalterado** (declarado OUT em D.2).
24. **REESCRITO pelo @po — não-regressão do blast radius (o texto do @architect em D.7 era vacuoso; ver Ratificação nº 1).** **Given** a taxonomia final aplicada sobre a **superfície de nome completa do C4** (`razao_social` + `nome_fantasia` + todo `fornecedor_nome` distinto), **when** avaliada **através de `classify_target_fit`** (não apenas do matcher isolado nem apenas de `resolve_identity`), **then**:
    - (a) `"FUNDACAO ENGENHARIA E CONSTRUCOES LTDA"` e `"CONSTRUTORA ALFA ENGENHARIA LTDA"` **não** recebem `parafiscal_institutional_hard_out` e **não** resultam em `TARGET_OUT_OF_SCOPE` por esse motivo — fixtures nomeadas obrigatórias. Este é o único ponto em que a taxonomia poderia morder um alvo legítimo, e hoje só está testado na camada `resolve_identity` (AC 12), **não** na camada que governa o outbound;
    - (b) `"FUNDACAO DE ENSINO E ENGENHARIA DE SANTA CATARINA"` (FEESC) e `"FUNDACAO DE PESQUISA E ASSESSORAMENTO A INDUSTRIA"` (FUPAI) são declarados como **supressões esperadas**, com fixture nomeada, para que a baixa consciente fique explícita no código de teste e não implícita;
    - (c) o conjunto de raízes suprimidas sobre a população confirmada corresponde às **68** medidas em D.4 — desvio material exige nova medição de blast radius antes da publicação.
25. **ACRESCENTADO pelo @po — a publicação não pode ser recusada por completude.** **Given** que o gate remove **68** raízes de `TARGET_CONFIRMED`, **when** o build de publicação roda, **then** as 68 saídas são declaradas como revogações explícitas com `MEMBERSHIP_DROP_REASON`, satisfazendo `_assert_membership_deactivation_delta` (`publish.py` ~linha 237). **Isto não é um teto numérico e não é apenas "antecipar o delta"**: o assert exige `declared == expected` e levanta `ValueError` → `PUBLICATION_REFUSED` (`publish.py:892` e `:931`) se as revogações não viajarem declaradas. Motivo de virar AC e não prosa: é um modo de falha recém-medido que trava o @devops, e prosa em seção de arquitetura não é verificável por gate.

    **Verificação partida em duas, deliberadamente (@po):** `publish.py` **não tem caminho de dry-run/plan-only** — verificado por `grep` (`dry.run|dry_run|plan_only|--plan` → zero ocorrências; só `MEMBERSHIP_DROP_REASON` em `:40`/`:249` e `PUBLICATION_REFUSED` em `:892`/`:931`). Escrever "ou dry-run equivalente" seria repetir exatamente o defeito que tornou o AC 17 insatisfazível **duas vezes**: nomear um mecanismo de verificação sem checar que ele existe. Portanto:
    - **(a) parte do @dev, verificável em CI:** teste unitário provando que cada raiz que sai de `TARGET_CONFIRMED` é emitida como revogação explícita carregando `MEMBERSHIP_DROP_REASON` em `reason_codes` (o predicado que `publish.py:249` consome). Não exige produção nem banco.
    - **(b) parte do @devops, verificável apenas pós-deploy:** o build real de publicação completa **sem** `PUBLICATION_REFUSED` no alert ledger, com as **68** revogações declaradas. Não bloqueia o @dev; bloqueia o fechamento da story.

## Tasks / Subtasks

- [x] Task 1 — Corrigir precisão em `contract_relevance.py` (AC: 1-5, 14)
  - [x] Remover token nu `"fundacao"` de `STRONG_PHRASES`, `STRONG_TOKENS` e `POSITIVE_CONTEXT`.
  - [x] Adicionar fraseologia estrutural inequívoca (`FOUNDATION_ENGINEERING_PHRASES`, 20 frases) concatenada em `STRONG_PHRASES`.
  - [x] Implementar `neutralize_evidence()` para o padrão `Fundação <qualificador>` via `ENTITY_FUNDACAO_RE` (regex do @architect, portado literalmente).
  - [x] Implementar gate de "presença física em evento ≠ execução de obra" (`EVENT_PRESENCE_RE` com `\b` word-boundary + `EVENT_EXECUTION_ESCAPE`).
  - [x] Criar constante nomeada `SQL_PREFILTER_SEEDS` incluindo `fundacao` nu, desacoplada de `STRONG_PHRASES`/`STRONG_TOKENS`.
  - [x] **Adicional (não previsto pelo @sm, obrigatório):** a neutralização foi aplicada dentro da própria `classify_contract_relevance` (wrapper sobre `_classify_relevance_raw`), não só no `target_fit`. Sem isso os ~15 call sites diretos continuariam vendo `PASS` no objeto SEBRAE.
- [x] Task 2 — Corrigir precisão e recall em `target_fit.py` (AC: 1-10, 14)
  - [x] Remover `"fundacao de"` e `"fundacoes de"` de `_EXECUTION_MARKERS`; acrescentar `FOUNDATION_ENGINEERING_PHRASES`.
  - [x] Aplicar `neutralize_evidence` em `_object_is_execution` **antes** de qualquer avaliação.
  - [x] Gate de evento aplicado pelo mesmo mecanismo (importado de `contract_relevance`, sem duplicação).
  - [x] Confirmado empiricamente: com o gate aplicado antes do corpo, o fallback `rel.strong_hits and not supply_adjacency` não retém mais o hit via `"construcao civil"` (teste `test_sistema_s_event_contract_does_not_confirm_target`).
- [x] Task 3 — Corrigir prefiltro SQL posicional em `pipeline.py` (AC: 14)
  - [x] `strongish.extend(STRONG_PHRASES[:12])` + `strongish.extend(STRONG_TOKENS[:10])` → `strongish.extend(SQL_PREFILTER_SEEDS)`.
  - [x] `ordered[:30]` continua contemplando `fundacao` nu — teste dedicado `test_bare_fundacao_survives_the_30_term_cut`.
- [x] Task 4 — Nova taxonomia de exclusão em `identity.py` (AC: 11-13)
  - [x] `DEFAULT_PARAFISCAL_INSTITUTIONAL_MARKERS` (54 marcadores: Sistema S, entidades religiosas, ensino fundacional).
  - [x] Código de exclusão próprio `PARAFISCAL_INSTITUTIONAL`, separado da lista de bancos (teste explícito de separação).
  - [x] Matching whole-token no nome normalizado, padrão herdado de `_ASSOCIATION_HINTS` / `_looks_like_non_construction_supplier`.
  - [x] `"fundacao"` removido de `DEFAULT_ORGAN_MARKERS`; substituído por `_looks_like_public_foundation()` com guarda de nome de construção (`_CONSTRUCTION_NAME_RE`), espelhando o guard `\bbanco\b`.
- [x] Task 5 — Fingerprints e versionamento (AC: 18)
  - [x] `RULE_VERSION` `contract-relevance-v2` → `contract-relevance-v3`; `TARGET_FIT_VERSION` `confenge-target-fit-v2` → `confenge-target-fit-v3`.
  - [x] Fingerprints em `store.py`/`compute.py` **verificados**: são computados em runtime via `inspect.getsource(...)` + `sha256` — não há valor hardcoded para editar. Ver desvio nº 2 no Dev Agent Record.
- [x] Task 6 — Testes de não-regressão e revalidação de call sites (AC: 6-20)
  - [x] `architect-exp3-baseline.py` portado para `tests/commercial_leads/test_real_corpus_no_regression.py` com caminhos relativos (`Path(__file__).parents[2]`), sem monkeypatch, sem mock.
  - [x] Fixtures nomeadas para os 6 casos-alvo e o caso SEBRAE real (AC 5), com o identificador do contrato na docstring.
  - [x] Teste do prefiltro SQL com a lista de cláusulas ILIKE pré-mudança capturada como literal (AC 14). `grep` confirmou que `pipeline.py:147-148` era o **único** consumidor posicional de `STRONG_PHRASES[`/`STRONG_TOKENS[`/`POSITIVE_CONTEXT[` no repositório — não há outro slicer a corrigir.
  - [x] Não-regressão do corpus verificada **por shard** (6 arquivos: 82/38, 82/38, 18/7, 18/7, 11/5, 11/5), não só pelo total — uma contagem global poderia mascarar um flip `True→False` compensado por um `False→True`.
  - [x] Call sites revalidados (ver tabela no Dev Agent Record).
  - [x] Gates de holdout rodados via corpus versionado: P=1.0, R=1.0 (n=44).
  - [x] `test_anti_overfitting.py` verde.
- [ ] Task 7 — Sequência de 2 PRs de re-freeze (AC: 20) — **NÃO EXECUTADA pelo @dev (autoridade do @devops)**. **Reconciliada pelo @po no fechamento: permanece aberta por desenho e é o único trabalho remanescente da story, integralmente na autoridade do @devops. Instruções operacionais na seção "Handoff para @devops".**
  - [ ] PR 1 (código) — working tree preparada, sem commit. @dev não tem autoridade de commit/push nesta execução.
  - [ ] PR 2 (artifact-only) — documentado, não executado. É etapa separada, posterior ao merge do PR 1.
  - [ ] `python3 -m scripts.ops.verify_confenge_artifact_binding` PASS após o PR 2.
  - [ ] Ordem preservada: rebind aponta para commit de código já em `main`.
- [x] Task 8 — Plano de deploy e reclassificação em produção (AC: 17)
  - [x] **Task 8.0 CONCLUÍDA — mecanismo identificado, ver seção "Task 8.0 — Achado" abaixo.**
  - [x] **Task 8.0 REVISADA na T9.7** — os 3 defeitos apontados pelo @po foram sanados (SQL por reason code na `confenge_target_fit_shadow`; ressalva SHADOW desinvertida com medição própria; passo 4 do universe builder acrescentado). Reconciliada pelo @po no fechamento.
  - [ ] Delta de população `TARGET_CONFIRMED` — só mensurável pós-deploy em produção. **DIFERIDO AO @devops** (AC 17), não pendência do @dev.

- [x] **Task 9 — Iteração 2 do QA loop (T9.1 a T9.8 do D.11)** — bloco acrescentado pelo @po no fechamento. As subtasks foram executadas e documentadas em **Dev Agent Record — Iteração 2**, mas nunca tiveram checkboxes; sem isto não haveria o que reconciliar. Todas verificadas pelo @qa na iteração 2.
  - [x] **T9.1** — `scripts/confenge_universe/parafiscal.py` criado como fonte única (taxonomia **movida**, não copiada, e não alterada).
  - [x] **T9.2** — `identity.py` importa de `parafiscal.py`; `_looks_like_parafiscal_institutional` virou wrapper fino. `test_identity_parafiscal.py` passou **sem edição** — prova do AC 23(a).
  - [x] **T9.3** — Gate C3 incondicional em `classify_target_fit` sobre a superfície C4, **sem cláusula `n_exec == 0`** (AC 21, 22). Verificado pelo @qa por leitura (linhas 311/314/333-362/365) e por execução.
  - [x] **T9.4/T9.5** — `classifier_sha()` em `compute.py` hasheia `parafiscal.py` (AC 23b); `compute.py` passa de MATCH a DRIFT no manifesto de freeze.
  - [x] **T9.5** — 24 testes novos (19 do gate, 3 do AC 25a, 2 do drift). @qa: 48 passed no conjunto dos ACs 21-25.
  - [x] **T9.6** — Validação empírica das 4 raízes reproduzida por medição própria do @dev e **re-reproduzida pelo @qa com o loader real** (`loader.load_company_input`): 4/4 saem para `TARGET_OUT_OF_SCOPE`, `n_exec` 6/3/3/0 preservado.
  - [x] **T9.7** — Seção "Task 8.0 — Achado" corrigida (ver Task 8 acima).
  - [x] **T9.8** — Dívidas `MNT-001`/`MNT-003`/`MNT-004` registradas com owner, prazo e ponto de entrada; `MNT-002` declarado como **4** `MEMORY.md` fora do File List de código, não revertidos. **Materializadas como drafts pelo @po no fechamento** — ver DoD.

## Task 8.0 — Achado (mecanismo de reclassificação de linhas já em `TARGET_CONFIRMED`)

> ### ✅ CORRIGIDA pelo @dev na T9.7 (iteração 2, 2026-09-01). Os 3 defeitos apontados pelo @po foram sanados neste texto.
>
> As três correções aplicadas, exatamente como o @po e o @architect (D.8) determinaram:
>
> 1. **SQL de medição trocado** — o SQL anterior apontava para `confenge_company_target_fit_current` (**tabela vazia** em produção, 0 linhas) e selecionava `razao_social` (**coluna inexistente** nela — verificado por mim em `information_schema.columns`: a tabela shadow tem `cnpj_raiz`, não `razao_social`). Substituído pelo SQL por reason code sobre `confenge_target_fit_shadow`.
> 2. **Ressalva SHADOW desinvertida** — o texto anterior afirmava que, em modo `SHADOW`, "a tabela que governa o outbound não muda". É o contrário, e eu confirmei por medição própria em produção (read-only): `TARGET_FIT_ASYNC_MODE=SHADOW` no unit file do `extra-confenge-target-fit-worker.service`, e as 4 raízes Sistema S estão em `confenge_target_fit_shadow` com `shadow_class = TARGET_CONFIRMED`, `target_fit_version = confenge-target-fit-v2`. **A shadow É a tabela que governa** — o reconcile em SHADOW opera na tabela certa.
> 3. **Passo 4 acrescentado** — rerun **manual** do universe builder (sem timer systemd), conforme D.8/REQ-002.
>
> O **mecanismo** (`reconcile` por drift de `classifier_sha`/`TARGET_FIT_VERSION`) permanece correto e ratificado, e agora é **materialmente suficiente**: na iteração 1 o reconcile reprocessava as linhas mas o classificador devolvia o mesmo resultado; com o gate C3 o resultado muda (medido — ver "Validação empírica das 4 raízes" no Dev Agent Record).

**Mecanismo:** `run_reconcile` em `scripts/confenge_target_fit/reconcile.py` (sweep nacional), drenado pelo worker.

**Evidência de código (não hipótese):**

- `reconcile.py:338` — `elif str(cur_row.get("classifier_sha") or "") != classifier_sha(): reason = "reconcile_classifier_drift"` → `enqueue_dirty(...)`.
- `reconcile.py:335` — gatilho **independente e concorrente**: `cur_row.get("target_fit_version") != TARGET_FIT_VERSION` → `reason = "reconcile_version_drift"`. Como esta story bumpa `TARGET_FIT_VERSION` (AC 18), os **dois** gatilhos disparam.
- `reconcile.py:136-172` (`_load_materialized_index`) — a query **não tem filtro por `target_fit_class`**. Lê `company_key, cnpj_raiz, target_fit_version, input_fingerprint, classifier_sha, operational_status, target_fit_class` de `confenge_company_target_fit_current` sem `WHERE`. Portanto linhas em `TARGET_CONFIRMED` **estão** no índice e **são** enfileiradas. É exatamente a diferença em relação a `reclassify_insufficient.py:125`, que filtra por `(TARGET_PROBABLE_RESEARCH,)`.
- `compute.py:87-98` — o short-circuit `skipped_fingerprint` exige `prev_classifier_sha == current_classifier_sha`. Com o sha mudado, o skip não ocorre e `classify_target_fit` roda de verdade sobre a linha confirmada.
- `compute.py:40-54` — `classifier_sha()` hasheia `inspect.getsource(target_fit_module) + inspect.getsource(relevance_module)`. Qualquer edição nesses dois módulos muda o sha. Provado por teste: `tests/confenge_universe/test_classifier_version_drift.py`.

**Comando exato (produção, pós-deploy — executar pelo @devops/operador, nesta ordem):**

```bash
cd /opt/extra-consultoria-releases/{novo_commit_hash}/

# 1) Sweep de diagnóstico limitado (proxy de dry-run — reconcile NÃO tem --dry-run):
#    enfileira no máximo 50 raízes e NÃO drena o worker; inspecionar stats antes de liberar.
.venv/bin/python -m scripts.confenge_target_fit reconcile --max-enqueue 50

# 2) Sweep nacional completo (sem cap) + drenagem controlada:
.venv/bin/python -m scripts.confenge_target_fit reconcile --drain-worker --max-worker-batches 20

# 3) O worker systemd drena o restante da fila naturalmente:
systemctl restart extra-confenge-target-fit-worker.service

# 4) NOVO (T9.7 / REQ-002 / D.8) — universe builder: batch nacional MANUAL.
#    NÃO existe unit nem timer systemd para ele (`systemctl list-unit-files 'extra-*'`
#    não mostra nenhum) — ele NÃO acontece sozinho. Sem este passo, a defesa em
#    profundidade (identity.py → eligibility.py → NOT_CONSTRUCTION) permanece
#    desativada indefinidamente e nada alerta, porque não há timer para falhar.
#    Sem modo incremental; `--max-rows` é apenas cap diagnóstico e invalida a
#    alegação de população completa.
.venv/bin/python -m scripts.confenge_universe build \
    --out /var/lib/extra-consultoria/confenge-universe/{data} \
    --result-json /var/lib/extra-consultoria/confenge-universe/{data}/result.json
```

**Medição do AC 17 (SQL em produção, antes e depois) — CORRIGIDO na T9.7.**

O SQL anterior estava quebrado duas vezes (tabela vazia + coluna inexistente). Forma correta, por reason code, na tabela que de fato governa:

```sql
-- (a) Deve retornar ZERO linhas apos a reclassificacao:
SELECT cnpj_raiz, shadow_class
  FROM confenge_target_fit_shadow
 WHERE reason_codes::text LIKE '%parafiscal_institutional_hard_out%'
   AND shadow_class = 'TARGET_CONFIRMED';

-- (b) Contagem esperada de linhas carregando o reason code (referencia medida: 568):
SELECT count(*) FROM confenge_target_fit_shadow
 WHERE reason_codes::text LIKE '%parafiscal_institutional_hard_out%';

-- (c) As 4 raizes Sistema S do denominador 4 -> 0:
SELECT cnpj_raiz, shadow_class, target_fit_version
  FROM confenge_target_fit_shadow
 WHERE cnpj_raiz IN ('03575238','03709814','03776284','16589137');
```

**Modo assíncrono — ressalva DESINVERTIDA na T9.7, com medição própria.** `_load_materialized_index(conn, *, mode)` lê `confenge_target_fit_shadow` quando o modo é `SHADOW` e `confenge_company_target_fit_current` caso contrário (`resolve_mode` em `worker.py:276`). Produção **está** em `SHADOW` — verificado por mim no unit file (`TARGET_FIT_ASYNC_MODE=SHADOW` em `systemctl show extra-confenge-target-fit-worker.service -p Environment`) — e a shadow é a tabela que o feed lê (`continuous_from_target_fit.py:111`). Portanto **o reconcile em SHADOW opera na tabela certa** e o AC 17 (4 → 0) se materializa nesse ciclo. Medição própria em produção (read-only, 2026-09-01) do estado ANTES, para servir de linha de base ao @devops:

| Raiz | Entidade | `shadow_class` | conf | `target_fit_version` |
|---|---|---|---|---|
| `03575238` | SESC-RS | `TARGET_CONFIRMED` | 0.8 | `confenge-target-fit-v2` |
| `03709814` | SENAC | `TARGET_CONFIRMED` | 0.8 | `confenge-target-fit-v2` |
| `03776284` | SENAI | `TARGET_CONFIRMED` | 0.8 | `confenge-target-fit-v2` |
| `16589137` | SEBRAE/MG | `TARGET_CONFIRMED` | 0.8 | `confenge-target-fit-v2` |

`confenge-target-fit-v2` em produção contra `confenge-target-fit-v3` no código confirma que **os dois gatilhos de drift do reconcile** (`reconcile.py:335` versão e `:338` `classifier_sha`) disparam.

**Asserção pós-deploy na segunda superfície (universe, defesa em profundidade):** no JSONL emitido pelo passo 4, as 4 raízes Sistema S devem ter `outreach_eligibility == "NOT_CONSTRUCTION"` e `in_universe == false`, com `reason` iniciando em `parafiscal_institutional_name:`. **Nota:** `outreach_eligibility` **não existe como coluna** em nenhuma tabela do banco (medido pelo @architect em `information_schema.columns`) — só existe no artefato JSONL/manifest. Não procurá-lo em SQL.

**Cobertura:** o reconcile itera raízes de `pncp_supplier_contracts`; materializações órfãs (raízes que sumiram dos contratos) são tratadas por `archive_orphan_materializations`, não pelo enfileiramento.

**Dry-run não executado localmente:** não há Postgres alcançável no ambiente de desenvolvimento (`LOCAL_DATALAKE_DSN` em `127.0.0.1:5433` → *Connection refused*). O predicado gatilho foi provado por teste unitário determinístico em vez de execução contra banco. **O AC 17 fica como "mecanismo identificado; medição em produção pendente de deploy" — não verificado.**

**Plano B NÃO acionado.** Existe mecanismo que reprocessa linhas confirmadas, logo não há escalonamento ao @po pela Decisão nº 1.

## Dev Notes

### Bug de recall na direção oposta (mesma raiz, corrigir junto)

`"fundacao"` está hoje em `DEFAULT_ORGAN_MARKERS` (linha 25 de `identity.py`), causando falso NEGATIVO verificado: `resolve_identity(cnpj, "FUNDACAO ENGENHARIA E CONSTRUCOES LTDA")` retorna hoje `valid=False, exclusion_code=PUBLIC_ORGAN` — uma empresa privada de engenharia sendo descartada como se fosse órgão público.

### Regressão silenciosa bloqueante — prefiltro SQL

`scripts/commercial_leads/pipeline.py:147-148` usa fatiamento POSICIONAL das tuplas `STRONG_PHRASES`/`STRONG_TOKENS`. `"fundacao"` é índice 10 em `STRONG_PHRASES` e índice 8 em `STRONG_TOKENS` — dentro dos cortes hoje. Se apenas removermos `"fundacao"` das tuplas e acrescentarmos as frases novas no fim, tudo desloca para além do corte (e além de `ordered[:30]` na linha 157) — o prefiltro SQL deixa de emitir `ILIKE '%fundacao%'` sobre a tabela de ~4M contratos, e QUALQUER contrato legítimo de fundação profunda deixa de ser lido pelo classificador. A docstring da função já declara a intenção correta ("Broad SQL prefilter (recall). Final relevance is hierarchical in Python."). Correção obrigatória: `SQL_PREFILTER_SEEDS` desacoplado.

### Mapa de regressão — call sites reais de `classify_contract_relevance`

`scripts/commercial_leads/sector_fit.py:326`, `scripts/commercial_leads/commercial_validity.py:81`, `scripts/commercial_leads/pipeline.py:234,316`, `scripts/confenge_universe/construction.py:67`, `scripts/confenge_universe/pipeline.py:446`, `scripts/confenge_universe/target_fit.py:191,260`, `scripts/ops/confenge_make_gates.py:976`, `scripts/ops/eval_contract_relevance_holdout.py`, `scripts/ops/eval_contract_relevance_real_holdout.py`.

Fingerprint de versão de regra (bump obrigatório): `scripts/confenge_sector/store.py:47`, `scripts/confenge_target_fit/compute.py:43`.

`resolve_identity` → único call site: `scripts/confenge_universe/aggregate.py:336`.

Cadeia a jusante que precisa ser reavaliada: `target_fit` → `scripts/confenge_contact_resolution/send_readiness.py` → `scripts/warmbly_bridge/mapping.py` → `scripts/confenge_activation/publish.py`. A requalificação REDUZ a população `TARGET_CONFIRMED`; `publish.py::_assert_membership_deactivation_delta` (linha ~237) e `MEMBERSHIP_DROP_REASON` vão disparar — comportamento correto e esperado, mas antecipar no plano de deploy para não ser confundido com incidente novo.

### Mecanismo de deploy real (produção)

- Serviço systemd: `extra-confenge-target-fit-worker.service`, working dir `/opt/extra-consultoria-releases/{commit_hash}/`, comando `.venv/bin/python -m scripts.confenge_target_fit worker --loop --idle-sleep 20`.
- Deploy manual: merge para `main` → novo diretório de release versionado por commit hash em `/opt/extra-consultoria-releases/` → `systemctl restart extra-confenge-target-fit-worker.service` (sem CI/CD automático).
- Comando de reclassificação pós-deploy: `python -m scripts.confenge_target_fit reclassify-insufficient --dry-run` primeiro, depois sem `--dry-run` (script: `scripts/confenge_target_fit/reclassify_insufficient.py`, função `reclassify_shadow_probable_without_evidence`).
- **RESOLVIDO pelo @po em 2026-09-01 — não reinvestigar.** A dúvida do @sm foi fechada por leitura direta do código, não por hipótese: `scripts/confenge_target_fit/reclassify_insufficient.py:125` restringe a query a `(TARGET_PROBABLE_RESEARCH,)`. Portanto `reclassify_shadow_probable_without_evidence` **comprovadamente NÃO cobre o caso SEBRAE**, que está em `TARGET_CONFIRMED`. O comando de reclassificação acima continua válido para o que ele faz, mas é insuficiente para o AC 17. O mecanismo correto deve ser determinado no **Task 8.0**. Ver Decisão do @po nº 1.

### Contenção imediata (fora do ciclo desta story)

Setar `do_not_contact=true` manualmente nas ~14 contas Sistema S na tabela `outreach_accounts` do warmbly em produção. Ação operacional direta em produção, fora do ciclo normal de story/PR — requer autorização explícita do usuário antes de qualquer escrita em produção, e execução por @devops/operador em paralelo ao ciclo de dev desta story.

### Relevant source tree

- `scripts/commercial_leads/contract_relevance.py` (CONGELADO — code-freeze de campanha)
- `scripts/confenge_universe/target_fit.py` (CONGELADO)
- `scripts/confenge_universe/identity.py` (NÃO congelado)
- `scripts/commercial_leads/pipeline.py` (CONGELADO)
- `scripts/confenge_sector/store.py`, `scripts/confenge_target_fit/compute.py` (fingerprints)
- `scripts/confenge_contact_resolution/discovery/official_domain.py:130-143` (`_ASSOCIATION_HINTS`, precedente de taxonomia)
- `scripts/confenge_activation/publish.py` (`_assert_membership_deactivation_delta` ~linha 237, `_validate_authoritative_manifest` ~linha 434)

Ignorar `.campaign/overnight/extra-cli/...` (untracked, fora do File List).

## Testing

- Focado: `pytest tests/confenge_universe/ tests/commercial_leads/ -v --cov=scripts -m "not slow"`
- Arquivos de teste convencionados a estender: `tests/confenge_universe/test_target_fit_adversarial.py`, `tests/confenge_universe/test_target_fit_probable_requires_evidence.py`, `tests/commercial_leads/test_identity.py`, `tests/commercial_leads/test_contract_relevance_adversarial.py`, `tests/confenge_universe/test_universe_builder.py`.
- Gates canônicos: `eval_contract_relevance_holdout`, `eval_contract_relevance_real_holdout`.
- Corpus real de 1076 objetos: teste formal de não-regressão portado do scratchpad da sessão do @architect.
- `tests/commercial_leads/test_anti_overfitting.py` deve permanecer verde.

**Acrescentado pelo @po na iteração 2:**

- ACs 21-25 exigem teste na camada `classify_target_fit` (não apenas no matcher isolado e não apenas em `resolve_identity`). Arquivo convencionado: estender `tests/confenge_universe/test_target_fit_adversarial.py` e/ou novo `tests/confenge_universe/test_target_fit_parafiscal_gate.py`.
- **Verificação atribuída explicitamente ao @qa no re-review (dívida `MNT-003` tem ação, não só registro):** confirmar por leitura de código que **ambos** os call sites reais de `continuous_from_target_fit` passam `target_confirmed_only=True` — `scripts/confenge_outreach_pipeline/pipeline.py:217` e `scripts/decision_unit_intelligence/batch_population.py:299`. Se qualquer um deles passar `False` (ou omitir o argumento), o ramo que seleciona por `sector_class` contorna o gate do AC 21 e as 4 raízes Sistema S (hoje `CONSTRUCTION_PROBABLE` conf 0.4 em `confenge_company_sector_current`) voltam ao feed — nesse caso `MNT-003` deixa de ser dívida e **vira bloqueante desta story**. O "não é alcançável hoje" precisa ser **verificado**, não assumido.
- T9.6: reexecutar os gates já verdes (holdout, corpus n=1076 objeto a objeto, `test_anti_overfitting`, suíte completa) e provar **zero delta** — o gate parafiscal é ortogonal à camada de texto e não deve mover nenhum desses números.

## Out of Scope (decisão do @architect — CONFIRMADA pelo @po)

- Gap de proveniência de 1.448 contas sem `contracts_json` + 27 "UNKNOWN" — story separada, sequencialmente dependente desta. **Confirmado OUT pelo @po.** Registrada no backlog como `story-outbound-provenance-gap-01` (Decisão nº 4).
- Exclusão de capacitação/treinamento do ICP — **confirmado OUT pelo @po** (Decisão nº 3).
- As 3 divergências pré-existentes do conjunto adversarial (curso de engenharia civil, bloco didático, estande de tiro) — **confirmado OUT pelo @po** (Decisão nº 6).

---

## Decisões do @po (Pax) — 2026-09-01

Esta seção fecha os 6 pontos que o @sm deixou em aberto. **Nenhum deles permanece como pergunta.** O @dev não deve reabrir nem reinvestigar os itens marcados como resolvidos por evidência de código.

### Decisão 1 — Mecanismo de reclassificação pós-deploy: RESOLVIDO POR EVIDÊNCIA, com sub-task bloqueante

**Pergunta do @sm:** `reclassify_shadow_probable_without_evidence` cobre `TARGET_CONFIRMED` ou só `TARGET_PROBABLE_RESEARCH`?

**Decisão:** Não é spike e não é risco residual. **É um defeito de AC que eu corrigi.** Verifiquei diretamente o código durante a validação: `scripts/confenge_target_fit/reclassify_insufficient.py:125` filtra a query por `(TARGET_PROBABLE_RESEARCH,)`. A resposta é **negativa e definitiva** — o mecanismo não toca linhas confirmadas, logo não pode produzir o resultado que o AC 17 exige (14 → 0).

**Por quê isso importa:** o AC 17, como o @sm escreveu, era **insatisfazível**. Nomeava um mecanismo que provadamente não faz o que o AC pede. Deixar isso como "risco residual documentado" teria empurrado uma falha garantida para a fase de QA, num incidente que já causou dano externo real. Um AC sem caminho de satisfação não é um risco — é um bug de story, e a fase @po existe para pegá-lo aqui.

**Ação:** criei a **Task 8.0**, bloqueante para o AC 17. Escopo estritamente delimitado (não é um spike aberto): o @dev avalia dois candidatos já nomeados pelo @architect — rerun de `scripts/confenge_universe/pipeline.py`, ou reprocessamento natural via `scripts/confenge_target_fit worker --loop` — escolhe um, roda o dry-run e escreve o comando de volta nesta story. O AC 17 foi reescrito para referenciar o mecanismo que o Task 8.0 nomear.

**Plano B (se nenhum mecanismo reprocessar linhas confirmadas):** a contenção via `do_not_contact=true` passa de mitigação temporária a controle primário e permanente para a coorte Sistema S existente, e o AC 17 é medido após o próximo ciclo completo de pipeline em vez de imediatamente pós-deploy. Neste cenário o @dev **deve** escalar ao @po antes de fechar a story — o Plano B altera o perfil de risco residual e não pode ser adotado silenciosamente.

### Decisão 2 — Contenção imediata em produção (`do_not_contact=true`): FORA DO ESCOPO desta story, e não autorizável por mim

**Decisão:** confirmo **OUT** do escopo desta story de código. É ação operacional de escrita em dados de produção, com ciclo de vida próprio, e não deve ser acoplada ao ciclo de PR de um fix de classificador — misturar as duas coisas atrasaria a contenção até o merge, que é exatamente o oposto do que o incidente exige.

**PRÉ-CONDIÇÃO EXPLÍCITA E INEGOCIÁVEL:**

> **Nenhuma escrita em `outreach_accounts` (nem em qualquer tabela de produção do warmbly) pode ser executada por qualquer agente sem autorização explícita e prévia do usuário humano.** Esta autorização **não** está concedida por esta story, e **não está no poder do @po concedê-la**. O @po pode recomendar; apenas o usuário humano pode autorizar. A execução, uma vez autorizada, cabe ao @devops/operador.

**Recomendação do @po ao usuário:** executar a contenção em paralelo ao ciclo de dev, não depois. A janela entre agora e a publicação do fix é a janela em que outro e-mail comercial pode sair para uma entidade Sistema S. Este é o ponto onde recomendo autorização com maior urgência — mas continua sendo decisão sua.

**Nota de rollback:** conforme já registrado no Rollback Plan, a contenção **não** deve ser revertida junto com um eventual rollback do código.

### Decisão 3 — Exclusão de capacitação/treinamento do ICP: FORA DO ESCOPO, decisão correta

**Decisão:** confirmo **OUT**, e a decisão do @architect está certa por dois motivos independentes.

Primeiro, empírico: o @architect testou a exclusão e comprovou que ela quebra recall legítimo. `"CONSTRUÇÃO DE CENTRO DE CAPACITAÇÃO PROFISSIONAL EM ALVENARIA ESTRUTURAL"` é obra real — excluir o token `capacitacao` derrubaria um alvo comercial válido. O AC 10 já fixa isso como teste positivo permanente, o que é a proteção certa.

Segundo, de natureza: isto é **política comercial de definição de ICP**, não defeito de precisão do classificador. O classificador está acertando; a questão seria se queremos ou não esse segmento. Misturar uma decisão de posicionamento comercial dentro de um hotfix de incidente contamina as duas — o fix fica mais arriscado e a decisão comercial fica sem a deliberação que merece.

**Quando revisitar:** após esta story estar publicada e a população estabilizada, como decisão de ICP separada, se e quando o usuário quiser reduzir o funil.

### Decisão 4 — Gap de proveniência (1.448 sem `contracts_json` + 27 UNKNOWN): FORA DO ESCOPO, com registro obrigatório de dívida

**Decisão:** confirmo **OUT**, e a dependência sequencial justifica de verdade — não é adiamento por conveniência. A story de proveniência precisa de um **denominador estável** para medir cobertura, e esta story vai mover o denominador ao derrubar a população `TARGET_CONFIRMED`. Executá-las em paralelo produziria medição sobre alvo móvel. Além disso os perfis de risco são distintos: aqui é **precisão** (falso positivo com dano externo já materializado); lá é **disponibilidade/degradação de evidência**. Empacotar os dois num único fix aumenta a superfície de regressão de uma mudança que já é HIGH-RISK.

**Registro de dívida técnica — obrigatório, não pode ser esquecido:**

| Campo | Valor |
|---|---|
| ID da story futura | `story-outbound-provenance-gap-01` |
| Título | Fechar gap de proveniência de contas `TARGET_CONFIRMED` sem `contracts_json` e resolver contas UNKNOWN |
| Escopo | 1.448 contas `TARGET_CONFIRMED` com `contracts_json` vazio + 27 contas com identidade UNKNOWN no warmbly |
| Pontos de entrada | `scripts/confenge_activation/publish.py::_validate_authoritative_manifest` (~linha 434); gancho `party_roles.buyer_supplier_conflict_fails_closed` (~linhas 468-470) |
| Bloqueada por | Esta story (`story-outbound-sector-classifier-false-positive-01`) — requer denominador pós-fix estável |
| Owner | @po (Pax) — criar via @sm assim que esta story for fechada |
| Prazo | Criar o draft no mesmo dia do fechamento desta story |
| Perfil de risco | Disponibilidade / integridade de evidência (≠ precisão) |

**Gate de fechamento:** o @po **não fecha** esta story enquanto `story-outbound-provenance-gap-01` não existir como draft em `docs/stories/`. Este item foi adicionado à Definition of Done para que o esquecimento seja estruturalmente impossível, não apenas improvável.

### Decisão 5 — Script de verify do freeze: RESOLVIDO AGORA, sem spike e sem tarefa para o @dev

**Pergunta do @sm:** qual é o nome exato do script de verificação do binding?

**Decisão:** resolvido durante esta validação. Não faz sentido carregar uma incerteza dessas para dentro da fase de implementação quando ela custa um grep. O script existe:

- **Caminho:** `scripts/ops/verify_confenge_artifact_binding.py`
- **Invocação:** `python3 -m scripts.ops.verify_confenge_artifact_binding`
- **CLI:** `--result` (default `result.json` no diretório de artefatos da campanha), `--queue-summary` (default `queue-summary.json`), `--head`, `--out`
- **O que ele lê:** as cinco chaves `*_git_sha` em `result.json` / `queue-summary.json`
- **Observação relevante:** o próprio script está na lista de caminhos congelados (`_SEED_PATHS` em `scripts/ops/confenge_frozen_inputs.py`) — os gates protegem a si mesmos. Não alterá-lo.

**Bônus da mesma verificação:** ao computar `discover_frozen_input_paths(Path('.'))` descobri que `scripts/confenge_sector/store.py` e `scripts/confenge_target_fit/compute.py` **também estão congelados**, o que o @sm não havia marcado. Isso corrigiu o "4 arquivos" do AC 20 para 6. Ver AC 20 (a).

### Decisão 6 — 3 divergências pré-existentes de recall: FORA DO ESCOPO, confirmado

**Decisão:** confirmo **OUT**. Os três casos (`curso de engenharia civil`, `bloco didático`, `estande de tiro`) já retornavam `False` **antes** da mudança, medido pelo @architect. Logo são gap de recall pré-existente, e não regressão introduzida por esta story.

**Por que o critério importa:** a fronteira entre "regressão desta mudança" e "defeito pré-existente" é o que torna o AC 16 verificável. Se arrastássemos correções pré-existentes para dentro deste diff, o teste de não-regressão do corpus de 1076 objetos perderia sua linha de base e o @qa não conseguiria distinguir dano novo de dano antigo — justamente na story em que essa distinção é mais cara.

**Nota:** o `architect-exp3-baseline.py` já contém `estande de tiro` como guarda de recall esperando `True`. Se a implementação do AC 1 (guarda de word-boundary para `"estande"`) acabar consertando esse caso como efeito colateral, isso é bem-vindo — mas **não** é requisito, e o @dev não deve forçá-lo.

## Definition of Done

> **Reconciliada pelo @po (Pax) em 2026-09-01, no fechamento.** Cada item tem verdito explícito: `[x]` satisfeito, `[x]` com nota quando satisfeito parcialmente com owner nomeado, `[ ]` quando **deliberadamente diferido ao @devops** com owner e condição. Nenhum item fica sem veredito.

- [x] **Todos os 25 ACs** verificados com evidência. **22 ACs + 25(a) verificados pelo @qa por medição própria** (1-16, 18, 19, 21-24, 25a). **AC 17, AC 20 e AC 25(b) diferidos ao @devops por desenho** — só são mensuráveis pós-deploy/pós-publicação; ver os 3 itens marcados `[ ]` abaixo.
- [x] Nenhum novo débito técnico introduzido sem registro explícito. 6 itens registrados (`MNT-001`, `MNT-002`, `MNT-003-REVISED`, `MNT-004`, `PROC-001`, `DOC-001`), todos com owner e destino — ver **Fechamento do @po**.
- [x] `RULE_VERSION`/`TARGET_FIT_VERSION` incrementados e fingerprints recomputados; `classifier_sha()` inclui `parafiscal.py` (AC 23b). Verificado literalmente pelo @qa (V-17, V-04): `contract-relevance-v3` e `confenge-target-fit-v3`.
- [ ] **DIFERIDO AO @devops (AC 20).** Sequência de 2 PRs de re-freeze: PR 1 de código (**7 arquivos de código**, sendo 1 novo, + testes + docs — lista exata na seção **Handoff para @devops**) + PR 2 artifact-only cobrindo **5 caminhos congelados desta story** (4 rebinds + 1 entrada nova `parafiscal.py`) **mais a herança de drift pré-existente da branch** (V-07), ambos com **merge commit, sem squash**.
- [ ] **DIFERIDO AO @devops (AC 20).** `python3 -m scripts.ops.verify_confenge_artifact_binding` retorna PASS após o PR 2, com **freeze marks E `confenge_final_status` regenerados**.
- [x] Gate sistêmico conjunto @architect + @qa aprovado (obrigatório por HIGH-RISK). @architect entregou a revisão de desenho (iteração 2); @qa emitiu **CONCERNS** com medição independente pelo loader real de produção.
- [x] **Task 8.0 concluída:** mecanismo nomeado (`reconcile` por drift de `classifier_sha` **e** de `TARGET_FIT_VERSION`), corrigido na T9.7 e escrito de volta nesta story. **Plano B não foi adotado** — ver Escalonamento REQ-008.
- [x] Plano de deploy documentado (seção "Task 8.0 — Achado", 4 passos, incluindo o rerun **manual** do universe builder).
- [ ] **DIFERIDO AO @devops (AC 17).** Delta de população `TARGET_CONFIRMED` medido pós-deploy e reportado como **esperado, não incidente**: alvo `4 → 0` nas raízes Sistema S, `-68` no total (8.667 → ~8.599), ~568 linhas com o reason code. Linha de base ANTES reconfirmada pelo @qa: as 4 em `TARGET_CONFIRMED`/`v2` e **zero** linhas com `parafiscal_institutional_hard_out` hoje.
- [x] Contenção imediata (`do_not_contact`) tratada conforme a Decisão do @po nº 2: **autorização humana explícita obtida** e execução realizada fora do ciclo de código. **Verificado pelo @po no fechamento por consulta read-only ao warmbly:** 14 linhas de `outreach_accounts` com `do_not_contact = true`, `blocked = true` e `block_reason = 'sector_classifier_false_positive_si…'`. Ver **Fechamento do @po — item 7**.
- [x] **Dívida técnica registrada:** `docs/stories/story-outbound-provenance-gap-01.md` **existe** como draft (verificado pelo @qa e reconfirmado pelo @po). O texto anterior deste item, que afirmava o contrário, era `DOC-001` e está corrigido aqui.
- [x] **REQ-003 — RESOLVIDO POR EVIDÊNCIA no fechamento, não estreitado.** A via de entrada da conta do incidente está **nomeada**: a conta é a raiz **`27364462`** (SEBRAE-ES, `27364462000144`), **não** `27080530` — este último é a raiz do **órgão comprador** dentro do identificador do contrato `27080530000143-2-000648/2024`. A conta está em `confenge_target_fit_shadow` como `TARGET_CONFIRMED`/`confenge-target-fit-v2`, tem **185 contratos como fornecedora** e `contracts_json` **não vazio** no warmbly — logo **não** pertence à coorte das 1.448. **Não há terceira via:** ela entrou pela superfície primária já mapeada (shadow → feed), que é exatamente a que o AC 21 passa a governar. Ver **Fechamento do @po — item 6**.
- [x] **Dívidas `MNT-001`, `MNT-003-REVISED`, `MNT-004` criadas como itens rastreáveis** em `docs/stories/`: `story-outbound-feed-selection-default-safety-01.md` (MNT-003-REVISED, prazo 2026-09-08) e `story-universe-identity-loader-hygiene-01.md` (MNT-001 + MNT-004, prazo 2026-09-15). `MNT-002` (**4** `MEMORY.md`, não 2) **declarado** e não revertido — decisão do @dev ratificada pelo @qa e pelo @po.
- [x] **`MNT-003` verificado pelo @qa e não apenas registrado.** Verificação executada e **o gatilho literal disparou** (3 call sites omitem o argumento). O @po **emendou o gatilho por escrito** em vez de aceitá-lo em silêncio — ver **Fechamento do @po — item 1**. Não vira bloqueante: os dois pontos de entrada que **constroem o feed** passam `True` ponta a ponta.
- [x] Teste de não-regressão do corpus portado a partir de `docs/stories/assets/story-outbound-sector-classifier-false-positive-01/architect-exp3-baseline.py` (caminho durável), **não** do scratchpad `/tmp` — `tests/commercial_leads/test_real_corpus_no_regression.py`, com `Path(__file__).parents[2]`.
- [x] @po fecha a story após veredito de QA. **Fechada em 2026-09-01** — ver **Fechamento do @po**.

## Rollback Plan

- **Atualizado pelo @po (iteração 2):** reverter os **7 arquivos de código** do File List ao estado anterior via `git revert` do PR de código — `contract_relevance.py`, `pipeline.py`, `target_fit.py`, `identity.py`, `eligibility.py` (iteração 1) + `compute.py` e o arquivo novo `parafiscal.py` (iteração 2). O revert precisa remover `parafiscal.py`, caso contrário `classifier_sha()` não retorna ao valor anterior e o `reconcile` continua enfileirando por drift.
- Reverter separadamente o PR de re-freeze artifact-only se o binding tiver sido atualizado.
- Restart do `extra-confenge-target-fit-worker.service` apontando para o release anterior em `/opt/extra-consultoria-releases/{commit_hash_anterior}/`.
- Nenhuma migration de dado é necessária — mudança é apenas de código/regra; população `TARGET_CONFIRMED` que caiu pode ser recomputada revertendo o código e reprocessando.
- Contenção (`do_not_contact=true`) NÃO deve ser revertida automaticamente junto com o rollback de código — é decisão operacional separada.

## Restrição de nova dívida

Nenhum threshold deve ser relaxado, nenhum teste deve ser marcado `skip`/`xfail`, nenhum mock deve substituir avaliação real do corpus, e nenhum CNPJ/nome de empresa específico deve ser hardcoded na lógica de produção (apenas em fixtures de teste — AC 19).

## Dev Agent Record

**Agente:** Dex (@dev) · **Data:** 2026-09-01 · **Modo:** YOLO · **Branch:** `feat/468-commercial-authority-split`

### Ordem de execução seguida

1. Capturas read-only pré-mudança (baseline do @architect, pytest, lista de cláusulas ILIKE, busca por fingerprints golden).
2. `identity.py` + `eligibility.py` (não congelados).
3. `contract_relevance.py` + `pipeline.py` (prefiltro SQL — crítico).
4. `target_fit.py`.
5. Testes, lint, suíte.

### Resultado empírico (pós-mudança, reproduzindo o baseline do @architect)

| Medida | Antes | Depois | Esperado |
|---|---|---|---|
| Conjunto adversarial (16 objetos) — mismatches | 8/16 | **3/16** | 3 (as 3 divergências pré-existentes, OUT of scope) |
| Corpus real n=1076 — `relevance PASS` | 222 | **222** | igual (zero flips) |
| Corpus real n=1076 — `is_execution` | 100 | **100** | igual (zero flips) |
| Gate rotulado n=44 | P=1.0 R=1.0 | **P=1.0 R=1.0** | P≥0.95 R≥0.90 |
| Objeto real SEBRAE (AC 5) | `exec=True`, `rel=PASS` | **`exec=False`, `rel=FAIL`** | False |

Os 3 mismatches remanescentes são exatamente `curso de engenharia civil`, `bloco didático` e `estande de tiro` — já `False` **antes** da mudança (Decisão do @po nº 6, OUT of scope). Não foram forçados.

### Revalidação dos call sites do mapa de regressão

| Call site | Situação |
|---|---|
| `commercial_leads/sector_fit.py:326` | coberto — `tests/commercial_leads/test_sector_fit.py`, `test_sector_fit_properties.py` verdes |
| `commercial_leads/commercial_validity.py:81` | coberto — `test_validity_gates.py` verde |
| `commercial_leads/pipeline.py:234,316` | inalterados (só o prefiltro SQL mudou); `test_sql_prefilter_seeds_regression.py` novo |
| `confenge_universe/construction.py:67` | coberto — `tests/confenge_universe/test_sector_dimension.py`, `test_universe_builder.py` verdes |
| `confenge_universe/pipeline.py:446` | coberto — `test_universe_builder.py` verde |
| `confenge_universe/target_fit.py:191,260` | alterado por design; `test_target_fit_adversarial.py` (+9 casos novos) e `test_target_fit_probable_requires_evidence.py` verdes |
| `ops/confenge_make_gates.py:976` | não alterado; `test_confenge_integrity_gates.py` sem delta vs. baseline |
| `ops/eval_contract_relevance_holdout.py` | gate reexecutado sobre o corpus versionado: P=1.0 R=1.0 |
| `ops/eval_contract_relevance_real_holdout.py` | corpus real reclassificado: 222/100, zero flips |
| `confenge_universe/aggregate.py:336` (`resolve_identity`) | novo código de exclusão propagado; `test_universe_builder.py` verde |
| `confenge_sector/store.py:47`, `confenge_target_fit/compute.py:43` | fingerprints derivam de `inspect.getsource` — mudam automaticamente; teste dedicado novo |

### Desvios do plano da story (todos declarados, nenhum silencioso)

1. **`PARAFISCAL_INSTITUTIONAL` definido em `identity.py`, não em `confenge_universe/__init__.py`.** Todos os demais códigos de exclusão vivem no `__init__.py`, mas ele **está congelado** (verificado via `discover_frozen_input_paths`) e **não** consta do File List da story. Colocar a constante lá elevaria o conjunto congelado de 5 para 6 arquivos e alteraria o escopo de rebind do AC 20. A Task 4 atribui o código à `identity.py`. `[AUTO-DECISION]` — mantida em `identity.py`; `OUTREACH_ELIGIBILITY_STATES` não foi tocado.
2. **`store.py` e `compute.py` NÃO foram modificados.** O AC 18 pede "fingerprints recomputados", mas a leitura do código mostra que `sector_classifier_sha256()` (`store.py:44-59`) e `classifier_sha()` (`compute.py:40-54`) computam o hash em runtime a partir de `inspect.getsource(...)` dos módulos classificadores. **Não existe fingerprint hardcoded para editar** — os hashes mudam sozinhos porque `contract_relevance.py` e `target_fit.py` mudaram. Busca por valor golden armazenado (`grep` em `scripts/`, `tests/`, `evals/`, `artifacts/`) não encontrou nenhum; nenhum artefato de campanha referencia `contract-relevance-v*`, `confenge-target-fit-v*` ou `classifier_sha`.

   **Evidência dura para o @devops (impacta o escopo do rebind do PR 2).** Comparando os sha256 gravados em `artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01/frozen-inputs-manifest.json` (162 entradas) com o conteúdo atual:

   | Caminho congelado | Freeze mark |
   |---|---|
   | `scripts/commercial_leads/contract_relevance.py` | **DRIFT** — precisa de rebind |
   | `scripts/commercial_leads/pipeline.py` | **DRIFT** — precisa de rebind |
   | `scripts/confenge_universe/target_fit.py` | **DRIFT** — precisa de rebind |
   | `scripts/confenge_sector/store.py` | **MATCH** — byte-idêntico, marca continua válida |
   | `scripts/confenge_target_fit/compute.py` | **MATCH** — byte-idêntico, marca continua válida |

   Logo o rebind do PR 2 cobre **3 caminhos congelados**, não os 6 assumidos pelo @po no AC 20(a) — a premissa daquele item era que os 6 seriam editados. `identity.py` e `eligibility.py` não são congelados e não entram no rebind. **@qa/@devops devem validar antes do PR 2.** O build `confenge_final_status` continua obrigatório (é a única fonte das cinco chaves `*_git_sha`).
3. **`scripts/confenge_universe/eligibility.py` adicionado ao File List (7º arquivo, NÃO congelado).** Sem mapeamento explícito, `decide_eligibility` faria o novo código cair no bucket genérico `INVALID_IDENTITY` (`eligibility.py:73-77`), reportando causa de exclusão falsa justamente no caminho de segurança de outbound que esta story corrige. Mapeado para o estado existente `NOT_CONSTRUCTION` com a causa real preservada em `reason`, evitando alterar o frozenset congelado. 11 linhas. Coberto por teste.
4. **Testes de identidade em arquivo novo `tests/confenge_universe/test_identity_parafiscal.py`**, não em `tests/commercial_leads/test_identity.py`. Motivo: aquele arquivo testa `scripts/commercial_leads/identity.py::resolve_supplier`, que é **outro módulo**; os ACs 11-13 são sobre `scripts/confenge_universe/identity.py::resolve_identity`.
5. **`--cov=scripts` não pôde ser usado.** `pytest-cov` não está instalado e `pip install` é bloqueado por PEP 668 (`externally-managed-environment`). A suíte foi rodada com `-o addopts=""`. Para auditabilidade: o `addopts` do `pytest.ini` contém **exclusivamente** três flags de cobertura — `--cov=scripts`, `--cov-report=term-missing`, `--cov-report=html:docs/td-001/coverage-reports/`. Nenhum marker, `-p`, `--ignore` ou flag de plugin foi suprimido junto. A suíte executada é, portanto, idêntica à mandatada exceto pela medição de cobertura.
6. **Task 7 não executada.** Commit, push e PR são autoridade exclusiva do @devops. Working tree deixada suja para revisão.

### AC 19 (anti-overfitting) — por que `sebrae`/`senai`/`sesi` em constante de produção não viola

`test_anti_overfitting.py` está verde, mas o ponto merece ser explicitado numa story HIGH-RISK. `DEFAULT_PARAFISCAL_INSTITUTIONAL_MARKERS` não contém CNPJ nem razão social de empresa — contém **marcadores de classe institucional**, casados como token inteiro no nome normalizado. É estruturalmente idêntico ao `DEFAULT_NON_CONSTRUCTION_SUPPLIER_MARKERS` que já existe **no mesmo arquivo** desde antes desta story (`banco do brasil`, `petrobras`, `correios`, `caixa economica`). O que o AC 19 proíbe — fixar uma entidade específica do incidente na lógica — não ocorre: o CNPJ do SEBRAE-ES aparece **apenas** em docstring/fixture de teste.

**Escopo deliberadamente contido:** fundações públicas genéricas (`fundacao municipal|estadual|nacional|cultural|hospitalar`) foram **removidas** da lista parafiscal durante a autocrítica. Elas continuam classificadas como `PUBLIC_ORGAN`, exatamente como antes da mudança. Reclassificá-las não era autorizado por nenhum AC e teria deslocado silenciosamente os contadores de `identity_exclusion_breakdown` em `aggregate.py:341-342`. Teste de guarda: `test_generic_public_foundations_stay_public_organ`.

### Bug latente encontrado, NÃO corrigido (fora de escopo, registrar como dívida)

`identity.py::_looks_like_non_construction_supplier` faz `re.search(r"\bbanco\b", n)` sobre `n = normalize_name(name)`, que retorna texto **MAIÚSCULO** — o padrão minúsculo sem `re.IGNORECASE` nunca casa. O guard genérico de "BANCO X" é código morto hoje (a lista literal `DEFAULT_NON_CONSTRUCTION_SUPPLIER_MARKERS` é que sustenta o comportamento). Não corrigido por estar fora dos ACs e por alterar recall de exclusão de bancos sem medição. As regexes novas desta story usam `re.IGNORECASE` justamente para não repetir o defeito.

### Nota operacional — efeito colateral da suíte

Rodar `tests/commercial_leads/test_confenge_integrity_gates.py` **reescreve** `artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01/code-freeze-gate.json` e `final-integrity-code-freeze-gate.json` na working tree (435 linhas de diff). São artefatos de campanha sob freeze e **não** fazem parte desta mudança. Foram revertidos com `git checkout --` antes da entrega. **@qa/@devops: verificar esse ponto após qualquer execução da suíte, para que não vazem para o PR de código.**

### Comandos de verificação

```bash
# suíte focada (invocação da story, sem --cov por indisponibilidade de pytest-cov)
python3 -m pytest tests/confenge_universe/ tests/commercial_leads/ -v -m "not slow" -o addopts=""

# baseline do @architect reproduzido
python3 docs/stories/assets/story-outbound-sector-classifier-false-positive-01/architect-exp3-baseline.py

# lint
python3 -m ruff check scripts/ tests/
```

---

## Dev Agent Record — Iteração 2 do QA loop (T9.1-T9.8)

**Agente:** Dex (@dev) · **Data:** 2026-09-01 · **Modo:** YOLO · **Branch:** `feat/468-commercial-authority-split`

O @qa está certo e o @architect está certo sobre por que eu errei. Minha implementação da iteração 1 estava correta no que fazia e **inalcançável** onde importava: `classify_target_fit` nunca chama `resolve_identity`. Esta iteração implementa o desenho (c) ratificado, e — a diferença central em relação à iteração 1 — **reproduz a validação empírica em produção em vez de confiar na medição de terceiros**.

### T9.1 — `scripts/confenge_universe/parafiscal.py` (novo)

Fonte única da taxonomia. Conteúdo **movido, não copiado**: a tupla `PARAFISCAL_INSTITUTIONAL_MARKERS` (38 marcadores efetivos) foi retirada de `identity.py` e a taxonomia **não foi alterada** — as fundações públicas genéricas continuam fora, como o @qa ratificou em "Colisão léxica 2.1". Exporta também `PARAFISCAL_INSTITUTIONAL` (código de exclusão) e `PARAFISCAL_HARD_OUT_REASON`. Depende apenas de `scripts.linkage.keys` — zero risco de ciclo e não puxa o `__init__` congelado.

### T9.2 — `identity.py` importa de `parafiscal.py`

`_looks_like_parafiscal_institutional` virou wrapper fino de uma linha. `DEFAULT_PARAFISCAL_INSTITUTIONAL_MARKERS` permanece como **alias** do nome novo (não é uma segunda lista — é a mesma tupla), para não quebrar importadores. **Zero alteração nos testes:** `tests/confenge_universe/test_identity_parafiscal.py` (20 testes, ACs 11-13) passou sem nenhuma edição, que é a prova de AC 23(a).

### T9.3 — Gate C3 + superfície C4 em `classify_target_fit`

Colocado **após** o bloco que calcula `n_exec`/`cnae_eng` e **antes** de todo hard-out e de todo path de confirmação. Superfície avaliada: `razao_social` + `nome_fantasia` + **todo `fornecedor_nome` distinto** dos `contracts` (`_parafiscal_name_surface`). Retorna `TARGET_OUT_OF_SCOPE` conf `0.95`, reason codes `parafiscal_institutional_hard_out` + `parafiscal_marker:{marcador}`. **Sem cláusula `n_exec == 0`.**

**Desvio declarado nº 7 (conflito entre o prompt de spawn e a story ratificada — segui a story).** O prompt do QA loop pedia early return "antes de qualquer lógica de n_exec/sector/CNAE". Isso é **incompatível com o AC 21 ratificado**, que exige o `relevant_execution_contract_count` verdadeiro (6/3/3/0) preservado e auditável no resultado suprimido: retornando antes do loop, `n_exec` seria 0 e a evidência que motivou a supressão seria apagada. Segui o D.2/C3 e o AC 21 (a story ratificada é a autoridade), colocando o gate depois do loop. Efeito prático idêntico quanto à classe; diferença apenas na auditabilidade — a favor do AC.

### T9.4 (D.11) / T9.5 (prompt) — `classifier_sha()` hasheia `parafiscal.py`

`compute.py` passa a incluir `inspect.getsource(parafiscal_module)`. **@devops: isto leva `compute.py` de MATCH a DRIFT**, exatamente como o @architect antecipou e o @po aceitou.

### T9.5 — Testes (24 novos)

- `tests/confenge_universe/test_target_fit_parafiscal_gate.py` (**novo**, 19 testes) — ACs 21, 22, 24. Inclui: as 4 raízes reais parametrizadas por CNPJ; preservação do `n_exec` real; as 4 variantes de produção que **não casam sozinhas** (`SESCRS`, `SESCRS - ADM REG RS`, `SEBRAEMG`, `SERVICO DE APOIO AS MICRO E PEQUENAS EM`) salvas pela superfície C4; ausência da cláusula `n_exec == 0` com `n_exec >= 3`; AC 24(a) `FUNDACAO ENGENHARIA E CONSTRUCOES LTDA` e `CONSTRUTORA ALFA` provadas **não suprimidas em `classify_target_fit`** (e confirmadas `TARGET_CONFIRMED`); AC 24(b) FEESC e FUPAI como **supressões declaradas** com fixture nomeada; guarda de whole-token (`SESCOOPERATIVA` e `SENAIA` não casam).
- `tests/confenge_universe/test_classifier_version_drift.py` (estendido, +2) — AC 23(b)(c). O teste de drift **não** usa monkeypatch da tupla em memória (que `inspect.getsource` nunca veria, e que seria uma prova falsa): escreve uma cópia do módulo com um marcador extra em arquivo temporário, carrega via `importlib` e prova que `classifier_sha()` real muda.
**Nota de auditabilidade do gate (AC 21).** O contador `relevant_execution_contract_count` é a **fonte auditável** do volume de execução suprimido e carrega o valor real. A lista `target_fit_evidence` é **amostra truncada em 10** (`evidence[:10]`, consistente com todos os demais caminhos de retorno do módulo) mais uma entrada `PARAFISCAL_NAME` indicando **qual variante de nome** disparou o gate — informação necessária porque frequentemente não é `razao_social`. Para raízes com mais de 10 contratos de execução, contador e evidência divergem por design; o contador prevalece. O teste do AC 21 assere o **número de entradas `CONTRACT_EXECUTION`**, não apenas que a evidência é não-vazia — asserir não-vazio seria vacuoso, já que o gate sempre anexa a própria entrada.

- `tests/confenge_activation/test_membership_drop_completeness.py` (**novo**, 3 testes) — **AC 25(a)**. Exercita `_assert_membership_deactivation_delta` diretamente: revogações declaradas fecham o delta; uma supressão omitida levanta `ValueError` (→ `PUBLICATION_REFUSED`); revogação sem `MEMBERSHIP_DROP_REASON` não conta. Sem banco, sem produção — roda em CI.

### T9.6 — Validação empírica das 4 raízes (reproduzida, não herdada)

Dump **read-only** de produção via `ssh ec-prod` (`conn.set_session(readonly=True)`, release `d0c706c5e46d8491ec510598173d5acf63eb71d8` do unit file), **1.552 contratos reais** das 4 raízes. Projeção idêntica à de `loader.load_company_input` (`razao_social` = primeiro `fornecedor_nome` não-nulo; `nome_fantasia`/`cnae_principal` = `None`; `construction_evidence` via `assess_construction`). **Nenhuma escrita em produção.**

| Raiz | Entidade | n contratos | `shadow_class` real em prod | DEPOIS (com o gate) | `n_exec` preservado | marcador |
|---|---|---|---|---|---|---|
| `03575238` | SESC-RS | 858 | `TARGET_CONFIRMED` | **`TARGET_OUT_OF_SCOPE`** | 6 | `sesc` |
| `03709814` | SENAC | 346 | `TARGET_CONFIRMED` | **`TARGET_OUT_OF_SCOPE`** | 3 | `senac` |
| `03776284` | SENAI | 140 | `TARGET_CONFIRMED` | **`TARGET_OUT_OF_SCOPE`** | 3 | `senai` |
| `16589137` | SEBRAE/MG | 208 | `TARGET_CONFIRMED` | **`TARGET_OUT_OF_SCOPE`** | 0 | `sebrae` |

**4 de 4 saem de `TARGET_CONFIRMED`.** As contagens de contratos (858/346/140/208 = 1.552) e os `n_exec` (6/3/3/0) **coincidem exatamente** com a medição independente do @architect em D.3 — duas simulações separadas convergindo sobre a mesma tabela viva.

**Verificação prévia da premissa do C4 (feita antes de declarar a T9.3 pronta):** confirmei marcador a marcador que cada uma das 4 raízes tem **ao menos uma** variante de `fornecedor_nome` que casa por token. `SESCRS`, `SESCRS - ADM REG RS`, `SEBRAEMG` e `SERVICO DE APOIO AS MICRO E PEQUENAS EM` **não casam sozinhas** — exatamente como o @architect mediu. **Não relaxei o matching para substring** para "resolver" isso: substring mudaria a taxonomia e invalidaria o blast radius medido de 68/568.

### AC 24(c) — blast radius de 68 raízes REPRODUZIDO (medição própria, read-only)

O AC 24 tem três alíneas; (a) e (b) são testes de CI (acima). A alínea **(c)** — "o conjunto de raízes suprimidas sobre a população confirmada corresponde às **68** medidas em D.4" — **não é verificável em CI** (exige a população viva de produção), então foi verificada por medição direta, não declarada por herança:

| Métrica | @architect (D.4) | Minha medição independente | Bate? |
|---|---|---|---|
| Raízes `TARGET_CONFIRMED` na shadow | 8.667 | **8.667** | ✅ exato |
| Pares distintos (raiz, `fornecedor_nome`) | 27.577 | 27.593 | ✅ (dados vivos, +16 em 27,5k) |
| **Raízes suprimidas — política C4 (qualquer variante)** | **68** | **68** | ✅ **exato** |
| Delas, com evidência de construção no nome | 1 (FEESC, declarada) | **1 — apenas `82895327 FUNDACAO DE ENSINO E ENGENHARIA DE SANTA CATARINA`** | ✅ |
| Construtoras suprimidas | 0 | **0** | ✅ |

Fronteiriças declaradas do AC 24(b) confirmadas presentes e suprimidas: `82895327` FEESC (`fundacao de ensino`) e `18025536` FUPAI (`fundacao de pesquisa`). As duas raízes que só o C4 captura, citadas pelo @architect, confirmadas: `43728245` SEBRAE-SP e `00360305` (CAIXA, via a variante `PAB SESC/MG`). Distribuição de marcadores: `fundacao de apoio` 44, `fundacao de amparo` 4, `fundacao educacional` 4, `servico nacional de aprendizagem` 3, `sebrae` 3, `sesc` 2, `senai` 2, `fundacao universitaria` 2, `servico de apoio as micro e pequenas empresas` 2, `mitra diocesana` 2, `servico social do comercio` 1, `senac` 1.

**Achado próprio que REFORÇA a decisão do C4 (não estava medido assim em D.4).** Comparei a política C4 com a política de nome único **usando como "nome único" exatamente o que o `loader` escolheria** (primeiro `fornecedor_nome` da query sem `ORDER BY`): ela suprime **58** raízes, não 68 — dez a menos (`00278912`, `00360305`, `00703697`, `01440615`, `31302808`, `43728245`, `52306613`, `74704008`, `83661074`, `89252431`). O @architect mediu 66 para a "variante dominante" (por frequência). **Os dois números diferem porque a variante dominante e o sorteio do loader não são a mesma coisa** — e é precisamente esse não-determinismo que o C4 elimina. A política C4 dá **68 de forma estável**; qualquer política de nome único dá um número que depende de qual variante é sorteada.

**Zero delta nos gates já verdes (o gate é ortogonal à camada de texto):**

| Gate | Iteração 1 | Iteração 2 | Delta |
|---|---|---|---|
| `eval_contract_relevance_holdout` | P=1.0 R=1.0 FPR=0.0 n=40 | **idêntico** | 0 |
| Conjunto adversarial (16 objetos) | 3/16 mismatches | **3/16** | 0 |
| Corpus real n=1076 — `relevance PASS` | 222 | **222** | 0 |
| Corpus real n=1076 — `is_execution` | 100 | **100** | 0 |
| `ALL FLIPS` (objeto a objeto) | vazio | **vazio** | 0 |
| `test_anti_overfitting.py` | verde | **verde** | 0 |

**Suíte completa** (`pytest tests/ -m "not slow"`), comparada contra `git worktree` destacado em `HEAD` (`6c7bb0ea`), duas execuções de cada lado:

| | HEAD (`6c7bb0ea`) | Working tree (iteração 2) |
|---|---|---|
| passed | 5.370 | **5.457** (+87 = 63 testes da iteração 1 + 24 da iteração 2) |
| failed | 134 | **134** |
| errors | 53 | **53** |
| **IDs que falham/erram** | 187 | **187 — conjuntos IDÊNTICOS (`diff` vazio)** |

**Zero regressões, zero correções acidentais.** Ruff: `All checks passed`.

**Achado metodológico honesto sobre a suíte (o @qa deve saber antes de comparar com o baseline dele).** Duas coisas mudaram desde a medição do @qa (5352→5415):

1. **A suíte completa hoje ABORTA na coleta** com `INTERNALERROR: SystemExit: 1`. Causa: `tests/test_official_status_reconfirmation.py` importa `scripts/collect_report_data.py`, que chama `sys.exit(1)` no import quando `httpx` está ausente (bloqueado por PEP 668). **Reproduzi isso idêntico no worktree em `HEAD`** — é ambiental e pré-existente, não introduzido por esta story. Invocação usada nos dois lados, sem suprimir nada além disso: `--ignore=tests/test_official_status_reconfirmation.py --continue-on-collection-errors`.
2. **A primeira execução de qualquer lado é contaminada por estado residual.** Na 1ª execução da working tree apareceram 3 IDs divergentes (`test_golden_path_coverage.py::test_dual_coverage_only_exits_nonzero_when_gates_fail` a mais; 2 erros de `test_live_consulting_pack.py` a menos). Rodados **isoladamente**, os 3 se comportam **exatamente igual** nas duas árvores. Na 2ª execução de cada lado os conjuntos ficaram idênticos. Registrado como flakiness de ordem/estado compartilhado, **não** como regressão — mas registrado, não escondido. Como o número de `passed`/`skipped` oscila entre execuções (5353/5370 no próprio HEAD), **o critério válido é o conjunto de IDs, não a contagem.**

### T9.7 — Seção "Task 8.0 — Achado" corrigida

Os 3 defeitos apontados pelo @po foram sanados no texto (SQL trocado para reason code sobre `confenge_target_fit_shadow`; ressalva SHADOW desinvertida com medição própria do unit file e da tabela; passo 4 do universe builder acrescentado com a advertência de que **não há timer systemd**). Acrescentei a linha de base ANTES medida por mim das 4 raízes, para o @devops comparar pós-deploy.

### T9.8 — Dívidas e MEMORY.md

| ID | Registro | Situação |
|---|---|---|
| `MNT-001` | Guard `\bbanco\b` morto em `identity.py` (`normalize_name` devolve MAIÚSCULAS; regex sem `re.IGNORECASE`) | Registrado abaixo com owner/prazo. **Não corrigido** — fora dos ACs e altera recall de exclusão de bancos sem medição. |
| `MNT-002` | `MEMORY.md` de agente fora do File List | **São 4, não 2** — ver declaração abaixo. |
| `MNT-003` | Ramo `target_confirmed_only=False` contorna o gate via `sector_class` | Registrado. Verificação atribuída ao @qa (não a mim) por decisão do @po. |
| `MNT-004` | `razao_social` não determinístico (`loader.py` sem `ORDER BY`) → `input_fingerprint` instável | Registrado. **Mitigado, não resolvido**, por esta story: o C4 torna o gate independente do sorteio, mas a instabilidade de fingerprint permanece. |

**MNT-002 — declaração explícita, não reversão.** O @qa contou 2 `MEMORY.md` modificados; **hoje são 4**: `.claude/agent-memory/aiox-architect/`, `aiox-dev/`, `aiox-po/`, `aiox-qa/`. Os de `aiox-architect`, `aiox-po` e `aiox-qa` **não são meus** — foram escritos por aqueles agentes durante as iterações 1 e 2 desta mesma story, e revertê-los destruiria trabalho de outro agente sem autoridade para tanto. **Decisão:** declaro os 4 aqui como modificações de memória de agente, **fora do File List de código**, e recomendo ao @devops que **não** os inclua no PR 1 (PR de código). `[AUTO-DECISION]` — declarar em vez de reverter; motivo: reverter memória alheia excede a autoridade do @dev.

**Registro formal das dívidas (este repositório não tem backlog central; o registro durável é a story):**

| ID | Owner | Prazo | Ponto de entrada |
|---|---|---|---|
| `MNT-001` | @po → draft via @sm | no fechamento desta story | `scripts/confenge_universe/identity.py` (`_looks_like_non_construction_supplier`, guard `\bbanco\b`) |
| `MNT-003` | @po → draft via @sm | no fechamento desta story | `scripts/confenge_outreach_pipeline/continuous_from_target_fit.py:122-131` |
| `MNT-004` | @po → draft via @sm | no fechamento desta story | `scripts/confenge_target_fit/loader.py:143-146,170`; `fingerprint.py:128` |

### AC 20(a) — discovery de freeze rodada por mim, não assumida

O @po pediu que eu não repetisse o padrão de "afirmar escopo de freeze sem rodar a discovery". Rodei `discover_frozen_input_paths(Path("."))` sobre a working tree real, **após** criar `parafiscal.py` e seus imports:

| Caminho | Discovery | vs. `frozen-inputs-manifest.json` |
|---|---|---|
| `scripts/commercial_leads/contract_relevance.py` | CONGELADO | **DRIFT** — rebind |
| `scripts/commercial_leads/pipeline.py` | CONGELADO | **DRIFT** — rebind |
| `scripts/confenge_universe/target_fit.py` | CONGELADO | **DRIFT** — rebind |
| `scripts/confenge_target_fit/compute.py` | CONGELADO | **DRIFT** — rebind (passou de MATCH por causa do C5) |
| `scripts/confenge_universe/parafiscal.py` | **CONGELADO** | **ENTRADA NOVA** (ausente do manifesto) |
| `scripts/confenge_sector/store.py` | CONGELADO | MATCH — **não editado, OUT** |
| `scripts/confenge_universe/identity.py` | livre | editado, fora do freeze |
| `scripts/confenge_universe/eligibility.py` | livre | não editado nesta iteração |

**O @po está certo e o D.2/C1 está errado: `parafiscal.py` É congelado** por fechamento transitivo de imports. Confirmado por execução, não por leitura. **PR 2 = 5 caminhos (4 rebinds + 1 entrada nova).**

**Achado incidental para o @devops — NÃO é desta story, mas não vou escondê-lo.** A mesma comparação discovery × manifesto revela drift **pré-existente** desta branch (`feat/468-commercial-authority-split`), alheio a esta story: `scripts/confenge_activation/publish.py`, `scripts/confenge_target_fit/store.py`, `scripts/decision_unit_intelligence/batch_projection.py`, `scripts/ops/confenge_feed_cycle.py`, `scripts/warmbly_bridge/__init__.py`, `scripts/warmbly_bridge/export.py`, mais a entrada nova `scripts/confenge_activation/commercial_authority.py` e 2 entradas do manifesto que a discovery já não retorna (`.github/workflows/ci.yml#CONFENGE`, `Makefile#CONFENGE`). Vem dos commits `8b47d3d0`/`c9cad134`/`6c7bb0ea`. **Não toquei em nenhum deles.** O escopo real do rebind do PR 2 pode ser maior que 5 por causa dessa herança — verificar antes de abrir o PR 2.

### O que NÃO fiz (limites de autoridade, declarados)

- **Task 7 (2 PRs de re-freeze)** — autoridade exclusiva do @devops. Working tree preparada, sem commit e sem push.
- **AC 17 pós-deploy, AC 20, AC 25(b)** — só mensuráveis após o deploy/publicação. A parte de CI do AC 25 (a) está feita e verde.
- **REQ-003 (via de entrada do SEBRAE-ES)** — é gate de fechamento do @po, não pré-requisito de implementação. Nada encontrado incidentalmente que o altere. **Registro relevante:** `docs/stories/story-outbound-provenance-gap-01.md` **agora existe** em `docs/stories/` (untracked) — o REQ-007 do @qa, que estava insatisfeito, aparenta ter sido atendido entre as iterações. Confirmação é do @po, não minha.
- **Contenção `do_not_contact=true`** — escrita em produção, exige autorização humana explícita. Não executada. Todos os meus acessos a produção foram `SELECT` com `set_session(readonly=True)`.

### Aviso ao @devops — working tree compartilhada com outro agente

Durante esta execução, **outro agente passou a editar, na mesma working tree**, `scripts/confenge_account_intelligence/{facts,message_spine,normalize}.py` e `scripts/confenge_contact_resolution/send_readiness.py` — a story `story-outreach-claim-policy-01` (cujo state file e draft apareceram como untracked no meio da minha execução). **Não são meus, estão fora do escopo desta story, e não os toquei.**

**Consequência que o @qa precisa saber para não me atribuir regressão alheia:** entre a minha medição da suíte completa e a verificação final, surgiram **2 falhas novas** em `tests/confenge_activation/test_strict_national_esr_and_service_ontology.py` (`test_message_spine_makes_copy_context_ready`, `test_pilot_review_has_full_identity_evidence_message_and_human_gate`). Os motivos reportados são `factual_claim_blocked` e `multiple_current_claims_fail_closed` — **política de claim**, do trabalho concorrente, sem qualquer relação com o gate parafiscal (que não toca `message_spine`, `send_readiness` nem `confenge_claim_policy`). Elas **não** aparecem na minha medição HEAD × working tree da suíte completa, feita **antes** dessas edições, cujos conjuntos de IDs eram idênticos.

Consequência prática: `ruff check scripts/ tests/` **não está limpo globalmente** neste instante — reporta `I001` em `confenge_account_intelligence/facts.py` e `F841` em `message_spine.py`, ambos naqueles arquivos alheios. **Restrito ao escopo desta story, o lint está limpo:**

```bash
python3 -m ruff check scripts/confenge_universe/ scripts/confenge_target_fit/ \
    scripts/commercial_leads/ tests/confenge_universe/ tests/commercial_leads/ \
    tests/confenge_activation/     # → All checks passed!
```

**@devops: o PR 1 deve conter apenas os 7 arquivos de código do File List final.** Não arrastar `confenge_account_intelligence/*`, os 4 `MEMORY.md`, nem os artefatos de campanha.

**Efeito colateral da suíte, confirmado de novo (DOC-003 do @qa):** rodar `tests/commercial_leads/test_confenge_integrity_gates.py` reescreve `artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01/{code-freeze-gate,final-integrity-code-freeze-gate,contract-relevance-holdout}.json`; a suíte completa também suja 4 arquivos em `docs/ops/campaigns/` e cria `artifacts/pseo/`, `output/process_documents/`, `output/coverage/`. **Restaurei todos** com `git checkout --` / `rm -rf` após a última medição — a working tree entregue está limpa nesses caminhos. Verificar `git status` antes do PR 1.

**Falha pré-existente esperada na suíte focada:** `test_rebound_freeze_drives_shipped_verifiers_on_campaign_tree` (`BLOCKED_CODE_EXECUTION_SHA_MISMATCH`). Idêntica à iteração 1 e ao baseline pré-mudança — é exatamente o estado que o PR 2 de re-freeze existe para resolver, não uma regressão.

### Comandos de verificação (iteração 2)

```bash
# gate parafiscal + ACs 21-24
python3 -m pytest tests/confenge_universe/test_target_fit_parafiscal_gate.py -v -o addopts=""
# AC 23 (drift de classifier_sha) e AC 25(a)
python3 -m pytest tests/confenge_universe/test_classifier_version_drift.py \
                 tests/confenge_activation/test_membership_drop_completeness.py -v -o addopts=""
# suíte focada
python3 -m pytest tests/confenge_universe/ tests/commercial_leads/ -q -m "not slow" -o addopts=""
# suíte completa (ver achado metodológico acima sobre as duas flags)
python3 -m pytest tests/ -q -m "not slow" -o addopts="" \
    --ignore=tests/test_official_status_reconfirmation.py --continue-on-collection-errors
# zero delta no baseline do @architect
python3 docs/stories/assets/story-outbound-sector-classifier-false-positive-01/architect-exp3-baseline.py
python3 -m scripts.ops.eval_contract_relevance_holdout
# lint
python3 -m ruff check scripts/ tests/
```

## File List (FINAL — iteração 2, autoritativa)

**Código — 7 arquivos (5 congelados + 2 livres), sendo 1 novo:**

| Arquivo | Freeze | Iteração | Mudança |
|---|---|---|---|
| `scripts/confenge_universe/parafiscal.py` | **CONGELADO — ENTRADA NOVA no manifesto** | **2 (novo)** | Fonte única: `PARAFISCAL_INSTITUTIONAL_MARKERS`, `match_parafiscal_institutional`, `match_parafiscal_in_names`, `PARAFISCAL_INSTITUTIONAL`, `PARAFISCAL_HARD_OUT_REASON`. |
| `scripts/confenge_universe/target_fit.py` | **CONGELADO — DRIFT (rebind)** | 1 + **2** | It. 1: `TARGET_FIT_VERSION` v2→v3, neutralização. **It. 2: gate C3 incondicional + `_parafiscal_name_surface` (C4).** |
| `scripts/confenge_target_fit/compute.py` | **CONGELADO — passa a DRIFT (rebind)** | **2** | `classifier_sha()` hasheia `parafiscal.py` (AC 23b). |
| `scripts/commercial_leads/contract_relevance.py` | **CONGELADO — DRIFT (rebind)** | 1 | Inalterado na it. 2. |
| `scripts/commercial_leads/pipeline.py` | **CONGELADO — DRIFT (rebind)** | 1 | Inalterado na it. 2. |
| `scripts/confenge_universe/identity.py` | livre | 1 + **2** | **It. 2: importa `parafiscal.py`; lista local removida; `_looks_like_parafiscal_institutional` virou wrapper fino.** |
| `scripts/confenge_universe/eligibility.py` | livre | 1 | Inalterado na it. 2. |

**NÃO alterado (declarado OUT em D.2, confirmado MATCH pela discovery):** `scripts/confenge_sector/store.py`.

**Testes — 3 estendidos, 5 novos:**

| Arquivo | Situação | Cobre |
|---|---|---|
| `tests/confenge_universe/test_target_fit_parafiscal_gate.py` | **NOVO (it. 2)** — 19 testes | ACs 21, 22, 24 |
| `tests/confenge_activation/test_membership_drop_completeness.py` | **NOVO (it. 2)** — 3 testes | AC 25(a) |
| `tests/confenge_universe/test_classifier_version_drift.py` | novo it. 1, **estendido it. 2** (+2) | AC 18, AC 23(b)(c), predicado do Task 8.0 |
| `tests/confenge_universe/test_identity_parafiscal.py` | novo it. 1 — **inalterado na it. 2 (é a prova do AC 23a)** | ACs 11-13 |
| `tests/commercial_leads/test_sql_prefilter_seeds_regression.py` | novo it. 1 | AC 14 |
| `tests/commercial_leads/test_real_corpus_no_regression.py` | novo it. 1 | ACs 15-16 |
| `tests/confenge_universe/test_target_fit_adversarial.py` | estendido it. 1 | ACs 1-10 |
| `tests/commercial_leads/test_contract_relevance_adversarial.py` | estendido it. 1 | ACs 1-5 nos ~15 call sites |

**Documentação e assets:**

- `docs/stories/story-outbound-sector-classifier-false-positive-01.md`
- `docs/stories/assets/story-outbound-sector-classifier-false-positive-01/architect-exp3-baseline.py`

**FORA do File List de código — declarados, não revertidos (MNT-002):** `.claude/agent-memory/aiox-architect/MEMORY.md`, `aiox-dev/MEMORY.md`, `aiox-po/MEMORY.md`, `aiox-qa/MEMORY.md`. **@devops: não incluir no PR 1.**

---

## File List (iteração 1 — registro histórico)

**Código alterado — 5 arquivos (4 congelados + 1 livre), NÃO os 6 previstos:**

- `scripts/commercial_leads/contract_relevance.py` — **CONGELADO** — `RULE_VERSION` v2→v3; `fundacao` nu removido das 3 camadas; `FOUNDATION_ENGINEERING_PHRASES`; `SQL_PREFILTER_SEEDS`; `neutralize_evidence()`; `classify_contract_relevance` virou wrapper sobre `_classify_relevance_raw`.
- `scripts/confenge_universe/target_fit.py` — **CONGELADO** — `TARGET_FIT_VERSION` v2→v3; `_EXECUTION_MARKERS` sem `fundacao de`/`fundacoes de`; neutralização em `_object_is_execution`.
- `scripts/commercial_leads/pipeline.py` — **CONGELADO** — prefiltro SQL posicional → `SQL_PREFILTER_SEEDS`.
- `scripts/confenge_universe/identity.py` — livre — `PARAFISCAL_INSTITUTIONAL`; `DEFAULT_PARAFISCAL_INSTITUTIONAL_MARKERS`; `_looks_like_parafiscal_institutional`; `_looks_like_public_foundation`; `fundacao` removido de `DEFAULT_ORGAN_MARKERS`.
- `scripts/confenge_universe/eligibility.py` — livre — **adicionado ao escopo** (desvio nº 3) — mapeamento explícito do novo código de exclusão.

**NÃO alterados (desvio nº 2, justificado acima):** `scripts/confenge_sector/store.py`, `scripts/confenge_target_fit/compute.py`.

**Testes (2 estendidos, 4 novos):**

- `tests/confenge_universe/test_target_fit_adversarial.py` — estendido: ACs 1-10, fixture do incidente SEBRAE, guarda de word-boundary, caso end-to-end Sistema S.
- `tests/commercial_leads/test_contract_relevance_adversarial.py` — estendido: neutralização no nível de `classify_contract_relevance` (proteção dos ~15 call sites).
- `tests/confenge_universe/test_identity_parafiscal.py` — **novo** — ACs 11-13 + guarda de fundação pública + mapeamento de eligibility.
- `tests/commercial_leads/test_sql_prefilter_seeds_regression.py` — **novo** — AC 14, com a lista de cláusulas ILIKE pré-mudança como literal.
- `tests/commercial_leads/test_real_corpus_no_regression.py` — **novo** — ACs 15-16, corpus real n=1076 portado do baseline durável, caminhos relativos.
- `tests/confenge_universe/test_classifier_version_drift.py` — **novo** — AC 18 + prova do predicado gatilho da Task 8.0.

**Documentação:**

- `docs/stories/story-outbound-sector-classifier-false-positive-01.md`

## File List (esperado — planejado pelo @sm/@po antes da implementação)

**OBSOLETO — substituído pelo bloco abaixo (@po, iteração 2).** Mantido apenas como registro histórico do planejamento pré-implementação; a premissa de que `store.py` e `compute.py` seriam editados não se confirmou na iteração 1.

- ~~6 arquivos: `contract_relevance.py`, `target_fit.py`, `pipeline.py`, `store.py`, `compute.py`, `identity.py`~~

**File List esperado — iteração 2 (autoritativo, @po 2026-09-01):**

| Arquivo | Freeze | Iteração |
|---|---|---|
| `scripts/commercial_leads/contract_relevance.py` | CONGELADO — rebind | 1 (feito) |
| `scripts/commercial_leads/pipeline.py` | CONGELADO — rebind | 1 (feito) |
| `scripts/confenge_universe/target_fit.py` | CONGELADO — rebind | 1 (feito) + 2 (gate C3) |
| `scripts/confenge_universe/identity.py` | livre | 1 (feito) + 2 (importa `parafiscal`) |
| `scripts/confenge_universe/eligibility.py` | livre | 1 (feito) |
| `scripts/confenge_universe/parafiscal.py` | **CONGELADO — entrada NOVA no manifesto** | **2 (novo)** |
| `scripts/confenge_target_fit/compute.py` | CONGELADO — passa a rebind | **2 (C5)** |
| `scripts/confenge_sector/store.py` | CONGELADO — **NÃO editar, OUT** | — |

**Testes e artefatos:**
- `tests/confenge_universe/test_target_fit_adversarial.py`
- `tests/confenge_universe/test_target_fit_probable_requires_evidence.py`
- `tests/commercial_leads/test_identity.py`
- `tests/commercial_leads/test_contract_relevance_adversarial.py`
- `tests/confenge_universe/test_universe_builder.py`
- (novo) `tests/commercial_leads/test_sql_prefilter_seeds_regression.py` (ou nome equivalente — cobre AC 14)
- (novo) `tests/commercial_leads/test_real_corpus_no_regression.py` (ou nome equivalente — porta `architect-exp3-baseline.py`, cobre AC 16)
- (adicionado pelo @po) `docs/stories/assets/story-outbound-sector-classifier-false-positive-01/architect-exp3-baseline.py` — baseline do @architect persistido em caminho durável; fonte para o AC 16
- `docs/stories/story-outbound-sector-classifier-false-positive-01.md`

## Fechamento do @po (Pax) — 2026-09-01

**Story FECHADA.** Status permanece `Done` (transição feita pelo @qa — o @po não altera status). Veredito de QA aceito: **CONCERNS**, com as duas ressalvas tratadas abaixo. `closure-key: outbound-sector-classifier-false-positive-01:digest:9640f9e015bd679e316f4bb70ad9248c86c97bcc4719540bb0bc1f28e6dbe832`

**Não há epic formal** — esta é story avulsa. Não há índice de epic/backlog central a atualizar; o registro autoritativo de fechamento é o Change Log desta story e o state file `.aiox/state/stories/outbound-sector-classifier-false-positive-01.json`.

### Gate de procedência re-verificado antes de qualquer escrita

O @qa registrou a âncora de revisão porque a working tree é compartilhada com um agente concorrente ativo. **Reconferi os 15 sha256 antes de fechar: 15/15 MATCH, zero divergência.** O veredito CONCERNS cobre exatamente a árvore que existe agora. O `reviewed_revision` não é um commit (não há commit ainda), então a chave de fechamento usa o **digest determinístico do manifesto de 15 arquivos** — escolha declarada aqui para ser auditável, não implícita.

### 1. `MNT-003-REVISED` — o gatilho disparou; emendo por escrito em vez de aceitar em silêncio

**Decisão: DÍVIDA, não bloqueante. Mas o gatilho que eu mesmo escrevi disparou, e isso não pode passar sem registro.**

Na Ratificação nº 5 eu escrevi: *"se qualquer um dos call sites passar `False` (ou omitir o argumento), `MNT-003` deixa de ser dívida e vira bloqueante desta story"*. O @qa encontrou **3 call sites que omitem o argumento**. Literalmente, o gatilho disparou.

**Por que não elevo a bloqueante — e por que a razão não é conveniência:** o gatilho existia para impedir **uma coisa**: que as raízes Sistema S voltassem ao feed e um e-mail comercial saísse de novo. Sua premissa de fato ("existem 2 call sites, ambos `True`") estava **errada**; seu propósito continua satisfeito por um discriminante melhor, que o @qa mediu e que eu não conhecia quando escrevi o gatilho:

| Natureza do comando | `target_confirmed_only` | Constrói feed? | Dispara e-mail? |
|---|---|---|---|
| `confenge_contact_cycle` → `batch_population.py:299` | **`True`** | sim | sim |
| `confenge_feed_cycle` → `pipeline.py:217` | **`True`** | sim | sim |
| `enrich-continuous` → `continuous_from_target_fit.py:338` | `False` (default) | **não** | **não** |
| `national-confirmed` → `national_confirmed.py:93` | `False` (default) | **não** | **não** |
| `load_confirmed_jobs_from_dsn:286` | `False` (default) | **código morto** | não |

**O gatilho fica formalmente SUPERSEDIDO por este discriminante**, que é mais estreito e mais verificável: *nenhum comando que constrói o feed de outbound seleciona a coorte ampla*. Se um dia isso deixar de ser verdade, `MNT-003` volta a ser bloqueante — e agora existe uma frase falsificável para checar, em vez de uma contagem de call sites que já se provou errada uma vez.

**O fato que sustenta a decisão é medição do @qa em produção, não verificação minha.** Registro isso explicitamente: eu não reproduzi os 67/68 nem o estado dos timers. Aceito como evidência de terceiro qualificado e independente.

**Não fica como linha de tabela.** Um bypass latente que traria de volta 67 das 68 raízes suprimidas não é item de tabela — virou draft rastreável: **`docs/stories/story-outbound-feed-selection-default-safety-01.md`**, owner @po, prazo de refinamento **2026-09-08**, carregando a recomendação do @qa (inverter o default para `True` ou torná-lo keyword-only sem default; corrigir junto `load_confirmed_jobs_from_dsn`).

### 2. `PROC-001` — instrução de separação é obrigatória, e a metade que faltava

**Decisão: aceito como dívida de processo, com ação em duas pontas.**

**Ponta @devops (registrada na seção Handoff):** o PR 1 **não pode** ser aberto com `git add -A`. Adicionar **por caminho explícito** a lista da seção Handoff. Conferir os 15 sha256 antes.

**Ponta que o @qa deixou aberta — verificada por mim no fechamento e, no ponto mais sensível, JÁ RESOLVIDA:** as 35 linhas em `scripts/confenge_activation/publish.py` (`CLAIM_SAFETY_ROLLBACK_ANCHOR_KEY`, `claim_safety_hash`, âncora de rollback) **não estão mais soltas na working tree — foram commitadas em `d8375d16`** (`feat(confenge): claim-safety audit for present-tense contract claims [claim-safety-audit-01]`). `git status -- scripts/confenge_activation/publish.py` retorna **vazio**. O arquivo congelado passou a ter **dono nomeável** (`story-claim-safety-audit-01`) e o drift é agora **committed**.

**Distinção de responsabilidade que o critério binário do @qa não separa — e que nesta story importa:** `git log main..HEAD` classifica `publish.py` junto com os 6 caminhos de V-07, mas as duas coisas não são iguais. Os 6 são **herança pré-story** (commits `8b47d3d0`/`c9cad134`/`6c7bb0ea`, anteriores a este ciclo, sem dono ativo). `publish.py` é **commit de story concorrente feito durante este ciclo** (`d8375d16`), com dono identificável agora. A consequência operacional é a mesma — entra no escopo do rebind do PR 2 nos dois casos —, mas a **responsabilidade** não: o rebind de `publish.py` tem a quem ser atribuído, e dizer "herança" esconderia isso.

**Onde permanece dívida, e de quem:** `story-outreach-claim-policy-01` declara `publish.py` como escopo **OUT** e atribui as 35 linhas a `story-current-claim-jit-authority-01`; nenhuma das duas o traz para dentro do seu File List. Como `publish.py` é **congelado**, alguém precisa responder pelo seu **rebind** no manifesto. **Ação de fechamento (cross-reference, não bloqueio desta story):** o rebind de `publish.py` deve ser assumido explicitamente pela story que o commitou (`story-claim-safety-audit-01`) ou absorvido no PR 2 desta como herança de branch — o @devops decide qual, mas **não pode ficar sem dono**. Já está listado na herança de V-07 do PR 2.

**Estado da árvore no momento do fechamento (mudou desde o review do @qa e isso é relevante):** `HEAD` avançou de `6c7bb0ea` para **`e29ee198`**; os arquivos de código alheios que o @qa encontrou soltos (`publish.py`, `confenge_account_intelligence/{facts,message_spine,normalize}.py`, `send_readiness.py`, `scripts/confenge/__main__.py`) **foram todos commitados** e já não aparecem como modificados. **Reconferi os 15 sha256 desta story após esse avanço: 15/15 MATCH.** O veredito continua cobrindo exatamente os arquivos desta story. A instrução de escopar o PR 1 por caminho explícito **permanece obrigatória** — os artefatos de campanha voltaram a sujar e a árvore segue compartilhada.

O AC 25(a) foi provado **independente** dessas 35 linhas (os 3 testes passam contra o `publish.py` do HEAD `6c7bb0ea`), então nada aqui contamina o veredito desta story.

### 3. `DOC-001` — DoD corrigida

A DoD afirmava que `docs/stories/story-outbound-provenance-gap-01.md` não existia. **Existe** — verificado por mim (li o cabeçalho: status `Draft`, story-mãe declarada, 1.448 contas, ponto de entrada `publish.py::_validate_authoritative_manifest`). Item da DoD reescrito e marcado. O texto errado veio de eu ter reconfirmado um estado que mudou entre as iterações; o gate funcionou exatamente como deveria — foi ele que fez alguém checar.

### 4. `MNT-001`, `MNT-002`, `MNT-004` — nenhuma dívida fica solta

| ID | Sev | Destino | Owner | Prazo |
|---|---|---|---|---|
| `MNT-003-REVISED` | medium | draft `story-outbound-feed-selection-default-safety-01.md` | @po → refinar com @sm | 2026-09-08 |
| `PROC-001` | medium | seção **Handoff para @devops** + cross-reference em `story-outreach-claim-policy-01` | @devops (PR 1) / @po (cross-ref) | no PR 1 |
| `MNT-001` | low | draft `story-universe-identity-loader-hygiene-01.md` | @po → refinar com @sm | 2026-09-15 |
| `MNT-004` | low | draft `story-universe-identity-loader-hygiene-01.md` | @po → refinar com @sm | 2026-09-15 |
| `MNT-002` | low | **declarado, não revertido** — 4 `MEMORY.md` de agente, fora do File List de código, excluídos do PR 1 | @dev (declarou), @po (ratifica) | encerrado aqui |
| `DOC-001` | low | corrigido na DoD nesta mesma edição | @po | encerrado aqui |

### 5. Story-filha `story-outbound-provenance-gap-01` — confirmada como follow-up obrigatório

**Confirmado.** `docs/stories/story-outbound-provenance-gap-01.md` existe, status `Draft`, declara esta story como story-mãe e registra corretamente que a investigação da via de entrada do SEBRAE-ES é REQ-003 desta story, **não** dela. Continua **sequencialmente dependente** desta: precisa do denominador estável pós-fix (esta story derruba 68 raízes de `TARGET_CONFIRMED`).

**Correção de escopo que o fechamento produz (item 6):** REQ-003 **não** é absorvido pela story-filha — a conta do incidente tem contratos e não pertence à coorte das 1.448. A story-filha permanece com o escopo original (proveniência/disponibilidade), sem herdar o incidente.

### 6. REQ-003 — RESOLVIDO POR EVIDÊNCIA. A via de entrada está nomeada, e não há terceira via

Este era o gate de fechamento mais duro que eu mesmo pus. **Não estreitei o Estado-alvo: respondi a pergunta.** Consulta read-only em produção (`outreach_accounts` no warmbly e `confenge_target_fit_shadow` no datalake; nenhuma escrita).

**A pergunta discriminante estava mal formada — e o erro era meu, da mesma família dos outros dois desta story: confusão de camada, agora de *entidade*.** A raiz `27080530` é a do **órgão comprador** dentro do identificador do contrato `27080530000143-2-000648/2024`. Ela nunca foi a conta do lead. Por isso "0 contratos e ausente da shadow" — não é uma conta, é um comprador.

**A conta que recebeu o e-mail, identificada pelo próprio registro de envio:**

| Evidência | Valor |
|---|---|
| `outreach_drafts.recipient_email` | `contato.sebrae@es.sebrae.com.br` (2 registros: 2026-08-25 e **2026-09-01 10:38 UTC**) |
| `account_id` | `71276ebc-f31a-4a19-b8df-0773f825ecbf` |
| `outreach_accounts.cnpj14` / `cnpj_root` | `27364462000144` / **`27364462`** |
| `razao_social` / `uf` | `sebrae` / `ES` |
| `target_fit_class` / `target_fit_version` | `TARGET_CONFIRMED` / `confenge-target-fit-v2` |
| `contracts_json` vazio? | **NÃO** |
| `do_not_contact` / `blocked` | **`true` / `true`** (contenção aplicada) |
| `confenge_target_fit_shadow` | presente: `27364462` → `TARGET_CONFIRMED` / `confenge-target-fit-v2` |
| Contratos como **fornecedora** (`pncp_supplier_contracts`) | **185** |

**Resposta à pergunta discriminante: NÃO** — a raiz `27364462` **não** pertence à coorte das 1.448 contas com `contracts_json` vazio; ela tem contratos e tem lastro.

**Mas a Ratificação nº 4 previa que "NÃO" implicaria terceira via não mapeada. Não implica, e a evidência é direta:** a conta está **na shadow**, em `TARGET_CONFIRMED`, com 185 contratos como fornecedora. Ou seja, entrou pela **superfície primária já mapeada** (`reconcile` → `compute` → `classify_target_fit` → `confenge_target_fit_shadow` → feed) — exatamente a que o **AC 21** passa a governar. **Verificação direta do alcance da correção:** extraí as **13** variantes distintas de `fornecedor_nome` da raiz `27364462` em produção e as submeti a `match_parafiscal_in_names` do `parafiscal.py` desta story → **casa o marcador `sebrae`**. Portanto a conta do incidente **é suprimida pelo gate desta story**.

**Consequência para o Estado-alvo:** a linha *"NÃO declarado como atingido: a cadeia do incidente concreto (SEBRAE-ES, raiz `27080530`)"* está **superada**. A cadeia está explicada, a raiz correta é `27364462`, e ela é coberta pela defesa primária. A redação forte da Story ("nunca mais dispare e-mail comercial real") passa a ser sustentada pela evidência **para a classe do erro e para o caso concreto** — condicionada, como todo o resto, ao deploy (AC 17) e ao gate ainda aberto do `MNT-003-REVISED`, que fica registrado e não escondido.

**Ressalva de honestidade metodológica (a Ratificação nº 4 exigia):** a contenção manual já foi aplicada nessa conta, então esta leitura mede um sistema **já alterado**. O que a contenção alterou foram `do_not_contact`/`blocked`; ela **não** cria contratos nem insere linhas na shadow — logo `target_fit_class = TARGET_CONFIRMED`, os 185 contratos e a presença na shadow descrevem o estado de origem, não o efeito da contenção.

### 7. Contenção manual em produção — o que ela resolveu e o que ela NÃO resolve

**Verificada por mim, read-only, no fechamento.** `outreach_accounts` do warmbly (**camada do warmbly — não é a camada `confenge_target_fit_shadow`, onde o denominador é 4, nem a camada target-fit, onde o blast radius é 68**; a confusão dessas camadas custou duas iterações a esta story e não se repete aqui):

- **14 linhas** Sistema S com `do_not_contact = true` **e** `blocked = true`, `block_reason = 'sector_classifier_false_positive_si…'`, todas em `target_fit_class = TARGET_CONFIRMED` — inclui a conta do incidente (`27364462`) e as raízes `03575238`, `03709814`, `03774688`, `03776284`, `03777341`, `16589137`, `43728245`, `00360305`.
- Autorizada explicitamente pelo usuário humano e executada **fora do ciclo de código** desta story, conforme a Decisão do @po nº 2. Nenhum agente escreveu em produção por conta própria. Satisfaz a DoD no ramo "autorização obtida".

**Papel correto de cada coisa, sem ambiguidade:**

- A **contenção é band-aid**: elimina a exposição imediata daquelas 14 contas, e só delas. Não corrige o classificador, não impede que **novas** entidades parafiscais sejam confirmadas, e não alcança as outras ~54 das 68 raízes fora do Sistema S.
- **O deploy desta correção é o que resolve a causa raiz**: o gate parafiscal incondicional em `classify_target_fit` (AC 21/22) impede a confirmação na origem, para a classe inteira.
- Conforme **Escalonamento REQ-008** e o **Rollback Plan**: a contenção **permanece mitigação temporária**, **não** vira controle primário permanente, e **não** deve ser revertida junto com um eventual rollback do código.

---

## Handoff para @devops (Gage)

> Emitido pelo @po no fechamento. Story `Done`, `po_closed: true`, **`publication_authorized: false`** — ver pré-condições abaixo. Branch: `feat/468-commercial-authority-split`.

### Antes de qualquer coisa: reconferir a âncora

A working tree é compartilhada com um agente concorrente ativo. Conferir os **15 sha256** de `devops_pr1_separation.reviewed_sha256` (gate file) / `qa_reviewed_sha256` (state file) **imediatamente antes** de montar o PR 1. Eu os reconferi no fechamento (15/15 MATCH), mas o intervalo até você abrir o PR não está coberto. **Divergência = reabrir com o @qa antes de publicar.** Conferir também `git status` — a suíte suja `artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01/*.json` e 4 arquivos em `docs/ops/campaigns/`.

### PR 1 — código. **PROIBIDO `git add -A`.** Adicionar por caminho explícito

**Código (7):**

```
scripts/confenge_universe/parafiscal.py          # NOVO
scripts/confenge_universe/target_fit.py
scripts/confenge_universe/identity.py
scripts/confenge_universe/eligibility.py
scripts/confenge_target_fit/compute.py
scripts/commercial_leads/contract_relevance.py
scripts/commercial_leads/pipeline.py
```

**Testes (8):**

```
tests/confenge_universe/test_target_fit_parafiscal_gate.py        # NOVO
tests/confenge_universe/test_identity_parafiscal.py               # NOVO
tests/confenge_universe/test_classifier_version_drift.py          # NOVO
tests/confenge_activation/test_membership_drop_completeness.py    # NOVO
tests/commercial_leads/test_sql_prefilter_seeds_regression.py     # NOVO
tests/commercial_leads/test_real_corpus_no_regression.py          # NOVO
tests/confenge_universe/test_target_fit_adversarial.py
tests/commercial_leads/test_contract_relevance_adversarial.py
```

**Precedência sobre o gate file (leia antes de montar o PR 1).** Esta lista **estende** `devops_pr1_separation.incluir_no_pr1_codigo` do gate file com **3 caminhos acrescentados no fechamento do @po**: os 2 drafts de dívida e o state file. Os **15 sha256 cobrem apenas os arquivos de código e teste**, não estes 3 nem os documentos. Seguir só o gate file faria os drafts de `MNT-003-REVISED`, `MNT-001` e `MNT-004` **não entrarem no repositório** — e os prazos que acabei de criar ficariam sem artefato.

**Verificação do encadeamento do AC 25(a) (feita no fechamento, registrada para não ser refeita às cegas):** `HEAD` avançou duas vezes durante o ciclo (`6c7bb0ea` → `d8375d16` → `e29ee198`). `test_membership_drop_completeness.py` exercita `_assert_membership_deactivation_delta`, que vive em `publish.py` — **fora** da âncora de 15 sha256 e fora do File List. Conferi os dois commits: `d8375d16` altera `publish.py` (as 35 linhas, agora com dono) e `e29ee198` **não o toca** (mexe em `confenge_claim_policy/`, `confenge_account_intelligence/*`, `send_readiness.py` e testes). **Se `HEAD` avançar de novo tocando `publish.py` antes do PR 1, reexecutar `tests/confenge_activation/test_membership_drop_completeness.py` contra o HEAD corrente** — divergência reabre com o @qa.

**Documentação e artefatos de rastreabilidade:**

```
docs/stories/story-outbound-sector-classifier-false-positive-01.md
docs/stories/assets/story-outbound-sector-classifier-false-positive-01/
docs/qa/gates/outbound-sector-classifier-false-positive-01.yml
docs/stories/story-outbound-feed-selection-default-safety-01.md    # NOVO (MNT-003-REVISED)
docs/stories/story-universe-identity-loader-hygiene-01.md          # NOVO (MNT-001 + MNT-004)
.aiox/state/stories/outbound-sector-classifier-false-positive-01.json
```

**NÃO incluir (arquivos de outras stories na mesma árvore):**

```
scripts/confenge_activation/publish.py                 # claim-safety — 35 linhas não commitadas, arquivo CONGELADO (PROC-001)
scripts/confenge_account_intelligence/{facts,message_spine,normalize}.py   # story-outreach-claim-policy-01
scripts/confenge_contact_resolution/send_readiness.py  # story-outreach-claim-policy-01
scripts/confenge/__main__.py                           # apareceu durante o review do @qa
scripts/confenge_claim_policy/ , scripts/confenge_claim_safety/ , scripts/confenge/claim_safety_audit/
tests/confenge_claim_policy/ , tests/confenge_claim_safety/
tests/confenge_contact_resolution/test_factual_claim_safe.py
.claude/agent-memory/*/MEMORY.md                       # 4 arquivos (MNT-002)
artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01/*.json , docs/ops/campaigns/**   # reescritos pela suíte
.campaign/ , artifacts/pseo/ , output/                 # lixo de execução
docs/stories/story-outbound-provenance-gap-01.md , story-outreach-claim-policy-01.md , story-current-claim-jit-authority-01.md   # de outras stories
```

### PR 2 — artifact-only, re-freeze. **Abrir imediatamente após o merge do PR 1**

**5 caminhos congelados desta story** (4 rebinds + 1 entrada nova):

```
scripts/commercial_leads/contract_relevance.py     # rebind
scripts/commercial_leads/pipeline.py               # rebind
scripts/confenge_universe/target_fit.py            # rebind
scripts/confenge_target_fit/compute.py             # rebind (passou de MATCH a DRIFT por causa do C5)
scripts/confenge_universe/parafiscal.py            # ENTRADA NOVA no frozen-inputs-manifest.json — não é rebind
```

`scripts/confenge_sector/store.py` continua **MATCH — não editar, OUT do rebind**.

**Herança pré-existente da branch (confirmada pelo @qa em V-07 por `git log main..HEAD`, NÃO introduzida por esta story):** `publish.py`, `confenge_target_fit/store.py`, `decision_unit_intelligence/batch_projection.py`, `ops/confenge_feed_cycle.py`, `warmbly_bridge/__init__.py`, `warmbly_bridge/export.py`, entrada nova `confenge_activation/commercial_authority.py`, mais 2 entradas do manifesto que a discovery já não retorna (`.github/workflows/ci.yml#CONFENGE`, `Makefile#CONFENGE`). **O escopo real do rebind é maior que 5.** Um rebind escopado só nos 5 desta story deixa os gates vermelhos.

**Regras do PR 2:** regenerar **as marcas de freeze E o build `confenge_final_status`** (as cinco chaves `*_git_sha` que `verify_confenge_artifact_binding` lê são escritas só por ele). `python3 -m scripts.ops.verify_confenge_artifact_binding` deve retornar **PASS** após o merge. **Merge commit em ambos os PRs — squash é proibido** (orfana o SHA de freeze; precedente `57d5efbb`/#457). Main fica vermelha entre os dois merges: **esperado, não é incidente novo**.

### Pré-condições de publicação

| # | Pré-condição | Estado |
|---|---|---|
| 1 | Story `Done` | ✅ (@qa) |
| 2 | `po_closed: true` | ✅ (este fechamento) |
| 3 | `qa_verdict` ∈ {PASS, CONCERNS, WAIVED} | ✅ **CONCERNS** |
| 4 | `gates.lint` PASS | ✅ **no escopo desta story** (`ruff` limpo em `scripts/confenge_universe/`, `scripts/confenge_target_fit/`, `scripts/commercial_leads/`, `tests/confenge_universe/`, `tests/commercial_leads/`, `tests/confenge_activation/`). Fora do escopo há achados dos arquivos alheios — **não são desta story e não devem ser corrigidos no PR 1**. |
| 5 | `gates.tests` PASS | ✅ **zero regressão real**: HEAD 187 IDs × working tree 188, único delta passa isolado nos dois lados. A falha `test_rebound_freeze_drives_shipped_verifiers_on_campaign_tree` (`BLOCKED_CODE_EXECUTION_SHA_MISMATCH`) é **pré-existente e é exatamente o que o PR 2 resolve**. |
| 6 | Working tree limpa **no escopo desta story** | ✅ 15/15 sha256 MATCH no fechamento — **reconferir antes do PR 1** |
| 7 | `reviewed_commit === HEAD` | ⛔ **NÃO satisfeito por desenho — não há commit.** O PR 1 é o que produz o commit. |
| 8 | `publication_authorized: true` | ⛔ **false.** Só pode virar `true` depois que o PR 1 existir como commit e os gates forem reconferidos contra ele. Marcar `true` agora seria selo não conquistado. |

### Pós-deploy — o que fecha os 3 ACs diferidos

- **AC 17:** rodar a sequência de 4 passos da seção "Task 8.0 — Achado" (inclui o rerun **manual** do universe builder — **não há timer systemd**) e medir os 3 SQLs: (a) zero `TARGET_CONFIRMED` com `parafiscal_institutional_hard_out`, (b) as 4 raízes em `TARGET_OUT_OF_SCOPE`, (c) ~568 linhas com o reason code / −68 confirmados. Desvio material dos números exige nova medição de blast radius **antes** de publicar.
- **AC 20:** `verify_confenge_artifact_binding` PASS após o PR 2.
- **AC 25(b):** build real de publicação completa **sem** `PUBLICATION_REFUSED` no alert ledger, com as 68 revogações declaradas. `publish.py` **não tem dry-run** — só é verificável no build real.

**Reportar as 3 medições de volta nesta story em até 24 h do deploy.** Desvio material nos números do AC 17 (4→0, −68, ~568) **reabre com o @qa antes de publicar** — é sinal de que a taxonomia mudou e exige nova medição de blast radius. **Enquanto as medições não vierem, a story está fechada mas o efeito em produção não está comprovado.**

**Próxima story elegível:** `docs/stories/story-outbound-provenance-gap-01.md` — continua bloqueada pela **publicação** desta (precisa do denominador estável pós-fix), não pelo fechamento. Refinar com o @sm assim que o AC 17 for medido.

---

## Change Log

| Date | Version | Description | Author |
|---|---|---|---|
| 2026-09-01 | 0.8.0 | **Fechamento formal do @po — story FECHADA. Status preservado em `Done` (transição é do @qa; o @po não altera status).** `[closure-key: outbound-sector-classifier-false-positive-01:digest:9640f9e015bd679e316f4bb70ad9248c86c97bcc4719540bb0bc1f28e6dbe832]` — digest determinístico do manifesto de 15 sha256 do @qa, usado porque `reviewed_revision` não é um commit; escolha declarada, não implícita. **Âncora reconferida antes de qualquer escrita: 15/15 sha256 MATCH.** Sem epic formal (story avulsa) — o Change Log e o state file são os artefatos autoritativos de fechamento. **REQ-003 RESOLVIDO POR EVIDÊNCIA, não estreitado:** consulta read-only ao warmbly e ao datalake identificou que a conta do incidente é a raiz **`27364462`** (SEBRAE-ES, `27364462000144`, `account_id 71276ebc-…`, e-mail `contato.sebrae@es.sebrae.com.br` em 2026-09-01 10:38 UTC), e **não** `27080530` — esta última é a raiz do **órgão comprador** dentro do identificador do contrato, erro de entidade da mesma família das duas confusões de camada anteriores. A conta tem `contracts_json` **não vazio** e **185 contratos como fornecedora**, logo **NÃO** pertence à coorte das 1.448 → REQ-003 **não** é absorvido por `story-outbound-provenance-gap-01`. **Também não há terceira via:** a conta está em `confenge_target_fit_shadow` como `TARGET_CONFIRMED`/`v2`, isto é, entrou pela superfície primária já mapeada; e as **13** variantes de `fornecedor_nome` da raiz submetidas a `match_parafiscal_in_names` **casam o marcador `sebrae`** — a conta do incidente **é suprimida pelo gate desta story**. Linha do Estado-alvo que declarava a cadeia inexplicada: **superada**. **`MNT-003-REVISED`: gatilho da Ratificação nº 5 DISPAROU (3 call sites omitem o argumento) e foi EMENDADO POR ESCRITO, não aceito em silêncio** — a premissa de fato ("2 call sites") era falsa; o propósito segue satisfeito por discriminante melhor e falsificável (*nenhum comando que constrói o feed seleciona a coorte ampla*: `batch_population.py:299` e `pipeline.py:217` passam `True`; os que herdam `False` só enriquecem contato). Gatilho formalmente **supersedido**; fato sustentador é **medição do @qa**, não verificação do @po — declarado. Materializado como draft `docs/stories/story-outbound-feed-selection-default-safety-01.md` (owner @po, prazo 2026-09-08). **`MNT-001` + `MNT-004`** → draft `docs/stories/story-universe-identity-loader-hygiene-01.md` (prazo 2026-09-15). **`MNT-002`** declarado e não revertido (4 `MEMORY.md`, fora do PR 1). **`DOC-001` corrigido:** a DoD afirmava que `story-outbound-provenance-gap-01.md` não existia; existe, verificado. **`PROC-001` fechado nas duas pontas:** instrução de separação do PR 1 por caminho explícito (proibido `git add -A`) **e** cross-reference determinando que **`story-outreach-claim-policy-01` declare `publish.py` — arquivo CONGELADO — no seu próprio File List e escopo de re-freeze**, metade que o @qa deixara aberta — **com atualização factual: as 35 linhas foram COMMITADAS em `d8375d16` (`story-claim-safety-audit-01`) e `publish.py` já não está sujo; o drift virou committed, mesma categoria de V-07. Permanece a dívida do REBIND, que precisa de dono (aquela story ou o PR 2 desta como herança) — o @devops decide, mas não fica sem dono.** **Estado da árvore no fechamento:** `HEAD` avançou `6c7bb0ea` → **`e29ee198`** e todos os arquivos de código alheios foram commitados; **os 15 sha256 foram RECONFERIDOS após o avanço: 15/15 MATCH**. **Contenção manual verificada read-only no fechamento:** 14 linhas de `outreach_accounts` (camada **warmbly**, não a shadow) com `do_not_contact=true`, `blocked=true`, `block_reason='sector_classifier_false_positive_si…'`, incluindo a conta do incidente — autorizada pelo usuário, executada fora do ciclo de código; **band-aid que elimina a exposição imediata daquelas 14 contas e só delas; a causa raiz é resolvida pelo deploy desta correção**; permanece mitigação temporária e **não** é revertida com rollback de código (Escalonamento REQ-008). **Reconciliação:** DoD reescrita com veredito em todos os 15 itens (11 satisfeitos, 4 diferidos ao @devops com owner e condição); **bloco Task 9 (T9.1-T9.8) criado com checkboxes** — as subtasks existiam só no Dev Agent Record, sem nada a reconciliar; Task 7 anotada como aberta por desenho (autoridade @devops); Task 8 reconciliada com a revisão T9.7. **Seção "Handoff para @devops"** acrescentada com File List exata do PR 1 por caminho, lista de exclusão, 5 caminhos congelados do PR 2 + herança da branch, e as 8 pré-condições de publicação. **`publication_authorized` permanece `false`** — não há commit; `reviewed_commit === HEAD` é insatisfazível hoje, e o PR 1 é o que produz o commit. Story **LIBERADA para o @devops** executar a Task 7 (2 PRs). | Pax (@po) |
| 2026-09-01 | 0.7.0 | **QA Gate iteração 2 — veredito CONCERNS. Status: `InReview` → `Done`.** Validação independente por medição própria; nenhum número do @dev aceito sem reprodução. **Método deliberadamente mais forte que o da iteração 1:** em vez de reimplementar a projeção de entrada (o modo de falha que quase deixou passar o fix inalcançável), **importei e chamei `loader.load_company_input`** — a mesma função que `worker.py:144` invoca — contra a base viva em modo somente leitura (`set_session(readonly=True)`, zero escrita), executando o código da working tree; verifiquei antes que o worker chama o loader **sem `contract_limit`**, logo a superfície C4 em produção não é truncada. **Resultado: 4 de 4 raízes Sistema S saem de `TARGET_CONFIRMED` → `TARGET_OUT_OF_SCOPE`** (conf 0.95), com `n_exec` **6/3/3/0** preservado e 858/346/140/208 = 1.552 contratos — terceira medição independente convergente. **Gate C3 verificado por leitura e execução:** `n_exec` na linha 311, `cnae_eng` na 314, gate nas 333-362, primeiro hard-out concorrente na 365, nenhum `return` antes, predicado `if parafiscal_hit:` **sem conjunção com `n_exec`** (provado com `n_exec=3` ainda suprimindo). **Superfície C4:** 235 variantes distintas (108+53+21+53), 220 casando, **15 não casando** — reproduz exatamente a docstring; caso discriminante exercitado (`"SESCRS - ADM REG RS"` não casa sozinha e a entidade ainda sai). **Blast radius reproduzido exatamente:** 8.667 raízes `TARGET_CONFIRMED`, 27.577 pares, **68 suprimidas**, **0 construtoras**, **1** com evidência de construção no nome (FEESC `82895327`, já declarada). **Suíte completa** com baseline em `git worktree` detached (NÃO `git stash` — working tree compartilhada com agente ativo): HEAD 5.370 passed / 134 failed / 53 errors → **187 IDs**; working tree 5.574 / 135 / 53 → **188 IDs**; `comm -23` vazio (zero correção acidental), `comm -13` = 1 ID (`test_transparencia_crawler::test_rate_limit`) que **passa isolado nos dois lados** — flakiness de ordem, **zero regressão real**. ACs 15/16 reexecutados: P=1.0 R=1.0, corpus 222/222 e 100/100, `ALL FLIPS` vazio. **Drift de freeze pré-existente CONFIRMADO por critério binário** (`git log main..HEAD -- <path>` retorna commits para os 7 caminhos) — não introduzido por esta story; **exceção: `publish.py`** tem além disso **35 linhas não commitadas** da story de claim-safety, arquivo **congelado** e **não declarado por ninguém**; testei a dependência em vez de supor — o AC 25(a) passa contra o `publish.py` do HEAD, logo é **independente** do diff alheio. **`MNT-003` PARCIALMENTE FALSIFICADO:** os 2 call sites que o @po nomeou passam `True`, mas existem **3 outros que omitem o argumento** e herdam o default `False` (`continuous_from_target_fit.py:338` via CLI `enrich-continuous`; `national_confirmed.py:93` via `cmd_national_confirmed`; `load_confirmed_jobs_from_dsn:286`, morto mas com nome enganoso); medido em produção que as 4 raízes estão `CONSTRUCTION_PROBABLE` conf 0.4 e **67 das 68** voltariam por esse ramo. **Não bloqueante** porque o caminho agendado está protegido ponta a ponta (`extra-confenge-contact-cycle` → `batch_population.py:299` e `extra-confenge-feed-cycle` → `pipeline.py:217`, ambos `True`) e nenhum timer/cron/Makefile invoca os comandos manuais. **Segurança HIGH-RISK:** `cnpj14` nunca alterado, `party_role.py` intocado, guarda whole-token verificada, ruff limpo no escopo. Higiene: sujei e **restaurei** os artefatos de campanha e `docs/ops/campaigns/`. **AC 17 / 20 / 25(b) pendentes do @devops por desenho — não rebaixam o veredito.** Issues abertas: `MNT-003-REVISED` (medium), `PROC-001` (medium, separação do PR 1), `MNT-001`/`MNT-002`/`MNT-004`/`DOC-001` (low). `DOC-001`: verifiquei por `ls` que `docs/stories/story-outbound-provenance-gap-01.md` **existe** — a DoD está desatualizada ao dizer que não. Gate: `docs/qa/gates/outbound-sector-classifier-false-positive-01.yml` | Quinn (@qa) |
| 2026-09-01 | 0.6.1 | **AC 24(c) verificado por medição própria (read-only) e asserções do AC 21 endurecidas.** (i) **Blast radius reproduzido:** sobre as **8.667** raízes `TARGET_CONFIRMED` vivas (denominador idêntico ao de D.4) e 27.593 pares (raiz, `fornecedor_nome`), a política C4 suprime **exatamente 68** raízes — bate com D.4. Apenas **1** carrega evidência de construção no nome (`82895327` FEESC, já declarada como supressão consciente no AC 24(b)); **zero construtoras**. FUPAI (`18025536`), SEBRAE-SP (`43728245`) e CAIXA via `PAB SESC/MG` (`00360305`) confirmadas presentes. **Achado próprio que reforça o C4:** usando como "nome único" exatamente o que o `loader` sortearia (primeiro `fornecedor_nome` sem `ORDER BY`), a supressão cai para **58** — o @architect mediu 66 para a *variante dominante por frequência*; os dois divergem porque não são a mesma coisa, e é esse não-determinismo que o C4 elimina (68 estável). (ii) **Asserções endurecidas após autocrítica:** o teste do AC 21 asseria `target_fit_evidence` apenas como não-vazia, o que era **vacuoso** — o gate sempre anexa a própria entrada `PARAFISCAL_NAME`, então a asserção passaria mesmo com toda a evidência de execução apagada (o mesmo defeito que o @po rejeitou no AC 24 original). Agora assere o **número de entradas `CONTRACT_EXECUTION`**. (iii) O parametrize das 4 raízes deixou de usar `max(n_exec, 1)` (que dava `n_exec=1` ao SEBRAE/MG, contrariando o 0 medido) e passa a reproduzir os portfólios reais **e a asserir `relevant_execution_contract_count == 6/3/3/0`**, travando os valores que o AC 21 nomeia. (iv) Nota de auditabilidade registrada: o contador é a fonte auditável; a evidência é amostra truncada em 10 (consistente com os demais retornos do módulo). | Dex (@dev) |
| 2026-09-01 | 0.6.0 | **Iteração 2 do QA loop implementada — Status: `InProgress` → `InReview`.** T9.1-T9.8 concluídas. **T9.1/T9.2:** `scripts/confenge_universe/parafiscal.py` criado como fonte única (taxonomia **movida**, não copiada, e **não alterada**); `identity.py` importa dele e `_looks_like_parafiscal_institutional` virou wrapper fino — `test_identity_parafiscal.py` (20 testes, ACs 11-13) passou **sem nenhuma edição**, que é a prova do AC 23(a). **T9.3:** gate C3 incondicional em `classify_target_fit` (`TARGET_OUT_OF_SCOPE`, conf 0.95, `parafiscal_institutional_hard_out` + `parafiscal_marker:{m}`), **sem cláusula `n_exec == 0`**, sobre a superfície C4 (`razao_social` + `nome_fantasia` + todo `fornecedor_nome` distinto). **T9.4:** `classifier_sha()` hasheia `parafiscal.py` — `compute.py` passa de MATCH a DRIFT, como o @po aceitou. **T9.5:** 24 testes novos (19 do gate, 3 do AC 25(a), 2 do drift). **T9.6 — validação empírica REPRODUZIDA, não herdada:** dump read-only de produção via `ssh ec-prod` (1.552 contratos reais das 4 raízes, projeção idêntica à de `loader.load_company_input`, `set_session(readonly=True)`, zero escrita) → **4 de 4 raízes Sistema S saem de `TARGET_CONFIRMED` para `TARGET_OUT_OF_SCOPE`**, com `n_exec` preservado em 6/3/3/0 e contagens 858/346/140/208 — **coincidentes com a medição independente do @architect em D.3**. Zero delta em todos os gates já verdes (holdout P=1.0 R=1.0 n=40; adversarial 3/16; corpus n=1076 222/100 com `ALL FLIPS` vazio; `test_anti_overfitting` verde). Suíte completa contra worktree em `6c7bb0ea`, 2 execuções de cada lado: HEAD 5.370 passed / 134 failed / 53 errors; working tree **5.457 passed / 134 failed / 53 errors**, **conjuntos de IDs IDÊNTICOS (187, `diff` vazio)** — zero regressão, zero correção acidental. Ruff limpo. **Dois achados metodológicos declarados sobre a suíte:** (i) ela hoje **aborta na coleta** com `INTERNALERROR: SystemExit: 1` (`tests/test_official_status_reconfirmation.py` → `collect_report_data.py` chama `sys.exit(1)` sem `httpx`), **reproduzido idêntico no HEAD** — ambiental e pré-existente, contornado com `--ignore` + `--continue-on-collection-errors` nos **dois** lados; (ii) a 1ª execução de cada lado é contaminada por estado residual (3 IDs divergiram e, isolados, se comportam igual nas duas árvores) — **o critério válido é o conjunto de IDs, não a contagem de `passed`**. **T9.7:** seção "Task 8.0 — Achado" corrigida (SQL por reason code na shadow; ressalva SHADOW **desinvertida com medição própria** do unit file `TARGET_FIT_ASYNC_MODE=SHADOW` e das 4 linhas em `confenge-target-fit-v2`; passo 4 do universe builder acrescentado com a advertência de que **não há timer systemd**). **T9.8:** `MNT-001`/`MNT-003`/`MNT-004` registradas com owner, prazo e ponto de entrada; **MNT-002 são 4 `MEMORY.md`, não 2** — declarados fora do File List de código e **não revertidos** (reverter memória de outro agente excede a autoridade do @dev). **AC 20(a) verificado por execução própria de `discover_frozen_input_paths`, não assumido: `parafiscal.py` É congelado — PR 2 = 5 caminhos (4 rebinds + 1 entrada nova).** **Desvio nº 7 declarado:** o prompt do QA loop pedia early return "antes de qualquer lógica de n_exec", o que é **incompatível com o AC 21** (que exige `n_exec` verdadeiro auditável no resultado suprimido); segui a story ratificada. **Achado incidental para o @devops (não desta story, não escondido):** a mesma discovery revela drift pré-existente da branch `feat/468-*` em `publish.py`, `confenge_target_fit/store.py`, `batch_projection.py`, `confenge_feed_cycle.py`, `warmbly_bridge/*` + entrada nova `commercial_authority.py` — o rebind do PR 2 pode ser maior que 5 por herança. Task 7 (2 PRs) **não executada** — autoridade do @devops. | Dex (@dev) |
| 2026-09-01 | 0.5.0 | **PO Ratification da Architect Revision — story LIBERADA para o @dev (iteração 2 do QA loop). Status permanece `InProgress`.** ACs 21, 22, 23 ratificados como propostos (com exigência menor no 21: `relevant_execution_contract_count` verdadeiro deve permanecer auditável). **AC 24 NÃO ratificado como escrito e REESCRITO** — o texto proposto era vacuoso (o marcador parafiscal é o predicado único do gate, logo "sem marcador ⇒ não suprimido" é verdadeiro por construção e o teste não pode falhar) e media o blast radius sobre superfície mais estreita (`razao_social`) do que a de decisão (C4), subestimando o raio por construção; reescrito para o caso discriminante — `FUNDACAO ENGENHARIA E CONSTRUCOES LTDA` e `CONSTRUTORA ALFA` provados **não suprimidos em `classify_target_fit`** (hoje só protegidos no AC 12, camada que o outbound não consulta), FEESC/FUPAI como supressões declaradas, 68 como referência. **AC 25 ACRESCENTADO** — completude de revogações com `MEMBERSHIP_DROP_REASON` sob `_assert_membership_deactivation_delta`, sob pena de `PUBLICATION_REFUSED` (era prosa em seção de arquitetura, não verificável por gate). **AC 11 rebaixado a defesa em profundidade** (asserção inalterada; só o papel muda; defesa primária passa ao AC 21). **AC 17 reescrito** — denominador 4→0 nesta camada (o "14" é do warmbly), SQL por reason code na `confenge_target_fit_shadow`, ressalva SHADOW desinvertida, valores 68/568/~532 fixados. **AC 20(a) corrigido pela 3ª vez: PR 2 = 5 caminhos congelados (4 rebinds + 1 entrada NOVA).** Correção material ao D.2/C1: **`parafiscal.py` É congelado** — `discover_frozen_input_paths` faz fechamento transitivo de imports; verificado empiricamente em cópia descartável da árvore `scripts/`, sem tocar a working tree. Achados operacionais ratificados: `outreach_eligibility` inexistente como coluna **inverte a premissa do REQ-002** (a via `eligibility.py` protege ativação/publish, não o feed — as duas superfícies são distintas, nenhuma redundante); ausência de timer systemd torna o rerun do universe builder **passo manual explícito e obrigatório** no plano de deploy. **REQ-003 NÃO bloqueia a implementação, VIRA gate de fechamento** com pergunta discriminante registrada (a raiz `27080530` pertence à coorte das 1.448 sem `contracts_json`?) e a possibilidade de o registro ter mudado de estado pela contenção manual. `MNT-001/003/004` ratificadas; **`MNT-003` promovida de dívida a verificação atribuída ao @qa** (se algum call site passar `target_confirmed_only=False`, vira bloqueante). Custo do `classifier_sha()` **ACEITO sem aprovação adicional**. Escalonamento REQ-008 respondido: **não é o Plano B**. Sweep de texto obsoleto: **Scope IN** (o gate parafiscal e o módulo novo estavam ausentes do escopo), Estado-alvo, Baseline, Dependencies/sizing (4→7 arquivos), Rollback, Testing, DoD (20→25 ACs), File List esperado; seção "Task 8.0 — Achado" **anotada como SUPERSEDED** (SQL quebrado + ressalva SHADOW invertida — anotada, não reescrita: a seção é do @dev, correção é a T9.7). AC 25 **partido em duas verificações** após `grep` confirmar que `publish.py` **não tem dry-run** — (a) teste unitário do @dev provando emissão de `MEMBERSHIP_DROP_REASON`, (b) build real sem `PUBLICATION_REFUSED` pelo @devops; escrever "ou dry-run equivalente" repetiria o defeito que tornou o AC 17 insatisfazível duas vezes. State file validado contra `schema.json` (`gates.tests` normalizado de `PASS_NO_REGRESSION`, valor fora do enum que quebraria a leitura dos hooks, para `PASS`, com o motivo preservado em `gates_evidence`). | Pax (@po) |
| 2026-09-01 | 0.4.0 | **Architect Revision — desenho corrigido, pronto para @dev (QA loop iteração 2).** Status permanece `InProgress`. Opção escolhida: **(c)** — novo módulo `scripts/confenge_universe/parafiscal.py` como fonte única + **early return incondicional** em `classify_target_fit` (sem cláusula `n_exec == 0`) + `identity.py` rebaixada a defesa em profundidade. (a) rejeitada por acoplar resolução de identidade cadastral ao classificador de ICP; (b) rejeitada por dois motivos medidos: a cláusula `n_exec == 0` não dispararia (n_exec 3/3/6) e `NAME_OUT_OF_SCOPE` também é consumido por `sector_fit.py:463`. **Validação empírica contra produção (read-only, 1.552 contratos reais, worktree em `6c7bb0ea` para calibração):** ANTES reproduz a shadow viva linha a linha; com o gate, **4 de 4 raízes Sistema S saem de `TARGET_CONFIRMED` para `TARGET_OUT_OF_SCOPE`**. Blast radius medido em duas escalas: sobre as 8.667 raízes confirmadas → **68 saem de `TARGET_CONFIRMED` (0,78%)**, nenhuma construtora, 2 fronteiriças declaradas; sobre a base inteira (730.039 duplas raiz/nome de 4,67M contratos) → **568 raízes parafiscais** passam a carregar o reason code (376 INSUFFICIENT + 88 PROBABLE + 68 CONFIRMED + 36 já OUT), ~532 transições de classe. Predicado de medição `reason_codes::text LIKE` verificado em produção antes de entrar na story (jsonb; 5.614 hits para um código existente, 0 para o novo). `_assert_membership_deactivation_delta` lido: não é teto numérico, é reconciliação de completude — publicação recusada se as 68 revogações não forem declaradas. REQ-002 resolvido: **não é redundante mas também não é a defesa que se supunha** — `outreach_eligibility` não existe como coluna no banco e o feed (`continuous_from_target_fit.py:110-140`) filtra por `shadow_class`, sem join de universo; são duas superfícies distintas e o universe build é batch manual **sem timer no systemd**, logo precisa ser comandado explicitamente. ACs 21-24 propostos para ratificação do @po; AC 11 rebaixado a defesa em profundidade. Novas dívidas `MNT-003` (ramo `target_confirmed_only=False` contorna o gate via `sector_class`) e `MNT-004` (`razao_social` não determinístico em `loader.py`). Nenhum código implementado. | Aria (@architect) |
| 2026-09-01 | 0.3.1 | **QA Gate FAIL — Status: InReview → InProgress.** Medição independente (worktree em `6c7bb0ea` + produção read-only via `ssh ec-prod`) falsifica o AC 17 e o Estado-alvo: SESC-RS, SENAC e SENAI permanecem `TARGET_CONFIRMED` após a mudança; apenas SEBRAE/MG sai. Causa: `classify_target_fit` nunca consulta `resolve_identity` — `PARAFISCAL_INSTITUTIONAL` não afeta a tabela que governa o outbound. Lacuna de design (nenhum AC exigia o wiring), escalar a @architect + @sm. Confirmado independentemente: ACs 1–16, 18, 19 verdes; **zero flips objeto a objeto** no corpus n=1076 contra o código pré-mudança; suíte completa com 186 IDs de falha idênticos antes/depois (zero regressões); `cnpj14` preservado; `party_role.py` intocado; ruff limpo. Correções factuais documentadas para ratificação do @po: AC 20(a) é 3 caminhos congelados em DRIFT (não 6 — desvio nº 2 do @dev está correto), ressalva SHADOW invertida (a shadow É a tabela que governa; `current` tem 0 linhas), SQL do AC 17 aponta para tabela vazia e coluna inexistente, denominador "14" é do warmbly (target-fit tem 4). Gate: `docs/qa/gates/outbound-sector-classifier-false-positive-01.yml` | Quinn (@qa) |
| 2026-09-01 | 0.3.0 | **Status: Ready → InProgress → InReview.** Implementação completa das Tasks 1-6 e 8. Task 8.0 concluída: mecanismo de reclassificação = `reconcile.py:338` (`reconcile_classifier_drift`, sem filtro de classe) + gatilho concorrente `reconcile_version_drift` (`:335`). Resultado empírico: 6 casos-alvo corrigidos, corpus real n=1076 com zero flips (222 PASS / 100 exec, idênticos ao baseline), gate rotulado P=1.0 R=1.0. 63 testes novos. Suíte focada: **288 passed, 1 failed** (falha pré-existente e idêntica ao baseline pré-mudança: `test_rebound_freeze_drives_shipped_verifiers_on_campaign_tree`); baseline era 225 passed, 1 failed. Autocrítica aplicada: escopo parafiscal reduzido (fundações públicas genéricas mantidas em `PUBLIC_ORGAN`) e AC 16 endurecido para verificação por shard. 6 desvios do plano declarados no Dev Agent Record — atenção especial aos nº 2 (fingerprints são runtime, `store.py`/`compute.py` não editados, impacta a premissa do AC 20(a)) e nº 3 (`eligibility.py` adicionado ao escopo). Task 7 (2 PRs de re-freeze) NÃO executada — autoridade do @devops. | Dex (@dev) |
| 2026-09-01 | 0.1.0 | Draft HIGH-RISK a partir do design técnico completo do @architect (auditoria adversarial confirmada, incidente real SEBRAE-ES) | River (@sm) |
| 2026-09-01 | 0.2.1 | Proveniência da fixture do AC 5 verificada (contrato SEBRAE não está no corpus versionado — fragmento citado é a fixture aceita); requisito de portabilidade de caminhos adicionado ao AC 16; n=1076 do Baseline confirmado; state file operacional criado em `.aiox/state/stories/outbound-sector-classifier-false-positive-01.json` (status Ready, po_validated=true) | Pax (@po) |
| 2026-09-01 | 0.2.0 | Validated GO (9/10) — Status: Draft → Ready. 6 pontos abertos decididos e registrados na seção "Decisões do @po". Correções aplicadas: AC 17 reescrito (mecanismo de reclassificação provado insuficiente por `reclassify_insufficient.py:125`) + nova Task 8.0 bloqueante; AC 20 corrigido de 4 para 6 arquivos, com script de verify localizado e recipe de re-freeze completado (regenerar `confenge_final_status`, proibir squash); AC 16 repontado para baseline durável em `docs/stories/assets/`; dívida `story-outbound-provenance-gap-01` registrada como gate de DoD | Pax (@po) |

## QA Results

---

# QA Gate — Iteração 2 do QA Loop (re-review) — Quinn (@qa), 2026-09-01

## Veredito: **CONCERNS** — `InReview` → `Done`

**Gate file:** `docs/qa/gates/outbound-sector-classifier-false-positive-01.yml`
**Revisão avaliada:** working tree sobre `6c7bb0ea` · **Baseline:** `git worktree` detached em `6c7bb0ea`

### Método (por que esta medição é mais forte que a da iteração 1)

Não aceitei nenhum número do @dev. E, mais importante que isso: **não reimplementei a projeção de entrada**. O FAIL da iteração 1 aconteceu porque a defesa não alcançava o caminho real de produção; repetir o erro seria simular o classificador sobre uma projeção que eu mesmo construísse. Em vez disso **importei e chamei `loader.load_company_input`** — a mesma função que `worker.py:144` chama — contra a base viva em modo somente leitura (`conn.set_session(readonly=True)`, zero escrita), executando o código da working tree. Verifiquei antes que o worker invoca o loader **sem `contract_limit`**, logo `limit=None` e a superfície C4 em produção **não é truncada**.

O baseline da suíte foi obtido em `git worktree` detached, **não por `git stash`** — a working tree é compartilhada com um agente concorrente ativo e um stash destruiria trabalho dele.

---

### 1. Item por item — evidência própria

| # | Item | Resultado |
|---|---|---|
| 1 | Gate C3 posicionado e incondicional | **CONFIRMADO** |
| 2 | Superfície C4 (15/235) | **CONFIRMADO — número reproduzido exatamente** |
| 3 | `n_exec` real preservado (AC 21) | **CONFIRMADO** |
| 4 | `classifier_sha()` hasheia `parafiscal.py` | **CONFIRMADO** |
| 5 | 4/4 raízes saem de `TARGET_CONFIRMED` | **CONFIRMADO com o loader REAL** |
| 6 | Blast radius 68 / 8.667, 0 construtoras | **CONFIRMADO — exato** |
| 7 | Drift de freeze pré-existente | **CONFIRMADO, com 1 exceção material** |
| 8 | AC 25(b) sem dry-run possível | **CONFIRMADO** |
| 9 | MNT-003 | **PARCIALMENTE FALSIFICADO — ver §3** |
| 10 | Suíte: zero regressão | **CONFIRMADO** |
| 11 | Falhas do agente concorrente | **JÁ NÃO EXISTEM** |
| 12 | Working tree × File List | **CONTAMINADA — ver §4** |

**Item 1 — gate C3.** `target_fit.py`: `n_exec = len(exec_contracts)` na **311**, `cnae_eng` na **314**, gate nas **333-362**, primeiro hard-out concorrente na **365**. Nenhum `return` entre a assinatura (266) e o gate. O predicado é `if parafiscal_hit:` — **sem qualquer conjunção com `n_exec`**. Provado também por execução: entidade parafiscal com `n_exec=3` sai `TARGET_OUT_OF_SCOPE`.

**Item 2 — superfície C4.** Contagem própria em produção, por raiz: variantes distintas de `fornecedor_nome` **108 + 53 + 21 + 53 = 235**; casando marcador **104 + 52 + 20 + 44 = 220**; **não casando = 15**. Reproduz exatamente o "15 de 235" da docstring. *Correção de enunciado:* o C4 é um **OR** sobre a superfície — as 15 variantes não precisam ser "cobertas"; o que importa é cada raiz ter **≥ 1** variante casando, e todas as 4 têm. Exercitei o caso discriminante: `"SESCRS - ADM REG RS"` **não casa sozinha** (verificado) e a entidade ainda assim sai `TARGET_OUT_OF_SCOPE` pela variante em `contracts`.

**Item 5 — as 4 raízes, via loader real:**

| Raiz | Entidade | n contratos | Classe | conf | `n_exec` | Marcador |
|---|---|---|---|---|---|---|
| `03575238` | SESC-RS | 858 | **`TARGET_OUT_OF_SCOPE`** | 0.95 | **6** | `sesc` |
| `03709814` | SENAC | 346 | **`TARGET_OUT_OF_SCOPE`** | 0.95 | **3** | `senac` |
| `03776284` | SENAI | 140 | **`TARGET_OUT_OF_SCOPE`** | 0.95 | **3** | `senai` |
| `16589137` | SEBRAE/MG | 208 | **`TARGET_OUT_OF_SCOPE`** | 0.95 | **0** | `sebrae` |

**4 de 4.** Total 1.552 contratos e `n_exec` 6/3/3/0 — idênticos aos do @architect (D.3) e aos do @dev (T9.6). Três medições independentes convergindo. Estado ANTES reconfirmado na shadow viva: as 4 em `TARGET_CONFIRMED` / `confenge-target-fit-v2`.

**Item 6 — blast radius, contagem própria:** **8.667** raízes `TARGET_CONFIRMED` (idêntico a D.4); **27.577** pares distintos `(raiz, fornecedor_nome)` — idêntico a D.4, e não os 27.593 do @dev (dados vivos, delta imaterial); **68 raízes suprimidas — exato**. Com evidência de construção no nome: **1**, e é a já declarada `82895327` FEESC. **Construtoras/empreiteiras: 0.** Distribuição: `fundacao de apoio` 44, `fundacao educacional` 4, `fundacao de amparo` 4, `sebrae` 2, `senai` 2, `sesc` 2, `fundacao universitaria` 2, e 1 cada para `sesi`, `senac`, `servico de apoio as micro e pequenas empresas`, `arquidiocese`, `diocese`, `mitra diocesana`, `fundacao de ensino`, `fundacao de pesquisa`.

**Item 10 — suíte completa.** Mesma invocação dos dois lados.

| | HEAD (`6c7bb0ea`, worktree) | Working tree |
|---|---|---|
| passed | 5.370 | 5.574 |
| failed | 134 | 135 |
| errors | 53 | 53 |
| **IDs distintos falha+erro** | **187** | **188** |

`comm -23` (só no HEAD) = **vazio** — nenhuma correção acidental. `comm -13` (só na working tree) = **1 ID**: `tests/test_transparencia_crawler.py::TestSeleniumCrawler::test_rate_limit`. **Isolado, ele PASSA nos dois lados** (verificado) — é a flakiness de ordem/estado que o @dev declarou, não regressão. **Zero regressões reais.**

**Item 11.** As 2 falhas em `test_strict_national_esr_and_service_ontology.py` que o @dev atribuiu ao agente concorrente **não aparecem em nenhum dos dois conjuntos** (grep = 0 de cada lado). Foram corrigidas nesse intervalo. Não há falha alheia pendente afetando o veredito.

**ACs 15 e 16 reexecutados por mim:** gate rotulado antes/depois idêntico **P=1.0 R=1.0** (tp=20 fp=0 tn=24 fn=0); corpus real n=1076 **222 → 222** e **100 → 100**; seção `ALL FLIPS` **vazia**; adversarial 3/16, exatamente os 3 pré-existentes OUT. `eval_contract_relevance_holdout`: `ok=true`, P=1.0, R=1.0, FPR=0.0, n=40.

**Segurança / integridade (HIGH-RISK):** `cnpj14` nunca alterado — o diff de `identity.py` reusa o mesmo par `normalize_cnpj14` + `is_valid_cnpj14` já existente, sem sintetizar dígito nem mutar a raiz; nenhum dos outros 6 arquivos toca `cnpj14`. **`party_role.py` INTOCADO** (ausente de `git status`; último commit `695b0b5b`, anterior a esta story). Nenhum CNPJ/razão social na lógica de produção; guarda whole-token verificada por execução (`SESCOOPERATIVA` e `SENAIA` não casam). **Ruff limpo no escopo da story.** Todos os meus acessos a produção foram `SELECT` com `set_session(readonly=True)`.

---

### 2. `publish.py` — achado que ninguém tinha nomeado

`scripts/confenge_activation/publish.py` tem **35 linhas NÃO COMMITADAS** na working tree (`CLAIM_SAFETY_ROLLBACK_ANCHOR_KEY`, `claim_safety_hash` em `publication_semantic_hash`, âncora de rollback em `atomic_publish_directory`). Ele **não está no File List** desta story e **não foi nomeado** no aviso de contaminação do @dev — que listou apenas `confenge_account_intelligence/*` e `send_readiness.py`. É arquivo **congelado**.

Isso importava porque o AC 25(a) exercita `_assert_membership_deactivation_delta`, que vive nesse arquivo. **Testei a dependência em vez de supor:** copiei `test_membership_drop_completeness.py` para o worktree em `6c7bb0ea` (`publish.py` **sem** as 35 linhas) e **os 3 testes passam**. O AC 25(a) é portanto verde sobre o código congelado original, **independente do diff alheio**. Não é bloqueante — é instrução de separação para o @devops.

**Item 7 — drift pré-existente, critério binário.** Committed em `main..HEAD` = herança da branch; uncommitted = precisa de dono. `git log --oneline main..HEAD -- <path>` retorna commits para os **7** caminhos apontados pelo @dev (`publish.py`, `confenge_target_fit/store.py`, `batch_projection.py`, `confenge_feed_cycle.py`, `warmbly_bridge/__init__.py`, `warmbly_bridge/export.py`, `commercial_authority.py`), todos tocados por `8b47d3d0` / `c9cad134` / `6c7bb0ea` e anteriores. **Drift pré-existente confirmado — não foi introduzido por esta story.** A única exceção é `publish.py`, que tem drift committed **E** as 35 linhas uncommitted acima.

---

### 3. MNT-003 — o @po tem razão em ter mandado verificar, e a story está incompleta

**Não é bloqueante, mas não é "verificado, tudo certo".**

Os 2 call sites que o @po nomeou **passam `True`** — confirmado (`confenge_outreach_pipeline/pipeline.py:217`, `decision_unit_intelligence/batch_population.py:299`). O gatilho literal do @po não dispara.

**Porém o @po assumiu que existiam apenas 2 call sites. Existem 5.** Os outros 3 **omitem** o argumento e herdam o default `target_confirmed_only: bool = False` (`continuous_from_target_fit.py:69`):

| Call site | Alcançável por | Situação |
|---|---|---|
| `continuous_from_target_fit.py:338` (`run_continuous_enrichment`) | `confenge_contact_resolution/cli.py:447` — comando `enrich-continuous` | CLI manual |
| `confenge_process_enrichment/national_confirmed.py:93` | `confenge_process_enrichment/cli.py:195` — `cmd_national_confirmed` | CLI manual |
| `continuous_from_target_fit.py:286` (`load_confirmed_jobs_from_dsn`) | sem chamadores | Código morto — mas o nome promete "confirmed" e o corpo passa `False`. Armadilha latente. |

**Impacto medido em produção, não estimado:** as 4 raízes Sistema S estão em `confenge_company_sector_current` como `CONSTRUCTION_PROBABLE` conf **0.4** — exatamente o que o @po antecipou — e **67 das 68** raízes suprimidas pelo gate seriam reselecionadas por esse ramo.

**Por que mesmo assim não é bloqueante — e por que o argumento NÃO é "agendado vs manual".** Conferi o estado real dos units em `ec-prod`: `extra-confenge-contact-cycle.timer` = **disabled**, `extra-confenge-feed-cycle.timer` = **disabled**; o único enabled é `extra-confenge-target-fit-worker.service`. **Hoje nenhum dos dois ciclos está agendado** — ambos são disparados a mão. Apoiar o veredito em "agendado" seria falsificável por um comando.

O discriminante real é **qual comando passa `True`**:

| Natureza do comando | Cadeia | `target_confirmed_only` |
|---|---|---|
| **Constrói o feed de outbound** | `scripts.ops.confenge_contact_cycle` → `scripts.decision_unit_intelligence batch` → `batch_population.py:299` | **`True`** |
| **Constrói o feed de outbound** | `confenge_feed_cycle` → outreach pipeline → `pipeline.py:217` | **`True`** |
| Apenas enriquece contatos | `enrich-continuous` → `continuous_from_target_fit.py:338` | `False` (default) |
| Apenas enriquece contatos | `national-confirmed` → `national_confirmed.py:93` | `False` (default) |

Enriquecer contato **não publica feed nem dispara e-mail**. O dano do incidente só se materializa pelo caminho de construção do feed — e esse está protegido nos dois pontos de entrada.

**Recomendação (story própria, não alargar este diff):** inverter o default para `True`, ou tornar o parâmetro keyword obrigatório sem default, de modo que a seleção ampla vire escolha explícita. Corrigir junto `load_confirmed_jobs_from_dsn`.

---

### 4. Higiene da working tree — instrução ao @devops

Os 7 arquivos de código do File List estão todos presentes e corretos. Há **5 arquivos de código alheios** misturados: `publish.py` (claim-safety), `confenge_account_intelligence/{facts,message_spine,normalize}.py` e `send_readiness.py` (`story-outreach-claim-policy-01`), mais `scripts/confenge/__main__.py`, que **apareceu durante este próprio review** — o agente concorrente segue ativo.

**O PR 1 não pode ser aberto a partir de `git add -A`.** A lista explícita de inclusão/exclusão está no gate file, seção `devops_pr1_separation`.

**Âncora de revisão (porque "working tree não commitada" não identifica nada).** Os artefatos de campanha voltaram a sujar **depois** de eu os restaurar, e `scripts/confenge/__main__.py` apareceu no meio deste review — o agente concorrente está vivo nesta árvore. Registrei os **sha256 dos 15 arquivos que revisei** em `devops_pr1_separation.reviewed_sha256` no gate file. **Conferir antes de abrir o PR 1.** Divergência = o arquivo mudou após o gate e este veredito **não o cobre**; reabrir com o @qa antes de publicar.

### 4.1 AC 18 — verificado literalmente, não por comportamento

Li as constantes em vez de inferi-las do teste de drift: `contract_relevance.py:14` → `RULE_VERSION = "contract-relevance-v3"`; `target_fit.py:49` → `TARGET_FIT_VERSION = "confenge-target-fit-v3"`. Produção está em `confenge-target-fit-v2` (reconfirmado por mim na shadow viva), logo o gatilho `reconcile_version_drift` (`reconcile.py:335`) dispara **além e independentemente** do `reconcile_classifier_drift` (`:338`) — os dois gatilhos do Task 8.0 estão de fato armados.

**Higiene:** rodar a suíte reescreve `artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01/*.json` e 4 arquivos em `docs/ops/campaigns/`. **Eu sujei e restaurei todos** com `git checkout --` após minhas medições; a working tree entregue está limpa nesses caminhos. Conferir `git status` imediatamente antes do PR 1.

---

### 5. Situação dos 25 ACs

- **Verificados por mim:** 1-16, 18, 19, 21, 22, 23, 24 · e **25(a)**, com a prova extra de independência do diff alheio.
- **Pendentes do @devops por desenho (não rebaixam o veredito):** **AC 17** (medição pós-deploy — linha de base ANTES reconfirmada por mim: as 4 em `TARGET_CONFIRMED`/`v2` e **zero** linhas na shadow com `parafiscal_institutional_hard_out` hoje), **AC 20** (2 PRs), **AC 25(b)** (build real — confirmei por `grep` que `publish.py` **não tem** dry-run: 0 ocorrências de `dry_run|dry-run|plan_only|--plan`).

### 6. Issues

| ID | Sev | Descrição |
|---|---|---|
| `MNT-003-REVISED` | medium | 3 call sites com default `False` que a story não conhecia; 67/68 raízes voltariam. Caminho agendado protegido → dívida, não bloqueio. |
| `PROC-001` | medium | 5 arquivos de código alheios na working tree; `publish.py` é congelado e não estava declarado. |
| `MNT-004` | low | `razao_social` não determinístico. Mitigado pelo C4, não resolvido. |
| `MNT-001` | low | Guard `\bbanco\b` morto. Não corrigir aqui — decisão correta do @dev. |
| `MNT-002` | low | 4 `MEMORY.md` declarados, não revertidos. Concordo com a decisão. |
| `DOC-001` | low | A DoD ainda diz que `story-outbound-provenance-gap-01` não existe. **Verifiquei: existe.** @po reconciliar no fechamento. |

### 7. Por que CONCERNS e não PASS

A lacuna que motivou o FAIL da iteração 1 está **fechada**, e eu a verifiquei pelo caminho mais forte disponível: chamei o loader real de produção contra a base viva, em vez de reimplementar a projeção. As 4 raízes saem, o blast radius bate exatamente, nenhuma construtora é suprimida, e a suíte não tem uma única regressão real.

Não é PASS por duas razões que não dependem de opinião: **(i)** MNT-003 é mais amplo do que a story descreve — há 3 call sites que o @po não sabia que existiam, e não posso fechar como "verificado, tudo certo" o item que ele me atribuiu justamente para não ser assumido; **(ii)** o PR 1 não pode ser montado por `git add -A`, e um arquivo congelado está contaminado por trabalho alheio não declarado.

Nenhuma das duas é defeito da implementação do @dex, que nesta iteração fez o trabalho certo — inclusive medindo produção em vez de herdar números.

---

## QA Results — Iteração 1 (registro histórico, veredito FAIL superado)

### Review Date: 2026-09-01

### Reviewed By: Quinn (@qa) — validação INDEPENDENTE do @dev

**Método.** Não aceitei nenhum número reportado pelo @dev. Criei um `git worktree` detached em `HEAD` (`6c7bb0ea`) e executei toda medição comparativa **before/after** contra código real, não contra afirmações. Produção foi consultada por `ssh ec-prod` em modo **somente leitura** (SELECT / healthcheck), no release `d0c706c5e46d8491ec510598173d5acf63eb71d8`.

### Veredito: **FAIL**

O motivo NÃO é qualidade de implementação — a implementação do @dev é boa e os 19 ACs verificáveis localmente passam. O motivo é que **a medição em produção falsifica o AC 17 e o Estado-alvo da story**.

---

### 1. Achado bloqueante (REQ-001) — AC 17 e Estado-alvo não são atingidos

Simulei `classify_target_fit` sobre **todos** os contratos reais de produção das 4 raízes Sistema S hoje em `TARGET_CONFIRMED`, nos dois worktrees:

| Entidade | n contratos | ANTES (HEAD) | DEPOIS (working tree) |
|---|---|---|---|
| SESC – Adm. Regional RS | 858 | `TARGET_CONFIRMED` (n_exec=9) | **`TARGET_CONFIRMED`** (n_exec=6) |
| SENAC | 346 | `TARGET_CONFIRMED` (n_exec=4) | **`TARGET_CONFIRMED`** (n_exec=3) |
| SENAI | 140 | `TARGET_CONFIRMED` (n_exec=4) | **`TARGET_CONFIRMED`** (n_exec=3) |
| SEBRAE/MG | 208 | `TARGET_CONFIRMED` (n_exec=3) | `TARGET_INSUFFICIENT_EVIDENCE` (n_exec=0) |

**A simulação está calibrada:** a coluna ANTES reproduziu **exatamente** o `shadow_class` vivo de produção nas 4 raízes. Não é um cenário hipotético — é a tabela real reproduzida em laboratório.

**Causa raiz do gap:** `classify_target_fit` (`target_fit.py:231`) **nunca consulta `resolve_identity`**. O único call site de `resolve_identity` é `aggregate.py:336` (universe builder), que **não** faz parte do caminho `reconcile`/`compute` nomeado no Task 8.0. Logo o novo `PARAFISCAL_INSTITUTIONAL` **não tem efeito nenhum sobre a tabela que governa o outbound**.

**Isto é lacuna de design da story, não erro do @dev.** Nenhum AC exigia esse wiring. O AC 11 pede que `resolve_identity` exclua Sistema S — e ele exclui, verificado com os CNPJs reais. O que falta é a ponte entre essa exclusão e o `target_fit_class`. **Encaminhamento correto: @architect + @sm para AC adicional — não @dev como "corrigir bug".**

### 2. Achado bloqueante (REQ-002) — o plano de deploy omite a única defesa que funciona

A defesa real que esta mudança cria contra Sistema S no outbound é o mapeamento em `eligibility.py`: `PARAFISCAL_INSTITUTIONAL → NOT_CONSTRUCTION`, consumido por `send_readiness.py:456`. Mas `outreach_eligibility` é produzido pelo **universe builder** (`confenge_universe/pipeline.py`), e o plano de deploy do Task 8.0 manda executar **apenas** `confenge_target_fit reconcile` + restart do worker — que não tocam esse campo. Sem rerun do universe pipeline, a defesa não é ativada.

### 3. Correções factuais à story (requerem ratificação do @po — não editei o texto dos ACs)

- **AC 20(a) está errado; o desvio nº 2 do @dev está certo.** sha256 contra `frozen-inputs-manifest.json`: **DRIFT** em `contract_relevance.py`, `pipeline.py`, `target_fit.py`; **MATCH byte-idêntico** em `store.py` e `compute.py`; `identity.py` e `eligibility.py` **não estão** no conjunto congelado. **Escopo real de rebind do PR 2 = 3 caminhos, não 6.**
- **A ressalva SHADOW da story está invertida.** Produção está em `ASYNC MODE: SHADOW`, `confenge_company_target_fit_current` tem **0 linhas** e `confenge_target_fit_shadow` tem 410.298 (8.667 `TARGET_CONFIRMED`). O feed (`continuous_from_target_fit.py:111`) lê a shadow quando o modo é SHADOW. **A shadow É a tabela que governa o outbound** — o reconcile em SHADOW opera na tabela certa. O texto atual desorientaria o deploy.
- **O SQL de medição do AC 17 está quebrado duas vezes:** aponta para `confenge_company_target_fit_current` (vazia) e seleciona `razao_social`, coluna que **não existe** nessa tabela. Forma correta: `confenge_target_fit_shadow JOIN supplier_registry ON left(cnpj14,8)=cnpj_raiz`.
- **O denominador "14" não existe nesta camada.** Refere-se a `outreach_accounts` do warmbly. Na camada target-fit medi **4** raízes Sistema S em `TARGET_CONFIRMED` (7 em `PROBABLE`, 1 em `OUT_OF_SCOPE`).
- **Cobertura da causa raiz do incidente real não comprovada (REQ-003).** A raiz do SEBRAE-ES (`27080530`) tem **0 linhas** em `pncp_supplier_contracts` e está **ausente** da shadow. A conta que recebeu o e-mail chegou ao warmbly por um caminho que esta story não toca. O fix previne a *classe* do erro; a cadeia do incidente concreto segue sem prova.
- **DoD não satisfeita (REQ-007):** `story-outbound-provenance-gap-01` **não existe** em `docs/stories/` (gate de fechamento da Decisão do @po nº 4).
- **Escalonamento omitido (REQ-008):** a Decisão do @po nº 1 previa escalonamento quando o mecanismo não reprocessa linhas confirmadas. O mecanismo existe mas é materialmente insuficiente — equivalente ao Plano B — e nenhum escalonamento foi registrado.

### 4. O que verifiquei e está correto (com meus próprios olhos)

| Item | Evidência |
|---|---|
| **AC 1–10** | Executados por mim em `_object_is_execution` **e** em `classify_contract_relevance`. 10/10. AC 5 (fragmento real SEBRAE): `exec=False`, `rel=FAIL`. `"ESTANDE DE TIRO"` continua `False` (gap pré-existente, OUT — não foi forçado). |
| **AC 11–13** | Testado com as **razões sociais e CNPJs reais de produção**: `03575238000133` SESC-RS, `03709814002808` SENAC, `03776284000109` SENAI, `16589137000163` SEBRAE/MG → todos `valid=False`, `PARAFISCAL_INSTITUTIONAL`. `FUNDACAO ENGENHARIA E CONSTRUCOES LTDA` → `valid=True`, inclusive acentuado. `CONSTRUTORA ALFA ENGENHARIA LTDA` → `valid=True`. |
| **AC 14** | 4 testes de `test_sql_prefilter_seeds_regression.py` verdes (superset + corte de 30 termos). |
| **AC 15** | `python3 -m scripts.ops.eval_contract_relevance_holdout` → `ok=true, precision=1.0, recall=1.0, fpr=0.0, n=40`. |
| **AC 16** | **Verificação mais forte que a exigida:** classifiquei os 1076 objetos com o código **pré-mudança** (worktree em HEAD) e com o atual, comparando **objeto a objeto**. **0 flips por objeto** (relPASS=222, exec=100 idênticos). Os constantes hardcoded do teste portado são, portanto, valores pré-mudança reais. Sem `skip`/`xfail`/mock; falha (`pytest.fail`) se o corpus sumir. |
| **AC 18** | Medido nos dois worktrees: `RULE_VERSION` v2→v3, `TARGET_FIT_VERSION` v2→v3, `classifier_sha` `03cb5f54…`→`3f5217a2…`, `sector_sha` `94697006…`→`f150a634…`. Ambos os predicados de reconcile disparam. Produção está em `confenge-target-fit-v2`, confirmando o drift. |
| **AC 19** | 3 testes de `test_anti_overfitting.py` verdes. |
| **Regressão sistêmica** | Suíte **completa** (`tests/`, `-m "not slow"`) nos dois worktrees. ANTES: 5352 passed / 135 failed / 51 errors. DEPOIS: 5415 passed / 135 failed / 51 errors. **Diff dos IDs que falham/erram: 186 idênticos, zero novos, zero corrigidos.** Todas ambientais (`httpx`, `prometheus_client`, `fastapi`, `numpy`, `lxml`, `hypothesis`, `reportlab` ausentes; sem Postgres local). Os ~15 call sites do mapa do @architect estão cobertos por esse conjunto. |
| **Segurança / integridade** | Nenhuma mudança altera `cnpj14` — todos os caminhos de exclusão preservam o valor original (verificado por execução). `scripts/confenge_outreach_pipeline/party_role.py` permanece **intocado**. Sem migration, sem segredo. |
| **Escopo do working tree** | Nenhum arquivo de **código** fora da File List. Única exceção: os 2 `MEMORY.md` de agente (MNT-002). |
| **Lint** | `ruff check scripts/ tests/` → All checks passed. |
| **Colisão léxica 2.1** | A remoção dos 5 marcadores de fundação pública **não** reabre a colisão: ACs 3 e 4 passam em `classify_contract_relevance` com `evidence_neutralized_entity_or_event` — a neutralização é independente da identidade; e `FUNDACAO MUNICIPAL/ESTADUAL/CULTURAL/HOSPITALAR/NACIONAL` seguem `PUBLIC_ORGAN`. **Decisão do @dev está correta.** |

### 5. Dívida e observações menores

- **MNT-001** — Bug latente `\bbanco\b` **confirmado real**: `normalize_name("Banco Alfa S.A.") == "BANCO ALFA S A"` e o guard retorna `False` — código morto. Fora de escopo é defensável; **a ausência de registro formal no backlog (ID/owner/prazo) não é** — a "Restrição de nova dívida" exige registro.
- **MNT-002** — `.claude/agent-memory/aiox-dev/MEMORY.md` e `aiox-po/MEMORY.md` modificados fora da File List.
- **TEST-001** — `--cov=scripts` (invocação mandatada na seção Testing) não executado: `pytest-cov` ausente, `pip` bloqueado por PEP 668. Nenhuma cobertura medida numa mudança HIGH-RISK.
- **DOC-001** — `n=40` no gate canônico vs. `n=44` afirmado na story.
- **DOC-002** — `eval_contract_relevance_real_holdout` (listado em `quality_gate_tools`) retorna `BLOCKED_REAL_HOLDOUT_NOT_REVIEWED`. **Idêntico antes e depois** — pré-existente, não é regressão desta story, mas é um gate declarado que não passa.
- **DOC-003** — O efeito colateral da suíte é maior do que a nota do @dev. A suíte **focada** suja 2 JSONs; a **completa** suja **8 arquivos rastreados** (`artifacts/campaigns/…` ×4, `docs/ops/campaigns/…` ×4) e cria untracked `artifacts/pseo/` e `output/process_documents/`. **Eu restaurei todos** após medir — o working tree entregue está limpo nesses caminhos. @devops deve conferir `git status` antes do PR 1.

### 6. O que o @dev precisa fazer (retorna a InProgress)

1. **Não** iniciar correção sozinho no REQ-001: escalar a @architect + @sm para AC adicional que ligue a exclusão de identidade ao caminho de target-fit (ou um gate parafiscal dentro de `classify_target_fit`).
2. Escalar ao @po (REQ-008) — a situação é equivalente ao Plano B da Decisão nº 1.
3. Corrigir o plano de deploy (REQ-002): incluir rerun explícito do universe pipeline e prova de que `outreach_eligibility` das raízes Sistema S vira `NOT_CONSTRUCTION`.
4. Registrar MNT-001 no backlog com ID, owner e prazo.
5. Declarar ou remover os 2 `MEMORY.md` (MNT-002).

Correções de texto de AC (REQ-004/005/006) são autoridade do **@po** — documentadas acima com evidência, aguardando ratificação. Não editei o bloco de ACs.

### Gate Status

Gate: FAIL → `docs/qa/gates/outbound-sector-classifier-false-positive-01.yml`

---

## Architect Revision — Ready for Dev Loop Iteration 2

**Autor:** Aria (@architect) · **Data:** 2026-09-01 · **Gatilho:** QA Gate FAIL (REQ-001, REQ-002) · **Status da story:** permanece `InProgress`

O @qa está certo e eu estou errado. O desenho original que produzi tratava `resolve_identity` como se fosse a barreira de identidade do sistema. Não é — é a barreira de identidade **de um pipeline** (`aggregate.py`/universe builder). O caminho que governa o outbound (`reconcile` → `compute` → `classify_target_fit` → `confenge_target_fit_shadow` → feed) nunca a consulta. A exclusão parafiscal que o @dev implementou está correta e é código vivo no caminho do universe builder, mas é **inalcançável** no caminho que causou o incidente. Esta seção corrige o desenho.

### D.0 — Metodologia (o erro anterior foi entregar desenho não testado; não se repete)

Toda afirmação abaixo é medida, não inferida:

- Produção consultada por `ssh ec-prod` em **modo somente leitura** (`conn.set_session(readonly=True)`), release `623acdcd251a20fb4d2f185cd8fedcfea474bb4a` (o que o `extra-confenge-target-fit-worker.service` realmente executa — note que difere do release citado pelo @qa; o unit file aponta para `623acdcd`).
- Dump real de **1.552 contratos** das 4 raízes Sistema S + **27.577** pares (raiz, `fornecedor_nome`) de **8.667 raízes `TARGET_CONFIRMED`** da shadow + as 410.298 classes da shadow.
- Simulação executada com `git worktree` destacado em `6c7bb0ea` (ANTES) e na working tree do @dev (DEPOIS), **sem editar `target_fit.py`** — o gate proposto é um early return puro, logo é simulável fora do módulo.
- **Nenhuma escrita em produção.** Nenhum arquivo de código do repositório foi alterado por mim.

### D.1 — Opções avaliadas e decisão

| Opção | Mecanismo | Veredito |
|---|---|---|
| **(a)** `classify_target_fit` chama `resolve_identity` | Reaproveita a função existente | **Rejeitada.** `resolve_identity` decide CNPJ/CPF/órgão/banco/dígito verificador e devolve uma `Identity` — 5 taxonomias que `classify_target_fit` não precisa e não deve herdar. Acopla o classificador de ICP à resolução de identidade cadastral e faz `target_fit.py` depender de `INVALID_IDENTITY`/`NATURAL_PERSON`, que são estados de universo, não de ICP. Também importaria `scripts.confenge_universe.__init__` (congelado) na cadeia. |
| **(b)** Estender `_NAME_HARD_OUT` / `NAME_OUT_OF_SCOPE` | Reusa `name_hard_out_without_execution` | **Rejeitada, com evidência dura.** Dois defeitos independentes: (i) a cláusula é `if hard_name and n_exec == 0` — com `n_exec ∈ {3,3,6}` nas 3 raízes que sobrevivem, o hard-out **não dispararia**; (ii) `NAME_OUT_OF_SCOPE` **não é privado do `target_fit.py`** — `scripts/commercial_leads/sector_fit.py:463` (`neg_name = _hits(name_norm, NAME_OUT_OF_SCOPE)`) também o consome. Mutá-lo altera silenciosamente a classificação de setor de toda a base, muito além do escopo desta story. Verificado por `grep`: 4 ocorrências, 2 delas fora de `target_fit.py`. |
| **(c) ESCOLHIDA** | Módulo compartilhado `parafiscal.py` + **early return incondicional** em `classify_target_fit` + `identity.py` rebaixada a defesa em profundidade | Ver D.2. |

### D.2 — Desenho escolhido (opção c)

**C1 — Fonte única de verdade: novo módulo `scripts/confenge_universe/parafiscal.py`** (arquivo NOVO, portanto **não congelado**).

Conteúdo: a tupla `PARAFISCAL_INSTITUTIONAL_MARKERS` (movida de `identity.py`, conteúdo inalterado — 38 marcadores efetivos) e `match_parafiscal_institutional(name) -> str | None` (matching whole-token sobre `normalize_name`, lógica idêntica à atual `_looks_like_parafiscal_institutional`). Depende **apenas** de `scripts.linkage.keys` → zero risco de import cíclico, e não puxa o `__init__` congelado.

**C2 — `identity.py` passa a importar de `parafiscal.py`.** Comportamento externo inalterado: ACs 11-13 continuam valendo, `PARAFISCAL_INSTITUTIONAL` continua sendo devolvido, `eligibility.py` continua mapeando para `NOT_CONSTRUCTION`. **Muda o papel, não o código:** deixa de ser a defesa primária e passa a ser defesa em profundidade do caminho `aggregate.py`/universe builder.

**C3 — Gate incondicional em `classify_target_fit`.** Um early return colocado **depois do loop de contratos** (para que `relevant_execution_contract_count` continue verdadeiro e auditável) e **antes de todo path de confirmação**:

- classe: `TARGET_OUT_OF_SCOPE`, confiança `0.95` (acima do `0.9` do `sector_fit_out_without_execution`, pois é evidência de tipo de entidade, não de texto de objeto);
- reason codes: `parafiscal_institutional_hard_out` + `parafiscal_marker:{marcador}`;
- **sem cláusula `n_exec == 0`.** Esta é a diferença material em relação ao `_name_hard_out` existente e é decisão de política de ICP, não de precisão: Sistema S reforma prédio próprio de verdade, e ainda assim não é construtora. Se o gate fosse condicionado a `n_exec == 0`, as 3 raízes que sobreviveram continuariam confirmando.

**C4 — Superfície de nome do gate (esta parte é a que impede a repetição do FAIL).** O gate **não pode** olhar só `razao_social`. Medição em produção:

- `loader.py:170` define `razao_social` como o **primeiro `fornecedor_nome` não-nulo** de uma query **sem `ORDER BY`** (`loader.py:143-146` só ordena quando há `limit`). O valor é, portanto, **não determinístico entre execuções**.
- As 4 raízes têm **235 variantes distintas** de `fornecedor_nome`. **15 delas não casam** com nenhum marcador: `SESCRS`, `SESCRS - ADM REG RS`, `SEBRAEMG`, `SERVICO DE APOIO AS MICRO E PEQUENAS EM` (truncada), além de 4 variantes com mojibake (`SERVIÃ‡O DE APOIO...`).
- Hoje, por sorte, o primeiro não-nulo de cada uma das 4 casa. **Depender disso seria desenhar sobre não-determinismo** — exatamente o tipo de suposição não verificada que causou este FAIL.

**Regra:** o gate avalia `razao_social`, `nome_fantasia` **e todo `fornecedor_nome` distinto presente em `contracts`** (que `classify_target_fit` já recebe). Basta **um** casar. Determinístico independentemente do sorteio do loader.

**C5 — `classifier_sha()` em `compute.py` passa a hashear `parafiscal.py`.** `inspect.getsource` só enxerga o módulo nomeado. Sem isso, acrescentar um marcador no futuro produziria **zero drift** no `reconcile` — reintroduzindo a mesma classe de bug de obsolescência silenciosa que esta story existe para matar.

> **Trade-off explícito para o @devops (não é surpresa, é decisão registrada):** `compute.py` está congelado e hoje está **MATCH byte-idêntico** (desvio nº 2 do @dev, ratificado pelo @qa). Editá-lo leva o rebind do PR 2 de **3 para 4 caminhos congelados**. Aceito: o custo é uma linha no manifesto; o benefício é que o mecanismo de reclassificação continua disparando em toda alteração futura da taxonomia.
>
> **`store.py::sector_classifier_sha256` NÃO muda — declarado OUT.** Verificado: hasheia `confenge_sector/classification.py` + `sector_fit.py` + `contract_relevance.py`. O caminho de setor não consulta marcadores parafiscais, logo incluí-lo seria acoplamento sem função. `store.py` permanece MATCH e fora do rebind.

### D.3 — Validação empírica (a exigência que eu não cumpri da primeira vez)

Simulação sobre os **1.552 contratos reais** das 4 raízes, projeção idêntica à de `loader.load_company_input` (`enriched_entities` devolveu `NULL` para as 4 → `cnae_principal=None`, `nome_fantasia=None`, confirmado em produção).

**Calibração — a coluna ANTES reproduz a shadow viva, linha a linha:**

| Raiz | Entidade | n | `shadow_class` real em prod | ANTES (worktree `6c7bb0ea`) |
|---|---|---|---|---|
| 03575238 | SESC-RS | 858 | `TARGET_CONFIRMED` conf=0.8 `multi_execution_contracts_triangulation` | `TARGET_CONFIRMED` conf=0.8 n_exec=9 — **idêntico** |
| 03709814 | SENAC | 346 | idem | `TARGET_CONFIRMED` conf=0.8 n_exec=4 — **idêntico** |
| 03776284 | SENAI | 140 | idem | `TARGET_CONFIRMED` conf=0.8 n_exec=4 — **idêntico** |
| 16589137 | SEBRAE/MG | 208 | idem | `TARGET_CONFIRMED` conf=0.8 n_exec=3 — **idêntico** |

**Resultado das três configurações:**

| Raiz | ANTES (`6c7bb0ea`) | DEPOIS — só mudança do @dev | DEPOIS — **+ gate arquitetural** |
|---|---|---|---|
| SESC-RS | `TARGET_CONFIRMED` (n_exec=9) | `TARGET_CONFIRMED` (n_exec=6) | **`TARGET_OUT_OF_SCOPE`** `parafiscal_marker:sesc` |
| SENAC | `TARGET_CONFIRMED` (n_exec=4) | `TARGET_CONFIRMED` (n_exec=3) | **`TARGET_OUT_OF_SCOPE`** `parafiscal_marker:senac` |
| SENAI | `TARGET_CONFIRMED` (n_exec=4) | `TARGET_CONFIRMED` (n_exec=3) | **`TARGET_OUT_OF_SCOPE`** `parafiscal_marker:senai` |
| SEBRAE/MG | `TARGET_CONFIRMED` (n_exec=3) | `TARGET_PROBABLE_RESEARCH` (n_exec=0) | **`TARGET_OUT_OF_SCOPE`** `parafiscal_marker:sebrae` |

**4 de 4 saem de `TARGET_CONFIRMED`.** O `n_exec` verdadeiro é preservado no registro (6, 3, 3, 0) — um auditor consegue ver "suprimi uma raiz com 6 contratos de execução reais", que é precisamente a informação que torna a decisão contestável e revisável.

*Divergência menor vs. @qa, sem consequência:* o @qa reportou SEBRAE/MG DEPOIS como `TARGET_INSUFFICIENT_EVIDENCE`; eu meço `TARGET_PROBABLE_RESEARCH` (n_exec=0, `sector=POSSIBLE_ENGINEERING_FIT` via `assess_construction`). Ambos são não-confirmados e ambos ficam `TARGET_OUT_OF_SCOPE` com o gate. Provável diferença na montagem de `sector_fit` na simulação. Registrado por honestidade, não altera nenhuma conclusão.

### D.4 — Blast radius do "incondicional" (medido em toda a população, não só nas 4)

Apliquei o matcher às **8.667 raízes `TARGET_CONFIRMED`** da shadow, sobre os 27.577 pares (raiz, nome):

| Política | Raízes atingidas | % da população confirmada |
|---|---|---|
| Só variante dominante | 66 | 0,76% |
| **Qualquer variante (C4 — a escolhida)** | **68** | **0,78%** |

As **2 raízes adicionais** que só a política C4 captura foram inspecionadas uma a uma:

- `43728245` — SEBRAE-SP. Nome dominante `SERVICO DE APOIO AS MICRO E PEQ EMPRESAS DE SAO PAULO` (abreviado, não casa), mas 58 de 91 variantes contêm `SEBRAE`. **Supressão correta** — e é a prova de que a política de variante dominante seria insuficiente.
- `00360305` — CAIXA ECONÔMICA FEDERAL, capturada por 1 variante em 75 (`PAB SESC/MG`, agência dentro de um SESC). **Supressão também correta no nível de ICP** (a CAIXA não é construtora; ela já é excluída por `DEFAULT_NON_CONSTRUCTION_SUPPLIER_MARKERS` no caminho de identidade), embora chegue lá pelo motivo errado. Registrado como imprecisão conhecida e aceita.

Inspeção das 68: são fundações de apoio universitário (~50), Sistema S (~6), fundações educacionais (4), dioceses/mitras (3), fundações de amparo (4). **Nenhuma construtora.** Duas fronteiriças, declaradas como baixas conscientes: `82895327 FUNDACAO DE ENSINO E ENGENHARIA DE SANTA CATARINA` (FEESC) e `18025536 FUNDACAO DE PESQUISA E ASSESSORAMENTO A INDUSTRIA` (FUPAI) — fundações de apoio que contratam engenharia, mas não são executoras de obra e não são o ICP da CONFENGE. **Ambas já eram suprimidas pela lista que o @dev implementou e o @po ratificou; o gate não amplia a taxonomia, só a torna alcançável.**

**Blast radius sobre a população INTEIRA (não só as confirmadas).** O gate é incondicional quanto à classe anterior, então o reason code vai aterrissar em toda raiz parafiscal, não só nas confirmadas. Medi separadamente, varrendo as 730.039 duplas distintas (raiz, `fornecedor_nome`) de `pncp_supplier_contracts` (4.668.511 linhas) com prefiltro ILIKE superset + matcher exato em Python:

| Métrica | Valor medido |
|---|---|
| Raízes parafiscais encontradas na base de fornecedores | **568** |
| Delas, presentes em `confenge_target_fit_shadow` | **568** (nenhuma sem materialização) |
| — hoje em `TARGET_INSUFFICIENT_EVIDENCE` | 376 |
| — hoje em `TARGET_PROBABLE_RESEARCH` | 88 |
| — hoje em **`TARGET_CONFIRMED`** | **68** |
| — hoje já em `TARGET_OUT_OF_SCOPE` | 36 |

**Dois números distintos, que NÃO devem ser confundidos no deploy:**

- **68** = raízes que **saem de `TARGET_CONFIRMED`** (8.667 → ~8.599). É este o delta a antecipar contra `_assert_membership_deactivation_delta`/`MEMBERSHIP_DROP_REASON` em `publish.py`.
- **568** = linhas que passam a **carregar o reason code** `parafiscal_institutional_hard_out`. É este o número da segunda query de medição do AC 17.
- **~532 transições de classe** (568 − 36 já OUT). Volume de `TransitionEvent` a esperar no ciclo de reconcile — não é incidente.

**Nota sobre `_assert_membership_deactivation_delta` (li o código, ~linha 237): não é um teto numérico, é uma reconciliação de completude.** Ele exige `declared == expected`: toda raiz que sai de `current` precisa viajar como uma revogação explícita com `MEMBERSHIP_DROP_REASON`; caso contrário `raise ValueError` → `PUBLICATION_REFUSED` (linha ~928-931). Portanto **68 não estoura nenhum limiar** — mas a publicação **é recusada** se o build não declarar as 68 revogações. @devops deve verificar isso no build de publicação, não só "antecipar o delta".

### D.5 — REQ-002: decisão, com a evidência que inverte a premissa do @qa

**Decisão: NÃO é redundante, mas também NÃO é a defesa que o @qa supôs. Ambos os caminhos entram no plano de deploy, com papéis corrigidos.**

Duas medições em produção mudam o quadro:

1. **`outreach_eligibility` não existe como coluna em lugar nenhum do banco de produção.** Consulta a `information_schema.columns` com `column_name='outreach_eligibility'` → **zero linhas**. O campo só existe no JSONL/manifest que o universe builder emite.
2. **O feed contínuo não lê `outreach_eligibility`.** `continuous_from_target_fit.py:110-140` faz `FROM confenge_company_sector_current s LEFT JOIN confenge_target_fit_shadow t USING (company_key) LEFT JOIN supplier_registry r ...` e filtra por `t.shadow_class = 'TARGET_CONFIRMED'`. Não há join com nenhuma tabela de universo.

Logo: `PARAFISCAL_INSTITUTIONAL → NOT_CONSTRUCTION` em `eligibility.py` **não protege o feed contínuo** — protege o caminho de ativação/planner/publish, que consome o artefato do universe builder. São **duas superfícies distintas**, não uma redundante da outra:

| Superfície | Produzida por | Defesa aplicável | Papel |
|---|---|---|---|
| `confenge_target_fit_shadow` → `continuous_from_target_fit.py` → contatos → warmbly | `reconcile` + worker | **Gate C3 em `classify_target_fit`** | **PRIMÁRIA** |
| JSONL do universe → `planner.py`/`publish.py` (campanha) | `python3 -m scripts.confenge_universe build` | `identity.py` → `eligibility.py` → `NOT_CONSTRUCTION` | Defesa em profundidade |

**A tabela acima NÃO é cobertura completa da cadeia do incidente — REQ-003 do @qa permanece ABERTO.** O @qa mediu que a raiz do SEBRAE-ES (`27080530`) tem **0 linhas** em `pncp_supplier_contracts` e está **ausente** da shadow. Confirmo a implicação: se a raiz não tem contratos, ela nunca é enfileirada pelo `reconcile` (que itera raízes de `pncp_supplier_contracts`) e nunca chega ao `classify_target_fit` — logo **nem o gate C3 nem a defesa de universo explicam como aquela conta específica chegou ao warmbly**. Este desenho previne a **classe** do erro nas duas superfícies conhecidas; **não** prova a cadeia do incidente concreto. REQ-003 exige uma terceira investigação (proveniência da conta no warmbly), que é adjacente a `story-outbound-provenance-gap-01` e deve ser explicitamente atribuída pelo @po — não a considere fechada por esta revisão.

**Achado operacional adicional que o plano de deploy precisa absorver:** `systemctl list-unit-files 'extra-*'` mostra **nenhuma unit/timer para o universe builder**. Ele é batch nacional manual (`cli.py`, subcomando `build`, sem modo incremental — só `--max-rows` como cap diagnóstico, que o próprio help marca como amostragem que não pode reivindicar população completa). Portanto o rerun **tem que ser comandado explicitamente**; não acontece sozinho. Isso reforça, e não enfraquece, a decisão de que o gate C3 é a defesa primária.

### D.6 — Risco residual identificado nesta revisão (novo, não estava mapeado)

`continuous_from_target_fit.py:122-131` tem um segundo predicado: quando `target_confirmed_only=False`, o feed seleciona por `s.sector_class IN ('CONSTRUCTION_CONFIRMED','CONSTRUCTION_PROBABLE')`, **sem olhar `shadow_class`**. Medido em produção: as 4 raízes Sistema S estão em `confenge_company_sector_current` como **`CONSTRUCTION_PROBABLE` (conf 0.4)**. Nesse ramo, o gate C3 seria contornado.

**Por que não é bloqueante agora:** ambos os call sites reais (`confenge_outreach_pipeline/pipeline.py:217` e `decision_unit_intelligence/batch_population.py:299`) passam `target_confirmed_only=True`. O default `False` só é alcançável por chamada ad-hoc.

**Decisão:** **OUT desta story** — um gate parafiscal no caminho de setor exigiria tocar `confenge_sector/classification.py` e `sector_fit.py`, ampliando o raio de uma mudança já HIGH-RISK, e mudaria `sector_classifier_sha256` (forçando recomputação de 410 mil linhas de setor). Registrar como dívida com owner e prazo (ver D.9). **@qa deve verificar o predicado nos dois call sites como parte do gate de re-review**, para que o "não é bloqueante" seja verificado e não assumido.

### D.7 — ACs propostos (texto para ratificação do @po — não editei o bloco de ACs)

Conforme `story-lifecycle.md`, o texto de AC é autoridade do @po. Proponho os quatro abaixo como **AC 21-24**, na mesma story. Somam-se aos REQ-004/005/006 do @qa, já pendentes de ratificação.

> **AC 21 — o gate alcança o caminho real.** *Given* as razões sociais e os contratos reais das 4 raízes Sistema S em `TARGET_CONFIRMED` (`03575238`, `03709814`, `03776284`, `16589137`), *when* `classify_target_fit` é executada com a projeção de `loader.load_company_input`, *then* as 4 retornam `target_fit_class == "TARGET_OUT_OF_SCOPE"` com `"parafiscal_institutional_hard_out"` em `target_fit_reason_codes`, **independentemente de `relevant_execution_contract_count`**. Teste obrigatório com fixture derivada de contratos reais (objetos podem ser abreviados; os nomes de fornecedor **não**).
>
> **AC 22 — o gate é incondicional e determinístico quanto ao nome.** *Given* uma entidade cujo `razao_social` **não** casa nenhum marcador (ex.: `"SESCRS - ADM REG RS"`, `"SEBRAEMG"`) mas cuja lista de contratos contém ao menos um `fornecedor_nome` que casa, *when* avaliada, *then* o resultado é `TARGET_OUT_OF_SCOPE`. E: *given* uma entidade parafiscal com `relevant_execution_contract_count >= 3`, *then* o resultado continua `TARGET_OUT_OF_SCOPE` (o gate não tem cláusula `n_exec == 0`).
>
> **AC 23 — fonte única e drift de classificador.** *Given* a taxonomia parafiscal vivendo em `scripts/confenge_universe/parafiscal.py`, *then* (a) `identity.py` a importa e os ACs 11-13 continuam verdes sem duplicação de lista; (b) `classifier_sha()` em `compute.py` inclui `parafiscal.py` em `inspect.getsource`; (c) teste que prova que **acrescentar um marcador altera `classifier_sha()`** — ou seja, que o `reconcile` volta a enfileirar. `store.py::sector_classifier_sha256` permanece inalterado (declarado OUT em D.2).
>
> **AC 24 — não-regressão do blast radius.** *Given* a taxonomia final, *when* aplicada às razões sociais das raízes `TARGET_CONFIRMED`, *then* nenhum nome contendo evidência de construção (`construt|construcao|engenhari|paviment|obras|edifica`) **e** sem marcador parafiscal é suprimido. Teste com fixtures nomeadas, incluindo os dois casos-fronteira medidos (`FUNDACAO DE ENSINO E ENGENHARIA DE SANTA CATARINA`, `FUNDACAO DE PESQUISA E ASSESSORAMENTO A INDUSTRIA`) declarados como **supressões esperadas**, para que a decisão fique explícita no código de teste e não implícita.

**Rebaixamento do AC 11 (também pendente de ratificação do @po):** o AC 11 permanece válido e verde, mas seu papel muda de "defesa primária contra Sistema S no outbound" para "defesa em profundidade do caminho `aggregate.py`/universe builder". A defesa primária passa a ser o AC 21.

**Correções ao AC 17 propostas ao @po** (convergentes com REQ-005/006 do @qa, e agora com uma medição melhor):

- a medição deixa de precisar de join com `supplier_registry`. Vira uma varredura de reason code na tabela que de fato governa:

```sql
-- Deve retornar ZERO linhas após a reclassificação:
SELECT cnpj_raiz, shadow_class
  FROM confenge_target_fit_shadow
 WHERE reason_codes::text LIKE '%parafiscal_institutional_hard_out%'
   AND shadow_class = 'TARGET_CONFIRMED';

-- Contagem esperada de linhas carregando o reason code (referência medida hoje: 568):
SELECT count(*) FROM confenge_target_fit_shadow
 WHERE reason_codes::text LIKE '%parafiscal_institutional_hard_out%';
```

**Predicado verificado em produção antes de entrar nesta story** (o AC 17 anterior já foi reprovado por SQL não testado — não repito): `reason_codes` é **`jsonb`**; `reason_codes::text LIKE '%multi_execution_contracts_triangulation%'` devolve **5.614** linhas hoje (código sabidamente presente) e `LIKE '%parafiscal_institutional_hard_out%'` devolve **0** (código ainda inexistente). O predicado funciona e a linha de base é zero.

- o denominador correto nesta camada é **4 raízes Sistema S em `TARGET_CONFIRMED`** (o "14" é do `outreach_accounts` do warmbly, outra camada). Alvo: **4 → 0**.
- **valores esperados, medidos, não estimados:** `TARGET_CONFIRMED` cai **68** (8.667 → ~8.599); o reason code aparece em **568** linhas; ~**532** transições de classe. Ver a tabela completa em D.4.

### D.8 — Plano de deploy corrigido (substitui a seção "Task 8.0 — Achado" no que conflitar)

**Ressalva SHADOW invertida — confirmo o @qa.** Produção está em `TARGET_FIT_ASYNC_MODE=SHADOW` (verificado no unit file). `confenge_target_fit_shadow` tem 410.298 linhas e é a tabela que o feed lê. **O reconcile em SHADOW opera na tabela certa.** O texto anterior da story desorientaria o deploy e deve ser corrigido pelo @po.

Ordem, após merge do PR 1 e criação do release:

```bash
cd /opt/extra-consultoria-releases/{novo_commit_hash}/

# 1) Sweep diagnóstico (proxy de dry-run — reconcile não tem --dry-run)
.venv/bin/python -m scripts.confenge_target_fit reconcile --max-enqueue 50

# 2) Sweep nacional + drenagem controlada
.venv/bin/python -m scripts.confenge_target_fit reconcile --drain-worker --max-worker-batches 20

# 3) Worker drena o restante
systemctl restart extra-confenge-target-fit-worker.service

# 4) NOVO (REQ-002) — universe builder: batch nacional MANUAL, sem timer no systemd.
#    Sem incremental; --max-rows é apenas cap diagnóstico e invalida a alegação de população completa.
.venv/bin/python -m scripts.confenge_universe build \
    --out /var/lib/extra-consultoria/confenge-universe/{data} \
    --result-json /var/lib/extra-consultoria/confenge-universe/{data}/result.json
```

**Asserção pós-deploy em CADA superfície (as duas são obrigatórias):**

- **Superfície target-fit (primária):** os dois SELECTs do D.7 — zero `TARGET_CONFIRMED` carregando `parafiscal_institutional_hard_out`, e ~568 linhas carregando o código no total.
- **Publicação:** o build de publicação precisa declarar as **68** revogações com `MEMBERSHIP_DROP_REASON`, ou `_assert_membership_deactivation_delta` recusa a publicação (`PUBLICATION_REFUSED`). Não é limiar — é completude.
- **Superfície universe (profundidade):** no JSONL emitido, as 4 raízes Sistema S têm `outreach_eligibility == "NOT_CONSTRUCTION"` e `in_universe == false`, com `reason` iniciando em `parafiscal_institutional_name:`.

**Estimativa de runtime do passo 4 pendente** — é varredura nacional de `pncp_supplier_contracts`. @devops deve cronometrar o passo 1 antes de agendar o passo 4. Não é bloqueante para o passo 1-3 (que já removem a exposição do feed).

### D.9 — Dívidas registradas nesta revisão

| ID | Descrição | Owner | Prazo |
|---|---|---|---|
| `MNT-001` | Guard `\bbanco\b` em `identity.py:210` é código morto (`normalize_name` devolve MAIÚSCULAS, regex sem `re.IGNORECASE`). Achado do @dev, confirmado pelo @qa. | @po → backlog via @sm | no fechamento desta story |
| `MNT-003` | **NOVO.** Ramo `target_confirmed_only=False` de `continuous_from_target_fit.py` seleciona por `sector_class` e contorna o gate parafiscal; as 4 raízes Sistema S são `CONSTRUCTION_PROBABLE` em `confenge_company_sector_current`. Hoje não alcançável pelos call sites reais. | @po → backlog via @sm | no fechamento desta story |
| `MNT-004` | **NOVO.** `loader._load_contracts` define `razao_social` a partir de query sem `ORDER BY` → valor não determinístico entre execuções, o que também afeta o `input_fingerprint` (`fingerprint.py:128` normaliza `razao`). Mitigado nesta story pelo C4 (o gate não depende dele), mas a instabilidade de fingerprint permanece. | @po → backlog via @sm | no fechamento desta story |

### D.10 — Story ou nova story?

**MESMA story.** Justificativa: (i) mesma causa raiz e mesmo incidente — o falso positivo Sistema S; (ii) a story já está `InProgress` por decisão do @qa e isto é a **iteração 2 do QA loop**, o fluxo previsto para exatamente esta situação; (iii) o Estado-alvo declarado ("população Sistema S em `TARGET_CONFIRMED` cai a 0") **nunca foi atingido** — abrir story nova permitiria fechar esta com o objetivo declarado não cumprido, que é o antipadrão que este próprio incidente expõe; (iv) o diff adicional é pequeno e concentrado (1 arquivo novo, 3 editados), reaproveitando integralmente a taxonomia já implementada e ratificada. Uma story nova só se justificaria se a taxonomia precisasse ser redesenhada — não precisa; ela só precisa alcançar o caminho certo.

### D.11 — Handoff para o @dev (iteração 2)

Escopo estritamente delimitado. **Não reabrir** nada já verde (ACs 1-16, 18, 19 foram verificados independentemente pelo @qa).

- [x] **T9.1** — Criar `scripts/confenge_universe/parafiscal.py` com `PARAFISCAL_INSTITUTIONAL_MARKERS` + `match_parafiscal_institutional`. Conteúdo movido de `identity.py`, **sem alterar a taxonomia** (as fundações públicas genéricas continuam fora — decisão do @dev ratificada pelo @qa em "Colisão léxica 2.1").
- [x] **T9.2** — `identity.py` importa de `parafiscal.py`; `_looks_like_parafiscal_institutional` vira wrapper fino. ACs 11-13 devem continuar verdes sem alteração de teste.
- [x] **T9.3** — Gate C3 em `classify_target_fit`, após o loop de contratos, antes de todo path de confirmação, com a superfície de nome do C4 (AC 21, 22).
- [x] **T9.4** — `classifier_sha()` em `compute.py` inclui `parafiscal.py` (AC 23). **Comunicar ao @devops:** rebind do PR 2 passa de 3 para 4 caminhos congelados.
- [x] **T9.5** — Testes dos ACs 21-24, incluindo os casos-fronteira nomeados do D.4.
- [x] **T9.6** — Reexecutar os gates já verdes (holdout n=40, corpus n=1076 objeto a objeto, `test_anti_overfitting`, suíte completa) e provar **zero delta** — o gate é ortogonal à camada de texto e não deve mover nenhum desses números.
- [x] **T9.7** — Atualizar a seção "Task 8.0 — Achado" com o plano do D.8 (incluir passo 4, corrigir a ressalva SHADOW, trocar o SQL de medição).
- [x] **T9.8** — Registrar `MNT-001`, `MNT-003`, `MNT-004` e declarar/reverter os 2 `MEMORY.md` (MNT-002).

**Escalonamento ao @po (REQ-008), que o @dev deve fazer e eu já enderecei aqui:** a situação **não** é o Plano B da Decisão nº 1. O Plano B pressupunha que *nenhum mecanismo reprocessa linhas confirmadas*. O mecanismo (`reconcile` por drift de `classifier_sha`/versão) **existe e funciona** — o que faltava era o classificador produzir resultado diferente para essas linhas. Com o gate C3 isso passa a acontecer, medido em D.3. Portanto a contenção `do_not_contact` continua sendo mitigação temporária, e **não** vira controle primário permanente. O @po decide se ratifica esta leitura.

**Não implementei nada.** Nenhum arquivo de código foi tocado por mim; a validação foi feita em worktree descartável e simulação externa ao módulo.

---

## Ratificação do @po — Architect Revision (iteração 2)

**Autor:** Pax (@po) · **Data:** 2026-09-01 · **Status da story:** permanece `InProgress` · **Veredito: LIBERADA para o @dev**

Contexto: a autoridade de texto de AC é do @po (`story-lifecycle.md`). O @architect e o @qa fizeram o correto ao **propor** e não editar. Esta seção exerce essa autoridade. Onde eu discordo, digo onde e por quê; onde ratifico, ratifico sem reescrever o que já está bom.

### Ratificação 1 — ACs 21-24 propostos: 3 ratificados, 1 reescrito, 1 acrescentado

**AC 21 — RATIFICADO como proposto.** É o AC que faltava na iteração 1 e o único que endereça diretamente o REQ-001. A cláusula "independentemente de `relevant_execution_contract_count`" é o que impede a repetição exata do FAIL — sem ela, o AC seria satisfeito por SEBRAE/MG (n_exec=0) e falharia nas 3 raízes que sobreviveram. Acrescentei uma exigência menor: o `n_exec` verdadeiro (6/3/3/0) deve permanecer **auditável no resultado**, não zerado pelo gate. Um supressor que apaga a evidência que o motivou não é contestável, e esta é uma decisão de política de ICP que precisa poder ser revista.

**AC 22 — RATIFICADO como proposto.** A superfície de nome do C4 é a parte mais importante desta revisão inteira e é a que separa "corrigi o desenho" de "corrigi o desenho e verifiquei a premissa". O @architect mediu 235 variantes de `fornecedor_nome` nas 4 raízes, 15 delas sem casamento, e recusou-se a depender do sorteio não determinístico do `loader`. Ratifico explicitamente essa recusa: **desenhar sobre não-determinismo é exatamente o defeito que produziu o FAIL da iteração 1**, e é sadio ver o mesmo agente que errou aplicando o critério de forma mais dura na segunda vez.

**AC 23 — RATIFICADO como proposto**, com uma correção material de fato na alínea que toca o freeze — ver Ratificação 6. O item (c) — provar que acrescentar um marcador altera `classifier_sha()` — é o melhor AC do conjunto: transforma "obsolescência silenciosa" de risco narrado em predicado testável.

**AC 24 — NÃO RATIFICADO COMO ESCRITO. REESCRITO pelo @po.** Motivo, com precisão:

> O texto proposto exigia que "nenhum nome contendo evidência de construção **e sem marcador parafiscal** seja suprimido". Mas o gate C3 suprime **se e somente se** um marcador casa — o marcador é o predicado único. A condição "sem marcador parafiscal ⇒ não suprimido" é verdadeira **por construção**. É um teste que não pode falhar, e um teste que não pode falhar dá a sensação de cobertura sem entregar cobertura — numa story cuja falha anterior foi exatamente cobertura ilusória (ACs verdes em laboratório, caminho de produção intocado).

Além disso, o texto media o blast radius sobre **`razão sociais`**, superfície mais estreita do que a que o gate usa (C4: `razao_social` + `nome_fantasia` + todo `fornecedor_nome`). Medir sobre superfície menor do que a de decisão **subestima o raio por construção** — o mesmo erro de superfície que o C4 existe para evitar.

O AC 24 reescrito inverte a lógica para o caso discriminante: nomes que carregam evidência de construção **e** transitam perto da taxonomia devem ser provados **não suprimidos** — em `classify_target_fit`, não em `resolve_identity`. `FUNDACAO ENGENHARIA E CONSTRUCOES LTDA` hoje só está protegida no AC 12, que roda numa camada que o outbound não consulta. É o único ponto onde esta taxonomia poderia derrubar um alvo comercial legítimo, e ele está sem teste na camada que importa. Também transformei FEESC/FUPAI em supressões **declaradas** e fixei as 68 como referência.

**AC 25 — ACRESCENTADO pelo @po.** O achado de `_assert_membership_deactivation_delta` em D.4/D.8 é um modo de falha novo, medido, e **bloqueante da publicação** (`PUBLICATION_REFUSED`), e estava vivendo apenas como prosa numa seção de arquitetura. Prosa não é verificável por gate. Se as 68 revogações não viajarem declaradas, o @devops trava no build e essa falha vai parecer incidente novo. Vira AC.

### Ratificação 2 — Rebaixamento do AC 11: RATIFICADO. A asserção não muda; o papel muda.

O AC 11 continua **verificando exatamente a mesma coisa** e continua verde: `resolve_identity` devolve `valid=False` + `PARAFISCAL_INSTITUTIONAL` para as razões sociais reais (o @qa testou com os 4 CNPJs de produção). Não há motivo para mexer no texto da asserção.

O que muda é o **papel**, e isso precisa estar escrito para não se repetir: o AC 11 deixou de ser a defesa primária porque `classify_target_fit` nunca consulta `resolve_identity` — o único call site é `aggregate.py:336`. Registrei o rebaixamento como nota no próprio AC 11 e apontei a defesa primária para o AC 21.

Deliberadamente **não** repeti no AC 11 a exigência de "sem duplicação de lista": ela já é do AC 23(a). Duplicar requisito entre ACs cria o risco de os dois divergirem numa edição futura, e esta story já sofreu com texto desatualizado o bastante.

**Nota metodológica que vale mais que o rebaixamento em si:** a lição não é "a exclusão estava no arquivo errado". É que **nenhum AC da iteração 1 exigia que a defesa alcançasse o caminho de produção** — todos eram verificáveis em laboratório. Foi por isso que 19 ACs verdes conviveram com o objetivo da story não atingido. O AC 21 existe para tornar isso estruturalmente impossível daqui em diante.

### Ratificação 3 — Os dois achados operacionais: ambos RATIFICADOS, com uma correção de premissa

**(a) `outreach_eligibility` não existe como coluna no banco.** RATIFICADO por medição (`information_schema.columns` → zero linhas; feed em `continuous_from_target_fit.py:110-140` filtra por `t.shadow_class` sem join de universo).

**Isso invalida uma suposição anterior? Sim — e não a que se poderia imaginar.** Não invalida o mapeamento `PARAFISCAL_INSTITUTIONAL → NOT_CONSTRUCTION` do `eligibility.py`, que continua correto e útil. **Inverte a premissa do REQ-002 sobre qual superfície ele protege.** O @qa escreveu que a via de `eligibility.py` era "a única defesa que funciona" e que o plano de deploy a omitia. A medição mostra o contrário: essa via **não** protege o feed contínuo — protege o caminho de ativação/`planner.py`/`publish.py`, que consome o artefato JSONL do universe builder. São **duas superfícies distintas**, nenhuma redundante da outra, e a defesa do feed (a superfície do incidente) só existe com o gate do AC 21.

Correção de texto aplicada: o Estado-alvo agora nomeia as duas superfícies com seus papéis. **Não editei a seção QA Results** — por `story-lifecycle.md` ela é do @qa. O registro da inversão fica aqui, na minha seção, com a evidência.

**(b) Não há timer systemd para o universe builder.** RATIFICADO — `systemctl list-unit-files 'extra-*'` não mostra unit nem timer; é batch nacional manual, sem modo incremental (`--max-rows` é cap diagnóstico e invalida a alegação de população completa).

**Sim, o plano de deploy precisa dizer isso explicitamente**, e é uma omissão perigosa por um motivo específico: um plano que lista "rerun do universe pipeline" sem marcar que é **manual e não agendado** convida ao raciocínio "o batch roda de noite, vai se resolver sozinho". Não roda. A defesa em profundidade permaneceria desativada **indefinidamente** e ninguém seria alertado — porque não há timer para falhar. O passo 4 do D.8 já está escrito nesses termos (com a advertência de `--max-rows` e o pedido de cronometragem ao @devops) e eu o ratifico como está. Reforço para o @devops: **os passos 1-3 removem a exposição do feed; o passo 4 não é opcional, é a segunda superfície, e não acontece sozinho.**

### Ratificação 4 — REQ-003 (SEBRAE-ES sem contratos, ausente da shadow): NÃO bloqueia a implementação; VIRA GATE DE FECHAMENTO

**Decisão: as duas coisas, e a distinção importa.**

**Não bloqueia a iteração 2 do @dev.** O gate do AC 21 está empiricamente validado, é ortogonal ao REQ-003 e remove exposição real e medida (68 raízes, 4 delas Sistema S confirmadas, no caminho que alimenta o warmbly). Segurar essa correção enquanto se investiga uma terceira via **aumenta** o risco em vez de reduzi-lo — a janela de novo envio comercial continua aberta enquanto o fix não é publicado. Bloquear implementação validada por investigação pendente seria trocar risco medido por conforto processual.

**Mas bloqueia o fechamento.** A Story desta story diz, em primeira linha, que o pipeline "**nunca mais** dispare e-mail comercial real" para essas entidades. Fechar com duas superfícies corrigidas e a via do incidente concreto inexplicada seria **declarar uma garantia mais forte do que a evidência sustenta** — que é precisamente o antipadrão que este incidente expôs e que o @architect nomeia em D.10(iii). Não vou fechar assim.

**Hipótese mais provável, e a pergunta que a discrimina.** Uma raiz com **0 contratos em `pncp_supplier_contracts`** e **ausente da shadow** casa com o perfil da coorte já conhecida: as **1.448 contas `TARGET_CONFIRMED` com `contracts_json` vazio** no warmbly — justamente o escopo de `story-outbound-provenance-gap-01` (Decisão nº 4). Se for isso, não há terceira via nova: há a via **já conhecida e já declarada OUT**, e o erro foi meu ao classificá-la como "disponibilidade/degradação de evidência" quando ela também é um **caminho de envio comercial sem lastro de contrato**. Pergunta discriminante, respondível com um SELECT por quem tiver acesso de produção:

> **A raiz `27080530` pertence à coorte das 1.448 contas `TARGET_CONFIRMED` com `contracts_json` vazio no warmbly?**

- **Se SIM:** REQ-003 é absorvido por `story-outbound-provenance-gap-01`, cujo escopo passa a **nomear a raiz do incidente explicitamente** e cujo perfil de risco é **reclassificado para incluir precisão/dano externo**, não só disponibilidade.
- **Se NÃO:** existe uma terceira via de entrada não mapeada e ela exige draft próprio antes do fechamento desta story.
- **Terceira possibilidade, que também precisa ser descartada:** o registro do SEBRAE-ES pode ter **mudado de estado desde a auditoria original** — a contenção manual `do_not_contact=true` já foi aplicada nele. Se a ausência atual for consequência da contenção e não do estado original, a auditoria mede um sistema já alterado, e a conclusão "0 contratos" não descreve o momento do envio. Quem responder a pergunta acima deve verificar isso também.

Gate registrado na Definition of Done. **Alternativa aceitável e honesta**, se a investigação não convergir: estreitar por escrito o Estado-alvo para "as duas superfícies mapeadas" e registrar que a cadeia do incidente permanece inexplicada. O que **não** é aceitável é fechar mantendo a redação forte sem a prova.

### Ratificação 5 — MNT-003 e MNT-004: RATIFICADAS, com uma correção de forma

Ambas estão bem formadas (ID, descrição com localização de código, owner, prazo) e são dívidas reais, não observações. Ratifico as duas, junto com `MNT-001` (guard `\bbanco\b` morto) e `MNT-002` (2 `MEMORY.md` fora do File List) que já estavam pendentes.

**Correção de forma — "estão no backlog corretamente"? Não exatamente, e é bom saber por quê.** Este repositório **não tem backlog central**: IDs `MNT-*` são locais de story e o registro durável de follow-up é um draft em `docs/stories/`. Portanto D.9 registra as dívidas **na story**, o que é correto, mas o prazo "no fechamento desta story" só se materializa se o fechamento verificar. Adicionei a criação dessas dívidas como item explícito da Definition of Done — mesmo padrão da Decisão nº 4, que existe pelo mesmo motivo (a Decisão nº 4 tem gate e sobreviveu; o @qa achou o REQ-007 justamente porque havia gate para checar).

**`MNT-003` carrega uma AÇÃO, não só um registro — e por isso não pode ficar só em D.9.** O @architect declara que o ramo `target_confirmed_only=False` "não é alcançável hoje" e pede ao @qa que **verifique** os dois call sites. Isso é a diferença entre dívida e bloqueante latente: se qualquer um dos call sites passar `False`, o gate do AC 21 é contornado por `sector_class` e as 4 raízes voltam ao feed — e `MNT-003` deixa de ser dívida e vira bloqueante **desta** story. Enterrada numa tabela de dívidas no fim do documento, essa verificação seria perdida. Promovi-a a item da seção **Testing** e a item da **Definition of Done**, explicitamente atribuída ao @qa no re-review. "Não é alcançável hoje" é exatamente o tipo de afirmação não verificada que produziu o FAIL da iteração 1.

**`MNT-004` (não determinismo de `razao_social`)** ratificada com a observação de que ela é **mitigada, não resolvida**, por esta story: o C4 torna o gate independente do sorteio do loader, mas a instabilidade de `input_fingerprint` (`fingerprint.py:128`) permanece e pode causar reprocessamento espúrio ou, pior, ausência de reprocessamento devido. Vale o `ORDER BY` na story de dívida.

### Ratificação 6 — Custo do `classifier_sha()`: ACEITO, sem aprovação adicional. Mas o número está errado — são 5, não 4.

**Aceito, e não requer aprovação adicional.** Motivos: (i) o custo é uma linha de manifesto num PR de re-freeze **que esta story já exige de qualquer forma** (AC 20) — não é um PR novo nem um processo novo; (ii) o benefício é estrutural: sem C5, acrescentar um marcador parafiscal no futuro produziria **zero drift** e o `reconcile` não reenfileiraria nada, reintroduzindo obsolescência silenciosa — que é a classe de bug que esta story existe para matar; (iii) a autorização humana explícita que este repositório exige está atrelada a **escrita em dados de produção**, não a rebind de manifesto de freeze. Nada em `compute.py` toca dados.

**Correção material ao D.2/C1 — verificada, não inferida.** O @architect afirma que `parafiscal.py` é "arquivo NOVO, **portanto não congelado**". **Isso é falso.** `discover_frozen_input_paths` (`scripts/ops/confenge_frozen_inputs.py:278-318`) faz **fechamento transitivo de imports locais** a partir dos seeds — a própria docstring diz "expands transitive local imports under `scripts/`". Como `parafiscal.py` será importado por `target_fit.py` **e** por `compute.py`, ambos congelados e ambos seeds, ele entra no conjunto congelado automaticamente.

**Verificação empírica que eu fiz antes de escrever o número** (cópia descartável da árvore `scripts/`, sem tocar a working tree do @dev): criei `parafiscal.py` e os dois imports, rodei `discover_frozen_input_paths` e ela retornou `scripts/confenge_universe/parafiscal.py` no conjunto. Não editei nenhum arquivo rastreado para descobrir isso.

**Portanto o PR 2 é: 4 rebinds (`contract_relevance.py`, `pipeline.py`, `target_fit.py`, `compute.py`) + 1 ENTRADA NOVA (`parafiscal.py`) = 5 caminhos.** `store.py` continua MATCH e OUT. AC 20(a) corrigido — pela terceira vez, o que por si só é um sinal: **este é o item que mais errou nesta story, e o padrão do erro é sempre o mesmo — afirmar escopo de freeze sem rodar a discovery.** @devops: um rebind escopado para 4 deixa os gates vermelhos, e a inserção de entrada nova pode ter caminho diferente do rebind no seu procedimento — verifique antes de abrir o PR 2.

### Escalonamento REQ-008 — respondido

O @architect está certo e eu ratifico: **não é o Plano B da Decisão nº 1.** O Plano B pressupunha que *nenhum mecanismo reprocessa linhas confirmadas*. O `reconcile` reprocessa (sem filtro de classe, `reconcile.py:136-172`) e dispara por drift de `classifier_sha`/`TARGET_FIT_VERSION`; o que faltava não era o mecanismo, era **o classificador produzir resultado diferente** para aquelas linhas — o que o gate C3 passa a fazer, medido em D.3. Consequência: a contenção `do_not_contact=true` **permanece mitigação temporária** e **não** vira controle primário permanente. O perfil de risco residual não muda.

### Liberação

**LIBERADA para o @dev — iteração 2 do QA loop.** Escopo: T9.1 a T9.8 do D.11, com as correções desta seção (AC 24 reescrito, AC 25 novo, AC 20(a) = 5 caminhos, `parafiscal.py` **é** congelado). Status permanece `InProgress`. Nada mais permanece em aberto para o @dev — REQ-003 é gate de fechamento do @po, não pré-requisito de implementação.

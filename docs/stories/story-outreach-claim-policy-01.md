# Story: Política determinística de evidência contratual no outbound (CLAIM_POLICY) — eliminar histórico apresentado como presente

## Status

**InReview**

## Risk Level

**HIGH-RISK** — *escalado pelo @po em 2026-09-01 (decisão explícita solicitada pelo @sm na versão 0.1.0).*

Racional da escalada, com evidência coletada na validação (não hipótese):

1. **Dois dos quatro arquivos de integração já estão dentro do conjunto congelado da campanha.** Execução de `scripts.ops.confenge_frozen_inputs.discover_frozen_input_paths(Path("."))` em HEAD retorna 162 caminhos, incluindo `scripts/confenge_account_intelligence/message_spine.py` e `scripts/confenge_contact_resolution/send_readiness.py`. (`facts.py` e `normalize.py` **não** estão.) Logo, esta story **edita inputs congelados de campanha**, o que aciona o ritual de 2 PRs (código → artifact-only re-freeze, sem squash) independentemente do pacote novo — isto é mudança sistêmica/operacional, não uma correção localizada.
2. **`send_readiness.py` governa `EMAIL_SEND_READY`**, que alimenta envio comercial real a prospects. Um defeito aqui chega ao lead.

O custo da escalada é baixo: `quality_gate: "@architect"` já estava atribuído. O que a escalada acrescenta é obrigatório e não opcional: revisão de @architect **antes** da implementação do contrato de API do módulo puro, QA aprofundado (não apenas AC-tracing), e gate sistêmico antes da publicação.

A avaliação original do @sm ("superfície de mudança não justifica HIGH-RISK por si só") era correta **dado o que o @sm sabia**; a evidência de pertencimento ao freeze não constava da story e inverte a conclusão.

## Executor Assignment

executor: "@dev"
quality_gate: "@architect"
quality_gate_tools: ["pytest", "ruff", "mypy"]

## Story

**Como** founder responsável pela precisão factual do outbound B2G da CONFENGE,
**quero** uma política única e determinística (`CLAIM_POLICY`) que decida como evidência contratual pode aparecer em copy/e-mail — em vez de heurísticas espalhadas em `facts.py`, `normalize.py`, `message_spine.py` e `send_readiness.py`,
**para que** nenhum contrato encerrado, desconhecido ou não comprovado seja citado no tempo presente, sem tornar os e-mails genéricos (histórico continua sendo um why_you legítimo).

## Contexto e autoridade (auditoria de HEAD, feita nesta sessão)

Bug confirmado por leitura direta do código, não por hipótese:

- **`scripts/confenge_account_intelligence/facts.py::why_now`** (linhas 302-307): o primeiro `pain_check` da lista, `"addendum"`, dispara sempre que `has_addendum` ou `addendum_count > 0` é verdadeiro em **qualquer** contrato do bag, produzindo o texto fixo `"Aditivos/alterações observados em contrato público recente ou ativo."` — **sem checar lifecycle do contrato**. Um contrato `COMPLETED`/`TERMINATED` com aditivo antigo produz o mesmo texto que um contrato `ACTIVE_PROVEN`. Este é o bug relatado: histórico apresentado como presente.
- **`scripts/confenge_account_intelligence/message_spine.py::_extract_temporal_event`** (linhas ~228-265) é um **segundo site independente do mesmo bug de classe**, que não passa por `facts.py`: qualquer `publication_date` ou `start_date` com `age_days <= 180` retorna força `"STRONG"` com texto presente-ish (`"Evento contratual público recente: ..."`), só com base em data — sem lifecycle. E o bloco de `end_date` (linhas ~245-254) retorna `"STRONG"`/`"janela temporal verificável"` para qualquer contrato com término entre -30 e +180 dias, **incluindo um contrato que terminou há 20 dias** (i.e., já encerrado). Os dois pontos violam a Regra 4 (crawl/publicação recente ≠ execução atual) e a Regra 3 (`COMPLETED` nunca presente). **Esta story precisa cobrir os dois sites, não só `facts.py`, para satisfazer os casos red-team "UNKNOWN publicado ontem" e "aditivo de contrato encerrado".**
- **`scripts/confenge_account_intelligence/normalize.py`** (linhas 188-213) já preserva `start_date`, `end_date`, `publication_date`, `age_days`, `has_addendum`, `addendum_count` por contrato — mas **não emite nenhum campo de lifecycle** (`ACTIVE`/`COMPLETED`/`TERMINATED`/etc). A política precisa de um mecanismo de derivação com precedência clara (ver Dev Notes).
- **`scripts/confenge_account_intelligence/message_spine.py`** já define `MessageSpine` (dataclass frozen, linha 437), `extract_contract_hook(bag)` (linha 83, **único call site**: linha 486, dentro de `build_message_spine`), `is_hollow_fact`, e o conceito `why_now_strength` (`STRONG`/`MODERATE`/`WEAK`) que hoje já impede `MessageSpine.complete=True` quando `why_now_strength == "WEAK"` (linhas 501-503, 524). Esse gate de completude **já existe e não pode ser enfraquecido** por esta story.
- **`scripts/contracts_truth.py` já é a autoridade de lifecycle deste repositório** *(achado da validação @po — ausente da versão 0.1.0 desta story)*. Ele define exatamente o vocabulário que esta story pretendia criar: `ACTIVE_PROVEN`, `COMPLETED`, `CANCELLED`, `TERMINATED`, `SUSPENDED`, `UNKNOWN` (constantes, linhas 59-65) agrupados em `ACTIVITY_STATES` (linha 70); a dataclass frozen `ContractActivity` (linha 115) com `is_active_proven`; `classify_contract_activity(...)` (linha 528), que **já implementa a exata precedência e a regra demote-only** pedidas na Task 2 — token de status explícito > janela de vigência > `UNKNOWN`, com `is_active_default` explicitamente ignorado ("`is_active=TRUE` defaults are ignored"), token ativo com `end < ref` → `COMPLETED`, token ativo sem vigência → `UNKNOWN`; os conjuntos de tokens PT-BR (`_ACTIVE_TOKENS`, `_COMPLETED_TOKENS`, `_CANCELLED_TOKENS`, `_TERMINATED_TOKENS`, `_SUSPENDED_TOKENS`, linhas 80-95); e `ACTIVITY_RULE_VERSION`. Já é consumido por `scripts/crawl/contracts_crawler.py`, `run_contracts_incremental.py`, `population_convergence.py`, `ops/pncp_contract_freshness.py` e testado em `tests/test_contract_activity_and_quality.py`. **Criar um `LifecycleState` paralelo produziria duas taxonomias divergentes para o mesmo domínio no mesmo repositório**, com risco de drift entre o rótulo que o crawler carimba (`stamp_contract_truth_labels`) e o rótulo que o outbound deriva. Ver AC 31-33 e Dev Notes.
- **`scripts/confenge_contact_resolution/send_readiness.py`** (1518 linhas) já define `CopyContextResult`, `EmailSendReadyResult` (ambos `@dataclass(frozen=True)`, linhas 309-366) e `evaluate_copy_context_ready` (linha 839), que hoje já rejeita `why_now_strength == WEAK` (linhas 927-931) e textos hollow/genéricos. **Não existe hoje nenhum conceito de `lifecycle_state` nem `FACTUAL_CLAIM_SAFE`** neste arquivo — é integração nova, não refatoração de algo existente.

### Restrição de invariante (resolve contradição potencial)

`MessageSpine.complete` já é `False` sempre que `why_now_strength == "WEAK"` (message_spine.py:501-503, 524) e `evaluate_copy_context_ready` já rejeita `why_now` fraco/genérico (send_readiness.py:927-931). "HISTORICAL compatível passa" **não pode** significar "histórico vira `EMAIL_SEND_READY`" — isso enfraqueceria um gate de segurança existente e violaria "integração mínima, não refatorar". Interpretação correta, e obrigatória: **`FACTUAL_CLAIM_SAFE` é condição necessária, nunca suficiente — o novo gate só pode subtrair send-readiness, nunca adicionar.** Nenhum caso que hoje não é `EMAIL_SEND_READY` pode se tornar `EMAIL_SEND_READY` só por causa desta mudança (AC 27). Histórico continua servindo como `why_you` (Regra 1) — isso é elegibilidade de **claim**, não completude de spine nem send-readiness.

## Scope

**IN:**

- **Módulo novo e puro** `scripts/confenge_claim_policy/` (sem I/O, sem DB, sem rede, sem `date.today()`/wall clock interno — `evaluated_as_of` é sempre injetado pelo chamador) implementando:
  - `OUTREACH_CONTRACT_RELEVANCE` / `CLAIM_POLICY`: função pura que recebe um candidato de claim (contract_id, lifecycle_state ou dados brutos suficientes para derivá-lo, `evidence_ids`, **`has_hollow_fact: bool` já decidido pelo chamador — o módulo puro não inspeciona texto (AC 23b)**, propósito) + `evaluated_as_of` e retorna o schema canônico abaixo.
  - Schema de saída (dataclass frozen): `outreach_use_class` (`CURRENT_ACTIONABLE | RECENT_RETROSPECTIVE | HISTORICAL_CONTEXT | DO_NOT_CITE`), `claim_mode` (`CURRENT_CONTRACT | HISTORICAL_CONTRACT | NONE`), `why_you_eligible: bool`, `why_now_eligible: bool`, `allowed_tense` (`PRESENT_CONFIRMED | NEUTRAL_FACTUAL | PAST_ONLY | NONE`), `requires_current_authority: bool`, `contract_id`, `evidence_ids`, `lifecycle_state`, `evaluated_as_of`, `reason_codes`, `copy_hash` (SHA256 do corpo final exato — recebido como string pelo chamador; o módulo puro não descobre corpo nenhum).
  - **Reuso obrigatório de `scripts/contracts_truth.py`** como fonte única do vocabulário e da derivação de lifecycle — o módulo novo **não define enum/literal de lifecycle próprio**. Ver AC 31-33 e Dev Notes ("Reuso de `contracts_truth.py`").
  - **[CORREÇÃO @po — dependência circular na v0.1.0]** A v0.1.0 pedia, simultaneamente, que `message_spine.py` importasse `confenge_claim_policy` (para consultar a política) **e** que `confenge_claim_policy.extract_contract_hook_by_purpose` fosse "wrapper/extensão sobre `message_spine.extract_contract_hook`" (Task 1) — isto é um **import circular**, não implementável. Resolução normativa, obrigatória: **a seleção de hook fica em `message_spine.py`**, onde a lógica de leitura do `bag` já vive; `scripts/confenge_claim_policy/` **nunca importa** `message_spine`, `facts`, `normalize` ou `send_readiness` (dependência estritamente unidirecional: integração → política). Concretamente:
    - `message_spine.extract_contract_hook(bag, *, purpose="why_you")` — o parâmetro `purpose` é adicionado **à função existente** (message_spine.py:83), com default que preserva byte-a-byte o comportamento atual (único call site hoje: message_spine.py:486). Não existe função nova chamada `extract_contract_hook_by_purpose` no módulo puro.
    - `why_you` pode selecionar o maior/mais forte contrato histórico; `why_now` só pode selecionar candidato `CURRENT_ACTIONABLE` — a decisão de elegibilidade vem de `confenge_claim_policy`, a seleção sobre o `bag` fica em `message_spine`.
  - Função de seleção de mensagem (`select_message_claims` ou equivalente) que recebe o conjunto de candidatos avaliados e aplica a regra "máximo 1 claim CURRENT por mensagem" — fail-closed/rewrite se houver mais de um. O módulo puro não tem visão de "mensagem"; a fronteira é explícita: quem chama monta a lista de candidatos, a função decide.
- **Integração mínima e cirúrgica** (sem refatorar) em:
  - `normalize.py`: preservar/derivar `lifecycle_state` por contrato (novo campo no dict de contrato normalizado), com precedência de derivação e regra "demote-only" (ver Dev Notes).
  - `facts.py`: `why_now` passa a consultar `CLAIM_POLICY` para decidir o texto/tempo verbal do pain-check `"addendum"` em vez da heurística atual (linhas 302-307) — mantendo a estrutura de `pain_checks` e o restante da função intactos.
  - `message_spine.py`: `_extract_temporal_event` (linhas ~153-281) e `build_message_spine` passam a consumir `claim_mode`/`allowed_tense`/`outreach_use_class` da política ao decidir `why_now_strength` e o texto de `why_now`; `extract_contract_hook` ganha o parâmetro `purpose` (acima) mantendo compatibilidade.
  - `send_readiness.py`: novo estado `FACTUAL_CLAIM_SAFE` — `HISTORICAL` compatível (`outreach_use_class in {RECENT_RETROSPECTIVE, HISTORICAL_CONTEXT}` com `allowed_tense in {NEUTRAL_FACTUAL, PAST_ONLY}`) passa a condição necessária satisfeita; `CURRENT` sem autoridade contemporânea verificável (`requires_current_authority=True` sem `why_now_eligible=True`) não pode ser `EMAIL_SEND_READY` citando presente — deve ser rebaixado para histórico seguro (se elegível) ou ficar pendente. **Nunca eleva** send-readiness (ver invariante de monotonicidade acima, AC 27).
- Verificação de code-freeze de campanha para o pacote novo (ver AC 30) antes de considerar a story pronta para push.

**OUT:**

- Migrations, feed-cycle, publication pipeline, Warmbly — nenhum arquivo desses domínios é tocado.
- Qualquer refatoração não relacionada nos 4 arquivos de integração (ex.: não mexer em `portfolio_summary`, na lógica de `signals`, na parte de `epistemic_item`/`build_epistemic_layers` que não seja o pain-check `"addendum"`, nem em `evaluate_email_send_ready`/`classify_target_fit_send_tier` além do necessário para introduzir `FACTUAL_CLAIM_SAFE`).
- Contenção operacional em produção (não há incidente de produção conhecido para este bug — é correção preventiva de semântica).
- Introdução de estados de lifecycle além dos já definidos em `scripts/contracts_truth.py::ACTIVITY_STATES` (`ACTIVE_PROVEN`, `COMPLETED`, `CANCELLED`, `TERMINATED`, `SUSPENDED`, `UNKNOWN`) — não inventar categorias novas, e não redefinir as existentes. *(Correção @po: a v0.1.0 omitia `SUSPENDED`, que existe em `ACTIVITY_STATES` e portanto pode chegar à política vindo do dado carimbado pelo crawler — ver AC 32.)*
- Alterar `scripts/contracts_truth.py` — esta story **consome** a classificação existente, não a modifica (o módulo é consumido por crawler/ops e tem testes próprios em `tests/test_contract_activity_and_quality.py`; alterá-lo seria mudança de blast radius muito maior). Se a classificação se mostrar insuficiente, registrar follow-up — não editar dentro desta story.
- Qualquer alteração em `scripts/ops/confenge_feed_cycle.py` e `scripts/confenge_activation/publish.py` — esses pontos pertencem à story irmã `story-current-claim-jit-authority-01` (ver Dependencies).

## Dependencies and sizing

- Nenhuma dependência de story em andamento é bloqueante **para esta story** — a regra 8 (degradação para `UNKNOWN` quando lifecycle não existir no dado) foi desenhada exatamente para que esta story seja mergeável independentemente de qualquer story futura de lifecycle mais completo.
- **Aresta reversa — esta story é upstream de `story-current-claim-jit-authority-01`** *(registrada pelo @po; a v0.1.0 só documentava que nada bloqueia esta story, perdendo o sequenciamento)*. `docs/stories/story-current-claim-jit-authority-01.md` (HIGH-RISK, Draft) **consome** exatamente os campos que esta story produz: `claim_mode=CURRENT_CONTRACT`, `requires_current_authority=true` e `copy_hash`. Os vocabulários foram conferidos e **são compatíveis** — não há conflito a resolver; o que se registra é a ordem de merge: **esta story deve entrar antes**, sob pena de a JIT depender de campos inexistentes. A partição de escopo também é limpa e deve permanecer assim: esta story não toca `scripts/ops/confenge_feed_cycle.py` nem `scripts/confenge_activation/publish.py` (pontos de integração da JIT); a JIT não altera regras de copy/wording (escopo desta). Qualquer mudança na definição de `copy_hash` aqui (AC 18/20 — SHA256 do corpo final exato) **quebra** o golden vector de `attestation_hash` da JIT e exige aviso explícito.
- `scripts/contracts_truth.py` — dependência de **código** (não de story), já em HEAD, estável e testada. Sem trabalho pendente; apenas reuso (AC 31-33).
- Não há `accumulated-context.md` no repositório para referenciar (verificado: nenhum arquivo com esse nome existe no projeto).
- T-shirt size: **M**. Módulo novo pequeno e puro + 4 pontos de integração cirúrgicos, mas com superfície de teste ampla (7 casos red-team + regras de negócio + monotonicidade de send-readiness).

## Risks and mitigations

- **Exposição real de outbound**: `send_readiness.py` governa `EMAIL_SEND_READY`, que alimenta o envio comercial real. Mitigado pelo invariante de monotonicidade (AC 27) e por testes que provam que nenhum caso que hoje é `EMAIL_SEND_READY` deixa de ser por um motivo não relacionado, e nenhum caso que hoje não é vira `EMAIL_SEND_READY` só por esta mudança.
- **Code-freeze de campanha**: `scripts/ops/confenge_frozen_inputs.py::discover_frozen_input_paths` faz fechamento transitivo de imports locais sob `scripts/` (comportamento documentado e verificado empiricamente em `docs/stories/story-outbound-sector-classifier-false-positive-01.md`, AC 20a). Um pacote novo importado por um arquivo congelado **pode ser puxado para dentro do freeze mesmo sendo novo**.

  **Medição feita pelo @po em HEAD (2026-09-01), que eleva isto de hipótese a fato** — `discover_frozen_input_paths(Path("."))` retorna **162 caminhos**:

  | Arquivo | Congelado em HEAD? |
  |---|---|
  | `scripts/confenge_account_intelligence/message_spine.py` | **SIM** |
  | `scripts/confenge_contact_resolution/send_readiness.py` | **SIM** |
  | `scripts/confenge_account_intelligence/facts.py` | não |
  | `scripts/confenge_account_intelligence/normalize.py` | não |
  | `scripts/contracts_truth.py` | não (**ainda**) |

  Consequências, que @dev deve tratar como dadas e não como incógnitas:
  1. `scripts/confenge_claim_policy/` **entrará** no conjunto congelado por fechamento transitivo (será importado por dois arquivos já congelados). A pergunta do AC 30 deixa de ser "entra ou não" e passa a ser "declarar o diff exato do conjunto".
  2. `scripts/contracts_truth.py` hoje **não** está congelado; ao ser importado pelo módulo novo, **será puxado para dentro do freeze junto com seu próprio fechamento transitivo**. Isso pode expandir o conjunto para além dos 162 + 1 — @dev deve declarar o número final e o delta completo, não apenas os arquivos que editou.
  3. Independentemente do pacote novo, esta story **edita dois inputs já congelados**, então a sequência de 2 PRs (código → artifact-only re-freeze, sem squash) se aplica de qualquer forma — com entradas **novas** no manifesto para os arquivos novos e **rebind** para os já existentes. Não é um caso ou outro: são os dois.

  Mitigado pelo AC 30 (reescrito) e pela escalada a HIGH-RISK.
- **Dois sites do mesmo bug**: cobrir só `facts.py` e deixar `message_spine.py::_extract_temporal_event` inalterado faria os casos red-team "UNKNOWN publicado ontem" e "aditivo de contrato encerrado" continuarem falhando por um caminho que nunca passa por `facts.py`. Mitigado pelos ACs 12-18, que nomeiam ambos os sites explicitamente.
- **Congelar dataclasses frozen**: `CopyContextResult`/`EmailSendReadyResult` em `send_readiness.py` são `@dataclass(frozen=True)` — qualquer "rebaixamento" de `CURRENT` para histórico seguro precisa acontecer **antes** da construção do resultado, não por mutação pós-construção. Mitigado pelo AC 26 (nomeando o mecanismo esperado: decisão de rebaixamento entra no fluxo de avaliação, não em pós-processamento do objeto imutável).

## Baseline (estado atual, verificado por leitura de HEAD)

- `facts.py::why_now`, pain-check `"addendum"` (linhas 302-307): texto fixo `"Aditivos/alterações observados em contrato público recente ou ativo."` disparado por qualquer contrato com `has_addendum`/`addendum_count > 0`, sem lifecycle.
- `message_spine.py::_extract_temporal_event`: `publication_date`/`start_date` com `age_days <= 180` → força `STRONG` (linhas ~255-265); `end_date` entre -30 e +180 dias → `STRONG`/"janela temporal verificável" (linhas ~245-254). Nenhum dos dois checa lifecycle.
- `normalize.py`: nenhum campo `lifecycle_state` emitido hoje.
- `send_readiness.py`: nenhum conceito de `lifecycle_state` ou `FACTUAL_CLAIM_SAFE` hoje; `evaluate_copy_context_ready` já rejeita `why_now_strength == WEAK` (linhas 927-931).
- `extract_contract_hook(bag)` (message_spine.py:83): único call site é message_spine.py:486, dentro de `build_message_spine`. Nenhum outro consumidor no repositório (verificado por grep).

## Estado-alvo

- Nenhuma afirmação material de outreach cita presente/ativo sem prova verificável de `ACTIVE_PROVEN` + evento contemporâneo (`why_now_eligible=True`).
- `COMPLETED`/`TERMINATED`/`CANCELLED`/`UNKNOWN` nunca produzem `allowed_tense in {PRESENT_CONFIRMED}` nem `outreach_use_class == CURRENT_ACTIONABLE`.
- Histórico continua alimentando `why_you` sem exigir `why_now` (Regra 1) — nenhuma perda de recall de copy.
- `send_readiness.py` nunca promove um caso previamente não-`EMAIL_SEND_READY` a `EMAIL_SEND_READY` por causa desta mudança; casos `CURRENT` sem autoridade contemporânea são rebaixados a histórico seguro (se elegível) ou ficam pendentes — nunca enviados como presente.
- Todos os 7 casos red-team cobertos por teste e passando; suíte existente (lint/typecheck/testes) permanece verde.

## Acceptance Criteria

**Regras de negócio (Given/When/Then, ordem = ordem do enunciado):**

1. **Given** um contrato cujo único fato disponível é histórico (ex.: `lifecycle_state=COMPLETED` ou `TERMINATED` com evidência), **when** `CLAIM_POLICY` avalia para propósito `why_you`, **then** `why_you_eligible=True` sem exigir `why_now_eligible=True`.
2. **Given** um contrato `lifecycle_state=ACTIVE_PROVEN` com evidência de qualidade (evidence_ids não vazios, fonte não-hollow), **when** avaliado para candidatura `CURRENT`, **then** o contrato é elegível a candidato `CURRENT_ACTIONABLE`; **and** `why_now_eligible` só é `True` se, além disso, houver evento contemporâneo verificável e datado associado (não apenas `ACTIVE_PROVEN` isolado).
3. **Given** `lifecycle_state=COMPLETED` **e prova factual mínima presente** (`evidence_ids` não vazio e fato não-hollow), **when** avaliado, **then** `outreach_use_class in {RECENT_RETROSPECTIVE, HISTORICAL_CONTEXT}` e `allowed_tense != PRESENT_CONFIRMED` — nunca presente; **and** se a prova factual mínima **não** estiver presente, o hard gate factual da Regra 7 prevalece e o resultado é `DO_NOT_CITE`. *(Correção @po: a v0.1.0 tornava a Regra 3 absoluta, o que a colocava em conflito com a Regra 7 e permitiria citar em passado um `COMPLETED` sem nenhuma evidência. A precedência normativa é: **Regra 7 (hard gate factual) > Regra 3**.)*
4. **Given** `lifecycle_state=UNKNOWN`, **when** avaliado, **then** `outreach_use_class != CURRENT_ACTIONABLE` e `allowed_tense != PRESENT_CONFIRMED`, mesmo que `publication_date` ou `start_date` sejam recentes — publicação/crawl recente não é execução atual.
5. **Given** `lifecycle_state in {TERMINATED, CANCELLED}`, **when** avaliado como gancho de abertura (why_you), **then** o resultado padrão é `outreach_use_class=DO_NOT_CITE`; **and** citação em tempo passado só é permitida quando sustentada por evidência explícita (`evidence_ids` não vazios e fato não-hollow) — caso contrário permanece `DO_NOT_CITE`.
6. **Given** um contrato com `has_addendum=True`, **when** avaliado via `CLAIM_POLICY`, **then** a existência do aditivo por si só **não** produz `outreach_use_class=CURRENT_ACTIONABLE` nem `allowed_tense=PRESENT_CONFIRMED` — lifecycle do contrato é obrigatório para essa decisão (corrige o bug relatado em `facts.py:302-307`).
7. **Given** qualquer avaliação, **when** falta prova factual mínima (`evidence_ids` vazio ou fato hollow), **then** o hard gate factual prevalece sobre **qualquer outra regra desta lista** e o resultado é rebaixado — nenhum score numérico e nenhum `lifecycle_state` favorável pode vencer esse gate. Aplica-se tanto ao caso `ACTIVE_PROVEN`/`CURRENT_ACTIONABLE` (rebaixa para histórico ou `DO_NOT_CITE`) quanto ao caso histórico sem evidência (`DO_NOT_CITE`, ver Regras 3 e 5).
8. **Given** um contrato sem campo de lifecycle no dado normalizado (dado legado, anterior a esta story ou anterior a qualquer story futura de lifecycle mais completo), **when** avaliado, **then** a política degrada para `lifecycle_state=UNKNOWN` (nunca lança exceção, nunca assume `ACTIVE_PROVEN`) e permite histórico factual normalmente (`why_you_eligible` pode ser `True` via Regra 1).
9. **Given** um bag com múltiplos contratos, **when** `message_spine.extract_contract_hook(bag, purpose="why_you")` e `message_spine.extract_contract_hook(bag, purpose="why_now")` são chamados, **then** podem retornar contratos diferentes — `why_you` pode usar o maior histórico; `why_now` só retorna um contrato que seja candidato `CURRENT_ACTIONABLE` válido (ou vazio, se nenhum existir).
10. **Given** nenhum contrato elegível a `why_now` (nenhum `CURRENT_ACTIONABLE` com `why_now_eligible=True`), **when** a política é avaliada, **then** `claim_mode` não inclui urgência inventada — `why_now_eligible=False` para todos os candidatos e nenhum texto de urgência é produzido a partir de dado insuficiente.
11. **Given** um resultado de `CLAIM_POLICY` com `outreach_use_class=CURRENT_ACTIONABLE`, **when** o resultado é construído, **then** `requires_current_authority=True` sempre acompanha esse resultado (nunca `False` para claims correntes).

**Casos red-team (obrigatoriamente testes, nomeados por caso):**

12. **Given** `lifecycle_state=COMPLETED` e um texto candidato "em execução", **when** a política é consultada para permitir esse tempo verbal, **then** bloqueado (`allowed_tense` não permite `PRESENT_CONFIRMED`/equivalente presente).
13. **Given** `lifecycle_state=COMPLETED` e um texto candidato "no histórico público vocês executaram", **when** consultado, **then** permitido (`allowed_tense=PAST_ONLY`, `outreach_use_class in {RECENT_RETROSPECTIVE, HISTORICAL_CONTEXT}`).
14. **Given** `lifecycle_state=UNKNOWN` com `publication_date` = ontem (age_days=1) em `normalize.py`/`message_spine.py::_extract_temporal_event`, **when** `why_now` é derivado, **then** o resultado não autoriza tempo presente e `why_now_strength` não é `STRONG` só por causa da data — cobre tanto o caminho de `facts.py` quanto o caminho de `message_spine.py::_extract_temporal_event` (linhas ~255-265).
15. **Given** um bag com um contrato histórico grande (`COMPLETED`, objeto extenso, múltiplos evidence_ids) e um contrato ativo menor, **when** `message_spine.extract_contract_hook` é chamado com `purpose="why_you"` vs `purpose="why_now"`, **then** `why_you` usa o contrato histórico grande e `why_now` só considera o contrato ativo (se este for de fato `CURRENT_ACTIONABLE` válido; caso contrário `why_now` fica vazio, não força o histórico grande como "agora").
16. **Given** nenhum contrato com `why_now_eligible=True` no bag, **when** `build_message_spine`/`why_now` são avaliados, **then** zero urgência é inventada — `why_now_out` fica vazio/`why_now_strength=WEAK`, sem texto de urgência sintético.
17. **Given** um contrato com aditivo (`has_addendum=True`) cujo `lifecycle_state` é `TERMINATED`/`COMPLETED`, **when** `CLAIM_POLICY` é consultada (via `facts.py::why_now` corrigido), **then** o resultado é sempre passado — nunca "recente ou ativo" — corrigindo literalmente o texto de `facts.py:306` (`"Aditivos/alterações observados em contrato público recente ou ativo."`) para esse cenário.
18. **Given** duas chamadas de `CLAIM_POLICY`/geração de copy com o mesmo `contract_id`/`evidence_ids` mas corpo de e-mail final diferente (string diferente passada como corpo), **when** `copy_hash` é calculado, **then** os dois hashes diferem (SHA256 do corpo final exato, não dos metadados).

**Contrato de API / pureza do módulo:**

19. **Given** o módulo `scripts/confenge_claim_policy/`, **when** inspecionado, **then** não contém I/O de arquivo, chamada de rede, acesso a banco, nem `date.today()`/`datetime.now()` internos — `evaluated_as_of` é sempre parâmetro explícito (nenhuma leitura de wall clock, ao contrário do padrão hoje usado em `normalize.py:59` e `message_spine.py:160`).
20. **Given** `copy_hash`, **when** calculado, **then** é SHA256 do corpo final exato (string) recebido como parâmetro pelo chamador — o módulo puro nunca monta ou descobre esse corpo sozinho.
21. **Given** uma lista de candidatos de claim para uma mesma mensagem contendo mais de um candidato com `outreach_use_class=CURRENT_ACTIONABLE`, **when** a função de seleção de mensagem é chamada, **then** o resultado é fail-closed (rewrite obrigatório / erro determinístico ou lista vazia com `reason_codes` explicando o motivo) — nunca mais de um claim `CURRENT` na mesma mensagem.
22. **Given** a lista de candidatos com exatamente zero ou um `CURRENT_ACTIONABLE`, **when** a função de seleção é chamada, **then** processa normalmente sem falso positivo de fail-closed.
23. **Given** `message_spine.extract_contract_hook(bag)` chamado **sem** o parâmetro `purpose` (novo, keyword-only, default `"why_you"`), **when** comparado ao comportamento de HEAD da mesma função (message_spine.py:83), **then** o resultado é idêntico para o mesmo `bag` (backward-compatible; o único call site hoje, message_spine.py:486, continua funcionando sem alteração de assinatura na chamada). *(Reescrito pelo @po: a v0.1.0 testava `extract_contract_hook_by_purpose`, função que deixa de existir com a resolução do import circular — a AC seria intestável.)*
23a. **Given** o pacote `scripts/confenge_claim_policy/`, **when** seus imports são inspecionados (estática ou via teste de import), **then** ele **não importa** `scripts.confenge_account_intelligence.*` nem `scripts.confenge_contact_resolution.*` — a dependência é estritamente unidirecional (integração → política), sem ciclo. **Exceção permitida e única:** `scripts.contracts_truth` (AC 31), que não pertence a nenhum dos dois pacotes e não os importa de volta.
23b. **Given** que as Regras 5 e 7 dependem do conceito "fato não-hollow" e que `is_hollow_fact` vive em `message_spine.py` — cujo import está proibido pela AC 23a — **when** o módulo puro avalia um candidato, **then** a hollowness e a qualidade de evidência chegam **como dados já decididos pelo chamador** no candidato (ex.: `has_hollow_fact: bool`, `evidence_ids: tuple[str, ...]`), e o módulo puro **nunca inspeciona texto** para decidir se um fato é hollow. *(Correção @po: sem esta cláusula, a AC 23a forçaria o @dev a duplicar `is_hollow_fact` dentro do módulo novo, recriando exatamente o problema de duas fontes de verdade que a AC 31 acabou de eliminar para lifecycle. `is_hollow_fact` permanece com dono único em `message_spine.py`.)*

**Integração:**

24. **Given** `normalize.py` derivando lifecycle via `contracts_truth.classify_contract_activity` (AC 31 é a autoridade; esta AC apenas descreve as consequências observáveis dela), **when** o lifecycle não vem explícito no dado bruto, **then** o campo derivado obedece exatamente ao comportamento da função reusada:

    | Entrada | `lifecycle_state` derivado | Caminho na função |
    |---|---|---|
    | `end_date` no passado **e** `start_date` presente | `COMPLETED` | `vigencia_ended` |
    | `end_date` no passado **sem** `start_date` | `UNKNOWN` | `missing_status_and_vigencia` |
    | `start_date <= as_of <= end_date` | `ACTIVE_PROVEN` | `vigencia_window` |
    | `start_date > end_date` | `UNKNOWN` | `inverted_vigencia` |
    | só `publication_date`/`start_date` recente | `UNKNOWN` | `missing_status_and_vigencia` |

    **and** em nenhum caminho a derivação promove a presente-elegível a partir de datas isoladas (demote-only preservado).

    *(Correção @po: a v0.1.0 exigia `COMPLETED` para "`end_date` no passado" sem qualificação, o que **contradiz** a função reusada — `classify_contract_activity` só entra no ramo de vigência com `start and end`, e `normalize.py:192` emite `start_date=None` quando ausente. Um teste escrito a partir da AC 24 antiga falharia contra uma implementação escrita a partir da AC 31. A segurança não é afetada: `UNKNOWN` já proíbe presente pelas Regras 4 e 7.)*

24a. **Given** que `TERMINATED`/`CANCELLED`/`SUSPENDED` só são alcançáveis via token em `raw_status` (`_TERMINATED_TOKENS` = `{"rescindido", "resilido", "terminated", "distratado"}` etc.) e que **o dict de contrato normalizado hoje não carrega nenhum campo de status** (verificado pelo @po: `normalize.py:188-213` não lê `situacao`/`status` por contrato), **when** Task 2 é implementada, **then** `normalize.py` passa a repassar o status bruto do contrato (ex.: `c.get("situacao") or c.get("status") or c.get("situacao_nome")`, seguindo o padrão de fallbacks já usado nas outras chaves) como `raw_status=` para `classify_contract_activity`; **and** se nenhuma dessas chaves existir no payload, o estado degrada por vigência/`UNKNOWN` normalmente (Regra 8) — sem exceção. Sem esse repasse, `TERMINATED`/`CANCELLED`/`SUSPENDED` seriam **inalcançáveis por derivação** e as ACs 5 e 32 ficariam sem caminho de produção real.
25. **Given** `message_spine.py::_extract_temporal_event`, **when** um contrato tem `end_date` entre -30 e +180 dias mas `lifecycle_state` derivado é `COMPLETED`/`TERMINATED`, **then** o resultado não retorna mais `"STRONG"`/"janela temporal verificável" para esse contrato — a força é rebaixada conforme `CLAIM_POLICY` (cobre o segundo red-team case, "aditivo de contrato encerrado").
26. **Given** `send_readiness.py` avaliando um candidato `CURRENT_ACTIONABLE` sem `why_now_eligible=True` (sem autoridade contemporânea comprovada), **when** o resultado de send-readiness é construído, **then** o rebaixamento para histórico seguro (ou pendência) acontece **antes** da construção do `CopyContextResult`/`EmailSendReadyResult` (que são `@dataclass(frozen=True)`, linhas 309-366) — nunca por mutação pós-construção.
27. **Given** o comportamento de `evaluate_copy_context_ready`/`evaluate_email_send_ready` antes desta mudança, **when** comparado ao comportamento depois, **then** nenhum caso que **não** era `EMAIL_SEND_READY` antes se torna `EMAIL_SEND_READY` depois só por causa da introdução de `FACTUAL_CLAIM_SAFE` (teste de não-regressão explícito de monotonicidade — o novo gate só pode subtrair, nunca adicionar).
28. **Given** um caso `HISTORICAL` compatível (`outreach_use_class in {RECENT_RETROSPECTIVE, HISTORICAL_CONTEXT}`, `allowed_tense in {NEUTRAL_FACTUAL, PAST_ONLY}`) que já atendia todos os outros requisitos de `EMAIL_SEND_READY` antes desta mudança, **when** reavaliado, **then** continua elegível — `FACTUAL_CLAIM_SAFE` não introduz regressão para histórico já seguro.
29. **Given** a suíte de testes existente (`pytest tests/ -q`), **when** executada após a mudança, **then** passa sem novas falhas — nenhuma regressão introduzida nos 4 arquivos de integração fora do escopo declarado.

**Freeze / operacional (bloqueia push, não bloqueia dev):**

30. **Given** que em HEAD `message_spine.py` e `send_readiness.py` **já pertencem** ao conjunto congelado de 162 caminhos (medido pelo @po — ver Riscos), **when** @dev roda `discover_frozen_input_paths(Path("."))` **antes e depois** da mudança e antes de considerar a story pronta para push, **then** declara no Dev Agent Record: (a) o total antes e depois; (b) o **delta completo** de caminhos adicionados — que deve incluir `scripts/confenge_claim_policy/*` e, se o reuso da Regra 31 for feito por import direto, também `scripts/contracts_truth.py` e o fechamento transitivo dele; (c) confirmação de que a sequência de 2 PRs (código → artifact-only re-freeze, **sem squash**) será usada, com entradas **novas** no manifesto para os arquivos novos **e rebind** para `message_spine.py`/`send_readiness.py`. **Bloqueia push, não bloqueia dev**: nenhum item desta AC impede escrever código ou rodar testes localmente; ela é pré-condição de publicação, e o push é autoridade exclusiva do @devops.

**Reuso e vocabulário de lifecycle (adicionadas pelo @po na validação — ver Contexto):**

31. **Given** o módulo `scripts/confenge_claim_policy/`, **when** inspecionado, **then** ele **não define** enum, `Literal`, constante ou conjunto próprio de estados de lifecycle: importa e reutiliza `ACTIVE_PROVEN`, `COMPLETED`, `CANCELLED`, `TERMINATED`, `SUSPENDED`, `UNKNOWN` e `ACTIVITY_STATES` de `scripts/contracts_truth.py`; **and** a derivação de lifecycle em `normalize.py` (Regra 24) usa `contracts_truth.classify_contract_activity(...)` em vez de reimplementar precedência de status/vigência. Um teste deve falhar se um segundo vocabulário de lifecycle for introduzido (ex.: assert de que os estados usados são subconjunto de `ACTIVITY_STATES`).
32. **Given** `lifecycle_state=SUSPENDED` (estado real de `ACTIVITY_STATES`, atingível via `_SUSPENDED_TOKENS` = `{"suspenso", "suspended", "paralisado"}` no dado carimbado pelo crawler), **when** avaliado, **then** o comportamento é definido e testado: `outreach_use_class != CURRENT_ACTIONABLE` e `allowed_tense != PRESENT_CONFIRMED` — um contrato suspenso **não** está em execução; o tratamento padrão é o mesmo de `UNKNOWN` (histórico factual permitido via Regra 1, presente proibido). *(A v0.1.0 omitia este estado inteiramente — era um buraco de cobertura, não uma decisão.)*
33. **Given** que `contracts_truth.classify_contract_activity` tem assinatura `today: date | None = None` com fallback interno para `date.today()`, **when** o módulo puro ou `normalize.py` a chamam, **then** `today=` é **sempre passado explicitamente** a partir de `evaluated_as_of`/`as_of` — nunca omitido. Um teste de pureza deve provar o **resultado observável**: nenhuma leitura de wall clock é alcançável durante a avaliação, e a avaliação é determinística para o mesmo input em qualquer data de execução. O mecanismo fica a critério do @dev (nota: `date` é tipo C — patch em `date.today` direto não funciona; patch-se a referência no módulo, ex. `contracts_truth.date`). *(Sem esta AC, um wrapper satisfaria a letra da Regra 19 — nenhum `date.today()` no código novo — violando sua intenção, porque o wall clock entraria pela função reusada.)*

## Tasks / Subtasks

- [x] Task 1 — Criar módulo `scripts/confenge_claim_policy/` (AC: 1-11, 19-23a, 31-33)
  - [x] **Importar** os estados de lifecycle de `scripts/contracts_truth.py` (AC 31) — **não** definir `LifecycleState` próprio. Definir apenas o que não existe: `OutreachUseClass`, `ClaimMode`, `AllowedTense`.
  - [x] Implementar dataclass frozen do resultado canônico com todos os campos listados no Scope.
  - [x] Implementar `evaluate_claim_policy(candidate, *, evaluated_as_of, purpose)` puro, cobrindo `SUSPENDED` (AC 32) e sempre repassando `today=evaluated_as_of` (AC 33).
  - [x] Garantir dependência unidirecional: nenhum import de `confenge_account_intelligence` / `confenge_contact_resolution` (AC 23a).
  - [x] Implementar função de seleção de mensagem com regra "máximo 1 CURRENT" fail-closed.
  - [x] Implementar cálculo de `copy_hash` (SHA256 de string recebida).
- [x] Task 2 — Derivar `lifecycle_state` em `normalize.py` (AC: 8, 24, 24a, 31, 33)
  - [x] Usar `contracts_truth.classify_contract_activity(...)` com `today=as_of` explícito — não reimplementar a precedência (ela já existe e já é demote-only por construção).
  - [x] **Repassar o status bruto por contrato** como `raw_status=` (AC 24a) — hoje `normalize.py:188-213` não lê nenhuma chave de status; sem isso `TERMINATED`/`CANCELLED`/`SUSPENDED` são inalcançáveis.
  - [x] Precedência resultante: status explícito do dado bruto > janela de vigência (`start_date` **e** `end_date`) vs `as_of` > `UNKNOWN`.
  - [x] Emitir o novo campo `lifecycle_state` no dict de contrato normalizado (hoje ausente, linhas 188-213).
- [x] Task 2a — **Gate de arquitetura (@architect), antes de Task 3-5** — validar o contrato de API do módulo puro e a fronteira de import (AC 23a, 31), dado o nível HIGH-RISK e o fato de dois arquivos de integração estarem congelados.
- [x] Task 3 — Corrigir `facts.py::why_now` (AC: 6, 12, 13, 17)
  - [x] Pain-check `"addendum"` consulta `CLAIM_POLICY` para decidir texto/tempo verbal em vez do texto fixo atual.
  - [x] Preservar estrutura de `pain_checks` e o restante da função.
- [x] Task 4 — Corrigir `message_spine.py::_extract_temporal_event` e `build_message_spine` (AC: 14, 16, 25)
  - [x] Consultar lifecycle/`CLAIM_POLICY` antes de atribuir força `STRONG` a `publication_date`/`start_date` recentes.
  - [x] Consultar lifecycle antes de atribuir força `STRONG` ao bloco de `end_date` (-30 a +180 dias).
  - [x] Adicionar parâmetro keyword-only `purpose="why_you"` a `extract_contract_hook` (message_spine.py:83) preservando compatibilidade byte-a-byte no default (único call site: linha 486) — AC 23.
- [x] Task 5 — Introduzir `FACTUAL_CLAIM_SAFE` em `send_readiness.py` (AC: 26, 27, 28)
  - [x] Rebaixamento de `CURRENT` sem autoridade contemporânea acontece antes da construção de `CopyContextResult`/`EmailSendReadyResult`.
  - [x] Teste de monotonicidade: nenhum caso ganha `EMAIL_SEND_READY` que não tinha antes.
  - [x] Teste de não-regressão: histórico já seguro continua elegível.
- [x] Task 6 — Testes red-team e de regra de negócio (AC: 1-18, 31-33, todos)
  - [x] Um teste nomeado por caso red-team (7 casos).
  - [x] Testes de pureza (sem I/O, sem wall clock — inclusive via função reusada, AC 33) e de `copy_hash`.
  - [x] Teste de vocabulário único de lifecycle (AC 31) e de `SUSPENDED` (AC 32).
  - [x] Teste de ausência de import circular (AC 23a).
  - [x] Rodar suíte completa (`pytest tests/ -q --tb=no`) e confirmar zero novas falhas.
- [x] Task 7 — Verificação de code-freeze (AC: 30)
  - [x] Rodar `discover_frozen_input_paths`/equivalente e declarar resultado no Dev Agent Record.
  - [x] Se aplicável, preparar sequência de 2 PRs (não executar push — fora da autoridade do @dev).

## 🤖 CodeRabbit Integration

**Story Type Analysis:**
- **Primary Type**: Architecture (novo módulo puro + contrato de API entre 4 arquivos existentes)
- **Secondary Type(s)**: Integration (pontos de integração cirúrgicos em 4 arquivos)
- **Complexity**: High — módulo novo, 4 pontos de integração, superfície de teste ampla (11 regras + 7 red-team + monotonicidade de send-readiness), risco de regressão em caminho que alimenta envio comercial real.

**Specialized Agent Assignment:**

**Primary Agents**:
- @dev (pre-commit reviews, todas as stories)
- @architect (decisões de contrato de API do módulo puro, dado o alcance sistêmico)

**Supporting Agents**:
- @qa (cobertura dos 7 casos red-team e do teste de monotonicidade de send-readiness)

**Quality Gate Tasks:**
- [ ] Pre-Commit (@dev): Run `coderabbit --prompt-only -t uncommitted` before marking story complete
- [ ] Pre-PR (@devops): Run `coderabbit --prompt-only --base main` before creating pull request

**Self-Healing Configuration:**
- Primary Agent: @dev (light mode)
- Max Iterations: 2
- Timeout: 15 minutes
- Severity Filter: CRITICAL

**Predicted Behavior:**
- CRITICAL issues: auto_fix (up to 2 iterations)
- HIGH issues: document_only (noted in Dev Notes)

**CodeRabbit Focus Areas:**

**Primary Focus:**
- Pureza do módulo novo (sem I/O, sem wall clock, sem side effects)
- Corretude do hard gate factual (nenhum score pode vencer o gate — AC 7)
- Monotonicidade de send-readiness (AC 27) — não introduzir promoção indevida

**Secondary Focus:**
- Backward compatibility de `extract_contract_hook` (único call site preservado)
- Cobertura dos 7 casos red-team nomeados individualmente

## Dev Notes

### Reuso de `contracts_truth.py` (obrigatório — AC 31-33)

**Não reimplementar.** `scripts/contracts_truth.py::classify_contract_activity` já entrega, em HEAD, a precedência exata que esta story pede, com a propriedade demote-only embutida:

```python
classify_contract_activity(
    raw_status=...,          # token PT-BR/EN; conjuntos já definidos no módulo
    vigencia_inicio=...,     # start_date
    vigencia_fim=...,        # end_date
    today=as_of,             # SEMPRE explícito (AC 33) — o default cai em date.today()
) -> ContractActivity        # frozen: .state, .raw_status, .rule_version, .reasons
```

Comportamento já garantido e testado (`tests/test_contract_activity_and_quality.py`), que satisfaz as Regras 8 e 24 sem código novo:

- token de status explícito vence a janela de vigência;
- token ativo **com** `end_date` no passado → `COMPLETED` (não `ACTIVE_PROVEN`);
- token ativo **sem** vigência → `UNKNOWN` (`active_token_without_vigencia`);
- vigência invertida (`start > end`) → `UNKNOWN`;
- ausência de status **e** de vigência → `UNKNOWN` (`missing_status_and_vigencia`);
- `is_active=TRUE` como default upstream é explicitamente **ignorado** (`del is_active_default  # never proof of activity`) — exatamente a postura desta story.

Só produz `ACTIVE_PROVEN` em dois caminhos, ambos exigindo janela de vigência real: `raw_status+vigencia` e `vigencia_window`. Datas sozinhas (`publication_date` recente) nunca promovem — o que é precisamente a Regra 4.

**Notas de fronteira:**

- `contracts_truth.py` contém seams de I/O (`PostgresWriterFence`, `resolve_checkpoint_dir`, `stamp_contract_truth_labels`) e constantes de caminho de produção, mas **o import do módulo não tem efeito colateral** (apenas constantes e definições). Usar somente `classify_contract_activity` + as constantes de estado não viola a Regra 19 — a proibição é de o módulo novo **fazer** I/O, não de conviver no mesmo namespace com funções que fazem. Documentar isso no PR evita falso positivo de CodeRabbit/QA.
- O import **expande o conjunto congelado** (ver Riscos e AC 30): `contracts_truth.py` hoje não está congelado e passará a estar, junto com o fechamento transitivo dele.

**Invariante obrigatório (preservado):** a derivação **só pode rebaixar** (demote), nunca promover a um estado presente-elegível.

### Architecture Gate (Task 2a) — @architect, 2026-09-01 — APROVADO COM RESSALVAS

Veredito: **aprovado com ressalvas**. Nenhum item abaixo bloqueia o @dev começar. Todos foram
verificados contra HEAD nesta sessão (não são hipóteses). Os itens A1-A4 são **normativos**:
o @dev deve implementá-los; eles não alteram nenhuma AC validada pelo @po, apenas fixam
escolhas que as ACs deixaram em aberto e que, se decididas em silêncio, quebram algo.

**Confirmações arquiteturais solicitadas:**

- **Reuso de `contracts_truth.py` — SEGURO e obrigatório.** Verificado: o módulo importa
  **apenas stdlib** (`hashlib, json, os, re, collections.abc, dataclasses, datetime, pathlib,
  typing`) e o nível de módulo contém somente literais e constantes `Path(...)` — nenhum
  `os.environ`/`os.getenv`, nenhuma leitura de arquivo, nenhum `subprocess` executado no import.
  A afirmação "o import não tem efeito colateral" das Dev Notes está confirmada por leitura, e a
  AC 19 (pureza) é satisfeita sem carve-out. `classify_contract_activity` confere com o descrito
  na story (precedência status > vigência > UNKNOWN, `is_active_default` descartado, demote-only).
- **Direção de dependência — CORRETA.** `message_spine.py` hoje tem **zero imports locais** (só
  `re`, `dataclasses`, `datetime`, `typing`); `normalize.py` importa apenas
  `confenge_account_intelligence.models`. Logo `confenge_claim_policy` → `contracts_truth`
  (stdlib-only) é um DAG por construção: **ciclo é impossível**, não apenas evitado. A AC 23a está
  correta e é verificável estaticamente.
- **Código-primeiro / freeze depois — NÃO bloqueia o @dev.** Confirmado. Medição repetida em HEAD:
  `discover_frozen_input_paths` = **162**, com `message_spine.py` e `send_readiness.py` dentro;
  `facts.py`, `normalize.py`, `contracts_truth.py`, `pipeline.py` fora. AC 30 é pré-condição de
  **publicação** (autoridade @devops), não de implementação.
- **Escopo OUT confirmado.** `contracts_truth.py` não se altera nesta story; arquivos da
  `story-current-claim-jit-authority-01` (`confenge_feed_cycle.py`, `confenge_activation/publish.py`)
  não se tocam.

**Correção factual à seção Riscos (item 2):** `contracts_truth.py` não arrasta fechamento
transitivo — seus imports são stdlib-only, então seu fechamento **é ele mesmo**. Predição
falsificável no push: delta esperado = `162 + N(scripts/confenge_claim_policy/*) + 1`.
`facts.py` e `normalize.py` **permanecem fora** do freeze (nenhum arquivo congelado os importa).

**A1 — `evaluated_as_of` é `datetime.date`, não string (risco de TypeError em runtime).**
`classify_contract_activity` faz `ref = today or date.today()` e compara `end < ref`, onde `end`
passou por `_as_date()` mas `ref` **não**. `normalize.py:59` produz `as_of` como **string ISO** e
`message_spine` trabalha em strings. Passar `today="2026-09-01"` levanta `TypeError`. Normativo:
`evaluated_as_of` no módulo puro é `datetime.date`; a conversão de string acontece **no chamador**,
antes de cruzar a fronteira. Nenhuma AC atual proíbe o erro — este é o ponto de quebra mais provável
do novo seam.

**A2 — `copy_hash`: encoding pinado.** `hashlib.sha256(body.encode("utf-8")).hexdigest()`,
sem normalização unicode (NFC/NFD), sem `strip()`, sem canonicalização de newline. A
`story-current-claim-jit-authority-01` fixa um golden vector de `attestation_hash` sobre este valor;
qualquer escolha silenciosa diferente quebra a story irmã.

**A3 — AC 21 fail-closed: escolher lista vazia + `reason_codes`, não exceção.** A AC admite
"erro determinístico **ou** lista vazia" — são sistemas diferentes. Em caminho que alimenta envio
comercial real, levantar exceção cria nova superfície de crash; retornar lista vazia com
`reason_codes` explícitos é fail-closed, não pode violar a monotonicidade (AC 27) e não derruba o
pipeline. Normativo: **lista vazia + `reason_codes`**.

**A4 — Armadilha de token: nunca alimentar um nome de estado em `raw_status=`.** `_norm_status`
apenas minúscula e colapsa espaços. Por coincidência dos tokens em inglês, `"COMPLETED"`,
`"CANCELLED"`, `"TERMINATED"` e `"SUSPENDED"` **casam** com `_COMPLETED/_CANCELLED/_TERMINATED/
_SUSPENDED_TOKENS`; `"ACTIVE_PROVEN"` **não** está em `_ACTIVE_TOKENS`. Ou seja: passar um estado já
carimbado como se fosse token funciona para 4 de 5 estados terminais e degrada `ACTIVE_PROVEN` em
silêncio — seguro hoje **por acidente**, e uma futura adição a `_ACTIVE_TOKENS` transforma isso em
caminho de promoção a presente. Normativo: `raw_status=` recebe **somente token bruto de situação
PT-BR** (AC 24a); um estado já carimbado, se algum dia chegar, entra por caminho separado validado
como `state in ACTIVITY_STATES`, senão `UNKNOWN`.

**A5 — ACs 5, 32 e 24a são test-only: não há alcançabilidade em produção hoje (escalado ao @po).**
Medido: nenhum produtor emite `situacao`/`status`/`situacao_nome` por contrato no bag
(`strict_national_esr._contracts_from_account` emite `objeto_contrato`/`data_inicio`/`data_fim`,
sem situação); `status_normalized` existe **apenas** dentro de `contracts_truth.py` e da tabela do
datalake, e nunca chega a `normalize.py`. Em produção, `status_raw` é NULL em 100% das linhas de
`public.pncp_supplier_contracts` e há **zero** CANCELLED/TERMINATED/SUSPENDED. Consequência: o
repasse da AC 24a é código correto **sem input vivo**; `TERMINATED`/`CANCELLED`/`SUSPENDED`
permanecem inalcançáveis por dado real. **Isto não quebra a story** — a Regra 8 degrada para
`UNKNOWN` e a meta de segurança se sustenta com mais folga em produção (tudo cai em
COMPLETED-por-vigência ou UNKNOWN). Mas @qa só consegue verificar essas ACs por teste unitário.
Obrigatório: (a) declarar a limitação no Dev Agent Record; (b) registrar follow-up referenciando o
defeito de `stamp_contract_truth_labels` / `status_observed_at`; (c) @po e @qa devem ler cobertura
verde dessas ACs como cobertura **de mecanismo**, não de produção. **Não** expandir escopo para
plumbar `status_normalized` até o bag — isso é blast radius de crawler/projeção e pertence ao
trabalho de lifecycle-truth.

**A6 — Recomendado (não normativo; vira AC 34 a critério do @po):** propagar
`ContractActivity.rule_version` para o resultado da política (campo próprio ou dentro de
`reason_codes`). É a mitigação direta do drift que a própria story teme (rótulo do crawler vs.
derivação do outbound): sem isso, uma mudança futura em `contracts_truth` altera o comportamento de
copy sem deixar rastro auditável na mensagem gerada.

**A7 — Nota anti-falso-positivo de QA:** o `date.today()` de `normalize.py:59` (resolução do
`as_of` do registro) é **pré-existente e fora de escopo**. A AC 33 vincula o módulo novo e o
argumento `today=` de `classify_contract_activity` — não a resolução própria de `as_of` do
`normalize.py`. Não abrir FAIL de AC 33 por essa linha.

**Segurança de `normalize.py` (pergunta 4 do @po) — CONFIRMADA SEGURA.** Adicionar
`lifecycle_state` (e ler chaves de status) ao dict de contrato normalizado não quebra consumidor
algum, por três evidências independentes em HEAD:
1. `pipeline.py:92` computa `source_hash = stable_source_hash(enriched)` **antes** de
   `normalize_record` (linha 93) — o hash é do payload bruto enriquecido, não do normalizado. Campo
   novo no dict normalizado **não** perturba `source_hash` nem `cache_key`.
2. O JSON schema `confenge-account-intelligence-v1` declara `additionalProperties: true`, e
   `schema.py::validate_dossier` só verifica presença de chaves top-level obrigatórias — nada
   valida a forma do dict de contrato.
3. Todos os consumidores do dict (`approach.py`, `router.py`, `structure.py`, `facts.py`,
   `message_spine.py`) leem chaves específicas via `.get(...)`; nenhum itera chaves nem compara
   dicts inteiros. `tests/confenge_account_intelligence/test_pipeline_golden.py` só assere
   estabilidade run-a-run (`d1[...] == d2[...]`), sem valor de hash pinado.

### Mapa de call sites e assinaturas a preservar

- `extract_contract_hook(bag)` — único call site: `message_spine.py:486`, dentro de `build_message_spine`. Verificado por grep no repositório inteiro (`scripts/` e `tests/`) — reconfirmado pelo @po na validação. (A cópia em `.campaign/overnight/extra-cli/` é snapshot de campanha, não um consumidor.)
- **Home da seleção de hook (resolução do import circular):** `extract_contract_hook` permanece em `message_spine.py` e ganha `purpose` keyword-only. O pacote `confenge_claim_policy` **não** conhece o formato do `bag` do message_spine e não importa nenhum dos 4 arquivos de integração (AC 23a).
- `CopyContextResult` / `EmailSendReadyResult` (`send_readiness.py:309-366`) são `@dataclass(frozen=True)` — qualquer lógica de rebaixamento decide o valor **antes** de instanciar, não via `dataclasses.replace` pós-hoc escondido (embora `replace` seja aceitável se usado de forma explícita e testada — o ponto é não confiar em mutação, que nem é possível em frozen dataclass).
- `evaluate_copy_context_ready` (`send_readiness.py:839`) já rejeita `why_now_strength == "WEAK"` (linhas 927-931) — este comportamento não muda; `FACTUAL_CLAIM_SAFE` é aditivo/subtrativo conforme o invariante de monotonicidade.

### Freeze de campanha — comando de verificação

Consultar `scripts/ops/confenge_frozen_inputs.py::discover_frozen_input_paths`. Precedente documentado (mesma mecânica, outro pacote novo): `docs/stories/story-outbound-sector-classifier-false-positive-01.md`, seção AC 20(a) — fechamento transitivo de imports locais sob `scripts/` pode capturar um arquivo novo mesmo sem edição de arquivo congelado pré-existente, bastando ser importado por um deles.

### Testing

- Localização: `tests/confenge_claim_policy/` (novo diretório, espelhando o padrão de `tests/confenge_universe/`, `tests/commercial_leads/`) para o módulo puro; testes de integração nos diretórios existentes (`tests/confenge_account_intelligence/` se existir, senão criar seguindo o mesmo padrão; `tests/commercial_leads/` ou `tests/confenge_contact_resolution/` para `send_readiness.py` — verificar padrão existente antes de criar).
- Framework: `pytest`, sem mocks de banco/rede (módulo é puro; integrações usam dicts/dataclasses in-memory).
- Cada um dos 7 casos red-team deve ter um teste nomeado individualmente (não agrupado em um único teste parametrizado sem nomes claros), para rastreabilidade direta com este documento.
- Comando de execução completa: `python3 -m pytest tests/ -q --tb=no -x`.

## Change Log

| Date | Version | Description | Author |
|------|---------|--------------|--------|
| 2026-09-01 | 0.4.1 | **Correção de QA (@dev) — MED-001 fechado, LOW-002 e LOW-003 tratados. Status permanece InReview (re-validação é do @qa).** MED-001: o fallback de `raw_status` em `resolve_lifecycle_state` deixou de rotear para o caminho de estado carimbado sem restrição. Introduzido `RAW_STATUS_FALLBACK_STATES = ACTIVITY_STATES − {ACTIVE_PROVEN}` — um `raw_status` textual só pode adotar estados **seguros por natureza** (`COMPLETED`, `TERMINATED`, `CANCELLED`, `SUSPENDED`, `UNKNOWN`); quando ele soletra `ACTIVE_PROVEN`, o token é **recusado e descartado** (`raw_status=None`) e a decisão volta inteiramente para `classify_contract_activity`, que exige janela de vigência real. Rastro auditável: reason code novo `raw_status_state_name_not_promotable`, **anexado ao fim** de `reasons` (não prepend, para não perturbar consumidores de `lifecycle_reasons`). `ACTIVE_PROVEN` passa a ser alcançável apenas por `stamped_state=` explícito (caminho confiável definido pelo item normativo A4) ou por evidência datada — restaurando literalmente o invariante da story: **a derivação só pode rebaixar (demote), nunca promover (promote)**, e a Regra 7 (hard gate factual nunca vencido por score) deixa de ter porta lateral. Probe do QA reproduzido como teste e agora falha-fechado: `normalize_record` com `situacao="active_proven"` e zero datas → `lifecycle_state=UNKNOWN` → `allowed_tense != PRESENT_CONFIRMED`, `outreach_use_class != CURRENT_ACTIONABLE`. LOW-003: `test_a4_stamped_state_never_enters_raw_status` renomeado para `test_a4_stamped_state_takes_the_validated_path_and_never_degrades` e a asserção que pinava o defeito (linha 274) foi **removida e substituída** pelos dois testes de regressão novos (`test_med001_raw_status_spelling_active_proven_never_promotes`, unitário e exaustivo nos grafemas/estados; `test_med001_normalize_record_probe_cannot_reach_present_confirmed`, end-to-end pelo caminho exato do probe do QA). LOW-002: o assert vazio de `test_red_team_cases.py:108` foi substituído por asserções materiais em **ambos** os ramos (chave presente → `UNKNOWN` + tempo não-presente; chave ausente → só tolerada para o fallback documentado `trigger == "portfolio_review"`), mais checagem de que o `temporal_fact` não contém linguagem de presente. LOW-001 e LOW-004 **não** tocados (decisão de wording/escopo do @po). Evidência: `ruff check` + `ruff format --check` limpos; mypy 2.3.1 (venv descartável) sem erro nos arquivos tocados; escopo `tests/confenge_claim_policy/ tests/confenge_contact_resolution/ tests/confenge_account_intelligence/` = **263 passed** (261 → 263, +2 testes novos, zero quebras). | Dex (@dev) |
| 2026-09-01 | 0.4.0 | **QA Gate (@qa) — veredito CONCERNS.** Revisão independente sobre `9a07228a` + working tree. Verificado por re-execução, não por leitura do Dev Agent Record: ruff limpo nos 3 pacotes; 261 passed em `tests/confenge_claim_policy/`+`tests/confenge_contact_resolution/`+`tests/confenge_account_intelligence/`; suíte completa `134 failed, 5575 passed, 261 skipped, 53 errors` — **idêntica número a número** ao baseline do @dev, mesmo com HEAD já avançado para `9a07228a`; AC 30 **re-medida pelo QA** em worktree limpo do HEAD atual (161 → 166, +4 atribuíveis confirmados). Os 7 casos red-team foram lidos linha a linha e têm assert material. Desvio #3 do @dev (`demote_to_historical` no fail-closed de múltiplos CURRENT) julgado **interpretação válida de "rewrite" (AC 21)** — não retorna ao @po. Monotonicidade (AC 27) confirmada estruturalmente: o gate só faz `missing.append`, e `ready = len(missing) == 0`. Contaminação de árvore **resolvida** — `publish.py` foi commitado em `9a07228a` e não está no diff desta story. Probes adversariais próprios do QA encontraram **MED-001**: `resolve_lifecycle_state` roteia `raw_status` para o caminho de estado carimbado, de modo que `normalize_record` com `situacao="active_proven"` e zero datas produz `ACTIVE_PROVEN` → `PRESENT_CONFIRMED`, contornando `classify_contract_activity`. Inalcançável em produção hoje (nenhum produtor emite situação por contrato — A5 reconfirmada pelo QA), mas **bloqueia o follow-up de lifecycle-truth** já declarado. Mais LOW-001 (`_cap_from_why` devolve `None` e deixa o branch de passthrough sem teto), LOW-002 (assert vaziano red-team 3) e LOW-003 (`test_a4_stamped_state_never_enters_raw_status` pina o oposto do que o nome afirma). Status permanece **InReview** — fechamento é autoridade do @po. | Quinn (@qa) |
| 2026-09-01 | 0.3.0 | **Implementação (@dev).** Transições de status registradas nesta entrada: **Ready → InProgress** (início da implementação) e **InProgress → InReview** (implementação concluída, aguardando @qa). Criado o pacote puro `scripts/confenge_claim_policy/` consumindo `scripts/contracts_truth.py` como autoridade única de lifecycle (AC 31-33); integrações cirúrgicas em `normalize.py` (campo `lifecycle_state` + repasse de `raw_status`), `facts.py` (pain-check `addendum` passa a depender do lifecycle), `message_spine.py` (`purpose` em `extract_contract_hook`, cap de força temporal por CLAIM_POLICY em `_extract_temporal_event`, campo `claim_policy` no spine) e `send_readiness.py` (`FACTUAL_CLAIM_SAFE`, subtrativo por construção). Itens normativos A1-A4 do gate de arquitetura implementados. Delta de freeze medido e declarado (AC 30), incluindo **correção factual à predição do @architect**: `contracts_truth.py` **tem** fechamento transitivo (`scripts/crawl/observation_lineage.py`, import de nível de função na linha 1115), logo o delta é +4 e não +3. Desvios declarados no Dev Agent Record (AC 15 vs AC 23; demote-to-historical em vez de bloqueio total da mensagem no fail-closed de múltiplos CURRENT). | Dex (@dev) |
| 2026-09-01 | 0.2.1 | **Task 2a (gate de arquitetura) executada — veredito APROVADO COM RESSALVAS.** Nenhuma AC alterada. Adicionada seção "Architecture Gate (Task 2a)" em Dev Notes com 4 itens normativos que fixam escolhas deixadas em aberto pelas ACs (A1 `evaluated_as_of` é `date`, não string — `classify_contract_activity` compara `end < ref` sem parsear `today`, e `normalize.py:59` produz string ISO: TypeError garantido se cruzar a fronteira; A2 encoding pinado de `copy_hash` = `sha256(body.encode("utf-8"))` sem normalização unicode, pois a story irmã fixa golden vector sobre ele; A3 AC 21 resolve para lista vazia + `reason_codes`, não exceção, por estar em caminho de envio real; A4 nunca alimentar nome de estado em `raw_status=` — 4 de 5 estados terminais casam por coincidência dos tokens em inglês e `ACTIVE_PROVEN` degrada em silêncio). Escalado ao @po: **A5 — ACs 5, 32 e 24a não têm alcançabilidade em produção hoje** (nenhum produtor emite situação por contrato no bag; `status_normalized` nunca chega a `normalize.py`; `status_raw` NULL em 100% da prod, zero CANCELLED/TERMINATED/SUSPENDED) — são test-only, exigem declaração no Dev Agent Record e follow-up, sem expandir escopo. Recomendado (vira AC 34 a critério do @po): A6 propagar `ContractActivity.rule_version` como rastro anti-drift. Confirmada como **segura** a alteração de `normalize.py` (pergunta 4 do @po): `source_hash` é computado antes de `normalize_record` (pipeline.py:92 vs 93), schema tem `additionalProperties: true`, e nenhum consumidor itera chaves. Corrigida afirmação da seção Riscos: `contracts_truth.py` importa só stdlib, seu fechamento transitivo é ele mesmo — delta de freeze previsto = 162 + N(`confenge_claim_policy/*`) + 1. **Próximo agente: @dev.** | Aria (@architect) |
| 2026-09-01 | 0.2.0 | Validada GO (8/10 pré-correção) — Status: Draft → Ready. Quatro defeitos encontrados por verificação factual contra HEAD e corrigidos nesta versão: (1) **mandato de reuso** de `scripts/contracts_truth.py`, que já define `ACTIVITY_STATES` e `classify_contract_activity` com a exata precedência demote-only pedida — a v0.1.0 criava taxonomia paralela (novas AC 31, 33; Dev Notes reescritas); (2) **import circular** entre `confenge_claim_policy` e `message_spine` implícito nas Task 1/Task 4 — resolvido fixando a home do hook em `message_spine` e a dependência como unidirecional (AC 23 reescrita, AC 23a nova); (3) **`SUSPENDED` omitido** do vocabulário apesar de existir em `ACTIVITY_STATES` e ser alcançável pelo dado do crawler (AC 32 nova); (4) **fato de code-freeze medido**: `message_spine.py` e `send_readiness.py` **já** estão entre os 162 caminhos congelados, e `contracts_truth.py` não está — AC 30 reescrita para exigir declaração do delta completo. Adicionalmente: precedência AC 7 > AC 3 explicitada (conflito latente), aresta reversa para `story-current-claim-jit-authority-01` registrada, **risk level escalado STANDARD → HIGH-RISK** (decisão que o @sm delegou explicitamente ao @po). Correções de consistência entre as próprias ACs novas: AC 24 reescrita como tabela do comportamento real de `classify_contract_activity` (a v0.1.0 exigia `COMPLETED` para `end_date` passado, mas a função retorna `UNKNOWN` quando `start_date` é `None` — contradição direta com a AC 31); AC 24a nova (repasse de `raw_status` em `normalize.py`, sem o qual `TERMINATED`/`CANCELLED`/`SUSPENDED` são inalcançáveis por derivação); AC 23b nova (hollowness entra como booleano do chamador, evitando que a AC 23a force duplicação de `is_hollow_fact`). **Próximo agente: @architect (Task 2a), não @dev.** | Pax (@po) |
| 2026-09-01 | 0.1.0 | Story criada via `create-next-story.md` a partir de contexto fornecido diretamente (sem epic/PRD de origem) e auditoria de HEAD de `facts.py`, `normalize.py`, `message_spine.py`, `send_readiness.py`. Revisão incorporada de advisor: cobertura do segundo site do bug em `message_spine.py::_extract_temporal_event`, invariante de monotonicidade de send-readiness, verificação de code-freeze para pacote novo, contrato de pureza explícito, backward-compatibility de `extract_contract_hook`. | River (SM) |

## Dev Agent Record

### Agent Model Used

Claude Opus 5 (`claude-opus-5[1m]`) atuando como @dev (Dex), modo YOLO autônomo.

### Debug Log References

- Suíte completa: `python3 -m pytest tests/ -q --tb=no -o addopts='-m "not slow"' --continue-on-collection-errors --ignore=tests/test_official_status_reconfirmation.py`
  - **Nota de ambiente (pré-existente, não introduzida por esta story):** `pytest.ini` declara `addopts = --cov=...`, mas `pytest-cov` **não está instalado** neste ambiente — o comando canônico `python3 -m pytest tests/ -q --tb=no` da story aborta com `unrecognized arguments: --cov`. Além disso, `tests/test_official_status_reconfirmation.py` faz `import collect_report_data`, que executa `sys.exit(1)` no import e derruba a coleta inteira do pytest com `INTERNALERROR`. Ambos são anteriores a esta story.
- **Suíte completa, resultado final: `134 failed, 5575 passed, 261 skipped, 11 deselected, 53 errors`.** As 134 falhas e os 53 erros de coleta são **idênticos** ao baseline medido antes da implementação (ambiente sem DB/rede, árvore suja com outras stories). Diff nominal de IDs de teste entre a rodada intermediária e a final: as **únicas** duas falhas atribuíveis a esta story (`tests/confenge_activation/test_strict_national_esr_and_service_ontology.py::test_message_spine_makes_copy_context_ready` e `::test_pilot_review_has_full_identity_evidence_message_and_human_gate`) foram encontradas e corrigidas antes do fechamento — causadas pelo fail-closed de múltiplos CURRENT bloqueando a mensagem inteira, resolvido com `demote_to_historical` (ver Desvios). **Zero regressões remanescentes atribuíveis a esta story (AC 29 satisfeita).**
- Escopo verde (determinístico, 349 testes): `tests/confenge_claim_policy/ tests/confenge_account_intelligence/ tests/confenge_contact_resolution/ tests/dossier tests/confenge_outreach_pipeline` → **349 passed**.
- Importadores dos módulos tocados fora desses diretórios (evidência direta de AC 29): 13 arquivos selecionados por `grep -rl -e confenge_account_intelligence -e send_readiness -e confenge_claim_policy -e contracts_truth tests/` → **180 passed, 12 skipped, 1 failed**. A única falha é `tests/commercial_leads/test_confenge_integrity_gates.py::test_rebound_freeze_drives_shipped_verifiers_on_campaign_tree` (`BLOCKED_CODE_EXECUTION_SHA_MISMATCH`), **reproduzida em worktree limpo de HEAD** — falha pré-existente, não regressão desta story.
- Lint: `python3 -m ruff check scripts/ tests/` → **All checks passed**. `ruff format` aplicado aos arquivos novos.
- Typecheck: `mypy` **não está instalado** no ambiente e `pip install --user mypy` é bloqueado por PEP 668. Rodado a partir de venv descartável (`mypy 2.3.1`), com o `pyproject.toml` do repositório. Resultado: **nenhum erro novo** — `send_readiness.py` 24 → 24 erros (o único erro introduzido foi corrigido em `_claim_policy_from_company`); `message_spine.py:214 unreachable` é o `return "", []` pré-existente (linha 113 em HEAD, verificado por worktree limpo); erros em `contracts_truth.py` e `crawl/observation_lineage.py` são pré-existentes e fora de escopo.

### Completion Notes List

#### Decisões de implementação

1. **Cap de força temporal STRONG → MODERATE (não STRONG → WEAK).** Em `_extract_temporal_event`, quando o lifecycle não autoriza presente, a força é rebaixada para `MODERATE` com o texto neutro já existente ("Marco contratual datado no portfólio…", "Registro público com data verificável…") em vez de `WEAK`. Isso satisfaz literalmente as AC 4/14/25 (`why_now_strength` não é `STRONG` só por causa da data; nenhum texto presente-ish é emitido) **sem** destruir `MessageSpine.complete` para contratos datados porém não comprovados — que é a esmagadora maioria do dado de produção (ver A5). `DO_NOT_CITE` continua rebaixando a `WEAK`. Consequência verificável: **zero fixtures existentes quebraram** (`tests/confenge_account_intelligence/` 46/46 verdes sem edição).
2. **`has_contemporary_event` usa janela de 180 dias** (`CONTEMPORARY_EVENT_DAYS`), não "existe qualquer data". Sem isso, a Regra 2 ("`ACTIVE_PROVEN` isolado não basta") seria vazia — todo `ACTIVE_PROVEN` tem datas de vigência por construção — e `FACTUAL_CLAIM_SAFE` nunca dispararia.
3. **A1** — `evaluated_as_of` é `datetime.date` em toda a fronteira; `evaluate_claim_policy` e `resolve_lifecycle_state` levantam `TypeError` para string (teste `test_a1_evaluated_as_of_must_be_a_real_date_not_a_string`). A conversão da string ISO acontece nos chamadores (`facts._as_of_date`, `message_spine._bag_as_of`).
4. **A2** — `compute_copy_hash` = `"sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()`, sem normalização unicode, sem `strip()`, sem canonicalização de newline. Pinado por teste contra `hashlib` direto.
5. **A3** — `select_message_claims` retorna `MessageClaimSelection` com `claims=()` + `reason_codes`, nunca exceção.
6. **A4** — `resolve_lifecycle_state` separa **estado carimbado** (validado por `state in ACTIVITY_STATES`, caminho próprio) de **token bruto** (vai para `raw_status=` de `classify_contract_activity`). Fecha a degradação silenciosa de `ACTIVE_PROVEN` (teste `test_a4_stamped_state_never_enters_raw_status`).
7. **A6 (recomendação do @architect, adotada)** — `ClaimPolicyResult` propaga `lifecycle_rule_version` (de `ACTIVITY_RULE_VERSION`) e `policy_version`, e `normalize.py` emite `lifecycle_rule_version`/`lifecycle_reasons` por contrato. Rastro anti-drift disponível sem custo.

#### Desvios do plano original (com justificativa)

- **AC 15 vs AC 23 — `why_you` mantém a seleção atual (primeiro contrato com objeto ≥ 24 chars), não "o maior".** A AC 23 exige resultado **idêntico** ao de HEAD quando `extract_contract_hook(bag)` é chamado sem `purpose`; qualquer troca do critério de seleção (ex.: maior valor) mudaria o resultado default para bags cujo primeiro contrato não é o maior, violando AC 23. A AC 15 diz que `why_you` **pode** usar o maior histórico — permissivo, não obrigatório. Resolução: AC 23 prevalece (é a restrição dura); `purpose="why_now"` é onde a divergência real acontece, filtrando por `CURRENT_ACTIONABLE` + `why_now_eligible`. O teste red-team 4 comprova a divergência de propósito com o histórico grande em primeira posição.
- **Fail-closed de múltiplos CURRENT não mata a mensagem inteira.** `select_message_claims` é fail-closed conforme a AC 21 (retorna lista vazia). Porém `_spine_claim_policy` **não** propaga isso como bloqueio total: quando há 2+ `CURRENT_ACTIONABLE`, o candidato mais forte é **rebaixado a claim histórico seguro** (`demote_to_historical`, tempo `NEUTRAL_FACTUAL`, `requires_current_authority=False`) com `multiple_current_claims_fail_closed` nos `reason_codes`. Motivo: sem isso, uma carteira multi-contrato ativa (caso comum, ex.: perfil `national_structured`) perderia `COPY_CONTEXT_READY` inteira por um motivo que a AC 21 não pede — a AC 21 exige "máximo 1 claim CURRENT por mensagem", não "nenhuma citação". A monotonicidade (AC 27) segue satisfeita: o rebaixamento só subtrai o direito ao presente, nunca adiciona send-readiness. Coberto por `test_two_active_contracts_demote_to_historical_instead_of_killing_the_message`.
- **`facts.py::_claim_policy_for_contract` importa `is_hollow_fact` de `message_spine` (import local, dentro da função).** É o cumprimento da AC 23b: hollowness continua com dono único em `message_spine.py`; o pacote puro nunca inspeciona texto. O import local evita qualquer ordem de import problemática entre módulos do mesmo pacote de integração (não há ciclo: `message_spine` não importa `facts`).
- **`MessageSpine` ganhou o campo `claim_policy: dict` (default vazio) e `CopyContextResult`/`EmailSendReadyResult` ganharam `factual_claim_safe: bool = True`.** Todos com default, para não quebrar construtores existentes. Verificado que nenhum teste compara `as_dict()` inteiro por igualdade, e que o schema `confenge-account-intelligence-v1` tem `additionalProperties: true`.

#### Limitação real encontrada (nota A5 do @architect — confirmada)

- **ACs 5, 32 e 24a são cobertura de mecanismo, não de produção.** O repasse de `raw_status` implementado em `normalize.py` (`c.get("situacao") or c.get("status") or c.get("situacao_nome")`) está correto, mas **nenhum produtor emite essas chaves por contrato no bag** hoje. Consequência: `TERMINATED`/`CANCELLED`/`SUSPENDED` permanecem **inalcançáveis por dado real**; em produção tudo degrada para `COMPLETED` (por vigência encerrada) ou `UNKNOWN`. Isso **não** enfraquece a meta de segurança da story — ambos os estados já proíbem o presente pelas Regras 3/4 — mas @qa e @po devem ler a cobertura verde dessas ACs como cobertura **do mecanismo**, não de produção.
- **Follow-up registrado (não executado nesta story, fora de escopo):** plumbar `status_normalized` / `status_observed_at` carimbados por `contracts_truth.stamp_contract_truth_labels` até o bag de `normalize.py`. Blast radius de crawler/projeção — pertence ao trabalho de lifecycle-truth, não a esta story.
- **Observação adicional:** `normalize.py` também aceita um estado já carimbado via `lifecycle_state` / `activity_state` / `status_normalized` no payload bruto (caminho validado por `state in ACTIVITY_STATES`, conforme A4). Quando o follow-up acima for feito, a política já estará pronta para consumi-lo sem alteração.

#### AC 30 — verificação de code-freeze de campanha (bloqueia push, não bloqueia dev)

Medição com `scripts/ops/confenge_frozen_inputs.py::discover_frozen_input_paths`, comparando um **worktree limpo de HEAD** (`git worktree add --detach`) contra a árvore de trabalho:

| Medição | Total |
|---|---|
| HEAD limpo (`6c7bb0ea`) | **161** |
| Árvore de trabalho após esta story | **166** |

Delta completo (nenhuma remoção):

| Caminho adicionado | Atribuível a esta story? |
|---|---|
| `scripts/confenge_claim_policy/__init__.py` | **SIM** (pacote novo) |
| `scripts/confenge_claim_policy/policy.py` | **SIM** (pacote novo) |
| `scripts/contracts_truth.py` | **SIM** (puxado por import do pacote novo) |
| `scripts/crawl/observation_lineage.py` | **SIM** (fechamento transitivo de `contracts_truth.py`) |
| `scripts/confenge_universe/parafiscal.py` | **NÃO** — arquivo não rastreado de outra story em andamento na mesma árvore |

**Correção factual à predição do gate de arquitetura.** A seção "Architecture Gate (Task 2a)" prevê `delta = 162 + N(confenge_claim_policy/*) + 1`, com a justificativa de que "`contracts_truth.py` não arrasta fechamento transitivo — seus imports são stdlib-only, então seu fechamento é ele mesmo". **Isso é falso em HEAD:** `scripts/contracts_truth.py:1115` contém `from scripts.crawl.observation_lineage import attach_lineage, lineage_from_envelope` — um import **de nível de função**, que a inspeção de imports de nível de módulo não vê, mas que `discover_frozen_input_paths` captura. Delta real desta story = **+4** (`confenge_claim_policy/__init__.py`, `confenge_claim_policy/policy.py`, `contracts_truth.py`, `crawl/observation_lineage.py`). `scripts/crawl/observation_lineage.py` importa apenas stdlib, então o fechamento para aqui. `facts.py` e `normalize.py` **permanecem fora** do conjunto congelado, como previsto.

**Sequência de publicação (confirmada, a executar pelo @devops — push está fora da autoridade do @dev):** 2 PRs, **sem squash**:
1. **PR de código** — os 10 arquivos da File List abaixo.
2. **PR artifact-only de re-freeze** — entradas **novas** no manifesto para `scripts/confenge_claim_policy/__init__.py`, `scripts/confenge_claim_policy/policy.py`, `scripts/contracts_truth.py` e `scripts/crawl/observation_lineage.py`; **rebind** para `scripts/confenge_account_intelligence/message_spine.py` e `scripts/confenge_contact_resolution/send_readiness.py` (ambos já congelados e editados nesta story).

Nota operacional para o @qa: `tests/commercial_leads/test_confenge_integrity_gates.py::test_rebound_freeze_drives_shipped_verifiers_on_campaign_tree` já falha em HEAD limpo (`BLOCKED_CODE_EXECUTION_SHA_MISMATCH`) — é falha pré-existente, independente desta story, e não deve ser lida como consequência do delta acima.

#### Aviso à story irmã

`copy_hash` ficou pinado como `"sha256:" + sha256(body.encode("utf-8")).hexdigest()` — **com o prefixo `sha256:`**. `story-current-claim-jit-authority-01`, que fixa golden vector de `attestation_hash` sobre este valor, deve usar `compute_copy_hash` (exportado por `scripts.confenge_claim_policy`) e não re-derivar o hash, para não divergir no prefixo.

#### Contaminação de árvore observada (não é trabalho desta story)

Durante a sessão, `scripts/confenge_activation/publish.py` recebeu +35 linhas (`CLAIM_SAFETY_ROLLBACK_ANCHOR_KEY`, `claim_safety_hash` em `publication_semantic_hash`) que **não** foram escritas por esta story — o arquivo pertence ao escopo OUT (`story-current-claim-jit-authority-01`). Não foi tocado nem revertido. O @devops deve garantir que ele **não** entre no PR de código desta story.

#### Correção pós-QA (iteração 1) — MED-001, LOW-002, LOW-003

*Aplicada em 2026-09-01 sobre o gate CONCERNS 0.4.0. Status mantido em **InReview** — a
re-validação é autoridade do @qa. LOW-001 e LOW-004 **não** foram tocados: são decisão de
wording/escopo do @po.*

**MED-001 (porta de promoção via `raw_status`) — FECHADO.**

Antes, `resolve_lifecycle_state` roteava qualquer `raw_status` que soletrasse um nome de
`ACTIVITY_STATES` para o caminho de estado carimbado, sem restrição — inclusive
`ACTIVE_PROVEN`. Agora:

```python
RAW_STATUS_FALLBACK_STATES = frozenset(ACTIVITY_STATES) - {ACTIVE_PROVEN}
```

- `raw_status` textual só adota estados **seguros por natureza** (`COMPLETED`,
  `TERMINATED`, `CANCELLED`, `SUSPENDED`, `UNKNOWN`) — nenhum deles habilita
  `CURRENT_ACTIONABLE`/`PRESENT_CONFIRMED`.
- `raw_status="ACTIVE_PROVEN"` (em qualquer caixa/espaçamento) é **recusado e descartado**;
  a decisão volta inteiramente para `classify_contract_activity`, que exige janela de
  vigência real. Um contrato que soletra `active_proven` **e** tem vigência válida continua
  legitimamente `ACTIVE_PROVEN` — a evidência datada é que promove, nunca o texto.
- `ACTIVE_PROVEN` passa a ser alcançável por exatamente dois caminhos: `stamped_state=`
  explícito (o canal confiável que o item normativo A4 designou) ou a evidência datada de
  `classify_contract_activity`.
- Rastro auditável: reason code novo `raw_status_state_name_not_promotable`
  (`REASON_RAW_STATUS_NOT_PROMOTABLE`), **anexado ao fim** de `reasons` — nunca prepend,
  para não perturbar quem consome `lifecycle_reasons` (`normalize.py:212`) por posição.
- Invariante restaurado literalmente: **a derivação só pode rebaixar (demote), nunca
  promover (promote)**; a Regra 7 (hard gate factual nunca vencido por score) fica sem
  porta lateral.

**LOW-003 — teste que pinava o defeito, corrigido.**
`test_a4_stamped_state_never_enters_raw_status` foi renomeado para
`test_a4_stamped_state_takes_the_validated_path_and_never_degrades` e a asserção da antiga
linha 274 (`raw_status="ACTIVE_PROVEN"` → `ACTIVE_PROVEN`) foi removida. No lugar dela,
dois testes de regressão que pinam a **guarda**, não o defeito:

| Teste | O que pina |
|---|---|
| `test_med001_raw_status_spelling_active_proven_never_promotes` | Unitário: três grafemas de `ACTIVE_PROVEN` → `UNKNOWN` + reason de recusa; todos os estados de `RAW_STATUS_FALLBACK_STATES` continuam adotáveis; `stamped_state=` intacto; evidência datada ainda promove |
| `test_med001_normalize_record_probe_cannot_reach_present_confirmed` | **End-to-end pelo caminho exato do probe do @qa**: `normalize_record` com `situacao="active_proven"` e zero datas → `lifecycle_state=UNKNOWN` → `allowed_tense != PRESENT_CONFIRMED`, `outreach_use_class != CURRENT_ACTIONABLE`, `allows_present_tense() is False` |

**LOW-002 — assert vazio do red-team 3, corrigido.**
`why.get("lifecycle_state", "UNKNOWN") == "UNKNOWN"` passava vacuamente. Substituído por
asserções materiais nos **dois** ramos: chave presente → precisa ser `UNKNOWN` com tempo
não-presente e `outreach_use_class != CURRENT_ACTIONABLE`; chave ausente → só tolerado no
fallback documentado (`trigger == "portfolio_review"`, sem `outreach_use_class`). Mais uma
checagem de que o `temporal_fact` não carrega linguagem de presente. Nenhum dos dois ramos
passa de graça.

**Residual declarado (não corrigido — fora de escopo desta iteração).**
`normalize.py:196` ainda alimenta `stamped_state=` a partir do mesmo dict não-confiável
(`c.get("lifecycle_state") or c.get("activity_state") or c.get("status_normalized")`), logo
um payload com `{"lifecycle_state": "ACTIVE_PROVEN"}` e zero datas ainda promove — por
outra chave. **Deliberadamente não alterado:** o item normativo A4 designa `stamped_state=`
como o caminho confiável validado, e a própria recomendação do @qa é "restringir o caminho
carimbado a `stamped_state=`". Fica **vinculado ao follow-up de lifecycle-truth** já
declarado (plumbar `status_normalized`/`status_observed_at` até o bag): é exatamente quando
essas chaves passam a ser preenchidas que a confiabilidade da fonte precisa ser decidida
junto com a origem do carimbo. Registrado aqui para que o @qa não o encontre como MED novo
na re-validação.

**Evidência desta iteração:**

- `python3 -m ruff check scripts/confenge_claim_policy/ tests/confenge_claim_policy/` → **All checks passed**; `ruff format --check` → 6 files already formatted.
- mypy 2.3.1 (venv descartável — `mypy` não está instalado no ambiente e `pip install --user` é bloqueado por PEP 668): **zero erro nos arquivos tocados**. Os 3 erros reportados são pré-existentes e fora de escopo (`scripts/contracts_truth.py:275`, `:995`; `scripts/crawl/observation_lineage.py:79`).
- Escopo da story: `pytest tests/confenge_claim_policy/ tests/confenge_contact_resolution/ tests/confenge_account_intelligence/ -q -o addopts=''` → **263 passed** (era 261 no gate do @qa; +2 testes novos, zero quebras).
- Escopo ampliado (+ `tests/dossier tests/confenge_outreach_pipeline tests/confenge_activation`) → **425 passed**.
- Importadores dos módulos tocados (`grep -rl` em `tests/`) → **334 passed, 12 skipped, 1 failed**; a única falha é `test_rebound_freeze_drives_shipped_verifiers_on_campaign_tree`, pré-existente em HEAD limpo e já documentada pelo @dev e pelo @qa.
- **Delta de freeze inalterado** (nenhum arquivo novo, nenhum import novo): o conjunto declarado no AC 30 permanece válido. A re-medição imediatamente antes do PR de re-freeze continua obrigatória (HEAD é móvel).

### File List

**Novos:**

- `scripts/confenge_claim_policy/__init__.py`
- `scripts/confenge_claim_policy/policy.py`
- `tests/confenge_claim_policy/__init__.py`
- `tests/confenge_claim_policy/test_claim_policy_rules.py`
- `tests/confenge_claim_policy/test_red_team_cases.py`
- `tests/confenge_claim_policy/test_module_purity_and_boundary.py`
- `tests/confenge_contact_resolution/test_factual_claim_safe.py`

**Modificados:**

- `scripts/confenge_account_intelligence/normalize.py`
- `scripts/confenge_account_intelligence/facts.py`
- `scripts/confenge_account_intelligence/message_spine.py`
- `scripts/confenge_contact_resolution/send_readiness.py`
- `docs/stories/story-outreach-claim-policy-01.md`
- `.aiox/state/stories/story-outreach-claim-policy-01.json`

**Explicitamente NÃO modificados** (escopo OUT): `scripts/contracts_truth.py`, `scripts/ops/confenge_feed_cycle.py`, `scripts/confenge_activation/publish.py`, migrations, feed-cycle, publication pipeline, Warmbly.

## QA Results

### Gate: **CONCERNS** — Quinn (@qa), 2026-09-01

**Revisor independente.** Nenhuma alegação do Dev Agent Record foi aceita sem re-execução.
`reviewed_commit`: `9a07228a` + working tree. Status permanece **InReview** (fechamento é do @po).

#### 1. Lint e testes de escopo — VERIFICADO

```
$ python3 -m ruff check scripts/confenge_claim_policy/ scripts/confenge_account_intelligence/ scripts/confenge_contact_resolution/
All checks passed!            (exit 0)

$ python3 -m pytest tests/confenge_claim_policy/ tests/confenge_contact_resolution/ tests/confenge_account_intelligence/ -q -o addopts=''
261 passed in 3.11s
```

O comando canônico `-k "claim_policy or contract_relevance or claim"` **aborta com `INTERNALERROR`** sem
`--ignore=tests/test_official_status_reconfirmation.py` (`scripts/collect_report_data.py:52` faz `sys.exit(1)`
no import). Falha de ambiente **pré-existente**, confirmada pelo QA — a nota do @dev procede. Com o ignore:
`1 failed, 277 passed, 10 skipped, 43 errors`. A única falha é
`tests/predictive/test_immutability_and_cli.py::test_facade_claims_cli` → `ModuleNotFoundError: No module named 'numpy'`.
Os 43 errors são todos `ModuleNotFoundError` (fastapi, numpy, httpx, hypothesis, reportlab, prometheus_client).
**Nada atribuível a esta story.**

#### 2. Suíte completa — BASELINE CONFIRMADO NUMERICAMENTE

```
$ python3 -m pytest tests/ -q --tb=no -o addopts='-m "not slow"' --continue-on-collection-errors \
    --ignore=tests/test_official_status_reconfirmation.py
134 failed, 5575 passed, 261 skipped, 11 deselected, 53 errors in 374.42s
```

**Idêntico, número a número, ao reportado pelo @dev** — e isso apesar de o HEAD ter avançado de `6c7bb0ea`
(baseline do @dev) para `9a07228a` (`claim-safety-audit-01`, que adicionou `scripts/confenge_claim_safety/` e
uma CLI). AC 29 **satisfeita com evidência independente**.

#### 3. Os 7 casos red-team — LIDOS, NÃO APENAS CONTADOS

`tests/confenge_claim_policy/test_red_team_cases.py` — cada caso é um teste nomeado, com assert material:

| Caso | Teste | Assert real? |
|---|---|---|
| 1 (COMPLETED "em execução") | `test_red_team_1_...cannot_claim_em_execucao` | Sim — `is_tense_permitted(res, PRESENT_CONFIRMED) is False` + `!= CURRENT_ACTIONABLE` |
| 2 (COMPLETED passado) | `test_red_team_2_...past_tense` | Sim — `allowed_tense == PAST_ONLY` |
| 3 (UNKNOWN publicado ontem) | `test_red_team_3_...` | Parcial — ver LOW-002 |
| 4 (why_you vs why_now) | `test_red_team_4_...` + `4b` | Sim — `why_now_ids == ["cf-contract-C-ATIVO"]`, `4b` prova `("", [])` |
| 5 (zero urgência inventada) | `test_red_team_5_...` | Sim — `spine.why_now == ""`, `complete is False` |
| 6 (aditivo de encerrado) | `test_red_team_6_...` + `6b` | Sim — `"recente ou ativo" not in text`, `"encerrado" in text`, `allowed_tense == PAST_ONLY`; `6b` prova o contrafactual ativo |
| 7 (copy_hash muda) | `test_red_team_7_...` | Sim — ver item 6 abaixo |

#### 4. Desvio #3 do @dev (`demote_to_historical` no fail-closed) — **INTERPRETAÇÃO VÁLIDA, NÃO VOLTA AO @po**

- `select_message_claims` (policy.py:421-437) é fail-closed **exatamente** conforme AC 21 + item normativo A3:
  `claims=()` + `reason_codes=("multiple_current_claims_fail_closed",)`, sem exceção. Pinado por
  `test_ac21_two_current_claims_fail_closed_with_empty_list_and_reasons`.
- O rebaixamento acontece **uma camada acima**, em `message_spine._spine_claim_policy` (linhas 590-620), que A3
  nunca governou. AC 21 nomeia **"rewrite obrigatório"** como desfecho aceitável *antes* de "lista vazia"; o
  rebaixamento a `HISTORICAL_CONTEXT` / `NEUTRAL_FACTUAL` / `requires_current_authority=False` **é** um rewrite.
- O invariante vinculante — "nunca mais de um claim CURRENT na mesma mensagem" — é satisfeito com folga: o
  resultado tem **zero** claims CURRENT.
- Monotonicidade preservada (o rebaixamento só retira o direito ao presente). Verificado empiricamente por
  `test_two_active_contracts_demote_to_historical_instead_of_killing_the_message`.

**Sem escalada ao @po.** Registrado aqui para visibilidade no fechamento.

#### 5. Monotonicidade de `send_readiness.py` (AC 27) — **CONFIRMADA POR LEITURA DE CÓDIGO**

`evaluate_copy_context_ready` (send_readiness.py:1013-1030):

```python
claim_safe, claim_reasons = evaluate_factual_claim_safe(company)
reasons.extend(claim_reasons)
if not claim_safe:
    missing.append("factual_claim_safe")
ready = len(missing) == 0
```

O gate **só faz `missing.append`** — nunca remove item de `missing`, nunca força `ready=True`. Como
`ready = len(missing) == 0`, é estruturalmente impossível elevar send-readiness. Em `evaluate_email_send_ready`
(linha 1586) o campo novo entra apenas como `factual_claim_safe=copy_res.factual_claim_safe`, sem participar de
nenhuma condição de decisão. Além disso, `evaluate_factual_claim_safe` retorna `(True, [])` quando não há
veredito de política anexado — payload legado permanece byte-a-byte inalterado. **Nenhum caminho eleva.**

#### 6. `copy_hash` — **TESTADO, NÃO SUPOSTO**

`test_red_team_7_changing_the_copy_body_changes_the_copy_hash` varia **só o corpo** (mesmo `contract_id`, mesmos
`evidence_ids`) e assere `res_a.copy_hash != res_b.copy_hash`. `test_copy_hash_contract_is_pinned_sha256_utf8`
pina contra `hashlib` direto: `"sha256:" + sha256(body.encode("utf-8")).hexdigest()`, sem `strip()`, sem
normalização unicode, sem canonicalização de newline (o corpo do teste inclui `\n` inicial e final).

**Ressalva ao contrato da story irmã:** o valor carrega o prefixo literal `sha256:`. A story mãe (AC 20) diz
apenas "SHA256 do corpo final exato". `story-current-claim-jit-authority-01` está em **Draft** e ainda não
congelou golden vector, então não há quebra — mas ela **deve** importar `compute_copy_hash` de
`scripts.confenge_claim_policy` em vez de re-derivar o digest. Aviso do @dev procede e está registrado.

#### 7. Contaminação de árvore — **RESOLVIDA, ESTA REVISÃO ESTÁ LIMPA**

```
$ git diff --stat HEAD -- scripts/confenge_activation/publish.py
(vazio)
```

As +35 linhas que o @dev observou foram commitadas em `9a07228a` (`claim-safety-audit-01`), que já é HEAD.
`publish.py` **não** está no diff desta story. A árvore ainda carrega ~10 arquivos de outras stories
(`confenge_universe/*`, `commercial_leads/*`, `confenge_target_fit/compute.py`, `parafiscal.py`) — por isso a
evidência de teste desta gate foi colhida em `tests/confenge_claim_policy/`, `tests/confenge_contact_resolution/`
e `tests/confenge_account_intelligence/` (261 passed), diretórios **sem** interseção com o trabalho das outras
stories. **O QA não avaliou código de outra story.**

#### 8. Hard-gate de segurança — **estrutura correta, com UMA porta de promoção encontrada**

**Estruturalmente correto:** em `policy.py::evaluate_claim_policy`, **apenas** o ramo `state == ACTIVE_PROVEN`
(linhas 321-340) devolve `CURRENT_ACTIONABLE` / `PRESENT_CONFIRMED`. `COMPLETED`, `TERMINATED`, `CANCELLED`,
`SUSPENDED` e `UNKNOWN` caem obrigatoriamente no bloco 342-374, que fixa `claim_mode=HISTORICAL_CONTRACT`,
`why_now_eligible=False` e `allowed_tense ∈ {PAST_ONLY, NEUTRAL_FACTUAL}`. A Regra 7 (linhas 302-317) precede
tudo. Além disso, `facts._claim_policy_for_contract` e `message_spine._contract_claim_policy` **leem**
`lifecycle_state` sem derivar — direção conservadora.

**Probes adversariais executados pelo QA (não pelo @dev):**

| Probe | Resultado | Veredito |
|---|---|---|
| `why` de fallback `portfolio_review`/`insufficient_facts` com data → branch `_cap_strength("STRONG", None)` | `MODERATE` — o texto de fallback é `is_hollow_fact()==True`, o branch nunca é alcançado | Seguro hoje (ver LOW-001) |
| `raw_status="Vigente"` sem vigência | `UNKNOWN` (`active_token_without_vigencia`) | demote-only preservado |
| `raw_status="Vigente"` + `end_date` passado | `COMPLETED` | correto |
| **`normalize_record` com `situacao="active_proven"` e ZERO datas** | **`lifecycle_state == "ACTIVE_PROVEN"`**, reason `stamped_lifecycle_state`; `why_now` produz `allowed_tense=PRESENT_CONFIRMED`, `outreach_use_class=CURRENT_ACTIONABLE`, texto `"…contrato público com vigência ativa comprovada."` | **MED-001 abaixo** |

#### Issues

**MED-001 — porta de promoção: `raw_status` entra no caminho de estado carimbado (segurança/design)**

`policy.py:220-232`:

```python
stamped = normalize_lifecycle_state(stamped_state)
if stamped is None:
    stamped = normalize_lifecycle_state(raw_status)   # <-- aqui
    if stamped is not None:
        raw_status = None
if stamped is not None:
    return LifecycleResolution(state=stamped, ..., reasons=(REASON_STAMPED_STATE,))
```

`normalize.py:196` alimenta `raw_status=` a partir de `c.get("situacao") or c.get("status") or c.get("situacao_nome")`
— chaves de **payload bruto**. Um contrato **sem nenhuma data** cujo `situacao` seja a string `active_proven`
(case-insensitive) **contorna `classify_contract_activity` inteiro** e chega a `PRESENT_CONFIRMED`. Isso
contraria o invariante declarado no Estado-alvo e nas Dev Notes ("a derivação **só pode rebaixar**, nunca
promover") e a leitura mais estrita do item normativo A4 ("`raw_status=` recebe **somente token bruto de
situação PT-BR**; um estado já carimbado entra por **caminho separado**"). O @dev aplicou a validação
`state in ACTIVITY_STATES` também ao `raw_status`, o que fecha a degradação silenciosa que A4 temia mas abre a
promoção simétrica que A4 explicitamente antecipou como risco futuro.

*Por que não é FAIL:* verificado independentemente pelo QA que **nenhum produtor vivo** emite essas chaves por
contrato no bag — `strict_national_esr._contracts_from_account` (linhas 105-128) não emite situação/status, e o
`SELECT` de `rebuild_national_funnel.py:392-399` não seleciona nenhuma coluna de status. A5 do @architect
confirmada. Nenhuma AC literal é violada; nenhum caso de produção é afetado hoje.

*Por que precisa de owner:* o follow-up já declarado pelo @dev ("plumbar `status_normalized`/`status_observed_at`
até o bag") é **exatamente** o que torna esta porta viva. Recomendação: restringir o caminho carimbado a
`stamped_state=` e fazer `raw_status=` rejeitar (ou degradar a `UNKNOWN`) qualquer valor que seja nome de estado
de `ACTIVITY_STATES` sem vigência comprovada. **Deve ser resolvido antes do follow-up de lifecycle-truth.**

**LOW-001 — `_cap_from_why` devolve `None` e o branch de passthrough fica sem teto**

`message_spine.py:264` + `291`/`293`: quando o dict `why` não traz `outreach_use_class`, `why_cap=None` e
`_cap_strength("STRONG", None)` devolve `STRONG` sem consultar lifecycle. Hoje inalcançável (os dois únicos
retornos de `facts.why_now` sem chaves de política produzem texto `is_hollow_fact()==True`, e o branch pula
textos hollow — comprovado por probe). É defesa-em-profundidade ausente: um produtor futuro de `why` com
`temporal_fact` datado e não-hollow reabre o segundo site do bug. Recomendação: derivar o cap dos contratos do
`bag` quando `why` não trouxer veredito, e adicionar teste de regressão para o branch.

**LOW-002 — assert vazio no red-team 3**

`test_red_team_cases.py:108`: `assert why.get("lifecycle_state", "UNKNOWN") == "UNKNOWN"` passa **vacuamente** se
a chave não existir (que é exatamente o caso no caminho `portfolio_review`). O teste ainda tem valor pelas
asserções de `strength != "STRONG"` e de ausência de texto presente-ish, mas essa linha não prova nada.

**LOW-003 — nome de teste desalinhado do que ele assere**

`test_claim_policy_rules.py:271-276`, `test_a4_stamped_state_never_enters_raw_status`: a linha 274
(`resolve_lifecycle_state(raw_status="ACTIVE_PROVEN").state == "ACTIVE_PROVEN"`) **pina o comportamento do
MED-001**, ou seja, documenta como desejado justamente o caminho em que um estado carimbado *entra* por
`raw_status`. O nome afirma o oposto do que a asserção fixa. Corrigir junto com MED-001.

**LOW-004 — o texto neutro "Ainda no horizonte operacional" passa a cobrir mais contratos não comprovados**

Probe do QA, contrato `UNKNOWN` publicado ontem:

```
PROBE1 TEXT   = "Ainda no horizonte operacional: publicação em 2026-08-31; órgão …; objeto: …"
PROBE1 spine.complete = True
PROBE1 claim_policy   = {'outreach_use_class': 'RECENT_RETROSPECTIVE', 'allowed_tense': 'NEUTRAL_FACTUAL'}
```

O texto é uma das três variantes de `_neutral()` **pré-existente** (antigo ramo `MODERATE`, message_spine.py:391-396
em HEAD), não escrito por esta story. Mas o cap novo **passa a rotear para ele** casos que antes tomavam o ramo
`STRONG` — logo a frequência dessa frase sobre contratos sem vigência comprovada **aumenta como consequência
direta desta mudança**. "Ainda no horizonte operacional" lê-se como afirmação de que a empresa segue operando.
Não viola nenhuma AC numerada (`allowed_tense` está correto e `FACTUAL_CLAIM_SAFE` aprova), mas toca o
**Estado-alvo** ("Nenhuma afirmação material de outreach cita presente/ativo sem prova verificável") — e a story
irmã `claim-safety-audit-01` (commit `9a07228a`) existe exatamente para caçar claim de presente em copy
publicada. Recomendação: revisar as três variantes de `_neutral()` para linguagem estritamente retrospectiva.
**Decisão de wording é do @po** — o @qa não altera copy.

#### Item de backlog obrigatório para o @po (protocolo §6 — CONCERNS exige owner)

No fechamento, o @po **deve** registrar **MED-001 + LOW-003** como item de backlog **vinculado ao follow-up de
lifecycle-truth** já declarado pelo @dev ("plumbar `status_normalized`/`status_observed_at` até o bag de
`normalize.py`"), com a dependência explícita: **MED-001 fecha antes daquele trabalho começar**. LOW-003 anda
junto porque `test_a4_stamped_state_never_enters_raw_status:274` **vai quebrar** no instante em que MED-001 for
corrigido — quem corrigir precisa saber que aquela asserção pina o defeito, não a guarda. LOW-001, LOW-002 e
LOW-004 são backlog comum, sem vínculo de bloqueio.

#### AC 30 — re-medição independente (o baseline do @dev estava em HEAD antigo)

O @dev mediu contra `6c7bb0ea`; HEAD avançou para `9a07228a`. **Re-medido pelo QA agora**, via
`git worktree add --detach` em `9a07228a` + `discover_frozen_input_paths(Path("."))`:

| Medição | Total |
|---|---|
| HEAD limpo (`9a07228a`) | **161** |
| Árvore de trabalho | **166** |

Delta **+5**, dos quais **+4 atribuíveis** — todos confirmados presentes no conjunto:
`scripts/confenge_claim_policy/__init__.py`, `scripts/confenge_claim_policy/policy.py`,
`scripts/contracts_truth.py`, `scripts/crawl/observation_lineage.py`. O quinto
(`scripts/confenge_universe/parafiscal.py`) é de outra story, como o @dev declarou.
A declaração do @dev **continua correta no HEAD atual**; a correção factual dele à predição do @architect
(`contracts_truth.py` puxa `observation_lineage.py` por import de nível de função, linha 1115) está
**confirmada**. Sequência de 2 PRs sem squash permanece obrigatória — autoridade do @devops.

#### Rastreabilidade de AC

| AC | Status | Evidência |
|---|---|---|
| 1-2, 6, 10-11 | PASS | `test_rule1_*`, `test_rule2_*` (linhas 56-98) |
| 3, 5, 7 (precedência 7 > 3) | PASS | `test_rule7_beats_rule3_*`, `test_rule5_*` (114-156) |
| 4 | PASS | `test_rule4_unknown_with_recent_publication_never_authorizes_present` |
| 8 | PASS | `test_rule8_missing_lifecycle_degrades_to_unknown_and_never_raises` |
| 9, 15, 23 | PASS | `test_red_team_4*`, `test_ac23_extract_contract_hook_default_is_backward_compatible` |
| 12-14, 16-18 | PASS | red-team 1-7 (AC 14 com ressalva LOW-002) |
| 19, 23a, 33 | PASS | `test_module_purity_and_boundary.py` (AST: imports proibidos, `date.today`/`datetime.now`/`os.getenv`); `test_ac33_evaluation_never_reads_wall_clock` faz monkeypatch de `contracts_truth.date` — prova o **resultado observável**, como a AC exige |
| 20 | PASS | `test_copy_hash_contract_is_pinned_sha256_utf8` |
| 21-22 | PASS | `test_ac21_*`, `test_ac22_*` (ver item 4) |
| 24, 24a | PASS | `test_ac24_lifecycle_derivation_matches_contracts_truth_table` — os 5 caminhos da tabela |
| 25 | PASS | cap em `_extract_temporal_event` (message_spine.py:348-378); probe QA devolveu `MODERATE` |
| 26 | PASS | `test_ac26_demotion_happens_before_the_frozen_result_is_built` |
| 27-28 | PASS | `test_ac27_monotonicity_*`, `test_ac28_*` + leitura de código (item 5) |
| 29 | PASS | suíte completa idêntica ao baseline (item 2) |
| 30 | PASS | re-medido pelo QA no HEAD atual (acima) |
| 31-32 | PASS | `test_ac31_no_second_lifecycle_vocabulary_is_introduced`, `test_ac32_suspended_*`; zero enum/Literal de lifecycle em `policy.py` (só import de `contracts_truth`) |

#### Veredito

**CONCERNS.** 33/33 ACs atendidas com evidência verificada de forma independente; zero regressões; lint limpo;
o hard gate central é estruturalmente correto. Um item de **segurança latente (MED-001)** e três itens **LOW**
ficam registrados como follow-up com owner — nenhum deles bloqueia a publicação desta story, mas **MED-001
bloqueia o follow-up de lifecycle-truth** já declarado pelo @dev.

Pré-condições de push (autoridade @devops, fora deste gate): 2 PRs sem squash; `publish.py` não pode entrar no
PR de código; re-medir o conjunto congelado imediatamente antes do PR de re-freeze.

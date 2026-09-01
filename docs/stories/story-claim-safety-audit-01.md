# Story: Auditar e corrigir claims de presente sobre status de contrato sem lastro no Contract Truth (Claim Safety Audit)

## Status

**InReview**

> Transicionada `Ready → InProgress → InReview` por @dev (Dex) em 2026-09-01. Ver Change Log e Dev Agent Record.

> Validada por @po (Pax) em 2026-09-01 com veredito **GO — 8/10**. Status transicionado explicitamente de `Draft` para `Ready`.
>
> **Correções aplicadas pelo @po durante a validação** (autoridade de @po sobre AC/Scope, conforme `.claude/rules/story-lifecycle.md`):
> 1. **AC 20 e AC 21 ACRESCENTADOS** — o conjunto de `why_now_code` declarado pelo @sm como "finito: 5 valores" está **factualmente errado**: `facts.py::why_now` produz **6** triggers. `mature_no_reajuste` existe em código e não era coberto por nenhum AC. Ver Decisão nº 1.
> 2. **Dependência de code-freeze de campanha DECLARADA** — `scripts/confenge_activation/publish.py` é input protegido do freeze `CONFENGE-COMMERCIAL-READY-01`. Omissão material para uma story HIGH-RISK que altera esse arquivo. Ver Decisão nº 2.
> 3. **Regra de serialização DECIDIDA** (o @sm a deixou como "recomendação ao @po") — implementação em paralelo, apenas o `--apply` de produção é serializado. Ver Decisão nº 3.
> 4. **Caminhos de CLI corrigidos** nas Dev Notes (apontavam para arquivos inexistentes).
>
> A estimativa de ≈179 leads foi verificada e está corretamente tratada como baseline a confirmar — **não trava a validação**. Ver Decisão nº 4.
>
> Detalhamento completo na seção **Decisões do @po** ao final deste documento.

## Risk Level

**HIGH-RISK** — aprovado por @architect (GO), pelos seguintes motivos concorrentes:

1. Toca o feed de produção `current` (release `run-adb0097e32b02188`, 8.667 leads) e o pipeline de publicação (`scripts/confenge_activation/publish.py`), que governa outbound comercial real.
2. Requer mudança condicional em `publication_semantic_hash` (`publish.py`) — se malfeita, pode causar `skipped_same=True` silencioso (apply vira no-op) ou quebrar retrocompatibilidade de hash de manifests legados já vinculados em `commercial_authority.basis_publication_semantic_hash`.
3. Colisão potencial de arquivos com story `story-outbound-sector-classifier-false-positive-01.md` (InProgress), que edita `identity.py`, `target_fit.py`, `eligibility.py`, `pipeline.py`, `parafiscal.py` — requer serialização explícita.

Fluxo aplicável: @architect (concluído, GO) → @sm (este documento) → @po → @dev → @qa aprofundado (10 gates) → gate sistêmico → @po → @devops.

## Executor Assignment

executor: "@dev"
quality_gate: "@architect + @qa (gate sistêmico conjunto, obrigatório para HIGH-RISK)"
quality_gate_tools: ["pytest", "claim_safety_audit --dry-run", "claim_safety_audit --apply", "claim_safety_audit rollback", "confenge_make_gates"]

## Story

**Como** founder responsável pela ativação do outbound B2G da CONFENGE,
**quero** que nenhum lead publicado no feed `current` afirme, no copy comercial (`why_now`/`fact_to_mention`), que um contrato público está "recente ou ativo" sem que isso seja lastreado pelo Contract Truth real,
**para que** o outbound comercial nunca dispare uma afirmação de presente falsificável sobre um contrato cujo status real é desconhecido, encerrado, cancelado ou suspenso.

## Contexto e causa raiz

- Medição real de produção (não fixtures), feita nesta sessão pelo @architect: release `run-adb0097e32b02188` (symlink `current` em `/opt/confenge-plane/feed-www/current`), 8.667 leads, 41.102 contratos, `publication_semantic_hash` prefixo `a77fd763126c`.
- Causa raiz: string hardcoded em `scripts/confenge_account_intelligence/facts.py:306` — `"Aditivos/alterações observados em contrato público recente ou ativo."` — o token "ativo" afirma presente sem qualquer lastro no Contract Truth real (`scripts/contracts_truth.py`).
- Universo afetado medido: `why_now_code == "ADDENDUM"` = 98 leads; universo inseguro total estimado ≈179 leads (2,1% do feed) após bind com `GLOSA_MEDICAO`/`REEQUILIBRIO`.
- 100% dos 41.102 contratos publicados têm `start_date` NULL — `classify_contract_activity()` resulta em `UNKNOWN` para praticamente todo o corpus. `ACTIVE_PROVEN` é hoje **inalcançável** a partir do payload publicado.
- Um detector lexical ingênuo (regex `"vigente|em execução|..."`) tem 100% de falso positivo (43/43 casos) porque casa dentro da citação do `objeto` do contrato (ex.: "execução de obras de EMPREENDIMENTOS HABITACIONAIS"), não numa asserção do copy. É preciso classificar o **template** do claim (`why_now_code`), não fazer regex sobre o texto renderizado final.
- **[CORRIGIDO PELO @po]** O @sm declarou o conjunto de `why_now_code` como "finito: 5 valores" (`PORTFOLIO_REVIEW`, `INSUFFICIENT_FACTS`, `ADDENDUM`, `GLOSA_MEDICAO`, `REEQUILIBRIO`). **Isso é factualmente incorreto.** Verificação direta em `scripts/confenge_account_intelligence/facts.py::why_now` mostra **6** triggers produzíveis: os 4 de `pain_checks` (`addendum`, `glosa_medicao`, `reequilibrio`, **`mature_no_reajuste`**) mais os 2 fallbacks (`insufficient_facts`, `portfolio_review`). O uppercase acontece a jusante em `scripts/confenge_outreach_pipeline/adapt.py:388` (`str(...).upper()`) — **não existe enum em código**, é string livre. `MATURE_NO_REAJUSTE` está ausente do release corrente apenas porque seu predicado exige `start_date` não-nulo (100% NULL hoje) — a aritmética do baseline confirma: 7131+1357+98+78+3 = 8667 = `lead_count` exato. Ele volta a ser alcançável assim que a dependência de publicar `status`/`start_date` (declarada OUT) for resolvida. Ver AC 20 e AC 21.

## Valor

Eliminar de forma seletiva (não pausar nem genericizar outbound) a classe de risco "claim de presente sobre contrato histórico/desconhecido", preservando os leads bons e a pesquisabilidade dos demais.

## Classificação — 5 classes (definidas por @architect)

Eixo 1 — claim extraído do template (`NONE`/`PRESENT`/`PAST`, com spans de evidência interpolada removidos antes da avaliação). Eixo 2 — `activity_state` real via `classify_contract_activity()` de `contracts_truth.py` (READ-ONLY, nunca duplicar tokens/enums).

| Classe | Condição |
|---|---|
| `SAFE_NO_CURRENT_CLAIM` | claim `NONE` |
| `SAFE_CURRENT_PROVEN` | claim `PRESENT` e `activity_state == ACTIVE_PROVEN`. **Estruturalmente vazia hoje** (ACTIVE_PROVEN inalcançável do payload publicado) — deve ser reportada como 0 com `reason_code` explícito `active_proven_unreachable_from_published_payload`, nunca escondida. |
| `SAFE_HISTORICAL` | claim `PAST` explícito ancorado em data (`end_date` passado) |
| `UNSAFE_PRESENT_CLAIM` | claim `PRESENT` e `activity_state ∈ {COMPLETED, CANCELLED, TERMINATED, SUSPENDED, UNKNOWN}`. Fail-closed: `UNKNOWN`+presente é UNSAFE, nunca promovido. |
| `NEEDS_RESEARCH` | claim `PRESENT` que não se liga a nenhum contrato específico do payload |

### Regra de reescrita determinística para `UNSAFE_PRESENT_CLAIM`

- Se `end_date` do contrato ligado `< hoje` → vira `SAFE_HISTORICAL` (frame passado explícito + data).
- Se `end_date >= hoje` ou `NULL` → vira `SAFE_NO_CURRENT_CLAIM` (remove asserção temporal, preserva fato observado).

## Scope

**IN:**

- NOVO `scripts/confenge_claim_safety/__init__.py`.
- NOVO `scripts/confenge_claim_safety/claim_surface.py` — extrai superfície de claim removendo spans de evidência interpolada.
- NOVO `scripts/confenge_claim_safety/classify.py` — as 5 classes; importa de `contracts_truth`, nunca duplica tokens/enums.
- NOVO `scripts/confenge_claim_safety/rewrite.py` — reescrita determinística (regra acima).
- NOVO `scripts/confenge_claim_safety/policy.py` — `CLAIM_SAFETY_POLICY_VERSION`.
- NOVO `scripts/confenge/claim_safety_audit/cli.py` — flags `--dry-run` (default seguro), `--apply`, subcomando `rollback`, `--feed-dir` (default aponta pro `current` real via `releases/`, nunca fixture), `--report-json`. Seguir convenção de `check-alerts.py`/`intel_pipeline.py` (exit codes: 0 limpo/corrigido, 1 unsafe encontrado em dry-run, 2 erro/recusa).
- `scripts/confenge/__main__.py` — adicionar dispatch para `claim-safety-audit`/`claim_safety_audit`, seguindo padrão existente de subcomandos.
- `scripts/confenge_activation/publish.py` — **MUDANÇA CIRÚRGICA E CRÍTICA**:
  - Inserir CONDICIONALMENTE (só se `manifest.get("claim_safety", {}).get("corpus_hash")` existir) uma chave `claim_safety_hash` no dict `semantics` usado por `publication_semantic_hash` (função em torno das linhas 368-401). Necessário porque sem isso um build corrigido com mesmo `lead_count`/membership teria hash IDÊNTICO ao anterior e `atomic_publish_directory` retornaria `skipped_same=True` sem criar release novo — o apply seria um no-op silencioso. A inserção deve ser estritamente condicional para não alterar o hash de manifests legados (sem bloco `claim_safety`) — preservando retrocompatibilidade com `commercial_authority.basis_publication_semantic_hash` já vinculado em produção.
  - Gravar `claim_safety_rollback_anchor` em `publication-state.json` ANTES do swap atômico do symlink, para servir de âncora de rollback explícito (distinta de `last_good_publication`, que o próprio apply sobrescreveria).
- `scripts/confenge_account_intelligence/facts.py:306` — correção de causa raiz: remover "ou ativo" da string do template `ADDENDUM` (uma linha), para que builds futuros não reintroduzam o claim inseguro.
- NOVO `tests/confenge_claim_safety/` — testes de classificação (5 classes × todos os `activity_states`), teste nomeado do falso positivo do `objeto` (regex ingênuo casando dentro de citação), teste de idempotência (segundo apply = skip observável, não segundo release), teste de retrocompatibilidade do hash (manifest sem bloco `claim_safety` → hash idêntico ao antes da mudança), teste de rollback ponta a ponta.

**OUT (com justificativa):**

- `scripts/contracts_truth.py` — read-only, sem novos tokens/enums/promoções.
- `scripts/warmbly_bridge/mapping.py::map_lead` — sem refatoração (só bloco aditivo `claim_safety{}` se necessário, retrocompatível).
- `scripts/confenge_activation/strict_national_esr.py` / MessageSpine — sem refatoração.
- Feed-cycle, weekly_cycle, crawler, `observation_lineage.py`.
- `facts.py` além da linha 306.
- Contact/target-fit/eligibility/parafiscal — **ATENÇÃO: colisão declarada.** `docs/stories/story-outbound-sector-classifier-false-positive-01.md` está `InProgress` mexendo em `identity.py`, `target_fit.py`, `eligibility.py`, `pipeline.py`, `parafiscal.py`. Ver seção **Dependencies and sizing** abaixo — não rodar em paralelo mudanças nos mesmos arquivos.
- Publicar `status`/`observed_at` em `contracts[]` do feed — dependência declarada, fora de escopo. `SAFE_CURRENT_PROVEN` continuará estruturalmente vazio até essa dependência ser resolvida em story separada.
- Contenção operacional em produção — não aplicável a esta story (não há incidente de outbound já disparado a corrigir por contenção manual, diferente da story sector-classifier).

## Dependencies and sizing

- **Depende de serialização com `story-outbound-sector-classifier-false-positive-01.md` (InProgress).** Esta story NÃO toca `identity.py`, `target_fit.py`, `eligibility.py`, `pipeline.py`, `parafiscal.py` — zero overlap direto de arquivos de escopo IN. O ponto de contato é indireto: ambas eventualmente produzem builds que alteram a população do feed publicado e disputam a mesma sequência de releases em `/opt/confenge-plane/feed-www/`. **Regra de serialização:** o apply desta story (`claim_safety_audit --apply`) só deve rodar contra um release-base que já reflita (ou explicitamente não reflita, e isso deve estar documentado no relatório de apply) o estado da story sector-classifier, para não confundir deltas de `lead_count`/`membership` de duas mudanças concorrentes. **DECIDIDO PELO @po (Decisão nº 3), substituindo a recomendação aberta do @sm:** implementação, testes e `--dry-run` desta story rodam **em paralelo** com a sector-classifier (overlap de `scope_files` = zero, verificado contra `.aiox/state/stories/outbound-sector-classifier-false-positive-01.json`). **Somente o `--apply` em produção é serializado** atrás da publicação do release da sector-classifier. Razão de não serializar o ciclo inteiro: a sector-classifier está em `qa_verdict: FAIL`, dev loop iteração 2, com REQ-003 aberto como gate de fechamento — serializar tudo travaria esta story por tempo indeterminado sem nenhum motivo em nível de arquivo.

- **[ACRESCENTADO PELO @po — Decisão nº 2] Dependência de code-freeze de campanha.** `scripts/confenge_activation/publish.py` é **input protegido** do freeze `CONFENGE-COMMERCIAL-READY-01` (consta em `artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01/frozen-inputs-manifest.json`, política `frozen_confenge_inputs_v1`, 162 inputs protegidos). O gate `code-freeze-gate.json` já está `BLOCKED_PROTECTED_INPUT_CHANGED` no HEAD atual — causado pelos commits #468, **não** por esta story. Consequência operacional: a mudança em `publish.py` exige **PR de código primeiro, depois um PR separado artifact-only de re-freeze**. **Isso bloqueia a publicação pelo @devops se não for declarado; NÃO bloqueia a implementação pelo @dev.** Verificado que os demais arquivos de escopo IN estão **fora** do conjunto protegido: `scripts/confenge_account_intelligence/facts.py`, `scripts/confenge/__main__.py`, `scripts/contracts_truth.py` e todos os caminhos novos `scripts/confenge_claim_safety/` — nenhum deles consta no manifesto de freeze.
- Depende de design técnico do @architect (já entregue, incorporado integralmente neste documento).
- T-shirt size: **M** — 6 arquivos novos + 1 linha em `facts.py` + mudança cirúrgica (porém sensível) em `publish.py`. Superfície de regressão contida (não altera classificação de target-fit/identity/eligibility), mas risco alto concentrado na mudança de hash em `publish.py` e no bloqueio de idempotência.

## Risks and mitigations

- **Skip silencioso no apply** (hash idêntico ao anterior por falta da chave `claim_safety_hash`) — mitigado pelo AC de retrocompatibilidade condicional + AC de idempotência observável (gate 2).
- **Quebra de retrocompatibilidade de hash** para manifests legados sem bloco `claim_safety`, invalidando `commercial_authority.basis_publication_semantic_hash` já vinculado — mitigado pelo gate 10 (hash de manifest legado inalterado, provado por teste).
- **Regex ingênuo reintroduzido por engano no classificador de claim** — mitigado pelo gate 6 (teste nomeado: `objeto` com "em execução" classifica `SAFE_NO_CURRENT_CLAIM`, não falso positivo) e pela decisão de classificar por `why_now_code` (template finito), não por regex no texto renderizado.
- **Remoção acidental de leads durante o apply** (regressão de completude) — mitigado pelos gates 3, 4, 5 (lead_count/source_lead_id idênticos, target_fit_* byte-idênticos, TARGET_CONFIRMED intocado, membership_hash inalterado, guard `_assert_membership_deactivation_delta` exercitado).
- **Rollback inexistente ou não testado** em caso de falha pós-deploy — mitigado pelo AC de `claim_safety_rollback_anchor` gravado ANTES do swap atômico e pelo gate 8 (rollback ponta a ponta com revalidação do delta guard).
- **Escrita indevida durante dry-run** — mitigado pelo gate 9 (dry-run comprovadamente não escreve em `feed-www/` nem em `publication-state.json`).
- **Colisão com story sector-classifier InProgress** — mitigado pela regra de serialização explícita acima; nenhum arquivo de escopo IN se sobrepõe, mas a sequência de releases exige coordenação do @po.
- **[ACRESCENTADO PELO @po] Template não reconhecido escapa como seguro** — um `why_now_code` fora do conjunto enumerado (o @sm enumerou 5; existem 6) seria classificado por omissão, furando a postura fail-closed da story exatamente na dimensão que ela existe para proteger. Mitigado pelos ACs 20 (default `NEEDS_RESEARCH`) e 21 (teste de drift contra `facts.py`).
- **[ACRESCENTADO PELO @po] Publicação bloqueada pelo code-freeze de campanha** — `publish.py` é input protegido e o gate já está `BLOCKED_PROTECTED_INPUT_CHANGED`. Sem o PR artifact-only de re-freeze, o @devops não publica e o `--apply` não chega a produção. Mitigado pela declaração explícita em **Dependencies and sizing** e pelo gate de fechamento correspondente no DoD.

## Baseline (medido, congelar como referência)

- 8.667 leads, 41.102 contratos, `run_id` `run-adb0097e32b02188`, `publication_semantic_hash` `a77fd763126c` (prefixo).
- `why_now_code` counts: `PORTFOLIO_REVIEW` 7131, `INSUFFICIENT_FACTS` 1357, `ADDENDUM` 98, `GLOSA_MEDICAO` 78, `REEQUILIBRIO` 3.
- `UNSAFE_PRESENT_CLAIM` esperado no dry-run inicial ≈179 (a confirmar exatamente pelo @dev ao rodar `claim_safety_audit --dry-run` contra o release corrente).
- 100% dos 41.102 contratos publicados têm `start_date` NULL — `ACTIVE_PROVEN` inalcançável do payload atual (registrar como fato de baseline, não como bug desta story).

## Estado-alvo

Após `--apply`:

- Novo release publicado com `UNSAFE_PRESENT_CLAIM == 0` (medido no release recém-publicado, não no `build_dir`).
- Mesmo `lead_count` (8.667) e mesmo `source_lead_id` set — zero leads removidos.
- `TARGET_CONFIRMED` intocado; todos os campos `target_fit_*` byte-idênticos.
- `membership_hash` inalterado (o apply não é uma revogação de membership — é reescrita de copy).
- Rollback funcional para o release anterior via `claim_safety_rollback_anchor`.
- `facts.py:306` corrigido para não reintroduzir o claim inseguro em builds futuros.
- `SAFE_CURRENT_PROVEN` permanece 0, com `reason_code` `active_proven_unreachable_from_published_payload` explícito no relatório — não é regressão, é limitação de payload documentada.
- Rerun do apply (idempotência) resulta em skip observável (ex.: `report-json` com `status: "skipped_no_change"`), não em segundo release físico.

## Acceptance Criteria

**Classificação (5 classes):**

1. **Given** um lead cujo `why_now_code == "PORTFOLIO_REVIEW"` ou `"INSUFFICIENT_FACTS"` (claim extraído `NONE`), **when** classificado por `classify.py`, **then** resultado é `SAFE_NO_CURRENT_CLAIM`.
2. **Given** um lead com claim `PRESENT` cujo contrato ligado tem `activity_state == ACTIVE_PROVEN` no `contracts_truth.py`, **when** classificado, **then** resultado é `SAFE_CURRENT_PROVEN`. **Given** que nenhum contrato no payload atual satisfaz essa condição (100% `start_date` NULL), **when** o relatório de classificação é gerado, **then** a contagem de `SAFE_CURRENT_PROVEN` é 0 e o relatório inclui explicitamente `reason_code: "active_proven_unreachable_from_published_payload"` (não omitido, não silenciado).
3. **Given** um claim `PAST` explícito ancorado em `end_date` no passado, **when** classificado, **then** resultado é `SAFE_HISTORICAL`.
4. **Given** um claim `PRESENT` ligado a um contrato cujo `activity_state` está em `{COMPLETED, CANCELLED, TERMINATED, SUSPENDED, UNKNOWN}`, **when** classificado, **then** resultado é `UNSAFE_PRESENT_CLAIM` — inclusive quando `activity_state == UNKNOWN` (fail-closed, nunca promovido a seguro por omissão de dado).
5. **Given** um claim `PRESENT` que não referencia nenhum contrato específico do payload, **when** classificado, **then** resultado é `NEEDS_RESEARCH`.

**Reescrita determinística:**

6. **Given** um lead `UNSAFE_PRESENT_CLAIM` cujo contrato ligado tem `end_date < hoje`, **when** `rewrite.py` processa, **then** o novo copy usa frame de passado explícito com a data, e a classe pós-rewrite é `SAFE_HISTORICAL`.
7. **Given** um lead `UNSAFE_PRESENT_CLAIM` cujo contrato ligado tem `end_date >= hoje` ou `end_date IS NULL`, **when** `rewrite.py` processa, **then** a asserção temporal de presente é removida (fato observado preservado sem afirmar vigência), e a classe pós-rewrite é `SAFE_NO_CURRENT_CLAIM`.

**Falso positivo do detector ingênuo (regressão nomeada):**

8. **Given** um objeto de contrato contendo a substring "em execução" dentro da citação do objeto (ex.: "execução de obras de EMPREENDIMENTOS HABITACIONAIS"), **when** o `why_now_code` associado é `PORTFOLIO_REVIEW` ou `INSUFFICIENT_FACTS` (claim `NONE` pelo template), **then** o lead classifica `SAFE_NO_CURRENT_CLAIM` — não é tratado como falso positivo de claim presente só porque o texto do objeto contém palavras de vigência. Este teste prova que a classificação é por template (`why_now_code`), não por regex sobre o texto renderizado final.

**Causa raiz — facts.py:306:**

9. **Given** o template `ADDENDUM` em `scripts/confenge_account_intelligence/facts.py`, **when** a linha 306 é lida após a correção, **then** a string não contém mais o token "ativo" como afirmação de presente (ex.: "Aditivos/alterações observados em contrato público." sem a cláusula "ou ativo").

**Gates de QA obrigatórios (HIGH-RISK) — cada um é um AC:**

10. `UNSAFE_PRESENT_CLAIM == 0` medido no release recém-publicado (não no `build_dir`) após `--apply`. **[ESTENDIDO PELO @po]** Adicionalmente, o release publicado deve conter **zero** leads com `why_now_code` não reconhecido pelo conjunto de `classify.py` portando claim de presente — de modo que `NEEDS_RESEARCH` por template desconhecido não seja uma rota de escape publicável (ver AC 20).
11. Idempotência: rerun do apply é skip observável (relatório indica no-op), não gera segundo release físico em `/opt/confenge-plane/feed-www/releases/`.
12. `lead_count` e `set(source_lead_id)` idênticos antes/depois do apply.
13. Todos os campos `target_fit_*` byte-idênticos antes/depois; `TARGET_CONFIRMED` intocado.
14. Nenhum lead removido; `membership_hash` inalterado; teste exercita o guard existente `_assert_membership_deactivation_delta` de `publish.py` e confirma que ele não dispara (delta de membership = 0).
15. Teste nomeado (mesmo do AC 8): lead cujo `objeto` contém "em execução" classifica `SAFE_NO_CURRENT_CLAIM` (não falso positivo).
16. Teste adversarial: todos os `activity_states` não-`ACTIVE_PROVEN` (`COMPLETED`, `CANCELLED`, `TERMINATED`, `SUSPENDED`, `UNKNOWN`) combinados com claim `PRESENT` → `UNSAFE_PRESENT_CLAIM`, sem exceção.
17. Rollback exercitado ponta a ponta: `claim_safety_audit rollback` restaura o release anterior via `claim_safety_rollback_anchor`, e o delta guard (`_assert_membership_deactivation_delta`) é revalidado no estado pós-rollback (deve refletir o estado anterior ao apply, sem drops adicionais).
18. Dry-run (`--dry-run`) comprovadamente não escreve em `feed-www/` (nenhum novo diretório em `releases/`, symlink `current` inalterado) nem em `publication-state.json` — verificado por teste que captura mtime/hash desses artefatos antes/depois do dry-run.
19. `publication_semantic_hash` de um manifest legado (sem bloco `claim_safety`) permanece byte-idêntico ao valor calculado antes desta mudança — prova de retrocompatibilidade da inserção condicional em `publish.py`.

**Completude do conjunto de templates (ACRESCENTADOS pelo @po — ver Decisão nº 1):**

20. **Fail-closed para template não reconhecido.** **Given** um lead cujo `why_now_code` não pertence ao conjunto reconhecido por `classify.py`, **when** classificado, **then** o resultado é `NEEDS_RESEARCH` — **nunca** `SAFE_NO_CURRENT_CLAIM` e nunca uma classe `SAFE_*` por omissão. Adicionalmente: **Given** `why_now_code == "MATURE_NO_REAJUSTE"` (sexto trigger real de `facts.py`, hoje com contagem 0 por depender de `start_date` não-nulo), **when** classificado, **then** o resultado é `NEEDS_RESEARCH` — decisão explícita do @po, não fallback: o texto do template ("Contrato maduro (com data de início observada) sem prova de reajuste no input — janela potencial de reajuste") é ambíguo entre claim `PRESENT` e `NONE`, e uma story fail-closed não pode resolver ambiguidade a favor do seguro. Promover `MATURE_NO_REAJUSTE` a `SAFE_*` exige story própria com decisão de copy.

    **Enforcement obrigatório (sem isto o AC 20 é um rótulo sem efeito):** `NEEDS_RESEARCH` não pode ser classe terminal com publicação permitida. Hoje `rewrite.py` só dispara em `UNSAFE_PRESENT_CLAIM` e o AC 10 só restringe `UNSAFE_PRESENT_CLAIM == 0` — um template não reconhecido classificaria `NEEDS_RESEARCH` e **publicaria inalterado, carregando o claim de presente do seu template**, que é exatamente o fail-open que este AC existe para fechar. Portanto: **Given** um lead classificado `NEEDS_RESEARCH` por template não reconhecido (incluindo `MATURE_NO_REAJUSTE`), **when** `--apply` processa, **then** ele passa pelo ramo de reescrita que remove a asserção temporal de presente (resultado pós-rewrite `SAFE_NO_CURRENT_CLAIM`, fato observado preservado), **e** o release publicado contém **zero** leads com `why_now_code` não reconhecido portando claim de presente — restrição verificada em conjunto com o AC 10.

21. **Teste de drift do conjunto de templates.** **Given** o conjunto de triggers efetivamente produzíveis por `scripts/confenge_account_intelligence/facts.py::why_now` (os 4 de `pain_checks` + `insufficient_facts` + `portfolio_review`), **when** o teste de drift roda, **then** ele falha se o conjunto reconhecido por `classify.py` divergir do conjunto real de `facts.py` — de modo que a introdução de um 7º trigger quebre o teste em vez de embarcar silenciosamente como não classificado. O conjunto reconhecido deve ser **derivado ou fixado contra `facts.py`**, nunca hardcoded de forma privada e independente em `classify.py` (a mesma restrição de não-duplicação que a story já impõe sobre `contracts_truth.py` vale aqui — ver seção "Restrição de nova dívida técnica"). Seguir o padrão já existente em `tests/confenge_universe/test_classifier_version_drift.py`.

## Tasks / Subtasks

- [x] Task 1 — Criar módulo `scripts/confenge_claim_safety/` (AC: 1-5)
  - [x] `claim_surface.py`: extrair claim (`NONE`/`PRESENT`/`PAST`) do template renderizado, removendo spans de evidência interpolada antes da avaliação.
  - [x] `classify.py`: implementar as 5 classes cruzando claim × `activity_state` (importado de `contracts_truth.py`, sem duplicar enum/tokens).
  - [x] `policy.py`: definir `CLAIM_SAFETY_POLICY_VERSION`.
- [x] Task 2 — Implementar reescrita determinística (AC: 6, 7)
  - [x] `rewrite.py`: regra `end_date < hoje` → `SAFE_HISTORICAL` com data explícita; `end_date >= hoje` ou `NULL` → `SAFE_NO_CURRENT_CLAIM` sem asserção temporal.
- [x] Task 3 — CLI de auditoria (AC: 10, 11, 17, 18)
  - [x] `scripts/confenge/claim_safety_audit/cli.py` com `--dry-run` (default), `--apply`, `rollback`, `--feed-dir` (default = `current` real via `releases/`), `--report-json`.
  - [x] Exit codes: 0 limpo/corrigido, 1 unsafe encontrado em dry-run, 2 erro/recusa.
  - [x] Registrar dispatch em `scripts/confenge/__main__.py`.
- [x] Task 4 — Mudança cirúrgica em `publish.py` (AC: 10-14, 19)
  - [x] Inserir `claim_safety_hash` no dict `semantics` de `publication_semantic_hash`, condicionalmente à presença de `manifest.get("claim_safety", {}).get("corpus_hash")`.
  - [x] Gravar `claim_safety_rollback_anchor` em `publication-state.json` antes do swap atômico do symlink.
- [x] Task 5 — Correção de causa raiz (AC: 9) — **satisfeita sem edição** por `story-outreach-claim-policy-01` (colisão não declarada; ver Desvios no Dev Agent Record).
  - [x] Verificado que o literal `"Aditivos/alterações observados em contrato público recente ou ativo."` não existe mais em `facts.py`; AC 9 provado por invariante em `test_template_set_drift.py::test_ac9_addendum_template_no_longer_asserts_present_activity`.
- [x] Task 6 — Testes (AC: 1-21)
  - [x] `tests/confenge_claim_safety/test_classify.py`: 5 classes × todos os `activity_states`.
  - [x] `tests/confenge_claim_safety/test_false_positive_objeto.py`: teste nomeado do AC 8/15.
  - [x] `tests/confenge_claim_safety/test_idempotency.py`: segundo apply = skip, não segundo release.
  - [x] `tests/confenge_claim_safety/test_hash_backcompat.py`: manifest legado sem `claim_safety` → hash idêntico (ancorado no digest real de produção).
  - [x] `tests/confenge_claim_safety/test_rollback.py`: rollback ponta a ponta + revalidação do delta guard.
  - [x] `tests/confenge_claim_safety/test_dry_run_no_writes.py`: dry-run não escreve em `feed-www/` nem `publication-state.json`.
  - [x] `tests/confenge_claim_safety/test_rewrite.py`: os dois ramos determinísticos + enforcement do AC 20.
  - [x] `tests/confenge_claim_safety/test_template_set_drift.py`: AC 21 — conjunto reconhecido por `classify.py` vs. conjunto real produzível por `facts.py::why_now` (extração por AST).
  - [x] Teste do AC 20: `why_now_code` desconhecido e `MATURE_NO_REAJUSTE` → `NEEDS_RESEARCH` (fail-closed) + reescrita obrigatória.
- [x] Task 7 — Medição e plano de deploy (AC: 10, 12, 13, 14)
  - [x] `--dry-run` rodado contra o release corrente de produção (`run-adb0097e32b02188`, cópia read-only): **98** `UNSAFE_PRESENT_CLAIM` (não ≈179). Relatório em `artifacts/confenge/claim-safety/dry-run-run-adb0097e32b02188.json`.
  - [x] Sequência de deploy documentada (ver Dev Agent Record → Plano de deploy). `--apply` em produção **NÃO** executado: bloqueado pelos gates de fechamento do @po (re-freeze de campanha + serialização com a sector-classifier).
  - [x] Plano de rollback registrado no relatório JSON do apply (`rollback_plan`, exercitado em teste).

## Testing

- Localização: `tests/confenge_claim_safety/` (novo diretório), seguindo padrão de `tests/commercial_leads/` e `tests/confenge_universe/` já existentes no repo.
- Sem SMTP em nenhuma parte da implementação ou dos testes.
- Testes de classificação e reescrita devem ser puros (sem I/O), usando fixtures sintéticas de contrato + `why_now_code`.
- Testes de CLI (`--dry-run`, `--apply`, `rollback`) devem operar sobre um `--feed-dir` de teste isolado (diretório temporário simulando a estrutura `releases/` + `current` symlink), nunca contra o feed real de produção.
- Teste de retrocompatibilidade de hash deve usar um manifest fixture congelado (sem bloco `claim_safety`) e comparar `publication_semantic_hash` calculado antes/depois da mudança em `publish.py`.
- Reutilizar `_assert_membership_deactivation_delta` existente em `publish.py` nos testes de idempotência/rollback, não recriar lógica equivalente.

## DoD

- Todos os **21** ACs satisfeitos com evidência de teste (19 do @sm + ACs 20 e 21 acrescentados pelo @po).
- `pytest tests/confenge_claim_safety/ -v` verde.
- **[CORRIGIDO PELO @po]** Suite completa: **zero regressão contra baseline medido** (delta before/after dos IDs de falha), **não** "suite verde". O @sm escreveu "`pytest tests/ -q --tb=no -x` (suite completa) verde", requisito **insatisfazível neste repo**: a medição do @qa na story sector-classifier registra 135 failed / 51 errors constantes antes e depois (186 IDs idênticos), todas falhas ambientais (`httpx`, `prometheus_client`, `fastapi`, `numpy`, `lxml`, `hypothesis`, `reportlab` ausentes; sem Postgres local). Manter "verde" forçaria um waiver no fechamento. Método aceito: rodar a suite antes e depois, comparar o conjunto de IDs de falha/erro, exigir delta vazio.
- Lint/typecheck limpos nos arquivos novos e modificados.
- `--dry-run` executado contra o release corrente com relatório JSON anexado à story (Dev Agent Record).
- Nenhum arquivo de escopo OUT tocado.
- Nenhuma nova dívida técnica introduzida sem registro explícito com owner e prazo.
- @po fecha a story após veredito PASS/CONCERNS/WAIVED do @qa e após confirmar a serialização com a story sector-classifier.
- **[GATE DE FECHAMENTO — @po]** Antes de qualquer `--apply` em produção: (a) release da sector-classifier publicado, ou registro explícito no relatório de apply de que não foi (Decisão nº 3); (b) plano de re-freeze da campanha declarado para `publish.py` — PR de código seguido de PR artifact-only de re-freeze (Decisão nº 2). Este gate **não** bloqueia a implementação nem os testes.

## Rollback Plan

1. `claim_safety_rollback_anchor` é gravado em `publication-state.json` ANTES do swap atômico do symlink `current` durante o `--apply` — captura o release anterior ao apply.
2. Em caso de problema pós-deploy, executar `python3 -m scripts.confenge.claim_safety_audit rollback` (ou comando CLI equivalente definido na Task 3), que:
   - Lê `claim_safety_rollback_anchor` de `publication-state.json`.
   - Restaura o symlink `current` para o release anterior (ancorado, não o `last_good_publication` genérico, que já teria sido sobrescrito pelo próprio apply).
   - Revalida o guard `_assert_membership_deactivation_delta` no estado pós-rollback.
3. Rollback é exercitado e provado em teste automatizado (AC 17) antes de qualquer execução em produção.
4. `facts.py:306` (correção de causa raiz) não precisa de rollback — é uma correção textual isolada sem efeito em runtime além do template renderizado em builds futuros.

## Restrição de nova dívida técnica

- Nenhum TODO/FIXME sem issue/story associada.
- Nenhuma duplicação de enum/token de `contracts_truth.py` — `classify.py` deve importar, nunca reimplementar.
- Nenhuma dependência nova de terceiros sem justificativa registrada no Change Log.
- Caminhos de scratchpad/temporários (`/tmp/...`) proibidos em testes ou scripts — usar caminhos relativos ao repositório (`pathlib.Path(__file__).parents[N]`), para garantir execução em CI.

## Dev Notes

### Relevant source tree

- `scripts/confenge_account_intelligence/facts.py` (linha 306 — única linha em escopo)
- `scripts/contracts_truth.py` (READ-ONLY — fonte de `activity_state` e `classify_contract_activity()`)
- `scripts/confenge_activation/publish.py` (função em torno das linhas 368-401 para `publication_semantic_hash`; `_assert_membership_deactivation_delta` ~linha 237; guard de recusa `PUBLICATION_REFUSED`)
- `scripts/confenge_account_intelligence/` — MessageSpine e templates de `why_now`/`fact_to_mention` (contexto, não escopo IN além de `facts.py:306`)
- Padrão de CLI a seguir: `scripts/check-alerts.py` e `scripts/intel_pipeline.py` (exit codes 0/1/2, flags `--dry-run`/`--apply`). **[CORRIGIDO PELO @po]** — o @sm indicou `scripts/confenge/check-alerts.py` e `scripts/confenge/intel_pipeline.py`; esses caminhos **não existem**. Os arquivos reais estão em `scripts/`, um nível acima.
- Padrão de subcomando a seguir para `scripts/confenge/__main__.py`: o dispatch existente de `human_review` (import tardio dentro do `if cmd in {...}`, retornando o `int` do `main` do submódulo), e a estrutura de pacote `scripts/confenge/human_review/cli.py` — que é exatamente o formato proposto para `scripts/confenge/claim_safety_audit/cli.py`. Lembrar de atualizar também o texto de `--help` do `__main__.py`, hoje hardcoded apenas com `human_review`.
- `scripts/confenge_account_intelligence/facts.py::why_now` é a fonte real dos triggers (`pain_checks` + fallbacks). Os valores em `facts.py` são **minúsculos** (`addendum`, `mature_no_reajuste`, ...); o uppercase que produz `why_now_code` acontece em `scripts/confenge_outreach_pipeline/adapt.py:388`. Atenção a essa diferença de caixa ao fixar o conjunto reconhecido (AC 21).

### Contexto de colisão com story em andamento

`story-outbound-sector-classifier-false-positive-01.md` está `InProgress` e toca `identity.py`, `target_fit.py`, `eligibility.py`, `pipeline.py`, `parafiscal.py` (novo). Esta story não tem overlap direto de arquivos, mas ambas produzem releases no mesmo `feed-www/`. Ver seção **Dependencies and sizing**.

## Change Log

| Date | Version | Description | Author |
|------|---------|-------------|--------|
| 2026-09-01 | 0.1.0 | Story criada em Draft a partir de mandato HIGH-RISK aprovado por @architect (GO), com medição real de produção incorporada. | River (@sm) |
| 2026-09-01 | 0.3.1 | Revisão pós-implementação: âncora de rollback passou a ser gravada **condicionalmente** (só para publicação com bloco `claim_safety`), evitando que uma publicação de rotina posterior desloque a âncora e torne o rollback um no-op silencioso; AC 9 ganhou metade **comportamental** (chama o resolver com política que proíbe presente, em vez de só verificar substring no fonte); `artifacts/confenge/claim-safety/build/` adicionado ao `.gitignore`. 70 testes, 240 na regressão de publicação. | Dex (@dev) |
| 2026-09-01 | 0.3.0 | Implementacao (`*dev-develop-story`, YOLO). Transicoes `Ready -> InProgress` e `InProgress -> InReview`. Modulo `confenge_claim_safety` + CLI `claim_safety_audit` + 2 mudancas cirurgicas em `publish.py`. Dry-run real de producao: **98** `UNSAFE_PRESENT_CLAIM` (nao ~179); ressalva do @po confirmada (GLOSA_MEDICAO/REEQUILIBRIO nao sao claim de presente). Falso positivo de 5 leads `PORTFOLIO_REVIEW` encontrado e corrigido na selecao de spans de evidencia. `facts.py` NAO editado - AC 9 ja satisfeito por `story-outreach-claim-policy-01` (colisao de escopo nao declarada, requer reconciliacao do @po). 67 testes novos, 0 regressao de escopo. | Dex (@dev) |
| 2026-09-01 | 0.2.0 | Validação `*validate-story-draft`: **GO 8/10**. Transição `Draft → Ready`. ACs 20 e 21 acrescentados (conjunto de `why_now_code` é 6, não 5 — `mature_no_reajuste` não estava coberto). Dependência de code-freeze de campanha sobre `publish.py` declarada. Regra de serialização decidida (paralelo na implementação, serial no `--apply`). Caminhos de CLI inexistentes corrigidos nas Dev Notes. AC 20 reforçado com enforcement de publicação (`NEEDS_RESEARCH` deixa de ser classe terminal publicável) e AC 10 estendido em conjunto. DoD corrigido: "suite verde" era insatisfazível → delta de regressão contra baseline medido. | Pax (@po) |

## Dev Agent Record

### Agent Model Used

Claude Opus 5 (`claude-opus-5[1m]`) — @dev (Dex), modo YOLO autônomo, 2026-09-01.

### Debug Log References

- Dry-run real de produção: `artifacts/confenge/claim-safety/dry-run-run-adb0097e32b02188.json`
- Fixture de retrocompatibilidade de hash: `tests/confenge_claim_safety/fixtures/legacy-manifest-run-adb0097e32b02188.json`

### Medição real de produção (Task 7 / Decisão nº 4 do @po)

Executado contra cópia read-only (`rsync`) do release imutável `run-adb0097e32b02188-feee0d2d91fb-a77fd763126c`, apontado pelo symlink `current` em `ec-prod`. Nenhuma escrita em produção.

| Métrica | Valor medido |
|---|---|
| `lead_count` | 8.667 (bate com o manifest) |
| `UNSAFE_PRESENT_CLAIM` | **98** — não ≈179 |
| `SAFE_NO_CURRENT_CLAIM` | 8.569 |
| `SAFE_HISTORICAL` | 0 |
| `SAFE_CURRENT_PROVEN` | 0, com `reason_code: active_proven_unreachable_from_published_payload` |
| `NEEDS_RESEARCH` | 0 |
| Exit code | 1 (unsafe encontrado em dry-run) |

Classificação por `why_now_code` (responde diretamente à **ressalva registrada** do @po):

| `why_now_code` | Contagem | Classe |
|---|---|---|
| `ADDENDUM` | 98 | `UNSAFE_PRESENT_CLAIM` |
| `GLOSA_MEDICAO` | 78 | `SAFE_NO_CURRENT_CLAIM` |
| `REEQUILIBRIO` | 3 | `SAFE_NO_CURRENT_CLAIM` |
| `PORTFOLIO_REVIEW` | 7.131 | `SAFE_NO_CURRENT_CLAIM` |
| `INSUFFICIENT_FACTS` | 1.357 | `SAFE_NO_CURRENT_CLAIM` |
| `MATURE_NO_REAJUSTE` | 0 | — (ausente do release, conforme baseline) |

**A ressalva do @po estava correta.** `GLOSA_MEDICAO` ("Sinais de glosa ou medição contestada no material ingerido.") e `REEQUILIBRIO` ("Menção a reequilíbrio em material contratual ingerido.") usam frame de observação passiva e **não** constituem claim `PRESENT`. O universo inseguro real é exatamente o conjunto `ADDENDUM` = 98, ou seja, 1,13% do feed (não 2,1%). Nenhum AC fixava 179, então nada falha.

Todos os 98 têm `activity_state == UNKNOWN` (`reason: missing_status_and_vigencia`), consistente com o fato de baseline de que 100% dos contratos publicados têm `start_date` NULL.

### Falso positivo encontrado e corrigido durante a medição (relevante para o @qa)

A **primeira** execução do dry-run reportou 103 unsafe: 98 `ADDENDUM` + **5 `PORTFOLIO_REVIEW`**. Os 5 eram **falsos positivos** — exatamente a classe de defeito que o AC 8 existe para impedir. Causa: a remoção de spans de evidência era gulosa da esquerda para a direita, e um fragmento curto de `fact_to_mention` (iniciado em `"objeto: "`) consumia a posição e bloqueava o span de 140 caracteres do objeto real oito caracteres adiante — deixando `"em execução de obras de EMPREENDIMENTOS HABITACIONAIS…"` de pé na superfície de asserção.

Correção em `claim_surface.strip_evidence_spans`: seleção de spans **não sobrepostos por maior comprimento** em vez de varredura gulosa. Fixada por `test_ac8_shared_boilerplate_prefix_does_not_truncate_the_stripped_span`. Após a correção o dry-run é estável em 98 e `PORTFOLIO_REVIEW` volta a 7.131 (= baseline exato do @architect).

### Desvios do plano original

1. **[MATERIAL] `facts.py` não foi editado — AC 9 já satisfeito por story concorrente não declarada.**
   Ao chegar na Task 5, `scripts/confenge_account_intelligence/facts.py` já estava modificado na working tree por **`story-outreach-claim-policy-01`** (status `Ready`, HIGH-RISK), que declara `facts.py` em seus `scope_files` e substituiu o literal `"Aditivos/alterações observados em contrato público recente ou ativo."` por um callable `_addendum_temporal_fact` cujo tempo verbal segue `CLAIM_POLICY` (`allows_present_tense`). A Decisão nº 3 do @po verificou interseção de escopo **apenas** contra `story-outbound-sector-classifier-false-positive-01`; esta terceira story não entrou na comparação.
   **Ação tomada:** não editar `facts.py`, para não sobrescrever trabalho ativo de outra story HIGH-RISK. AC 9 verificado e provado por **invariante** (não por igualdade de string) em `test_ac9_addendum_template_no_longer_asserts_present_activity`: o literal inseguro não existe mais, e um template ADDENDUM em forma de callable só pode emitir tempo presente sob `allows_present_tense(policy)`.
   **Requer reconciliação do @po**: sobreposição de `scope_files` não declarada entre três stories vivas.

2. **Neutralizador reforçado por causa da story concorrente.** O novo ramo presente de `_addendum_temporal_fact` emite `"…em contrato público com vigência ativa comprovada."`. A excisão apenas do token produzia `"…em contrato público com comprovada."` — copy quebrado. `rewrite._neutralize` passou a remover a **frase preposicional inteira** até o limite da oração, com queda de oração inteira como último recurso determinístico e um fallback neutro que impede `why_now` vazio. Coberto em `test_neutralizer_produces_well_formed_copy`.

3. **Enforcement do AC 20 implementado como invariante de corpus, não como segundo ramo de `rewrite`.** Após a reescrita, o `--apply` **reclassifica o corpus inteiro** e recusa (exit 2, sem publicar) se qualquer lead não cair em `PUBLISHABLE_CLASSES = {SAFE_NO_CURRENT_CLAIM, SAFE_CURRENT_PROVEN, SAFE_HISTORICAL}`. Isso fecha AC 6, 7, 10 (ambas as cláusulas) e o enforcement do AC 20 de uma vez, e falha fechado para um template não antecipado em vez de embarcá-lo.

4. **`moment.summary` incluído na superfície de asserção.** Não estava no texto da story, mas `moment.summary` é byte-idêntico a `messaging_context.why_now` no payload real. Reescrever só `why_now` republicaria o claim inseguro pelo campo espelho, e a verificação pós-apply passaria por só ler o campo corrigido. Coberto em `test_rewrite_updates_every_assertion_field_not_just_why_now`.

5. **`--apply` em produção NÃO executado.** ACs 10-14 e 17 são provados por teste sobre feed isolado, não contra o feed vivo — em respeito aos dois gates de fechamento do @po (re-freeze de campanha para `publish.py`; serialização atrás do release da sector-classifier). Ver "Estado dos ACs" abaixo.

6. **Âncora de rollback gravada condicionalmente, não em toda publicação.** Primeira versão escrevia `claim_safety_rollback_anchor` em qualquer publicação bem-sucedida. Isso deixaria a próxima publicação de rotina (`confenge_feed_cycle`, `make extra-weekly`) mover a âncora para o próprio release de claim-safety — e um rollback posterior restauraria o release corrigido, um no-op silencioso reportando sucesso. A escrita passou a ser condicionada a `manifest.claim_safety.corpus_hash`, o **mesmo gatilho** da inserção na hash. Coberto por `test_a_routine_publish_does_not_write_or_clobber_the_anchor` e `test_a_routine_publish_after_an_apply_leaves_the_anchor_intact`.

7. **`.gitignore` recebeu `artifacts/confenge/claim-safety/build/`** (fora do escopo IN declarado, adicionado como higiene direta do CLI): o `--apply` copia um release inteiro (~145 MB) para o build dir, e sem a regra um `git add -A` posterior arrastaria a cópia para o repositório. O relatório JSON da auditoria continua **rastreado**.

8. **DoD "suite completa" medido com duas exclusões.** `pytest tests/` aborta a coleta inteira com `INTERNALERROR` porque `tests/test_official_status_reconfirmation.py` e `tests/test_datalake_helper.py` importam `scripts/collect_report_data.py`, que faz `sys.exit(1)` quando `httpx` está ausente. Medição feita com `--ignore` desses dois módulos e `--continue-on-collection-errors`.

### Estado dos 21 ACs

| AC | Estado | Evidência |
|---|---|---|
| 1 | SATISFEITO | `test_classify.py::test_ac1_templates_without_a_claim_are_safe` |
| 2 | SATISFEITO | `test_ac2_present_claim_over_active_proven_is_safe_current_proven`, `test_ac2_zero_safe_current_proven_is_reported_with_an_explicit_reason_code`, `test_ac2_published_payload_shape_cannot_reach_active_proven` + `reason_codes` no relatório real |
| 3 | SATISFEITO | `test_ac3_explicit_past_frame_anchored_on_a_date_is_safe_historical` |
| 4 | SATISFEITO | `test_ac4_ac16_present_claim_over_any_unproven_state_is_unsafe`, `test_ac4_unknown_activity_is_never_promoted_to_safe` |
| 5 | SATISFEITO | `test_ac5_present_claim_without_any_contract_needs_research`, `test_ac5_ambiguous_multi_contract_binding_fails_closed` |
| 6 | SATISFEITO | `test_rewrite.py::test_ac6_past_end_date_becomes_an_explicit_dated_historical_frame` |
| 7 | SATISFEITO | `test_ac7_future_or_null_end_date_drops_the_temporal_assertion` (parametrizado em `end_date` futuro e NULL) |
| 8 | SATISFEITO | `test_false_positive_objeto.py` — 3 objetos verbatim de produção × 2 códigos + teste do prefixo compartilhado |
| 9 | SATISFEITO (sem edição) | Duas metades: `test_ac9_addendum_template_no_longer_asserts_present_activity` (estrutural — literal inseguro ausente, presente só sob gate) e `test_ac9_callable_addendum_template_emits_no_present_claim_when_ungated` (**comportamental** — chama `_addendum_temporal_fact` com política que proíbe presente e verifica o copy emitido). Ver Desvio nº 1 |
| 10 | **PROVADO POR TESTE; apply de produção DIFERIDO** | `test_idempotency.py::test_ac10_*` sobre feed isolado. Ambas as cláusulas (unsafe = 0 **e** zero template não reconhecido com claim de presente) verificadas pelo invariante de corpus |
| 11 | **PROVADO POR TESTE; apply de produção DIFERIDO** | `test_ac11_second_apply_is_an_observable_skip_not_a_second_release` (`status: skipped_no_change`, `releases/` inalterado) |
| 12 | **PROVADO POR TESTE; apply de produção DIFERIDO** | `test_ac12_lead_count_and_source_lead_ids_are_identical` |
| 13 | **PROVADO POR TESTE; apply de produção DIFERIDO** | `test_ac13_target_fit_fields_are_byte_identical_and_target_confirmed_untouched` |
| 14 | **PROVADO POR TESTE; apply de produção DIFERIDO** | `test_ac14_membership_is_unchanged_and_the_delta_guard_does_not_fire` — `_assert_membership_deactivation_delta` real é executado e permanece silencioso |
| 15 | SATISFEITO | mesmo teste do AC 8 |
| 16 | SATISFEITO | `test_ac4_ac16_*` parametrizado sobre `ACTIVITY_STATES - {ACTIVE_PROVEN}` importado de `contracts_truth` |
| 17 | **PROVADO POR TESTE; rollback de produção DIFERIDO** | `test_rollback.py` — âncora gravada antes do swap (e **só** para publicação de claim-safety), estabilidade da âncora sob publicação de rotina, restauração, revalidação do delta guard, e 3 recusas fail-closed |
| 18 | SATISFEITO | `test_dry_run_no_writes.py` — snapshot sha256+mtime de toda a árvore `feed-www/` e de `publication-state.json` antes/depois |
| 19 | SATISFEITO | `test_hash_backcompat.py` — ancorado no digest real de produção `a77fd763126c…2ec7`, verificado reproduzível **antes** da mudança em `publish.py` |
| 20 | SATISFEITO | `test_ac20_*` (classificação) + `test_ac20_needs_research_leads_are_rewritten_into_a_publishable_class` (enforcement) |
| 21 | SATISFEITO | `test_template_set_drift.py` — extração por AST de `facts.py::why_now`, cobrindo `ast.Assign` e `ast.AnnAssign`, com guarda anti-vacuidade |

**Resumo honesto:** 21/21 provados por teste; **6 deles (10-14, 17) não foram exercidos contra produção**, por decisão explícita dos gates de fechamento do @po, não por limitação técnica.

### Gates

| Gate | Resultado |
|---|---|
| `pytest tests/confenge_claim_safety/ -v` | **70 passed** |
| Regressão de publicação (`tests/test_confenge_feed_publication.py`, `tests/warmbly_bridge/`, `tests/confenge_activation/`, `tests/confenge_outreach_pipeline/`) | **240 passed** |
| Suite ampla (`tests/`, 2 módulos ignorados por `httpx` ausente) | 5.548 passed, 134 failed, 53 errors, 271 skipped — **nenhum** dos 18 arquivos com falha importa qualquer módulo do escopo desta story; todas as falhas são o baseline ambiental documentado (dependências ausentes, sem Postgres local) |
| `ruff check` (arquivos novos e modificados) | All checks passed |
| `ruff format --check` | limpo |
| `mypy` | **não executado** — `mypy` não está instalado neste ambiente (`No module named mypy`) |

### Plano de deploy (Task 7)

1. PR de código (esta story) — inclui `publish.py`, que é input protegido do freeze `CONFENGE-COMMERCIAL-READY-01`.
2. PR separado **artifact-only** de re-freeze da campanha (Decisão nº 2 do @po). Sem ele o `code-freeze-gate` permanece `BLOCKED_PROTECTED_INPUT_CHANGED` e o @devops não publica.
3. Só então, e apenas após a publicação do release da `story-outbound-sector-classifier-false-positive-01` (ou registro explícito no relatório de que não houve — Decisão nº 3):
   `python3 -m scripts.confenge claim_safety_audit --apply --report-json <path>`
4. Verificar no relatório: `status: published`, `unsafe_present_claim_count: 0`, `release_dir` novo, `rollback_plan.anchor` preenchido.
5. Rerun imediato para provar idempotência: esperado `status: skipped_no_change`, sem segundo release.
6. Rollback, se necessário: `python3 -m scripts.confenge claim_safety_audit rollback`.

**@dev não executou nenhum passo remoto.** Publicação remota, PR e release são autoridade exclusiva de @devops.

### Acoplamento declarado ao @qa

`test_ac9_callable_addendum_template_emits_no_present_claim_when_ungated` importa `scripts/confenge_claim_policy` (`ClaimCandidate`, `evaluate_claim_policy`, `allows_present_tense`), módulo **de propriedade da story concorrente** `story-outreach-claim-policy-01`. Se a assinatura desse construtor mudar, o teste quebra. Essa quebra é o sinal de drift pretendido, **não** uma regressão desta story. O teste faz `skip` explícito se `facts.py` voltar a carregar uma string fixa (nesse caso o teste estrutural cobre sozinho).

### Dívida técnica registrada

Nenhum TODO/FIXME introduzido. Nenhuma dependência nova. Nenhum token/enum de `contracts_truth.py` duplicado (`classify.py` importa `ACTIVE_PROVEN` e `classify_contract_activity`). Nenhum caminho `/tmp` hardcoded em código ou testes (os testes usam a fixture `tmp_path` do pytest).

Um item para o backlog, **não** dívida desta story: promover `MATURE_NO_REAJUSTE` de `NEEDS_RESEARCH` para uma classe `SAFE_*` exige decisão de copy em story própria (Decisão nº 1 do @po). Hoje ele conta 0 e, quando voltar a ser alcançável, será reescrito para `SAFE_NO_CURRENT_CLAIM` pelo `--apply` em vez de embarcar não classificado.

### File List

**Criados:**

- `scripts/confenge_claim_safety/__init__.py`
- `scripts/confenge_claim_safety/policy.py`
- `scripts/confenge_claim_safety/claim_surface.py`
- `scripts/confenge_claim_safety/classify.py`
- `scripts/confenge_claim_safety/rewrite.py`
- `scripts/confenge/claim_safety_audit/__init__.py`
- `scripts/confenge/claim_safety_audit/cli.py`
- `tests/confenge_claim_safety/__init__.py`
- `tests/confenge_claim_safety/conftest.py`
- `tests/confenge_claim_safety/test_classify.py`
- `tests/confenge_claim_safety/test_false_positive_objeto.py`
- `tests/confenge_claim_safety/test_rewrite.py`
- `tests/confenge_claim_safety/test_template_set_drift.py`
- `tests/confenge_claim_safety/test_hash_backcompat.py`
- `tests/confenge_claim_safety/test_dry_run_no_writes.py`
- `tests/confenge_claim_safety/test_idempotency.py`
- `tests/confenge_claim_safety/test_rollback.py`
- `tests/confenge_claim_safety/fixtures/legacy-manifest-run-adb0097e32b02188.json`
- `artifacts/confenge/claim-safety/dry-run-run-adb0097e32b02188.json`

**Modificados:**

- `scripts/confenge_activation/publish.py` (duas mudanças cirúrgicas: `claim_safety_hash` condicional em `publication_semantic_hash`; `claim_safety_rollback_anchor` gravado antes do swap atômico)
- `scripts/confenge/__main__.py` (dispatch `claim_safety_audit` + texto de `--help`)
- `.gitignore` (ignora apenas `artifacts/confenge/claim-safety/build/`; ver Desvio nº 7)
- `docs/stories/story-claim-safety-audit-01.md`
- `.aiox/state/stories/claim-safety-audit-01.json`

**NÃO modificados (declarados no escopo IN, mas deliberadamente intocados):**

- `scripts/confenge_account_intelligence/facts.py` — ver Desvio nº 1. AC 9 já satisfeito por story concorrente que detém o arquivo.

## QA Results

_A preencher pelo @qa._

## Decisões do @po (validação `*validate-story-draft`, 2026-09-01)

Veredito: **GO — 8/10**. Nenhuma questão permanece em aberto para o @dev.

### Decisão nº 1 — O conjunto de `why_now_code` é 6, não 5 (ACs 20 e 21 acrescentados)

O @sm declarou o conjunto como "finito: 5 valores" e construiu toda a tese de desenho sobre essa enumeração. Verificação direta em `scripts/confenge_account_intelligence/facts.py::why_now` falsifica: existem **6** triggers produzíveis — `addendum`, `glosa_medicao`, `reequilibrio`, **`mature_no_reajuste`** (`pain_checks`), mais `insufficient_facts` e `portfolio_review` (fallbacks).

Por que isso importa numa story fail-closed: `MATURE_NO_REAJUSTE` não era coberto por nenhum AC e, sem default definido, um template não enumerado cai **aberto**, não fechado — exatamente a falha que a story existe para impedir.

Classificação do defeito: **não classificado**, não "comprovadamente inseguro". O texto do template ("Contrato maduro (com data de início observada) sem prova de reajuste no input — janela potencial de reajuste") é genuinamente ambíguo entre claim `PRESENT` e `NONE`. **Decisão: `NEEDS_RESEARCH`**, explicitamente e não por fallback. Promovê-lo a `SAFE_*` é decisão de copy que exige story própria.

Interação composta que agrava: `mature_no_reajuste` exige `start_date` não-nulo, e 100% dos 41.102 contratos publicados têm `start_date` NULL — por isso hoje conta 0 (a aritmética do baseline fecha exata: 7131+1357+98+78+3 = 8667 = `lead_count`). A story lista "publicar `status`/`observed_at` em `contracts[]`" como OUT/dependência futura. **Quando essa dependência for resolvida, este trigger volta a ser alcançável e embarcaria não classificado.** Daí o AC 21 (teste de drift): um 7º trigger deve quebrar o teste, não vazar em silêncio.

Restrição herdada: não existe enum em código para `why_now_code` — é string livre uppercased em `adapt.py:388`. Logo `classify.py` necessariamente manterá um conjunto de strings. A própria seção "Restrição de nova dívida técnica" da story proíbe duplicar tokens de `contracts_truth.py`; a mesma regra vale aqui — o conjunto deve ser derivado/fixado contra `facts.py`, sob pena de o AC novo criar a dívida que a story bane.

### Decisão nº 2 — Code-freeze de campanha sobre `publish.py`: declarado, não veta escopo

`scripts/confenge_activation/publish.py` é input protegido do freeze `CONFENGE-COMMERCIAL-READY-01` (`frozen-inputs-manifest.json`, política `frozen_confenge_inputs_v1`, 162 inputs). O gate `code-freeze-gate.json` já está `BLOCKED_PROTECTED_INPUT_CHANGED` no HEAD — **causado pelos commits #468, não por esta story** (`protected_changed` já lista `publish.py`, `commercial_authority.py`, `warmbly_bridge/export.py` e outros 4).

Essa distinção é o que torna isto um *declarar-e-sequenciar* em vez de um veto de escopo: **@dev deve sim mexer em `publish.py`**. O que muda é a rota de publicação — PR de código primeiro, depois PR separado artifact-only de re-freeze. Bloqueia @devops se não declarado; não bloqueia @dev.

Verificado que o restante do escopo IN está fora do conjunto protegido: `facts.py`, `scripts/confenge/__main__.py`, `contracts_truth.py` e todos os caminhos novos `scripts/confenge_claim_safety/`.

### Decisão nº 3 — Serialização: paralelo na implementação, serial só no `--apply`

O @sm deixou isto como "Recomendação ao @po: sequenciar". Decisão do @po, fechada:

- **Zero overlap de arquivos, verificado empiricamente** contra `scope_files` de `.aiox/state/stories/outbound-sector-classifier-false-positive-01.json`. A sector-classifier toca `contract_relevance.py`, `pipeline.py`, `target_fit.py`, `identity.py`, `eligibility.py`, `parafiscal.py`, `confenge_target_fit/compute.py` + testes. Esta story toca `confenge_claim_safety/*` (novo), `confenge/claim_safety_audit/cli.py` (novo), `confenge/__main__.py`, `confenge_activation/publish.py`, `facts.py`, `tests/confenge_claim_safety/`. **Interseção vazia.**
- Portanto: **implementação, testes e `--dry-run` rodam em paralelo.**
- **Somente o `--apply` em produção é serializado** atrás da publicação do release da sector-classifier, porque ambos disputam a sequência de releases em `/opt/confenge-plane/feed-www/` e deltas de `lead_count`/`membership` de duas mudanças concorrentes seriam indistinguíveis.
- Razão de não serializar o ciclo inteiro: a sector-classifier está em `qa_verdict: FAIL`, dev loop iteração 2, com REQ-003 aberto como gate de fechamento. Serializar tudo travaria esta story por tempo indeterminado sem nenhum motivo em nível de arquivo.

### Decisão nº 4 — A estimativa de ≈179 é baseline a confirmar e **não** trava a validação

Confirmado, com evidência textual: a seção Baseline diz "≈179 (a confirmar exatamente pelo @dev ao rodar `claim_safety_audit --dry-run` contra o release corrente)"; a Task 7 manda "confirmar/atualizar o número". Decisivo: **nenhum AC fixa 179 como número.** O AC 10 exige `UNSAFE_PRESENT_CLAIM == 0` no release pós-apply — uma invariante de estado-alvo, não uma asserção de baseline. Se o dry-run real medir 150 ou 210, nada na story falha. Tratamento correto, sem ressalva.

### Decisão nº 5 — DoD "suite verde" era insatisfazível

O @sm exigiu `pytest tests/ -q --tb=no -x` (suite completa) **verde**. Esse requisito não é atingível neste repositório: a medição do @qa na story sector-classifier registra 135 failed / 51 errors **constantes** antes e depois da mudança (186 IDs de falha idênticos), todas ambientais (dependências ausentes e sem Postgres local). Um AC/DoD insatisfazível força waiver no fechamento e corrói o gate. **Substituído por:** zero regressão contra baseline medido, via delta before/after do conjunto de IDs de falha — o mesmo método que o @qa já usou e que o @po já aceitou como evidência na story irmã.

### Ressalva registrada (não bloqueante)

O universo estimado de ≈179 leads deriva de um bind com `GLOSA_MEDICAO`/`REEQUILIBRIO` cujos templates (`"Sinais de glosa ou medição contestada no material ingerido."`, `"Menção a reequilíbrio em material contratual ingerido."`) usam frame de observação passiva e podem não constituir claim `PRESENT` sob a extração de `claim_surface.py`. O @dev deve reportar a classificação real de cada `why_now_code` no relatório do dry-run, não assumir que os 179 são todos `UNSAFE_PRESENT_CLAIM`. Isso já está coberto pela Task 7 e pelo AC 10.

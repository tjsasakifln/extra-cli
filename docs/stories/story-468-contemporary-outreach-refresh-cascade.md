# Story #468: Cascata contemporânea do feed autoritativo CONFENGE

## Status

**InProgress**

## Executor Assignment

executor: "@dev"
quality_gate: "@architect"
quality_gate_tools: ["pytest", "systemd-analyze", "dod_controller", "coderabbit"]

## Story

**Como** founder responsável pela ativação do outbound da CONFENGE,
**quero** que cada fechamento contemporâneo e completo da fonte dispare, em ordem, a reconciliação target-fit, a descoberta de contato e a publicação atômica,
**para que** o reservoir do Warmbly seja abastecido continuamente pelo mesmo run/hash sem transformar o `extra-cli` em scheduler comercial.

## Contexto e autoridade

- Origem P0: [extra-cli #468](https://github.com/tjsasakifln/extra-cli/issues/468), complementada por #469 e #381.
- O founder revogou contemporaneamente o freeze operacional anterior e autorizou ativação e abastecimento contínuo. O checkpoint foi registrado em [#468](https://github.com/tjsasakifln/extra-cli/issues/468#issuecomment-5425203178), deve preceder a primeira publicação live e não relaxa nenhum guard fail-closed.
- O código e os contratos de publicação foram entregues no PR #511. O residual desta story é operacional: hoje os serviços de source, target-fit, contato e feed possuem cadências independentes ou timers desabilitados, de modo que um source run completo não conduz deterministicamente os estágios seguintes.
- A cascata é agendamento de pipeline de dados. Não cria fila comercial, scheduler de e-mail, CRM, approval, outcome store ou envio.

## Scope

**IN:** dependências systemd entre os quatro estágios já existentes, um gate que reutiliza o contrato de freshness vigente, testes do grafo, runbook, deploy e prova live.

**OUT:** thresholds, nova fonte/consumer, fila ou cadência de e-mail, CRM, approval, outcomes, composer, cohort, Warmbly mutável e compra/guess de contatos.

## Dependencies and sizing

- Pré-requisitos já entregues: PR #511 no `main`, freshness PNCP versionada, reconcile target-fit, contact cycle, publisher atômico e consumer Warmbly existente.
- Dependência externa live: disponibilidade e fechamento completo do PNCP. Indisponibilidade bloqueia publicação, não implementação/deploy da cascata.
- T-shirt size: **M**. O diff é pequeno, mas o risco operacional é P0 e exige deploy exato, rollback e observação live.

## Risks and mitigations

- `exit 75` parecer sucesso ao systemd: mitigado pelo gate semântico separado, que exige `FRESH`/0.
- Overlap de ciclos: mitigado pelos locks existentes, validação de mesma membership/run no publisher e recuperação no próximo source slot; nenhum resultado divergente promove.
- Loop ou bypass entre units: mitigado por grafo linear sem `OnSuccess` no feed e teste estático do conjunto exato de arestas.
- Fonte externa indisponível: último feed válido permanece servido e a issue recebe blocker factual; nenhum timestamp é renovado.

## Acceptance Criteria

1. O término bem-sucedido de `pncp-contracts.service` aciona um gate dedicado que avalia o contrato live `PNCP_CONTRACT_FRESHNESS/1.0`; somente `FRESH`/exit 0 prossegue. `LOCK_BUSY`/75, `DEGRADED`, `STALE`, `UNKNOWN`, partial e error interrompem a cascata.
2. O gate aprovado aciona `extra-confenge-target-fit-reconcile.service`; somente o sucesso real da reconciliação aciona `extra-confenge-contact-cycle.service`, e somente o sucesso real do ciclo de contatos aciona `extra-confenge-feed-cycle.service`.
3. Falha em qualquer estágio não aciona o sucessor, não altera o symlink `current` e preserva o último feed válido. Os `OnFailure` existentes continuam ativos e o reconcile/gate ganham alerta explícito.
4. O encadeamento não depende dos timers independentes de target-fit, contato ou feed e não habilita nenhum deles. O único disparador recorrente necessário é o timer canônico da fonte; o monitor do feed permanece independente.
5. Reexecução é segura: os locks existentes evitam writers concorrentes; membership/run/hash continuam reproduzíveis; snapshot sem mudança semântica continua recusado como `SAME_SNAPSHOT_NOT_FRESHNESS` e não toca `generated_at`.
6. Testes estáticos verificam grafo, gate e ausência de bypass; teste funcional do contrato comprova exits 0/1/2 e que exit 75 nunca promove. Todas as units alteradas passam por validação do repositório e `systemd-analyze verify` no ambiente disponível.
7. O runbook documenta o grafo, os estados que interrompem a cascata, instalação, observabilidade, rollback e a separação explícita entre refresh de dados e scheduling comercial.
8. Deploy usa o SHA exato com CI verde. Em produção, um source run contemporâneo completo deve atravessar a cascata ou ser executado manualmente na mesma ordem; a publicação só fecha #468 com `coverage_complete=true`, terminais exaustivos e prova Warmbly do mesmo `source_run_id`/`source_snapshot_hash`.
9. Os updates de #468/#469/#381 reportam números LIVE e hashes do run publicado. Se a fonte real não permitir 1.000 contas com recipient atribuível, o máximo real e a decomposição nominal do gargalo são publicados sem fabricar volume.

## Tasks / Subtasks

- [x] Task 1 — Codificar o grafo fail-closed (AC: 1–5)
  - [x] Adicionar unit oneshot de freshness gate que executa o contrato live com `--health`.
  - [x] Encadear source → gate → target-fit reconcile → contact cycle → feed cycle por `OnSuccess`.
  - [x] Preservar locks, `OnFailure`, usuários, environment files e limites atuais.
- [ ] Task 2 — Provar o contrato operacional (AC: 5–7)
  - [x] Adicionar testes do grafo, do comando do gate e dos bloqueios `DEGRADED`/`STALE`/75.
  - [ ] Rodar testes focados, validator systemd e `systemd-analyze verify`.
  - [x] Atualizar o runbook com instalação, health, journals e rollback.
- [ ] Task 3 — PR, deploy e prova live (AC: 8–9)
  - [ ] Rodar gates de reviewability, CI e review; mergear e implantar somente o HEAD exato.
  - [ ] Observar ou iniciar o source run contemporâneo sem contornar a fonte; avançar apenas com `FRESH` e cobertura completa.
  - [ ] Publicar atomicamente, provar readback do Warmbly no mesmo run/hash e atualizar #468/#469/#381.

## Dev Notes

### Contratos e decisões

- `SuccessExitStatus=75` em `pncp-contracts.service` representa contenção esperada do writer para o systemd, mas o contrato de freshness o classifica explicitamente como não `FRESH`. Por isso o source não pode apontar diretamente para target-fit. [Source: `deploy/systemd/pncp-contracts.service`; `scripts/ops/pncp_contract_freshness.py`]
- `python -m scripts.ops.pncp_contract_freshness --live --health` retorna 0 apenas para `FRESH`, 1 para `DEGRADED` e 2 para `STALE`/`UNKNOWN`. Esse contrato existente é o gate, sem nova segunda verdade. [Source: `scripts/ops/pncp_contract_freshness.py`; `tests/test_pncp_contract_freshness.py`]
- `OnSuccess=` é uma dependência de transição entre oneshots, não um timer. Cada serviço mantém seu próprio lock e somente saída bem-sucedida aciona o sucessor.
- O publisher já valida fonte, membership exata, cobertura terminal, hashes, max age e promoção atômica; snapshot semanticamente idêntico não renova freshness. [Source: `scripts/ops/confenge_feed_cycle.py`; `scripts/confenge_activation/publish.py`]

### Relevant source tree

- Units: `deploy/systemd/{pncp-contracts,extra-confenge-target-fit-reconcile,extra-confenge-contact-cycle,extra-confenge-feed-cycle}.service`
- Freshness: `scripts/ops/pncp_contract_freshness.py`
- Tests: `tests/test_pncp_contract_freshness.py`, `tests/confenge_target_fit/test_cli_and_invariants.py`, `tests/test_confenge_contact_cycle.py`, `tests/test_confenge_feed_publication.py`, `tests/test_local_resilience.py`
- Runbooks: `docs/ops/confenge-outreach-pipeline.md`, `docs/ops/confenge-activation-planner.md`

### Operational safeguards

- Nenhuma alteração de threshold, `skip`, `xfail`, mock irreal ou promoção de estado incompleto.
- Nenhum dado live, PII, dump, log ou secret entra no Git; evidence pack pesado permanece como artifact/host protegido.
- A primeira onda é instalação + validação das units; a cascata só é observada live depois de CI/merge/deploy do SHA exato.
- Rollback remove os `OnSuccess` adicionados e a unit de gate, recarrega o daemon e mantém o último `current` válido; não apaga releases nem estado durável.

## Testing

- Focado: `python3 -m pytest tests/test_confenge_outreach_refresh_cascade.py tests/test_pncp_contract_freshness.py -q --tb=short`
- Systemd: `python3 -m scripts.ops.validate_systemd` e `systemd-analyze verify` das cinco units.
- Regressão do raio: target-fit, contact cycle, feed publication e outreach pipeline.
- Gates canônicos: suíte completa, golden path com DSN explícito e policies fail-closed de PR.

## 🤖 CodeRabbit Integration

### Story Type Analysis

**Primary Type:** Integration

**Secondary Type(s):** Deployment

**Complexity:** Medium — mudança pequena de units com impacto operacional P0.

### Specialized Agent Assignment

**Primary Agents:**

- @dev — implementação, testes e pre-commit.
- @github-devops — PR, instalação das units e deploy do SHA exato.

**Supporting Agents:**

- @architect — gate independente do grafo e do raio arquitetural.
- @qa — verificação dos ACs, regressões e evidência live.

### Quality Gate Tasks

- [ ] Pre-Commit (@dev): review do diff exato; se o CLI local não existir, registrar ausência sem falso-verde.
- [ ] Pre-PR (@github-devops): generated-artifacts policy, reviewability e CI no HEAD.
- [ ] Pre-Deployment (@github-devops): `systemd-analyze verify`, daemon-reload, status do grafo e rollback explícito.

### Self-Healing Configuration

**Expected Self-Healing:**

- Primary Agent: @dev (light mode)
- Max Iterations: 2
- Timeout: 15 minutes
- Severity Filter: CRITICAL only

**Predicted Behavior:**

- CRITICAL: corrigir até duas iterações e parar se persistir.
- HIGH: documentar para o quality gate; não reduzir guard nem ocultar falha.

### CodeRabbit Focus Areas

**Primary Focus:**

- Bypass por `SuccessExitStatus=75`, partial/stale/error ou falha silenciosa.
- Loops/deadlocks de `OnSuccess`, concorrência de locks e preservação do último feed válido.

**Secondary Focus:**

- Nenhum secret ou path mutável incorporado ao artefato.
- Nenhum acoplamento a scheduling comercial ou mutação do Warmbly.

## Change Log

| Date | Version | Description | Author |
|---|---|---|---|
| 2026-08-26 | 0.1.0 | Draft P0 do residual de abastecimento contínuo do #468 | River (@sm) |
| 2026-08-26 | 0.1.1 | Validated GO (10/10) — Status: Draft → Ready | Pax (@po) |
| 2026-08-26 | 0.2.0 | Desenvolvimento iniciado — Status: Ready → InProgress | Dex (@dev) |
| 2026-08-26 | 0.2.1 | Grafo, gate causal, testes e runbook implementados; host/live permanecem abertos | Dex (@dev) |

## Dev Agent Record

### Agent Model Used

GPT-5 Codex (Dex / @dev)

### Debug Log References

- Focados: `40 passed` em 1,00s.
- Regressão integrada: `110 passed, 1 skipped`; o caso condicionado a PostgreSQL foi reexecutado com `REQUIRE_REAL_DB=1` e passou.
- Suíte canônica: `5928 passed, 240 skipped, 11 deselected` em 1466,09s.
- Source contracts offline: `17/17` verdes.
- Golden path real local: `PARTIAL`, exit 2; PNCP 2×720s timeout, PCP 141 fetched/135 inserted, ComprasGov `success_zero`; freshness bloqueou `pncp, contracts`.
- `scripts.ops.validate_systemd`, Ruff e `git diff --check`: verdes. `systemd-analyze verify` fica aberto para o host com `/opt`/PostgreSQL reais.
- CodeRabbit local: CLI atual exigiu autenticação interativa por navegador e foi encerrado sem resultado; review não foi declarado verde.

### Completion Notes List

- A cascata usa somente `OnSuccess` entre oneshots existentes e termina no feed; não existe timer/componente comercial novo.
- `pncp_contract_freshness` agora impede que uma tentativa mais nova sem fechamento reutilize a freshness de um fechamento anterior.
- Stale/partial/error/75 interrompem antes de target-fit; falhas posteriores interrompem o sucessor; o publisher continua responsável por coverage, hash e troca atômica.
- O host Debian 13 usa systemd 257, compatível com `OnSuccess`; instalação e verificação do fragmento aguardam merge/CI no SHA exato.
- A indisponibilidade PNCP permanece blocker factual para source run contemporâneo e publicação, sem alteração de threshold ou reuso do feed antigo.

### File List

- `.ai/story-468-validation.json`
- `deploy/systemd/extra-confenge-source-freshness-gate.service`
- `deploy/systemd/pncp-contracts.service`
- `deploy/systemd/extra-confenge-target-fit-reconcile.service`
- `deploy/systemd/extra-confenge-contact-cycle.service`
- `deploy/systemd/extra-confenge-feed-cycle.service`
- `docs/ops/confenge-activation-planner.md`
- `docs/ops/confenge-outreach-pipeline.md`
- `docs/stories/story-468-contemporary-outreach-refresh-cascade.md`
- `scripts/ops/pncp_contract_freshness.py`
- `tests/test_confenge_outreach_refresh_cascade.py`
- `tests/test_pncp_contract_freshness.py`

## QA Results

Architect gate: **PASS WITH CONCERNS**, sem CRITICAL/HIGH. O grafo, causalidade,
fail-closed e raio foram aprovados. Concern MEDIUM: ciclos downstream muito
longos podem sobrepor slots de 4h; locks e hashes bloqueiam promoção divergente,
mas duração deve ser observada live. `systemd-analyze verify` no host e review
CodeRabbit autenticado permanecem gates antes do live.

# Story — Message spine perde a identidade oficial do contrato

- **ID:** `message-spine-official-contract-identity-01`
- **Status:** Done
- **Risco:** STANDARD
- **Base:** `main` @ `ad4d18f8`
- **Origem:** bug pré-existente em `main`, introduzido pelo #534. Descoberto ao
  integrar o #532 (os testes do CLAIM_POLICY o expuseram).

## Problema

`normalize_record` resolve a identidade oficial do contrato
(`contrato_id`, `numero_controle_pncp`, `contract_id`) para o campo `id` do fact
bag:

```python
# scripts/confenge_account_intelligence/normalize.py
"id": public_contract_id(c) or f"contract-{i + 1}",
```

Em seguida, `extract_contract_hook` **re-deriva** a identidade a partir dos nomes
oficiais, sobre um dicionário que já foi normalizado:

```python
# scripts/confenge_account_intelligence/message_spine.py (main)
cid = public_contract_id(c) or f"contract-{i}"
```

Num bag normalizado esses campos não existem mais — a identidade vive em `id`.
Logo `public_contract_id` retorna `""` **sempre**, e todo `evidence_id` degrada
para um substituto posicional: `cf-contract-contract-0`.

## Impacto

O `evidence_id` deixa de apontar para um contrato público real. É exatamente a
perda de identidade oficial que o #534 existe para impedir, ocorrendo dentro do
próprio #534. Consumidores a jusante que casam evidência por id
(`strict_national_esr.py` remove os prefixos `cf-contract-`/`ev-contract-` para
reconciliar) passam a receber um índice posicional em vez do identificador PNCP.

### Severidade real — achado do @qa (não é cosmético de id)

Em `scripts/confenge_activation/strict_national_esr.py:720-724`,
`_primary_contract` monta o conjunto `wanted` removendo os prefixos
`cf-contract-`/`ev-contract-` dos `fact_evidence_ids` e escolhe o contrato cujo
`contract_id` pertence a esse conjunto, com `contracts[0]` como fallback:

```python
wanted = {str(value).removeprefix("cf-contract-").removeprefix("ev-contract-") for value in evidence_ids}
chosen = next(
    (row for row in contracts if str(row.get("contract_id") or "") in wanted),
    contracts[0] if contracts else {},
)
```

Com o bug, `wanted` valia `{"contract-0"}` — um índice posicional que **nunca**
casa com nenhum `contract_id` real. O `next(...)` portanto **sempre** caía no
fallback `contracts[0]`. Consequência: a evidência citada na mensagem podia ser
de um contrato **diferente** daquele efetivamente escolhido como primário. O
defeito não era só um identificador feio no `evidence_id`; era a quebra do
casamento evidência↔contrato. O fix restaura o casamento real.

Duas funções acima, no mesmo módulo, o código já faz o certo — lê `id` primeiro:

```python
cid = str(contract.get("id") or contract.get("contrato_id") or ... )
```

## Correção

```python
cid = public_contract_id(c, allow_legacy_surrogate=True) or f"contract-{i}"
```

`allow_legacy_surrogate=True` faz a função aceitar o `id` do registro. Num bag
normalizado esse `id` **é** a identidade oficial quando ela existia, e o
substituto posicional quando não existia — que é precisamente o contrato de
`normalize_record`. A regra do #534 (oficial primeiro, surrogate só por opt-in
explícito) fica preservada; o opt-in agora é declarado onde é legítimo.

## Critérios de aceite

- **AC1** — `Given` um contrato com `contrato_id`, `numero_controle_pncp` ou
  `contract_id` `When` o bag é normalizado e `extract_contract_hook` roda
  `Then` o `evidence_id` é `cf-contract-<id oficial>`.
- **AC2** — `Given` um contrato identificado `When` o hook roda `Then` o
  `evidence_id` nunca começa com `cf-contract-contract-`.
- **AC3** — `Given` um contrato sem identidade oficial `When` o hook roda
  `Then` ainda recebe um substituto estável e não vazio.

## Testes

Estado final (após o re-review do @qa em `7f2a6a8d`) — **8 casos em 2 arquivos**:

- `tests/confenge_account_intelligence/test_message_spine_contract_identity.py`
  — identidade no `extract_contract_hook`, lote misto, reordenação.
- `tests/confenge_activation/test_esr_contract_identity_reconciliation.py`
  — prova end-to-end `raw → normalize → spine → ESR` até `_primary_contract`,
  com *decoy row* em primeira posição.

Execução do @qa em checkout completo de `7f2a6a8d`: **8 passed em 127.14s**.
Verificado por mutação (remover `allow_legacy_surrogate=True` da linha 103 de
`message_spine.py`): **7 reprovam, 1 passa**. O sobrevivente é
`test_a_contract_with_no_official_identity_still_gets_a_stable_surrogate`,
corretamente insensível ao fix (AC3 cobre o caso sem identidade oficial, onde o
substituto posicional é o comportamento esperado com e sem o fix).

*Histórico do contador, reconciliado por medição e não por transcrição:* o
veredito original falava em "4 dos 5" (suite de `b4af8408`); `323855d7` alegou
"5 dos 7"; `0fe7e718` alegou "7 dos 8". O @qa executou a mutação em `7f2a6a8d` e
mediu 7/8 — a alegação mais recente confere.

## Escopo OUT

Não altera `normalize.py`, `public_contract_id`, nem a política do #534. Não
toca CLAIM_POLICY (#532) — esta correção é pré-requisito da integração dele,
não parte dela.

## Rollback

`git revert`. Sem migration e sem mudança de schema.

### Correção de imprecisão — impacto no release pinado

A redação original desta seção afirmava "sem impacto no release pinado". O @qa
demonstrou que a afirmação é **imprecisa** e ela fica retratada aqui:

- `scripts/confenge_account_intelligence/message_spine.py` **consta** em
  `artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01/frozen-inputs-manifest.json`
  (entrada `kind: file`, `blob_sha 637c085a`).
- O ADR `docs/architecture/adr-confenge-frozen-inputs-v1.md` (seção
  *Consequences → Negative / costs*) nomeia explicitamente
  "contract identity mapping (including the precedence between a PNCP control
  number and a technical table surrogate)" como política de pipeline comercial:
  alterá-la **exige re-freeze + rebind**.

Logo, esta correção é exatamente do tipo que invalida a evidência de freeze.

**Contexto atenuante (verificável, não asserido):** o manifesto pina
`blob_sha 637c085a`, que é o blob **pré-#534**. Derivação:

```
git rev-parse e693f2ae~1:scripts/confenge_account_intelligence/message_spine.py
  -> 637c085a959e894290e0bc193778abb2215f7a32   (= o blob pinado no manifesto)
git rev-parse ad4d18f8:scripts/confenge_account_intelligence/message_spine.py
  -> 364c0d1d272ba6c0d5ad771c3f70e33d09717b2f   (base desta story, já divergente)
git rev-parse b4af8408:scripts/confenge_account_intelligence/message_spine.py
  -> a5bd3efa1b42a6869e36d8e0e27a715b02d65393   (após esta correção)
```

A evidência de freeze **já estava inválida na base `ad4d18f8`** (divergiu desde
o #534, `e693f2ae`). O impacto marginal deste commit sobre a validade do freeze
é, portanto, **zero** — ele não invalida nada que já não estivesse inválido. O
que muda é o alvo do re-freeze pendente: ver `DOC-001` abaixo.

## Follow-ups

| ID | Sev | Item | Owner | Estado |
|----|-----|------|-------|--------|
| ARCH-001 | LOW | Surrogate "lavado" para dentro de campo de aparência oficial em `confenge_universe`: `resolve_physical_map(allow_legacy_surrogate_contract_id=True)` faz `normalize_contract_row` escrever `out["contrato_id"] = row["id"]` (`source.py:201-202`) **antes** de `out["contrato_id"] = public_contract_id(out)` (`source.py:215`), então `public_contract_id` devolve o surrogate pelo laço de campos oficiais. Permanece LOW: os 3 call sites (`rebuild.py:83`, `cli.py:125`, `pipeline.py:376`) não publicam o valor como identidade. **Código NÃO modificado por esta story.** | @dev | **ABERTO** — registrado como item de backlog rastreável no `DOD.md` (2026-09-02). Escopo: `confenge_universe`/`confenge_sector`. |
| TST-001 | LOW | AC3 estava coberto por asserção parcialmente infalsificável (passava com e sem o fix, por construção do caso). | @dev | **RESOLVIDO** por `7f2a6a8d`: a reordenação agora asserta sobre a saída de `extract_contract_hook(forward)/(backward)` (linhas 131-139 da suite), não mais apenas sobre o bag. Reprova sob mutação — está entre os 7 de 8 que caem. Verificado pelo @qa no re-review. |
| DOC-001 | LOW | Re-freeze pendente da campanha CONFENGE-COMMERCIAL-READY-01 (item já aberto pelo #534 no `DOD.md`) precisa agora cobrir um tip que **inclua `7f2a6a8d`** (o commit de código que toca o caminho pinado continua sendo `b4af8408`; o alvo subiu para o tip revisado). **NÃO executar re-freeze agora:** proibido nesta campanha até o código final estar definido, e ainda faltam entrar os PRs #531 e #532. | @devops | **ABERTO** — item de backlog rastreável no `DOD.md`, alvo atualizado em 2026-09-02. |

## Handoff — publicação LIBERADA, próximo agente é @devops

> **Histórico:** este bloco declarava publicação BLOQUEADA e próximo agente
> `@qa`. O bloqueio **está sanado**: o @qa re-revisou em 2026-09-02, estendeu o
> veredito PASS a `323855d7`, `0fe7e718` e `7f2a6a8d`, e reancorou
> `reviewed_commit` no tip de código `7f2a6a8d` (`72fe9ef6`). O @po reancorou o
> fechamento e liberou `publication_authorized: true`.

- Branch `fix/message-spine-official-contract-identity`. Commit de código de
  produção: `b4af8408` (único que toca `scripts/`). Tip de código revisado:
  `7f2a6a8d`. `reviewed_commit` ancorado em `7f2a6a8d`.
- **`publication_authorized: true`.** Base da liberação, verificada pelo @po
  neste worktree: `git diff --name-only b4af8408..HEAD -- scripts/` retorna
  **vazio** — nenhuma linha de código de produção mudou depois do commit já
  revisado no veredito original. Os três commits subsequentes são *test-only*
  (`323855d7`, `0fe7e718`, `7f2a6a8d`), e todos estão dentro do veredito
  estendido. Gates `lint: PASS` / `tests: PASS` seguem válidos para o código
  real: a suite (2 arquivos, 8 testes) foi executada pelo @qa em checkout
  completo de `7f2a6a8d` (8 passed, 127.14s), com mutação medida (7 failed / 1
  passed) confirmando o contador alegado.
- **Condição operacional para o @devops (1) — `reviewed_commit` vs `HEAD`.** O
  protocolo (seção 8) pede `reviewed_commit === HEAD`. A igualdade **não é
  atingível** nesta story: `HEAD` já era `72fe9ef6` (docs/state do @qa) antes do
  fechamento, e o próprio commit de fechamento do @po avança `HEAD` de novo —
  `--amend` está proibido nesta árvore (ver `po_git_incident`) e não há como
  antecipar o próprio SHA. A divergência é **docs/state-only e auditável**:
  `git diff --name-only 7f2a6a8d..HEAD -- scripts/ tests/` é vazio. O @devops
  avalia essa condição com a justificativa acima. Nenhum hook ativo a verifica —
  checado em três níveis: `checkPushGate` está exportado em
  `.claude/hooks/story-state.cjs:335` mas não é invocado por
  `enforce-git-push-authority.cjs` nem por `pre-push-gate.cjs`; `story-state.cjs`
  está registrado como comando em `.claude/settings.local.json:80` porém **não
  tem bloco `main`/CLI** (o arquivo termina em `module.exports`), logo executá-lo
  é no-op; e `pre-push-gate.cjs`, que de fato intercepta `git push`/`git commit`,
  só checa o frescor (<5 min) de `.claude/.pre-push-passed`. O @devops ainda
  precisa satisfazer **esse** gate (`/pre-push` + `touch`).
- **Condição operacional (2) — worktree.** O pre-push e o PR precisam ser feitos
  **a partir deste worktree**, com a story branch ativa. Enquanto ele existir, o
  checkout principal não consegue dar `git checkout` nesta branch (ver
  `qa_write_destination` no state file). Remover com `git worktree remove`
  somente depois da publicação.
- **Condição operacional (3) — isolamento do #532.** Verificado:
  `git log --oneline ad4d18f8..HEAD` traz exatamente os 7 commits desta story, e
  o único arquivo de produção da branch é
  `scripts/confenge_account_intelligence/message_spine.py`. Nenhum artefato de
  CLAIM_POLICY. O `pr532` está estacionado em outro worktree, em `8fc01192`. O PR
  deve ser **isolado**, sem misturar #532 — o rebase do #532 sobre esta branch
  conflita em `message_spine.py`/`normalize.py` e é trabalho de @dev, posterior.
- Re-freeze: ver `DOC-001` — **não executar nesta janela**.

## File List

- `scripts/confenge_account_intelligence/message_spine.py`
- `tests/confenge_account_intelligence/test_message_spine_contract_identity.py`
- `docs/stories/story-message-spine-official-contract-identity-01.md`
- `.aiox/state/stories/message-spine-official-contract-identity-01.json`
- `tests/confenge_activation/test_esr_contract_identity_reconciliation.py`
  *(entrou pós-QA em `0fe7e718`; **coberto** pelo veredito estendido de
  2026-09-02 — executado pelo @qa no re-review)*

## Change Log

| Data | Versão | Autor | Descrição |
|------|--------|-------|-----------|
| 2026-09-02 | 0.1 | @sm/@dev | Story criada a partir do bug exposto pela integração do #532. |
| 2026-09-02 | 0.2 | @dev | Implementação em `b4af8408`: `allow_legacy_surrogate=True` em `extract_contract_hook` + 5 testes de identidade. Ready → InProgress → InReview. |
| 2026-09-02 | 0.3 | @qa (Quinn) | QA gate **PASS** em `b4af8408`, verificado por mutação (4 dos 5 casos de identidade reprovam sem o fix) e com rastreamento completo dos call-sites. InReview → Done. 3 riscos residuais LOW. |
| 2026-09-02 | 0.4 | @po (Pax) | Fechamento administrativo. Corrigida a imprecisão do Rollback sobre o release pinado (evidência de freeze e ADR). Registrado o achado de severidade elevada do @qa em `strict_national_esr.py:720-724`. Follow-ups ARCH-001/TST-001 (@dev) e DOC-001 (@devops) registrados. Status `Done` preservado — nenhuma transição de ciclo de vida atribuída ao PO. Publicação **bloqueada** (`publication_authorized: false`): `323855d7` e `0fe7e718` entraram pós-QA e a âncora do veredito ficou obsoleta — próximo agente é @qa. `[closure-key: message-spine-official-contract-identity-01:commit:b4af8408]` |
| 2026-09-02 | 0.5 | @dev (sessão concorrente) | Dois commits *test-only* acrescentados **após** o QA gate, sobre `b4af8408`: `323855d7` (+46 linhas em `test_message_spine_contract_identity.py` — lote misto e reordenação) e `0fe7e718` (+83 linhas, arquivo novo `tests/confenge_activation/test_esr_contract_identity_reconciliation.py` — prova end-to-end até `_primary_contract`). **Fora do veredito PASS**, que nomeia `b4af8408` e só ele. Requerem re-review do @qa antes da publicação. |
| 2026-09-02 | 0.6 | @qa (Quinn) | Re-review. Veredito **PASS estendido** de `b4af8408` para `323855d7`, `0fe7e718` e `7f2a6a8d`; `reviewed_commit` reancorado no tip de código `7f2a6a8d` (commit `72fe9ef6`). Evidência de execução própria: suite de 2 arquivos em checkout completo de `7f2a6a8d` → 8 passed em 127.14s; mutação (remover `allow_legacy_surrogate=True`) → 7 failed / 1 passed, confirmando por medição o contador que antes era só transcrito. `TST-001` fechado. `ARCH-001` reconfirmado LOW após rastreamento dos 3 call sites de `allow_legacy_surrogate_contract_id`. Achado elevado: com o bug, `_primary_contract` (`strict_national_esr.py:720-724`) caía **sempre** no fallback `contracts[0]` — era quebra do casamento evidência↔contrato, não cosmética de identificador. |
| 2026-09-02 | 0.7 | @po (Pax) | **Reancoragem do fechamento e liberação da publicação.** Verificado neste worktree: `git diff --name-only b4af8408..HEAD -- scripts/` **vazio** (delta 100% *test-only*/docs), veredito estendido cobre os 3 commits pós-QA, gates `lint`/`tests` PASS válidos para o código real. `publication_authorized: false → true`. Status `Done` preservado — nenhuma transição de ciclo de vida atribuída ao PO. `reviewed_commit` (`7f2a6a8d`) ≠ `HEAD` por construção (commits docs/state posteriores; `--amend` proibido nesta árvore): divergência **docs-only**, auditável por `git diff --name-only 7f2a6a8d..HEAD -- scripts/ tests/` vazio, e registrada como condição a ser avaliada pelo @devops. Follow-ups LOW `ARCH-001` (@dev) e `DOC-001` (@devops) registrados como itens de backlog rastreáveis no `DOD.md`; `TST-001` marcado RESOLVIDO por `7f2a6a8d`. Próximo agente: **@devops** (`*pre-push`, PR isolado a partir deste worktree, sem misturar #532). `[closure-key: message-spine-official-contract-identity-01:commit:7f2a6a8d]` |

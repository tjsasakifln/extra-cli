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

`tests/confenge_account_intelligence/test_message_spine_contract_identity.py`
(5 casos). Verificado por mutação: com o código de `main`, 4 dos 5 reprovam; o
quinto (substituto legítimo) passa nos dois, como deve.

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

| ID | Sev | Item | Owner |
|----|-----|------|-------|
| ARCH-001 | LOW | `extract_contract_hook` não valida que o bag recebido é normalizado. Com `allow_legacy_surrogate=True`, um chamador direto que passe um bag **não** normalizado e sem campo oficial recebe o `id` bruto do registro. Não há caminho de produção (o único é `pipeline.build_dossier` → `normalize_record`). | @dev |
| TST-001 | LOW | AC3 está coberto por asserção parcialmente infalsificável (passa com e sem o fix, por construção do caso). Reforçar a asserção do substituto legítimo. | @dev |
| DOC-001 | LOW | Re-freeze pendente da campanha CONFENGE-COMMERCIAL-READY-01 (item já aberto pelo #534 no `DOD.md`) precisa agora cobrir um tip que **inclua `b4af8408`**. **NÃO executar re-freeze agora:** proibido nesta campanha até o código final estar definido, e ainda faltam entrar os PRs #531 e #532. | @devops |

## Handoff — publicação BLOQUEADA, próximo agente é @qa

- Branch `fix/message-spine-official-contract-identity`, commit de código
  revisado `b4af8408`. `reviewed_commit` permanece ancorado nele.
- **`publication_authorized: false`.** Durante o fechamento, **dois** commits
  *test-only* da mesma story, de sessão concorrente, foram criados sobre
  `b4af8408` e são ancestrais do commit de fechamento: `323855d7` (+46 linhas na
  mesma suite — lote misto e reordenação) e `0fe7e718` (+83 linhas, arquivo novo
  `tests/confenge_activation/test_esr_contract_identity_reconciliation.py`, prova
  end-to-end até `_primary_contract`). O veredito PASS nomeia `b4af8408` e só
  ele, e a âncora ficou obsoleta de forma verificável: o registro do @qa diz "4
  dos 5 casos reprovam" por mutação; `323855d7` diz "5 dos 7"; `0fe7e718` diz "7
  dos 8 da dupla de arquivos". A suite descrita pelo veredito foi superada duas
  vezes.
- Resta ainda **não commitada** na árvore uma modificação adicional (+14/-7) na
  mesma suite, que endereça `TST-001`. O @po não a commitou — está fora do
  veredito.
- **Próximo passo: @qa** estende o veredito a `323855d7` e `0fe7e718` e decide
  sobre a alteração pendente. É um delta *test-only*; não é reabertura do bug.
  Só então `reviewed_commit` é re-ancorado e `publication_authorized` vira
  `true`.
- Re-freeze: ver `DOC-001` — não executar nesta janela.

## File List

- `scripts/confenge_account_intelligence/message_spine.py`
- `tests/confenge_account_intelligence/test_message_spine_contract_identity.py`
- `docs/stories/story-message-spine-official-contract-identity-01.md`
- `.aiox/state/stories/message-spine-official-contract-identity-01.json`
- `tests/confenge_activation/test_esr_contract_identity_reconciliation.py`
  *(pós-QA, `0fe7e718` — fora do veredito)*

## Change Log

| Data | Versão | Autor | Descrição |
|------|--------|-------|-----------|
| 2026-09-02 | 0.1 | @sm/@dev | Story criada a partir do bug exposto pela integração do #532. |
| 2026-09-02 | 0.2 | @dev | Implementação em `b4af8408`: `allow_legacy_surrogate=True` em `extract_contract_hook` + 5 testes de identidade. Ready → InProgress → InReview. |
| 2026-09-02 | 0.3 | @qa (Quinn) | QA gate **PASS** em `b4af8408`, verificado por mutação (4 dos 5 casos de identidade reprovam sem o fix) e com rastreamento completo dos call-sites. InReview → Done. 3 riscos residuais LOW. |
| 2026-09-02 | 0.4 | @po (Pax) | Fechamento administrativo. Corrigida a imprecisão do Rollback sobre o release pinado (evidência de freeze e ADR). Registrado o achado de severidade elevada do @qa em `strict_national_esr.py:720-724`. Follow-ups ARCH-001/TST-001 (@dev) e DOC-001 (@devops) registrados. Status `Done` preservado — nenhuma transição de ciclo de vida atribuída ao PO. Publicação **bloqueada** (`publication_authorized: false`): `323855d7` e `0fe7e718` entraram pós-QA e a âncora do veredito ficou obsoleta — próximo agente é @qa. `[closure-key: message-spine-official-contract-identity-01:commit:b4af8408]` |
| 2026-09-02 | 0.5 | @dev (sessão concorrente) | Dois commits *test-only* acrescentados **após** o QA gate, sobre `b4af8408`: `323855d7` (+46 linhas em `test_message_spine_contract_identity.py` — lote misto e reordenação) e `0fe7e718` (+83 linhas, arquivo novo `tests/confenge_activation/test_esr_contract_identity_reconciliation.py` — prova end-to-end até `_primary_contract`). **Fora do veredito PASS**, que nomeia `b4af8408` e só ele. Requerem re-review do @qa antes da publicação. |

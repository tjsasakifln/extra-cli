# Story — Message spine perde a identidade oficial do contrato

- **ID:** `message-spine-official-contract-identity-01`
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

`git revert`. Sem migration, sem schema, sem impacto no release pinado.

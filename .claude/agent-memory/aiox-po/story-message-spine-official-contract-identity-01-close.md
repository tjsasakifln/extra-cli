---
name: story-message-spine-official-contract-identity-01-close
description: Fechamento PO da story message-spine-official-contract-identity-01 (QA PASS em b4af8408) — correcao de imprecisao de freeze, achado elevado do @qa e arvore compartilhada com agente concorrente
metadata:
  type: project
---

Fechamento administrativo de `message-spine-official-contract-identity-01`
(branch `fix/message-spine-official-contract-identity`, codigo em `b4af8408`,
base `ad4d18f8`). QA PASS pelo @qa, verificado por mutacao. `closure_key:
message-spine-official-contract-identity-01:commit:b4af8408`.

**Why:** tres coisas deste fechamento nao sao derivaveis do codigo nem do git log.

1. **"Sem impacto no release pinado" e falso por default nesta campanha.**
   `scripts/confenge_account_intelligence/message_spine.py` esta pinado no
   `frozen-inputs-manifest.json` da CONFENGE-COMMERCIAL-READY-01, e o ADR
   `docs/architecture/adr-confenge-frozen-inputs-v1.md` classifica "contract
   identity mapping" como politica que exige re-freeze + rebind. O atenuante que
   salvou esta story: o manifesto pina `blob_sha 637c085a` = `e693f2ae~1`, blob
   PRE-#534 — a evidencia de freeze ja estava invalida na base. Sempre derivar
   isso com `git rev-parse <commit>:<path>` em vez de asserir.
2. **O bug nao era cosmetico de identificador.** Com `evidence_id` degradado a
   `cf-contract-contract-0`, o `wanted` de `_primary_contract`
   (`strict_national_esr.py:720-724`) nunca casava e o `next(...)` caia SEMPRE em
   `contracts[0]` — a evidencia citada podia ser de contrato diferente do
   escolhido. Achado do @qa; eleva a leitura da severidade sem reabrir o gate.
3. **Fechamento com a arvore em movimento.** Um agente concorrente commitou
   DUAS vezes na mesma story durante este fechamento (`323855d7`, `0fe7e718`,
   ambos test-only). Resultado: `publication_authorized` ficou `false` — o
   veredito PASS nomeia `b4af8408` e as mensagens dos proprios commits provam
   que a suite mudou ("4 de 5" -> "5 de 7" -> "7 de 8"). `po_closed: true` com
   `publication_authorized: false` e a combinacao correta e ja tem precedente.
   Pior: um `git commit --amend` do @po reescreveu o commit do concorrente
   (7aeaff6f); reparado com `reset --soft` + `git commit -C 7aeaff6f`, tree
   conferida identica, nada publicado.

**How to apply:** NUNCA usar `git commit --amend` nesta arvore — ela tem agente
concorrente ativo e o HEAD anda entre a leitura e o commit; reconferir
`git rev-parse HEAD` imediatamente antes de qualquer commit. Se um `--amend`
atropelar commit alheio, o reparo e `git reset --soft <avo>` + `git reset` +
recommit com `git commit -C <sha-original>` (preserva mensagem, autor e data) e
`git diff <original> <novo>` para provar tree identica. Ao fechar story que toque
caminho pinado nesta campanha,
conferir o `frozen-inputs-manifest.json` e o ADR antes de aceitar qualquer frase
de rollback do @dev, e derivar o blob pinado com `git rev-parse`. Ao rodar gates
no fechamento, escopar `pytest` a UM arquivo (uma suite ampla escreve em
`artifacts/`/`output/`) e medir contra o blob revisado (`git show <sha>:<path>`),
nao contra a arvore — esta arvore tem agente concorrente ativo.

Relacionado: [[story-pncp-outbound-decoupling-close]],
[[epic-td-001-id-conflict]]

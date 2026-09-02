---
name: story-message-spine-contract-identity-reclose
description: Segunda passagem de fechamento PO da story message-spine-official-contract-identity-01 — publicacao liberada apos re-review do QA; padrao para reviewed_commit != HEAD docs-only
metadata:
  type: project
---

Story `message-spine-official-contract-identity-01` teve **dois** fechamentos PO.
O segundo (2026-09-02, commit `b7c26dde` na branch
`fix/message-spine-official-contract-identity`) liberou
`publication_authorized: true` com `closure_key
message-spine-official-contract-identity-01:commit:7f2a6a8d`.

**Why:** o primeiro fechamento (`closure_key ...:commit:b4af8408`) travou a
publicacao porque dois commits test-only de sessao concorrente entraram depois do
veredito QA. O @qa re-revisou, estendeu o PASS ao tip `7f2a6a8d` e reancorou
`reviewed_commit`; sobrou ao @po reconciliar e liberar.

**How to apply:**

1. **Duas closure keys convivem.** po-close-story.md manda inspecionar cada
   artefato independentemente e nao reverter escrita valida. Quando o veredito
   e reancorado, escreva a chave NOVA e **preserve** a antiga. DOD.md e Change
   Log ficaram com uma ocorrencia de cada.
2. **`reviewed_commit === HEAD` e inatingivel quando o fechamento gera commit.**
   HEAD avanca com os proprios artefatos de docs/state e `--amend` esta proibido
   nesta arvore. O criterio que substitui a igualdade literal:
   `git diff --name-only <reviewed_commit>..HEAD -- scripts/ tests/` **vazio**.
   Documente isso no state e transfira a avaliacao ao @devops.
3. **`checkPushGate` nao esta ativo.** Esta definido e exportado em
   `.claude/hooks/story-state.cjs` (linhas 197 e 335), mas nenhum hook o invoca —
   os consumidores de `story-state.cjs` sao `no-story-no-edit.cjs` e
   `db-destructive-guard.cjs`, que nao o chamam. Verifique antes de afirmar que
   um push esta "hard-blocked". Alem disso ele usa `findAnyStoryState`, que numa
   arvore com ~55 state files pega um arquivo arbitrario.
4. **Risco residual so conta como fechado se virar item de backlog rastreavel.**
   ARCH-001 existia apenas no state/story; foi promovido a item no `DOD.md` com
   mecanismo, call sites e escopo. DOC-001 ja estava la e teve o alvo atualizado.

Relacionado: [[story-message-spine-official-contract-identity-01-close]],
[[validation-process-po]].

---
name: feedback-stash-before-qa-gate
description: Story nao deve ser marcada InReview se alteracoes estao em stash, nao em HEAD/working tree
metadata:
  type: feedback
---

# Regra: Nao marcar InReview com alteracoes em stash

Story COVERAGE-2.3 foi marcada InReview mas as alteracoes estavam no stash (776fc08), nao aplicadas ao HEAD ou working tree.

**Why:** QA gate revisa o codigo atual, nao alteracoes pendentes. Se as mudancas estao em stash, o QA nao pode verificar ACs contra a implementacao real. Isso gera FAIL desnecessario que poderia ser evitado.

**How to apply:** Antes de atualizar status para InReview, verificar se `git stash list` esta vazio (para o branch atual) e `git diff HEAD` mostra as alteracoes esperadas da story. Se as alteracoes estao apenas em stash, manter como InProgress e aplicar o stash primeiro.

Relacionado: [[story-COVERAGE-2.3-qa-gate]]

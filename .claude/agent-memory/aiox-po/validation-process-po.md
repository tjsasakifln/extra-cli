---
name: validation-process-po
description: Protocolo de validacao PO (Pax) — 10-point checklist com atualizacao de status e decision log
metadata:
  type: feedback
---

Validacao PO usa 10-point checklist do `story-lifecycle.md`: titulo, descricao, ACs testaveis, escopo, dependencias, complexidade, valor de negocio, riscos, DoD, alinhamento com epic.

Resultado GO (>=7): atualizar status Draft → Ready, adicionar entry no Change Log.
Resultado NO-GO (<7): manter Draft, listar Must-Fix.

**Por que:** O `validate-next-story.md` e o `story-lifecycle.md` definem este fluxo como procedimento obrigatorio. A transicao de status e responsabilidade exclusiva do @po.

**Como aplicar:** Seguir o task file `validate-next-story.md` sequencialmente (steps 0-12). Nao pular a verificacao de executor assignment (step 1.1). Nao pular o post-validation status update (step 12).

[[epic-td-001-id-conflict]]

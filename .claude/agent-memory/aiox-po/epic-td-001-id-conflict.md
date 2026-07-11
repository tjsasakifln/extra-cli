---
name: epic-td-001-id-conflict
description: Story de expansao pos-completude do EPIC-TD-001 reusou ID TD-3.2 que ja pertence a story concluida (Eliminar Codigo Duplicado)
metadata:
  type: project
---

A expansao pos-completude do EPIC-TD-001 criou a story `docs/stories/td-3.2-pncp-resilience.md` (Fase 5 -- Resiliencia) usando o ID **TD-3.2**, que ja havia sido usado pela story original "Eliminar Codigo Duplicado" (Fase 3 -- Refactoring Seguro, Status: Done).

**Por que:** A story de resiliencia PNCP foi criada apos a completude das 22 stories originais do EPIC-TD-001 (commit e9729e1). O autor (@sm) reaproveitou o ID sem verificar o epic.

**Como aplicar:** Ao validar stories de expansao, verificar se o ID ja existe no EPIC e se ja foi concluido. Sugerir ID novo (ex: TD-5.6 para a 6a story da Fase 5).

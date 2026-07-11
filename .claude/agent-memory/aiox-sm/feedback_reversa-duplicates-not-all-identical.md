---
name: reversa-duplicates-not-all-identical
description: "Nem todos os 10 pares kebab/snake_case sao identicos — 4 tem diferencas reais, incluindo intel_collect.py com upgrades v1.5 nao presentes no kebab"
metadata:
  type: feedback
---

Antes de deletar qualquer duplicata, executar diff em CADA par. Nao confiar na afirmacao generica do Reversa de que sao todos identicos.

**Why:** A analise Reversa classificou os 10 pares como "identicos" mas a verificacao com diff revelou que 4 pares tem diferencas reais. O mais critico: intel_collect.py (snake) contem um upgrade v1.5 completo (429 handling, chunked mode, TCU tracking, etc.) que nao existe no kebab. Deletar o snake sem revisao perderia funcionalidade de resiliencia.

**How to apply:** Sempre executar diff antes de deletar. Para cada par diferente, documentar o output completo do diff e submeter a revisao humana. Nao confiar em analises automatizadas que afirmam identidade sem verificacao binaria.

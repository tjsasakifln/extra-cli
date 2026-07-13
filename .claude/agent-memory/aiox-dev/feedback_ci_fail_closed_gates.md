---
name: feedback-ci-fail-closed-gates
description: CI gates must be fail-closed — no continue-on-error, no || true, no skips amplos em segurança
metadata:
  type: feedback
---

CI gates devem ser **fail-closed**: qualquer falha em security, lint ou audit = CI vermelho.

- **Why:** Regra #10 (B2G-4) exige gates que bloqueiam em vez de apenas alertar. bandit com `continue-on-error: true` e `|| true` nao quebrava CI mesmo com HIGH severity.
- **How to apply:** NUNCA usar `continue-on-error: true` ou `|| true` em jobs de seguranca (bandit, pip-audit). Usar `--cov-fail-under` para coverage. Para exclusao de teste, preferir `-m "not slow"` em vez de excluir categorias inteiras como `integration` e `smoke`.

Ver [[feedback_silent_exceptions]] para principio similar sobre excecoes nao silenciadas.

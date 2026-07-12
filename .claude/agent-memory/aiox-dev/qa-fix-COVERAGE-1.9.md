---
name: qa-fix-Coverage-1.9
description: QA CONCERNS fix para COVERAGE-1.9 — 2 issues corrigidos (test naming + schema doc)
metadata:
  type: project
---

QA CONCERNS no gate COVERAGE-1.9-sc-dados-abertos-fix (2026-07-11). 2 issues:

- **TEST-001 (medium):** Metodo `handles_db_error_gracefully` sem prefixo `test_` — pytest ignorava silenciosamente. Renomeado para `test_handles_db_error_gracefully`. Testes foram de 27 para 28 passando.
- **DOC-001 (low):** Schema na story omitia `codigo_municipio_ibge` e `municipio_inferido` (colunas da migration 021). Adicionadas ao schema doc.

**Why:** QA Quinn identificou ambos. Gate CONCERNS significa que nao bloqueia, mas deve ser corrigido.
**How to apply:** Ao revisar gates CONCERNS, conferir se os issues foram mapeados. Ao criar stories com schemas de tabelas, verificar migrations associadas para garantir que a documentacao reflita o schema real.

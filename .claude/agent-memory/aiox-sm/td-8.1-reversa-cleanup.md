---
name: td-8.1-reversa-cleanup
description: "Story TD-8.1 para limpeza dos problemas identificados pelo Reversa: 10 scripts duplicados, subprocess.run em intel_pipeline.py, psycopg2-binary em producao"
metadata:
  type: project
---

**Story TD-8.1 criada** em 2026-07-11 para resolver 3 problemas do Reversa:
1. 10 pares de scripts duplicados (kebab vs snake_case) — 6 identicos, 4 divergentes
2. subprocess.run em intel_pipeline.py — refatorar para imports diretos
3. psycopg2-binary em producao — trocar para psycopg2 compilado

**Descoberta critica:** intel_collect.py (snake, 138KB) contem upgrades v1.5 de resiliencia (429 handling, chunked mode, TCU status) que NAO estao em intel-collect.py (kebab, 127KB) — a versao snake e a mais atual.

**Why:** Reversa re-analysis pos e9729e1 revelou 3 debitos nao cobertos por EPIC-TD-001/002 existentes. TD-001 estava completo (22 stories), entao criou-se EPIC-TD-003 com TD-8.1.

**How to apply:** Ao implementar TD-8.1, NUNCA deletar os 4 pares divergentes sem revisao humana. Prestar atencao especial ao intel_collect.py que e a versao mais atual.

---
name: story-COVERAGE-3.2-qa-gate
description: CONCERNS verdict for COVERAGE-3.2 (Portal Transparencia Individual Scraping)
metadata:
  type: project
---

# Story COVERAGE-3.2 QA Gate

**Story:** COVERAGE-3.2 | **Status:** InReview -> Done | **Verdict:** CONCERNS

**Why:** Functional implementation is solid (AC1-AC8 PASS, 29/29 tests, clean ruff), but AC9 partially unmet — template `sc_gov_portal` not registered in config, municipalities use `template: custom` instead. Two minor documentation/code integration issues.

**Issues:**
- MNT-001 (MEDIUM): Template `sc_gov_portal` ausente em `config/transparencia_config.yaml` — AC9 parcialmente nao atendido.
- MNT-002 (LOW): `monitor.py` nao atualizado com `--source transparencia_residual` conforme consta na File List.
- TST-001 (LOW): Contagem de testes desatualizada no DoD (122 vs 29 do modulo, 742+ total suite).

**How to apply:** Para futuras stories de scraping: verificar se todos os templates mencionados nas ACs estao realmente registrados nos arquivos de configuracao. Contagens de testes no DoD devem refletir o estado atual.

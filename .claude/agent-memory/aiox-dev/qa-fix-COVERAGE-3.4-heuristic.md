---
name: qa-fix-coverage-3.4-heuristic
description: NATUREZA_CAUSA_HEURISTIC expanded from 10 to 23 types in validate_coverage.py, reducing nao_investigado from 87.8% to 31.9%
metadata:
  type: feedback
---

**Rule:** When extending NATUREZA_CAUSA_HEURISTIC in validate_coverage.py, always query the database for exact natureza_juridica strings used in sc_public_entities to ensure exact string matching. Use `.get()` with "nao_investigado" fallback to handle any unseen types safely.

**Why:** The original heuristic covered only 10 of 29 types (34%), leaving 87.8% of uncovered entities as "nao_investigado". The QA flagged this as a medium-severity concern (REQ-001). The fix expanded coverage to 23 types (79%).

**How to apply:** When updating the heuristic, (1) query `SELECT DISTINCT natureza_juridica FROM sc_public_entities` for exact names, (2) group by legal regime (Lei 14.133 vs 13.303, judiciary vs executive, autonomous vs fund), (3) run `ruff check --fix` after changes, (4) regenerate CSV/report and verify distribution improved.

**Key mappings added:**
- Sociedade de Economia Mista, Empresa Publica -> sem_obrigacao_legal_14133 (Lei 13.303)
- Orgao Legislativo Municipal -> dom_sc_sem_api_key (publicam no DOM-SC)
- Fundacoes de Direito Publico, Autarquias, Orgaos Estaduais/Federais -> sem_dados_publicos
- Consorcio Publico de Direito Publico -> sem_dados_publicos

**Result:** nao_investigado: 87.8% (1110/1264) -> 31.9% (401/1258). Residual 401 sao orgaos do Poder Executivo Municipal (390) + municipios (11) — principais alvos do PNCP que requerem investigacao individual.

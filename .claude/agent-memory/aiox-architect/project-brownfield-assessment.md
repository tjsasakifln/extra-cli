---
name: brownfield-assessment-scope
description: Extra Consultoria — Brownfield Discovery Fase 8, 38 debitos tecnicos (4 CRITICAL, 9 HIGH, 18 MEDIUM, 7 LOW)
metadata:
  type: project
---

Projeto Extra Consultoria (CLI crawling de licitacoes, 64K linhas Python + SQL, 4.1 GB PostgreSQL em Hetzner VPS).

Brownfield Discovery completo (10 fases):
- Fase 1: system-architecture.md por @architect
- Fase 2: SCHEMA.md + DB-AUDIT.md por @data-engineer
- Fase 4: technical-debt-DRAFT.md (30 debitos) por @architect
- Fase 5: db-specialist-review.md por @data-engineer (+3 debitos, severidades ajustadas)
- Fase 7: qa-review.md por @qa (5 gaps identificados, NEEDS WORK 7.5/10)
- Fase 8: technical-debt-assessment.md (FINAL, 38 debitos) por @architect

Decisoes chave:
- SQL injection risk: classificado como LOW (DB-AUDIT confirmado pelo @data-engineer apos analise codigo fonte)
- ORM anti-pattern: reclassificado como INFORMATIVO (valido para single-user sem ORM)
- TD-DB-05 (senha hardcoded): HIGH por ser arbitro entre DB review (HIGH) e QA (MEDIUM) — senha em git history de VPS remota
- TD-DB-10: MEDIUM (arbitro aceita argumento QA sobre crawlers nao resumeveis)

Esforco total estimado: 140-170h | Custo R$ 21.000-25.500 (R$150/h)

**Why:** Resultado consolidado de 3 especialistas (@architect, @data-engineer, @qa) em assessment brownfield.
**How to apply:** Usar como baseline para criacao de epic + stories (Fase 9-10) e priorizacao de resolucao.

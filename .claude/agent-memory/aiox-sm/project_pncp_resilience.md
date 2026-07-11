---
name: project-pncp-resilience-td32
description: PNCP API resilience story TD-3.2 created to fix 7 pipeline problems from LCM execution failure
metadata:
  type: project
---

Story TD-3.2 (PNCP Resilience) created on 2026-07-11 after intel pipeline failed for LCM CONSTRUCOES LTDA (CNPJ 01.721.078/0001-68). The execution had: 28 PNCP errors (429), 15 pages fetched, 0 opportunities found, SICAF as SCRIPT_NOT_FOUND, sancoes UNAVAILABLE (no API key), TCU with empty certificates, keyword gap for "desassoreamento" in engineering sector.

Story covers 7 problems across 4 phases (A-D): rate-limit resilience, missing scripts/config, pipeline dependencies, and keyword gaps. 16h estimate, 9 tasks.

**Why:** LCM execution was a production failure -- pipeline completed but returned no value. Fixing these issues is critical for client-facing reliability.

**How to apply:** When referencing pipeline performance metrics, cross-reference against TD-3.2's DoD criteria. The story file is at `docs/stories/td-3.2-pncp-resilience.md`.

Related: [[user-pm-context]]

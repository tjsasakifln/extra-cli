---
name: story-coverage-2.1-pulada
description: "COVERAGE-2.1 (MiDES BigQuery) PULADA — BigQuery account indisponivel. Prioridade redirecionada para SC Compras + DOE-SC."
metadata:
  type: project
---

# Story COVERAGE-2.1 PULADA

**Story:** COVERAGE-2.1 — MiDES BigQuery Integration
**Epic:** EPIC-COVERAGE-100PCT
**Status:** PULADA (skipped)
**Date pulada:** 2026-07-11
**Executor:** @dev (Dex)

**Why:** BigQuery account nao disponivel. `GOOGLE_APPLICATION_CREDENTIALS` nao definido, `google-cloud-bigquery` SDK nao instalado, nenhuma service account configurada. O `gotchas.json` ja advertia este bloqueio.

**How to apply:** O unico AC executado foi AC9 (fallback). A story foi marcada como PULADA com justificativa completa. Se uma conta GCP/BigQuery for criada no futuro, esta story pode ser reativada — mas o potencial de cobertura (+200-276 entes) deve ser reavaliado, pois pode haver sobreposicao com dados ja coletados por outras fontes (CIGA CKAN, PNCP v3 expansion).

**Redirect:** Prioridade redirecionada para COVERAGE-2.2 (SC Compras) e COVERAGE-2.3 (DOE-SC), que nao requerem autenticacao externa.

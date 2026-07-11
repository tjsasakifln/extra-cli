---
name: state-level-entities
description: State-level entities (municipio=SANTA CATARINA) have non-7-digit IBGE codes that should be stored as NULL since no valid municipality code exists
metadata:
  type: reference
---

The spreadsheet `Extra - alvos de licitacao. R-0.xlsx` has ~513 state-level entities with municipio="SANTA CATARINA" and IBGE code "42" (the 2-digit SC state code). These are not valid 7-digit municipality IBGE codes.

**Rule:** IBGE codes shorter than 7 digits are invalid for municipality-constrained matching and should be stored as NULL in the database. The consuming system (name-matching) should skip IBGE-constrained matching for these records.

**Impact:** 513/2085 entities (~24.6%) have `codigo_ibge IS NULL` and will not participate in municipality-scoped matching. Documented in story risks as expected behavior.

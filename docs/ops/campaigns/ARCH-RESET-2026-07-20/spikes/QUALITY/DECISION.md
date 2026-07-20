# Spike Quality — Decision

| Field | Value |
|-------|--------|
| Result | **ADOPT_PYTHON_SQL_NATIVE** |
| Reject now | Soda production dual-path; dbt tests dual-path |
| Optional later | dbt tests **only if** PR E adopts dbt snapshots |
| New production deps | **None** |
| ADR | ADR-025 |

## Claims

**Allowed:** one quality contract registry of critical check IDs.  
**Forbidden:** 95% coverage achieved; LOCAL_READY; Soda/dbt adopted.

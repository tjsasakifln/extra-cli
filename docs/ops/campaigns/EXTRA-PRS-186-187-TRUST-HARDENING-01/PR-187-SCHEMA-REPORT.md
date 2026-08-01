# PR #187 Schema Report

## schema.json
- Draft: JSON Schema 2020-12
- `$id`: `https://extra-cli.local/schemas/pseo-public-export.json`
- Root `additionalProperties: false`
- `$defs`: Archetype, Market, Agency, Price, Competition, Opportunity, ProblemService, ICPMethodology
- Nested public models (B2): ValueBand, PrivacyMetadata, Modality, StatusBreakdown, Freshness,
  OfficialReference, ClaimEvidence, DocumentSignal, BudgetSignal, ClassifierMetadata,
  InternalSignatureAggregates, MethodologyMetadata
- All object nodes force `additionalProperties: false` (walk test rejects free/`{}` objects)
- **Zero `Any` in public model field annotations**

## export-descriptor.json
- Human/tool descriptor (former pseudo-schema content)
- Not a JSON Schema validator target

## Validation behavior
- Pydantic models validate payloads before write (`extra=forbid` at every nesting level)
- Unexpected fields → fail closed (no silent strip at validation layer)
- HTTPS-only URLs; official domain allowlist for OfficialReference; dangerous schemes rejected
- Finite numbers; CNPJ8; UF enum (27); slug regex; ISO dates

## Fixture evidence
- Export with `--validate` produced valid `schema.json` and checksummed files
- `dataset_hash` recomputed from body files matches manifest
- Default snapshot remains **CANDIDATE** / `indexable=false` (not MERGE_READY)

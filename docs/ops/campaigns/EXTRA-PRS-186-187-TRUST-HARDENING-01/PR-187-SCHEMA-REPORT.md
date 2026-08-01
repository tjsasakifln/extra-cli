# PR #187 Schema Report

## schema.json
- Draft: JSON Schema 2020-12
- `$id`: `https://extra-cli.local/schemas/pseo-public-export.json`
- Root `additionalProperties: false`
- `$defs`: Archetype, Market, Agency, Price, Competition, Opportunity, ProblemService, ICPMethodology
- Nested object schemas also set `additionalProperties: false` where type=object

## export-descriptor.json
- Human/tool descriptor (former pseudo-schema content)
- Not a JSON Schema validator target

## Validation behavior
- Pydantic models validate payloads before write
- Unexpected fields → fail closed (no silent strip at validation layer)
- Forbidden commercial keys are not present on models; denylist still scanned by `sanitize`/`validation`

## Fixture evidence
- Export with `--validate` produced valid `schema.json` and checksummed files
- `dataset_hash` recomputed from body files matches manifest

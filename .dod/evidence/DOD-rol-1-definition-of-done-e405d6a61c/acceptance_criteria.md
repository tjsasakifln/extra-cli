# O golden path importa ou valida a planilha-alvo

## Given / When / Then (strong)

Given the repo root contains the canonical spreadsheet
When `python3 -m scripts.golden_path --validate-spreadsheet-only` runs
Then:
1. A single canonical file is selected by explicit rule (exact basename preferred)
2. `.backup` / `.copy` / temp are never chosen silently
3. Selected path is recorded
4. SHA-256 of the file is recorded
5. Sheet `Entes Públicos SC` and required header markers are validated
6. `physical_rows` and `canonical_entities` are separate metrics (2085 vs 1093)
7. Universe is loaded via `scripts.lib.universe.load_canonical_universe`
8. Canonical included set size is exactly 1093
9. Ordered `canonical_ids_sha256` matches `0b3f894d87ba71f2e0fa96887cb3075033488de1af1e6e55f97ccda0701fb396`
10–13. Missing / backup-only / ambiguous candidates fail closed
14. Step `validate_target_spreadsheet` appears in the golden path ledger
15. Canonical CLI command exits 0 on valid scenario
16. Adversarial unit tests cover invalid scenarios
17. Proof is not only an isolated function call (CLI + ledger)

## Evidence
- PR #75 merged @ ae5302a
- CI run 29831727568 SUCCESS (full suite)
- tests/test_golden_path_canonical.py (strong suite)
- adversarial QA: PASS_FOR_MERGE (CONTINUE-02)

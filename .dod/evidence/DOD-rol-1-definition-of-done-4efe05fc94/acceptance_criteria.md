# O golden path calcula cobertura

Given clean DB + canonical planilha
When --execute-coverage-only runs
Then denominator == 1093 from load_canonical_universe
And numerator and coverage_pct are recorded
And proof is not public table count

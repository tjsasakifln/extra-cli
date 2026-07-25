## Summary

<!-- What changes and why (1–3 sentences). -->

## Scope

- [ ] Single capability (not migrations + CI + runtime + commercial pack together)
- [ ] Ready for review (not draft) only if ≤ 60 files and ≤ 10k textual lines added
- [ ] No PDF/XLSX/bulk CSV/JSON dumps/logs under `artifacts/` or `output/`

## Exact HEAD under test

- **HEAD SHA:** `<!-- paste full tip SHA after push -->`
- **Base:** `main` @ `<!-- origin/main SHA at open/update -->`

## Validation

- [ ] `python -m scripts.ops.check_generated_artifacts_policy --base origin/main`
- [ ] `python -m scripts.ops.check_pr_reviewability --base origin/main` (add `--draft` if draft)
- [ ] Canonical CI green on **this** HEAD (not a previous SHA)
- [ ] Migrations (if any): fresh + upgrade paths exercised

## Risk / privacy

- [ ] No production / VPS / soak touch
- [ ] No private client documents or secrets

## Human gates (if any)

- [ ] N/A
- [ ] Explicit human decision required: <!-- who / what -->

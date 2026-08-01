# PR #186 Visual QA

## Method
Playwright `e2e/visual-matrix.spec.ts` + dedicated page `/__visual_matrix`.

Determinism: fixed clock, reduced motion, fixture data, stable labels.

## Captures (test-results/, local CI artifacts)
- Home light / dark
- Home viewports 1440, 1280, 1024, 768, 390
- Command palette
- Component matrix light/dark (all StatusBadge, buttons, inputs, empty/loading/error/success, table, card, dialog)
- Review queue
- FIXTURE workflow
- REAL blocked preflight
- Error state

## Axe
Runs on home (both themes), palette open, component matrix (both themes + open dialog), review queue, fixture workflow.

## Latest run
**14 passed** (expanded matrix) after palette a11y fixes (listbox label, option-on-button, input name).

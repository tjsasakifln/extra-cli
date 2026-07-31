# VISUAL-QA

## Policy

Large PNG screenshots are not committed (generated-artifacts policy). Proof is Playwright on real `./bin/command-center` + SPA dist build.

## Covered surfaces (e2e)

| Surface | Evidence |
|---------|----------|
| Home outcome-first | workbench + smoke |
| Iniciar trabalho / preflight | workbench |
| Job result + PDF iframe | task1/2/4 hard asserts |
| XLSX Abas + table | task1/2 |
| Review rationale | task3 + reject blocked |
| Compare | task5 |
| Mobile 390×844 | workbench mobile |
| a11y | e2e/a11y.spec.ts axe |

## Local reproduce

```bash
cd apps/command-center && CC_OPEN_BROWSER=0 npm run test:e2e
```

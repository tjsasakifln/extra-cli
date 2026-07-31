# ACCESSIBILITY-REPORT

## Automated axe

```bash
cd apps/command-center && CC_OPEN_BROWSER=0 npx playwright test e2e/a11y.spec.ts
```

Routes: `/`, `/work/start`, `/review`, `/results`, `/compare`, `/onboarding`, `/extra`  
**Result:** no critical or serious violations (full suite 30/30 including axe).

## Fixes applied this wave

- Brand logo: `role="img"` + `aria-label` (no prohibited aria on bare span)
- Status badge foreground colors darkened for ≥4.5:1 on soft backgrounds
- Token muted text darkened for AA on light surfaces

## Manual

- Keyboard nav covered in smoke + workbench e2e
- Mobile 390×844 covered in workbench e2e

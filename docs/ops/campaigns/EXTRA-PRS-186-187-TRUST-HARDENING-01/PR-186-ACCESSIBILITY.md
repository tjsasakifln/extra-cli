# PR #186 Accessibility

## Axe
- `@axe-core/playwright` on routes: `/`, `/work/start`, `/review`, `/results`, `/compare`, `/onboarding`, `/extra`
- Tags: wcag2a, wcag2aa
- Filter: critical + serious must be empty
- **Result (A16 re-run):** all 7 routes PASS

## Fixes relevant to a11y in this campaign
- Semantic status tokens with non-color indicator (dot + label)
- Unknown status explicit text
- Skeleton `role="status"` + `aria-label`
- NotFound page with heading
- Error boundary with recoverable action
- Command palette `aria-modal`, labelled dialog, empty state
- Specific aria-labels on home CTAs
- Mobile nav scrim + Escape

## Contrast policy
Status tokens define bg/fg/border for light and dark themes targeting ≥4.5:1 body text on soft backgrounds (see `tokens.css`).

# UX Heuristic Review (Nielsen-inspired)

Date: 2026-07-30 · Campaign: EXTRA-LOCAL-COMMAND-CENTER-01

| # | Heuristic | Finding | Action |
|---|-----------|---------|--------|
| 1 | Visibility of system status | Home shows attention + job states with human copy | StatusBadge + HumanStatusExplanation |
| 2 | Match real world | Labels in PT-BR; CLI jargon translated | status maps |
| 3 | User control | Cancel job, confirmation dialogs, DEFER/REJECT | implemented |
| 4 | Consistency | Shared tokens/components | tokens.css + components |
| 5 | Error prevention | CSRF, allowlist, phrase confirm | API tests |
| 6 | Recognition vs recall | Nav IA + palette + search | AppShell |
| 7 | Flexibility | Advanced params collapsed | ParameterForm |
| 8 | Minimalism | Attention-first home, limited KPIs | HomePage |
| 9 | Error recovery | ErrorState + next_action on jobs | Job detail |
| 10 | Help | Onboarding + capability docs links | OnboardingPage |

Issues found and fixed during build:

- Initial risk of template-like multi-card KPI soup → limited metrics with denominators.
- ACCEPT as green primary → neutral buttons + phrase confirm.
- Missing empty states → EmptyState component on jobs/search/artifacts.

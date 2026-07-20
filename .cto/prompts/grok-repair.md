# Grok Repair Prompt Template

Repair the previous execution. Do NOT expand scope.

## Failures (concrete)

{{failed_criteria}}

## Repair instructions

{{repair_instructions}}

## Constraints remain

- allowed_paths: {{allowed_paths}}
- forbidden_paths: {{forbidden_paths}}
- forbidden_actions: {{forbidden_actions}}
- authorized test_ids only: {{test_ids}}
- max_repair_attempts remaining: {{remaining_repairs}}

Fix only the listed failures. Re-run only authorized test_ids (never free shell).
No push/merge/deploy.

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
- max_repair_attempts remaining: {{remaining_repairs}}

Fix only the listed failures. Re-run relevant tests. No push/merge/deploy.

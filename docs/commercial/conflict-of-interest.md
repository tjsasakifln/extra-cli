# Conflito de interesses — vertical órgãos públicos

Config: `config/commercial/conflict_of_interest.yaml`

## Estados

| Estado | Significado |
|--------|-------------|
| CONFLICT_CHECK_PENDING | Default; sem match automático |
| CONFLICT_REVIEW_REQUIRED | Marcadores exigem revisão |
| CONFLICT_BLOCKED | Bloqueio |
| CONFLICT_CLEARED_BY_HUMAN_REVIEW | Clearance documentado (reviewer + note) |

## Princípios

- Ausência de dados **não** prova ausência de conflito
- Nenhum dado não público do trabalho estatal do operador pode entrar no Extra-CLI
- Outreach exige `CONFLICT_CLEARED_BY_HUMAN_REVIEW`

## Manutenção

Operador mantém `blocked_agency_ids`, `blocked_cnpj14`, `blocked_name_markers` e `review_required_name_markers` no YAML.

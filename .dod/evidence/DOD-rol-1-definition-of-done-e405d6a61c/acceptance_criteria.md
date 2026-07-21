# O golden path importa ou valida a planilha-alvo

Given Extra alvos xlsx in repo
When validate_target_spreadsheet runs
Then path+sha256+entity_rows>=100 recorded and fail-closed if missing

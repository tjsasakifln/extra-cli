# O hash da planilha é registrado.

Given golden_path validates the planilha-alvo
When ledger is saved
Then meta.spreadsheet_sha256 is present and non-empty

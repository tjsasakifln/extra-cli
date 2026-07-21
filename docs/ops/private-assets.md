# Private assets (public repository)

This repository is **public**. Real commercial materials, client-branded spreadsheets,
intelligence packs, and credentials must **not** live in the git tree.

## Required local private spreadsheet

Canonical operational universe is derived from Tiago's private planilha (1.093 entities
within 200 km). Provide it **outside git**:

```bash
export EXTRA_TARGET_SPREADSHEET="/absolute/path/to/your-private-alvos.xlsx"
# or
python3 -m scripts.golden_path --spreadsheet /absolute/path/to/your-private-alvos.xlsx ...
```

Optional local filename (gitignored): `Extra - alvos de licitação. R-0.xlsx` in project root.

## Public sanitized seed

`config/target_entities_200km.csv` — public, no client branding. Use for documentation
and non-branded fixtures. Do not reintroduce branded `.xlsx` into git.

## Prohibited in public tree

- `proposta-*.pdf` and commercial proposals
- `data/intel/**` client/competitor packs
- Client briefings under `output/briefing*`
- Branded Extra alvos `.xlsx` / `.backup.xlsx`
- SQLite client DBs under `data/*.db`
- Weak password defaults (`smartlic_local`)

History is not rewritten; rotate any credentials that may have been exposed.

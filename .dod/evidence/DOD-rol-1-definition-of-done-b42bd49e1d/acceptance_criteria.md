# Acceptance — Existe um comando canônico de golden path

## Given/When/Then
- Given the repository on main
- When an operator runs `python3 -m scripts.golden_path --help` or `make golden-path`
- Then the command is discovered, documented in DEVELOPMENT.md/AGENTS.md, and exits 0 for --help
- And the entrypoint is versioned at `scripts/golden_path.py`

## Evidence
- --help exit 0
- Makefile targets golden-path / golden-path-quick
- docs/DEVELOPMENT.md canonical commands section

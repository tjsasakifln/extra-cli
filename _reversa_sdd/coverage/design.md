# Design — Coverage (atualizado 2026-07-17)

## Componentes
- `coverage_contract.py` — motor M1–M5
- `states.py` — máquina de estados + evidence
- `commercial_status.py` — classificação comercial
- `multi_source_coverage.py` — métricas de sessão multi-fonte
- CLIs: coverage_contract_cli, validate_coverage, session pipeline

## Fluxos
Ver `flowcharts/coverage.md`.

## Dependências
source_registry, lib.universe, crawl evidence, db coverage_evidence

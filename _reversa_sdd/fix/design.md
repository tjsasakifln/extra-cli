# Fix — Design Técnico (v1.0)

> Gerado pelo Writer em 2026-07-13 | doc_level: completo | Base: 249340d

## Interface

| Script | Propósito | Input | Output |
|--------|-----------|-------|--------|
| `rebuild_evidence_ledger.py` | Reconstruir coverage_evidence de runs históricos | PostgreSQL conn | Evidence ledger atualizado |
| `resolve_unresolved_entities.py` | Matching cascade em entidades não resolvidas | PostgreSQL conn | Entidades com match ou flag |
| Demais scripts (5) | Correções pontuais de dados | Variável | Variável |

## Dependências

- `scripts/lib/` — universe, geocode, name normalizer
- `scripts/matching/` — entity matching cascade
- PostgreSQL — `coverage_evidence`, `sc_public_entities`
- `data/raw/` — payloads brutos de crawls históricos

## Decisões de Design

| Decisão | Evidência | Confiança |
|---------|-----------|-----------|
| Scripts táticos, execução manual sob demanda | Localização em `scripts/fix/` | 🟡 |
| Sem testes automatizados para maioria dos scripts | Ausência de `tests/test_fix_*.py` | 🟡 |

## Riscos e Lacunas

- 🔴 165K LOC em 7 arquivos — densidade muito alta. Cada script pode ter milhares de linhas.
- 🔴 Sem cobertura de testes. Scripts de reparo que alteram dados sem teste são arriscados.
- 🟡 Propósito exato de cada script inferido do nome do arquivo, não do conteúdo.

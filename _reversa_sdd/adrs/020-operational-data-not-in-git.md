# ADR-020 — Operational Data Not in Git (retroativo Reversa)

| Campo | Valor |
|-------|-------|
| **Status** | Accepted |
| **Data** | 2026-07-17 |
| **Fonte** | `docs/architecture/adr/ADR-020-operational-data-not-in-git.md` |
| **Confiança** | 🟢 CONFIRMADO |

## Contexto
Repo poluído com JSONL/raw/checkpoints; risco PII e PRs inviáveis.

## Decisão
Classes A–E: só código/specs/evidência carimbada mínima no git; raw em `output/`/`data/` gitignored.

## Consequências
CI usa fixtures mínimas; scripts de seal/stamp separados da coleta.

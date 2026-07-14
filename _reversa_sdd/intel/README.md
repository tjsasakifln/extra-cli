# Intel Pipeline (Legado) — Migrado

> Em 2026-07-13, o conteudo deste modulo foi incorporado a `root_scripts/`.
> Os scripts do pipeline legado (`intel_pipeline.py`, `intel-collect.py`, etc.)
> residem em `scripts/` (top-level) e sao documentados em `_reversa_sdd/root_scripts/`.
>
> Esta pasta e mantida como registro historico. Para novos desenvolvimentos,
> consulte `_reversa_sdd/opportunity_intel/` (substituto funcional).

## Arquivos mantidos aqui

| Arquivo | Status | Descricao |
|---------|--------|-----------|
| `requirements.md` | 🔒 Historico | Requisitos originais do pipeline Intel (7 estagios, 5 quality gates) |
| `design.md` | 🔒 Historico | Design original do pipeline |
| `tasks.md` | 🔒 Historico | Tarefas originais |

## O que mudou

- Os scripts `intel_pipeline.py`, `intel-collect.py`, `intel-enrich.py`, `intel-validate.py`, `intel-analyze.py`, `intel-extract-docs.py`, `intel-excel.py`, `intel-report.py` sempre estiveram em `scripts/` (top-level) — nunca foram um submodulo Python separado.
- A documentacao original em `intel/` foi unificada em `root_scripts/` para refletir a localizacao real dos arquivos.
- O substituto funcional e `opportunity_intel/` (radar de oportunidades QW-01), que substitui o pipeline Intel legado.

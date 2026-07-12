---
name: story-COVERAGE-1.9-backfill
description: "Story COVERAGE-1.9: SC Dados Abertos municipio backfill — script, migration, 27 tests, self-critique PASSED. Status: InReview."
metadata:
  type: project
---

Story COVERAGE-1.9 implementada em YOLO mode: backfill script para 75.523 contratos sem municipio. 3 niveis de inferencia (sc_public_entities > Brasil API > cache). Migration 021 adiciona colunas + audit log.

**Why:** Entity matching requer municipio preenchido. 75.523 contratos SC Dados Abertos tinham municipio=NULL.

**How to apply:** Para executar contra o banco: `python scripts/fix/sc_dados_abertos_backfill.py --dry-run` (teste) depois `--commit` (real). `--report-only` gera relatorio atual.

# Fix — Requirements (v1.0)

> Gerado pelo Writer em 2026-07-13 | doc_level: completo | Base: 249340d

## Visão Geral

Scripts de reparo, scrape residual e reconstrução de dados. Módulo com maior LOC (~165K) — scripts de correção únicos ou semi-automatizados para resolver problemas de dados históricos.

## Responsabilidades

- Rebuild de evidence ledger (`rebuild_evidence_ledger.py`)
- Resolução de entidades não resolvidas (`resolve_unresolved_entities.py`)
- Scrape residual e correção de dados de crawls passados
- Repair scripts para inconsistências de banco

## Requisitos Funcionais

| ID | Requisito | Prioridade | Critério de Aceite |
|----|-----------|-----------|-------------------|
| RF-FX01 | Rebuild evidence ledger a partir de runs históricos | Must | Ledger reconstruído sem perda |
| RF-FX02 | Resolver entidades não resolvidas com matching cascade | Must | Entidades resolvidas ou flagadas |
| RF-FX03 | Scripts de reparo idempotentes (seguros para reexecução) | Should | Dupla execução não causa dano |

## Regras de Negócio

- 🟡 Scripts de reparo são táticos, não operacionais. Executados sob demanda, não em cron.
- 🟡 Idempotência é esperada mas não garantida em todos os scripts.

🔴 **LACUNA:** 7 arquivos, ~165K LOC. Análise superficial — muitos scripts não foram lidos integralmente.

## Tarefas

| # | Tarefa | Confiança |
|---|--------|-----------|
| T-FX01 | Documentar cada script de reparo com propósito e pré-condições | 🟡 |
| T-FX02 | Garantir idempotência em todos os scripts | 🟡 |
| T-FX03 | Adicionar testes para scripts críticos (rebuild, resolve) | 🔴 |

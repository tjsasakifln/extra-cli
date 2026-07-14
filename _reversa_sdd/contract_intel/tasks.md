# Contract Intelligence — Tasks

> Gerado pelo Writer em 2026-07-13 | doc_level: completo | Base: 249340d

| # | Tarefa | Fonte | Confiança |
|---|--------|-------|-----------|
| T-CI01 | Implementar `load_target_universe()` com Haversine, flags duplicata/sem-coord | `target_universe.py:1-200` | 🟢 |
| T-CI02 | Implementar CLI: historical, suppliers, expiring, manifesto | `cli.py:1-600` | 🟢 |
| T-CI03 | Implementar queries canônicas PostgreSQL (16 colunas) | `cli.py:46-200` | 🟢 |
| T-CI04 | Implementar ranking fornecedores: count, value, ticket, órgãos, HHI | `cli.py` | 🟢 |
| T-CI05 | Implementar readiness manifest por capability | `cli.py` | 🟢 |
| T-CI06 | 🔴 Corrigir checkpoint de backfill: janela parcial ≠ concluída | `plano-mestre §12` | 🔴 |
| T-CI07 | 🔴 Substituir `DO NOTHING` por upsert com atualização | `plano-mestre §12` | 🔴 |
| T-CI08 | 🔴 Reescrever métricas contra `v_contracts_canonical` | `plano-mestre §13` | 🔴 |
| T-CI09 | 🔴 Unificar carregador de universo (remover duplicata em consulting_readiness) | `plano-mestre §7` | 🔴 |
| T-CI10 | Criar `v_contracts_canonical`, `v_suppliers_canonical` | `plano-mestre §6` | 🔴 |

**Estimativa:** 8-12 dias (10 tarefas, 5 blockers)

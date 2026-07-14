# Opportunity Intelligence — Tasks

> Gerado pelo Writer em 2026-07-13 | doc_level: completo | Base: 249340d

## Tarefas de Reimplementação

| # | Tarefa | Fonte | Confiança |
|---|--------|-------|-----------|
| T-OI01 | Implementar CLI com 8 comandos (argparse + Rich tables) | `cli.py:1-700` | 🟢 |
| T-OI02 | Implementar `score_opportunity()` com scoring duplo independente | `scoring.py:28-120` | 🟢 |
| T-OI03 | Implementar `calculate_canonical_status()` com 3 níveis (source→temporal→heuristic) | `status.py:1-400` | 🟢 |
| T-OI04 | Implementar ranking determinístico: 6 HARD_BLOCKS + 9 POSITIVE + 9 NEGATIVE | `ranking.py:1-350` | 🟢 |
| T-OI05 | Implementar QW-01 Radar pipeline com manifest, readiness gate, exit codes | `radar.py:1-800` | 🟢 |
| T-OI06 | Implementar PNCP audit: 19 modalidades, paginação completa | `pncp_audit.py:1-500` | 🟢 |
| T-OI07 | Implementar deduplicação cross-source 3 níveis | `dedup.py:1-200` | 🟢 |
| T-OI08 | Implementar crawler base com circuit breaker + retry | `crawler_base.py:1-600` | 🟢 |
| T-OI09 | Implementar transformador raw → CanonicalOpportunity | `transformer.py:1-450` | 🟢 |
| T-OI10 | Implementar ClientProfile com weights YAML configuráveis | `profile.py:1-130` | 🟢 |
| T-OI11 | Implementar schema validation: extensions, migrations, fingerprint | `schema.py:1-130` | 🟢 |
| T-OI12 | Criar models SQLAlchemy para opportunity_intel | `models.py:1-200` | 🟢 |
| T-OI13 | 🔴 Implementar snapshot reconciliation (P0-04): inativar ausentes, NUNCA em run parcial | `plano-mestre §8` | 🔴 |
| T-OI14 | 🔴 Implementar URL oficial obrigatória para PRIORITARIA | `plano-mestre §2.2` | 🔴 |
| T-OI15 | 🔴 Reescrever métricas competitive intel contra `v_contracts_canonical` | `plano-mestre §13` | 🔴 |
| T-OI16 | 🔴 Provar fontes complementares (7) ponta a ponta com fixtures | `plano-mestre §10` | 🔴 |
| T-OI17 | Completar perfil EXTRA: modalidades, cidades, faixa valor, termos negativos | `plano-mestre §11` | 🔴 |
| T-OI18 | Implementar manifest de cobertura com métricas desagregadas | `manifest.py:1-300` | 🟢 |
| T-OI19 | Implementar backfill de oportunidades históricas | `backfill.py:1-350` | 🟡 |

**Estimativa:** 12-16 dias (19 tarefas, 5 delas 🔴 blockers)
**Pré-requisitos:** Story 1.2 (schema canônico), Story 1.3 (universo autoridade), Story 1.4 (reconciliação snapshot)

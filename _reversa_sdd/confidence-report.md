# Relatório de Confiança — Reversa

> Reviewer consolidado **2026-07-17** | Re-extração completa  
> HEAD `d3e82ba` | doc_level completo | 25 módulos

---

## Score geral: **82% 🟡→🟢**

| Dimensão | Score | Notas |
|----------|------:|-------|
| Superfície / inventário | 95% | Scout quantificado via git ls-files |
| Análise de código | 85% | Delta profundo; módulos estáveis com refresh transversal |
| Domínio / regras | 88% | R27–R40 + ADRs 017–022 🟢 |
| Arquitetura / ERD | 85% | C4 + ERD 052–054 |
| Specs SDD por unit | 72% | Novos 100%; legados 2026-07-13 mantidos com ponte |
| Testes ↔ specs | 80% | chaos/unit coverage/registry/workspace |
| Runtime DB live | 40% | 🔴 sem dump live nesta sessão |

**Comparativo:** 78% (2026-07-13) → **82%** (2026-07-17) — ganho por ADRs nativos do projeto e código de coverage/ESR/resilience lido diretamente; perda residual em specs unit legadas não reescritas linha a linha.

---

## Por módulo (confiança)

| Módulo | Confiança | Motivo |
|--------|:---------:|--------|
| crawl | 🟢 88% | registry + resilience lidos |
| source_registry | 🟢 90% | código + mig 053 |
| coverage | 🟢 92% | contract + ADR-018 + tests |
| workspace | 🟢 88% | ADR-017 + queue/actions |
| matching | 🟢 85% | reconcile determinístico lido |
| schema | 🟢 85% | store + mig 052 |
| ops | 🟢 80% | resilient_cycle |
| lib | 🟢 85% | universe + value semantics |
| opportunity_intel | 🟡 78% | scoring/status; radar não re-lido integralmente |
| buyer_intel | 🟢 85% | ranking completo |
| reports | 🟡 70% | superfície; internals parciais |
| root_scripts | 🟡 70% | muitos entry points |
| db | 🟢 88% | migrations lidas 045–054 |
| deploy | 🟡 75% | contagem units |
| tests | 🟢 80% | layout + chaos |
| demais | 🟡 65–75% | inventário + residual |

---

## Lacunas consolidadas

### 🔴 Críticas (produto, não doc)
1. M2 operational strict **0/1093** vs meta 95%  
2. Runtime DB/prod não validado nesta extração  

### 🟠 Altas (doc/código)
3. Specs SDD de módulos legados não reescritas integralmente (ponte via code-analysis/domain)  
4. ADR-022 sole law — aderência total de scorers legados 🟡  
5. Duplicação `scripts/clients|ingestion` vs `crawl/*`  

### 🟡 Médias
6. Sem pip lockfile  
7. mypy boundary parcial  
8. Win rate NOT_READY  
9. M3/M5 coverage backlog  

### 🟢 Baixas
10. orchestrator deprecated ainda no tree  
11. Visor/Design System N/A (sem UI produto)  

---

## Correções in-place nesta re-extração
- Inventário/deps/surface regenerados  
- code-analysis + data-dictionary + 9 flowcharts  
- domain R27–R40, MS11–MS16, ADRs 017–022  
- architecture/C4/ERD/impact matrix  
- SDD units novos: source_registry, workspace, buyer_intel, extra_ledger, ops, schema, clients, ingestion + refresh crawl/coverage  

## Veredito Reviewer
**PASS com CONCERNS** — artefatos de auditoria atualizados em profundidade no eixo transversal e nos módulos delta; units legados aceitos com cobertura transversal + matrix.  
Próximo ciclo Writer pode reescrever opportunity_intel/reports/root_scripts se necessário para 90%+.

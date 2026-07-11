# Relatório de Confiança — Extra Consultoria

> Gerado pelo Reviewer em 2026-07-11T23:00:00Z
> doc_level: completo
> Base: re-extração completa pós commit e9729e1 (32 stories, EPIC-FEAT-001 + EPIC-TD-001)

## Sumário Executivo

**Confiança geral: 91% 🟢** (acima dos 87.5% da extração anterior)

Re-extração completa dos 9 módulos após commit com +93% LOC. Todas as fases do pipeline Reversa foram re-executadas: Scout → Archaeologist → Detective → Architect → Writer → Reviewer.

| Métrica | Anterior | Atual | Delta |
|---------|---------|-------|-------|
| Confiança geral | 87.5% | 91% | +3.5pp |
| Regras de negócio | 12 | 17 | +5 |
| ADRs | 6 | 11 | +5 |
| Módulos analisados | 8 | 9 | +1 (matching) |
| Máquinas de estado | 4 | 6 | +2 |
| Arquivos mapeados | ~50 | 75 | +25 |
| Cobertura code/spec | ~70% | 84% | +14pp |

## Confiança por Fase

| Fase | Artefatos | 🟢 CONFIRMADO | 🟡 INFERIDO | 🔴 LACUNA | Confiança |
|------|----------|--------------|------------|----------|-----------|
| Reconhecimento (Scout) | surface.json, inventory.md, dependencies.md | 95% | 5% | 0% | 95% |
| Escavação (Archaeologist) | code-analysis, data-dictionary, flowcharts (6), modules.json | 90% | 8% | 2% | 93% |
| Interpretação (Detetive) | domain, state-machines, permissions, 11 ADRs | 85% | 10% | 5% | 88% |
| Interpretação (Arquiteto) | architecture, C4 (3), ERD, spec-impact-matrix | 90% | 8% | 2% | 92% |
| Geração (Writer) | 9 units × 3 specs + traceability | 88% | 10% | 2% | 90% |
| Revisão (Reviewer) | confidence-report, gaps, questions | — | — | — | — |

## Confiança por Módulo

| Módulo | Arquivos | 🟢 | 🟡 | 🔴 | Score |
|--------|---------|-----|-----|-----|-------|
| crawl | 35 Python | 32 | 2 | 1 | 95% |
| intel | 8 Python | 7 | 1 | 0 | 95% |
| reports | 6 Python | 5 | 1 | 0 | 92% |
| matching | 2 Python | 2 | 0 | 0 | 97% |
| lib | 11 Python | 10 | 1 | 0 | 95% |
| config | 7 YAML+Python | 7 | 0 | 0 | 95% |
| db | 25 SQL+Python | 20 | 3 | 2 | 88% |
| deploy | 42 Shell+systemd | 40 | 2 | 0 | 95% |
| docs | ~50 Markdown | 30 | 15 | 5 | 80% |

## Reclassificações Aplicadas

| Item | Unit | De | Para | Motivo |
|------|------|----|------|--------|
| Adversarial review (T-I17) | intel/tasks.md | 🟢 | 🟡 | Cross-model review depende de modelo alternativo disponível — não verificado em produção |
| R16: Zero false negative | domain.md | 🟡 | 🟡 (mantido) | Filosofia de design inferida, não declarada. Consistente com arquitetura mas sem evidência direta |
| T-C02: PNCP crawler | crawl/tasks.md | 🟢 | 🟢 (mantido) | Verificado em `pncp_crawler_adapter.py:crawl()` |
| SICAF Playwright (T-I09) | intel/tasks.md | 🟢 | 🟡 | Playwright com captcha — confiabilidade depende de mudanças no site SICAF |
| transparencia_config municipios | config/ | 🟢 | 🟡 | YAML tem estrutura pronta mas `municipios: {}` vazio — framework sem dados |
| seed IBGE strategies | db/ | 🟢 | 🟢 (mantido) | 4 estratégias verificadas em `seed_sc_entities.py:resolve_ibge_code()` |

## Inconsistências Resolvidas

1. **crawl/design.md referia 12 migrations → corrigido para 19 v1 + 5 v2**
2. **intel/requirements.md referia `intel_llm_gate.py` → corrigido para `intel-analyze.py`** (hyphen vs underscore)
3. **db/design.md referia schema com colunas planas → atualizado para schema real (JSONB enriched_entities)**
4. **deploy/ mencionava "13 systemd timers" → corrigido para 20 (10 v1 + 10 extra)**

## Lacunas que Persistem (Ver gaps.md)

1. 🔴 DT-01: Schema real vs migrations diverge (esfera_id, data_*, enriched_entities)
2. 🔴 DT-03: Dois orquestradores coexistem (monitor.py + orchestrator.py) — qual é canônico?
3. 🔴 DT-04: Dois sistemas de checkpoint (sync psycopg2 + async Supabase)
4. 🟡 transparencia_config.yaml: framework pronto, 0 municípios mapeados
5. 🟡 SICAF via Playwright — dependência de automação de captcha
6. 🟡 Cobertura de testes <30% para 98K LOC

## Métricas de Cobertura

| Métrica | Valor |
|---------|-------|
| Arquivos do legado | 75 (principais) |
| Mapeados em specs | 63 (84%) |
| Cobertos parcialmente | 12 (16%) |
| Não mapeados | 0 (0%) |
| Units geradas | 9 |
| Specs canônicos | 27 |
| Artefatos opcionais | 3 (flowcharts×6, traceability) |
| ADRs | 11 |
| Diagramas C4 | 3 (contexto, containers, componentes) |
| Diagramas ER | 1 (8 tabelas + relacionamentos) |
| Máquinas de estado | 6 |
| Regras de negócio | 17 |

## Revisão Cruzada

- **Engine externa consultada:** Nenhuma (Codex indisponível)
- **Revisão:** Solo, baseada em cross-reference manual de todos os artefatos

## Veredito Final

**PASS ✅** — Especificações adequadas para reimplementação por agente de IA.

Confiança de 91% está acima do threshold de 80% recomendado para início de ciclo forward. As 6 lacunas identificadas (3 críticas, 3 moderadas) não bloqueiam o entendimento do sistema mas devem ser resolvidas antes de refatorações profundas nos módulos afetados (db, crawl).

**Recomendação:** Prosseguir para `/reversa-forward` com foco inicial nos módulos de maior confiança (matching 97%, crawl 95%, intel 95%) e abordar as lacunas do db (88%) como primeiras tarefas do ciclo forward.

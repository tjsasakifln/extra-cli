# Spec Impact Matrix — Extra Consultoria

> Gerado pelo Architect em 2026-07-11T15:00:00Z
> 🟢 CONFIRMADO — baseado em code-analysis.md, modules.json, domain.md

---

## Matriz de Impacto: Componente × Artefato

| Componente \ Artefato | inventory.md | dependencies.md | code-analysis.md | data-dictionary.md | domain.md | state-machines.md | permissions.md | ADRs | C4 Context | C4 Containers | C4 Components | ERD |
|------------------------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **monitor.py** | 🟢 | 🟢 | 🟢 | 🟢 | 🟢 | 🟢 | — | 001,002,003,004 | 🟢 | 🟢 | 🟢 | 🟢 |
| **pncp_crawler_adapter.py** | 🟢 | — | 🟢 | — | — | — | — | 003 | — | 🟢 | 🟢 | — |
| **dom_sc_crawler.py** | 🟢 | — | 🟢 | — | — | — | — | 003 | 🟢 | — | 🟢 | — |
| **pcp_crawler.py** | 🟢 | — | 🟢 | — | — | — | — | 003 | 🟢 | — | 🟢 | — |
| **tce_sc_crawler.py** | 🟢 | — | 🟢 | — | — | — | — | 003 | 🟢 | — | 🟢 | — |
| **transformer.py** | — | — | 🟢 | 🟢 | 🟢 | — | — | 004 | — | — | 🟢 | 🟢 |
| **enricher.py** | — | 🟢 | 🟢 | 🟢 | 🟢 | — | — | 001 | 🟢 | — | 🟢 | 🟢 |
| **name_normalizer.py** | — | — | 🟢 | — | 🟢 | — | — | 004 | — | — | 🟢 | — |
| **intel_pipeline.py** | 🟢 | 🟢 | 🟢 | — | 🟢 | 🟢 | — | 005 | 🟢 | 🟢 | 🟢 | — |
| **intel_llm_gate.py** | — | 🟢 | 🟢 | — | 🟢 | — | — | 005 | 🟢 | — | 🟢 | — |
| **intel_analyze.py** | — | 🟢 | 🟢 | — | 🟢 | — | — | 005 | 🟢 | — | 🟢 | — |
| **panorama.py** | 🟢 | — | 🟢 | — | — | — | — | — | — | — | 🟢 | — |
| **bid_simulator.py** | — | — | 🟢 | 🟢 | 🟢 | — | — | — | — | — | 🟢 | — |
| **victory_profile.py** | — | — | 🟢 | 🟢 | 🟢 | — | — | — | — | — | 🟢 | — |
| **intel_report.py** | — | 🟢 | 🟢 | — | — | — | — | 006 | — | — | 🟢 | — |
| **settings.py** | 🟢 | 🟢 | 🟢 | — | 🟢 | — | — | 001 | 🟢 | 🟢 | — | — |
| **sectors_config.yaml** | 🟢 | — | 🟢 | — | 🟢 | — | — | 005 | — | — | 🟢 | — |
| **db/migrations/001-012** | 🟢 | — | 🟢 | 🟢 | 🟢 | 🟢 | — | 001,004 | — | 🟢 | — | 🟢 |
| **systemd timers** | 🟢 | — | 🟢 | — | 🟢 | — | — | 002 | — | 🟢 | — | — |

**Legenda:** 🟢 = Impacta diretamente | 🟡 = Impacta indiretamente | — = Sem impacto

---

## Matriz de Impacto: Story × Componente

| Story (EPIC-001) | crawl | intel | reports | lib | config | db | deploy |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **001.1** Systemd timers | 🟢 | — | 🟢 | — | 🟢 | — | 🟢 |
| **001.2** TCE-SC crawler | 🟢 | — | — | — | — | — | 🟢 |
| **001.3** Entity matching | 🟢 | — | — | 🟢 | 🟢 | 🟢 | — |
| **001.4** Seed entities | — | — | — | — | 🟢 | 🟢 | — |
| **001.5** Coverage monitoring | 🟢 | — | 🟢 | — | 🟢 | 🟢 | — |
| **001.6** Transparência gap-fill | 🟢 | — | 🟢 | — | 🟢 | — | 🟢 |
| **001.7** Coverage report | 🟢 | — | 🟢 | — | — | 🟢 | 🟢 |

---

## Matriz de Impacto: Integração Externa × Componente

| Integração | monitor | pncp_adapter | dom_sc | pcp | compras_gov | tce_sc | transparencia | enricher | intel_llm | intel_analyze |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **PNCP API** | 🟢 | 🟢 | — | — | — | — | — | — | — | 🟢 |
| **DOM-SC** | 🟢 | — | 🟢 | — | — | — | — | — | — | — |
| **PCP v2** | 🟢 | — | — | 🟢 | — | — | — | — | — | — |
| **ComprasGov v3** | 🟢 | — | — | — | 🟢 | — | — | — | — | — |
| **TCE-SC ESFINGE** | 🟢 | — | — | — | — | 🟢 | — | — | — | — |
| **Portais Transparência** | 🟢 | — | — | — | — | — | 🟢 | — | — | — |
| **OpenAI API** | — | — | — | — | — | — | — | — | 🟢 | 🟢 |
| **BrasilAPI** | — | — | — | — | — | — | — | 🟢 | — | — |
| **IBGE API** | — | — | — | — | — | — | — | 🟢 | — | — |

---

## Hotspots de Mudança

Componentes com maior probabilidade de impacto em mudanças futuras:

| Rank | Componente | Razões |
|------|-----------|--------|
| 🔴 1 | **monitor.py** | Orquestrador central — qualquer nova fonte, regra de matching, ou métrica impacta aqui |
| 🔴 2 | **sectors_config.yaml** | 13 setores — adicionar/ajustar setores é a operação mais frequente |
| 🟡 3 | **intel_pipeline.py** | Pipeline central — mudanças em gates ou stages afetam o fluxo inteiro |
| 🟡 4 | **pncp_crawler_adapter.py** | PNCP é a fonte primária — mudanças na API PNCP impactam diretamente |
| 🟢 5 | **db/migrations/** | Schema changes requerem novas migrations — cuidado com breaking changes |

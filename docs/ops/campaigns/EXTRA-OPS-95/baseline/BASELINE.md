# EXTRA-OPS-95-FOUNDATION — Baseline canônico (humano)

**Congelado em:** 2026-07-19T02:30:55Z  
**Artefato máquina:** `foundation-baseline.json`  
**Branch:** `campaign/extra-ops-95-20260719`  
**HEAD trabalho:** `eef1413e64480c369f82d756b10988dc1474e236`  
**Main na recuperação:** `dbc5adb2ab62898cd3fd005c83c90dcef36c1cde`

## 1. Recuperação forense (resumo)

| Item | Estado |
|------|--------|
| Campanha R2 em main | Incorporada (N01–N18 exceto N09 DONE) |
| N01 | **DONE** — não reabrir (`resume.md` R2 stale) |
| N09 | **BLOCKED_SOURCE** (amostra-ouro independente ausente) |
| PR #28 | CONFLICTING — **não mergear** |
| SmartLic dataset | **DEFERRED_STALE** |
| Extra-roi default | Fatias de claims — **override DECISION-001** → cobertura operacional |
| HTML executivo | `extra-consultoria-plano-executivo.html` |
| DOD checkboxes | **195 / 1355 = 14,39%** |

## 2. Planilha canônica

| Campo | Valor |
|-------|-------|
| Path | `Extra - alvos de licitação. R-0.xlsx` |
| SHA-256 | `d65f272812cf8dc95f3ca78c5db9a2fb2a39a759e5633eb3fb91891ad10a5486` |
| Bytes | 156599 |
| Seed | 2085 entes totais; **1093** ativos no raio 200 km (denominador) |

## 3. Ambiente e schema

- DSN: `postgresql://test:test@127.0.0.1:5433/extra_test`
- Container: `extra-test-db` (postgis/postgis:16-3.4)
- **Incidente:** volume PG vazio após restart Docker → rebuild migrations 001–056 + seed
- Pré-condição fresh install: `esfera_id` INT→TEXT antes da migration 018
- Extension `vector`/HNSW: optional gap (014 repair)

## 4. Métricas live **pós-rebuild** (verdade atual)

| Métrica | Valor | Claim |
|---------|------:|-------|
| Denominador 200 km | **1093** | Sim |
| Bids rows | **0** | Volume zerado — re-coleta obrigatória |
| Contracts rows | **0** | Idem |
| Presença editais | **0%** | Não cobertura operacional |
| Presença contratos | **0%** | Idem |
| Either | **0%** | Proibido como meta |
| Strict operational | **0%** | Meta ≥95% cada capability |
| Freshness / recall / snapshot | NOT_READY | — |

### Histórico R2 (NÃO é estado atual)

Antes do wipe do volume: presença editais 26,08%, contratos 33,67%, either 37,15%, strict ~37,24% após promote, ~1,08M contratos.  
Esses números são **lineage only** até re-coleta.

## 5. Segunda importação do universo

```
Upsert: 0 inserted, 2085 updated
Within 200km: 1093 (estável)
```

**Interpretação:** denominador estável; seed é reentrante (zero inserts).  
Diff de conteúdo campo-a-campo (true zero-change) permanece a validar via snapshot universe se disponível.

## 6. Metas DOD de aceitação

| Meta | Itens (den=1355) |
|------|-----------------:|
| Piso 50% | ≥678 |
| DONE campanha 55% | ≥746 |
| Excelência 60% | ≥813 |
| Atual | **195 (14,39%)** |

## 7. Claims proibidos neste baseline

- 95% cobertura; either como cobertura; LOCAL_READY; recall 95%; SmartLic operacional; 1M contratos ainda presentes; inflação de checkboxes.

## 8. Próximo passo material (ROI override)

1. Re-coleta contratos (`full` 90d + checkpoint) e editais PNCP  
2. Promote registry com proveniência  
3. Medir presença e strict **separados**  
4. Matriz OSS (M0.5) sem adotar sem benchmark  
5. Ciclo consultivo REVIEW-first (perfil incompleto)

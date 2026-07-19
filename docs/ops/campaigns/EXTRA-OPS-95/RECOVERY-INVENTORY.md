# EXTRA-OPS-95 — Recuperação forense (Fase 0)

**UTC start:** ver `STARTED_AT.txt`  
**HEAD de partida (main):** `dbc5adb2ab62898cd3fd005c83c90dcef36c1cde`  
**Mensagem HEAD:** `feat(campaign): close N06c Extra-owned coverage wave and refresh executive HTML`  
**Branch de trabalho canônica:** `main` (campanhas anteriores em main; PR #28 **não** é baseline)

## 1. Última campanha incorporada em main

| Campanha | Path | Status em main |
|----------|------|----------------|
| NEXT-30D-ROI-MAIN-R2 | `docs/ops/campaigns/NEXT-30D-ROI-MAIN-R2/` | **Incorporada** — HEAD tip inclui closeout N06c + HTML |
| NEXT-30D-ROI-MAIN (R1) | `docs/ops/campaigns/NEXT-30D-ROI-MAIN/` | Incorporada (pré-R2) |
| ADVANCE-30D / PR #28 | `epic/advance-30d-local-ready-20260718` | **NÃO mergeada**; `mergeable=CONFLICTING` |

**Não recontar** resultados de branches não integradas (PR #28, epic coverage branches).

## 2. Hipóteses herdadas — confirmação

| Hipótese | Veredito | Evidência live |
|----------|----------|----------------|
| Campanha recente PNCP + contratos | **CONFIRMADO** | N06c wave2 em main; ledger R2 |
| >1M registros de contratos | **CONFIRMADO** | `pncp_supplier_contracts` = **1.082.055** |
| “Either” ~37% | **CONFIRMADO** | **406/1093 = 37,15%** (união; **proibido** como meta) |
| SmartLic stale fora do caminho crítico | **CONFIRMADO** | `DEFERRED_STALE_SOURCE`; container `smartlic-datalake` sobe mas dataset **não** usado |
| N01 próximo vs N01 DONE | **CONFIRMADO contradição** | `scope.json` N01=**DONE** + evidence golden; `resume.md` STALE diz “Next ROI: N01” |
| N09 recall bloqueado | **CONFIRMADO** | `B-R2-N09` BLOCKED_SOURCE; sample scaffold only |
| PR campanha antigo conflitante | **CONFIRMADO** | PR #28 CONFLICTING, +88k/−790 vs main |
| Componentes reutilizáveis | **CONFIRMADO** | opportunity_intel, workspace, crawlers, registry, packages, migrations |
| DOD muitos itens abertos | **CONFIRMADO** | **195/1355** checked em main; 1160 open |
| HTML executivo atualizado | **CONFIRMADO** | tip commits `0517363`, `c8ab504`, `dbc5adb` |

## 3. Contradição N01 — resolução

| Fonte | Diz |
|-------|-----|
| `scope.json` R2 | N01 **DONE** |
| `FINAL-REPORT.md` | N01 DONE com golden PNCP+PCP strict |
| `evidence/N01-golden/` | ledger + log de sucesso |
| `resume.md` R2 | “Next ROI: **N01**” — **STALE / errado** |

**Decisão EXTRA-OPS-95:** N01 **não** é reexecutado como marco de campanha. Golden path pode ser re-provado como smoke de aceitação (Fase 5/7), não como “abrir N01 de novo”. Próximo avanço material = **cobertura operacional separada editais/contratos** + ciclo consultivo.

## 4. Baseline de métricas (live 2026-07-19, PG `extra_test:5433`)

| Métrica | Valor | Claim permitido? |
|---------|------:|------------------|
| Denominador canônico | **1093** | Sim (seed planilha + `sc_public_entities`) |
| Meta 95% numérica | **≥1039/1093** cada capacidade | Sim como meta, **não** como atingido |
| Entidades com editais (match live) | **285 / 1093 = 26,08%** | Presença de registros — **não** cobertura operacional §3.2 |
| Entidades com contratos (cnpj8) | **368 / 1093 = 33,67%** | Idem |
| Either (proibido como meta) | **406 / 1093 = 37,15%** | Só diagnóstico |
| Linhas contratos | **1.082.055** | Volume, não cobertura |
| Linhas bids PNCP | **10.974** | Volume |
| Janela contratos min→max pub | 2026-01-19 → 2026-07-18 (~180d) | 3y **não** GO |
| `operational_source_coverage` (registry strict) | **90/1093 = 8,23%** (contract CLI) / stats `operational=0` se `is_strict_operational` | Divergência de contagem a reconciliar; **nenhum** ≥95% |
| `source_mapping_coverage` | **1093/1093 = 100%** | Mapeamento ≠ operacional |
| Commercial signal | **116/1093 = 10,61%** | **NÃO** cobertura |
| Freshness entity-level | **NOT_READY** | — |
| Recall estratificado | **NOT_READY / BLOCKED_SOURCE** | — |
| `capability_coverage` rows | **0** | tabela vazia |
| DoD checked main | **195/1355 = 14,39%** | Processo, não ops |

## 5. Capacidades reaproveitáveis (não reescrever)

- Crawlers: `scripts/crawl/contracts_crawler.py` (full/incremental/backfill_3y + checkpoint), bids, ciga_dom, sc_compras, monitores
- Registry: `scripts/source_registry/` + `promote_from_evidence` / acquire strategies
- Coverage contract: `scripts/coverage/coverage_contract.py` (métricas separadas)
- Opportunity intel / workspace / deliverables A–E (parcialmente em epic PR #28)
- Golden path, ops packages, migrations 052–056, extra-dod-roi squad
- HTML: `extra-consultoria-plano-executivo.html`

## 6. Blockers

| ID | Classe | Impacto |
|----|--------|---------|
| B-R2-N09 | BLOCKED_SOURCE | Recall ≥95% sem gold set independente |
| B-R2-001 | BLOCKED_SOURCE/runtime | Backfill contratos 3y incompleto (só ~180d) |
| B-R2-002 / PR#28 | CONFLICT_WITH_ACTIVE_WORK | PR conflitante — não mergear às cegas |
| blk-coverage-95 | WORK REMAINS | Editais e contratos << 95% operacional |
| blk-vps / canary | BLOCKED_EXTERNAL | Fora do caminho local obrigatório |
| DEF-SMARTLIC | DEFERRED_STALE | Não reintroduzir dataset |

## 7. PRs abertos — decisão proposta

| PR | Estado | Decisão EXTRA-OPS-95 |
|----|--------|----------------------|
| **#28** epic advance-30d | OPEN, CONFLICTING, base main desatualizada | **Não mergear como entrega.** Tratar como **parcialmente superseded** por R2 em main. Extrair depois, se necessário, apenas deltas exclusivos úteis (deliverables A–E, package final, monthly monitor) via cherry-pick seletivo em branch limpa. Preferir **fechar sem merge** se delta já existir em main ou for fixture-only. |

## 8. Documentos canônicos vs stale

| Canônico (confiar) | Stale / lineage only |
|--------------------|----------------------|
| `DOD.md` em main HEAD | `resume.md` R2 (aponta N01) |
| `coverage_contract` + report live | Métricas “either” como se fossem meta |
| `NEXT-30D-ROI-MAIN-R2/scope.json` + FINAL-REPORT | Scorecards do epic PR #28 |
| `output/` + PG live | Session reports em branch epic não mergeada |
| Denominador 1093 | Qualquer “denominador reduzido” |

## 9. Ponto exato de retomada

1. **Não** reabrir N01/N02–N06c como marcos de checkbox.
2. Tratar **cobertura operacional editais e contratos separadas** como caminho crítico.
3. Elevar de:
   - presença editais 26% / contratos 34%
   - operacional strict ~0–8%
   para marcos 60% → 80% → 95% **ou** blockers nominais incontestáveis.
4. Em paralelo seguro: ciclo consultivo (radar → decisão → package) sobre dados já existentes.
5. Extra-roi default ranking prioriza fatias DoD de linguagem/claims — **OVERRIDE** para capacidade operacional (ver `roi/DECISION-001.json`).

## 10. Premissas conservadoras registradas

- Perfil Extra incompleto para GO → recomendações **REVIEW** por default.
- Fixture ≠ prova live.
- SmartLic container up ≠ fonte operacional.
- PR #28 DoD 437/1354 **não** é métrica de main.

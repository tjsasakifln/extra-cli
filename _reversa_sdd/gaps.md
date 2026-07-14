# Gaps Report — Extra Consultoria (v3.0)

> Gerado pelo Reviewer em 2026-07-13 | doc_level: completo | Base: 249340d
> **Fonte:** Consolidação de 5 agentes QA (Grupos A-E) + gaps v2.0 remanescentes

## 🔴 CRÍTICAS (8) — Bloqueiam operação confiável

| ID | Lacuna | Módulo | Bloqueia | Origem |
|----|--------|--------|----------|--------|
| G-01 | Schema fragmentado: 3 diretórios (db/migrations, supabase/migrations, current-schema.sql) | db | P0-02 | v2.0 |
| G-02 | Snapshot reconciliation não implementado (673 vs 34 registros) | opportunity_intel | P0-04 | v3.0 |
| G-03 | 4 módulos lib ausentes: universe, geocode, entity_hierarchy, value_semantics | lib | P0-03, P0-05 | v3.0 |
| G-04 | ~18 crawlers reais, 9 documentados + subdiretórios omitidos (clients/, ingestion/) | crawl | P0-06 | v3.0 |
| G-05 | diagnose (25K LOC) e transparencia (14K LOC) com apenas 2 FRs cada | diagnose, transparencia | — | v3.0 |
| G-06 | Módulo `intel/` nas matrizes não existe na lista oficial de 17 módulos | code-spec-matrix | Consistência | v3.0 |
| G-07 | 76 arquivos Python não listados individualmente na code-spec-matrix | code-spec-matrix | Rastreabilidade | v3.0 |
| G-08 | Views canônicas não materializadas (v_contracts, v_suppliers, v_entities, v_value_obs) | db, contract_intel | P0-02, P0-09 | v3.0 |

## 🟡 ALTAS (7) — Afetam qualidade significativamente

| ID | Lacuna | Módulo | Origem |
|----|--------|--------|--------|
| G-09 | Reports não documenta dependência do módulo Coverage | reports | v3.0 |
| G-10 | db spec sem refs ao plano-mestre §6 e migrations 030-036 | db | v3.0 |
| G-11 | config/constants.py invisível em todos os specs | config | v3.0 |
| G-12 | Sobreposição crawl PNCP: intel (legado) vs opportunity_intel (novo) | intel, opportunity_intel | v3.0 |
| G-13 | Duas funções de universo sem relação documentada | lib, contract_intel | v3.0 |
| G-14 | docs/requirements.md (base e9729e1) vs docs/design.md (base 249340d) | docs | v3.0 |
| G-15 | Convenção dupla de nomenclatura (snake_case vs kebab-case) nos scripts intel | intel | v2.0 |

## 🟢 MÉDIAS (5)

| ID | Lacuna | Módulo | Origem |
|----|--------|--------|--------|
| G-16 | bids_crawler.py possivelmente dead code | crawl | v3.0 |
| G-17 | Helpers duplicados (_digits_only, _safe_float, _parse_date) entre crawlers | crawl | v2.0 |
| G-18 | Transição de orquestrador (monitor.py → orchestrator.py) não documentada | crawl | v2.0 |
| G-19 | Modelo de negócio da consultoria não documentado formalmente | docs | v3.0 |
| G-20 | SICAF via Playwright — dependência frágil de captcha | intel | v2.0 |

## ⚪ BAIXAS (4)

| ID | Lacuna | Módulo | Origem |
|----|--------|--------|--------|
| G-21 | Version pinning ausente em requirements.txt | config | v2.0 |
| G-22 | Docs operacionais potencialmente desatualizados (30 commits) | docs | v2.0 |
| G-23 | Sem smoke tests para 7 fontes complementares | tests | v3.0 |
| G-24 | transparencia_config.yaml com municipios: {} vazio | transparencia | v2.0 |

## Lacunas Resolvidas (v2.0 → v3.0)

| ID | Lacuna Original | Resolução |
|----|----------------|-----------|
| GAP-01 (antigo) | Schema v1 vs migrations divergentes | Baseline v2 aplicada. Migrations 030-036 planejadas no plano-mestre §6 |
| GAP-02 (antigo) | Orquestrador dual (monitor.py vs orchestrator.py) | Decidido: orchestrator.py canônico. Systemd timers a migrar |
| GAP-07 (antigo) | ARP/PCA incompatíveis com pipeline sync | Async é intencional. Execução separada na VPS |

## Relação com Plano-Mestre

| EPIC P0 | Gaps Relacionados | Status |
|---------|-------------------|--------|
| P0-01 (Documentação) | G-14, G-19, G-22 | ❌ Não iniciado |
| P0-02 (Schema) | G-01, G-08, G-10 | ❌ Não iniciado |
| P0-03 (Universo) | G-03, G-13 | 🔄 Parcial |
| P0-04 (Reconciliação) | G-02 | ❌ Não iniciado |
| P0-05 (Cobertura) | G-03 | 🔄 Parcial |
| P0-06 (Fontes) | G-04 | ❌ Não iniciado |
| P0-07 (Perfil) | — | ❌ Não iniciado |
| P0-08 (Contratos) | G-08 | ❌ Não iniciado |
| P0-09 (Concorrentes) | G-08 | ❌ Não iniciado |

**Conclusão:** Nenhum EPIC P0 concluído. Sistema `PARTIAL / NOT CLIENT-READY`.

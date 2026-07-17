# Cycle Summary — B2G Operational Platform (2026-07-17)

**Branch:** `epic/b2g-operational-platform-2026-07-17`  
**Base SHA (main):** `bb3800b47bce574ebfcb5d85cdebb033aa1e21b1`  
**Denominador:** **1093** (fixado; não alterado)

## Baseline → atual

| Dimensão | Baseline (sessão PR#9) | Após este ciclo | Meta |
|----------|------------------------|-----------------|------|
| Sinal comercial (`entities_with_recent_commercial_signal`) | 116/1093 (10,61%) | **116/1093 (10,61%)** — renomeado, não confundir com cobertura | n/a (sinal) |
| Source mapping coverage | inexistente formal | **1093/1093 (100%)** | 100% |
| Operational source coverage | confuso com sinal comercial | **0/1093 (0%)** estrito (collected/verified only; dry_run local_hit NÃO conta) | **95%** |
| Freshness coverage | parcial | **NOT_READY** — sem ledger por entidade válido | 95% |
| Opportunity recall | ausente | **PARTIAL 4/4 observado; NOT_READY no contrato** por estratos e independência ausentes | 95% |
| Field completeness | implícito | **~17,7%** mean decision fields | alto |
| GO recommendations | 14 | 14 (subset do encontrado) | — |

## Entregas do ciclo

1. **Contrato formal de cobertura** (`scripts/coverage/coverage_contract.py` + CLI)
2. **Source registry 1093** + discovery + gaps nominais
3. **Estratégias de aquisição:** CIGA DOM público live (15.793 registros; 282 municípios observados) e DOE-SC CKAN público (41.080 lidos; sem credencial)
4. **Workspace CLI unificado** (`python -m scripts.workspace`)
5. **Perfil Extra expandido** com elicitação PENDING
6. **Recall benchmark preliminar real** com quatro itens oficiais, propositalmente `PARTIAL`
7. **ADRs 017–022**, matriz de capacidades, epic B2G + stories E1–E5
8. **Persistência:** migrations 052/053; 1.093 entidades + 300 atos; duplicatas source/hash = 0
9. **Testes:** 74 críticos PASS; golden path PCP estrito SUCCESS (`gp-20260717-102949`)

## Gaps restantes (honestos)

- Operational **0% (0/1.093)** << 95% — gap nominal em `output/coverage/entity-source-gaps.*` (1.093 entidades)
- Blockers: pending_collection (714), pending_live_verification (226), fragmented (153); **credential=0** para DOM/DOE públicos
- Recall 4/4 observado não é aceito: requer observação independente e sete estratos restantes
- opportunity_intel em DB local tem poucos registros reais (muitos test_batch)
- Scheduler VPS não marcado operacional sem prova
- Preço praticado item-level NOT_READY (ADR-002)

## Impeditivos por classe → estratégia

| Classe | Estratégia |
|--------|------------|
| rate_limited | backoff+jitter+checkpoint; fail-closed parcial (ADR-021) |
| fonte pública stale | atualizar catálogo/recurso CIGA/DOE e verificar publicação dentro do SLA |
| fragmented / no_api | adapters HTML/PDF/JS + shared portals |
| shared_portal_mapped | CIGA expand + reconcile official_acts |
| weak_cnpj | enricher CNPJ + matching |

## Não feitos neste ciclo (stories abertas)

E1.S3–S4, E2.S3–S4, E3.*, E4.S2–S3, E5.*, E6–E13 (outline no epic). E1.S2 e E2.S2 permanecem em revisão até CI/QA final.

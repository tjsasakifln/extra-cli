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
| Freshness coverage | parcial | **35/1093 (3,2%)** SLA proxy | 95% |
| Opportunity recall | ausente | **NOT_READY** (scaffold) | 95% |
| Field completeness | implícito | **~17,7%** mean decision fields | alto |
| GO recommendations | 14 | 14 (subset do encontrado) | — |

## Entregas do ciclo

1. **Contrato formal de cobertura** (`scripts/coverage/coverage_contract.py` + CLI)
2. **Source registry 1093** + discovery + gaps nominais
3. **Estratégias de aquisição:** `pncp_orgao_probe` (105 hits locais), `ciga_municipio_expand` (483–556 municipais)
4. **Workspace CLI unificado** (`python -m scripts.workspace`)
5. **Perfil Extra expandido** com elicitação PENDING
6. **Recall benchmark scaffold**
7. **ADRs 017–022**, matriz de capacidades, epic B2G + stories E1–E5
8. **Testes:** 46 unitários coverage+registry+workspace PASS

## Gaps restantes (honestos)

- Operational 9,61% << 95% — gap nominal em `output/coverage/entity-source-gaps.*` (988 entidades)
- Blockers: credential (264), fragmented (137), pending collection evidence
- Recall ainda requer observação independente de portais (não DB count)
- opportunity_intel em DB local tem poucos registros reais (muitos test_batch)
- Scheduler VPS não marcado operacional sem prova
- Preço praticado item-level NOT_READY (ADR-002)

## Impeditivos por classe → estratégia

| Classe | Estratégia |
|--------|------------|
| rate_limited | backoff+jitter+checkpoint; fail-closed parcial (ADR-021) |
| credential | DOM/DOE secrets; não contar como coberto até validar |
| fragmented / no_api | adapters HTML/PDF/JS + shared portals |
| shared_portal_mapped | CIGA expand + reconcile official_acts |
| weak_cnpj | enricher CNPJ + matching |

## Não feitos neste ciclo (stories abertas)

E1.S2–S4, E2.S3–S4, E3.*, E4.S2–S3, E5.*, E6–E13 (outline no epic).

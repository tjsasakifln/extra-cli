# PE-C2-05 — Desbloquear DOM-SC via CIGA Dados (sem API key)

Status: InProgress  
Epic: EPIC-PLANO-EXECUTIVO-30D  
Tasks plano: C2.5  
Risk: HIGH-RISK  
Priority: P0

## Story

Como data engineer, quero integrar o DOM/SC pelo CIGA Dados (CKAN público, sem chave), para desbloquear a fonte municipal que estava BLOCKED por credenciais desnecessárias.

## Acceptance Criteria

1. **Given** e-mail CIGA, **when** documentação, **then** baseline registra portal público sem auth.
2. **Given** `ciga_ckan`, **when** validate credentials, **then** ok sem env vars.
3. **Given** publicação fixture, **when** transform, **then** registro com source_id, link, município; valor/CNPJ nulos (não inventados).
4. **Given** registry, **when** lookup ciga_ckan, **then** capabilities incluem open_tenders.
5. **Given** runtime (1 mês ou amostra), **when** crawl, **then** evidência com contagens em docs/baseline.

## File List

- `scripts/crawl/ciga_ckan_crawler.py`
- `scripts/crawl/registry.py`
- `config/source_applicability.yaml`
- `.env.example`
- `tests/test_ciga_ckan_transform.py`
- `docs/baseline/c2-domsc-ciga-dados-unblocked.md`
- `docs/baseline/c2-ciga-ckan-runtime.md`
- `docs/baseline/c2-domsc-blocked.md`
- `extra-consultoria-plano-executivo.html`

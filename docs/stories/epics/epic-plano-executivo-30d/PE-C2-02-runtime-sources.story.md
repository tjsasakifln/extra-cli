# PE-C2-02 — Evidências runtime PNCP/PCP/ComprasGov

Status: InReview  
Epic: EPIC-PLANO-EXECUTIVO-30D  
Tasks plano: C2.3, C2.4, C2.6  
Risk: HIGH-RISK  
Priority: P1

## Story

Como data engineer, quero evidências runtime das fontes prioritárias no HEAD, para avançar cobertura de editais sem fake green.

## Acceptance Criteria

1. **Given** PNCP, **when** crawl dry-run ou incremental limitado, **then** evidência de sucesso ou BLOCKED com causa.
2. **Given** PCP, **when** validação, **then** evidência de records/entes ou BLOCKED.
3. **Given** ComprasGov, **when** validação, **then** reconciliar claim de validação com execução HEAD.
4. **Given** DOM-SC (C2.5), **when** sem credencial, **then** permanece BLOCKED documentado.

## File List

- `docs/baseline/c2-pncp-runtime.md`
- `docs/baseline/c2-pcp-tce-runtime.md`
- `docs/baseline/c2-comprasgov-runtime.md`
- `docs/baseline/c2-domsc-blocked.md`

# PE-L1-02 — Universo canônico + registry capability

Status: Ready  
Epic: EPIC-PLANO-EXECUTIVO-30D  
Tasks plano: L1.2, L1.4  
Risk: HIGH-RISK  
Priority: P0

## Story

Como data engineer, quero importar/versionar o universo de 1.093 entes e consolidar registry fonte×ente×capability, para denominadores de cobertura corretos.

## Acceptance Criteria

1. **Given** planilha canônica, **when** import/reconciliação, **then** total no raio é calculado da planilha e reportado (baseline 1093 se planilha atual).
2. **Given** universe module, **when** relatório, **then** hash/versão da planilha e contagens batem planilha×código.
3. **Given** fontes, **when** registry, **then** manifesto de aplicabilidade por capability existe (applicable/not_applicable; unknown listados).

## File List

- `docs/baseline/l1-universe-reconciliation.md`
- `docs/baseline/l1-source-capability-registry.md`

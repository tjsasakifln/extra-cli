# Evidence Inconsistency Matrix — Pilot 90d PNCP (K3.2 / NEXT-30D)

**Auditoria:** Subagent A (evidence)  
**Data:** 2026-07-17  
**Fonte de verdade (on-disk):** `output/contracts/pilot-90d-next30d.json`

## Ground truth (verificado)

| Campo | Valor |
|-------|-------|
| `status` | `partial` |
| `go_no_go_3y` | `NO-GO` |
| `go_no_go_path` | `GO` |
| `path_proof.status` | `success` (1d, `20260715_20260715`) |
| `full_90d_session.status` | `not_completed` |
| Checkpoint canônico | 1 janela (`20260715_20260715`); não 90d |
| DB contracts (artifact) | ~42k (parcial / cumulativo) |
| Cobertura editais | **4.76%** (não 95%) |
| VPS | **não** operacional |
| `claims_forbidden` | Full 90d national completed; GO 3y unsupervised; `CONTRATOS_95` |

## Matriz

| # | Artefato | Claim problemático | Verdade | Severidade | Ação |
|---|----------|-------------------|---------|------------|------|
| 1 | `NEXT-30D-FINAL-SCORECARD.md` metrics | `pilot status \| **success**` | overall `status=partial` (path_proof=success ≠ pilot full) | **HIGH** | Corrigido → `partial` |
| 2 | `NEXT30-GATE-D.md` | `Terminal pilot artifact — status success` | `partial` | **HIGH** | Corrigido → `partial` + NO-GO 3y |
| 3 | `NEXT-30D-ADVERSARIAL-AUDIT.md` §on-disk | `pilot status = success` (bloco top) | overall `partial`; só path_proof=success | **HIGH** | Corrigido; bloco distingue path vs full |
| 4 | `NEXT-30D-ADVERSARIAL-AUDIT.md` | ref `test_terminal_pilot_artifact_is_success` | teste real: `…_is_not_running` | MED | Corrigido nome |
| 5 | `NEXT-30D-ADVERSARIAL-AUDIT.md` commands | `pilot status… → success` | `partial` | MED | Corrigido |
| 6 | Scorecard K3.2 row | `DONE_PARTIAL` + NO-GO | **OK** (coerente) | — | Manter |
| 7 | `k3.2-pncp-90d-pilot-next30d.md` | PARTIAL / NO-GO | **OK** | — | Manter |
| 8 | `NEXT30-GATE-B.md` | status=partial; NO-GO 3y | **OK** | — | Manter |
| 9 | Adversarial table Contracts pilot | DONE_PARTIAL partial/NO-GO | **OK** (contradizia §top) | — | §top alinhado |
| 10 | Pilot JSON numbers | — | **não inventar success** | — | Intactos |
| 11 | Checkpoint `a5_next30d` | 1 janela ~42k fetched | partial run, não 90d full | INFO | Não confunde claim terminal |

## Claims permitidos (ainda)

- Path proof 1 dia com 0 page errors
- Runner resumível; janela parcial não marca complete
- Dezenas de milhares de contratos em DB (parcial)
- `go_no_go_path=GO`; `go_no_go_3y=NO-GO`
- Cobertura editais **4.76%**

## Claims proibidos (ainda)

- Full 90-day national pilot completed / `status=success` no pilot integral
- GO para backfill 3y sem supervisão
- `CONTRATOS_95` / `EDITAIS_95`
- `LOCAL_READY` / `VPS_OPERATIONAL` / `PROJECT_DONE`

## Teste de regressão

`tests/test_evidence_artifact_consistency.py` — fail-closed se scorecard/artifact divergirem quando `status=partial`.

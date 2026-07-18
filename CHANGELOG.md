# Changelog — Extra Consultoria

Formato baseado em [Keep a Changelog](https://keepachangelog.com/).  
O histórico de git (`git log`) permanece a fonte de verdade de commits; este arquivo resume marcos operacionais.

## [Unreleased] — branch `epic/advance-30d-local-ready-20260718`

### Campanha ADVANCE-30D-LOCAL-READY (2026-07-18)

- Baseline regenerado: DoD ~92→117+ `[x]` (em evolução); cobertura operacional **não** ≥95%; gates `LOCAL_READY` / `PRE_VPS_FINAL_READY` **não** claimados.
- Fail-closed: scanner de gates sem `|| true` (`scripts/ops/scan_mandatory_gates_failclosed.py`).
- Catálogo de indicadores com definition/formula/denominator/as_of/source + `READY_SEMANTICS`.
- Guards de linguagem de claims (`scripts/lib/claim_language.py`).
- Consistência de definições em docs canônicos; glossário; índice de ADRs; runbooks rollback / schema drift / cobertura &lt;95%.
- Remoção de checkbox DoD vazio + filtro no ranking ROI.
- PRD v2.1 alinhado ao DOD (64,4% reclassificado como histórico).

## [2026-07-17] — DoD-50 + coverage M2 + next-30d close

- Campanha DoD-50 com remediação cética (PRs #24–#27).
- Coverage multi-source M2 (presença operacional parcial, não 95%).
- NEXT-30D scorecard: CP PERT ≥30 sem claim de 95%/LOCAL_READY.

## Como identificar o próximo passo

1. `python3 squads/extra-dod-roi/scripts/cli.py force-next` — ranking[0] obrigatório.
2. Ler `squads/extra-dod-roi/state/campaigns/advance-30d-20260718/scorecard.json`.
3. Regenerar métricas: `python3 -m scripts.coverage.coverage_contract_cli` (quando DSN válido).

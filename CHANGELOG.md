# Changelog — Extra Consultoria

## Unreleased

### CONFENGE commercial activation

- Campaign CONFENGE-COMMERCIAL-ACTIVATION-AND-OUTCOME-LOOP-01: full-history commercial cycle, canonical coverage, dossiers/kits (see PR #172).

Formato baseado em [Keep a Changelog](https://keepachangelog.com/).  
O histórico de git (`git log`) permanece a fonte de verdade de commits; este arquivo resume marcos operacionais.

## [Unreleased]

- chore(campaign): re-freeze CONFENGE after official registry coverage honesty fix


- fix(commercial): separate official RFB registry coverage from redistributor fallbacks; skeptic closeout artifacts (§23/§24)


- docs(campaign): CONFENGE commercial activation closeout (PR B) — post-merge cycle on main `7243b87f`, soak non-interference PASS, human-only commercial blocker


### Documentação (2026-07-25)

- README, DEVELOPMENT, ops hub, architecture, GLOSSARY, INDEX e NEXT-DEV-STEP alinhados ao host Netcup, dual HC + open_tenders, soaks e non-claims DOD.
- Docs pré-VPS / Hetzner rotulados como snapshot histórico.
- Estado na `main`: dual 100% em ambas capabilities; campanhas OT/HC **BLOCKED** por calendário (soak) + recall residual.

### Campanha HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01 (2026-07-22…23)

- Spec `specs/002-historical-contracts-operational-coverage/`.
- Backfill PNCP ≥3 anos **37/37** materializado na VPS (~4,4M `pncp_supplier_contracts`).
- Dual `historical_contracts` **PASS 100%** (1093/1093).
- Cutover VPS, incremental `pncp-contracts`, restore drill, off-site **Netcup Storagespace NFS**.
- Resultado de campanha: **BLOCKED** por soak 7d (não claimar `VPS_OPERATIONAL` / `PROJECT_DONE`).
- Artefatos: `artifacts/campaigns/HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01/`.

### Dual capability + full suite (2026-07-20…21)

- ADR-028 freshness por capability; ADR-029 full suite; ADR-030 dual coverage truth.
- Spec `specs/001-dual-capability-coverage-truth/`.
- Freshness dual reports editais/contratos (sem claim 95% open_tenders).

### Host Netcup (2026-07-23)

- Host de record: Netcup RS 2000 · Debian 13 · PostgreSQL 17 · `ssh ec-prod`.
- ADR INDEX / README atualizados; Hetzner permanece fallback/histórico de planejamento.

## [2026-07-18] — ADVANCE-30D-LOCAL-READY

- Baseline regenerado: DoD em evolução; cobertura operacional **não** ≥95%; gates `LOCAL_READY` / `PRE_VPS_FINAL_READY` **não** claimados.
- Fail-closed: scanner de gates sem `|| true` (`scripts/ops/scan_mandatory_gates_failclosed.py`).
- Catálogo de indicadores + guards de linguagem de claims.
- Consistência de definições em docs canônicos; glossário; índice de ADRs.
- Branch de referência: `epic/advance-30d-local-ready-20260718`.

## [2026-07-17] — DoD-50 + coverage M2 + next-30d close

- Campanha DoD-50 com remediação cética (PRs #24–#27).
- Coverage multi-source M2 (presença operacional parcial, não 95%).
- NEXT-30D scorecard: CP PERT ≥30 sem claim de 95%/LOCAL_READY.
- Ciclo B2G operacional: universo 1.093, workspace commands, golden path PCP.

## Como identificar o próximo passo

1. Ler `docs/ops/NEXT-DEV-STEP.md`.
2. `python3 squads/extra-dod-roi/scripts/cli.py force-next` — ranking[0] obrigatório quando em modo campanha ROI.
3. `python3 tools/dod_controller.py next` — convergência DOD.
4. Regenerar métricas: `python3 -m scripts.coverage.coverage_contract_cli` (quando DSN válido).

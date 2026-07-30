# Spec 007 — CONFENGE Commercial Activation & Outcome Loop

**Campaign:** `CONFENGE-COMMERCIAL-ACTIVATION-AND-OUTCOME-LOOP-01`  
**Capability:** `confenge_commercial_activation`  
**Class:** `REPAIR_AND_ACTIVATE_VERTICAL`  
**Branch:** `campaign/confenge-commercial-activation-outcome-loop-01`  
**Base main:** `e39a75f35224cdf1acd34c2a8eb2f5ea08fa220e` (post-#171)  
**Operator / sole human acceptance:** Tiago Sasaki  
**Pilot client preserved:** Extra Construtora  

## Problem

A implementação comercial CONFENGE existe (`specs/006`, `make confenge-commercial-cycle`) mas permanece **BLOCKED** com:

- snapshots de 60k / 12k contratos tratados como se fossem varredura integral;
- métricas de cobertura cadastral divergentes entre `result.json`, `queue-summary` e nested metrics;
- `supplier_registry` vazio no banco de record (VPS);
- ausência de dossiers/kits acionáveis e de loop de outcome append-only em operação real;
- único blocker legítimo residual deveria ser o aceite humano de Tiago.

## Actors

| Actor | Role |
|-------|------|
| Tiago Sasaki | Revisão humana, labels, aceite comercial, envio manual de mensagens |
| Pipeline determinístico | Snapshot → cadastro → sinais → fila → dossiers → kits → delta |
| Soak / timers VPS | Observados; não mutados por esta capability |

## Goals

1. Histórico canônico **integral** (≥3 anos, contagem real observada — baseline VPS **4 467 364** contratos).
2. Cadastro oficial RFB (ou extract autenticado) com estados `RESOLVED|DEFINITIVELY_NOT_FOUND|INVALID_CNPJ|SOURCE_ERROR|PENDING`.
3. **Uma** fonte canônica de cobertura (global, elegíveis, Top100, Top20, status, blockers).
4. Top 20 (ou todas as defensáveis) + gate Top 10 forte.
5. Dossier por empresa (20) + kit de abordagem Top 5 (manual only).
6. Ledger append-only de estados/outcomes; segunda execução idempotente.
7. Pacote de revisão humana; precision@k null até labels de Tiago.
8. Entry point canônico permanece `make confenge-commercial-cycle`.

## Non-goals

- Envio automático de WhatsApp/e-mail/ligação.
- Claims de propensão, intenção de compra, lead quente, probabilidade de conversão.
- Nova plataforma comercial paralela ou segundo comando canônico concorrente.
- Merge/rebase/close do PR #133.
- Declarar `VPS_OPERATIONAL`, `LOCAL_READY`, `PROJECT_DONE`, soak 7 dias fabricado.
- Justificar avanço por % no `DOD.md`.

## Inputs

- SOURCE: DB record ou snapshot autenticado do histórico real (read-only).
- STATE: DB/schema isolado para `commercial_*` e registry (portas allowlist 5441/5433/…).
- Perfil: `config/commercial_profiles/confenge.yaml`.
- Catálogo: `config/commercial_profiles/signal_catalog.yaml` (≥12 sinais).
- Manifest de snapshot com hash canônico escalável (não só row_count + 5 amostras).

## Outputs

| Artifact | Description |
|----------|-------------|
| `run/cycle-manifest.json` + `run-result.json` | Status terminal + métricas canônicas |
| `top20` queue exports | JSON/CSV reconciliados |
| `top20-dossiers/` | Markdown+JSON por CNPJ |
| `top5-outreach-kits/` | Kits manuais |
| `TIAGO-REVIEW.md` + review xlsx/template | Pacote humano |
| `baseline-comparison` + `run-delta` | Diff vs run anterior / baselines simples |
| `user-acceptance.template.json` | Só Tiago → ACCEPTED |

## States (commercial)

`NEW`, `REVIEWED`, `QUALIFIED`, `DISQUALIFIED`, `CONTACTED`, `REPLIED`, `MEETING`, `PROPOSAL`, `WON`, `LOST`, `DO_NOT_CONTACT`.

Transitions append-only; re-run must not erase human history or reactivate DNC.

## Language rules

**Forbidden as fact:** propensão, probabilidade de compra, intenção, dor comprovada, lead quente, culpa por evento adverso.  
**Allowed:** sinal observado, hipótese, aderência, prioridade de revisão, oferta sugerida, limitação.

## Sources

- Contratos: `pncp_supplier_contracts` (canônico).
- Cadastro: Receita Federal dados abertos / extract autenticado com provenance.
- Não declarar PASS usando apenas agregadores opacos (BrasilAPI etc.) como autoridade oficial.

## Isolation

- `production_touched=false`, `soak_touched=false`.
- SOURCE read-only; STATE isolado.
- Verify soak non-interference before/after live runs.

## Gates

- Snapshot autenticado integral (ou prefilter documentado com denominadores).
- Cobertura canônica sem divergência entre artefatos.
- Top10: CNPJ + registry resolvido + sector strong/confirmed + ≥1 sinal + evidência + dossier.
- Idempotência no mesmo snapshot.
- Human: `BLOCKED_PENDING_HUMAN_ACCEPTANCE` / `READY_FOR_TIAGO_REVIEW` até Tiago.

## Claims / Non-claims

**Claims (após evidência):** fila sobre histórico real identificado; score decomponível; dossiers/kits gerados; outcomes preserváveis; coverage single-truth.  
**Non-claims:** precision@k sem labels; conversão; soak 7d; PROJECT_DONE.

## Rollback

- Reverter branch/PR; STATE comercial isolado pode dropar/recriar sem tocar SOURCE.
- Não reverter soak counters.

## Human acceptance

Somente Tiago Sasaki altera `user-acceptance` para `ACCEPTED`. Agentes nunca preenchem labels humanos nem forjam precision.

## PR strategy

1. Spec + harness (coverage canônica, dossiers/kits, tests) — reviewable.  
2. Snapshot/registry tooling se necessário.  
3. Evidence package + handoff (artefatos pesados fora do git).  
Never open ready PR with bulk dumps/PDF/XLSX no git.

## Success

- Execução integral real + segunda execução idempotente/delta.
- Top20 + dossiers + kits Top5 + pacote Tiago.
- Terminal: no máximo blockers humanos de Tiago (não inconsistência de coverage/snapshot).

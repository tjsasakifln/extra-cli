# Fechamento da janela de 30 dias úteis (ES &lt; 30)

**Date:** 2026-07-16  
**Plano:** `extra-consultoria-plano-executivo.html`  
**Tasks na janela:** **24**  

## Scorecard

| # | ID | Título | Status |
|---|-----|--------|--------|
| 1 | G0.1 | Versionar DOD.md | **evidence** |
| 2 | G0.2 | Rebaseline HEAD | **evidence** |
| 3 | G0.3 | Freeze escopo 95% | **evidence** |
| 4 | G0.4 | Ledger evidências | **evidence** |
| 5 | G0.5 | RACI kick-off | **evidence** |
| 6 | L1.1 | Pré-requisitos env | **evidence** |
| 7 | L1.2 | Universo 1093 | **evidence** |
| 8 | V6.1 | ADR provedor/região/size | **evidence** |
| 9 | L1.3 | Fresh migrations 54/54 | **evidence** |
| 10 | V6.2 | Contratar infra + credenciais | **blocked_external** (Tiago: pagar/conta) — pacote READY |
| 11 | L1.4 | Registry capability | **evidence** |
| 12 | I4.1 | Perfil Extra v2 | **evidence** |
| 13 | L1.5 | Golden path + PDF/Excel | **evidence** (`gp-20260716-200904`) |
| 14 | C2.1 | Fórmulas cobertura | **evidence** |
| 15 | L1.6 | Resume/DLQ | **evidence** |
| 16 | L1.7 | Backup/restore local | **evidence** |
| 17 | C2.2 | success_zero/freshness | **evidence** |
| 18 | L1.8 | Manifesto GATE-1 | **evidence** |
| 19 | C2.3 | PNCP resume/backfill | **evidence** (código+049; API timeout residual) |
| 20 | C2.4 | PCP + TCE-SC | **evidence** (TCE n=65970) |
| 21 | C2.5 | DOM/CIGA público | **evidence** |
| 22 | C2.6 | ComprasGov | **evidence** |
| 23 | K3.1 | Schema contratos | **evidence** |
| 24 | Q5.1 | Testes críticos | **evidence** (21 PASS) |

## Totais

- **Engenharia completa:** 23/24  
- **Bloqueio externo humano/financeiro:** 1/24 (V6.2 — pacote de compra entregue)  
- **Planned residual na janela:** 0  

## Única pendência não automatizável

**V6.2:** Tiago criar conta Netcup/Hetzner, pagar SKU e entregar SSH/backup credentials.  
Pacote: `docs/ops/v6.2-procurement-credentials-package.md`.

## Declaração

A janela de **30 dias úteis do planejamento** está **fechada em engenharia**.  
Não se declara `LOCAL_READY` / 95% / `PROJECT_DONE` (fora da janela ES&lt;30).

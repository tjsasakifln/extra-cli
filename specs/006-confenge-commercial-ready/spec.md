# Spec 006 — CONFENGE Commercial Ready

**Campaign:** `CONFENGE-COMMERCIAL-READY-01`  
**Capability:** `confenge_commercial_intelligence`  
**Branch:** `campaign/confenge-commercial-ready-01`  
**Base:** `origin/main` @ `8344254942ec48978566317df16d7b3e3caabd89`  
**Primary operator:** Tiago Sasaki  
**Product context:** CONFENGE (pilot client Extra Construtora preserved separately)

## Problem

A CONFENGE precisa de uma fila comercial B2G pequena, explicável e acionável, gerada a partir do dataset canônico de contratos públicos, com perfil e sinais versionados, identidade defensável por CNPJ, evidência reproduzível, revisão humana auditável e execução recorrente — sem interferir no soak de contratos/editais.

## Actors

| Actor | Role |
|-------|------|
| Tiago Sasaki | Operador único; revisão, override, aceite humano |
| Pipeline determinístico | Gera sinais, score, fila, artefatos |
| Soak/VPS timers | Fora de escopo de mutação desta campanha |

## Goals

1. Perfil comercial CONFENGE versionado (`config/commercial_profiles/confenge.yaml`).
2. Catálogo ≥12 sinais com `NOT_COMPUTABLE` honesto.
3. Ciclo canônico `make confenge-commercial-cycle`.
4. Workspace: list / explain / review.
5. Ledger de estados, feedback e outcomes.
6. Baseline comparison + exports abertos.
7. Isolation fail-closed; soak non-interference.
8. Aceite humano explícito (`PENDING_HUMAN` até Tiago).

## Non-goals

- Automatizar contato em nome da CONFENGE.
- Declarar propensão / probabilidade de compra.
- Alterar `make extra-weekly` ou timers de soak.
- Concluir campanhas de soak / 95% / LOCAL_READY.
- Usar `config/client_profiles/extra.yaml` como lei comercial da CONFENGE.

## Functional requirements

| ID | Requirement |
|----|-------------|
| FR-01 | Perfil YAML versionado com serviços, segmentos, geografia, ticket, exclusões, capacidade, limites, policies. |
| FR-02 | Catálogo ≥12 sinais com hipótese, fórmula, campos, janela, threshold, oferta, NC policy. |
| FR-03 | Unidade de lead = PJ com CNPJ14 defensável; excluir PF, órgãos, CNPJ inválido. |
| FR-04 | Score decomponível; ausência → `NOT_COMPUTABLE` (nunca zero silencioso). |
| FR-05 | Fila top-20 ou insuficiência honesta. |
| FR-06 | Estados comerciais fechados + overrides com autor/motivo/data. |
| FR-07 | Baseline recency + total contracted value. |
| FR-08 | Exports: commercial-leads.json/csv, commercial-review.csv, summary, HTML, evidence ledger, baseline. |
| FR-09 | Source/state isolation; production_touched=false; soak_touched=false. |
| FR-10 | Snapshot real autenticado; fixture não passa gate real. |
| FR-11 | Workspace CLI canônico para list/explain/review. |
| FR-12 | Recorrência: duas execuções no mesmo snapshot são idempotentes no ranking. |
| FR-13 | `user-acceptance.json` só vira ACCEPTED com autor Tiago + hashes. |

## Language constraints

**Proibido:** propensão, probabilidade de compra, intenção de compra, empresa interessada, lead quente (como fato), chance de conversão, necessidade comprovada de consultoria.

**Permitido:** sinal observado, hipótese comercial, aderência ao perfil, prioridade para revisão humana, oferta sugerida.

## Claims / Non-claims

**Claims técnicos (após PASS técnico):** perfil versionado; fila sobre snapshot identificado; score explicável; feedback preservável.

**Non-claims:** CONFENGE_COMMERCIAL_READY sem aceite Tiago; purchase propensity; conversion probability; PROJECT_DONE; VPS_OPERATIONAL; LOCAL_READY; soak concluído.

## Errors (fail-closed)

| Condition | Status |
|-----------|--------|
| Isolation violation | FAIL |
| Snapshot missing/unauthenticated | BLOCKED |
| Zero contracts in state DB | BLOCKED |
| Top-10 without CNPJ/evidence/signal | FAIL |
| Export reconciliation fail | FAIL |
| Human acceptance absent | BLOCKED_PENDING_HUMAN (campaign) |

## Gates

- `make campaign-gate-confenge-commercial-ready`
- `make confenge-commercial-cycle`
- `make verify-confenge-commercial-ready-real`
- `make verify-soak-non-interference`
- `make release-candidate-confenge-commercial-ready`
- `make dod-audit-confenge-commercial-ready`

## DOD refs

DOD §2.7 Inteligência comercial CONFENGE — gate `CONFENGE_COMMERCIAL_READY`.

## Success criteria

- **PASS:** requisitos técnicos + snapshot real + gates + aceite Tiago.
- **BLOCKED:** trabalho técnico completo + impedimento humano/externo documentado.
- **FAIL:** requisito obrigatório impossível ou interferência no soak.

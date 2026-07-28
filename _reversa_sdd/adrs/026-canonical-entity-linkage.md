# ADR-026 — Canonical entity linkage com refuse-merge de strong keys

- **Data:** 2026-07-28 (retroativo)
- **Status:** Aceito
- **Confiança:** 🟢

## Contexto
Oportunidades/contratos/órgãos/fornecedores precisavam de golden records sem autoridade paralela que corrompesse coverage.

## Decisão
Tabelas `canonical_organs` / `canonical_suppliers` + links auditáveis (mig 061); decisões pure functions em `linkage/resolve.py`; conflito de strong IDs → ambiguous; auto-accept só exact/deterministic ≥ 0.99.

## Consequências
- Ambiguous/unresolved permanecem no denominador de investigações.
- Dossier consultivo JSON/HTML, não merge silencioso.

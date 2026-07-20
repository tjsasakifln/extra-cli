# PR-MATRIX

> SSOT: `pr-state.json` (generated 2026-07-20T02:14:00Z). Do not hand-edit recommendations/heads without regenerating from SSOT.

| PR | Base | Head | Objetivo | DoD antes | DoD depois | Código funcional | Execução real | Testes | Riscos | Estado |
| -- | ---- | ---- | -------- | --------- | ---------- | ---------------- | ------------- | ------ | ------ | ------ |
| #48 | main | `b1bd71d10dcd` | Orquestrador CTO headless seguro AIOX/ROI | gaps segurança free-shell/always-approve | registry+veto+seal+dontAsk | scripts/cto/* security | unit/adversarial CTO | tests/cto security green; full suite SKIPPED≠green | residual full suite debt | **READY_FOR_HUMAN_REVIEW** |
| #50 | branch #48 | `b73cc2d316c7` | Ciclo real 1 §29 ledger + force-next | canary-only | ledger operacional PARTIAL; story Draft | run_execution_ledger + wire ops | force-next + ledger writes | ledger+wire tests | SDC incompleto (PO/QA) | **BLOCKED_HUMAN** |
| #51 | branch #50 | `11ab4b962a48` | Ciclo real 2 rerank + reconstruct | canary-only | evidence_reconstruct PARTIAL; story Draft | evidence_reconstruct | rerank exclude cycle-1 | reconstruct+ledger tests | depends #50 SDC; force-next still ranking[0]=cycle-1 | **BLOCKED_HUMAN** |
| #52 | main | `466fc09dc05a` | Decision loop semântico | falsos positivos prazo/id/offline | hard-block prazo; identity_mismatch; offline never PARTICIPAR | decision_engine+snapshot+ledger wire | 44+ decision tests | decision_loop_v2 + ledger | perfil PENDING human | **READY_FOR_HUMAN_REVIEW** |

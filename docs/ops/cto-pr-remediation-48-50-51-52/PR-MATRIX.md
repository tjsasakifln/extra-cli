# PR-MATRIX

| PR | Base | Head | Objetivo | DoD antes | DoD depois | Código funcional | Execução real | Testes | Riscos | Estado |
| -- | ---- | ---- | -------- | --------- | ---------- | ---------------- | ------------- | ------ | ------ | ------ |
| #48 | main | `423743fcebb8` | Orquestrador CTO seguro AIOX/ROI | canary+gaps segurança | security gates + PARTIAL cycle status | scripts/cto/* security | unit/adversarial | 146 CTO | full suite skipped | READY_FOR_HUMAN_REVIEW |
| #50 | #48 branch | `28c2cfb720f3` | Ciclo real 1 ACCEPT_TOP | canary-only | binding ROI + PARTIAL §1/§33 | cycle1_roi_integration | cycle1-real ran | unit + suite | story PO still human | READY_FOR_HUMAN_REVIEW |
| #51 | #50 branch | `f707e7b7d42d` | Ciclo real 2 rerank | canary-only | 2º slice + evidence chain | cycle2_rerank_integration | cycle2-real ran | 2 unit | depends #48+#50 | READY_FOR_HUMAN_REVIEW |
| #52 | main | `dd2d501496e3` | Decision loop semântico | falsos positivos | PARTIAL prazo/id/offline | decision_engine+snapshot | 41 tests | 41 | perfil PENDING | READY_FOR_HUMAN_REVIEW |

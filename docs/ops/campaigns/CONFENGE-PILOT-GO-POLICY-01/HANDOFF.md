# HANDOFF — CONFENGE-PILOT-GO-POLICY-01

## Estado desta mudança

Esta implementação corrige a política e os contratos de evidência; não declara aceite humano nem dispara campanha. O DoD §2.7 permanece aberto até CI verde no `main`, revisão Top-20, dez aprovações atribuíveis e aceite formal de Tiago.

## Fluxo operacional

1. Executar o reconcile target-fit sem `--max-enqueue` e o rebuild nacional sobre o datalake integral.
2. Confirmar `UNIVERSE-MANIFEST.json` v2 com `FULLY_RECONCILED=true`, `full_scale=true`, `truncated=false`, `database_snapshot` preenchido e soma das classes igual aos roots observados.
3. Emitir o pacote final informando esse manifesto; contagens históricas não possuem fallback.
4. Tiago revisa o Top-20 via `python -m scripts.confenge.human_review`; decisões são anexadas a `HUMAN-REVIEW-DECISIONS.jsonl`.
5. Reemitir o pacote. Com dez aprovações e gates técnicos verdes, o terminal pode ser `GO_FOR_REAL_CONFENGE_EMAIL_PILOT`, independentemente do gap para 900.
6. O GO mantém Warmbly `PAUSED_MANUAL_START`. Tiago executa separadamente o comando manual de início; e-mail apenas, WhatsApp OFF, 10/h.

## Evidência pesada

Contagens live, listas de roots, decisões e linhas ESR pertencem ao host/Actions. Somente manifesto resumido, hashes e ponteiros podem ser publicados no Git, conforme ADR-020.

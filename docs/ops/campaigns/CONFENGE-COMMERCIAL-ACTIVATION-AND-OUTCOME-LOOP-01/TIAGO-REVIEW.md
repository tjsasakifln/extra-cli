# Revisão humana — Tiago Sasaki

- Status do run: `BLOCKED` / `BLOCKED_INSUFFICIENT_HUMAN_LABELS`
- Handoff: `READY_FOR_TIAGO_REVIEW`
- Run ID: `cl-20260730T010931Z-1b0e4da2`
- Leads na fila: 20
- commercial_release_ready: `False`
- precision@10 / @20: `null` (somente após seus labels)

## O que revisar

1. Top 20 em `leads.json` / `commercial-review.csv`
2. Dossiers em `top20-dossiers/`
3. Kits manuais em `top5-outreach-kits/` (não enviar automaticamente)
4. Holdout / exclusões em artefatos de gate quando presentes
5. Preencher `user-acceptance.template.json` apenas se aceitar

## Regras

- Somente você pode marcar ACCEPTED.
- Não use avaliações de agentes como label humano.
- Contatos ausentes são NOT_AVAILABLE — não inventar.


---

## Campaign closeout (skeptic-fixed)

- Integrated capability SHA: `7243b87ff8158a8026ccba6c4690a42b09884b07`
- Closeout main tip at packaging: `70d904ef6cd5d68a54dbf16abc41a5954539062c`
- Status vocabulary: `status=BLOCKED`, handoff `READY_FOR_TIAGO_REVIEW`
- Official RFB-authority registry coverage: **0.0298** (683/22882)
- Operational supplier_registry coverage (incl. redistributor fallbacks): **1.0**
- Dossiers packaged: under `review-package/top20-dossiers/`
- Kits packaged: under `review-package/top5-outreach-kits/`
- No auto-send. Fill `user-acceptance.template.json` only if you accept.

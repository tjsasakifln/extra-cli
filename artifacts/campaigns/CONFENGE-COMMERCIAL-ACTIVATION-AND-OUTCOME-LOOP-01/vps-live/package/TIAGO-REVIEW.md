# Revisão humana — Tiago Sasaki

- Status do run: `BLOCKED` / `BLOCKED_INSUFFICIENT_HUMAN_LABELS`
- Handoff: `READY_FOR_TIAGO_REVIEW`
- Run ID: `cl-20260730T023737Z-c6f5d5d2`
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

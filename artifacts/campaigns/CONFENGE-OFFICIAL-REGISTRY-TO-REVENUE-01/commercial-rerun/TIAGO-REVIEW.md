# Revisão humana — Tiago Sasaki

- Status do run: `BLOCKED` / `BLOCKED_INSUFFICIENT_HUMAN_LABELS`
- Handoff: `READY_FOR_TIAGO_REVIEW`
- Run ID: `cl-20260730T201737Z-a35bd698`
- Leads na fila: 20
- commercial_release_ready: `False`
- Top10 gate ok: `True` (official_registry_failures=0)
- precision@10 / @20: `null` (somente após seus labels)

## O que revisar

1. Top 20 em `leads.json` / `commercial-review.csv`
2. Dossiers em `top20-dossiers/`
3. Kits manuais em `top5-outreach-kits/` (não enviar automaticamente)
4. Holdout de calibração em `holdout-review.json` (near_cut_n=10, excluded_negative_n=10)
5. Preencher `user-acceptance.template.json` apenas se aceitar

## Regras

- Somente você pode marcar ACCEPTED.
- Não use avaliações de agentes como label humano.
- Contatos ausentes são NOT_AVAILABLE — não inventar.
- Top10 exige cadastro **oficial RFB** resolvido (não só setor).

# Story — Desacoplar PNCP (ingestão) do plano comercial outbound

- **ID:** `current-pncp-outbound-decoupling-01`
- **Risco:** HIGH-RISK (systemd, deploy, gates de publicação)
- **Base:** `main` @ `e693f2ae` (#529 + #534)
- **Origem parcial:** PR #528 — tratado como `SUPERSEDED/PARTIALLY_REUSED`

## Problema

O plano comercial (qualificação, publicação, exportação, coorte, transporte) está
acoplado à saúde viva do PNCP por dois caminhos:

1. **systemd:** `pncp-contracts.service` → `OnSuccess=extra-confenge-source-freshness-gate.service`.
   O gate executa `pncp_contract_freshness --live --health`, que **retorna
   `health_exit != 0` quando o contrato não é `FRESH`**. Um `OnSuccess` só dispara
   em sucesso, portanto PNCP não-FRESH congela toda a cascata
   `gate → target-fit-reconcile → contact-cycle → feed-cycle`.
2. **código:** cinco pontos abortam com `ValueError`/`EXIT_FAIL` quando o contrato
   PNCP não é `FRESH`, mesmo havendo dado persistido válido no datalake.

Consequência: indisponibilidade/STALE/UNKNOWN de uma fonte de **aquisição** bloqueia
operação comercial sobre população já provada e persistida.

## Arquitetura desejada

```
PNCP live      = ingestão + telemetria assíncrona (não governa nada)
Datalake       = fonte operacional do outbound (fail-closed de verdade)
```

## Escopo IN

1. `pncp-contracts.service` vira ingestion-only (sem `OnSuccess`).
2. `extra-confenge-feed-cycle.timer` com cadência independente 4x/dia.
3. Remoção do bloqueio de freshness PNCP em:
   `confenge_outreach_pipeline/cli.py`, `confenge_activation/publish.py`,
   `warmbly_bridge/export.py`, `ops/build_controlled_email_cohort.py`,
   `confenge_outreach_pipeline/pipeline.py`.
4. Freshness PNCP permanece visível como telemetry/source health, sem fabricar `FRESH`.
5. Datalake indisponível, membership inválido, suppression/DNC, identidade ou binding
   inválidos continuam fail-closed.

## Escopo OUT (invariantes absolutos)

- **NÃO** adotar a população `COMMERCIAL_AUTHORITY/2.0` do #528
  (`commercial_authority_v2.py`, `rebuild_commercial_qualification.py`,
  `commercial_qualification_corpus`). A mudança de população comercial exige
  decisão separada.
- **NÃO** escrever `TARGET_CONFIRMED` como carimbo fabricado.
- Preservar a semântica de targeting vigente em `main` pós-#529, inclusive
  `parafiscal_institutional_hard_out`.
- Preservar a identidade oficial de contratos corrigida por #534.
- **NÃO** usar DNC/env pause como substituto de exclusão estrutural.
- **NÃO** mexer em SMTP/GO/kill switch.
- **NÃO** re-freezar artefatos nesta PR.

## Correção obrigatória sobre o #528

O #528 remove `OnSuccess` do PNCP mas mantém
`extra-confenge-target-fit-refresh.timer`, `...-reconcile.timer` e
`extra-confenge-contact-cycle.timer` em `CHAIN_DISABLED_TIMERS`. Sem o `OnSuccess`
e sem timer, **nada mais dispara target-fit e contatos** — a loja `published`
de target-fit congela. No #528 isso é irrelevante (a população passa a vir direto
da view V2); aqui seria fatal, porque a população continua sendo a loja target-fit.

Portanto esta PR também **habilita as cadências independentes** de refresh,
reconcile e contact-cycle, e quebra o `OnSuccess` gate→reconcile e
contact-cycle→feed-cycle.

## Critérios de aceite

- **AC1** — `Given` contrato PNCP `STALE`/`503` `And` datalake válido
  `When` o pipeline comercial roda `Then` qualificação, publicação, exportação e
  construção de coorte concluem, com `source_operational_health` registrado.
- **AC2** — `Given` contrato PNCP `FRESH` `When` o pipeline roda `Then` o
  comportamento (observação, watermark, `target_fit_observation_run_id`) permanece
  compatível com `main`.
- **AC3** — `Given` datalake indisponível/inválido (coverage < 1.0, missing
  inexplicado, paginação incompleta, fila não resolvida) `When` o pipeline roda
  `Then` falha fechada, independentemente da saúde do PNCP.
- **AC4** — regressão #529: as 9 raízes contidas e os hard-outs permanecem fora.
- **AC5** — regressão #534: `numeroControlePNCP`/`contrato_id` oficial sobrevive no feed.
- **AC6** — cohort builder aceita autoridade comercial válida com source health
  `STALE`/`UNKNOWN`.
- **AC7** — `pncp-contracts.service` e `extra-confenge-source-freshness-gate.service`
  não possuem nenhum `OnSuccess`; `extra-confenge-feed-cycle.timer` roda 4x/dia
  com `Persistent=true`.
- **AC8** — CI completo verde.

## Rollback

`git revert` do merge; restaurar `OnSuccess=extra-confenge-source-freshness-gate.service`
em `pncp-contracts.service` e `OnCalendar=*-*-* 01,13:20:00` no timer do feed;
`python3 deploy/confenge/pin_release.py apply --sha <sha anterior>`.

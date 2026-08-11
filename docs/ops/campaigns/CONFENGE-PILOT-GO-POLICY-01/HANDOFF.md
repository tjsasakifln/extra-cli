# HANDOFF — CONFENGE-PILOT-GO-POLICY-01

## Estado desta mudança

`READY_FOR_TIAGO_TO_ENABLE_PILOT`: uma coorte de 20 empresas reais foi
revalidada sobre contratos live, traduzida pelo bridge existente para
`confenge.outreach.v1` e importada no Warmbly. Os 20 contatos estão
`EMAIL_SEND_READY`; nenhuma aprovação humana foi fabricada (`approved=0`) e o
dispatch permanece pausado.

A amostra strict ESR antiga não é evidência de prontidão: ela produzia CNPJ
sintético e tratava documento público como autoria da empresa. Com validação
fail-closed, essa amostra cai de 71 para zero. A coorte do piloto vem da amostra
clean anterior, mas cada linha foi reidratada com CNPJ completo, identidade,
contratos live, contact ownership e service fit atuais.

Distribuição: 7 `apoio_licitacoes_propostas`, 6
`gestao_monitoramento_contratual`, 5 `auditoria_orcamento_bdi`, 1
`aditivos_extracontratuais` e 1 `reforco_temporario_backoffice`.

## Fluxo operacional

1. Revisar as 20 linhas de `HUMAN-REVIEW-SAMPLE.json` via
   `python -m scripts.confenge.human_review`; decisões atribuíveis são
   anexadas a `HUMAN-REVIEW-DECISIONS.jsonl`.
2. Aplicar somente as linhas aprovadas à campanha e autorizar o início manual.
   E-mail apenas, WhatsApp OFF, no máximo 10/h.

Não é necessário atingir reserva nacional 900 para este piloto. O universo
continua integral e reconciliado; escala nacional e prontidão do piloto são
decisões distintas.

## Provas operacionais em 2026-08-11

- Feed: run `run-7ade4a98377f5c1f`, 20 leads, todos ESR.
- Import aplicado: 20 updates, zero bloqueios/erros; segundo import: 20
  unchanged, demonstrando idempotência.
- Warmbly: 20/20 contatos da coorte presentes, zero DNC, bounce ou bloqueio;
  zero itens na fila e zero autorizações de envio.
- Outcome receptor: persistência PostgreSQL (sem `--memory-store`), HMAC e
  idempotência comprovados; quatro eventos distintos persistidos e 68 itens do
  outbox entregues ao receptor.
- Controles: `stop_on_reply=true`; casos live de reply-stop sem touch futuro;
  governor 10/h; kill switch engatado; dispatch pausado por operador.
- Transporte: conexões SMTP e IMAP e o self-smoke anterior passaram. SPF ainda
  não está publicado e DMARC está em `p=none`; é ressalva de reputação para o
  operador, não evidência suficiente para inventar entrega nem para liberar o
  dispatch automaticamente.

## Evidência pesada

Contagens live, listas de roots, decisões e linhas ESR pertencem ao host/Actions.
Somente a amostra operacional pequena, manifesto resumido, hashes e ponteiros
podem ser publicados no Git, conforme ADR-020. O envio continua proibido até a
decisão humana e a habilitação deliberada de Tiago.

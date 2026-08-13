# HANDOFF — CONFENGE-AUTHORITATIVE-OUTREACH-FEED-01

## Estado

`OPERATIONALLY_VERIFIED_DOD_ACCEPTANCE_PENDING`: o release integral foi gerado
pelo extra-cli no `main`, publicado, validado e sincronizado no Warmbly. A
seleção manual e o envio não foram executados; todos os bloqueios de envio
continuam ativos. Este estado não marca o item como `ACCEPTED` no `DOD.md`.

## Contrato operacional

- `confenge.outreach.v1` contém uma linha por CNPJ endereçável do universo
  reconciliado, inclusive exclusões e DNC.
- Toda linha carrega decisão target-fit completa e não nula.
- Ausência no snapshot vira `TARGET_FIT_MISSING` + tombstone; downgrade OUT
  permanece presente; ambos bloqueiam envio e impedem ressurreição.
- Ordem: source watermark, computed_at e CNPJ, ascendente.
- Importação só pode consumir manifest com `coverage_complete=true`,
  `watermarks_monotonic=true` e `omission_preserves_authorization=false`.
- A seleção strict ESR/piloto isolada é recusada como feed autoritativo.
- Timestamps de decisão são serializados em UTC RFC 3339 antes de ordenar,
  calcular hashes e gravar chunks.

## Release operacional

- commit do gerador: `d0ce84741eb12eb115a4bcf73a9fde73d8fd1cfa`;
- run: `run-0cd4121c646cb6d9`;
- snapshot: `a6c32643e67bcf2f9a1f3a8147d700a605de5de8934a078ddefb8308e8a03e5f`;
- manifesto SHA-256: `341052580fe737bb9a70e289825fa56ecd970fefa6c94080ff1332320db2b06a`;
- universo: 401.923 CNPJs únicos em 402 chunks, sem duplicatas;
- elegibilidade strict no feed: 32 contas e 32 contatos reais verificáveis;
- sincronização Warmbly: `completed`, 402/402 chunks e 32 contas elegíveis
  para seleção manual;
- manifesto contínuo: `https://159.195.18.88:8443/manifest.json`;
- release imutável:
  `https://159.195.18.88:8443/releases/run-0cd4121c646cb6d9-d0ce8474/manifest.json`.

Os 402 hashes de arquivo, os hashes canônicos de `leads+source`, o self-hash
do manifesto e o schema `confenge.outreach.v1` foram recalculados. Os mesmos
844.480.022 bytes de chunks foram relidos via HTTPS e comparados ao manifesto.

## Evidência reproduzível

```bash
python3 -m pytest tests/warmbly_bridge/test_authoritative_target_fit_feed.py -q
python3 -m pytest tests/confenge_outreach_pipeline/test_pipeline.py -q
python3 -m json.tool scripts/warmbly_bridge/schemas/confenge.outreach.v1.json
```

Os testes comprovam PREVENCAO como `14893700000105`, PREVENCAO e BEBA MAIS
OUT, SULPEL com evidência insuficiente, DNC/stale/missing inelegíveis e uma
engenharia `TARGET_CONFIRMED`, fresh e `email_send_ready=true`. Também executam
as sequências CONFIRMED→OUT e CONFIRMED→omissão, sem ressurreição.
O resumo sanitizado da regeneração, publicação, sincronização e gates está em
[`verification.json`](./verification.json).

Chunks operacionais permanecem fora do Git conforme ADR-020. O release foi
gerado pelo mesmo `main` que passou na CI. `CONFENGE_AUTO_SEND_ENABLED=false`,
`CONFENGE_GREEN_AUTORUN_ENABLED=false`, aprovação humana obrigatória,
`CONFENGE_SENDING_PAUSED=true` e o kill switch durável estavam ativos após o
sync. Nenhum destinatário foi selecionado e nenhum envio foi disparado.

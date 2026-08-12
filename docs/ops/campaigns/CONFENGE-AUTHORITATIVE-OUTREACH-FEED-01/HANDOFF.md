# HANDOFF — CONFENGE-AUTHORITATIVE-OUTREACH-FEED-01

## Estado

`IMPLEMENTED_PENDING_MAIN_AND_CI`: o exportador e o pipeline agora distinguem
hot set de enriquecimento do universo integral de decisões. Nenhum envio,
import ou habilitação de campanha faz parte desta mudança.

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
O resumo carimbado da regeneração, validação do schema e hashes está em
[`verification.json`](./verification.json).

Chunks operacionais regenerados permanecem fora do Git conforme ADR-020. O
manifest e os hashes devem corresponder ao mesmo HEAD que passou na CI antes de
qualquer importação futura.

# Runbook — autoridade comercial durável CONFENGE

O ciclo comercial é independente do crawler PNCP. Para confirmar a instalação:

```bash
systemctl is-enabled extra-confenge-feed-cycle.timer pncp-contracts.timer
systemctl is-active extra-confenge-feed-cycle.timer pncp-contracts.timer
systemctl show pncp-contracts.service -p OnSuccess --value
systemctl list-timers extra-confenge-feed-cycle.timer pncp-contracts.timer
```

O `OnSuccess` do serviço PNCP deve estar vazio. Uma execução comercial manual,
sem aguardar PNCP, é:

```bash
systemctl start extra-confenge-feed-cycle.service
journalctl -u extra-confenge-feed-cycle.service -n 200 --no-pager
```

O serviço adquire `/run/extra-confenge-feed/feed-cycle.lock`; concorrência é
recusada, nunca sobreposta. Sucesso exige corpus não vazio, hashes V2 fechando
contra os roots publicados e promoção atômica. Falha do datalake, view ausente,
evidência inválida/revogada/vencida ou divergência de membership deve falhar a
unit sem trocar `current`.

Falha PNCP deve aparecer apenas em `source_operational_health` e no journal do
ingestor. Ela não é incidente de publicação se a visão V2 persistida for válida.
DNC, supressão e falta de contato apto continuam podendo impedir transporte e
devem ser investigados no plano Warmbly, sem alterar a autoridade comercial.

Após um release imutável:

```bash
python3 -P deploy/confenge/pin_release.py "$SHA"
python3 -P deploy/confenge/pin_release.py "$SHA" --verify-only
systemctl start extra-confenge-feed-cycle.service
```

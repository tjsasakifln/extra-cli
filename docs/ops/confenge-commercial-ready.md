# CONFENGE Commercial Ready — runbook

## Ciclo canônico

```bash
export CONFENGE_COMMERCIAL_STATE_DSN=postgresql://confenge:confenge@127.0.0.1:5441/confenge_commercial
export CONFENGE_COMMERCIAL_SNAPSHOT=artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01/snapshot-manifest.json
make confenge-commercial-cycle
```

## Operador

```bash
python3 -m scripts.workspace commercial-leads --limit 20
python3 -m scripts.workspace commercial-lead 07192414000109 --explain
python3 -m scripts.workspace commercial-review 07192414000109 --status REVIEWED --reason "..."
```

## Gates

```bash
make campaign-gate-confenge-commercial-ready
make verify-soak-non-interference
make release-candidate-confenge-commercial-ready
```

## Separação Extra vs CONFENGE

- Extra: `config/client_profiles/extra.yaml` + `make extra-weekly`
- CONFENGE: `config/commercial_profiles/confenge.yaml` + `make confenge-commercial-cycle`

## Aceite humano

`artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01/user-acceptance.json` inicia como `PENDING_HUMAN`.
Somente Tiago pode marcar `ACCEPTED` com hashes do pacote.

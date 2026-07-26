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

## Gates (final hardening)

```bash
# Histórico integral (ALL_SNAPSHOT) vs portfólio ativo
make verify-confenge-all-status-history
make verify-confenge-active-vs-historical-separation

# Registry universe (antes do top20) + ingestão oficial
make ingest-confenge-official-cnpj-registry
make resume-confenge-registry-ingestion
make verify-confenge-registry-universe
make verify-confenge-registry-selection-independence

# Janela temporal STRONG (não rebaixa 180d)
make verify-confenge-historical-window

# Snapshot: export fecha âncora; validate nunca minta hash
make export-confenge-authenticated-snapshot
make verify-confenge-authenticated-snapshot
make verify-confenge-snapshot-manifest-immutability

# Holdout: smoke ≠ claim real
make test-confenge-contract-relevance-smoke
make evaluate-confenge-real-contract-holdout

# E2E, oferta, proveniência
make verify-confenge-end-to-end-reproducibility
make verify-confenge-offer-discrimination
make package-confenge-commercial-evidence
make verify-confenge-evidence-provenance

make campaign-gate-confenge-commercial-ready
make release-candidate-confenge-commercial-ready
```

Estado esperado até cobertura/registry/holdout/humano completos: **BLOCKED**
(ex.: `BLOCKED_REGISTRY_SELECTION_BIAS`, `BLOCKED_INSUFFICIENT_HISTORICAL_WINDOW`,
`BLOCKED_REAL_HOLDOUT_NOT_REVIEWED`, `BLOCKED_MISSING_INDEPENDENT_SNAPSHOT_ANCHOR`).

`FULL_CANDIDATE_HISTORY` só é válido com **todas** as situações contratuais do snapshot
(`ALL_SNAPSHOT_SUPPLIER_HISTORY`). Portfólio ativo é `ACTIVE_COMMERCIAL_PORTFOLIO` e
nunca é denominador histórico setorial.

## Separação Extra vs CONFENGE

- Extra: `config/client_profiles/extra.yaml` + `make extra-weekly`
- CONFENGE: `config/commercial_profiles/confenge.yaml` + `make confenge-commercial-cycle`

## Aceite humano

`artifacts/campaigns/CONFENGE-COMMERCIAL-READY-01/user-acceptance.json` inicia como `PENDING_HUMAN`.
Somente Tiago pode marcar `ACCEPTED` com hashes do pacote.

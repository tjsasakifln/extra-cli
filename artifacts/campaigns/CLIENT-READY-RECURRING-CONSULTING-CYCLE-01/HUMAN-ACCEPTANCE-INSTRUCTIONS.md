# Aceite humano do release candidate — Tiago

**Campanha:** `CLIENT-READY-RECURRING-CONSULTING-CYCLE-01`  
**PR:** https://github.com/tjsasakifln/extra-cli/pull/131  
**Pacote:** `artifacts/campaigns/CLIENT-READY-RECURRING-CONSULTING-CYCLE-01/pack/`

## O que revisar

| Artefato | Caminho |
|----------|---------|
| PDF executivo | `pack/executive-report.pdf` |
| Excel | `pack/consulting-pack.xlsx` |
| Sumário | `pack/executive-summary.md` |
| Apoio reunião | `pack/meeting-support.md` |
| A–E JSON | `pack/deliverable_*.json` |
| Dossiers | `dossiers/dossier-opp-*.json` |
| Reconciliação | `package-reconciliation.json` |
| Resultado | `result.json` (`final_status: BLOCKED` até aceite) |

## Como aceitar (somente humano real)

Editar `user-acceptance.json`:

```json
{
  "status": "ACCEPTED",
  "rc_sha": "<git rev-parse HEAD da branch>",
  "run_id": "live-pack-20260724-210500-96b1aa13",
  "package_checksums": { "...": "ver pack/checksums.json" },
  "accepted_by": "Tiago Sasaki",
  "accepted_at": "2026-07-24T…Z",
  "notes": "Pack revisado: A–E e linkage utilizáveis para consultoria Extra"
}
```

Depois reexecutar:

```bash
python3 -m scripts.ops.client_ready_consulting_cycle run \
  --dsn "$CLIENT_READY_DSN" \
  --out artifacts/campaigns/CLIENT-READY-RECURRING-CONSULTING-CYCLE-01
```

Se `status=ACCEPTED` com `accepted_by` humano válido e recorrência live ok, o terminal pode passar a `PASS`.

## Como rejeitar

```json
{
  "status": "REJECTED",
  "accepted_by": "Tiago Sasaki",
  "accepted_at": "…",
  "notes": "motivo concreto"
}
```

## Proibido

- Aceite preenchido por agente/auto/system
- Tratar CI verde como aceite
- Declarar `PASS` sem este arquivo

## Estado atual

`status: PENDING_HUMAN` — terminal da campanha: **BLOCKED**.

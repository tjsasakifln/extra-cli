# Runbook — verificação de freshness de contratos PNCP

Campanha: `CONFENGE-PNCP-PRODUCTION-FRESHNESS-CERTIFICATION-01`
Contrato: `PNCP_CONTRACT_FRESHNESS/1.0`
Host de record: `ec-prod` / `159.195.18.88` (`v2202607385716487230`)

Este runbook é idempotente. Não refaz backfill histórico. Não zera checkpoint.

## 1. Contrato local (sempre)

```bash
python3 -m scripts.ops.pncp_contract_freshness \
  --from-snapshot tests/fixtures/pncp_contract_freshness/host-2026-08-20.snapshot.json \
  --json --health
```

Exit: `0` FRESH, `1` DEGRADED, `2` STALE/UNKNOWN.

Repetir o mesmo comando. O JSON tem de ser consistente (`status` estável, `UNKNOWN` nunca vira `FRESH`).

## 2. Canário live no host (única ação externa se o agente não tiver SSH)

**Ação externa nomeada:** `ssh ec-prod` (alias em `~/.ssh/config`, host `159.195.18.88`).

```bash
ssh ec-prod 'bash -s' << 'EOF'
set -a
. /opt/extra-consultoria/.env
set +a
cd /opt/extra-consultoria
systemctl show pncp-contracts.timer pncp-contracts.service \
  -p ActiveState,UnitFileState,LastTriggerUSec,NextElapseUSec,Result,ExecMainStatus,ExecMainStartTimestamp --no-pager
python3 -m scripts.crawl.contracts_checkpoint_contract diagnose \
  --checkpoint-dir /var/lib/extra-consultoria/checkpoints/contracts
/opt/extra-consultoria/.venv/bin/python -m scripts.ops.pncp_contract_freshness --live --json --health
EOF
```

## 3. Paginação legal + spot-check PNCP → PostgreSQL

`tamanhoPagina` canónico de contratos: ≥ 10 e ≤ 500 (crawler: 50).

```bash
# página 1 de um dia recente (legal)
curl -sS "https://pncp.gov.br/api/consulta/v1/contratos?dataInicial=YYYYMMDD&dataFinal=YYYYMMDD&pagina=1&tamanhoPagina=50" \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["totalRegistros"], d["totalPaginas"], len(d["data"]), d["data"][0]["numeroControlePNCP"])'
```

No host, com o venv:

```bash
sudo -u extra-consultoria env LOCAL_DATALAKE_DSN="$LOCAL_DATALAKE_DSN" \
  /opt/extra-consultoria/.venv/bin/python -c \
  'import os,psycopg2; c=psycopg2.connect(os.environ["LOCAL_DATALAKE_DSN"]); cur=c.cursor();
cur.execute("select contrato_id, ingested_at, objeto_contrato from pncp_supplier_contracts where contrato_id=%s", ("NUMERO_CONTROLE",));
print(cur.fetchone())'
```

Ausência de um contrato publicado **depois** da última janela fechada é `UNCLOSED_CURRENT_WINDOW` (cadência Mon/Wed/Fri), não evidência de FRESH. Ausência **dentro** da janela fechada é gap com `reason_code`.

ZERO só é ZERO quando `pages_expected = pages_fetched` e a query terminou.

## 4. Checkpoint durável

Autoridade: `/var/lib/extra-consultoria/checkpoints/contracts/contracts_full.json`
Produção recusa Git/worktree (`scripts.contracts_truth.resolve_checkpoint_dir`).

Não apagar. Não `--reset-checkpoint` para “facilitar” teste. Interrupção controlada: SIGTERM num *attempt* de teste, nunca wipe.

## 5. Alertas

`extra-check-alerts.timer` chama `scripts/check-alerts.py`. No host (`/opt` + `/var/lib/extra-consultoria`) o check `check_pncp_contract_freshness` entra sozinho. STALE/UNKNOWN → exit 2; DEGRADED → exit 1.

## 6. O que este runbook não faz

- declarar `VPS_OPERATIONAL`
- iniciar soak #248 (ver `soak-prep.json`, `SOAK_STARTED_AT=NOT_STARTED`)
- reabrir #249 como redo de histórico
- reimplementar probes #351/#285/#341/#343 (PR #443)

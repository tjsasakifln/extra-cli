# Migração do backfill histórico local → VPS Netcup

**Data:** 2026-07-23  
**VPS:** `159.195.18.88` · `ssh ec-prod` · port **2222**  
**Origem local:** `postgresql://…@127.0.0.1:5433/extra_test` (PG **16**)  
**Destino:** `pncp_datalake` na VPS (PG **17**)

---

## Estado (preparação)

| Item | Local | VPS |
|------|-------|-----|
| Backfill 3y campanha | **RODANDO** PID + checkpoint `hc_closure_3y` | crawls PNCP **pausados** |
| `pncp_supplier_contracts` | ~3.3M · ~3.8 GB | schema ok · **0 rows** (pré-restore) |
| Disco | host livre | ~476 GB livre |
| Timers PNCP | n/a | `pncp-crawl-inc` / `extra-crawl-pncp` **disabled** |
| Health / backup timer | n/a | ativos |

Não declarar `VPS_OPERATIONAL` nem coverage 95% só com restore.

---

## Estratégia

1. **Não matar** o pilot local a menos que seja cutover final.  
2. Export snapshot (tabela + checkpoint) com `export_backfill_for_vps.sh`.  
3. Upload `rsync`/`scp` → `/var/lib/extra-consultoria/incoming/`.  
4. Restore data-only na VPS com `restore_backfill_on_vps.sh`.  
5. Se janelas faltarem: **resume** do pilot **só na VPS** (ou só no local — não os dois).  
6. Cutover final: parar local → re-export → restore → validar counts.

**Regra de ouro:** um único writer de contratos PNCP por vez (local **ou** VPS).

---

## Comandos

### 1) Export local

```bash
export LOCAL_DATALAKE_DSN=postgresql://test:test@127.0.0.1:5433/extra_test
bash scripts/ops/export_backfill_for_vps.sh
# package em artifacts/migration/backfill-vps/pkg-<UTC>/
```

### 2) Upload

```bash
# opção A
bash scripts/ops/export_backfill_for_vps.sh --upload

# opção B
rsync -avP artifacts/migration/backfill-vps/pkg-XXXX \
  ec-prod:/var/lib/extra-consultoria/incoming/
```

### 3) Restore na VPS

```bash
ssh ec-prod
bash /opt/extra-consultoria/scripts/ops/restore_backfill_on_vps.sh \
  /var/lib/extra-consultoria/incoming/pkg-XXXX
```

### 4) Resume janelas restantes (só se incompleto e local parado)

```bash
ssh ec-prod
source /root/.extra-pg-credentials
cd /opt/extra-consultoria
sudo -u extra-consultoria bash -lc "
  source .venv/bin/activate
  export LOCAL_DATALAKE_DSN='$LOCAL_DATALAKE_DSN'
  mkdir -p /var/lib/extra-consultoria/backfill
  python3 -u scripts/crawl/run_contracts_90d_pilot.py \
    --dsn \"\$LOCAL_DATALAKE_DSN\" \
    --days 1099 \
    --checkpoint-dir /var/lib/extra-consultoria/checkpoints/hc_closure_3y \
    --output-json /var/lib/extra-consultoria/backfill/live-3y.json \
    --allow-cross-run-resume
"
```

### 5) Validação

```bash
# counts iguais (manifest vs VPS)
ssh ec-prod "source /root/.extra-pg-credentials && psql \"\$LOCAL_DATALAKE_DSN\" -c 'SELECT count(*) FROM pncp_supplier_contracts;'"

# dual coverage só depois de projection + janelas 37/37
```

---

## O que é copiado

| Artefato | Conteúdo |
|----------|----------|
| `db/pncp_supplier_contracts.dump` | **bulk** histórico |
| `db/pncp_backfill_*.dump` | metadados de runs (se existirem) |
| `db/pipeline_*.dump` | watermarks/runs |
| `checkpoints/hc_closure_3y/` | resume de janelas 30d |
| `meta/export-manifest.txt` | counts + git + versões |
| `meta/SHA256SUMS` | integridade |

---

## Pós-migração (VPS)

- [ ] Counts batem com manifest (± deltas se local avançou)  
- [ ] Checkpoint instalado  
- [ ] Timers PNCP **permanecem off** até cutover + política de rate limit  
- [ ] Backup off-box configurado (não só snapshot SCP)  
- [ ] (Opcional) reimage Ubuntu 24.04 — requer reauth Netcup  
- [ ] Entity projection + dual gate (campanha STATUS)

---

## Anti-padrões

- ❌ Dois pilots (local + VPS) no mesmo tempo contra PNCP  
- ❌ `--reset-checkpoint` no restore/resume  
- ❌ Claim de 95% sem projection pós-3y completo  
- ❌ Commit de dumps/DSN no git (`artifacts/migration/` deve ficar gitignored se grande)

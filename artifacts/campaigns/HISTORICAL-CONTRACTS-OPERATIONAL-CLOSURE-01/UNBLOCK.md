# Desbloqueio da campanha HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01

**Resultado atual:** `BLOCKED`  
**SHA main com fundação:** `f25b96b` (PRs #124 + #125)

## Bloqueador 1 — OFFSITE_BACKUP_CREDENTIAL

### Observado (3x)

`BACKUP_STORAGE_BOX_SSH` em `/etc/backup-database.conf` está **EMPTY**.  
Backup local na VPS existe; **não** conta como off-site.

### Ação do operador (Tiago)

1. Obter Storage Box (Hetzner) ou destino SSH off-site equivalente.
2. Na VPS (`ssh ec-prod`), editar **somente no host**:

```bash
# /etc/backup-database.conf  (NÃO commitar)
BACKUP_STORAGE_BOX_SSH=uXXXXXX@uXXXXXX.your-storagebox.de
BACKUP_MOUNT_POINT=/mnt/storage-box
BACKUP_REMOTE_DIR=backups/postgresql
```

3. Garantir chave SSH autorizada no Storage Box e montagem:

```bash
mkdir -p /mnt/storage-box
# montar conforme docs/ops/backup.md (sshfs)
```

4. Rodar backup real:

```bash
/usr/local/bin/backup-database.sh   # ou systemctl start extra-db-backup.service
```

5. Teste de desbloqueio:

```bash
cd /opt/extra-consultoria
python3 -m scripts.ops.campaign_offsite_backup_status
# esperado: status=ok (ou configured com verify de transfer)
```

6. Restore a partir do pacote off-site em DB separado (além do drill local já feito).

## Bloqueador 2 — SOAK_7D_IN_PROGRESS

### Observado

- Timer: `extra-contracts-soak.timer` **active**, `OnCalendar=daily`
- Observação dia 1: `2026-07-23` health_ok, freshness ~22h, contracts_count=4438393
- Faltam 6 dias calendário **reais** (não fabricáveis)

### Ação

Deixar o timer rodar. A cada dia (ou após 7 dias):

```bash
# no laptop com ssh ec-prod configurado, no repo:
python3 -m scripts.ops.campaign_soak_tracker --campaign HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01
# soak.json.complete deve ficar true com 7 dias consecutivos
```

## Após desbloquear ambos

```bash
git checkout main && git pull
python3 -m scripts.ops.campaign_verify_production \
  --campaign HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01 \
  --output artifacts/campaigns/HISTORICAL-CONTRACTS-OPERATIONAL-CLOSURE-01/verify-production.json
# se status=pass:
# - atualizar result.json para PASS
# - aceitar itens DOD sequencialmente via tools/dod_controller.py
```

## Já comprovado (não reabrir sem regressão)

| Gate | Prova |
|------|--------|
| Backfill 37/37 | checkpoint + live-3y success |
| Cutover VPS | cutover.json, 4437142 match |
| Dual 100% | dual-coverage.json PASS |
| Incremental VPS | journal pncp-contracts success |
| Separate-DB restore | restore.json RTO 645s |
| PG restart recovery | recovery.json |
| Produto VPS | consulting-package-vps-meta.json |
| CI main | PRs #124, #125 merged |

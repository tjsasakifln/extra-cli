# EXTRA-002 — política de recuperação (DB + blobs)

**DECISION-ID:** `PREAPPROVED-EXTRA-002-2026-08-17`  
**Owner:** CONFENGE owner  
**Veredito:** APROVADO SOB CONDIÇÕES (`CONDITIONAL_OFFSITE_EXECUTE`)  
**`VPS_OPERATIONAL`:** não declarado.

## Alvos

| Item | Valor aprovado |
|------|----------------|
| RPO máximo | 24 h |
| RTO máximo | 8 h |
| Retenção | 14 diários + 8 semanais + 12 mensais |
| Restore formal | trimestral |
| Destino | Netcup Storagespace NFS já provisionado (`46.38.248.210`, volume `voln1116040a1`) |
| Criptografia | AES-256-CBC (openssl) + HMAC-SHA256 no pacote conjunto |
| Versionamento | prefixo lógico `backups/extra-002/` no volume existente |
| Purge | proibido até dois restores verdes |

A VPS é hop SSH, não destino. Disco local da VPS não é off-site. Nenhum plano novo.

## Chave de cifra (off-VPS)

A chave AES **não** mora em `restore-root` nem no pacote. Ela é persistida no vault já usado (`~/.config/extra-consultoria/joint-offsite.key` / `EXTRA_JOINT_KEY_FILE`) e, no push, como sidecar off-site `backups/extra-002/sidecar/joint.key`. Restore após perda da VPS usa só o pacote NFS + essa chave off-VPS.

`assemble` copia o dump `pg_dump` mais recente e blobs CAS reais para `joint-src`. Recusa fixture ASCII (`PGDUMP-…`).

## Recorrência

O timer `extra-joint-offsite-backup.timer` permanece **desabilitado** até:

1. restore isolado com `hash_identical=true`;
2. merge + deploy do código;
3. `systemctl enable` explícito após o deploy.

Código recusa `recurrence.enabled=true` sem o arquivo de prova.

## Relatório por execução

Cada `python3 -m scripts.ops.backup_integrity joint` emite JSON com `version`, `duration_s`, `bytes`, `object_count`, alertas e `vps_operational_claimed=false`. Falha de blob/backup marca o job como `failed`.

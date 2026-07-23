# Acesso VPS Produção — Extra Consultoria

> Folha de acesso à infraestrutura de produção.  
> **Versão:** 3.0 — 2026-07-23 (Netcup RS 2000 G12 · MNZ)  
> **Responsável:** @devops (Gage)

## Status

| Campo | Valor |
|-------|--------|
| Provedor | **Netcup** |
| SKU | RS 2000 G12 · IPv4 · Manassas (MNZ) |
| Host | **159.195.18.88** (`v2202607385716487230.happysrv.de`) |
| SO | **Debian 13 (trixie)** — Ubuntu 24.04 reimage pendente reauth CCP |
| Estado | **SERVER_UP** — inventário: `docs/ops/netcup-inventory-live.md` |

Ativação: `docs/ops/netcup-phase0-activate.md`  
Provision: `deploy/provision-vps.sh` (`HARDWARE_PROFILE=rs2000-16g`)

---

## Acesso SSH

| Campo | Valor |
|-------|-------|
| **Host** | `159.195.18.88` |
| **Porta (bootstrap)** | `22` (ainda no UFW; remover após estabilidade) |
| **Porta (pós-harden)** | **`2222`** (ativa) |
| **Usuário bootstrap** | `root` (chave) |
| **Usuário app** | `extra-consultoria` (chave) |
| **Autenticação** | Chave SSH ed25519 — senha desabilitada após harden |
| **Chave local** | `~/.ssh/extra-consultoria-prod` |

### Configuração `~/.ssh/config` (recomendado)

**Antes do harden:**

```sshconfig
Host ec-prod
    HostName 159.195.18.88
    Port 2222
    User root
    IdentityFile ~/.ssh/extra-consultoria-prod
    IdentitiesOnly yes
```

**Depois de validar user app (opcional):**

```sshconfig
Host ec-prod
    HostName 159.195.18.88
    Port 2222
    User extra-consultoria
    IdentityFile ~/.ssh/extra-consultoria-prod
    IdentitiesOnly yes
```

```bash
ssh ec-prod
```

### Gerar chave (laptop)

```bash
ssh-keygen -t ed25519 -f ~/.ssh/extra-consultoria-prod -C "extra-prod@$(hostname)"
ssh-copy-id -i ~/.ssh/extra-consultoria-prod.pub root@{VPS_IP}
```

---

## Console do provedor (emergência)

### Netcup (ativo)

1. https://www.customercontrolpanel.de/ — localizar o Root Server  
2. Abrir **Server Control Panel (SCP)**  
3. **VNC / Console** para acesso sem SSH  
4. **Snapshots** — restaurar imagem se o SO quebrar  
5. Reinstall Ubuntu 24.04 se recovery for mais barato que debug

### Hetzner (histórico / fallback)

1. https://console.hetzner.cloud/  
2. Rescue System + VNC — ver versões antigas desta doc no git

---

## Credenciais (sem secrets no git)

| Serviço | Host | User | Método |
|---------|------|------|--------|
| SSH | `{VPS_IP}:2222` | `root` / `extra-consultoria` | Chave SSH |
| PostgreSQL | `127.0.0.1:5432` | `postgres` | Vault + `/root/.extra-pg-credentials` (apagar após copiar) |
| Backup remoto | conforme `/etc/backup-database.conf` | backup key em `/opt/extra-consultoria/backup-ssh/` | SSH/SFTP |
| Netcup CCP/SCP | customercontrolpanel.de / SCP | e-mail conta | senha vault |

---

## Backups

| Item | Localização | Frequência | Notas |
|------|-------------|------------|-------|
| Snapshot SCP | Netcup | diário ou pré-mudança | **não** substitui dump off-site |
| Dump PostgreSQL | destino em `BACKUP_*` | timer `extra-db-backup` | 7 diários / 4 semanais |
| Restore drill | DB de teste | após 1º dump | obrigatório DoD §22 |

---

## Monitoramento (comandos)

```bash
ssh ec-prod "systemctl list-timers --all | grep -E 'extra|pncp|coverage'"
ssh ec-prod "journalctl -u extra-health-check.service --no-pager -n 20"
ssh ec-prod "journalctl -u pncp-crawl-inc.service --no-pager -n 30"
ssh ec-prod "journalctl -u extra-crawl-pncp.service --no-pager -n 30"
ssh ec-prod "df -h /; free -h; uptime"
ssh ec-prod "sudo ufw status verbose"
ssh ec-prod "sudo systemctl status postgresql --no-pager"
```

---

## Emergency procedures

### Perda de acesso SSH

1. CCP → SCP → **VNC console**  
2. Login root (senha SCP ou single-user se souber)  
3. Corrigir `/etc/ssh/sshd_config` / `sshd_config.d/99-extra-consultoria.conf`  
4. `ufw allow 2222/tcp` (ou 22)  
5. `systemctl restart ssh`  
6. Se irrecuperável: restaurar **snapshot** ou reinstall Ubuntu + re-rodar `provision-vps.sh`

### Restore de backup

```bash
# Listar dumps no mount remoto
ls -lh /mnt/backup-remote/backups/postgresql/daily/

# Restaurar (script do repo)
sudo /usr/local/bin/restore-database.sh /mnt/backup-remote/backups/postgresql/daily/pncp_datalake-*.dump.gz
```

---

## Política

- Nenhum agente de IA/IDE é dependência operacional na VPS (DoD §17).  
- PostgreSQL **nunca** exposto na internet.  
- Não commitar IP real, senhas ou DSN no repositório.

---

> **Última atualização:** 2026-07-23  
> **Responsável:** @devops (Gage)

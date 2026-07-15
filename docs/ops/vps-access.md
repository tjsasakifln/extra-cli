# Acesso VPS Producao — Extra Consultoria

> Folha de acesso a infraestrutura de producao.
> **Versão:** 2.0 — 2026-07-15 (provider-agnostic)
> **Story original:** FEAT-4.1 — Provisionar Hetzner VPS
> **Responsavel:** @devops (Gage)

## Nota

O provedor de nuvem ainda não está definido. Os exemplos abaixo usam Hetzner como referência da implementação atual, mas os princípios de acesso (SSH key-only, non-root, firewall) são válidos para qualquer provedor.
Ver `docs/architecture/adr/ADR-007-cloud-hosting-strategy.md`.

## Acesso SSH

| Campo | Valor |
|-------|-------|
| **Host** | `{VPS_IP}` ou `{vps-hostname}.extra-consultoria.internal` |
| **Porta** | `2222` |
| **Usuario** | `root` (chave) ou `extra-consultoria` (chave) |
| **Autenticacao** | Chave SSH (ed25519) — senha desabilitada |
| **Chave** | `~/.ssh/extra-consultoria-prod` |

### Conectar

```bash
ssh -p 2222 -i ~/.ssh/extra-consultoria-prod root@{VPS_IP}
```

### Configuracao ~/.ssh/config (recomendado)

```bash
Host ec-prod
    HostName {VPS_IP}
    Port 2222
    User extra-consultoria
    IdentityFile ~/.ssh/extra-consultoria-prod
    IdentitiesOnly yes
```

Conectar:

```bash
ssh ec-prod
```

## Console do Provedor

Acesso de emergencia (rescue mode) via console web do provedor contratado.

### Hetzner (implementação atual)

1. https://console.hetzner.cloud/
2. Projeto: Extra Consultoria
3. Servidor: `extra-consultoria`
4. Aba "Rescue" → iniciar Linux Rescue System
5. Conectar via VNC no console web

## Credenciais

| Servico | Host | User | Metodo |
|---------|------|------|--------|
| SSH | `{VPS_IP}:2222` | `root` / `extra-consultoria` | Chave SSH |
| PostgreSQL | `localhost:5432` | `postgres` | Senha em `/etc/backup-database.conf` |
| Storage Box | `{username}.your-storagebox.de:23` | `{username}` | Chave SSH dedicada |
| Hetzner Cloud | console.hetzner.cloud | Seu email | API Token ou senha |
| Hetzner Robot | robot.hetzner.com | Seu email | Senha (para Storage Box) |

## Backups

| Item | Localizacao | Frequencia | Retencao |
|------|-------------|------------|----------|
| Dump PostgreSQL | Storage Box `backups/postgresql/daily/` | 06:00 UTC | 7 diarios |
| Dump semanal | Storage Box `backups/postgresql/weekly/` | Domingos | 4 semanais |

## Monitoramento

| Item | Comando |
|------|---------|
| Health check | `journalctl -u extra-health-check.service --no-pager -n 10` |
| Timers ativos | `systemctl list-timers 'extra-*'` |
| Backup | `tail -20 /var/log/backup-database.log` |
| Crawl status | `journalctl -u extra-crawl-pncp.service --no-pager -n 30` |

## Service Status Commands

```bash
# Verificar todos os timers
systemctl list-timers 'extra-*'

# Status de um servico
systemctl status extra-crawl-pncp.service

# Logs de um servico (ultimos 30)
journalctl -u extra-crawl-pncp.service --no-pager -n 30

# Logs em tempo real
journalctl -u extra-crawl-pncp.service -f

# Firewall
ufw status verbose

# PostgreSQL
systemctl status postgresql

# Disco
df -h /

# Memoria
free -h
```

## Emergency Procedures

### Perda de acesso SSH

Se o firewall bloquear SSH ou a configuracao estiver incorreta:

1. Acesse https://console.hetzner.cloud/
2. Selecione o servidor `extra-consultoria`
3. Aba "Rescue" → "Enable Rescue System"
4. Selecione "linux64" como tipo de rescue
5. Clique "Enable Rescue System and reboot"
6. Apos reboot, conecte via web console
7. Monte o sistema: `mount /dev/sda1 /mnt`
8. Corrija config: `nano /mnt/etc/ssh/sshd_config`
9. Reboot: `reboot`

### Restore de backup

```bash
# Listar backups disponiveis
ls -lh /mnt/storage-box/daily/

# Restaurar o mais recente
/usr/local/bin/restore-database.sh /mnt/storage-box/daily/pncp_datalake-*.dump.gz

# Verificar dados
psql -d pncp_datalake -c "SELECT count(*) FROM sc_public_entities"
```

---

> **Ultima atualizacao:** 2026-07-11
> **Responsavel:** @devops (Gage)

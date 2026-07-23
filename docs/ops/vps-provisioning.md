# Provisionamento de VPS — Extra Consultoria

> Documentação de provisionamento da infraestrutura de produção.  
> **Versão:** 3.0 — 2026-07-23 (Netcup RS 2000 G12 · MNZ)  
> **Responsável:** @devops (Gage)

## Aviso

Provedor **ativo:** Netcup Root Server. Scripts e runbooks são provider-agnostic onde possível.  
Seções Hetzner abaixo são **registro histórico** (CX22 subdimensionado).

**Ferramenta canônica atual:** `deploy/provision-vps.sh` (bash idempotente o quanto possível).  
Ansible/OpenTofu permanecem como evolução (ADR-008), sem playbooks no repo nesta onda.

Ver: `docs/architecture/adr/ADR-007-v6.1-provider-decision.md`,  
`docs/ops/v6.2-procurement-credentials-package.md`,  
`docs/ops/netcup-phase0-activate.md`.

## Sumário

- [Dimensionamento](#dimensionamento)
- [SKU em contratação](#sku-em-contratação)
- [Provisionamento](#provisionamento)
- [Systemd Timers](#systemd-timers)
- [Backup](#backup)
- [Firewall](#firewall)
- [Manutenção](#manutencao)
- [Troubleshooting](#troubleshooting)
- [Histórico Hetzner](#histórico-hetzner-cx22)

## Dimensionamento

| Recurso | Mínimo ADR | Alvo ADR | **Contratado (RS 2000)** |
|---------|------------|----------|---------------------------|
| RAM | 16 GB | 32 GB | **16 GB** |
| CPU | 4 vCPU | 8 dedicados | **8 dedicados** |
| Disco | 250 GB NVMe | ~1 TB | **512 GB NVMe** |
| PostgreSQL | 16 | 16 | 16 (pacote Ubuntu) |
| SO | Ubuntu 24.04 LTS | 24.04 | 24.04 |
| Swap | 4 GB | 8 GB | **4 GB** (script) |

Região: **Manassas (MNZ)** — preferência US-East do ADR. Teste PNCP obrigatório pós-boot.

## SKU em contratação

| Item | Valor |
|------|--------|
| Provedor | Netcup |
| Plano | RS 2000 G12 + IPv4 |
| DC | MNZ |
| Console | SCP (VNC + snapshots) |
| Upgrade | CCP → RS 4000 se RAM/disco apertarem |
| Ativação | `docs/ops/netcup-phase0-activate.md` |

## Provisionamento

### Método canônico: script bash

**Pré-requisitos:** Ubuntu 24.04, root com **authorized_keys** já instalada.

```bash
# Do laptop
scp deploy/provision-vps.sh root@<VPS_IP>:/root/
ssh root@<VPS_IP>

export HARDWARE_PROFILE=rs2000-16g
export ENABLE_TIMERS=minimal    # none | minimal | full
export REPO_URL=https://github.com/tjsasakifln/extra-consultoria.git
# export SKIP_SSH_HARDEN=1     # se quiser endurecer SSH depois
bash /root/provision-vps.sh
```

O script:

1. Pacotes + timezone + swap  
2. User `extra-consultoria`  
3. UFW (22 + 2222)  
4. SSH key-only porta 2222 (recusa se não houver chave root)  
5. fail2ban  
6. PostgreSQL localhost + tuning 16 GB  
7. Clone repo + venv + deps  
8. Migrations  
9. Timers em onda (`minimal` por default)  
10. Skeleton de backup off-box  
11. unattended-upgrades  

Credenciais PG: `/root/.extra-pg-credentials` (0600) — copiar para vault e apagar.

### Ansible / OpenTofu

Planejados (ADR-008). **Não** bloquear provision Netcup aguardando IaC.

### Histórico Hetzner CX22

Ver [seção no fim](#histórico-hetzner-cx22). **Não usar** CX22 4 GB para produção atual.

## PostgreSQL tuning (RS 2000 · 16 GB)

Aplicado por `HARDWARE_PROFILE=rs2000-16g` em `deploy/provision-vps.sh`:

| Parâmetro | Valor |
|-----------|--------|
| shared_buffers | 4GB |
| effective_cache_size | 12GB |
| work_mem | 32MB |
| maintenance_work_mem | 512MB |
| max_parallel_workers | 4 |

Para upgrade futuro RS 4000: `HARDWARE_PROFILE=rs4000-32g` (8GB / 24GB shared/cache).

## Systemd Timers

### Ondas de ativação (obrigatório no RS 2000)

| Onda | `ENABLE_TIMERS` | Timers |
|------|-----------------|--------|
| **A (dia 1)** | `minimal` | `extra-health-check`, `extra-db-backup`, `pncp-crawl-inc`, `extra-crawl-pncp`, metrics/alerts |
| **B** | manual enable | CIGA/CKAN, SC Compras, coverage |
| **C** | `full` | restante (DOE, selenium, contracts, …) só com A+B estável |

Não usar `ENABLE_TIMERS=full` no primeiro boot.

### Mapa (referência — nomes reais em `deploy/systemd/`)

| Timer | Função típica |
|-------|----------------|
| `pncp-crawl-inc` / `extra-crawl-pncp` | PNCP incremental |
| `pncp-crawl-full` | PNCP full (onda C) |
| `extra-crawl-ciga-ckan` | DOM/CIGA |
| `extra-crawl-sc-compras` | SC Compras |
| `extra-db-backup` | dump diário |
| `extra-health-check` | health |
| `coverage-report` | cobertura |

Schedules exatos: ler cada `.timer` em `deploy/systemd/`.

### OnFailure Template

O template `extra-onfailure@.service` e referenciado por todos os servicos.
Em caso de falha, executa um webhook configurado via `WEBHOOK_URL` no `.env`:

```ini
[Service]
ExecStart=/usr/bin/curl -sf --max-time 10 -X POST \
  -H "Content-Type: application/json" \
  -d '{"service":"%i","host":"%H","project":"extra-consultoria","status":"failed"}' \
  "${WEBHOOK_URL}"
```

## Backup

### Aviso

Snapshots do SCP Netcup **não** substituem dump PostgreSQL off-box.  
Estratégia: provider-agnostic (`docs/ops/backup.md`). Hetzner Storage Box é só exemplo histórico.

Opções ativas para Netcup:

| Opção | Destino |
|-------|---------|
| A | Storage/SFTP Netcup (se contratado no CCP) |
| B | rsync/SFTP para host/NAS controlado por Tiago |
| C | S3-compatible (B2/R2/Wasabi) |
| D | volume extra no mesmo DC (pior: risco correlacionado) |

Config gerada em `/etc/backup-database.conf`. Chave: `/opt/extra-consultoria/backup-ssh/id_ed25519.pub`.

### Histórico Hetzner Storage Box

A Storage Box Hetzner (BX11) era montada via sshfs:

```bash
# Gerar chave SSH dedicada
ssh-keygen -t ed25519 -f /root/.ssh/storage_box -N ""
cat /root/.ssh/storage_box.pub
# → Adicionar no Hetzner Robot

# Configurar acesso SSH
cat >> /root/.ssh/config << 'EOF'
Host storagebox
    HostName u000000.your-storagebox.de
    Port 23
    User u000000
    IdentityFile /root/.ssh/storage_box
EOF

# Montar
mkdir -p /mnt/storage-box
sshfs -p 23 -o reconnect,ServerAliveInterval=15,ServerAliveCountMax=3 \
  u000000@u000000.your-storagebox.de:backups/postgresql \
  /mnt/storage-box
```

### Configuracao via fstab (automontagem)

```bash
# /etc/fstab
sshfs#u000000@u000000.your-storagebox.de:backups/postgresql /mnt/storage-box fuse user,_netdev,reconnect,port=23,ServerAliveInterval=15,ServerAliveCountMax=3,idmap=user,transform_symlinks,identityfile=/root/.ssh/storage_box,allow_other,default_permissions 0 0
```

## Firewall

Regras ativas de producao:

| Porta | Protocolo | Servico | Origem |
|-------|-----------|---------|--------|
| 2222 | TCP | SSH | Any |
| 9100 | TCP | Prometheus node exporter | Any (monitoring) |
| 5432 | TCP | PostgreSQL | localhost apenas (bloqueado por ufw) |

Verificacao:

```bash
ufw status verbose
```

## Manutencao

### Rotina Diaria

```bash
# Verificar health check
journalctl -u extra-health-check.service --no-pager -n 10

# Verificar timers ativos
systemctl list-timers 'extra-*'

# Verificar backup
tail -5 /var/log/backup-database.log
```

### Rotina Semanal

```bash
# Verificar espaco em disco
df -h /

# Verificar Storage Box
ls -lh /mnt/storage-box/daily/

# Verificar logs do PostgreSQL
journalctl -u postgresql --no-pager --since "7 days ago" | grep -i error | tail -20

# Verificar status do fail2ban
fail2ban-client status sshd
```

### Rotina Mensal

```bash
# Testar restore do backup
/usr/local/bin/restore-database.sh /mnt/storage-box/daily/$(ls -t /mnt/storage-box/daily/ | head -1) --list | head -20

# Verificar updates pendentes
apt list --upgradable

# Verificar integridade dos backups
for f in /mnt/storage-box/daily/*.dump.gz; do
    gzip -t "$f" && echo "$(basename $f): OK" || echo "$(basename $f): CORROMPIDO"
done
```

## Troubleshooting

### Problema: PostgreSQL nao inicializa

```bash
# Verificar logs
journalctl -u postgresql --no-pager -n 50

# Verificar config
pg_lsclusters

# Tentar start manual
systemctl start postgresql
```

### Problema: Storage Box nao monta

```bash
# Testar conexao SSH
ssh -p 23 u000000@u000000.your-storagebox.de

# Verificar chave
ssh -p 23 -i /root/.ssh/storage_box u000000@u000000.your-storagebox.de

# Montar manual com verbose
sshfs -p 23 -o reconnect,debug -o IdentityFile=/root/.ssh/storage_box \
  u000000@u000000.your-storagebox.de:backups/postgresql \
  /mnt/storage-box -o sshfs_debug
```

### Problema: Systemd timer nao executa

```bash
# Verificar status
systemctl status extra-crawl-pncp.timer

# Verificar ultimas execucoes
journalctl -u extra-crawl-pncp.service --no-pager -n 30

# Trigger manual
systemctl start extra-crawl-pncp.service
```

### Problema: Disco cheio

```bash
# Identificar diretorios grandes
du -sh /* 2>/dev/null | sort -rh | head -10

# Logs do journald (ocupam muito)
journalctl --disk-usage
sudo journalctl --vacuum-size=500M

# Backups antigos (se Storage Box desmontada)
find /opt/extra-consultoria/ -name "*.dump*" -delete
```

---

> **Ultima atualizacao:** 2026-07-15 (desacoplado de Hetzner como baseline)
> **Story original:** FEAT-4.1 — Provisionar Hetzner VPS
> **Responsavel:** @devops (Gage)

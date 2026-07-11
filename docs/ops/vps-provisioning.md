# Provisionamento VPS Hetzner — Extra Consultoria

> Documentacao de provisionamento da infraestrutura de producao.
> **Story:** FEAT-4.1 — Provisionar Hetzner VPS
> **Responsavel:** @devops (Gage)

## Sumario

- [Especificacao Tecnica](#especificacao-tecnica)
- [Provisionamento Rapido](#provisionamento-rapido)
- [Passo a Passo Manual](#passo-a-passo-manual)
- [Systemd Timers](#systemd-timers)
- [Storage Box](#storage-box)
- [Firewall](#firewall)
- [Manutencao](#manutencao)
- [Troubleshooting](#troubleshooting)

## Especificacao Tecnica

| Item | Especificacao |
|------|---------------|
| **Plano** | Hetzner CX22 (2 vCPU, 4 GB RAM, 40 GB SSD) |
| **SO** | Ubuntu 24.04 LTS |
| **Regiao** | Nuremberg (nbg1-dc3) |
| **Storage Box** | BX11 (100 GB) |
| **Custo estimado** | ~EUR 7,40/mes (~R$ 45/mes) |
| **Traffic** | 20 TB/mes (CX22) |

### Custo Detalhado

| Item | Custo (EUR/mes) |
|------|-----------------|
| CX22 (2 vCPU, 4 GB RAM, 40 GB) | 4,49 |
| BX11 Storage Box (100 GB) | 2,90 |
| IP extra (se necessario) | 1,50 |
| **Total** | **~7,39 - 8,89** |

## Provisionamento Rapido

### Metodo 1: Script automatico (recomendado)

Apos boot da VPS, execute como root:

```bash
# SSH na VPS
ssh root@<IP_DA_VPS>

# Baixar e executar script de provisionamento
bash <(curl -fsSL https://raw.githubusercontent.com/extra-consultoria/main/deploy/provision-vps.sh)
```

### Metodo 2: Hetzner Cloud API (automatizado)

Requer `hcloud` CLI instalado e API token configurado:

```bash
# Instalar hcloud CLI
# https://community.hetzner.com/tutorials/howto-hcloud-cli

# Configurar token
export HCLOUD_TOKEN="seu-token-aqui"

# Criar VPS
hcloud server create \
  --name extra-consultoria \
  --type cx22 \
  --image ubuntu-24.04 \
  --location nbg1 \
  --ssh-key ~/.ssh/id_ed25519.pub \
  --enable-ipv4 \
  --enable-ipv6

# Criar Storage Box via Hetzner Robot (web console apenas)
# https://robot.hetzner.com/storagebox
```

### Metodo 3: Hetzner Console (manual)

1. Acesse https://console.hetzner.cloud/
2. Crie projeto "Extra Consultoria"
3. Crie servidor: CX22, Ubuntu 24.04, nbg1
4. Adicione sua chave SSH
5. Apos boot, execute o script de provisionamento

## Passo a Passo Manual

### 1. System Packages

```bash
apt-get update && apt-get upgrade -y
apt-get install -y python3 python3-pip python3-venv postgresql postgresql-client \
  sshfs gzip curl wget git ufw fail2ban htop unattended-upgrades
```

### 2. PostgreSQL

```bash
# Configurar para ouvir apenas localhost
sed -i "s/^#listen_addresses = 'localhost'/listen_addresses = 'localhost'/" /etc/postgresql/*/main/postgresql.conf

# Tuning para CX22 (2 vCPU, 4 GB RAM)
cat >> /etc/postgresql/*/main/postgresql.conf << 'EOF'
shared_buffers = 1GB
effective_cache_size = 2GB
work_mem = 64MB
maintenance_work_mem = 256MB
random_page_cost = 1.1
effective_io_concurrency = 200
wal_buffers = 16MB
max_parallel_workers = 2
max_parallel_workers_per_gather = 2
EOF

systemctl restart postgresql

# Criar database
sudo -u postgres createdb pncp_datalake
sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'SENHA_SEGURA'"
```

### 3. Clone e Deploy

```bash
# Criar usuario de aplicacao
useradd -m -s /bin/bash extra-consultoria

# Clonar repositorio
git clone https://github.com/extra-consultoria/extra-consultoria.git /opt/extra-consultoria
cd /opt/extra-consultoria
chown -R extra-consultoria:extra-consultoria /opt/extra-consultoria

# Dependencias Python
pip3 install -r requirements.txt

# Migrations e seeds
bash db/setup_db.sh postgresql://postgres:SENHA@localhost:5432/pncp_datalake
```

### 4. Systemd Timers

```bash
# Copiar arquivos
cp deploy/systemd/*.service /etc/systemd/system/
cp deploy/systemd/*.timer /etc/systemd/system/
systemctl daemon-reload

# Habilitar todos os timers
for timer in extra-crawl-pncp extra-crawl-dom-sc extra-crawl-pcp \
  extra-crawl-compras-gov extra-crawl-tce-sc extra-crawl-doe-sc \
  extra-crawl-transparencia extra-crawl-contracts extra-coverage-report \
  extra-panorama-weekly extra-db-backup extra-db-purge extra-health-check; do
  systemctl enable "${timer}.timer"
  systemctl start "${timer}.timer"
done

# Verificar
systemctl list-timers 'extra-*'
```

### 5. SSH Hardening

```bash
# Editar /etc/ssh/sshd_config
Port 2222
PermitRootLogin without-password
PasswordAuthentication no

systemctl restart sshd
```

### 6. Firewall

```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow 2222/tcp comment "SSH custom port"
ufw --force enable
```

## Systemd Timers

### Mapa de Timers (13 pares)

A tabela abaixo mapeia cada servico ao seu script correspondente:

| Timer | Schedule (UTC) | Script | Frequencia |
|-------|----------------|--------|------------|
| `extra-crawl-pncp` | 02:00 | `monitor.py --source pncp --mode full` | Diario |
| `extra-crawl-dom-sc` | 06:00, 14:00, 22:00 | `monitor.py --source dom_sc --mode full` | 3x/dia |
| `extra-crawl-pcp` | 06:30, 14:30 | `monitor.py --source pcp --mode full` | 2x/dia |
| `extra-crawl-compras-gov` | 07:00 | `monitor.py --source compras_gov --mode full` | Diario |
| `extra-crawl-tce-sc` | 05:30 | `monitor.py --source tce_sc --mode full` | Diario |
| `extra-crawl-doe-sc` | 03:00 | `monitor.py --source doe_sc --mode full` | Diario |
| `extra-crawl-transparencia` | Sun 06:00 | `monitor.py --source transparencia --mode full` | Semanal |
| `extra-crawl-contracts` | Mon,Wed,Fri 06:00 | `monitor.py --source contracts --mode full` | 3x/semana |
| `extra-coverage-report` | 09:00 | `monitor.py --report-coverage + coverage snapshot` | Diario |
| `extra-panorama-weekly` | Mon 07:00 | `panorama.py` | Semanal |
| `extra-db-backup` | 06:00 | `backup-database.sh` | Diario |
| `extra-db-purge` | 07:00 | `purge_old_records(400)` | Diario |
| `extra-health-check` | */30 min | `health_check.py` | 30/30 min |

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

## Storage Box

### Configuracao

A Storage Box Hetzner (BX11, 100 GB) e montada via sshfs para backups:

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

> **Documentacao gerada em:** 2026-07-11
> **Story:** FEAT-4.1 — Provisionar Hetzner VPS
> **Responsavel:** @devops (Gage)

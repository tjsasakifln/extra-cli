# Provisionamento de VPS — Extra Consultoria

> Documentacao de provisionamento da infraestrutura de producao.
> **Versão:** 2.0 — 2026-07-15 (desacoplado de provedor específico)
> **Responsavel:** @devops (Gage)

## Aviso

Esta documentação está em transição. As seções específicas da Hetzner permanecem como registro histórico e implementação existente, mas a direção arquitetural é provider-agnostic.

**Estratégia atual:** Ansible como ferramenta primária de configuração (Estágio 1). OpenTofu/Terraform como camada futura de provisionamento (Estágio 2).
Ver `docs/architecture/adr/ADR-007-cloud-hosting-strategy.md` e `docs/architecture/adr/ADR-008-infrastructure-as-code-strategy.md`.

## Sumario

- [Dimensionamento de Referência](#dimensionamento-de-referencia)
- [Especificacao Tecnica (Hetzner — registro historico)](#especificacao-tecnica-hetzner)
- [Provisionamento](#provisionamento)
- [Systemd Timers](#systemd-timers)
- [Backup](#backup)
- [Firewall](#firewall)
- [Manutencao](#manutencao)
- [Troubleshooting](#troubleshooting)

## Dimensionamento de Referência

O dimensionamento abaixo é a referência de implantação inicial para o cenário pós-backfill (4M+ contratos, centenas de milhares de editais, múltiplas fontes, crescimento contínuo).

| Recurso | Referência Inicial |
|---------|-------------------|
| RAM | 32 GB |
| CPU | Dedicada (boa disponibilidade sustentada) |
| Armazenamento | ~1 TB NVMe (expansível) |
| PostgreSQL | 16 |
| SO | Ubuntu 24.04 LTS |

O dimensionamento real depende do provedor selecionado e dos resultados do teste comparativo da API PNCP (ver ADR-007).

## Especificacao Tecnica (Hetzner — registro historico)

A configuração abaixo é o provisionamento atual documentado na story FEAT-4.1. **Esta configuração (CX22, 4 GB RAM, 40 GB SSD) é inadequada para o volume de dados esperado após backfill.**

| Item | Especificacao (ATUAL) | Especificacao (REFERÊNCIA FUTURA) |
|------|---------------|----------------------------------|
| **Plano** | Hetzner CX22 (2 vCPU, 4 GB RAM, 40 GB SSD) | ~32 GB RAM, CPU dedicada, ~1 TB NVMe |
| **SO** | Ubuntu 24.04 LTS | Ubuntu 24.04 LTS |
| **Regiao** | Nuremberg (nbg1-dc3) | A definir (EUA costa leste preferencial, condicionado a teste PNCP) |
| **Storage Box** | BX11 (100 GB) | Storage externo (provider-agnostic) |
| **Custo estimado** | ~EUR 7,40/mes | A cotar conforme provedor selecionado |

### Custo Detalhado (Hetzner CX22 — ATUAL)

| Item | Custo (EUR/mes) |
|------|-----------------|
| CX22 (2 vCPU, 4 GB RAM, 40 GB) | 4,49 |
| BX11 Storage Box (100 GB) | 2,90 |
| IP extra (se necessario) | 1,50 |
| **Total** | **~7,39 - 8,89** |

**Nota:** Este custo é da configuração atual subdimensionada. O custo da configuração de referência (32 GB RAM, ~1 TB NVMe) será significativamente maior e depende do provedor selecionado.

## Provisionamento

### Método recomendado: Ansible (Estágio 1)

Playbook Ansible como forma canônica de configurar a VPS, oferecendo idempotência, rastreabilidade e reexecução segura.

```bash
# Localmente, a partir do repositório
ansible-playbook -i inventory.yml playbooks/site.yml
```

### Método histórico: Script bash (Hetzner)

```bash
# SSH na VPS
ssh root@<IP_DA_VPS>

# Baixar e executar script de provisionamento
bash <(curl -fsSL https://raw.githubusercontent.com/extra-consultoria/main/deploy/provision-vps.sh)
```

### Método histórico: Hetzner Cloud API

Requer `hcloud` CLI instalado e API token configurado:

```bash
export HCLOUD_TOKEN="seu-token-aqui"
hcloud server create \
  --name extra-consultoria \
  --type cx22 \
  --image ubuntu-24.04 \
  --location nbg1 \
  --ssh-key ~/.ssh/id_ed25519.pub
```

## Passo a Passo (registro historico para Hetzner)

### 1. System Packages

```bash
apt-get update && apt-get upgrade -y
apt-get install -y python3 python3-pip python3-venv postgresql-16 postgresql-client-16 \
  sshfs gzip curl wget git ufw fail2ban htop unattended-upgrades
```

### 2. PostgreSQL 16

```bash
# Configurar para ouvir apenas localhost
sed -i "s/^#listen_addresses = 'localhost'/listen_addresses = 'localhost'/" /etc/postgresql/16/main/postgresql.conf

# Tuning para 32 GB RAM (referência)
cat >> /etc/postgresql/16/main/postgresql.conf << 'EOF'
shared_buffers = 8GB
effective_cache_size = 24GB
work_mem = 64MB
maintenance_work_mem = 1GB
random_page_cost = 1.1
effective_io_concurrency = 200
wal_buffers = 64MB
max_parallel_workers = 4
max_parallel_workers_per_gather = 4
EOF

systemctl restart postgresql

# Criar database
sudo -u postgres createdb pncp_datalake
sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'SENHA_SEGURA'"
```

**Nota:** O tuning acima é para a configuração de referência (32 GB RAM). Ajustar conforme o hardware real provisionado.

### 3. Clone e Deploy

```bash
useradd -m -s /bin/bash extra-consultoria
git clone https://github.com/extra-consultoria/extra-consultoria.git /opt/extra-consultoria
cd /opt/extra-consultoria
chown -R extra-consultoria:extra-consultoria /opt/extra-consultoria
pip3 install -r requirements.txt
bash db/setup_db.sh postgresql://postgres:SENHA@localhost:5432/pncp_datalake
```

### 4. SSH Hardening

```bash
# Editar /etc/ssh/sshd_config
Port 2222
PermitRootLogin without-password
PasswordAuthentication no

systemctl restart sshd
```

### 5. Firewall

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

## Storage Box (Backup Externo)

### Aviso

A documentação abaixo referencia Hetzner Storage Box como implementação atual. A estratégia de backup é provider-agnostic (ver `docs/ops/backup.md` e `docs/ops/cloud-deployment-plan.md`). Storage Box da Hetzner não é requisito arquitetural.

### Configuracao (Hetzner — implementação atual)

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

> **Ultima atualizacao:** 2026-07-15 (desacoplado de Hetzner como baseline)
> **Story original:** FEAT-4.1 — Provisionar Hetzner VPS
> **Responsavel:** @devops (Gage)

# Backup Automatizado do PostgreSQL

> Documentacao do sistema de backup do banco PostgreSQL (DataLake da Extra Consultoria).
> **Versão:** 2.0 — 2026-07-15 (desacoplado de provedor específico)
> **Debito:** TD-DB-15 (CRITICAL) -- Ausencia total de backup strategy

## Aviso

A estratégia de backup é **provider-agnostic**. A implementação atual usa Hetzner Storage Box como destino, mas a direção arquitetural é armazenamento externo desacoplado de provedor (object storage, volume separado ou storage box de qualquer fornecedor).

**A Hetzner Storage Box não é requisito obrigatório.** Ver `docs/ops/cloud-deployment-plan.md` para a estratégia completa.

## Sumario

- [Estratégia de Backup](#estrategia-de-backup)
- [Arquitetura](#arquitetura)
- [Scripts](#scripts)
- [Instalacao no Servidor](#instalacao-no-servidor)
- [Systemd Service e Timer](#systemd-service-e-timer)
- [Configuracao de Storage Externo](#configuracao-de-storage-externo)
- [Retention Policy](#retention-policy)
- [Restore](#restore)
- [Monitoramento](#monitoramento)
- [Perguntas Frequentes](#perguntas-frequentes)

## Estratégia de Backup

### Direção pretendida

- Backup fora da máquina principal
- Backup criptografado (em trânsito via SSH)
- Retenção diária (7) e semanal (4)
- Armazenamento externo (provider-agnostic)
- Possibilidade de point-in-time recovery (WAL archiving — futuro)
- Ferramentas: `pg_dump` (atual) → `pgBackRest` ou `WAL-G` (evolução futura)
- Testes periódicos de restauração
- Registro do último backup válido
- Alertas de falha

### Implementação atual

O script `scripts/backup-database.sh` implementa backup via `pg_dump --format=custom` com destino em storage externo montado via sshfs. A implementação atual usa Hetzner Storage Box, mas o script é adaptável a qualquer destino sshfs ou object storage.

### O que NÃO é backup

- Snapshots do provedor não substituem backup do PostgreSQL
- Réplicas não substituem backup (protegem contra falha de hardware, não contra erro lógico)

## Arquitetura

```
[VPS em Nuvem]                      [Storage Externo]
+---------------+                    +---------------------+
| PostgreSQL 16 |                    | backups/postgresql/ |
| (pncp)        |                    |  +-- daily/         |
+-------+-------+                    |  |   +-- pncp_*.gz  |
        |                            |  +-- weekly/        |
        | pg_dump --format=custom    |      +-- pncp_*.gz  |
        | gzip                       |                     |
        v                            |                     |
+---------------+                    +---------------------+
| backup-       |-- sshfs mount -->  |                     |
| database.sh   |                    |                     |
+---------------+                    +---------------------+
        |
        v
+----------------+
| Log            |
| /var/log/      |
| backup-database|
| .log           |
+----------------+
```

### Fluxo

1. Script monta Hetzner Storage Box via `sshfs` no ponto `/mnt/storage-box`
2. Executa `pg_dump --format=custom` com compressao nativa (nivel 9)
3. Comprime saida com `gzip` para reducao adicional
4. Salva em `daily/pncp_datalake-YYYY-MM-DD.dump.gz`
5. Verifica integridade do gzip no arquivo gerado
6. Executa retention: mantem 7 backups diarios + 4 semanais
7. Aos Domingos: promove o ultimo backup diario como semanal
8. Desmonta Storage Box
9. Loga status, tamanho e duracao

### Dependencias

| Pacote | Funcao |
|--------|--------|
| `postgresql-client-16` | pg_dump, pg_restore, psql |
| `sshfs` | Montagem FUSE da Storage Box |
| `gzip` | Compressao e verificacao de integridade |

## Scripts

### `scripts/backup-database.sh`

Script principal de backup. Pode ser executado manualmente ou via systemd timer.

```bash
# Backup completo
./scripts/backup-database.sh

# Apenas limpeza de retention
./scripts/backup-database.sh --retention-only

# Simulacao (dry-run)
./scripts/backup-database.sh --dry-run
```

#### Variaveis de Ambiente

| Variavel | Obrigatoria | Default | Descricao |
|----------|-------------|---------|-----------|
| `LOCAL_DATALAKE_DSN` | Sim | - | PostgreSQL DSN (`postgresql://user:pass@host:5432/pncp_datalake`) |
| `BACKUP_STORAGE_BOX_SSH` | Sim | - | SSH user@host para Hetzner Storage Box |
| `BACKUP_MOUNT_POINT` | Nao | `/mnt/storage-box` | Ponto de montagem sshfs |
| `BACKUP_REMOTE_DIR` | Nao | `backups/postgresql` | Diretorio remoto na Storage Box |
| `BACKUP_TEMP_DIR` | Nao | `/tmp/pg-backup` | Diretorio temporario local |
| `BACKUP_RETENTION_DAILY` | Nao | `7` | Numero de backups diarios a manter |
| `BACKUP_RETENTION_WEEKLY` | Nao | `4` | Numero de backups semanais a manter |
| `BACKUP_LOG_FILE` | Nao | `/var/log/backup-database.log` | Caminho do arquivo de log |
| `BACKUP_NOTIFY_CMD` | Nao | - | Comando executado em caso de falha |
| `BACKUP_PREFIX` | Nao | `pncp_datalake` | Prefixo dos nomes de arquivo |
| `SSHFS_OPTIONS` | Nao | `-o reconnect,...` | Opcoes extras para sshfs |

### `scripts/restore-database.sh`

Script de restauracao de backup.

```bash
# Listar conteudo do backup
./scripts/restore-database.sh backups/pncp_datalake-2026-07-11.dump.gz --list

# Restaurar backup completo
./scripts/restore-database.sh backups/pncp_datalake-2026-07-11.dump.gz

# Restaurar apenas schema
./scripts/restore-database.sh backups/pncp_datalake-2026-07-11.dump.gz --schema-only

# Restaurar apenas dados
./scripts/restore-database.sh backups/pncp_datalake-2026-07-11.dump.gz --data-only
```

## Instalacao no Servidor

### 1. Configurar variaveis de ambiente

Crie ou edite `/etc/backup-database.conf`:

```bash
LOCAL_DATALAKE_DSN=postgresql://postgres:SENHA@localhost:5432/pncp_datalake
BACKUP_STORAGE_BOX_SSH=u123456@u123456.your-storagebox.de
BACKUP_REMOTE_DIR=backups/postgresql
BACKUP_RETENTION_DAILY=7
BACKUP_RETENTION_WEEKLY=4
BACKUP_LOG_FILE=/var/log/backup-database.log
```

### 2. Instalar dependencias

```bash
apt update
apt install -y postgresql-client-16 sshfs gzip  # PostgreSQL 16 (versão canônica inicial)
```

### 3. Copiar script para o servidor

```bash
# Do repositorio local para o VPS
scp scripts/backup-database.sh usuario@vps:/usr/local/bin/backup-database.sh
scp scripts/restore-database.sh usuario@vps:/usr/local/bin/restore-database.sh
chmod +x /usr/local/bin/backup-database.sh /usr/local/bin/restore-database.sh
```

### 4. Configurar chave SSH para Storage Box

```bash
# Gerar chave (se nao existir)
ssh-keygen -t ed25519 -f /root/.ssh/storage_box -N ""

# Adicionar chave publica no Hetzner Robot > Storage Box > SSH Keys
cat /root/.ssh/storage_box.pub

# Criar config SSH
cat >> /root/.ssh/config << 'EOF'
Host storagebox
    HostName u123456.your-storagebox.de
    User u123456
    IdentityFile /root/.ssh/storage_box
EOF

# Testar conexao
ssh storagebox
```

### 5. Testar montagem manual

```bash
mkdir -p /mnt/storage-box
sshfs -o reconnect,ServerAliveInterval=15,ServerAliveCountMax=3 \
  u123456@u123456.your-storagebox.de:backups/postgresql \
  /mnt/storage-box
ls /mnt/storage-box
umount /mnt/storage-box
```

## Systemd Service e Timer

### Service: `/etc/systemd/system/extra-db-backup.service`

```ini
[Unit]
Description=Extra Consultoria - Backup PostgreSQL DataLake
Documentation=https://github.com/extra-consultoria/docs/ops/backup.md
Requires=network-online.target
After=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/local/bin/backup-database.sh
EnvironmentFile=/etc/backup-database.conf
User=root
Group=root
Nice=19
IOSchedulingClass=best-effort
IOSchedulingPriority=7
StandardOutput=append:/var/log/backup-database.log
StandardError=append:/var/log/backup-database.log
# Reinicia em caso de falha (max 3 tentativas, 5min intervalo)
Restart=on-failure
RestartSec=300
StartLimitIntervalSec=3600
StartLimitBurst=3

[Install]
WantedBy=multi-user.target
```

### Timer: `/etc/systemd/system/extra-db-backup.timer`

```ini
[Unit]
Description=Extra Consultoria - Backup PostgreSQL Diario 03:00 BRT
Documentation=https://github.com/extra-consultoria/docs/ops/backup.md

[Timer]
# Executa diariamente as 03:00 BRT (06:00 UTC = 03:00 BRT fora do horario de verao)
# Brasil nao adota horario de verao desde 2019
OnCalendar=*-*-* 06:00:00 America/Sao_Paulo
# Previne execucao se o servidor estava desligado (armadilha)
Persistent=false
# Unidade de tempo aleatoria para evitar picos
RandomizedDelaySec=300

[Install]
WantedBy=timers.target
```

### Ativar e testar

```bash
# Instalar arquivos
cp extra-db-backup.service /etc/systemd/system/
cp extra-db-backup.timer /etc/systemd/system/
systemctl daemon-reload

# Habilitar e iniciar timer
systemctl enable extra-db-backup.timer
systemctl start extra-db-backup.timer

# Verificar status
systemctl status extra-db-backup.timer
systemctl list-timers --all | grep extra-db

# Testar servico manualmente
systemctl start extra-db-backup.service
journalctl -u extra-db-backup.service --no-pager -n 50
```

## Configuracao de Storage Externo

O backup deve ser armazenado fora da máquina principal. A implementação atual usa Hetzner Storage Box via sshfs, mas qualquer destino compatível com sshfs ou object storage pode ser utilizado.

### Dados de Acesso (exemplo com Hetzner Storage Box — implementação atual)

| Campo | Valor |
|-------|-------|
| Host | `{username}.your-storagebox.de` |
| User | `{username}` |
| Porta SSH | 23 |
| Path padrao | `backups/postgresql` |

### Opcoes sshfs recomendadas

```bash
sshfs -o reconnect,ServerAliveInterval=15,ServerAliveCountMax=3,allow_other \
  u123456@u123456.your-storagebox.de:backups/postgresql \
  /mnt/storage-box
```

### Automontagem via fstab (alternativa)

```bash
# /etc/fstab
sshfs#u123456@u123456.your-storagebox.de:backups/postgresql /mnt/storage-box fuse user,_netdev,reconnect,ServerAliveInterval=15,ServerAliveCountMax=3,idmap=user,transform_symlinks,identityfile=/root/.ssh/storage_box,allow_other,default_permissions 0 0
```

## Retention Policy

### Regras

| Tipo | Quantidade | Janela Estimada | Identificacao |
|------|------------|-----------------|---------------|
| Diario | 7 backups | 7 dias | Nome `pncp_datalake-YYYY-MM-DD.dump.gz` |
| Semanal | 4 backups | 28 dias | Nome `pncp_datalake-YYYY-MM-DD.weekly.dump.gz` |

### Logica de Retention

1. **Diarios:** Lista todos os arquivos `pncp_datalake-*.dump.gz` em order alfabetica (por data), mantem os 7 mais recentes, remove os excedentes
2. **Semanais:** Aos Domingos, o ultimo backup diario e copiado para o diretorio `weekly/` com sufixo `.weekly.dump.gz`. A retention semanal mantem os 4 mais recentes
3. A retention pode ser executada isoladamente com `--retention-only`

### Estimativa de Armazenamento

| Item | Tamanho Estimado |
|------|-----------------|
| Backup diario (comprimido) | 1-2 GB |
| Retention 7 diarios | 7-14 GB |
| Retention 4 semanais | 4-8 GB |
| **Total estimado** | **11-22 GB** |

## Restore

### Procedimento de Restauracao Completa

```bash
# 1. (Opcional) Dropar e recriar database para restore limpo
psql -h localhost -U postgres -c "DROP DATABASE IF EXISTS pncp_datalake;"
psql -h localhost -U postgres -c "CREATE DATABASE pncp_datalake;"

# 2. Restaurar do backup mais recente
./scripts/restore-database.sh /mnt/storage-box/daily/pncp_datalake-$(date +%F).dump.gz

# 3. Verificar dados restaurados
psql -d pncp_datalake -c "SELECT count(*) FROM information_schema.tables;"
```

### Restaurase Seletiva

O formato `pg_dump --format=custom` permite restore seletivo:

```bash
# Listar tabelas no backup
./scripts/restore-database.sh backup.dump.gz --list | grep TABLE

# Apenas schema (estrutura, sem dados)
./scripts/restore-database.sh backup.dump.gz --schema-only

# Apenas dados (schema existente)
./scripts/restore-database.sh backup.dump.gz --data-only
```

### Restaurao para Ambiente Local (dev)

```bash
# Copiar backup da Storage Box
rsync -avz -e "ssh -p 23" \
  u123456@u123456.your-storagebox.de:backups/postgresql/daily/ \
  /tmp/pg-restore/

# Restaurar localmente
LOCAL_DATALAKE_DSN=postgresql://postgres:local@localhost:5432/pncp_datalake \
  ./scripts/restore-database.sh /tmp/pg-restore/pncp_datalake-*.dump.gz
```

## Monitoramento

### Logs

O script gera logs em formato estruturado em `/var/log/backup-database.log`:

```
[2026-07-11 03:00:01 -0300] [INFO] === Inicio da execucao (modo: backup) ===
[2026-07-11 03:00:02 -0300] [INFO] Montando Storage Box em /mnt/storage-box
[2026-07-11 03:00:05 -0300] [INFO] Storage Box montada com sucesso
[2026-07-11 03:00:06 -0300] [INFO] Iniciando pg_dump para pncp_datalake-2026-07-11.dump.gz
[2026-07-11 03:02:15 -0300] [INFO] Backup concluido: pncp_datalake-2026-07-11.dump.gz | Tamanho: 1.2G | Duracao: 129s
[2026-07-11 03:02:15 -0300] [INFO] Integridade do gzip verificada: OK
[2026-07-11 03:02:16 -0300] [INFO] Retention concluida | Diarios: 5 | Semanais: 3
[2026-07-11 03:02:17 -0300] [INFO] === Backup concluido com sucesso ===
```

### JSON estruturado para ingestao

Cada backup gera uma linha com `LOG_JSON:` contendo:

```json
{
  "event": "backup",
  "timestamp": "2026-07-11T06:00:01+00:00",
  "file": "pncp_datalake-2026-07-11.dump.gz",
  "size_bytes": 1287654321,
  "duration_sec": 129,
  "status": "success"
}
```

### Verificacao Rapida

```bash
# Ultimo backup
tail -20 /var/log/backup-database.log

# Status do timer
systemctl status extra-db-backup.timer

# Ultimas execucoes
journalctl -u extra-db-backup.service --no-pager -n 30

# Listar backups na Storage Box
ls -lh /mnt/storage-box/daily/
ls -lh /mnt/storage-box/weekly/

# Verificar integridade dos backups
for f in /mnt/storage-box/daily/*.dump.gz; do
  echo -n "$(basename $f): "
  gzip -t "$f" && echo "OK" || echo "CORROMPIDO"
done
```

### Notificacao de Falha

Em caso de falha, o script executa o comando definido em `BACKUP_NOTIFY_CMD`.
Exemplos de uso:

```bash
# Notificacao via Telegram (exemplo)
BACKUP_NOTIFY_CMD='curl -s -X POST https://api.telegram.org/bot$TOKEN/sendMessage \
  -d chat_id=$CHAT_ID -d text="[BACKUP] $1: $2"'

# Notificacao via webhook (exemplo)
BACKUP_NOTIFY_CMD='curl -s -X POST https://hooks.example.com/backup-alert \
  -H "Content-Type: application/json" \
  -d "{\"subject\":\"$1\",\"body\":\"$2\"}"'
```

## Perguntas Frequentes

### O backup impacta a performance do banco?

Sim, `pg_dump` executa em paralelo e le o banco durante operacao. Para minimizar impacto:
- O servico executa com `Nice=19` e `IOSchedulingPriority=7` (baixa prioridade)
- O horario agendado (03:00 BRT) e de baixa atividade
- Se necessario, usar `pg_dump --jobs=2` para limitar paralelismo

### O que acontece se a Storage Box estiver indisponivel?

O script falha e loga o erro. O systemd service esta configurado com `Restart=on-failure`,
entao tentara novamente a cada 5 minutos por ate 3 vezes na mesma janela.

### Como recuperar se o backup estiver corrompido?

O script verifica integridade do gzip apos cada backup. Se um arquivo existente estiver
corrompido, tente:

```bash
# Verificar todos os backups
for f in /mnt/storage-box/daily/*.dump.gz; do
  gzip -t "$f" || echo "CORROMPIDO: $f"
done

# Se o dump internamente estiver ok (formato custom),
# pg_restore pode ignorar objetos corrompidos
gzip -dc backup_corrompido.dump.gz | pg_restore --list 2>&1 | head -20
```

### Preciso testar o restore?

Sim! Recomenda-se testar o restore mensalmente em ambiente de staging.
Consulte o procedimento em [Procedimento de Restauracao](#procedimento-de-restauracao-completa).

---

> **Documentacao gerada em:** 2026-07-11
> **Story:** TD-0.1 -- Setup Backup Automatizado
> **Responsavel:** @devops (Gage)

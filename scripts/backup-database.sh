#!/usr/bin/env bash
# =============================================================================
# backup-database.sh — PostgreSQL Backup Automatizado
# =============================================================================
# Realiza dump do banco PostgreSQL (formato custom), compacta com gzip,
# copia para Hetzner Storage Box via sshfs, e gerencia retention.
#
# Uso:
#   ./scripts/backup-database.sh                    # Executa backup completo
#   ./scripts/backup-database.sh --retention-only   # Apenas limpeza retention
#   ./scripts/backup-database.sh --dry-run          # Simula sem executar
#   ./scripts/backup-database.sh --help             # Ajuda
#
# Configuração via variáveis de ambiente (ou .env):
#   LOCAL_DATALAKE_DSN          - PostgreSQL DSN (obrigatório)
#   BACKUP_MOUNT_POINT          - Ponto de montagem sshfs (def: /mnt/storage-box)
#   BACKUP_STORAGE_BOX_SSH      - SSH user@host para Storage Box (obrigatório)
#   BACKUP_REMOTE_DIR           - Diretório remoto de backups (def: backups/postgresql)
#   BACKUP_TEMP_DIR             - Diretório temporário local (def: /tmp/pg-backup)
#   BACKUP_RETENTION_DAILY      - Qtde diários a manter (def: 7)
#   BACKUP_RETENTION_WEEKLY     - Qtde semanais a manter (def: 4)
#   BACKUP_LOG_FILE             - Arquivo de log (def: /var/log/backup-database.log)
#   BACKUP_NOTIFY_CMD           - Comando executado em falha (opcional)
#   SSHFS_OPTIONS               - Opções extras para sshfs (opcional)
#
# Dependências:
#   - pg_dump (PostgreSQL client)
#   - sshfs (FUSE)
#   - gzip
# =============================================================================

set -euo pipefail

# ─── Configuração ───────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Carrega .env se existir
if [ -f "$PROJECT_DIR/.env" ]; then
  set -a
  source "$PROJECT_DIR/.env"
  set +a
fi

# Configurações com defaults
DSN="${LOCAL_DATALAKE_DSN:-}"
MOUNT_POINT="${BACKUP_MOUNT_POINT:-/mnt/storage-box}"
STORAGE_BOX_SSH="${BACKUP_STORAGE_BOX_SSH:-}"
# NFS off-site (Netcup Storagespace etc.): host:/export — prefer over sshfs when set
NFS_EXPORT="${BACKUP_NFS_EXPORT:-}"
REMOTE_DIR="${BACKUP_REMOTE_DIR:-backups/postgresql}"
TEMP_DIR="${BACKUP_TEMP_DIR:-/tmp/pg-backup}"
RETENTION_DAILY="${BACKUP_RETENTION_DAILY:-7}"
RETENTION_WEEKLY="${BACKUP_RETENTION_WEEKLY:-4}"
LOG_FILE="${BACKUP_LOG_FILE:-/var/log/backup-database.log}"
NOTIFY_CMD="${BACKUP_NOTIFY_CMD:-}"
SSHFS_OPTS="${SSHFS_OPTIONS:--o reconnect,ServerAliveInterval=15,ServerAliveCountMax=3}"
NFS_OPTS="${BACKUP_NFS_OPTIONS:-vers=3,nolock,hard,timeo=600,retrans=2}"
# If 1, keep mount after backup (for fstab / permanent NFS)
KEEP_MOUNT="${BACKUP_KEEP_MOUNT:-0}"
PREFIX="${BACKUP_PREFIX:-pncp_datalake}"
LOCK_FILE="/tmp/backup-database.lock"

# ─── Funções ────────────────────────────────────────────────────────────────

log() {
  local level="$1"
  shift
  local message="$*"
  local timestamp
  timestamp="$(date '+%Y-%m-%d %H:%M:%S %z')"
  echo "[$timestamp] [$level] $message" >> "$LOG_FILE"
  if [ "$level" = "ERROR" ] || [ "$level" = "FATAL" ]; then
    echo "[$timestamp] [$level] $message" >&2
  fi
}

notify_failure() {
  local subject="$1"
  local body="$2"
  if [ -n "$NOTIFY_CMD" ]; then
    eval "$NOTIFY_CMD" "$subject" "$body" 2>/dev/null || true
  fi
  log "WARN" "Notificação configurada como: $NOTIFY_CMD"
}

cleanup() {
  local exit_code=$?
  if [ -f "$LOCK_FILE" ]; then
    rm -f "$LOCK_FILE"
    log "INFO" "Lock file removido"
  fi
  if [ $exit_code -ne 0 ]; then
    log "ERROR" "Script finalizou com código $exit_code"
  fi
  exit "$exit_code"
}

usage() {
  cat <<EOF
Uso: $0 [opções]

Opções:
  --retention-only  Executa apenas a limpeza de retention
  --dry-run         Simula as operações sem executar
  --help            Exibe esta mensagem

Variáveis de ambiente obrigatórias:
  LOCAL_DATALAKE_DSN     - PostgreSQL DSN
  BACKUP_STORAGE_BOX_SSH - SSH user@host para Storage Box

Variáveis de ambiente opcionais:
  BACKUP_MOUNT_POINT     - Ponto de montagem (default: /mnt/storage-box)
  BACKUP_REMOTE_DIR      - Diretório remoto (default: backups/postgresql)
  BACKUP_RETENTION_DAILY - Qtde diários (default: 7)
  BACKUP_RETENTION_WEEKLY- Qtde semanais (default: 4)
  BACKUP_LOG_FILE        - Caminho do log (default: /var/log/backup-database.log)
  BACKUP_NOTIFY_CMD      - Comando para notificação em falha
EOF
  exit 0
}

# ─── Parse de argumentos ────────────────────────────────────────────────────

MODE="backup"  # backup | retention-only
DRY_RUN=false

while [ $# -gt 0 ]; do
  case "$1" in
    --retention-only) MODE="retention-only"; shift ;;
    --dry-run)        DRY_RUN=true; shift ;;
    --help)           usage ;;
    *) echo "Opção desconhecida: $1"; usage ;;
  esac
done

# ─── Verificações iniciais ──────────────────────────────────────────────────

# Cria diretório de log se não existir
LOG_DIR="$(dirname "$LOG_FILE")"
if [ ! -d "$LOG_DIR" ]; then
  if [ "$DRY_RUN" = false ]; then
    mkdir -p "$LOG_DIR"
  fi
fi

log "INFO" "=== Início da execução (modo: $MODE) ==="

# Verifica dependências
for cmd in pg_dump gzip; do
  if ! command -v "$cmd" &>/dev/null; then
    log "FATAL" "Comando não encontrado: $cmd"
    notify_failure "Backup DB - Falha" "Comando não encontrado: $cmd"
    exit 1
  fi
done

# Verifica DSN
if [ -z "$DSN" ]; then
  log "FATAL" "LOCAL_DATALAKE_DSN não configurada"
  notify_failure "Backup DB - Falha" "LOCAL_DATALAKE_DSN não configurada"
  exit 1
fi

# Verifica lock file (evita execução concorrente)
if [ -f "$LOCK_FILE" ] && [ "$DRY_RUN" = false ]; then
  LOCK_PID=$(cat "$LOCK_FILE" 2>/dev/null || echo "")
  if [ -n "$LOCK_PID" ] && kill -0 "$LOCK_PID" 2>/dev/null; then
    log "ERROR" "Outra instância do backup está em execução (PID: $LOCK_PID)"
    exit 1
  else
    log "WARN" "Lock file órfão encontrado, removendo"
    rm -f "$LOCK_FILE"
  fi
fi

if [ "$DRY_RUN" = false ]; then
  echo $$ > "$LOCK_FILE"
fi
trap cleanup EXIT

# ─── Storage Box (sshfs) ────────────────────────────────────────────────────

_offsite_configured() {
  # Accept NFS export, nfs:// URI in STORAGE_BOX_SSH, or classic user@host SSH.
  if [ -n "$NFS_EXPORT" ]; then
    return 0
  fi
  if [ -n "$STORAGE_BOX_SSH" ]; then
    return 0
  fi
  return 1
}

mount_storage_box() {
  if ! _offsite_configured; then
    log "FATAL" "Off-site não configurado (defina BACKUP_NFS_EXPORT ou BACKUP_STORAGE_BOX_SSH)"
    notify_failure "Backup DB - Falha" "Off-site destination not configured"
    exit 1
  fi

  # Already mounted (e.g. fstab NFS) — treat as success
  if mountpoint -q "$MOUNT_POINT" 2>/dev/null; then
    log "INFO" "Destino off-site já montado em $MOUNT_POINT"
    return 0
  fi

  mkdir -p "$MOUNT_POINT"

  # Prefer explicit NFS export (Netcup Storagespace)
  local export_spec=""
  if [ -n "$NFS_EXPORT" ]; then
    export_spec="$NFS_EXPORT"
  elif [[ "$STORAGE_BOX_SSH" == nfs://* ]]; then
    # nfs://host/path → host:/path
    export_spec="${STORAGE_BOX_SSH#nfs://}"
    export_spec="${export_spec%%/*}:/${export_spec#*/}"
  elif [[ "$STORAGE_BOX_SSH" == *":/"* ]] && [[ "$STORAGE_BOX_SSH" != *@* ]]; then
    # host:/export form
    export_spec="$STORAGE_BOX_SSH"
  fi

  if [ -n "$export_spec" ]; then
    log "INFO" "Montando NFS off-site $export_spec em $MOUNT_POINT"
    if [ "$DRY_RUN" = true ]; then
      log "INFO" "[DRY-RUN] mount -t nfs -o $NFS_OPTS $export_spec $MOUNT_POINT"
      return 0
    fi
    if ! mount -t nfs -o "$NFS_OPTS" "$export_spec" "$MOUNT_POINT"; then
      log "ERROR" "Falha ao montar NFS $export_spec"
      notify_failure "Backup DB - Falha" "Falha ao montar NFS off-site"
      return 1
    fi
    log "INFO" "NFS off-site montado com sucesso"
    return 0
  fi

  # Classic sshfs path
  if ! command -v sshfs &>/dev/null; then
    log "FATAL" "sshfs não encontrado. Instale com: apt install sshfs"
    notify_failure "Backup DB - Falha" "sshfs não encontrado"
    exit 1
  fi

  log "INFO" "Montando Storage Box sshfs em $MOUNT_POINT"
  if [ "$DRY_RUN" = true ]; then
    log "INFO" "[DRY-RUN] sshfs $STORAGE_BOX_SSH:$REMOTE_DIR $MOUNT_POINT $SSHFS_OPTS"
    return 0
  fi

  if ! sshfs "$STORAGE_BOX_SSH:$REMOTE_DIR" "$MOUNT_POINT" $SSHFS_OPTS; then
    log "ERROR" "Falha ao montar Storage Box"
    notify_failure "Backup DB - Falha" "Falha ao montar Storage Box via sshfs"
    return 1
  fi
  log "INFO" "Storage Box montada com sucesso"
}

umount_storage_box() {
  if [ "$KEEP_MOUNT" = "1" ]; then
    log "INFO" "BACKUP_KEEP_MOUNT=1 — mantendo montagem em $MOUNT_POINT"
    return 0
  fi
  if mountpoint -q "$MOUNT_POINT" 2>/dev/null; then
    log "INFO" "Desmontando destino off-site"
    if [ "$DRY_RUN" = false ]; then
      umount "$MOUNT_POINT" 2>/dev/null || log "WARN" "Falha ao desmontar (pode estar ocupada)"
    fi
  fi
}

ensure_remote_dirs() {
  local base="$1"
  if [ "$DRY_RUN" = true ]; then
    log "INFO" "[DRY-RUN] Criaria diretórios: $base/{daily,weekly}"
    return 0
  fi
  mkdir -p "$base/daily" "$base/weekly"
}

# ─── Backup ──────────────────────────────────────────────────────────────────

do_backup() {
  local backup_base="$1"
  local date_stamp
  date_stamp="$(date '+%Y-%m-%d')"
  local dump_name="${PREFIX}-${date_stamp}.dump.gz"
  local dump_path="${backup_base}/daily/${dump_name}"
  local staging_path="${TEMP_DIR%/}/${dump_name}"
  local start_time end_time duration_sec file_size

  log "INFO" "Iniciando pg_dump para $dump_name"

  start_time="$(date +%s)"
  mkdir -p "$TEMP_DIR" "${backup_base}/daily"

  if [ "$DRY_RUN" = true ]; then
    log "INFO" "[DRY-RUN] pg_dump → stage $staging_path → $dump_path"
    file_size="0 (dry-run)"
    duration_sec=0
  else
    # Stage to local file first (pg_dump --file=/dev/stdout fails fsync; NFS needs stable copy).
    local staging_custom="${TEMP_DIR%/}/${PREFIX}-${date_stamp}.dump"
    rm -f "$staging_path" "$staging_custom"
    if pg_dump --dbname="$DSN" --format=custom --compress=9 \
        --file="$staging_custom" 2>> "$LOG_FILE"; then
      end_time="$(date +%s)"
      duration_sec=$(( end_time - start_time ))
      # wrap custom dump in gzip for transport naming (.dump.gz)
      if ! gzip -c "$staging_custom" > "$staging_path"; then
        log "ERROR" "gzip falhou ao embalar $staging_custom"
        rm -f "$staging_custom" "$staging_path"
        notify_failure "Backup DB - Falha" "gzip falhou"
        return 1
      fi
      rm -f "$staging_custom"
      file_size="$(stat --printf='%s' "$staging_path" 2>/dev/null || echo 0)"
      log "INFO" "Dump local: $staging_path | Tamanho: $(numfmt --to=iec "$file_size") | Duração: ${duration_sec}s"

      if [ "$file_size" -eq 0 ]; then
        log "ERROR" "Backup gerado com tamanho zero: $staging_path"
        rm -f "$staging_path"
        notify_failure "Backup DB - Falha" "Backup gerado com tamanho zero"
        return 1
      fi

      if ! gzip -t "$staging_path" 2>/dev/null; then
        log "ERROR" "Arquivo de backup corrompido (gzip inválido): $staging_path"
        rm -f "$staging_path"
        notify_failure "Backup DB - Falha" "Arquivo de backup corrompido (gzip inválido)"
        return 1
      fi
      log "INFO" "Integridade do gzip verificada: OK"

      log "INFO" "Copiando para off-site: $dump_path"
      if ! cp -f "$staging_path" "$dump_path"; then
        log "ERROR" "Falha ao copiar dump para destino off-site $dump_path"
        notify_failure "Backup DB - Falha" "Falha ao copiar dump off-site"
        return 1
      fi
      sync
      local remote_size
      remote_size="$(stat --printf='%s' "$dump_path" 2>/dev/null || echo 0)"
      if [ "$remote_size" != "$file_size" ]; then
        log "ERROR" "Tamanho off-site ($remote_size) != local ($file_size)"
        notify_failure "Backup DB - Falha" "Size mismatch after off-site copy"
        return 1
      fi
      log "INFO" "Backup off-site concluído: $dump_name | Tamanho: $(numfmt --to=iec "$file_size")"
      rm -f "$staging_path"
    else
      end_time="$(date +%s)"
      duration_sec=$(( end_time - start_time ))
      log "ERROR" "pg_dump falhou após ${duration_sec}s"
      notify_failure "Backup DB - Falha" "pg_dump falhou após ${duration_sec}s"
      rm -f "$staging_path" "$staging_custom"
      return 1
    fi
  fi

  # Log estruturado
  local log_entry
  log_entry="$(printf '{"event":"backup","timestamp":"%s","file":"%s","size_bytes":%s,"duration_sec":%d,"status":"%s"}' \
    "$(date -Iseconds)" "$dump_name" "${file_size:-0}" "${duration_sec:-0}" \
    "$([ "$DRY_RUN" = true ] && echo 'dry-run' || echo 'success')")"
  log "INFO" "LOG_JSON: $log_entry"

  return 0
}

# ─── Retention ──────────────────────────────────────────────────────────────

do_retention() {
  local backup_base="$1"
  local daily_dir="${backup_base}/daily"
  local weekly_dir="${backup_base}/weekly"
  local day_of_week
  day_of_week="$(date '+%u')"  # 1=segunda .. 7=domingo

  log "INFO" "Executando retention (diários: até $RETENTION_DAILY, semanais: até $RETENTION_WEEKLY)"

  # ── Promove backup de domingo como semanal ──
  if [ "$day_of_week" = "7" ]; then
    log "INFO" "Domingo: promovendo último backup diário como semanal"
    local latest_daily
    latest_daily="$(ls -1t "$daily_dir"/"${PREFIX}"-*.dump.gz 2>/dev/null | head -1 || true)"
    if [ -n "$latest_daily" ] && [ "$DRY_RUN" = false ]; then
      local weekly_name
      weekly_name="$(basename "$latest_daily" | sed 's/.dump.gz/.weekly.dump.gz/')"
      cp "$latest_daily" "$weekly_dir/$weekly_name"
      log "INFO" "Promovido: $weekly_name"
    elif [ "$DRY_RUN" = true ]; then
      log "INFO" "[DRY-RUN] Promoveria daily mais recente para weekly"
    else
      log "WARN" "Nenhum backup diário encontrado para promoção semanal"
    fi
  fi

  # ── Limpeza de backups diários ──
  if [ "$DRY_RUN" = true ]; then
    local daily_count
    daily_count="$(find "$daily_dir" -maxdepth 1 -name "${PREFIX}-*.dump.gz" 2>/dev/null | wc -l)"
    log "INFO" "[DRY-RUN] Diários existentes: $daily_count | Manter: $RETENTION_DAILY"
  else
    # Keep newest N by mtime; never fail the whole backup on retention edge cases
    mapfile -t _daily_files < <(find "$daily_dir" -maxdepth 1 -name "${PREFIX}-*.dump.gz" -printf '%T@ %p\n' 2>/dev/null | sort -n | cut -d' ' -f2-) || true
    local _n=${#_daily_files[@]}
    local _drop=$(( _n > RETENTION_DAILY ? _n - RETENTION_DAILY : 0 ))
    local _i
    for ((_i=0; _i<_drop; _i++)); do
      rm -f "${_daily_files[_i]}"
      log "INFO" "Removido backup diário antigo: $(basename "${_daily_files[_i]}")"
    done
  fi

  # ── Limpeza de backups semanais ──
  if [ "$DRY_RUN" = true ]; then
    local weekly_count
    weekly_count="$(find "$weekly_dir" -maxdepth 1 -name "${PREFIX}-*.weekly.dump.gz" 2>/dev/null | wc -l)"
    log "INFO" "[DRY-RUN] Semanais existentes: $weekly_count | Manter: $RETENTION_WEEKLY"
  else
    mapfile -t _weekly_files < <(find "$weekly_dir" -maxdepth 1 -name "${PREFIX}-*.weekly.dump.gz" -printf '%T@ %p\n' 2>/dev/null | sort -n | cut -d' ' -f2-) || true
    local _wn=${#_weekly_files[@]}
    local _wdrop=$(( _wn > RETENTION_WEEKLY ? _wn - RETENTION_WEEKLY : 0 ))
    local _j
    for ((_j=0; _j<_wdrop; _j++)); do
      rm -f "${_weekly_files[_j]}"
      log "INFO" "Removido backup semanal antigo: $(basename "${_weekly_files[_j]}")"
    done
  fi

  # Relatório final de retention
  local final_daily_count=0 final_weekly_count=0
  if [ "$DRY_RUN" = false ]; then
    final_daily_count="$(find "$daily_dir" -maxdepth 1 -name "${PREFIX}-*.dump.gz" 2>/dev/null | wc -l)"
    final_weekly_count="$(find "$weekly_dir" -maxdepth 1 -name "${PREFIX}-*.weekly.dump.gz" 2>/dev/null | wc -l)"
  fi
  log "INFO" "Retention concluída | Diários: $final_daily_count | Semanais: $final_weekly_count"
}

# ─── Execução principal ─────────────────────────────────────────────────────

_resolve_backup_base() {
  # sshfs mounts remote dir at MOUNT_POINT → base is mount point.
  # NFS mounts volume root → optional REMOTE_DIR subdirectory under mount.
  if [ -n "$NFS_EXPORT" ] || [[ "${STORAGE_BOX_SSH:-}" == nfs://* ]] \
    || { [ -n "${STORAGE_BOX_SSH:-}" ] && [[ "$STORAGE_BOX_SSH" == *":/"* ]] && [[ "$STORAGE_BOX_SSH" != *@* ]]; }; then
    if [ -n "${REMOTE_DIR}" ]; then
      echo "${MOUNT_POINT%/}/${REMOTE_DIR#/}"
    else
      echo "$MOUNT_POINT"
    fi
  else
    echo "$MOUNT_POINT"
  fi
}

# Se apenas retention, não precisa de DSN nem Storage Box
if [ "$MODE" = "retention-only" ]; then
  log "INFO" "Modo: apenas retention (armazenamento local)"

  if _offsite_configured; then
    mount_storage_box || exit $?
    BACKUP_BASE="$(_resolve_backup_base)"
  else
    BACKUP_BASE="${BACKUP_REMOTE_DIR}"
    mkdir -p "$BACKUP_BASE/daily" "$BACKUP_BASE/weekly"
  fi

  do_retention "$BACKUP_BASE"
  _offsite_configured && umount_storage_box
  log "INFO" "=== Retention concluída ==="
  exit 0
fi

# Backup completo
# 1. Monta destino off-site (NFS ou sshfs)
log "INFO" "Passo 1/4: Montando destino off-site"
mount_storage_box || exit $?
BACKUP_BASE="$(_resolve_backup_base)"

# 2. Garante diretórios
log "INFO" "Passo 2/4: Garantindo diretórios de backup"
ensure_remote_dirs "$BACKUP_BASE"

# 3. Executa backup
log "INFO" "Passo 3/4: Executando pg_dump"
if ! do_backup "$BACKUP_BASE"; then
  backup_exit=$?
  umount_storage_box
  exit "$backup_exit"
fi

# 4. Executa retention
log "INFO" "Passo 4/4: Executando retention"
do_retention "$BACKUP_BASE"

# Desmonta Storage Box
umount_storage_box

log "INFO" "=== Backup concluído com sucesso ==="
exit 0

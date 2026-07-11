#!/usr/bin/env bash
# =============================================================================
# restore-database.sh — Restore de Backup PostgreSQL
# =============================================================================
# Restaura um backup do banco PostgreSQL a partir de arquivo .dump.gz
# gerado pelo script backup-database.sh.
#
# Uso:
#   ./scripts/restore-database.sh <arquivo.dump.gz>            # Restaura completo
#   ./scripts/restore-database.sh <arquivo.dump.gz> --list     # Lista conteúdo
#   ./scripts/restore-database.sh <arquivo.dump.gz> --schema-only  # Apenas schema
#   ./scripts/restore-database.sh <arquivo.dump.gz> --data-only    # Apenas dados
#   ./scripts/restore-database.sh --help                       # Ajuda
#
# Configuração via variáveis de ambiente:
#   LOCAL_DATALAKE_DSN     - PostgreSQL DSN de destino (obrigatório)
#   PGRESTORE_JOBS         - Paralelismo do pg_restore (def: 4)
#
# Dependências:
#   - pg_restore (PostgreSQL client)
#   - gzip
#   - psql (para criar database se necessário)
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

DSN="${LOCAL_DATALAKE_DSN:-}"
PG_JOBS="${PGRESTORE_JOBS:-4}"
BACKUP_FILE=""
MODE="restore"  # restore | list | schema-only | data-only

# ─── Funções ────────────────────────────────────────────────────────────────

usage() {
  cat <<EOF
Uso: $0 <arquivo.dump.gz> [opções]

Argumentos:
  <arquivo.dump.gz>   Caminho para o arquivo de backup .dump.gz

Opções:
  --list              Lista o conteúdo do backup sem restaurar
  --schema-only       Restaura apenas o schema (estrutura)
  --data-only         Restaura apenas os dados
  --help              Exibe esta mensagem

Variáveis de ambiente:
  LOCAL_DATALAKE_DSN  - PostgreSQL DSN de destino (obrigatório)
  PGRESTORE_JOBS      - Paralelismo do pg_restore (default: 4)

Exemplos:
  # Listar conteúdo do backup
  $0 backups/pncp_datalake-2026-07-11.dump.gz --list

  # Restaurar backup completo
  $0 backups/pncp_datalake-2026-07-11.dump.gz

  # Restaurar apenas estrutura (para recriar schema vazio)
  $0 backups/pncp_datalake-2026-07-11.dump.gz --schema-only

  # Restaurar apenas dados (schema existente)
  $0 backups/pncp_datalake-2026-07-11.dump.gz --data-only
EOF
  exit 0
}

die() {
  echo "ERRO: $*" >&2
  exit 1
}

# ─── Parse de argumentos ────────────────────────────────────────────────────

while [ $# -gt 0 ]; do
  case "$1" in
    --list)         MODE="list"; shift ;;
    --schema-only)  MODE="schema-only"; shift ;;
    --data-only)    MODE="data-only"; shift ;;
    --help)         usage ;;
    -*)
      # Assume que é o arquivo
      if [ -z "$BACKUP_FILE" ]; then
        BACKUP_FILE="$1"; shift
      else
        die "Opção desconhecida: $1"
      fi
      ;;
    *)
      if [ -z "$BACKUP_FILE" ]; then
        BACKUP_FILE="$1"; shift
      else
        die "Múltiplos arquivos fornecidos: $1"
      fi
      ;;
  esac
done

# ─── Verificações ───────────────────────────────────────────────────────────

# Ajuda se sem argumentos
if [ -z "$BACKUP_FILE" ]; then
  usage
fi

# Verifica dependências
for cmd in pg_restore gzip; do
  if ! command -v "$cmd" &>/dev/null; then
    die "Comando não encontrado: $cmd"
  fi
done

if [ "$MODE" = "restore" ] || [ "$MODE" = "schema-only" ] || [ "$MODE" = "data-only" ]; then
  if ! command -v psql &>/dev/null; then
    die "psql não encontrado (necessário para verificar/criar database)"
  fi
fi

# Verifica DSN
if [ -z "$DSN" ]; then
  die "LOCAL_DATALAKE_DSN não configurada. Defina no .env ou exporte a variável."
fi

# Verifica backup
if [ ! -f "$BACKUP_FILE" ]; then
  die "Arquivo de backup não encontrado: $BACKUP_FILE"
fi

if [ ! -r "$BACKUP_FILE" ]; then
  die "Arquivo de backup sem permissão de leitura: $BACKUP_FILE"
fi

# Verifica integridade do gzip
if ! gzip -t "$BACKUP_FILE" 2>/dev/null; then
  die "Arquivo de backup corrompido (gzip inválido): $BACKUP_FILE"
fi

echo "Arquivo de backup: $BACKUP_FILE"
echo "DSN de destino:    $(echo "$DSN" | sed 's/:[^:@]*@/:****@/')"  # oculta senha
echo "Modo:              $MODE"
echo ""

# ─── Listagem ────────────────────────────────────────────────────────────────

if [ "$MODE" = "list" ]; then
  echo "=== Conteúdo do Backup ==="
  gzip -dc "$BACKUP_FILE" | pg_restore --list 2>/dev/null || {
    # Se pg_restore --list falhar, tenta com --verbose para diagnóstico
    echo "Tentando listagem detalhada..."
    gzip -dc "$BACKUP_FILE" | pg_restore --list --verbose 2>&1
  }
  exit $?
fi

# ─── Preparação do banco de destino ─────────────────────────────────────────

# Extrai database name do DSN
DB_NAME="$(echo "$DSN" | sed 's/.*\/\([^?]*\).*/\1/' | sed 's/\/$//')"
if [ -z "$DB_NAME" ]; then
  DB_NAME="pncp_datalake"
fi

echo "Database alvo: $DB_NAME"

# Verifica se database existe, senão cria
if [ "$MODE" = "restore" ] || [ "$MODE" = "schema-only" ] || [ "$MODE" = "data-only" ]; then
  # Conecta ao postgres default database para verificar
  ADMIN_DSN="$(echo "$DSN" | sed 's|/[^/]*$|/postgres|')"
  if psql "$ADMIN_DSN" -t -c "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" 2>/dev/null | grep -q 1; then
    echo "Database '$DB_NAME' já existe."
    if [ "$MODE" = "restore" ] || [ "$MODE" = "schema-only" ]; then
      echo "ATENÇÃO: A restauração pode sobrescrever objetos existentes."
      echo "Recomenda-se dropar e recriar o database antes para restauração limpa:"
      echo "  psql '$ADMIN_DSN' -c 'DROP DATABASE IF EXISTS $DB_NAME;'"
      echo "  psql '$ADMIN_DSN' -c 'CREATE DATABASE $DB_NAME;'"
      echo ""
      echo "Continuando em 3 segundos... (CTRL+C para abortar)"
      sleep 3
    fi
  else
    echo "Criando database '$DB_NAME'..."
    psql "$ADMIN_DSN" -c "CREATE DATABASE $DB_NAME;" || die "Falha ao criar database"
    echo "Database criado com sucesso."
  fi
fi

# ─── Execução do restore ────────────────────────────────────────────────────

RESTORE_ARGS=()

case "$MODE" in
  restore)
    echo "=== Restaurando backup completo ==="
    RESTORE_ARGS=(
      "--dbname=$DSN"
      "--jobs=$PG_JOBS"
      "--verbose"
      "--clean"        # Drop objects before restore (limpeza)
      "--if-exists"    # Evita erros se objeto não existir
    )
    ;;
  schema-only)
    echo "=== Restaurando apenas schema ==="
    RESTORE_ARGS=(
      "--dbname=$DSN"
      "--jobs=$PG_JOBS"
      "--verbose"
      "--schema-only"
      "--clean"
      "--if-exists"
    )
    ;;
  data-only)
    echo "=== Restaurando apenas dados ==="
    RESTORE_ARGS=(
      "--dbname=$DSN"
      "--jobs=$PG_JOBS"
      "--verbose"
      "--data-only"
      "--disable-triggers"  # Desativa triggers durante carga para performance
    )
    ;;
esac

echo "Comando: gzip -dc \"$BACKUP_FILE\" | pg_restore ${RESTORE_ARGS[*]}"
echo "Iniciando restauração em $(date '+%Y-%m-%d %H:%M:%S %z')..."
echo ""

START_TIME="$(date +%s)"

if gzip -dc "$BACKUP_FILE" | pg_restore "${RESTORE_ARGS[@]}" 2>&1; then
  END_TIME="$(date +%s)"
  DURATION=$(( END_TIME - START_TIME ))
  echo ""
  echo "=== Restauração concluída com sucesso em ${DURATION}s ==="
else
  END_TIME="$(date +%s)"
  DURATION=$(( END_TIME - START_TIME ))
  echo ""
  echo "=== Restauração FALHOU após ${DURATION}s ===" >&2
  echo "Verifique os logs acima para detalhes." >&2
  exit 1
fi

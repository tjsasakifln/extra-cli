#!/usr/bin/env bash
# =============================================================================
# apply-migrations.sh — Aplica migrations v2/v3 com tracking
# =============================================================================
# Story TD-2.1: Reconstruir Migrations do Zero
# AC-8: Deve existir um comando para aplicar migrations futuras
#
# Uso:
#   bash scripts/apply-migrations.sh                         # Aplica migrations pendentes
#   bash scripts/apply-migrations.sh --dsn <DSN>             # DSN explicito
#   bash scripts/apply-migrations.sh --dry-run               # Simula sem aplicar
#   bash scripts/apply-migrations.sh --status                # Status das migrations
#   bash scripts/apply-migrations.sh --help                  # Ajuda
#
# Comportamento:
#   1. Cria a tabela _migrations se nao existir
#   2. Lista arquivos .sql em supabase/migrations/ em ordem alfabetica
#   3. Para cada arquivo nao registrado em _migrations:
#      a. Calcula checksum SHA256
#      b. Aplica via psql
#      c. Registra em _migrations (version, name, checksum)
#   4. Reporta resultado
#
# Version naming:
#   - A versao e o filename stem (ex: "001-v2_initial_schema" para
#     "001-v2_initial_schema.sql")
#   - _migrations.sql e _migrations.sql arquivos de tracking sao ignorados
#
# Dependencias:
#   - psql (PostgreSQL client)
#   - sha256sum (coreutils)
#   - LOCAL_DATALAKE_DSN configurado em .env
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
MIGRATIONS_DIR="$PROJECT_DIR/supabase/migrations"

# ─── Config ─────────────────────────────────────────────────────────────────

if [ -f "$PROJECT_DIR/.env" ]; then
  set -a
  source "$PROJECT_DIR/.env"
  set +a
fi

DSN="${LOCAL_DATALAKE_DSN:-}"
DRY_RUN=false

# ─── Help ────────────────────────────────────────────────────────────────────

show_help() {
    sed -n '/^#/p' "${BASH_SOURCE[0]}" | head -30 | sed 's/^# //;s/^#//'
    exit 0
}

# ─── Utils ──────────────────────────────────────────────────────────────────

error() { echo "ERRO: $*" >&2; exit 1; }
info()  { echo "  ◆ $*"; }
ok()    { echo "  ✅ $*"; }
warn()  { echo "  ⚠️  $*"; }

compute_checksum() {
    sha256sum "$1" | cut -d' ' -f1
}

# Extract version from migration filename (stem without .sql)
file_version() {
    local f="$1"
    basename "$f" .sql
}

psql_exec() {
    if [ "$DRY_RUN" = true ]; then
        echo "    [DRY-RUN] psql $DSN -f \"$1\""
        return 0
    fi
    psql "$DSN" -f "$1" -v ON_ERROR_STOP=1 > /dev/null 2>&1
}

psql_cmd() {
    if [ "$DRY_RUN" = true ]; then
        echo "    [DRY-RUN] $1"
        return 0
    fi
    psql "$DSN" -t -A -c "$1" 2>/dev/null
}

# ─── List all migration files (sorted, excluding _migrations) ─────────────

list_all_files() {
    find "$MIGRATIONS_DIR" -maxdepth 1 -name '*.sql' ! -name '_migrations.sql' | sort
}

# ─── Get applied versions from DB ─────────────────────────────────────────

get_applied_versions() {
    psql_cmd "SELECT version FROM public._migrations ORDER BY version" 2>/dev/null || echo ""
}

# ─── Ensure tracking table ──────────────────────────────────────────────────

ensure_tracking_table() {
    local sql="$MIGRATIONS_DIR/_migrations.sql"

    if [ ! -f "$sql" ]; then
        error "Arquivo _migrations.sql nao encontrado em $sql"
    fi

    info "Garantindo tabela de tracking..."
    psql_exec "$sql"
    ok "Tabela _migrations pronta"
}

# ─── List pending migrations ────────────────────────────────────────────────

list_pending() {
    local applied
    applied=$(get_applied_versions)

    while IFS= read -r f; do
        [ -z "$f" ] && continue
        local version
        version=$(file_version "$f")

        if echo "$applied" | grep -qxF "$version"; then
            continue
        fi
        echo "$f|$version"
    done < <(list_all_files)
}

# ─── Apply migrations ───────────────────────────────────────────────────────

cmd_apply() {
    echo "=== Aplicando migrations pendentes ==="
    echo ""

    if [ -z "$DSN" ]; then
        error "LOCAL_DATALAKE_DSN nao definido. Configure no .env ou use --dsn."
    fi

    ensure_tracking_table

    local pending=()
    while IFS='|' read -r path version; do
        [ -z "$path" ] && continue
        pending+=("$path|$version")
    done < <(list_pending)

    if [ ${#pending[@]} -eq 0 ]; then
        ok "Nenhuma migration pendente."
        return 0
    fi

    echo "  Pendentes: ${#pending[@]} migrations"
    echo ""

    for entry in "${pending[@]}"; do
        local path="${entry%%|*}"
        local version="${entry##*|}"
        local name
        name=$(basename "$path")
        local checksum
        checksum=$(compute_checksum "$path")

        echo "  Aplicando: $name"
        echo "    Version: $version"
        echo "    Checksum: $checksum"

        if [ "$DRY_RUN" = true ]; then
            echo "    [DRY-RUN] psql $DSN -f \"$path\""
        else
            info "Executando SQL..."
            psql_exec "$path" || error "Falha ao aplicar $name"

            info "Registrando em _migrations..."
            psql_cmd "
                INSERT INTO public._migrations (version, name, applied_at, checksum)
                VALUES ('$version', '$name', NOW(), '$checksum')
                ON CONFLICT (version) DO NOTHING;
            " || warn "Falha ao registrar $version em _migrations"
        fi

        ok "$name aplicada"
        echo ""
    done

    echo "=== Todas as migrations aplicadas com sucesso ==="
}

# ─── Status ──────────────────────────────────────────────────────────────────

cmd_status() {
    echo "=== Status das migrations ==="
    echo ""

    local applied=""
    local conn_ok=false

    if [ -n "$DSN" ]; then
        applied=$(psql_cmd "
            SELECT version, name, applied_at::TEXT FROM public._migrations ORDER BY version
        ") && conn_ok=true
    fi

    if [ "$conn_ok" = false ]; then
        # Tentar conexao local (peer auth)
        applied=$(sudo -u postgres psql -d pncp_datalake -t -A -c "
            SELECT version, name, applied_at::TEXT FROM public._migrations ORDER BY version
        " 2>/dev/null) && conn_ok=true
    fi

    if [ "$conn_ok" = false ]; then
        warn "Nao foi possivel conectar ao banco."
        echo ""
        echo "Arquivos de migration disponiveis:"
        while IFS= read -r f; do
            echo "  - $(basename "$f")"
        done < <(list_all_files)
        return 0
    fi

    echo "  Migrations aplicadas ($(echo "$applied" | grep -c . || echo 0)):"
    echo ""
    if [ -z "$applied" ]; then
        echo "    (nenhuma)"
        echo ""
    else
        echo "$applied" | while IFS='|' read -r v n a; do
            [ -z "$v" ] && continue
            if [ ${#v} -gt 20 ]; then
                printf "    %-22s %-30s %s\n" "${v:0:20}..." "$n" "$a"
            else
                printf "    %-22s %-30s %s\n" "$v" "$n" "$a"
            fi
        done
        echo ""
    fi

    echo "  Arquivos de migration:"
    echo ""
    local any_pending=false
    while IFS= read -r f; do
        [ -z "$f" ] && continue
        local version
        local name
        local checksum
        version=$(file_version "$f")
        name=$(basename "$f")
        checksum=$(compute_checksum "$f" 2>/dev/null || echo "?")

        if echo "$applied" | grep -q "^$version|"; then
            ok "$name (aplicada, checksum: ${checksum:0:12})"
        else
            warn "$name (PENDENTE, checksum: ${checksum:0:12})"
            any_pending=true
        fi
    done < <(list_all_files)

    if [ "$any_pending" = true ]; then
        echo ""
        warn "Existem migrations pendentes. Execute 'bash scripts/apply-migrations.sh' para aplicar."
    fi
}

# ─── Main ────────────────────────────────────────────────────────────────────

case "${1:-}" in
    --apply|--update)  shift; cmd_apply "$@" ;;
    --status)          cmd_status ;;
    --dry-run)         DRY_RUN=true; cmd_apply ;;
    --dsn)             shift; DSN="$1"; cmd_apply ;;
    --help)            show_help ;;
    *)                 cmd_apply ;;
esac

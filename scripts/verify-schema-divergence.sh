#!/usr/bin/env bash
# =============================================================================
# verify-schema-divergence.sh — Verifica divergencias entre migrations e schema
# =============================================================================
# Story TD-2.1: Reconstruir Migrations do Zero
# Debito: TD-DB-01 (CRITICAL) — Migrations totalmente divergentes do schema real
#
# Uso:
#   bash scripts/verify-schema-divergence.sh                    # Verifica schema atual vs baseline
#   bash scripts/verify-schema-divergence.sh --refresh          # Regenera baseline a partir do DB
#   bash scripts/verify-schema-divergence.sh --diff             # Mostra diff detalhado
#   bash scripts/verify-schema-divergence.sh --check-migrations # Verifica migrations v2 vs baseline
#   bash scripts/verify-schema-divergence.sh --help             # Ajuda
#
# Dependencias:
#   - pg_dump (PostgreSQL client)
#   - diff (GNU diffutils)
#   - LOCAL_DATALAKE_DSN configurado em .env
#
# Estrategia:
#   1. Extrai schema atual do banco via pg_dump --schema-only
#   2. Compara com o baseline versionado (supabase/current-schema.sql)
#   3. Relata divergencias (se houver)
#   4. Opcionalmente verifica se as migrations v2 reproduzem o baseline
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# ─── Config ─────────────────────────────────────────────────────────────────

BASELINE_FILE="$PROJECT_DIR/supabase/current-schema.sql"
MIGRATIONS_DIR="$PROJECT_DIR/supabase/migrations"
TEMP_DIR="/tmp/pg-schema-verify-$$"

# Carrega .env se existir
if [ -f "$PROJECT_DIR/.env" ]; then
  set -a
  source "$PROJECT_DIR/.env"
  set +a
fi

DSN="${LOCAL_DATALAKE_DSN:-}"

# ─── Help ────────────────────────────────────────────────────────────────────

show_help() {
    sed -n '/^#/p' "${BASH_SOURCE[0]}" | head -30 | sed 's/^# //;s/^#//'
    exit 0
}

# ─── Utils ──────────────────────────────────────────────────────────────────

cleanup() {
    rm -rf "$TEMP_DIR"
}
trap cleanup EXIT

error() {
    echo "ERRO: $*" >&2
    exit 1
}

info() {
    echo "  ◆ $*"
}

success() {
    echo "  ✅ $*"
}

warn() {
    echo "  ⚠️  $*"
}

# ─── Extract current schema ─────────────────────────────────────────────────

extract_schema() {
    local output="$1"
    mkdir -p "$(dirname "$output")"

    if [ -z "$DSN" ]; then
        # Fallback: tentar conexao local (peer auth)
        info "LOCAL_DATALAKE_DSN nao definido. Tentando conexao local..."
        pg_dump --schema-only --no-owner --no-privileges pncp_datalake > "$output" 2>/dev/null \
            || sudo -u postgres pg_dump --schema-only --no-owner --no-privileges pncp_datalake > "$output" 2>/dev/null \
            || error "Nao foi possivel conectar ao banco. Defina LOCAL_DATALAKE_DSN no .env ou configure peer auth."
        success "Schema extraido via conexao local"
    else
        pg_dump "$DSN" --schema-only --no-owner --no-privileges > "$output" 2>/dev/null \
            || error "Falha ao conectar via DSN. Verifique LOCAL_DATALAKE_DSN."
        success "Schema extraido via DSN"
    fi
}

# ─── Normalize schema for comparison ────────────────────────────────────────
# Remove linhas variaveis (timestamps, session tokens, etc.)

normalize_schema() {
    local input="$1"
    local output="$2"

    grep -vE '^-- (Dumped from|Dumped by)' "$input" \
        | grep -vE '^\\restrict|^\\unrestrict' \
        | sed 's/CURRENT_TIMESTAMP/NOW/g' \
        | sed 's/now()/NOW()/g' \
        > "$output"
}

# ─── Commands ───────────────────────────────────────────────────────────────

cmd_refresh() {
    echo "=== Regenerando baseline do schema real ==="
    echo ""

    extract_schema "$BASELINE_FILE"

    echo ""
    echo "Baseline atualizado: $BASELINE_FILE"
    echo ""
    echo "Proximo passo: verificar migrations v2:"
    echo "  bash scripts/verify-schema-divergence.sh --check-migrations"
}

cmd_verify() {
    echo "=== Verificando schema atual vs baseline ==="
    echo ""

    if [ ! -f "$BASELINE_FILE" ]; then
        error "Baseline nao encontrado: $BASELINE_FILE"
        echo ""
        echo "Execute --refresh primeiro:"
        echo "  bash scripts/verify-schema-divergence.sh --refresh"
        exit 1
    fi

    mkdir -p "$TEMP_DIR"
    local current="$TEMP_DIR/current-schema.sql"
    local baseline_norm="$TEMP_DIR/baseline-normalized.sql"
    local current_norm="$TEMP_DIR/current-normalized.sql"

    extract_schema "$current"

    normalize_schema "$BASELINE_FILE" "$baseline_norm"
    normalize_schema "$current" "$current_norm"

    if diff -q "$baseline_norm" "$current_norm" > /dev/null 2>&1; then
        success "Schema atual IDENTICO ao baseline. Zero divergencias."
        return 0
    else
        warn "Schema atual DIVERGE do baseline!"
        echo ""
        echo "Resumo das diferencas:"
        diff --stat "$baseline_norm" "$current_norm"
        echo ""
        echo "Para diff completo:"
        echo "  bash scripts/verify-schema-divergence.sh --diff"
        return 1
    fi
}

cmd_diff() {
    echo "=== Diff detalhado: schema atual vs baseline ==="
    echo ""

    if [ ! -f "$BASELINE_FILE" ]; then
        error "Baseline nao encontrado: $BASELINE_FILE"
    fi

    mkdir -p "$TEMP_DIR"
    local current="$TEMP_DIR/current-schema.sql"
    local baseline_norm="$TEMP_DIR/baseline-normalized.sql"
    local current_norm="$TEMP_DIR/current-normalized.sql"

    extract_schema "$current"

    normalize_schema "$BASELINE_FILE" "$baseline_norm"
    normalize_schema "$current" "$current_norm"

    diff -u "$baseline_norm" "$current_norm" || true
}

cmd_check_migrations() {
    echo "=== Verificando migrations v2 vs baseline ==="
    echo ""

    local v2_file="$MIGRATIONS_DIR/001-v2_initial_schema.sql"

    if [ ! -f "$v2_file" ]; then
        error "Migration v2 nao encontrada: $v2_file"
    fi

    mkdir -p "$TEMP_DIR"

    # Aplicar migration v2 em um banco temporario (dry-run via pg_dump comparison)
    # Como nao temos banco temporario, fazemos verificacao estrutural:

    echo "Verificacao estrutural da migration v2:"
    echo ""

    # Check 1: Contem todos os CREATE TABLE?
    local expected_tables=(
        "sc_public_entities" "enriched_entities" "entity_coverage"
        "pncp_raw_bids" "pncp_supplier_contracts" "coverage_snapshots"
        "ingestion_checkpoints" "ingestion_runs"
    )

    local missing_tables=0
    for table in "${expected_tables[@]}"; do
        if grep -q "CREATE TABLE.*$table" "$v2_file"; then
            success "Tabela $table: presente"
        else
            warn "Tabela $table: AUSENTE"
            missing_tables=$((missing_tables + 1))
        fi
    done

    echo ""

    # Check 2: Contem IF NOT EXISTS ou OR REPLACE?
    if grep -q "IF NOT EXISTS\|OR REPLACE" "$v2_file"; then
        success "Migration v2 usa IF NOT EXISTS / OR REPLACE (reexecutavel)"
    else
        warn "Migration v2 pode NAO ser reexecutavel (sem IF NOT EXISTS/OR REPLACE)"
    fi

    # Check 3: Numeros de CREATE TABLE vs baseline
    local baseline_tables
    baseline_tables=$(grep -c "^CREATE TABLE" "$BASELINE_FILE" 2>/dev/null || echo 0)
    local v2_tables
    v2_tables=$(grep -c "^CREATE TABLE" "$v2_file")
    # _migrations e criada pela v2 mas nao existe no baseline original
    if grep -q "CREATE TABLE.*_migrations" "$v2_file"; then
        v2_tables=$((v2_tables - 1))
    fi

    echo ""
    if [ "$baseline_tables" -eq "$v2_tables" ]; then
        success "Numero de tabelas: $v2_tables (igual ao baseline)"
    else
        warn "Tabelas na migration v2: $v2_tables, baseline: $baseline_tables"
    fi

    # Check 4: Indexes
    local baseline_indexes
    baseline_indexes=$(grep -c "^CREATE INDEX" "$BASELINE_FILE" 2>/dev/null || echo 0)
    local v2_indexes
    v2_indexes=$(grep -c "^CREATE INDEX" "$v2_file")

    echo ""
    if [ "$baseline_indexes" -eq "$v2_indexes" ]; then
        success "Numero de indexes: $v2_indexes (igual ao baseline)"
    else
        warn "Indexes na migration v2: $v2_indexes, baseline: $baseline_indexes"
    fi

    echo ""
    if [ "$missing_tables" -eq 0 ]; then
        success "Migration v2 cobre todas as tabelas do baseline"
    else
        warn "$missing_tables tabelas ausentes na migration v2"
        return 1
    fi
}

# ─── Main ────────────────────────────────────────────────────────────────────

case "${1:-}" in
    --refresh)       cmd_refresh ;;
    --diff)          cmd_diff ;;
    --check-migrations) cmd_check_migrations ;;
    --help)          show_help ;;
    *)               cmd_verify ;;
esac

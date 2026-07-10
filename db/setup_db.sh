#!/bin/bash
# setup_db.sh — Apply all migrations and seed the database
# Usage: bash db/setup_db.sh [DSN]

set -euo pipefail

DSN="${1:-${LOCAL_DATALAKE_DSN:-postgresql://postgres:smartlic_local@127.0.0.1:54399/postgres}}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
MIGRATIONS_DIR="$SCRIPT_DIR/migrations"

echo "🔧 Setting up Extra Consultoria DataLake..."
echo "   DSN: ${DSN%%@*}@***"

# Apply migrations in order
for migration in "$MIGRATIONS_DIR"/*.sql; do
    name="$(basename "$migration")"
    echo "   Applying: $name"
    psql "$DSN" -f "$migration" -v ON_ERROR_STOP=1 > /dev/null 2>&1
    echo "   ✅ $name"
done

echo ""
echo "📋 Seeding SC public entities..."
python3 "$SCRIPT_DIR/seed/001_sc_entities.py" --dsn "$DSN" --truncate

echo ""
echo "✅ Database setup complete!"
echo ""
echo "   Run verification:"
echo "   psql $DSN -c \"SELECT count(*) FROM sc_public_entities\""
echo "   psql $DSN -c \"SELECT source, count(*) FROM entity_coverage GROUP BY source\""

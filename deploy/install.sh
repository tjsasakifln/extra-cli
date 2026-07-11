#!/bin/bash
# install.sh — Install Extra Consultoria on a fresh Hetzner VPS
# Run as root: bash deploy/install.sh

set -euo pipefail

APP_DIR="/opt/extra-consultoria"
APP_USER="extra-consultoria"

echo "============================================"
echo " Extra Consultoria — Instalação VPS"
echo "============================================"

# ---- System ----
echo ""
echo "📦 Installing system packages..."
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv postgresql postgresql-client > /dev/null

# ---- User ----
if ! id "$APP_USER" &>/dev/null; then
    useradd -m -s /bin/bash "$APP_USER"
    echo "✅ User $APP_USER created"
fi

# ---- Database ----
echo ""
echo "🐘 Configuring PostgreSQL..."
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='pncp_datalake'" | grep -q 1 || \
    sudo -u postgres createdb pncp_datalake

sudo -u postgres psql -c "ALTER USER postgres PASSWORD '${PG_PASSWORD:-smartlic_local}'" > /dev/null 2>&1 || true

# ---- App directory ----
echo ""
echo "📁 Setting up app directory..."
mkdir -p "$APP_DIR"
cp -r . "$APP_DIR"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

# ---- Python ----
echo ""
echo "🐍 Installing Python dependencies..."
cd "$APP_DIR"
pip3 install -q -r requirements.txt

# ---- Database setup ----
echo ""
echo "🗄️ Applying migrations..."
bash "$APP_DIR/db/setup_db.sh" "${LOCAL_DATALAKE_DSN:-postgresql://postgres:smartlic_local@127.0.0.1:5432/pncp_datalake}"

# ---- Systemd timers ----
echo ""
echo "⏰ Installing systemd timers..."
cp "$APP_DIR/deploy/systemd/"*.service /etc/systemd/system/
cp "$APP_DIR/deploy/systemd/"*.timer /etc/systemd/system/
systemctl daemon-reload

# Enable and start all timers
for timer in pncp-crawl-full pncp-crawl-inc coverage-report \
             dom-sc-crawl pcp-crawl compras-gov-crawl \
             pncp-contracts pncp-enrich pncp-purge pncp-report-weekly; do
    systemctl enable "${timer}.timer"
    systemctl start "${timer}.timer"
done

# ---- Done ----
echo ""
echo "============================================"
echo " ✅ Extra Consultoria instalado!"
echo "============================================"
echo ""
echo "   App:    $APP_DIR"
echo "   DB:     pncp_datalake"
echo "   Timers: $(systemctl list-timers pncp-* coverage-* --no-pager 2>/dev/null | grep -E 'pncp|coverage' || echo 'check with: systemctl list-timers')"
echo ""
echo "   Verificar:"
echo "     systemctl status pncp-crawl-full.timer"
echo "     journalctl -u pncp-crawl-full.service -f"
echo "     python3 $APP_DIR/scripts/crawl/monitor.py --report-coverage"
echo ""

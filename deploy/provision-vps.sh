#!/bin/bash
# provision-vps.sh — Provision a fresh Hetzner VPS for Extra Consultoria
# Extra Consultoria — Story FEAT-4.1: Provisionar Hetzner VPS
#
# Usage:
#   1. Boot CX22 VPS on Hetzner Cloud (Ubuntu 24.04 LTS)
#   2. SSH in as root: ssh root@<VPS_IP>
#   3. bash <(curl -fsSL https://raw.githubusercontent.com/extra-consultoria/main/deploy/provision-vps.sh)
#
# Or copy and run locally:
#   scp deploy/provision-vps.sh root@<VPS_IP>:/root/
#   ssh root@<VPS_IP> bash /root/provision-vps.sh

set -euo pipefail

# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────

APP_USER="extra-consultoria"
APP_DIR="/opt/extra-consultoria"
REPO_URL="${REPO_URL:-https://github.com/extra-consultoria/extra-consultoria.git}"
REPO_BRANCH="${REPO_BRANCH:-main}"
SSH_PORT="${SSH_PORT:-2222}"
TIMEZONE="America/Sao_Paulo"

# ──────────────────────────────────────────────────────────────────────────────
# Colors & helpers
# ──────────────────────────────────────────────────────────────────────────────

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; }

check_root() {
    if [[ $EUID -ne 0 ]]; then
        error "This script must be run as root"
        exit 1
    fi
}

# ──────────────────────────────────────────────────────────────────────────────
# Step 1: System packages & timezone
# ──────────────────────────────────────────────────────────────────────────────

install_system_packages() {
    info "Step 1/10: Installing system packages..."

    apt-get update -qq
    apt-get upgrade -y -qq
    apt-get install -y -qq \
        python3 python3-pip python3-venv \
        postgresql postgresql-client \
        sshfs gzip curl wget git \
        ufw fail2ban \
        htop iotop nload \
        unattended-upgrades \
        prometheus-node-exporter \
        > /dev/null

    # Set timezone
    timedatectl set-timezone "$TIMEZONE"
    info "Timezone set to $TIMEZONE"
}

# ──────────────────────────────────────────────────────────────────────────────
# Step 2: Create application user
# ──────────────────────────────────────────────────────────────────────────────

create_app_user() {
    info "Step 2/10: Creating application user..."

    if ! id "$APP_USER" &>/dev/null; then
        useradd -m -s /bin/bash -G sudo "$APP_USER"
        info "User $APP_USER created"
    else
        info "User $APP_USER already exists"
    fi

    # Passwordless sudo for deploy operations
    echo "$APP_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl, /usr/bin/journalctl" > /etc/sudoers.d/extra-consultoria
    chmod 440 /etc/sudoers.d/extra-consultoria
}

# ──────────────────────────────────────────────────────────────────────────────
# Step 3: SSH hardening
# ──────────────────────────────────────────────────────────────────────────────

harden_ssh() {
    info "Step 3/10: Hardening SSH..."

    # Change SSH port
    sed -i "s/^#Port 22/Port $SSH_PORT/" /etc/ssh/sshd_config
    sed -i "s/^Port 22/Port $SSH_PORT/" /etc/ssh/sshd_config

    # Disable root password login (key-only)
    sed -i 's/^#PermitRootLogin prohibit-password/PermitRootLogin without-password/' /etc/ssh/sshd_config
    sed -i 's/^PermitRootLogin yes/PermitRootLogin without-password/' /etc/ssh/sshd_config

    # Disable password authentication
    sed -i 's/^#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
    sed -i 's/^PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config

    # Disable X11 forwarding
    sed -i 's/^X11Forwarding yes/X11Forwarding no/' /etc/ssh/sshd_config

    systemctl restart sshd
    info "SSH configured on port $SSH_PORT (key-only)"
    warn "Keep this SSH session open! Test new connection before closing."
}

# ──────────────────────────────────────────────────────────────────────────────
# Step 4: Firewall (ufw)
# ──────────────────────────────────────────────────────────────────────────────

configure_firewall() {
    info "Step 4/10: Configuring firewall..."

    ufw --force reset
    ufw default deny incoming
    ufw default allow outgoing

    # SSH on custom port
    ufw allow "$SSH_PORT/tcp" comment "SSH custom port"

    # Node exporter for monitoring — restrict to known monitoring IPs
    # IMPORTANTE: Substitua MONITORING_IPS abaixo pelos IPs reais do Prometheus/Grafana
    # Exemplo: ufw allow from 10.0.0.0/8 to any port 9100 proto tcp
    if [[ -n "${MONITORING_IPS:-}" ]]; then
        for ip in $MONITORING_IPS; do
            ufw allow from "$ip" to any port 9100 proto tcp comment "Prometheus node exporter"
        done
        info "Node exporter restricted to: $MONITORING_IPS"
    else
        warn "MONITORING_IPS not set — node exporter port 9100 NOT opened. Set MONITORING_IPS env var."
    fi

    # Enable
    ufw --force enable
    info "Firewall enabled. Open ports: $SSH_PORT/tcp (+ node exporter if MONITORING_IPS configured)"
}

# ──────────────────────────────────────────────────────────────────────────────
# Step 5: Fail2ban
# ──────────────────────────────────────────────────────────────────────────────

configure_fail2ban() {
    info "Step 5/10: Configuring fail2ban..."

    cat > /etc/fail2ban/jail.local << 'EOF'
[sshd]
enabled = true
port = {{SSH_PORT}}
maxretry = 3
bantime = 3600
findtime = 600
EOF
    sed -i "s/{{SSH_PORT}}/$SSH_PORT/" /etc/fail2ban/jail.local

    systemctl enable fail2ban
    systemctl restart fail2ban
    info "Fail2ban configured"
}

# ──────────────────────────────────────────────────────────────────────────────
# Step 6: PostgreSQL
# ──────────────────────────────────────────────────────────────────────────────

configure_postgresql() {
    info "Step 6/10: Configuring PostgreSQL..."

    # Listen only on localhost
    sed -i "s/^#listen_addresses = 'localhost'/listen_addresses = 'localhost'/" /etc/postgresql/*/main/postgresql.conf
    sed -i "s/^listen_addresses = '*'/listen_addresses = 'localhost'/" /etc/postgresql/*/main/postgresql.conf

    # Tune for CX22 (2 vCPU, 4 GB RAM)
    cat >> /etc/postgresql/*/main/postgresql.conf << 'EOF'

# ── Extra Consultoria tuning (CX22: 2 vCPU, 4 GB RAM) ──
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

    systemctl enable postgresql
    systemctl restart postgresql

    # Create database
    sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='pncp_datalake'" | grep -q 1 || \
        sudo -u postgres createdb pncp_datalake

    # Set password
    PG_PASSWORD="${PG_PASSWORD:-$(openssl rand -base64 24)}"
    sudo -u postgres psql -c "ALTER USER postgres PASSWORD '${PG_PASSWORD}'" > /dev/null 2>&1 || true

    info "PostgreSQL configured. Database 'pncp_datalake' created."
    warn "Save this password: PG_PASSWORD=${PG_PASSWORD}"
}

# ──────────────────────────────────────────────────────────────────────────────
# Step 7: Clone repository & install dependencies
# ──────────────────────────────────────────────────────────────────────────────

deploy_application() {
    info "Step 7/10: Deploying application..."

    if [[ -d "$APP_DIR/.git" ]]; then
        cd "$APP_DIR"
        git pull origin "$REPO_BRANCH"
    else
        git clone --branch "$REPO_BRANCH" "$REPO_URL" "$APP_DIR"
    fi

    cd "$APP_DIR"
    chown -R "$APP_USER:$APP_USER" "$APP_DIR"

    # Python dependencies
    if [[ -f requirements.txt ]]; then
        pip3 install -q -r requirements.txt
    fi

    # Copy .env if not exists
    if [[ ! -f "$APP_DIR/.env" ]]; then
        if [[ -f "$APP_DIR/.env.example" ]]; then
            cp "$APP_DIR/.env.example" "$APP_DIR/.env"
            info "Created .env from .env.example — EDIT with real credentials!"
        else
            warn "No .env.example found. Create $APP_DIR/.env manually."
        fi
    fi
}

# ──────────────────────────────────────────────────────────────────────────────
# Step 8: Database migrations & seeds
# ──────────────────────────────────────────────────────────────────────────────

setup_database() {
    info "Step 8/10: Running database migrations and seeds..."

    cd "$APP_DIR"
    bash db/setup_db.sh "${LOCAL_DATALAKE_DSN:-postgresql://postgres:${PG_PASSWORD:-smartlic_local}@127.0.0.1:5432/pncp_datalake}"
    info "Database migrations and seeds applied"
}

# ──────────────────────────────────────────────────────────────────────────────
# Step 9: Systemd timers (13 pairs + onfailure template)
# ──────────────────────────────────────────────────────────────────────────────

install_systemd_timers() {
    info "Step 9/10: Installing systemd timers..."

    # Copy all service and timer files
    cp "$APP_DIR/deploy/systemd/"*.service /etc/systemd/system/
    cp "$APP_DIR/deploy/systemd/"*.timer /etc/systemd/system/
    systemctl daemon-reload

    # Enable all timers — names MUST match .timer files on disk
    # NOTE: PNCP split into full + incremental + contracts + enrich + purge
    timers=(
        pncp-crawl-full
        pncp-crawl-inc
        pncp-contracts
        pncp-enrich
        pncp-purge
        pncp-report-weekly
        dom-sc-crawl
        pcp-crawl
        compras-gov-crawl
        sc-compras-crawl
        tce-sc-crawl
        transparencia-crawl
        extra-crawl-doe-sc
        extra-crawl-ciga-ckan
        coverage-report
        coverage-report-weekly
        extra-check-alerts
        extra-collect-metrics
        extra-db-backup
        extra-health-check
    )

    for timer in "${timers[@]}"; do
        if [[ -f "/etc/systemd/system/${timer}.timer" ]]; then
            systemctl enable "${timer}.timer"
            systemctl start "${timer}.timer"
            info "  ✓ ${timer}.timer enabled & started"
        else
            warn "  ✗ ${timer}.timer not found — skipping"
        fi
    done

    info "All timers installed"
    systemctl list-timers 'extra-*' --no-pager
}

# ──────────────────────────────────────────────────────────────────────────────
# Step 10: Storage Box & Backup configuration
# ──────────────────────────────────────────────────────────────────────────────

configure_storage_box() {
    info "Step 10/10: Configuring Storage Box..."

    mkdir -p "$APP_DIR/backup-ssh"

    # Generate SSH key for Storage Box access
    if [[ ! -f "$APP_DIR/backup-ssh/id_ed25519" ]]; then
        ssh-keygen -t ed25519 -f "$APP_DIR/backup-ssh/id_ed25519" -N "" -C "backup@$(hostname)"
        info "SSH key generated for Storage Box:"
        cat "$APP_DIR/backup-ssh/id_ed25519.pub"
        warn "Add this public key to Hetzner Robot → Storage Box → SSH Keys"
    fi

    # Create backup config
    if [[ ! -f /etc/backup-database.conf ]]; then
        cat > /etc/backup-database.conf << 'STORAGECONF'
# Backup configuration for extra-db-backup.service
# Extra Consultoria — Story FEAT-4.1
# Fill in with actual credentials after Storage Box is configured

LOCAL_DATALAKE_DSN=postgresql://postgres:CHANGE_ME@localhost:5432/pncp_datalake
BACKUP_STORAGE_BOX_SSH=u000000@u000000.your-storagebox.de
BACKUP_MOUNT_POINT=/mnt/storage-box
BACKUP_REMOTE_DIR=backups/postgresql
BACKUP_RETENTION_DAILY=7
BACKUP_RETENTION_WEEKLY=4
BACKUP_LOG_FILE=/var/log/backup-database.log
STORAGECONF
        chmod 600 /etc/backup-database.conf
        info "Backup config created at /etc/backup-database.conf — EDIT with real credentials!"
    fi

    # Install backup scripts
    cp "$APP_DIR/scripts/backup-database.sh" /usr/local/bin/backup-database.sh
    cp "$APP_DIR/scripts/restore-database.sh" /usr/local/bin/restore-database.sh
    chmod +x /usr/local/bin/backup-database.sh /usr/local/bin/restore-database.sh
    info "Backup scripts installed to /usr/local/bin/"
}

# ──────────────────────────────────────────────────────────────────────────────
# Final: Summary
# ──────────────────────────────────────────────────────────────────────────────

print_summary() {
    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║  Extra Consultoria — VPS Provisioning Complete             ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""
    echo "  App directory:  $APP_DIR"
    echo "  App user:       $APP_USER"
    echo "  Database:       pncp_datalake (localhost:5432)"
    echo "  SSH port:       $SSH_PORT/tcp"
    echo "  Timezone:       $TIMEZONE"
    echo ""
    echo "  Systemd timers:"
    systemctl list-timers 'extra-*' --no-pager 2>/dev/null || echo "    (check: systemctl list-timers 'extra-*')"
    echo ""
    echo "  Post-provisioning steps:"
    echo "    1. Edit /etc/backup-database.conf with Storage Box credentials"
    echo "    2. Add Storage Box SSH key (printed above) to Hetzner Robot"
    echo "    3. Mount Storage Box: sshfs -p 23 ... /mnt/storage-box"
    echo "    4. Edit $APP_DIR/.env with production credentials"
    echo "    5. Test backup: /usr/local/bin/backup-database.sh --dry-run"
    echo "    6. Test crawler: systemctl start extra-crawl-pncp.service"
    echo "    7. Monitor: journalctl -u extra-health-check.service -f"
    echo ""
    echo "  Documentation:"
    echo "    docs/ops/vps-provisioning.md"
    echo "    docs/ops/vps-access.md"
    echo "    docs/ops/backup.md"
    echo ""
}

# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

main() {
    echo ""
    echo "============================================"
    echo " Extra Consultoria — VPS Provisioning"
    echo " Story FEAT-4.1: Provisionar Hetzner VPS"
    echo "============================================"
    echo ""

    check_root

    install_system_packages
    create_app_user
    harden_ssh
    configure_firewall
    configure_fail2ban
    configure_postgresql
    deploy_application
    setup_database
    install_systemd_timers
    configure_storage_box

    # Enable unattended upgrades
    dpkg-reconfigure -f noninteractive unattended-upgrades > /dev/null 2>&1 || true

    print_summary
}

main "$@"

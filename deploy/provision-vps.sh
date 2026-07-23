#!/bin/bash
# provision-vps.sh — Provision a fresh VPS for Extra Consultoria
# Target hardware baseline: Netcup RS 2000 G12 (8 cores, 16 GB RAM, 512 GB NVMe)
# Provider-agnostic (Netcup SCP, Hetzner, etc.) — Ubuntu 24.04 LTS
#
# Usage (recommended):
#   1. Boot Ubuntu 24.04 LTS on the VPS
#   2. Install your SSH public key for root (authorized_keys) BEFORE running
#   3. scp deploy/provision-vps.sh root@<VPS_IP>:/root/
#   4. ssh root@<VPS_IP>
#   5. export PG_PASSWORD='...strong...'
#      export ENABLE_TIMERS=minimal   # none | minimal | full
#      bash /root/provision-vps.sh
#
# Env knobs:
#   REPO_URL, REPO_BRANCH, SSH_PORT, TIMEZONE, PG_PASSWORD
#   ENABLE_TIMERS=none|minimal|full   (default: minimal)
#   SKIP_SSH_HARDEN=1                 (keep port 22 + passwords until keys verified)
#   MONITORING_IPS="1.2.3.4 5.6.7.8"  (optional node-exporter allowlist)
#   LOCAL_DATALAKE_DSN=...            (optional; built from PG_PASSWORD if unset)
#   BACKUP_REMOTE_SSH=user@host       (optional off-box backup target)

set -euo pipefail

# ──────────────────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────────────────

APP_USER="extra-consultoria"
APP_DIR="/opt/extra-consultoria"
REPO_URL="${REPO_URL:-https://github.com/tjsasakifln/extra-consultoria.git}"
REPO_BRANCH="${REPO_BRANCH:-main}"
SSH_PORT="${SSH_PORT:-2222}"
TIMEZONE="${TIMEZONE:-America/Sao_Paulo}"
ENABLE_TIMERS="${ENABLE_TIMERS:-minimal}"   # none | minimal | full
SKIP_SSH_HARDEN="${SKIP_SSH_HARDEN:-0}"
# Netcup RS 2000 G12 profile
HARDWARE_PROFILE="${HARDWARE_PROFILE:-rs2000-16g}"
SWAP_GB="${SWAP_GB:-4}"

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
# Step 1: System packages, timezone, swap
# ──────────────────────────────────────────────────────────────────────────────

install_system_packages() {
    info "Step 1/11: Installing system packages..."

    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get upgrade -y -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
        python3 python3-pip python3-venv python3-dev \
        postgresql postgresql-client postgresql-contrib \
        sshfs gzip curl wget git rsync \
        ufw fail2ban \
        htop iotop nload \
        unattended-upgrades \
        prometheus-node-exporter \
        ca-certificates \
        > /dev/null

    timedatectl set-timezone "$TIMEZONE"
    info "Timezone set to $TIMEZONE"

    # Swap (helps 16 GB hosts under crawl+PG spikes)
    if ! swapon --show | grep -q .; then
        if [[ ! -f /swapfile ]]; then
            info "Creating ${SWAP_GB}G swapfile..."
            fallocate -l "${SWAP_GB}G" /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=$((SWAP_GB * 1024))
            chmod 600 /swapfile
            mkswap /swapfile
        fi
        swapon /swapfile || true
        if ! grep -q '^/swapfile' /etc/fstab; then
            echo '/swapfile none swap sw 0 0' >> /etc/fstab
        fi
        info "Swap enabled (${SWAP_GB}G)"
    else
        info "Swap already present — skipping"
    fi
}

# ──────────────────────────────────────────────────────────────────────────────
# Step 2: Create application user
# ──────────────────────────────────────────────────────────────────────────────

create_app_user() {
    info "Step 2/11: Creating application user..."

    if ! id "$APP_USER" &>/dev/null; then
        useradd -m -s /bin/bash -G sudo "$APP_USER"
        info "User $APP_USER created"
    else
        info "User $APP_USER already exists"
    fi

    # Passwordless sudo only for deploy ops (not full root shell)
    echo "$APP_USER ALL=(ALL) NOPASSWD: /usr/bin/systemctl, /usr/bin/journalctl" > /etc/sudoers.d/extra-consultoria
    chmod 440 /etc/sudoers.d/extra-consultoria

    # Ensure app user can SSH with same keys as root if present
    if [[ -f /root/.ssh/authorized_keys ]]; then
        mkdir -p "/home/$APP_USER/.ssh"
        cp /root/.ssh/authorized_keys "/home/$APP_USER/.ssh/authorized_keys"
        chown -R "$APP_USER:$APP_USER" "/home/$APP_USER/.ssh"
        chmod 700 "/home/$APP_USER/.ssh"
        chmod 600 "/home/$APP_USER/.ssh/authorized_keys"
        info "Copied authorized_keys to $APP_USER"
    else
        warn "No /root/.ssh/authorized_keys — install a key before disabling password auth"
    fi
}

# ──────────────────────────────────────────────────────────────────────────────
# Step 3: Firewall (open SSH before changing port)
# ──────────────────────────────────────────────────────────────────────────────

configure_firewall() {
    info "Step 3/11: Configuring firewall..."

    ufw --force reset
    ufw default deny incoming
    ufw default allow outgoing

    # Keep 22 open during transition if hardening will move to SSH_PORT
    ufw allow 22/tcp comment "SSH bootstrap"
    ufw allow "$SSH_PORT/tcp" comment "SSH custom port"

    if [[ -n "${MONITORING_IPS:-}" ]]; then
        for ip in $MONITORING_IPS; do
            ufw allow from "$ip" to any port 9100 proto tcp comment "Prometheus node exporter"
        done
        info "Node exporter restricted to: $MONITORING_IPS"
    else
        warn "MONITORING_IPS not set — node exporter port 9100 NOT opened"
    fi

    ufw --force enable
    info "Firewall enabled. Open: 22/tcp + $SSH_PORT/tcp"
}

# ──────────────────────────────────────────────────────────────────────────────
# Step 4: SSH hardening
# ──────────────────────────────────────────────────────────────────────────────

harden_ssh() {
    info "Step 4/11: Hardening SSH..."

    if [[ "$SKIP_SSH_HARDEN" == "1" ]]; then
        warn "SKIP_SSH_HARDEN=1 — leaving SSH defaults (port 22 / passwords may remain)"
        return 0
    fi

    if [[ ! -s /root/.ssh/authorized_keys ]]; then
        error "Refusing to harden SSH: /root/.ssh/authorized_keys is empty"
        error "Install your public key first, or set SKIP_SSH_HARDEN=1"
        exit 1
    fi

    # Prefer drop-in so package upgrades do not clobber settings
    mkdir -p /etc/ssh/sshd_config.d
    cat > /etc/ssh/sshd_config.d/99-extra-consultoria.conf << EOF
Port $SSH_PORT
PermitRootLogin prohibit-password
PasswordAuthentication no
KbdInteractiveAuthentication no
X11Forwarding no
PubkeyAuthentication yes
EOF

    # Also set Port in main file for older parsers
    if grep -qE '^#?Port ' /etc/ssh/sshd_config; then
        sed -i "s/^#\\?Port .*/Port $SSH_PORT/" /etc/ssh/sshd_config
    else
        echo "Port $SSH_PORT" >> /etc/ssh/sshd_config
    fi

    if systemctl list-unit-files | grep -q '^ssh\.service'; then
        systemctl restart ssh
    else
        systemctl restart sshd
    fi

    info "SSH configured on port $SSH_PORT (key-only)"
    warn "Keep this session open! Test: ssh -p $SSH_PORT root@<IP> before closing."
    warn "After confirming, remove port 22 from UFW: ufw delete allow 22/tcp"
}

# ──────────────────────────────────────────────────────────────────────────────
# Step 5: Fail2ban
# ──────────────────────────────────────────────────────────────────────────────

configure_fail2ban() {
    info "Step 5/11: Configuring fail2ban..."

    cat > /etc/fail2ban/jail.local << EOF
[sshd]
enabled = true
port = $SSH_PORT,22
maxretry = 3
bantime = 3600
findtime = 600
EOF

    systemctl enable fail2ban
    systemctl restart fail2ban
    info "Fail2ban configured"
}

# ──────────────────────────────────────────────────────────────────────────────
# Step 6: PostgreSQL (tuned for 16 GB / RS 2000)
# ──────────────────────────────────────────────────────────────────────────────

configure_postgresql() {
    info "Step 6/11: Configuring PostgreSQL (profile=$HARDWARE_PROFILE)..."

    # Listen only on localhost (idempotent; avoid double-substitution on Debian/Ubuntu)
    for conf in /etc/postgresql/*/main/postgresql.conf; do
        [[ -f "$conf" ]] || continue
        if grep -qE "^#?listen_addresses\s*=" "$conf"; then
            sed -i -E "s/^#?listen_addresses\s*=.*/listen_addresses = 'localhost'/" "$conf"
        else
            echo "listen_addresses = 'localhost'" >> "$conf"
        fi
    done

    # Idempotent tuning block
    TUNE_MARKER="# ── Extra Consultoria tuning ($HARDWARE_PROFILE) ──"
    for conf in /etc/postgresql/*/main/postgresql.conf; do
        [[ -f "$conf" ]] || continue
        if grep -qF "$TUNE_MARKER" "$conf"; then
            info "PG tuning already present in $conf"
            continue
        fi
        case "$HARDWARE_PROFILE" in
            rs2000-16g|rs2000|16g)
                cat >> "$conf" << 'EOF'

# ── Extra Consultoria tuning (rs2000-16g) ──
# Netcup RS 2000 G12: 8 cores, 16 GB RAM, NVMe
shared_buffers = 4GB
effective_cache_size = 12GB
work_mem = 32MB
maintenance_work_mem = 512MB
random_page_cost = 1.1
effective_io_concurrency = 200
wal_buffers = 64MB
max_worker_processes = 8
max_parallel_workers = 4
max_parallel_workers_per_gather = 2
checkpoint_completion_target = 0.9
EOF
                ;;
            rs4000-32g|32g)
                cat >> "$conf" << 'EOF'

# ── Extra Consultoria tuning (rs4000-32g) ──
shared_buffers = 8GB
effective_cache_size = 24GB
work_mem = 64MB
maintenance_work_mem = 1GB
random_page_cost = 1.1
effective_io_concurrency = 200
wal_buffers = 64MB
max_worker_processes = 12
max_parallel_workers = 4
max_parallel_workers_per_gather = 4
checkpoint_completion_target = 0.9
EOF
                ;;
            *)
                warn "Unknown HARDWARE_PROFILE=$HARDWARE_PROFILE — using conservative 16G defaults"
                cat >> "$conf" << 'EOF'

# ── Extra Consultoria tuning (fallback-16g) ──
shared_buffers = 4GB
effective_cache_size = 12GB
work_mem = 32MB
maintenance_work_mem = 512MB
random_page_cost = 1.1
EOF
                ;;
        esac
    done

    systemctl enable postgresql
    systemctl restart postgresql

    sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='pncp_datalake'" | grep -q 1 || \
        sudo -u postgres createdb pncp_datalake

    PG_PASSWORD="${PG_PASSWORD:-$(openssl rand -base64 24)}"
    sudo -u postgres psql -c "ALTER USER postgres PASSWORD '${PG_PASSWORD}'" > /dev/null 2>&1 || true

    # Persist password hint only for root (0600) — operator must move to vault
    umask 077
    cat > /root/.extra-pg-credentials << EOF
# Generated by provision-vps.sh — move to vault and delete this file
PG_PASSWORD=${PG_PASSWORD}
LOCAL_DATALAKE_DSN=postgresql://postgres:${PG_PASSWORD}@127.0.0.1:5432/pncp_datalake
EOF
    chmod 600 /root/.extra-pg-credentials

    info "PostgreSQL configured. Database 'pncp_datalake' created."
    warn "Credentials written to /root/.extra-pg-credentials (mode 600) — copy to vault, then delete."
}

# ──────────────────────────────────────────────────────────────────────────────
# Step 7: Clone repository & install dependencies
# ──────────────────────────────────────────────────────────────────────────────

deploy_application() {
    info "Step 7/11: Deploying application..."

    mkdir -p "$(dirname "$APP_DIR")"
    if [[ -d "$APP_DIR/.git" ]]; then
        cd "$APP_DIR"
        sudo -u "$APP_USER" git fetch origin || true
        sudo -u "$APP_USER" git checkout "$REPO_BRANCH" || true
        sudo -u "$APP_USER" git pull origin "$REPO_BRANCH" || git pull origin "$REPO_BRANCH"
    else
        if [[ -d "$APP_DIR" ]] && [[ -n "$(ls -A "$APP_DIR" 2>/dev/null || true)" ]]; then
            warn "$APP_DIR exists and is not a git repo — leaving contents, skipping clone"
        else
            git clone --branch "$REPO_BRANCH" "$REPO_URL" "$APP_DIR"
        fi
    fi

    chown -R "$APP_USER:$APP_USER" "$APP_DIR"
    cd "$APP_DIR"

    # Prefer venv (Ubuntu 24 pecl/pip system isolation)
    if [[ ! -d "$APP_DIR/.venv" ]]; then
        sudo -u "$APP_USER" python3 -m venv "$APP_DIR/.venv"
    fi
    # shellcheck disable=SC1091
    source "$APP_DIR/.venv/bin/activate"
    pip install -q --upgrade pip
    if [[ -f requirements.txt ]]; then
        pip install -q -r requirements.txt
    fi
    deactivate || true
    chown -R "$APP_USER:$APP_USER" "$APP_DIR/.venv"

    mkdir -p /var/lib/extra-consultoria/resilience
    chown -R "$APP_USER:$APP_USER" /var/lib/extra-consultoria

    if [[ ! -f "$APP_DIR/.env" ]]; then
        if [[ -f "$APP_DIR/.env.example" ]]; then
            # shellcheck disable=SC1091
            source /root/.extra-pg-credentials 2>/dev/null || true
            cp "$APP_DIR/.env.example" "$APP_DIR/.env"
            if [[ -n "${LOCAL_DATALAKE_DSN:-}" ]]; then
                sed -i "s|^DATABASE_URL=.*|DATABASE_URL=${LOCAL_DATALAKE_DSN}|" "$APP_DIR/.env" || true
                sed -i "s|^LOCAL_DATALAKE_DSN=.*|LOCAL_DATALAKE_DSN=${LOCAL_DATALAKE_DSN}|" "$APP_DIR/.env" || true
            fi
            if [[ -f "$APP_DIR/deploy/systemd/extra-collector.env.example" ]]; then
                cat "$APP_DIR/deploy/systemd/extra-collector.env.example" >> "$APP_DIR/.env"
            fi
            chmod 600 "$APP_DIR/.env"
            chown "$APP_USER:$APP_USER" "$APP_DIR/.env"
            info "Created $APP_DIR/.env — review secrets before enabling crawlers"
        else
            warn "No .env.example found. Create $APP_DIR/.env manually."
        fi
    fi
}

# ──────────────────────────────────────────────────────────────────────────────
# Step 8: Database migrations & seeds
# ──────────────────────────────────────────────────────────────────────────────

setup_database() {
    info "Step 8/11: Running database migrations..."

    cd "$APP_DIR"
    # shellcheck disable=SC1091
    source /root/.extra-pg-credentials 2>/dev/null || true
    if [[ -z "${LOCAL_DATALAKE_DSN:-}" ]]; then
        : "${PG_PASSWORD:?PG_PASSWORD is required when LOCAL_DATALAKE_DSN is unset}"
        LOCAL_DATALAKE_DSN="postgresql://postgres:${PG_PASSWORD}@127.0.0.1:5432/pncp_datalake"
    fi
    export LOCAL_DATALAKE_DSN
    export DATABASE_URL="${DATABASE_URL:-$LOCAL_DATALAKE_DSN}"

    if [[ -x "$APP_DIR/db/setup_db.sh" ]] || [[ -f "$APP_DIR/db/setup_db.sh" ]]; then
        bash "$APP_DIR/db/setup_db.sh" "${LOCAL_DATALAKE_DSN}"
    else
        # shellcheck disable=SC1091
        source "$APP_DIR/.venv/bin/activate"
        python3 -m scripts.ops.apply_migrations --dsn "$LOCAL_DATALAKE_DSN"
        deactivate || true
    fi
    info "Database migrations applied"
}

# ──────────────────────────────────────────────────────────────────────────────
# Step 9: Systemd timers (phased)
# ──────────────────────────────────────────────────────────────────────────────

install_systemd_timers() {
    info "Step 9/11: Installing systemd units (ENABLE_TIMERS=$ENABLE_TIMERS)..."

    if [[ ! -d "$APP_DIR/deploy/systemd" ]]; then
        warn "No deploy/systemd directory — skipping timers"
        return 0
    fi

    cp "$APP_DIR/deploy/systemd/"*.service /etc/systemd/system/ 2>/dev/null || true
    cp "$APP_DIR/deploy/systemd/"*.timer /etc/systemd/system/ 2>/dev/null || true
    # env example is not a unit
    rm -f /etc/systemd/system/*.example 2>/dev/null || true
    systemctl daemon-reload

    # Wave A — safe day-1 set for 16 GB host
    local minimal_timers=(
        extra-health-check
        extra-db-backup
        pncp-crawl-inc
        extra-crawl-pncp
        extra-collect-metrics
        extra-check-alerts
    )

    # Wave full — all known timers (use only after wave A stable)
    local full_timers=(
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
        extra-crawl-ciga-dom
        extra-crawl-sc-compras
        extra-crawl-pncp
        extra-crawl-selenium
        coverage-report
        coverage-report-weekly
        extra-check-alerts
        extra-collect-metrics
        extra-db-backup
        extra-health-check
    )

    local timers=()
    case "$ENABLE_TIMERS" in
        none|off|0)
            info "ENABLE_TIMERS=none — units installed but none enabled"
            return 0
            ;;
        minimal|min|wave-a|a)
            timers=("${minimal_timers[@]}")
            ;;
        full|all)
            timers=("${full_timers[@]}")
            ;;
        *)
            warn "Unknown ENABLE_TIMERS=$ENABLE_TIMERS — defaulting to minimal"
            timers=("${minimal_timers[@]}")
            ;;
    esac

    for timer in "${timers[@]}"; do
        if [[ -f "/etc/systemd/system/${timer}.timer" ]]; then
            systemctl enable "${timer}.timer"
            systemctl start "${timer}.timer"
            info "  ✓ ${timer}.timer enabled & started"
        else
            warn "  ✗ ${timer}.timer not found — skipping"
        fi
    done

    info "Timers wave installed"
    systemctl list-timers --all --no-pager 2>/dev/null | head -40 || true
}

# ──────────────────────────────────────────────────────────────────────────────
# Step 10: Backup configuration (provider-agnostic)
# ──────────────────────────────────────────────────────────────────────────────

configure_backup() {
    info "Step 10/11: Configuring backup..."

    mkdir -p "$APP_DIR/backup-ssh"
    chown -R "$APP_USER:$APP_USER" "$APP_DIR/backup-ssh"

    if [[ ! -f "$APP_DIR/backup-ssh/id_ed25519" ]]; then
        sudo -u "$APP_USER" ssh-keygen -t ed25519 -f "$APP_DIR/backup-ssh/id_ed25519" -N "" -C "backup@$(hostname -f 2>/dev/null || hostname)"
        info "Backup SSH public key:"
        cat "$APP_DIR/backup-ssh/id_ed25519.pub"
        warn "Authorize this key on the OFF-BOX backup host (SFTP/rsync). Snapshots SCP ≠ off-site backup."
    fi

    # shellcheck disable=SC1091
    source /root/.extra-pg-credentials 2>/dev/null || true

    if [[ ! -f /etc/backup-database.conf ]]; then
        cat > /etc/backup-database.conf << EOF
# Backup configuration for extra-db-backup.service
# Extra Consultoria — Netcup / provider-agnostic
# Fill BACKUP_* after choosing remote target (Netcup storage, S3, NAS, etc.)

LOCAL_DATALAKE_DSN=${LOCAL_DATALAKE_DSN:-postgresql://postgres:CHANGE_ME@127.0.0.1:5432/pncp_datalake}
BACKUP_STORAGE_BOX_SSH=${BACKUP_REMOTE_SSH:-backup@CHANGE_ME}
BACKUP_MOUNT_POINT=/mnt/backup-remote
BACKUP_REMOTE_DIR=backups/postgresql
BACKUP_RETENTION_DAILY=7
BACKUP_RETENTION_WEEKLY=4
BACKUP_LOG_FILE=/var/log/backup-database.log
EOF
        chmod 600 /etc/backup-database.conf
        info "Backup config created at /etc/backup-database.conf — EDIT remote target"
    fi

    if [[ -f "$APP_DIR/scripts/backup-database.sh" ]]; then
        cp "$APP_DIR/scripts/backup-database.sh" /usr/local/bin/backup-database.sh
        chmod +x /usr/local/bin/backup-database.sh
    fi
    if [[ -f "$APP_DIR/scripts/restore-database.sh" ]]; then
        cp "$APP_DIR/scripts/restore-database.sh" /usr/local/bin/restore-database.sh
        chmod +x /usr/local/bin/restore-database.sh
    fi
    info "Backup scripts installed under /usr/local/bin/ (if present in repo)"
}

# ──────────────────────────────────────────────────────────────────────────────
# Step 11: Directories & unattended upgrades
# ──────────────────────────────────────────────────────────────────────────────

finalize_host() {
    info "Step 11/11: Finalizing host..."

    mkdir -p /var/log/extra-consultoria /var/tmp/extra-consultoria
    chown -R "$APP_USER:$APP_USER" /var/log/extra-consultoria /var/tmp/extra-consultoria

    dpkg-reconfigure -f noninteractive unattended-upgrades > /dev/null 2>&1 || true
    info "Unattended upgrades enabled (best-effort)"
}

# ──────────────────────────────────────────────────────────────────────────────
# Summary
# ──────────────────────────────────────────────────────────────────────────────

print_summary() {
    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║  Extra Consultoria — VPS Provisioning Complete               ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""
    echo "  Profile:        $HARDWARE_PROFILE"
    echo "  App directory:  $APP_DIR"
    echo "  App user:       $APP_USER"
    echo "  Database:       pncp_datalake (localhost:5432 only)"
    echo "  SSH port:       $SSH_PORT/tcp (test before closing this session)"
    echo "  Timezone:       $TIMEZONE"
    echo "  Timers:         ENABLE_TIMERS=$ENABLE_TIMERS"
    echo "  Repo:           $REPO_URL @$REPO_BRANCH"
    echo ""
    echo "  Credentials:    /root/.extra-pg-credentials  (delete after vault)"
    echo "  Env file:       $APP_DIR/.env"
    echo "  Backup conf:    /etc/backup-database.conf"
    echo ""
    echo "  Next steps:"
    echo "    1. ssh -p $SSH_PORT root@<IP>   # confirm key login"
    echo "    2. ufw delete allow 22/tcp      # after confirm"
    echo "    3. Fill backup remote + authorize backup pubkey"
    echo "    4. Review $APP_DIR/.env"
    echo "    5. PNCP smoke:"
    echo "         sudo -u $APP_USER bash -lc 'cd $APP_DIR && . .venv/bin/activate && \\"
    echo "           python scripts/crawl/monitor.py --source pncp --mode incremental'"
    echo "    6. systemctl list-timers --all | grep -E 'extra|pncp'"
    echo ""
    echo "  Docs: docs/ops/vps-provisioning.md · docs/ops/vps-access.md"
    echo ""
}

# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

main() {
    echo ""
    echo "============================================"
    echo " Extra Consultoria — VPS Provisioning"
    echo " Profile: $HARDWARE_PROFILE · timers: $ENABLE_TIMERS"
    echo "============================================"
    echo ""

    check_root

    install_system_packages
    create_app_user
    configure_firewall
    harden_ssh
    configure_fail2ban
    configure_postgresql
    deploy_application
    setup_database
    install_systemd_timers
    configure_backup
    finalize_host

    print_summary
}

main "$@"

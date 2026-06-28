#!/bin/bash

# ============================================================
# ONE-CLICK INSTALL - Reinstall OS Telegram Bot
# by xyzval
#
# Jalankan dengan:
# bash <(curl -sL https://raw.githubusercontent.com/xyzval/reinstallos/main/install.sh)
#
# Bot akan aktif 24/7 otomatis (auto-restart jika crash)
# ============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

INSTALL_DIR="/opt/reinstallos"
SERVICE_NAME="reinstall-bot"
REPO_URL="https://github.com/xyzval/reinstallos.git"

print_banner() {
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════╗"
    echo "║                                                      ║"
    echo "║   🖥️  REINSTALL OS - Telegram Bot Installer          ║"
    echo "║   One-Click Setup | Auto 24/7                        ║"
    echo "║   by xyzval                                          ║"
    echo "║                                                      ║"
    echo "╚══════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_step() {
    echo -e "${GREEN}[✓] $1${NC}"
}

print_info() {
    echo -e "${CYAN}[i] $1${NC}"
}

print_error() {
    echo -e "${RED}[✗] $1${NC}"
}

print_warn() {
    echo -e "${YELLOW}[!] $1${NC}"
}

# Check root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        print_error "Harus dijalankan sebagai root!"
        echo ""
        echo "  Jalankan ulang dengan:"
        echo -e "  ${BOLD}sudo bash <(curl -sL https://raw.githubusercontent.com/xyzval/reinstallos/main/install.sh)${NC}"
        echo ""
        exit 1
    fi
}

# Check OS compatibility
check_os() {
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        case "$ID" in
            debian|ubuntu|linuxmint|pop) PKG_MANAGER="apt" ;;
            centos|rhel|rocky|alma|fedora) PKG_MANAGER="yum" ;;
            *) PKG_MANAGER="apt" ;;
        esac
    else
        PKG_MANAGER="apt"
    fi
}

# Install system dependencies
install_deps() {
    print_info "Menginstall dependencies sistem..."
    if [[ "$PKG_MANAGER" == "apt" ]]; then
        apt-get update -qq > /dev/null 2>&1
        apt-get install -y -qq python3 python3-pip python3-venv git curl wget > /dev/null 2>&1
    else
        yum install -y -q python3 python3-pip git curl wget > /dev/null 2>&1
    fi
    print_step "Dependencies sistem terinstall"
}

# Clone or update repository
setup_repo() {
    print_info "Mengunduh bot dari GitHub..."
    if [[ -d "$INSTALL_DIR/.git" ]]; then
        cd "$INSTALL_DIR"
        git pull --quiet > /dev/null 2>&1
        print_step "Bot diupdate ke versi terbaru"
    else
        rm -rf "$INSTALL_DIR"
        git clone --quiet "$REPO_URL" "$INSTALL_DIR" > /dev/null 2>&1
        print_step "Bot berhasil diunduh"
    fi
}

# Install Python packages
install_python_deps() {
    print_info "Menginstall Python packages..."
    cd "$INSTALL_DIR"
    
    # Try with virtual environment first
    if python3 -m venv "$INSTALL_DIR/venv" 2>/dev/null; then
        source "$INSTALL_DIR/venv/bin/activate"
        pip install --quiet --upgrade pip > /dev/null 2>&1
        pip install --quiet -r requirements.txt > /dev/null 2>&1
        deactivate
        PYTHON_BIN="$INSTALL_DIR/venv/bin/python3"
    else
        # Fallback: install globally
        pip3 install --break-system-packages --quiet -r requirements.txt > /dev/null 2>&1 || \
        pip3 install --quiet -r requirements.txt > /dev/null 2>&1
        PYTHON_BIN="/usr/bin/python3"
    fi
    
    print_step "Python packages terinstall"
}

# Get configuration from user
get_config() {
    echo ""
    echo -e "${BOLD}─────────────────────────────────────────${NC}"
    echo -e "${BOLD}  KONFIGURASI BOT${NC}"
    echo -e "${BOLD}─────────────────────────────────────────${NC}"
    echo ""
    
    # Bot Token
    echo -e "  ${CYAN}1. Bot Token${NC}"
    echo -e "     Dapatkan dari @BotFather di Telegram"
    echo ""
    while true; do
        read -p "     Masukkan Bot Token: " BOT_TOKEN
        if [[ -n "$BOT_TOKEN" && "$BOT_TOKEN" == *":"* ]]; then
            break
        fi
        print_error "Token tidak valid! Format: 123456:ABC-DEF..."
    done
    echo ""
    
    # Allowed Users
    echo -e "  ${CYAN}2. Telegram User ID (opsional)${NC}"
    echo -e "     Dapatkan dari @userinfobot di Telegram"
    echo -e "     Kosongkan = semua orang bisa pakai"
    echo ""
    read -p "     Masukkan User ID: " ALLOWED_USERS
    echo ""
}

# Create .env file
create_env() {
    cat > "$INSTALL_DIR/.env" << EOF
BOT_TOKEN=${BOT_TOKEN}
ALLOWED_USERS=${ALLOWED_USERS}
EOF
    chmod 600 "$INSTALL_DIR/.env"
    print_step "Konfigurasi tersimpan"
}

# Create systemd service
create_service() {
    print_info "Membuat service systemd (auto 24/7)..."
    
    cat > "/etc/systemd/system/${SERVICE_NAME}.service" << EOF
[Unit]
Description=Reinstall OS Telegram Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${INSTALL_DIR}
ExecStart=${PYTHON_BIN} ${INSTALL_DIR}/bot.py
Restart=always
RestartSec=5
StartLimitIntervalSec=60
StartLimitBurst=5
Environment=PYTHONUNBUFFERED=1

# Security hardening
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=${INSTALL_DIR}

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable "$SERVICE_NAME" > /dev/null 2>&1
    systemctl restart "$SERVICE_NAME"
    
    print_step "Service systemd dibuat & dijalankan"
}

# Verify bot is running
verify_bot() {
    sleep 3
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        return 0
    else
        return 1
    fi
}

# Print success message
print_success() {
    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║                                                      ║${NC}"
    echo -e "${GREEN}║   ✅  BOT BERHASIL DIINSTALL & AKTIF 24/7!          ║${NC}"
    echo -e "${GREEN}║                                                      ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  ${BOLD}Status:${NC}     ${GREEN}RUNNING${NC} (auto-restart jika crash)"
    echo -e "  ${BOLD}Install:${NC}    ${INSTALL_DIR}"
    echo -e "  ${BOLD}Service:${NC}    ${SERVICE_NAME}"
    echo ""
    echo -e "  ${BOLD}${CYAN}Langkah selanjutnya:${NC}"
    echo -e "  1. Buka Telegram"
    echo -e "  2. Cari bot kamu"
    echo -e "  3. Kirim ${BOLD}/start${NC}"
    echo ""
    echo -e "─────────────────────────────────────────"
    echo -e "  ${BOLD}Perintah berguna:${NC}"
    echo ""
    echo -e "  ${YELLOW}systemctl status ${SERVICE_NAME}${NC}    # Cek status"
    echo -e "  ${YELLOW}systemctl restart ${SERVICE_NAME}${NC}   # Restart bot"
    echo -e "  ${YELLOW}systemctl stop ${SERVICE_NAME}${NC}      # Stop bot"
    echo -e "  ${YELLOW}journalctl -u ${SERVICE_NAME} -f${NC}    # Lihat log"
    echo ""
    echo -e "─────────────────────────────────────────"
    echo -e "  ${BOLD}Update bot:${NC}"
    echo -e "  ${YELLOW}cd ${INSTALL_DIR} && git pull && systemctl restart ${SERVICE_NAME}${NC}"
    echo ""
}

# Print failure message
print_failure() {
    echo ""
    print_error "Bot gagal dijalankan!"
    echo ""
    echo -e "  Cek log dengan:"
    echo -e "  ${YELLOW}journalctl -u ${SERVICE_NAME} -n 30${NC}"
    echo ""
    echo -e "  Kemungkinan masalah:"
    echo "  - Bot Token salah"
    echo "  - Tidak ada koneksi internet"
    echo "  - Port diblokir firewall"
    echo ""
    echo -e "  Jalankan ulang installer:"
    echo -e "  ${BOLD}bash <(curl -sL https://raw.githubusercontent.com/xyzval/reinstallos/main/install.sh)${NC}"
    echo ""
}

# ============================================================
# MAIN
# ============================================================

print_banner
check_root
check_os

echo -e "${BOLD}  Memulai instalasi...${NC}"
echo ""

install_deps
setup_repo
install_python_deps
get_config
create_env
create_service

if verify_bot; then
    print_success
else
    print_failure
    exit 1
fi

#!/bin/bash

# ============================================================
# Auto Setup - Reinstall OS Telegram Bot
# by xyzval
# 
# Jalankan di VPS yang akan menjalankan bot (BUKAN VPS target)
# Bot akan aktif 24/7 otomatis
# ============================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}"
echo "╔══════════════════════════════════════════════════════╗"
echo "║   AUTO SETUP - Reinstall OS Telegram Bot            ║"
echo "║   by xyzval                                         ║"
echo "╚══════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Check root
if [[ $EUID -ne 0 ]]; then
    echo -e "${RED}[ERROR] Jalankan sebagai root: sudo bash setup.sh${NC}"
    exit 1
fi

# Get bot token
echo ""
read -p "Masukkan Bot Token (dari @BotFather): " BOT_TOKEN
if [[ -z "$BOT_TOKEN" ]]; then
    echo -e "${RED}[ERROR] Bot Token tidak boleh kosong!${NC}"
    exit 1
fi

# Get allowed users (optional)
echo ""
read -p "Masukkan Telegram User ID kamu (dari @userinfobot): " ALLOWED_USERS
echo ""

echo -e "${GREEN}[1/6] Menginstall dependencies...${NC}"
apt-get update -qq > /dev/null 2>&1
apt-get install -y -qq python3 python3-pip git > /dev/null 2>&1

echo -e "${GREEN}[2/6] Mengunduh bot dari GitHub...${NC}"
rm -rf /opt/reinstallos
git clone https://github.com/xyzval/reinstallos.git /opt/reinstallos > /dev/null 2>&1

echo -e "${GREEN}[3/6] Menginstall Python packages...${NC}"
pip3 install --break-system-packages -q python-telegram-bot==21.6 paramiko==3.5.0 python-dotenv==1.0.1 > /dev/null 2>&1 || \
pip3 install -q python-telegram-bot==21.6 paramiko==3.5.0 python-dotenv==1.0.1 > /dev/null 2>&1

echo -e "${GREEN}[4/6] Membuat konfigurasi...${NC}"
cat > /opt/reinstallos/.env << EOF
BOT_TOKEN=${BOT_TOKEN}
ALLOWED_USERS=${ALLOWED_USERS}
EOF

echo -e "${GREEN}[5/6] Membuat service systemd (24/7)...${NC}"
cat > /etc/systemd/system/reinstall-bot.service << 'EOF'
[Unit]
Description=Reinstall OS Telegram Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/reinstallos
ExecStart=/usr/bin/python3 /opt/reinstallos/bot.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

echo -e "${GREEN}[6/6] Menjalankan bot...${NC}"
systemctl daemon-reload
systemctl enable reinstall-bot > /dev/null 2>&1
systemctl restart reinstall-bot

# Check status
sleep 3
if systemctl is-active --quiet reinstall-bot; then
    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║   BOT BERHASIL DIJALANKAN! ✅                       ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  Status    : ${GREEN}AKTIF 24/7${NC}"
    echo -e "  Bot Token : ${BOT_TOKEN:0:10}..."
    echo -e "  User ID   : ${ALLOWED_USERS}"
    echo ""
    echo -e "${CYAN}Buka Telegram → cari bot kamu → kirim /start${NC}"
    echo ""
    echo -e "${YELLOW}Perintah berguna:${NC}"
    echo "  systemctl status reinstall-bot   # Cek status"
    echo "  systemctl restart reinstall-bot  # Restart bot"
    echo "  systemctl stop reinstall-bot     # Stop bot"
    echo "  journalctl -u reinstall-bot -f   # Lihat log"
    echo ""
else
    echo ""
    echo -e "${RED}[ERROR] Bot gagal dijalankan!${NC}"
    echo "Cek log: journalctl -u reinstall-bot -n 20"
    echo ""
fi

#!/bin/bash

# ============================================================
# Reinstall OS Script - by xyzval
# Script untuk reinstall VPS ke Windows atau Linux
# Menggunakan leitbogioro/Tools dan bin456789/reinstall
# ============================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Default values
DEFAULT_USER="Administrator"
DEFAULT_PASS="Teddysun.com"
DEFAULT_LANG="en"
SCRIPT_VERSION="1.0.0"

show_banner() {
    clear
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════╗"
    echo "║          REINSTALL OS - by xyzval                   ║"
    echo "║       VPS Reinstall Script (Windows & Linux)        ║"
    echo "║                  Version ${SCRIPT_VERSION}                    ║"
    echo "╚══════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

show_menu() {
    echo -e "${GREEN}=== PILIH SISTEM OPERASI ===${NC}"
    echo ""
    echo -e "${YELLOW}[WINDOWS DESKTOP]${NC}"
    echo "  1) Windows 10"
    echo "  2) Windows 11"
    echo ""
    echo -e "${YELLOW}[WINDOWS SERVER]${NC}"
    echo "  3) Windows Server 2012 R2"
    echo "  4) Windows Server 2016"
    echo "  5) Windows Server 2019"
    echo "  6) Windows Server 2022"
    echo ""
    echo -e "${YELLOW}[LINUX]${NC}"
    echo "  7) Debian 12"
    echo "  8) Debian 11"
    echo "  9) Ubuntu 24.04"
    echo " 10) Ubuntu 22.04"
    echo " 11) Ubuntu 20.04"
    echo " 12) CentOS 9 Stream"
    echo " 13) AlmaLinux 9"
    echo " 14) RockyLinux 9"
    echo " 15) Fedora 43"
    echo " 16) Alpine 3.22"
    echo ""
    echo -e "${YELLOW}[LAINNYA]${NC}"
    echo " 17) Custom Windows ISO (masukkan link sendiri)"
    echo " 18) Custom Linux DD Image"
    echo ""
    echo -e "${RED}  0) Keluar${NC}"
    echo ""
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        echo -e "${RED}[ERROR] Script ini harus dijalankan sebagai root!${NC}"
        echo "Jalankan: sudo bash reinstall.sh"
        exit 1
    fi
}

check_virt() {
    if command -v systemd-detect-virt &>/dev/null; then
        VIRT=$(systemd-detect-virt)
        if [[ "$VIRT" == "openvz" || "$VIRT" == "lxc" ]]; then
            echo -e "${RED}[ERROR] VPS bertipe $VIRT TIDAK didukung!${NC}"
            echo "Script ini hanya mendukung KVM, XEN, Hyper-V."
            exit 1
        fi
    fi
}

get_system_info() {
    echo -e "${BLUE}[INFO] Mengecek sistem...${NC}"
    echo -e "  OS       : $(cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d'"' -f2)"
    echo -e "  Arch     : $(uname -m)"
    echo -e "  RAM      : $(free -m | awk '/Mem:/ {print $2}') MB"
    echo -e "  Disk     : $(df -h / | awk 'NR==2 {print $2}')"
    echo -e "  Virt     : $(systemd-detect-virt 2>/dev/null || echo 'Unknown')"
    echo -e "  IP       : $(curl -s4 ip.sb 2>/dev/null || echo 'N/A')"
    echo ""
}

confirm_install() {
    local os_name="$1"
    echo ""
    echo -e "${RED}╔══════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║  PERINGATAN: SEMUA DATA AKAN DIHAPUS!               ║${NC}"
    echo -e "${RED}║  Pastikan sudah backup data penting.                ║${NC}"
    echo -e "${RED}╚══════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "Akan menginstall: ${GREEN}${os_name}${NC}"
    echo ""
    read -p "Lanjutkan? (y/n): " confirm
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        echo -e "${YELLOW}[BATAL] Instalasi dibatalkan.${NC}"
        exit 0
    fi
}

install_windows_leitbogioro() {
    local version="$1"
    local lang="$2"

    echo -e "${BLUE}[INFO] Mengunduh script InstallNET.sh...${NC}"
    wget --no-check-certificate -qO /tmp/InstallNET.sh 'https://raw.githubusercontent.com/leitbogioro/Tools/master/Linux_reinstall/InstallNET.sh'

    if [[ ! -f /tmp/InstallNET.sh ]]; then
        echo -e "${RED}[ERROR] Gagal mengunduh script!${NC}"
        exit 1
    fi

    chmod a+x /tmp/InstallNET.sh

    echo -e "${GREEN}[INFO] Memulai instalasi Windows ${version}...${NC}"
    echo -e "${CYAN}[INFO] Login setelah selesai:${NC}"
    echo -e "  Host     : $(curl -s4 ip.sb 2>/dev/null || echo 'IP_VPS')"
    echo -e "  Port     : 3389"
    echo -e "  Username : Administrator"
    echo -e "  Password : Teddysun.com"
    echo ""

    bash /tmp/InstallNET.sh -windows "$version" -lang "$lang"
}

install_windows_bin456789() {
    local image_name="$1"
    local iso="$2"
    local username="$3"
    local password="$4"

    echo -e "${BLUE}[INFO] Mengunduh script reinstall.sh (bin456789)...${NC}"
    curl -O https://raw.githubusercontent.com/bin456789/reinstall/main/reinstall.sh 2>/dev/null || \
    wget -O reinstall.sh https://raw.githubusercontent.com/bin456789/reinstall/main/reinstall.sh 2>/dev/null

    if [[ ! -f reinstall.sh ]]; then
        echo -e "${RED}[ERROR] Gagal mengunduh script!${NC}"
        exit 1
    fi

    echo -e "${GREEN}[INFO] Memulai instalasi Windows...${NC}"
    echo -e "${CYAN}[INFO] Login setelah selesai:${NC}"
    echo -e "  Host     : $(curl -s4 ip.sb 2>/dev/null || echo 'IP_VPS')"
    echo -e "  Port     : 3389"
    echo -e "  Username : ${username}"
    echo -e "  Password : ${password}"
    echo ""

    if [[ -n "$iso" ]]; then
        bash reinstall.sh windows --image-name "$image_name" --iso "$iso" --username "$username" --password "$password"
    else
        bash reinstall.sh windows --image-name "$image_name" --lang en-us --username "$username" --password "$password"
    fi
}

install_linux_leitbogioro() {
    local distro="$1"
    local version="$2"
    local password="$3"

    echo -e "${BLUE}[INFO] Mengunduh script InstallNET.sh...${NC}"
    wget --no-check-certificate -qO /tmp/InstallNET.sh 'https://raw.githubusercontent.com/leitbogioro/Tools/master/Linux_reinstall/InstallNET.sh'

    if [[ ! -f /tmp/InstallNET.sh ]]; then
        echo -e "${RED}[ERROR] Gagal mengunduh script!${NC}"
        exit 1
    fi

    chmod a+x /tmp/InstallNET.sh

    echo -e "${GREEN}[INFO] Memulai instalasi ${distro} ${version}...${NC}"
    echo -e "${CYAN}[INFO] Login setelah selesai:${NC}"
    echo -e "  Host     : $(curl -s4 ip.sb 2>/dev/null || echo 'IP_VPS')"
    echo -e "  Port     : 22 (SSH)"
    echo -e "  Username : root"
    echo -e "  Password : ${password}"
    echo ""

    bash /tmp/InstallNET.sh -"$distro" "$version" -pwd "$password"
}

set_password() {
    local default="$1"
    read -p "Masukkan password (default: ${default}): " custom_pass
    if [[ -z "$custom_pass" ]]; then
        echo "$default"
    else
        echo "$custom_pass"
    fi
}

set_language() {
    echo ""
    echo "Pilih bahasa:"
    echo "  1) English (en)"
    echo "  2) Chinese (cn)"
    echo "  3) Japanese (jp)"
    read -p "Pilihan [1]: " lang_choice
    case "$lang_choice" in
        2) echo "cn" ;;
        3) echo "jp" ;;
        *) echo "en" ;;
    esac
}

# ============================================================
# MAIN
# ============================================================

check_root
check_virt
show_banner
get_system_info
show_menu

read -p "Pilih nomor [0-18]: " choice

case "$choice" in
    1)
        confirm_install "Windows 10"
        lang=$(set_language)
        install_windows_leitbogioro "10" "$lang"
        ;;
    2)
        confirm_install "Windows 11"
        lang=$(set_language)
        install_windows_leitbogioro "11" "$lang"
        ;;
    3)
        confirm_install "Windows Server 2012 R2"
        lang=$(set_language)
        install_windows_leitbogioro "2012" "$lang"
        ;;
    4)
        confirm_install "Windows Server 2016"
        lang=$(set_language)
        install_windows_leitbogioro "2016" "$lang"
        ;;
    5)
        confirm_install "Windows Server 2019"
        lang=$(set_language)
        install_windows_leitbogioro "2019" "$lang"
        ;;
    6)
        confirm_install "Windows Server 2022"
        lang=$(set_language)
        install_windows_leitbogioro "2022" "$lang"
        ;;
    7)
        confirm_install "Debian 12"
        password=$(set_password "password123")
        install_linux_leitbogioro "debian" "12" "$password"
        ;;
    8)
        confirm_install "Debian 11"
        password=$(set_password "password123")
        install_linux_leitbogioro "debian" "11" "$password"
        ;;
    9)
        confirm_install "Ubuntu 24.04"
        password=$(set_password "password123")
        install_linux_leitbogioro "ubuntu" "24.04" "$password"
        ;;
    10)
        confirm_install "Ubuntu 22.04"
        password=$(set_password "password123")
        install_linux_leitbogioro "ubuntu" "22.04" "$password"
        ;;
    11)
        confirm_install "Ubuntu 20.04"
        password=$(set_password "password123")
        install_linux_leitbogioro "ubuntu" "20.04" "$password"
        ;;
    12)
        confirm_install "CentOS 9 Stream"
        password=$(set_password "password123")
        install_linux_leitbogioro "centos" "9" "$password"
        ;;
    13)
        confirm_install "AlmaLinux 9"
        password=$(set_password "password123")
        install_linux_leitbogioro "almalinux" "9" "$password"
        ;;
    14)
        confirm_install "RockyLinux 9"
        password=$(set_password "password123")
        install_linux_leitbogioro "rockylinux" "9" "$password"
        ;;
    15)
        confirm_install "Fedora 43"
        password=$(set_password "password123")
        install_linux_leitbogioro "fedora" "43" "$password"
        ;;
    16)
        confirm_install "Alpine 3.22"
        password=$(set_password "password123")
        install_linux_leitbogioro "alpinelinux" "3.22" "$password"
        ;;
    17)
        echo ""
        read -p "Masukkan Image Name (contoh: Windows 10 Pro): " img_name
        read -p "Masukkan link ISO (kosongkan untuk otomatis): " iso_link
        read -p "Username (default: administrator): " win_user
        win_user=${win_user:-administrator}
        read -p "Password (default: bolehtuh#1): " win_pass
        win_pass=${win_pass:-"bolehtuh#1"}
        confirm_install "$img_name"
        install_windows_bin456789 "$img_name" "$iso_link" "$win_user" "$win_pass"
        ;;
    18)
        echo ""
        read -p "Masukkan link DD image (.img/.raw/.gz/.xz): " dd_link
        confirm_install "Custom DD Image"
        echo -e "${BLUE}[INFO] Mengunduh script reinstall.sh (bin456789)...${NC}"
        curl -O https://raw.githubusercontent.com/bin456789/reinstall/main/reinstall.sh 2>/dev/null || \
        wget -O reinstall.sh https://raw.githubusercontent.com/bin456789/reinstall/main/reinstall.sh 2>/dev/null
        bash reinstall.sh dd --img "$dd_link"
        ;;
    0)
        echo -e "${GREEN}Keluar. Bye!${NC}"
        exit 0
        ;;
    *)
        echo -e "${RED}[ERROR] Pilihan tidak valid!${NC}"
        exit 1
        ;;
esac

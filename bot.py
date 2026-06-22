#!/usr/bin/env python3
"""
Telegram Bot - Reinstall OS
by xyzval

Bot Telegram untuk reinstall VPS ke Windows/Linux secara otomatis.
Kirim detail VPS (IP, username, password) dan pilih OS, bot akan menginstall otomatis.
"""

import os
import logging
import asyncio
import paramiko
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)
from dotenv import load_dotenv

load_dotenv()

# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Bot Token
BOT_TOKEN = os.getenv("BOT_TOKEN")
ALLOWED_USERS = os.getenv("ALLOWED_USERS", "").split(",")

# Conversation states
VPS_IP, VPS_PORT, VPS_USER, VPS_PASS, SELECT_OS, SELECT_LANG, CONFIRM = range(7)

# OS Options
WINDOWS_OPTIONS = {
    "win10": {"name": "Windows 10", "cmd": '-windows 10'},
    "win11": {"name": "Windows 11", "cmd": '-windows 11'},
    "ws2012": {"name": "Windows Server 2012 R2", "cmd": '-windows 2012'},
    "ws2016": {"name": "Windows Server 2016", "cmd": '-windows 2016'},
    "ws2019": {"name": "Windows Server 2019", "cmd": '-windows 2019'},
    "ws2022": {"name": "Windows Server 2022", "cmd": '-windows 2022'},
}

LINUX_OPTIONS = {
    "debian12": {"name": "Debian 12", "cmd": '-debian 12'},
    "debian11": {"name": "Debian 11", "cmd": '-debian 11'},
    "ubuntu2404": {"name": "Ubuntu 24.04", "cmd": '-ubuntu 24.04'},
    "ubuntu2204": {"name": "Ubuntu 22.04", "cmd": '-ubuntu 22.04'},
    "ubuntu2004": {"name": "Ubuntu 20.04", "cmd": '-ubuntu 20.04'},
    "centos9": {"name": "CentOS 9 Stream", "cmd": '-centos 9'},
    "alma9": {"name": "AlmaLinux 9", "cmd": '-almalinux 9'},
    "rocky9": {"name": "RockyLinux 9", "cmd": '-rockylinux 9'},
    "fedora43": {"name": "Fedora 43", "cmd": '-fedora 43'},
    "alpine": {"name": "Alpine 3.22", "cmd": '-alpinelinux 3.22'},
}

LANG_OPTIONS = {
    "en": "English",
    "cn": "Chinese",
    "jp": "Japanese",
}


def is_authorized(user_id: int) -> bool:
    """Check if user is authorized to use the bot."""
    if not ALLOWED_USERS or ALLOWED_USERS == [""]:
        return True
    return str(user_id) in ALLOWED_USERS


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start command - begin the conversation."""
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("Kamu tidak memiliki akses ke bot ini.")
        return ConversationHandler.END

    await update.message.reply_text(
        "Reinstall OS Bot - by xyzval\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Bot ini akan menginstall Windows/Linux di VPS kamu secara otomatis.\n\n"
        "PERINGATAN: Semua data di VPS akan DIHAPUS!\n\n"
        "Masukkan IP VPS kamu:"
    )
    return VPS_IP


async def get_vps_ip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Get VPS IP address."""
    ip = update.message.text.strip()
    context.user_data["vps_ip"] = ip
    await update.message.reply_text(
        f"IP: {ip}\n\n"
        "Masukkan SSH Port (default: 22):"
    )
    return VPS_PORT


async def get_vps_port(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Get VPS SSH port."""
    port_text = update.message.text.strip()
    port = int(port_text) if port_text.isdigit() else 22
    context.user_data["vps_port"] = port
    await update.message.reply_text(
        f"Port: {port}\n\n"
        "Masukkan SSH Username (default: root):"
    )
    return VPS_USER


async def get_vps_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Get VPS SSH username."""
    username = update.message.text.strip() or "root"
    context.user_data["vps_user"] = username
    await update.message.reply_text(
        f"Username: {username}\n\n"
        "Masukkan SSH Password:"
    )
    return VPS_PASS


async def get_vps_pass(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Get VPS SSH password and show OS menu."""
    password = update.message.text.strip()
    context.user_data["vps_pass"] = password

    # Delete password message for security
    try:
        await update.message.delete()
    except Exception:
        pass

    # Show OS selection menu
    keyboard = [
        [InlineKeyboardButton("WINDOWS", callback_data="cat_windows")],
        [InlineKeyboardButton("LINUX", callback_data="cat_linux")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Detail VPS tersimpan.\n\n"
        f"IP: {context.user_data['vps_ip']}\n"
        f"Port: {context.user_data['vps_port']}\n"
        f"User: {context.user_data['vps_user']}\n"
        f"Pass: {'*' * len(password)}\n\n"
        "Pilih kategori OS:",
        reply_markup=reply_markup,
    )
    return SELECT_OS


async def select_os_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show OS options based on category."""
    query = update.callback_query
    await query.answer()

    category = query.data

    if category == "cat_windows":
        keyboard = []
        for key, val in WINDOWS_OPTIONS.items():
            keyboard.append([InlineKeyboardButton(val["name"], callback_data=f"os_{key}")])
        keyboard.append([InlineKeyboardButton("Kembali", callback_data="back_main")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Pilih Windows:", reply_markup=reply_markup)

    elif category == "cat_linux":
        keyboard = []
        for key, val in LINUX_OPTIONS.items():
            keyboard.append([InlineKeyboardButton(val["name"], callback_data=f"os_{key}")])
        keyboard.append([InlineKeyboardButton("Kembali", callback_data="back_main")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Pilih Linux:", reply_markup=reply_markup)

    elif category == "back_main":
        keyboard = [
            [InlineKeyboardButton("WINDOWS", callback_data="cat_windows")],
            [InlineKeyboardButton("LINUX", callback_data="cat_linux")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Pilih kategori OS:", reply_markup=reply_markup)

    return SELECT_OS


async def select_os(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle OS selection."""
    query = update.callback_query
    await query.answer()

    os_key = query.data.replace("os_", "")
    context.user_data["os_key"] = os_key

    # Determine if Windows or Linux
    if os_key in WINDOWS_OPTIONS:
        context.user_data["os_name"] = WINDOWS_OPTIONS[os_key]["name"]
        context.user_data["os_cmd"] = WINDOWS_OPTIONS[os_key]["cmd"]
        context.user_data["os_type"] = "windows"

        # Ask for language
        keyboard = [
            [InlineKeyboardButton("English", callback_data="lang_en")],
            [InlineKeyboardButton("Chinese", callback_data="lang_cn")],
            [InlineKeyboardButton("Japanese", callback_data="lang_jp")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"OS: {context.user_data['os_name']}\n\n"
            "Pilih bahasa:",
            reply_markup=reply_markup,
        )
        return SELECT_LANG

    elif os_key in LINUX_OPTIONS:
        context.user_data["os_name"] = LINUX_OPTIONS[os_key]["name"]
        context.user_data["os_cmd"] = LINUX_OPTIONS[os_key]["cmd"]
        context.user_data["os_type"] = "linux"
        context.user_data["lang"] = ""

        # Skip language, go to confirm
        return await show_confirm(query, context)

    return SELECT_OS


async def select_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle language selection."""
    query = update.callback_query
    await query.answer()

    lang = query.data.replace("lang_", "")
    context.user_data["lang"] = lang

    return await show_confirm(query, context)


async def show_confirm(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show confirmation before install."""
    data = context.user_data

    # Build summary
    summary = (
        "KONFIRMASI INSTALASI\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"VPS: {data['vps_ip']}:{data['vps_port']}\n"
        f"User: {data['vps_user']}\n"
        f"OS: {data['os_name']}\n"
    )
    if data.get("lang"):
        summary += f"Bahasa: {LANG_OPTIONS.get(data['lang'], data['lang'])}\n"

    if data["os_type"] == "windows":
        summary += (
            "\nLogin setelah selesai:\n"
            f"  RDP Host: {data['vps_ip']}:3389\n"
            "  Username: Administrator\n"
            "  Password: Teddysun.com\n"
        )
    else:
        summary += (
            "\nLogin setelah selesai:\n"
            f"  SSH: root@{data['vps_ip']}\n"
            "  Password: yang kamu set / password123\n"
        )

    summary += (
        "\nPERINGATAN: SEMUA DATA AKAN DIHAPUS!\n"
        "\nLanjutkan instalasi?"
    )

    keyboard = [
        [
            InlineKeyboardButton("YA, INSTALL!", callback_data="confirm_yes"),
            InlineKeyboardButton("BATAL", callback_data="confirm_no"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(summary, reply_markup=reply_markup)
    return CONFIRM


async def confirm_install(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle confirmation."""
    query = update.callback_query
    await query.answer()

    if query.data == "confirm_no":
        await query.edit_message_text("Instalasi dibatalkan.")
        return ConversationHandler.END

    # Start installation
    await query.edit_message_text(
        "Memulai instalasi...\n"
        "Menghubungkan ke VPS via SSH..."
    )

    data = context.user_data
    success = await run_install(query, context, data)

    if success:
        if data["os_type"] == "windows":
            await query.edit_message_text(
                "INSTALASI DIMULAI!\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"OS: {data['os_name']}\n"
                "Status: VPS sedang reboot & install\n"
                "Estimasi: 15-30 menit\n\n"
                "Login setelah selesai:\n"
                f"  RDP Host: {data['vps_ip']}:3389\n"
                "  Username: Administrator\n"
                "  Password: Teddysun.com\n\n"
                "Gunakan /status untuk cek apakah VPS sudah online."
            )
        else:
            await query.edit_message_text(
                "INSTALASI DIMULAI!\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"OS: {data['os_name']}\n"
                "Status: VPS sedang reboot & install\n"
                "Estimasi: 10-20 menit\n\n"
                "Login setelah selesai:\n"
                f"  SSH: ssh root@{data['vps_ip']}\n"
                "  Password: password123\n\n"
                "Gunakan /status untuk cek apakah VPS sudah online."
            )
    else:
        await query.edit_message_text(
            "GAGAL!\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Tidak bisa terhubung ke VPS.\n"
            "Pastikan:\n"
            "- IP benar\n"
            "- Port SSH benar\n"
            "- Username & password benar\n"
            "- VPS online\n\n"
            "Gunakan /start untuk coba lagi."
        )

    return ConversationHandler.END


async def run_install(query, context: ContextTypes.DEFAULT_TYPE, data: dict) -> bool:
    """Connect to VPS via SSH and run the install command."""
    try:
        # Build the install command
        if data["os_type"] == "windows":
            cmd = (
                "wget --no-check-certificate -qO /tmp/InstallNET.sh "
                "'https://raw.githubusercontent.com/leitbogioro/Tools/master/Linux_reinstall/InstallNET.sh' && "
                f"chmod a+x /tmp/InstallNET.sh && "
                f"bash /tmp/InstallNET.sh {data['os_cmd']} -lang \"{data['lang']}\""
            )
        else:
            cmd = (
                "wget --no-check-certificate -qO /tmp/InstallNET.sh "
                "'https://raw.githubusercontent.com/leitbogioro/Tools/master/Linux_reinstall/InstallNET.sh' && "
                f"chmod a+x /tmp/InstallNET.sh && "
                f"bash /tmp/InstallNET.sh {data['os_cmd']} -pwd 'password123'"
            )

        # Connect via SSH
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            hostname=data["vps_ip"],
            port=data["vps_port"],
            username=data["vps_user"],
            password=data["vps_pass"],
            timeout=30,
        )

        # Execute command (non-blocking, because VPS will reboot)
        transport = ssh.get_transport()
        channel = transport.open_session()
        channel.exec_command(cmd)

        # Wait a bit to make sure command started
        await asyncio.sleep(5)

        ssh.close()
        return True

    except Exception as e:
        logger.error(f"SSH Error: {e}")
        return False


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Check if VPS is online (ping test)."""
    if not is_authorized(update.effective_user.id):
        await update.message.reply_text("Tidak ada akses.")
        return

    vps_ip = context.user_data.get("vps_ip")
    if not vps_ip:
        await update.message.reply_text(
            "Belum ada VPS yang terdaftar.\n"
            "Gunakan /start untuk memulai."
        )
        return

    await update.message.reply_text(f"Mengecek status {vps_ip}...")

    # Ping test
    result = await asyncio.create_subprocess_exec(
        "ping", "-c", "3", "-W", "5", vps_ip,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await result.communicate()

    if result.returncode == 0:
        await update.message.reply_text(
            f"VPS {vps_ip} ONLINE!\n\n"
            "Coba login sekarang:\n"
            f"  RDP: {vps_ip}:3389 (Windows)\n"
            f"  SSH: ssh root@{vps_ip} (Linux)"
        )
    else:
        await update.message.reply_text(
            f"VPS {vps_ip} masih OFFLINE.\n"
            "Mungkin masih dalam proses instalasi.\n"
            "Coba lagi dalam beberapa menit."
        )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the conversation."""
    await update.message.reply_text("Dibatalkan. Gunakan /start untuk mulai lagi.")
    return ConversationHandler.END


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show help message."""
    await update.message.reply_text(
        "Reinstall OS Bot - by xyzval\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Perintah:\n"
        "  /start  - Mulai reinstall OS\n"
        "  /status - Cek status VPS (online/offline)\n"
        "  /cancel - Batalkan proses\n"
        "  /help   - Tampilkan bantuan\n\n"
        "Windows yang tersedia:\n"
        "  - Windows 10\n"
        "  - Windows 11\n"
        "  - Windows Server 2012 R2\n"
        "  - Windows Server 2016\n"
        "  - Windows Server 2019\n"
        "  - Windows Server 2022\n\n"
        "Linux yang tersedia:\n"
        "  - Debian 11, 12\n"
        "  - Ubuntu 20.04, 22.04, 24.04\n"
        "  - CentOS 9 Stream\n"
        "  - AlmaLinux 9\n"
        "  - RockyLinux 9\n"
        "  - Fedora 43\n"
        "  - Alpine 3.22\n\n"
        "Login setelah install:\n"
        "  Windows: Administrator / Teddysun.com (RDP port 3389)\n"
        "  Linux: root / password123 (SSH port 22)"
    )


def main() -> None:
    """Run the bot."""
    if not BOT_TOKEN:
        print("ERROR: BOT_TOKEN not set!")
        print("Buat file .env dan isi: BOT_TOKEN=your_bot_token_here")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    # Conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            VPS_IP: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_vps_ip)],
            VPS_PORT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_vps_port)],
            VPS_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_vps_user)],
            VPS_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_vps_pass)],
            SELECT_OS: [CallbackQueryHandler(select_os, pattern="^os_"),
                        CallbackQueryHandler(select_os_category, pattern="^(cat_|back_)")],
            SELECT_LANG: [CallbackQueryHandler(select_lang, pattern="^lang_")],
            CONFIRM: [CallbackQueryHandler(confirm_install, pattern="^confirm_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("help", help_command))

    print("Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

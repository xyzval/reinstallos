#!/usr/bin/env python3
"""
Telegram Bot - Reinstall OS v2.0
by xyzval

Features:
- Multi-VPS management (save multiple VPS)
- Inline button menu (reinstall, info, reboot, shutdown, ssh)
- Professional loading UI
- Auto-fix Linux password after install
"""

import os
import json
import logging
import asyncio
import socket
import time as _time
import paramiko
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
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

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ALLOWED_USERS = os.getenv("ALLOWED_USERS", "").split(",")
VPS_FILE = "/opt/reinstallos/vps_data.json"

# Conversation states
ADD_VPS, SELECT_VPS_ACTION, SELECT_OS, SELECT_LANG, CONFIRM, SSH_CMD = range(6)


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
    "debian12": {"name": "Debian 12", "cmd": '-debian 12', "engine": "leitbogioro"},
    "debian11": {"name": "Debian 11", "cmd": '-debian 11', "engine": "leitbogioro"},
    "debian10": {"name": "Debian 10", "cmd": '-debian 10', "engine": "leitbogioro"},
    "debian9": {"name": "Debian 9", "cmd": '-debian 9', "engine": "leitbogioro"},
    "ubuntu2204": {"name": "Ubuntu 22.04", "cmd": 'ubuntu 22.04', "engine": "bin456789"},
    "ubuntu2004": {"name": "Ubuntu 20.04", "cmd": 'ubuntu 20.04', "engine": "bin456789"},
    "centos9": {"name": "CentOS 9 Stream", "cmd": '-centos 9', "engine": "leitbogioro"},
    "alma9": {"name": "AlmaLinux 9", "cmd": '-almalinux 9', "engine": "leitbogioro"},
}

LANG_OPTIONS = {"en": "English", "cn": "Chinese", "jp": "Japanese"}



# ============ VPS Storage ============

def load_vps_list(user_id: int) -> list:
    """Load VPS list from JSON file."""
    try:
        if os.path.exists(VPS_FILE):
            with open(VPS_FILE, 'r') as f:
                data = json.load(f)
            return data.get(str(user_id), [])
    except Exception:
        pass
    return []


def save_vps_list(user_id: int, vps_list: list):
    """Save VPS list to JSON file."""
    try:
        data = {}
        if os.path.exists(VPS_FILE):
            with open(VPS_FILE, 'r') as f:
                data = json.load(f)
        data[str(user_id)] = vps_list
        with open(VPS_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Save VPS error: {e}")


def is_authorized(user_id: int) -> bool:
    if not ALLOWED_USERS or ALLOWED_USERS == [""]:
        return True
    return str(user_id) in ALLOWED_USERS


def parse_vps_detail(text: str) -> dict:
    """Parse ip:port@user:password"""
    text = text.strip()
    result = {"vps_ip": "", "vps_port": 22, "vps_user": "root", "vps_pass": ""}
    try:
        if "@" not in text:
            return None
        connection, login = text.split("@", 1)
        if ":" in connection:
            ip, port = connection.rsplit(":", 1)
            result["vps_ip"] = ip
            result["vps_port"] = int(port)
        else:
            result["vps_ip"] = connection
        if ":" in login:
            user, password = login.split(":", 1)
            result["vps_user"] = user
            result["vps_pass"] = password
        else:
            return None
        if not result["vps_ip"] or not result["vps_pass"]:
            return None
        return result
    except (ValueError, IndexError):
        return None



# ============ Menu Helpers ============

def get_vps_list_keyboard(user_id: int):
    """Build VPS list keyboard."""
    vps_list = load_vps_list(user_id)
    keyboard = []
    for i, vps in enumerate(vps_list):
        label = f"🖥 {vps['vps_ip']}:{vps['vps_port']}"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"selvps_{i}")])
    keyboard.append([InlineKeyboardButton("➕ Tambah VPS Baru", callback_data="addvps")])
    return InlineKeyboardMarkup(keyboard)


def get_action_keyboard():
    """Build action menu keyboard."""
    keyboard = [
        [InlineKeyboardButton("🔄 REINSTALL OS", callback_data="act_reinstall")],
        [
            InlineKeyboardButton("📊 Info", callback_data="act_info"),
            InlineKeyboardButton("🔄 Reboot", callback_data="act_reboot"),
            InlineKeyboardButton("⏹ Shutdown", callback_data="act_shutdown"),
        ],
        [
            InlineKeyboardButton("💻 SSH Command", callback_data="act_ssh"),
            InlineKeyboardButton("📡 Status", callback_data="act_status"),
        ],
        [
            InlineKeyboardButton("🗑 Hapus VPS", callback_data="act_delete"),
            InlineKeyboardButton("◀️ Kembali", callback_data="act_back"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_vps_info_text(data: dict) -> str:
    """Build VPS info header."""
    return (
        "─────────────────────────────\n"
        f"  🖥️  VPS: {data['vps_ip']}:{data['vps_port']}\n"
        f"  👤  User: {data['vps_user']}\n"
        "─────────────────────────────"
    )



# ============ Handlers ============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show VPS list or add new."""
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("Tidak ada akses.")
        return ConversationHandler.END

    vps_list = load_vps_list(user_id)
    if vps_list:
        await update.message.reply_text(
            "─────────────────────────────\n"
            "  🖥️  Reinstall OS Bot\n"
            "─────────────────────────────\n\n"
            "  Pilih VPS atau tambah baru:\n",
            reply_markup=get_vps_list_keyboard(user_id),
        )
        return SELECT_VPS_ACTION
    else:
        await update.message.reply_text(
            "─────────────────────────────\n"
            "  🖥️  Reinstall OS Bot\n"
            "─────────────────────────────\n\n"
            "  Belum ada VPS tersimpan.\n"
            "  Kirim detail VPS dengan format:\n\n"
            "  `ip:port@user:password`\n\n"
            "  Contoh:\n"
            "  `104.207.77.243:22@root:Bolehtuh1`",
            parse_mode="Markdown",
        )
        return ADD_VPS


async def add_vps_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Parse and save new VPS."""
    text = update.message.text.strip()
    data = parse_vps_detail(text)

    if data is None:
        await update.message.reply_text(
            "Format salah! Kirim ulang:\n\n"
            "`ip:port@user:password`\n\n"
            "Contoh: `104.207.77.243:22@root:Bolehtuh1`",
            parse_mode="Markdown",
        )
        return ADD_VPS

    # Delete message (contains password)
    try:
        await update.message.delete()
    except Exception:
        pass

    # Save to VPS list
    user_id = update.effective_user.id
    vps_list = load_vps_list(user_id)
    # Check if already exists
    exists = any(v['vps_ip'] == data['vps_ip'] and v['vps_port'] == data['vps_port'] for v in vps_list)
    if not exists:
        vps_list.append(data)
        save_vps_list(user_id, vps_list)

    # Set as active VPS
    context.user_data.update(data)

    # Show action menu
    await update.message.reply_text(
        get_vps_info_text(data) + "\n\n  ✅ VPS tersimpan!\n\n  Pilih aksi:",
        reply_markup=get_action_keyboard(),
    )
    return SELECT_VPS_ACTION



async def select_vps(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle VPS selection or add new."""
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id

    if query.data == "addvps":
        await query.edit_message_text(
            "─────────────────────────────\n"
            "  ➕  Tambah VPS Baru\n"
            "─────────────────────────────\n\n"
            "  Kirim detail VPS:\n\n"
            "  `ip:port@user:password`\n\n"
            "  Contoh:\n"
            "  `104.207.77.243:22@root:Bolehtuh1`",
            parse_mode="Markdown",
        )
        return ADD_VPS

    if query.data.startswith("selvps_"):
        idx = int(query.data.replace("selvps_", ""))
        vps_list = load_vps_list(user_id)
        if idx < len(vps_list):
            data = vps_list[idx]
            context.user_data.update(data)
            await query.edit_message_text(
                get_vps_info_text(data) + "\n\n  Pilih aksi:",
                reply_markup=get_action_keyboard(),
            )
            return SELECT_VPS_ACTION

    return SELECT_VPS_ACTION


async def handle_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle action buttons."""
    query = update.callback_query
    await query.answer()
    data = context.user_data
    user_id = update.effective_user.id
    action = query.data

    if action == "act_back":
        await query.edit_message_text(
            "─────────────────────────────\n"
            "  🖥️  Reinstall OS Bot\n"
            "─────────────────────────────\n\n"
            "  Pilih VPS atau tambah baru:\n",
            reply_markup=get_vps_list_keyboard(user_id),
        )
        return SELECT_VPS_ACTION

    if action == "act_delete":
        vps_list = load_vps_list(user_id)
        vps_list = [v for v in vps_list if not (v['vps_ip'] == data.get('vps_ip') and v['vps_port'] == data.get('vps_port'))]
        save_vps_list(user_id, vps_list)
        await query.edit_message_text(
            f"  🗑 VPS {data.get('vps_ip')} dihapus!\n\n",
            reply_markup=get_vps_list_keyboard(user_id),
        )
        return SELECT_VPS_ACTION

    if action == "act_reinstall":
        keyboard = [
            [InlineKeyboardButton("WINDOWS", callback_data="cat_windows")],
            [InlineKeyboardButton("LINUX", callback_data="cat_linux")],
            [InlineKeyboardButton("◀️ Kembali", callback_data="act_back_menu")],
        ]
        await query.edit_message_text(
            get_vps_info_text(data) + "\n\n  Pilih kategori OS:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return SELECT_OS

    if action == "act_ssh":
        keyboard = [[InlineKeyboardButton("◀️ Kembali", callback_data="act_back_menu")]]
        await query.edit_message_text(
            get_vps_info_text(data) + "\n\n"
            "  💻 Kirim command SSH:\n\n"
            "  Contoh: `uptime` atau `df -h`\n\n"
            "  Atau klik Kembali untuk menu.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return SSH_CMD

    if action == "act_info":
        await query.edit_message_text(f"  ⏳ Mengambil info {data['vps_ip']}...")
        info_text = await get_vps_system_info(data)
        keyboard = [[InlineKeyboardButton("◀️ Kembali", callback_data="act_back_menu")]]
        await query.edit_message_text(info_text, reply_markup=InlineKeyboardMarkup(keyboard))
        return SELECT_VPS_ACTION

    if action == "act_reboot":
        result = await ssh_exec(data, "reboot")
        await query.edit_message_text(
            "─────────────────────────────\n"
            "  🔄  VPS Rebooting\n"
            "─────────────────────────────\n\n"
            f"  🎯 {data['vps_ip']}\n"
            "  Status: Reboot sent!\n"
            "  Online dalam 1-3 menit.\n\n"
            "─────────────────────────────",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Kembali", callback_data="act_back_menu")]]),
        )
        return SELECT_VPS_ACTION

    if action == "act_shutdown":
        result = await ssh_exec(data, "shutdown -h now")
        await query.edit_message_text(
            "─────────────────────────────\n"
            "  ⏹️  VPS Shutting Down\n"
            "─────────────────────────────\n\n"
            f"  🎯 {data['vps_ip']}\n"
            "  Status: Shutdown sent!\n\n"
            "─────────────────────────────",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Kembali", callback_data="act_back_menu")]]),
        )
        return SELECT_VPS_ACTION

    if action == "act_status":
        vps_ip = data["vps_ip"]
        await query.edit_message_text(f"  📡 Checking {vps_ip}...")
        proc = await asyncio.create_subprocess_exec(
            "ping", "-c", "3", "-W", "5", vps_ip,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        if proc.returncode == 0:
            status_text = f"  ✅ {vps_ip} ONLINE"
        else:
            status_text = f"  ❌ {vps_ip} OFFLINE"
        keyboard = [[InlineKeyboardButton("◀️ Kembali", callback_data="act_back_menu")]]
        await query.edit_message_text(
            "─────────────────────────────\n"
            "  📡  VPS Status\n"
            "─────────────────────────────\n\n"
            f"{status_text}\n\n"
            "─────────────────────────────",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return SELECT_VPS_ACTION

    if action == "act_back_menu":
        await query.edit_message_text(
            get_vps_info_text(data) + "\n\n  Pilih aksi:",
            reply_markup=get_action_keyboard(),
        )
        return SELECT_VPS_ACTION

    return SELECT_VPS_ACTION



async def ssh_cmd_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Execute SSH command from chat."""
    data = context.user_data
    cmd_text = update.message.text.strip()

    await update.message.reply_text(f"⏳ `{cmd_text}`...", parse_mode="Markdown")

    result = await ssh_exec(data, cmd_text)
    if len(result) > 3000:
        result = result[:3000] + "\n... (truncated)"

    keyboard = [[InlineKeyboardButton("◀️ Menu", callback_data="act_back_menu")]]
    await update.message.reply_text(
        "─────────────────────────────\n"
        "  💻  SSH Result\n"
        "─────────────────────────────\n\n"
        f"  ⌨️  {cmd_text}\n\n"
        f"{result}\n\n"
        "─────────────────────────────\n\n"
        "Kirim command lain atau klik Menu.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return SSH_CMD


# ============ SSH Helpers ============

async def ssh_exec(data: dict, cmd: str) -> str:
    """Execute SSH command and return output."""
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            hostname=data["vps_ip"], port=data["vps_port"],
            username=data["vps_user"], password=data["vps_pass"],
            timeout=15, allow_agent=False, look_for_keys=False,
        )
        stdin, stdout, stderr = ssh.exec_command(cmd)
        stdout.channel.settimeout(30)
        output = stdout.read().decode('utf-8', errors='ignore').strip()
        error = stderr.read().decode('utf-8', errors='ignore').strip()
        ssh.close()
        return output if output else error if error else "(no output)"
    except Exception as e:
        return f"Error: {str(e)}"


async def get_vps_system_info(data: dict) -> str:
    """Get VPS system info via SSH."""
    info_cmd = (
        "echo \"OS: $(cat /etc/os-release 2>/dev/null | grep PRETTY_NAME | cut -d'\"' -f2)\";"
        "echo \"Kernel: $(uname -r)\";"
        "echo \"Uptime: $(uptime -p 2>/dev/null || uptime)\";"
        "echo \"CPU: $(nproc) cores\";"
        "echo \"RAM: $(free -m | awk '/Mem:/ {printf \"%dMB / %dMB (%.0f%%)\", $3, $2, $3/$2*100}')\";"
        "echo \"Disk: $(df -h / | awk 'NR==2 {printf \"%s / %s (%s)\", $3, $2, $5}')\";"
        "echo \"Load: $(cat /proc/loadavg | awk '{print $1, $2, $3}')\""
    )
    result = await ssh_exec(data, info_cmd)
    return (
        "─────────────────────────────\n"
        "  📊  VPS System Info\n"
        "─────────────────────────────\n\n"
        f"  🎯 {data['vps_ip']}:{data['vps_port']}\n\n"
        "─────────────────────────────\n\n"
        f"{result}\n\n"
        "─────────────────────────────"
    )



# ============ OS Install Flow ============

async def select_os_category(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show OS options."""
    query = update.callback_query
    await query.answer()
    data = context.user_data
    category = query.data

    if category == "cat_windows":
        keyboard = [[InlineKeyboardButton(v["name"], callback_data=f"os_{k}")] for k, v in WINDOWS_OPTIONS.items()]
        keyboard.append([InlineKeyboardButton("◀️ Kembali", callback_data="act_back_menu")])
        await query.edit_message_text("Pilih Windows:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif category == "cat_linux":
        keyboard = [[InlineKeyboardButton(v["name"], callback_data=f"os_{k}")] for k, v in LINUX_OPTIONS.items()]
        keyboard.append([InlineKeyboardButton("◀️ Kembali", callback_data="act_back_menu")])
        await query.edit_message_text("Pilih Linux:", reply_markup=InlineKeyboardMarkup(keyboard))
    elif category == "act_back_menu":
        await query.edit_message_text(
            get_vps_info_text(data) + "\n\n  Pilih aksi:",
            reply_markup=get_action_keyboard(),
        )
        return SELECT_VPS_ACTION
    return SELECT_OS


async def select_os(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle OS selection."""
    query = update.callback_query
    await query.answer()
    os_key = query.data.replace("os_", "")

    if os_key in WINDOWS_OPTIONS:
        context.user_data["os_name"] = WINDOWS_OPTIONS[os_key]["name"]
        context.user_data["os_cmd"] = WINDOWS_OPTIONS[os_key]["cmd"]
        context.user_data["os_type"] = "windows"
        keyboard = [[InlineKeyboardButton(v, callback_data=f"lang_{k}")] for k, v in LANG_OPTIONS.items()]
        await query.edit_message_text(f"OS: {context.user_data['os_name']}\n\nPilih bahasa:", reply_markup=InlineKeyboardMarkup(keyboard))
        return SELECT_LANG
    elif os_key in LINUX_OPTIONS:
        context.user_data["os_name"] = LINUX_OPTIONS[os_key]["name"]
        context.user_data["os_cmd"] = LINUX_OPTIONS[os_key]["cmd"]
        context.user_data["os_type"] = "linux"
        context.user_data["os_engine"] = LINUX_OPTIONS[os_key]["engine"]
        context.user_data["lang"] = ""
        return await show_confirm(query, context)
    return SELECT_OS


async def select_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle language selection."""
    query = update.callback_query
    await query.answer()
    context.user_data["lang"] = query.data.replace("lang_", "")
    return await show_confirm(query, context)


async def show_confirm(query, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show confirmation."""
    data = context.user_data
    os_type = data["os_type"]
    summary = (
        "─────────────────────────────\n"
        "  ⚠️  KONFIRMASI REINSTALL\n"
        "─────────────────────────────\n\n"
        f"  🎯 {data['vps_ip']}:{data['vps_port']}\n"
        f"  📦 {data['os_name']}\n"
    )
    if data.get("lang"):
        summary += f"  🌐 {LANG_OPTIONS.get(data['lang'], '')}\n"
    if os_type == "windows":
        summary += "\n  🔑 Login: Administrator / Teddysun.com\n"
    else:
        summary += "\n  🔑 Login: root / Bolehtuh1\n"
    summary += "\n  ⚠️ SEMUA DATA AKAN DIHAPUS!\n"

    keyboard = [
        [InlineKeyboardButton("✅ YA, INSTALL!", callback_data="confirm_yes"),
         InlineKeyboardButton("❌ BATAL", callback_data="confirm_no")]
    ]
    await query.edit_message_text(summary, reply_markup=InlineKeyboardMarkup(keyboard))
    return CONFIRM



async def confirm_install(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle install confirmation - runs monitoring in background."""
    query = update.callback_query
    await query.answer()

    if query.data == "confirm_no":
        data = context.user_data
        await query.edit_message_text(
            "  ❌ Dibatalkan.\n",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Menu", callback_data="act_back_menu")]]),
        )
        return SELECT_VPS_ACTION

    data = dict(context.user_data)  # Copy data for background task

    success = await run_install(query, context, data)

    if not success:
        error_msg = data.get("error_msg", "Unknown error")
        await query.edit_message_text(
            "─────────────────────────────\n"
            "  ❌  Installation Failed\n"
            "─────────────────────────────\n\n"
            f"  Error: {error_msg}\n",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Menu", callback_data="act_back_menu")]]),
        )
        return SELECT_VPS_ACTION

    # Launch monitoring in background task (bot stays free)
    chat_id = query.message.chat_id
    message_id = query.message.message_id
    bot = query.get_bot()

    asyncio.create_task(
        monitor_install_background(bot, chat_id, message_id, data)
    )

    # Conversation ends immediately - bot is free to respond to other commands
    return ConversationHandler.END


async def monitor_install_background(bot, chat_id: int, message_id: int, data: dict):
    """Background task: monitor VPS until online, update progress bar."""
    start_time = _time.time()
    vps_ip = data["vps_ip"]
    os_type = data["os_type"]
    check_port = 3389 if os_type == "windows" else 22

    await asyncio.sleep(30)

    online = False
    for i in range(60):  # max 30 minutes
        await asyncio.sleep(30)
        elapsed = int((_time.time() - start_time) / 60)
        progress_pct = min(int((elapsed / 20) * 100), 90)
        filled = int(progress_pct / 5.5)
        bar = "█" * filled + "░" * (18 - filled)

        # Update progress every 2 minutes
        if i % 4 == 0:
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=(
                        "─────────────────────────────\n"
                        "  ⚙️  OS Installation Service\n"
                        "─────────────────────────────\n\n"
                        f"  🎯 {data['vps_ip']}\n"
                        f"  📦 {data['os_name']}\n\n"
                        "─────────────────────────────\n\n"
                        "  ● SSH Connection      DONE\n"
                        "  ● Download Script     DONE\n"
                        "  ● Run Installer       DONE\n"
                        "  ◐ Installing OS       IN PROGRESS\n"
                        "  ○ Final Check         WAITING\n\n"
                        f"  ┃{bar}┃ {progress_pct}%\n\n"
                        f"  ⏱ Elapsed: {elapsed} min\n"
                        f"  ⏳ Remaining: ~{max(15 - elapsed, 2)} min\n\n"
                        "─────────────────────────────"
                    ),
                )
            except Exception:
                pass

        # Check if port is open
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((vps_ip, check_port))
            sock.close()
            if result == 0:
                online = True
                break
        except Exception:
            pass

    elapsed_final = int((_time.time() - start_time) / 60)

    # Send final result
    if online:
        if os_type == "windows":
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=(
                    "─────────────────────────────\n"
                    "  ✅  OS Installation Complete\n"
                    "─────────────────────────────\n\n"
                    f"  🎯 {data['vps_ip']}\n"
                    f"  📦 {data['os_name']}\n"
                    f"  ⏱ {elapsed_final} min\n\n"
                    "  ┃██████████████████┃ 100%\n\n"
                    "─────────────────────────────\n\n"
                    "  🔑 LOGIN:\n"
                    f"  Host: {data['vps_ip']}:3389\n"
                    "  User: Administrator\n"
                    "  Pass: Teddysun.com\n\n"
                    "─────────────────────────────\n\n"
                    "  /start untuk kembali ke menu"
                ),
            )
        else:
            await asyncio.sleep(10)
            fix_success = await fix_linux_password(vps_ip, data)
            pass_info = "  Pass: Bolehtuh1" if fix_success else "  Pass: Bolehtuh1 atau LeitboGi0662"
            fix_status = "● Root Login          FIXED" if fix_success else "⚠ Root Login          CHECK"

            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=(
                    "─────────────────────────────\n"
                    "  ✅  OS Installation Complete\n"
                    "─────────────────────────────\n\n"
                    f"  🎯 {data['vps_ip']}\n"
                    f"  📦 {data['os_name']}\n"
                    f"  ⏱ {elapsed_final} min\n\n"
                    f"  ┃██████████████████┃ 100%\n"
                    f"  {fix_status}\n\n"
                    "─────────────────────────────\n\n"
                    "  🔑 LOGIN:\n"
                    f"  Host: ssh root@{data['vps_ip']}\n"
                    f"{pass_info}\n\n"
                    "─────────────────────────────\n\n"
                    "  /start untuk kembali ke menu"
                ),
            )
    else:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=(
                "─────────────────────────────\n"
                "  ⚠️  Installation Timeout\n"
                "─────────────────────────────\n\n"
                f"  🎯 {data['vps_ip']}\n"
                f"  📦 {data['os_name']}\n"
                f"  ⏱ {elapsed_final} min\n\n"
                "  Kemungkinan masih install.\n"
                "  Cek VNC console.\n\n"
                "─────────────────────────────\n\n"
                "  /start untuk kembali ke menu"
            ),
        )



async def fix_linux_password(vps_ip: str, data: dict) -> bool:
    """Try to fix Linux root password after install."""
    default_passwords = ['Bolehtuh1', 'LeitboGi0662', 'Teddysun.com', 'teddysun.com', '']
    default_users = ['root', 'ubuntu', 'debian']
    try:
        fix_ssh = paramiko.SSHClient()
        fix_ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        connected = False
        for user in default_users:
            if connected:
                break
            for pwd in default_passwords:
                try:
                    fix_ssh.connect(hostname=vps_ip, port=22, username=user, password=pwd,
                                    timeout=10, allow_agent=False, look_for_keys=False)
                    connected = True
                    break
                except Exception:
                    continue
        if connected:
            fix_commands = (
                "echo 'root:Bolehtuh1' | sudo chpasswd 2>/dev/null; "
                "echo 'root:Bolehtuh1' | chpasswd 2>/dev/null; "
                "sudo sed -i 's/.*PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config 2>/dev/null; "
                "sed -i 's/.*PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config 2>/dev/null; "
                "sudo sed -i 's/.*PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config 2>/dev/null; "
                "sed -i 's/.*PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config 2>/dev/null; "
                "sudo systemctl restart sshd 2>/dev/null; sudo service ssh restart 2>/dev/null; "
                "systemctl restart sshd 2>/dev/null; service ssh restart 2>/dev/null; echo 'FIX_DONE'"
            )
            stdin, stdout, stderr = fix_ssh.exec_command(fix_commands)
            stdout.channel.settimeout(15)
            output = stdout.read().decode('utf-8', errors='ignore')
            fix_ssh.close()
            return "FIX_DONE" in output
    except Exception as e:
        logger.info(f"Linux fix error: {e}")
    return False


async def run_install(query, context: ContextTypes.DEFAULT_TYPE, data: dict):
    """Connect to VPS and run install."""
    try:
        if data["os_type"] == "windows":
            url = "https://raw.githubusercontent.com/leitbogioro/Tools/master/Linux_reinstall/InstallNET.sh"
            dl_cmd = f"wget --no-check-certificate -qO /tmp/InstallNET.sh '{url}' && chmod a+x /tmp/InstallNET.sh && echo 'DOWNLOAD_OK' || echo 'DOWNLOAD_FAIL'"
            run_cmd = f"bash /tmp/InstallNET.sh {data['os_cmd']} -lang '{data['lang']}' -pwd Bolehtuh1 -firmware > /tmp/reinstall.log 2>&1; reboot"
        elif data.get("os_engine") == "bin456789":
            url = "https://raw.githubusercontent.com/bin456789/reinstall/main/reinstall.sh"
            dl_cmd = f"wget --no-check-certificate -qO /tmp/reinstall.sh '{url}' && chmod a+x /tmp/reinstall.sh && echo 'DOWNLOAD_OK' || echo 'DOWNLOAD_FAIL'"
            run_cmd = f"bash /tmp/reinstall.sh {data['os_cmd']} --password Bolehtuh1 > /tmp/reinstall.log 2>&1; reboot"
        else:
            url = "https://raw.githubusercontent.com/leitbogioro/Tools/master/Linux_reinstall/InstallNET.sh"
            dl_cmd = f"wget --no-check-certificate -qO /tmp/InstallNET.sh '{url}' && chmod a+x /tmp/InstallNET.sh && echo 'DOWNLOAD_OK' || echo 'DOWNLOAD_FAIL'"
            run_cmd = f"bash /tmp/InstallNET.sh {data['os_cmd']} -pwd Bolehtuh1 -firmware > /tmp/reinstall.log 2>&1; reboot"

        # Step 1: Connect
        await query.edit_message_text(
            "─────────────────────────────\n"
            "  ⚙️  OS Installation Service\n"
            "─────────────────────────────\n\n"
            f"  🎯 {data['vps_ip']}\n  📦 {data['os_name']}\n\n"
            "  ◐ SSH Connection      CONNECTING\n"
            "  ○ Download Script     WAITING\n"
            "  ○ Run Installer       WAITING\n\n"
            "  ┃░░░░░░░░░░░░░░░░░░┃ 0%\n\n"
            "─────────────────────────────"
        )

        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(hostname=data["vps_ip"], port=data["vps_port"], username=data["vps_user"],
                    password=data["vps_pass"], timeout=30, allow_agent=False, look_for_keys=False)

        # Step 2: Download
        await query.edit_message_text(
            "─────────────────────────────\n"
            "  ⚙️  OS Installation Service\n"
            "─────────────────────────────\n\n"
            f"  🎯 {data['vps_ip']}\n  📦 {data['os_name']}\n\n"
            "  ● SSH Connection      DONE\n"
            "  ◐ Download Script     DOWNLOADING\n"
            "  ○ Run Installer       WAITING\n\n"
            "  ┃███░░░░░░░░░░░░░░░┃ 15%\n\n"
            "─────────────────────────────"
        )

        stdin, stdout, stderr = ssh.exec_command(dl_cmd)
        stdout.channel.settimeout(60)
        output = stdout.read().decode('utf-8', errors='ignore').strip()
        if "DOWNLOAD_OK" not in output:
            context.user_data["error_msg"] = f"Download gagal: {output}"
            ssh.close()
            return False

        # Step 3: Run
        await query.edit_message_text(
            "─────────────────────────────\n"
            "  ⚙️  OS Installation Service\n"
            "─────────────────────────────\n\n"
            f"  🎯 {data['vps_ip']}\n  📦 {data['os_name']}\n\n"
            "  ● SSH Connection      DONE\n"
            "  ● Download Script     DONE\n"
            "  ◐ Run Installer       RUNNING\n\n"
            "  ┃██████░░░░░░░░░░░░┃ 30%\n\n"
            "─────────────────────────────"
        )

        channel = ssh.get_transport().open_session()
        channel.exec_command(run_cmd)
        await asyncio.sleep(20)

        try:
            ssh.close()
        except Exception:
            pass
        return True

    except paramiko.AuthenticationException:
        context.user_data["error_msg"] = "Username atau password salah"
        return False
    except paramiko.ssh_exception.NoValidConnectionsError:
        context.user_data["error_msg"] = f"Port {data['vps_port']} tidak bisa diakses"
        return False
    except Exception as e:
        context.user_data["error_msg"] = str(e)
        return False



# ============ Auto-detect VPS handler (tanpa /start) ============

async def auto_add_vps(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Auto-detect VPS format dari pesan biasa tanpa harus /start."""
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        return

    text = update.message.text.strip()
    data = parse_vps_detail(text)

    if data is None:
        return  # Bukan format VPS, abaikan

    # Delete message (contains password)
    try:
        await update.message.delete()
    except Exception:
        pass

    # Save to VPS list
    vps_list = load_vps_list(user_id)
    exists = any(v['vps_ip'] == data['vps_ip'] and v['vps_port'] == data['vps_port'] for v in vps_list)
    if not exists:
        vps_list.append(data)
        save_vps_list(user_id, vps_list)

    # Set as active VPS
    context.user_data.update(data)

    # Show action menu langsung
    await update.message.reply_text(
        get_vps_info_text(data) + "\n\n  ✅ VPS tersimpan!\n\n  Pilih aksi:",
        reply_markup=get_action_keyboard(),
    )


# ============ Standalone Commands ============

async def cmd_ssh(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Standalone /ssh command."""
    if not is_authorized(update.effective_user.id):
        return
    data = context.user_data
    if not data.get("vps_ip"):
        await update.message.reply_text("Gunakan /start untuk pilih VPS dulu.")
        return
    cmd_text = update.message.text.replace("/ssh", "").strip()
    if not cmd_text:
        await update.message.reply_text("Cara: /ssh <command>\nContoh: /ssh uptime")
        return
    result = await ssh_exec(data, cmd_text)
    if len(result) > 3000:
        result = result[:3000] + "\n..."
    await update.message.reply_text(f"💻 {cmd_text}\n\n{result}")


async def cmd_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Standalone /info command."""
    if not is_authorized(update.effective_user.id):
        return
    data = context.user_data
    if not data.get("vps_ip"):
        await update.message.reply_text("Gunakan /start untuk pilih VPS dulu.")
        return
    info = await get_vps_system_info(data)
    await update.message.reply_text(info)


async def cmd_reboot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Standalone /reboot command."""
    if not is_authorized(update.effective_user.id):
        return
    data = context.user_data
    if not data.get("vps_ip"):
        await update.message.reply_text("Gunakan /start untuk pilih VPS dulu.")
        return
    await ssh_exec(data, "reboot")
    await update.message.reply_text(f"🔄 Reboot sent ke {data['vps_ip']}")


async def cmd_shutdown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Standalone /shutdown command."""
    if not is_authorized(update.effective_user.id):
        return
    data = context.user_data
    if not data.get("vps_ip"):
        await update.message.reply_text("Gunakan /start untuk pilih VPS dulu.")
        return
    await ssh_exec(data, "shutdown -h now")
    await update.message.reply_text(f"⏹ Shutdown sent ke {data['vps_ip']}")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Standalone /status command."""
    if not is_authorized(update.effective_user.id):
        return
    data = context.user_data
    if not data.get("vps_ip"):
        await update.message.reply_text("Gunakan /start untuk pilih VPS dulu.")
        return
    vps_ip = data["vps_ip"]
    proc = await asyncio.create_subprocess_exec(
        "ping", "-c", "3", "-W", "5", vps_ip,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()
    if proc.returncode == 0:
        await update.message.reply_text(f"✅ {vps_ip} ONLINE")
    else:
        await update.message.reply_text(f"❌ {vps_ip} OFFLINE")


async def cmd_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Update bot dari GitHub (git pull) dan restart service."""
    if not is_authorized(update.effective_user.id):
        return

    await update.message.reply_text("⏳ Mengupdate bot dari GitHub...")

    try:
        # Fetch latest dari remote
        proc = await asyncio.create_subprocess_exec(
            "git", "fetch", "origin", "main",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd="/opt/reinstallos",
        )
        await proc.communicate()

        # Cek apakah ada perbedaan
        proc = await asyncio.create_subprocess_exec(
            "git", "diff", "HEAD", "origin/main", "--stat",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd="/opt/reinstallos",
        )
        stdout, stderr = await proc.communicate()
        diff_output = stdout.decode('utf-8', errors='ignore').strip()

        if not diff_output:
            await update.message.reply_text(
                "─────────────────────────────\n"
                "  ✅  Bot Sudah Terbaru\n"
                "─────────────────────────────\n\n"
                "  Tidak ada perubahan baru.\n\n"
                "─────────────────────────────"
            )
            return

        # Reset ke versi terbaru dari GitHub
        proc = await asyncio.create_subprocess_exec(
            "git", "reset", "--hard", "origin/main",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd="/opt/reinstallos",
        )
        stdout, stderr = await proc.communicate()
        git_output = stdout.decode('utf-8', errors='ignore').strip()
        git_error = stderr.decode('utf-8', errors='ignore').strip()

        if proc.returncode != 0:
            await update.message.reply_text(
                "─────────────────────────────\n"
                "  ❌  Update Gagal\n"
                "─────────────────────────────\n\n"
                f"  Error:\n  {git_error or git_output}\n\n"
                "─────────────────────────────"
            )
            return

        # Ada update, restart service
        await update.message.reply_text(
            "─────────────────────────────\n"
            "  🔄  Update Berhasil!\n"
            "─────────────────────────────\n\n"
            f"  {diff_output}\n\n"
            "  ⏳ Merestart bot...\n"
            "─────────────────────────────"
        )

        # Restart service (bot akan mati dan hidup lagi otomatis)
        proc = await asyncio.create_subprocess_exec(
            "systemctl", "restart", "reinstall-bot",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

    except Exception as e:
        await update.message.reply_text(
            "─────────────────────────────\n"
            "  ❌  Update Error\n"
            "─────────────────────────────\n\n"
            f"  {str(e)}\n\n"
            "─────────────────────────────"
        )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Help command."""
    await update.message.reply_text(
        "─────────────────────────────\n"
        "  🖥️  Reinstall OS Bot v2.0\n"
        "─────────────────────────────\n\n"
        "Perintah:\n"
        "  /start    - Menu VPS\n"
        "  /info     - Info VPS\n"
        "  /ssh CMD  - SSH command\n"
        "  /reboot   - Reboot VPS\n"
        "  /shutdown - Shutdown VPS\n"
        "  /status   - Cek online\n"
        "  /update   - Update bot dari GitHub\n"
        "  /help     - Bantuan\n\n"
        "Tambah VPS:\n"
        "  Kirim langsung: ip:port@user:password\n\n"
        "Password:\n"
        "  Windows: Teddysun.com\n"
        "  Linux: Bolehtuh1\n\n"
        "─────────────────────────────"
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Dibatalkan. /start untuk mulai lagi.")
    return ConversationHandler.END



# ============ Main ============

async def post_init(application):
    """Set bot commands menu."""
    commands = [
        BotCommand("start", "Menu VPS"),
        BotCommand("info", "Info VPS"),
        BotCommand("ssh", "SSH command"),
        BotCommand("reboot", "Reboot VPS"),
        BotCommand("shutdown", "Shutdown VPS"),
        BotCommand("status", "Cek online/offline"),
        BotCommand("update", "Update bot dari GitHub"),
        BotCommand("help", "Bantuan"),
    ]
    await application.bot.set_my_commands(commands)


def main() -> None:
    if not BOT_TOKEN:
        print("ERROR: BOT_TOKEN not set!")
        return

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ADD_VPS: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_vps_handler)],
            SELECT_VPS_ACTION: [
                CallbackQueryHandler(select_vps, pattern="^(selvps_|addvps)"),
                CallbackQueryHandler(handle_action, pattern="^act_"),
                CallbackQueryHandler(select_os_category, pattern="^cat_"),
            ],
            SELECT_OS: [
                CallbackQueryHandler(select_os, pattern="^os_"),
                CallbackQueryHandler(select_os_category, pattern="^cat_"),
                CallbackQueryHandler(handle_action, pattern="^act_"),
            ],
            SELECT_LANG: [CallbackQueryHandler(select_lang, pattern="^lang_")],
            CONFIRM: [
                CallbackQueryHandler(confirm_install, pattern="^confirm_"),
                CallbackQueryHandler(handle_action, pattern="^act_"),
            ],
            SSH_CMD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ssh_cmd_handler),
                CallbackQueryHandler(handle_action, pattern="^act_"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", start)],
        allow_reentry=True,
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("info", cmd_info))
    app.add_handler(CommandHandler("ssh", cmd_ssh))
    app.add_handler(CommandHandler("reboot", cmd_reboot))
    app.add_handler(CommandHandler("shutdown", cmd_shutdown))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("update", cmd_update))
    app.add_handler(CommandHandler("help", cmd_help))

    # Auto-detect VPS format tanpa /start (priority rendah, jadi tidak ganggu conversation)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, auto_add_vps))

    print("Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()

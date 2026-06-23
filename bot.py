#!/usr/bin/env python3
"""
Telegram Bot - Reinstall OS
by xyzval

Bot Telegram untuk reinstall VPS ke Windows/Linux secara otomatis.
Kirim detail VPS dalam 1 pesan, pilih OS, bot akan menginstall otomatis.
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
VPS_DETAIL, SELECT_OS, SELECT_LANG, CONFIRM = range(4)

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
    "debian12": {"name": "Debian 12", "cmd": 'debian 12'},
    "debian11": {"name": "Debian 11", "cmd": 'debian 11'},
    "ubuntu2204": {"name": "Ubuntu 22.04", "cmd": 'ubuntu 22.04'},
    "ubuntu2004": {"name": "Ubuntu 20.04", "cmd": 'ubuntu 20.04'},
    "centos9": {"name": "CentOS 9 Stream", "cmd": 'centos 9'},
    "alma9": {"name": "AlmaLinux 9", "cmd": 'almalinux 9'},
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


def parse_vps_detail(text: str) -> dict:
    """
    Parse VPS detail dari 1 pesan.
    Format: ip:port@user:password
    Contoh: 209.74.81.155:22@root:password123
    """
    text = text.strip()

    result = {
        "vps_ip": "",
        "vps_port": 22,
        "vps_user": "root",
        "vps_pass": "",
    }

    try:
        # Split by @ -> [ip:port, user:password]
        if "@" not in text:
            return None

        connection, login = text.split("@", 1)

        # Parse ip:port
        if ":" in connection:
            ip, port = connection.rsplit(":", 1)
            result["vps_ip"] = ip
            result["vps_port"] = int(port)
        else:
            result["vps_ip"] = connection
            result["vps_port"] = 22

        # Parse user:password
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


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start command - begin the conversation."""
    user_id = update.effective_user.id
    if not is_authorized(user_id):
        await update.message.reply_text("Kamu tidak memiliki akses ke bot ini.")
        return ConversationHandler.END

    await update.message.reply_text(
        "Reinstall OS Bot - by xyzval\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Kirim detail VPS dengan format:\n\n"
        "`ip:port@user:password`\n\n"
        "Contoh:\n"
        "`209.74.81.155:22@root:password123`",
        parse_mode="Markdown",
    )
    return VPS_DETAIL


async def get_vps_detail(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Parse VPS detail from single message."""
    text = update.message.text.strip()

    # Parse the detail
    data = parse_vps_detail(text)

    if data is None:
        await update.message.reply_text(
            "Format salah! Kirim ulang dengan format:\n\n"
            "`ip:port@user:password`\n\n"
            "Contoh:\n"
            "`209.74.81.155:22@root:password123`",
            parse_mode="Markdown",
        )
        return VPS_DETAIL

    # Store data
    context.user_data.update(data)

    # Delete message for security (contains password)
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
        "VPS tersimpan!\n\n"
        f"  IP   : {data['vps_ip']}\n"
        f"  Port : {data['vps_port']}\n"
        f"  User : {data['vps_user']}\n"
        f"  Pass : {'*' * len(data['vps_pass'])}\n\n"
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
            "  Password: Bolehtuh1\n"
        )
    else:
        summary += (
            "\nLogin setelah selesai:\n"
            f"  SSH: root@{data['vps_ip']}\n"
            "  Password: Bolehtuh1\n"
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
        await query.edit_message_text("Instalasi dibatalkan.\n\nGunakan /start untuk mulai lagi.")
        return ConversationHandler.END

    data = context.user_data

    # Loading: Step 1
    await query.edit_message_text(
        f"Menginstall {data['os_name']}...\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "[ ] Menghubungkan ke VPS...\n"
        "[ ] Download script...\n"
        "[ ] Menjalankan installer...\n"
        "[ ] Menunggu reboot...\n"
        "[ ] Verifikasi selesai..."
    )

    success = await run_install(query, context, data)

    if not success:
        error_msg = data.get("error_msg", "Unknown error")
        await query.edit_message_text(
            "GAGAL!\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Error: {error_msg}\n\n"
            f"Detail koneksi:\n"
            f"  IP: {data['vps_ip']}\n"
            f"  Port: {data['vps_port']}\n"
            f"  User: {data['vps_user']}\n\n"
            "Gunakan /start untuk coba lagi."
        )
        return ConversationHandler.END

    # Loading: Step 4 - waiting for reboot
    await query.edit_message_text(
        f"Menginstall {data['os_name']}...\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "[✓] Menghubungkan ke VPS\n"
        "[✓] Download script\n"
        "[✓] Menjalankan installer\n"
        "[⏳] Menunggu VPS reboot & install OS...\n"
        "[ ] Verifikasi selesai\n\n"
        "Estimasi: 15-30 menit\n"
        "Mohon tunggu..."
    )

    # Monitor: ping VPS every 30s until it comes back online
    vps_ip = data["vps_ip"]
    vps_port = data.get("vps_port", 22)
    os_type = data["os_type"]

    # Determine which port to check (RDP for Windows, SSH for Linux)
    check_port = 3389 if os_type == "windows" else 22

    # Wait for VPS to go offline first (reboot)
    await asyncio.sleep(30)

    # Then wait for VPS to come back online (max 30 minutes)
    online = False
    for i in range(60):  # 60 * 30s = 30 minutes max
        await asyncio.sleep(30)

        # Update loading message every 2 minutes
        minutes_passed = (i + 1) * 0.5
        if i % 4 == 0:
            try:
                await query.edit_message_text(
                    f"Menginstall {data['os_name']}...\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    "[✓] Menghubungkan ke VPS\n"
                    "[✓] Download script\n"
                    "[✓] Menjalankan installer\n"
                    f"[⏳] Menginstall OS... ({int(minutes_passed)} menit)\n"
                    "[ ] Verifikasi selesai\n\n"
                    "Mohon tunggu..."
                )
            except Exception:
                pass

        # Check if target port is open
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((vps_ip, check_port))
            sock.close()
            if result == 0:
                # Port is open! VPS is back online with new OS
                online = True
                break
        except Exception:
            pass

    # Final message
    if online:
        if os_type == "windows":
            await query.edit_message_text(
                "BERHASIL! ✅\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "[✓] Menghubungkan ke VPS\n"
                "[✓] Download script\n"
                "[✓] Menjalankan installer\n"
                "[✓] Install OS selesai\n"
                "[✓] VPS online!\n\n"
                f"OS: {data['os_name']}\n"
                f"Status: BERHASIL DIUBAH!\n\n"
                "Login sekarang:\n"
                f"  RDP Host: {data['vps_ip']}:3389\n"
                "  Username: Administrator\n"
                "  Password: Bolehtuh1\n\n"
                "Gunakan /start untuk reinstall lagi."
            )
        else:
            # Fix Linux: enable root login and set password
            await asyncio.sleep(10)  # Wait for SSH to be fully ready
            try:
                fix_ssh = paramiko.SSHClient()
                fix_ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                # Try login as root first
                try:
                    fix_ssh.connect(
                        hostname=vps_ip, port=22,
                        username='root', password='Bolehtuh1',
                        timeout=15, allow_agent=False, look_for_keys=False,
                    )
                except Exception:
                    # Try as ubuntu user (cloud image default)
                    fix_ssh.connect(
                        hostname=vps_ip, port=22,
                        username='ubuntu', password='Bolehtuh1',
                        timeout=15, allow_agent=False, look_for_keys=False,
                    )

                # Enable root login and set password
                fix_commands = (
                    "echo 'root:Bolehtuh1' | sudo chpasswd; "
                    "sudo sed -i 's/#PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config; "
                    "sudo sed -i 's/PermitRootLogin.*/PermitRootLogin yes/' /etc/ssh/sshd_config; "
                    "sudo sed -i 's/#PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config; "
                    "sudo sed -i 's/PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config; "
                    "sudo systemctl restart sshd 2>/dev/null; "
                    "sudo service ssh restart 2>/dev/null; "
                    "echo 'FIX_DONE'"
                )
                stdin, stdout, stderr = fix_ssh.exec_command(fix_commands)
                stdout.channel.settimeout(15)
                fix_output = stdout.read().decode('utf-8', errors='ignore').strip()
                logger.info(f"Linux fix output: {fix_output}")
                fix_ssh.close()
            except Exception as e:
                logger.info(f"Linux fix failed (might already be OK): {e}")

            await query.edit_message_text(
                "BERHASIL! ✅\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "[✓] Menghubungkan ke VPS\n"
                "[✓] Download script\n"
                "[✓] Menjalankan installer\n"
                "[✓] Install OS selesai\n"
                "[✓] VPS online!\n"
                "[✓] Root login diaktifkan!\n\n"
                f"OS: {data['os_name']}\n"
                f"Status: BERHASIL DIUBAH!\n\n"
                "Login sekarang:\n"
                f"  SSH: ssh root@{data['vps_ip']}\n"
                "  Password: Bolehtuh1\n\n"
                "Gunakan /start untuk reinstall lagi."
            )
    else:
        await query.edit_message_text(
            "TIMEOUT ⚠️\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "[✓] Menghubungkan ke VPS\n"
            "[✓] Download script\n"
            "[✓] Menjalankan installer\n"
            "[?] VPS belum online setelah 30 menit\n\n"
            "Kemungkinan masih install. Coba cek manual:\n"
            f"  - RDP: {data['vps_ip']}:3389 (Windows)\n"
            f"  - SSH: ssh root@{data['vps_ip']} (Linux)\n"
            f"  - Cek VNC console di panel hosting\n\n"
            "Gunakan /start untuk reinstall lagi."
        )

    return ConversationHandler.END


async def run_install(query, context: ContextTypes.DEFAULT_TYPE, data: dict):
    """Connect to VPS via SSH and run the install command."""
    try:
        # Build the install command
        if data["os_type"] == "windows":
            # Windows uses leitbogioro/Tools
            install_script_url = "https://raw.githubusercontent.com/leitbogioro/Tools/master/Linux_reinstall/InstallNET.sh"
            install_cmd = f"/tmp/InstallNET.sh {data['os_cmd']} -lang '{data['lang']}' -pwd Bolehtuh1 -firmware"
            download_cmd = (
                f"wget --no-check-certificate -qO /tmp/InstallNET.sh '{install_script_url}' "
                "&& chmod a+x /tmp/InstallNET.sh && echo 'DOWNLOAD_OK' || echo 'DOWNLOAD_FAIL'"
            )
            run_cmd = f"bash {install_cmd} > /tmp/reinstall.log 2>&1; reboot"
        else:
            # Linux uses bin456789/reinstall (better password support)
            install_script_url = "https://raw.githubusercontent.com/bin456789/reinstall/main/reinstall.sh"
            install_cmd = f"reinstall.sh {data['os_cmd']} --password Bolehtuh1"
            download_cmd = (
                f"wget --no-check-certificate -qO /tmp/reinstall.sh '{install_script_url}' "
                "&& chmod a+x /tmp/reinstall.sh && echo 'DOWNLOAD_OK' || echo 'DOWNLOAD_FAIL'"
            )
            run_cmd = f"bash /tmp/reinstall.sh {data['os_cmd']} --password Bolehtuh1 > /tmp/reinstall.log 2>&1; reboot"

        # Loading: Step 1 - Connecting
        await query.edit_message_text(
            f"Menginstall {data['os_name']}...\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "[⏳] Menghubungkan ke VPS...\n"
            "[ ] Download script...\n"
            "[ ] Menjalankan installer...\n"
            "[ ] Menunggu reboot...\n"
            "[ ] Verifikasi selesai..."
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
            allow_agent=False,
            look_for_keys=False,
        )

        # Loading: Step 2 - Downloading
        await query.edit_message_text(
            f"Menginstall {data['os_name']}...\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "[✓] Menghubungkan ke VPS\n"
            "[⏳] Download script...\n"
            "[ ] Menjalankan installer...\n"
            "[ ] Menunggu reboot...\n"
            "[ ] Verifikasi selesai..."
        )

        # Step 1: Download install script and wait for it to finish
        logger.info(f"Downloading script to {data['vps_ip']}...")
        stdin, stdout, stderr = ssh.exec_command(download_cmd)
        # Wait for download to complete (max 60s)
        stdout.channel.settimeout(60)
        output = stdout.read().decode('utf-8', errors='ignore').strip()
        logger.info(f"Download result: {output}")

        if "DOWNLOAD_OK" not in output:
            context.user_data["error_msg"] = f"Gagal download script: {output}"
            ssh.close()
            return False

        # Loading: Step 3 - Running installer
        await query.edit_message_text(
            f"Menginstall {data['os_name']}...\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "[✓] Menghubungkan ke VPS\n"
            "[✓] Download script\n"
            "[⏳] Menjalankan installer...\n"
            "[ ] Menunggu reboot...\n"
            "[ ] Verifikasi selesai..."
        )

        # Step 2: Run install and reboot after completion
        logger.info(f"Running install: {run_cmd}")
        channel = ssh.get_transport().open_session()
        channel.exec_command(run_cmd)

        # Wait for script to download images and setup grub
        await asyncio.sleep(20)

        # Step 3: Check log to see progress
        try:
            stdin3, stdout3, stderr3 = ssh.exec_command("tail -10 /tmp/reinstall.log 2>/dev/null")
            await asyncio.sleep(3)
            check_output = stdout3.read().decode('utf-8', errors='ignore').strip()
            logger.info(f"Check output: {check_output}")
        except Exception:
            logger.info("SSH connection lost - VPS is rebooting (good!)")

        try:
            ssh.close()
        except Exception:
            pass

        return True

    except paramiko.AuthenticationException:
        context.user_data["error_msg"] = "Username atau password salah"
        logger.error("SSH Auth Error: Authentication failed")
        return False
    except paramiko.ssh_exception.NoValidConnectionsError as e:
        context.user_data["error_msg"] = f"Port {data['vps_port']} tidak bisa diakses"
        logger.error(f"SSH Connection Error: {e}")
        return False
    except TimeoutError:
        context.user_data["error_msg"] = "Timeout - VPS tidak merespon (offline?)"
        logger.error("SSH Timeout Error")
        return False
    except Exception as e:
        context.user_data["error_msg"] = str(e)
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
        "Cara pakai:\n"
        "1. Kirim /start\n"
        "2. Kirim detail VPS: ip password\n"
        "3. Pilih OS\n"
        "4. Selesai!\n\n"
        "Format detail VPS:\n"
        "  ip password\n"
        "  ip port password\n"
        "  ip port username password\n\n"
        "Contoh:\n"
        "  103.1.2.3 MyPass123\n"
        "  103.1.2.3 22 root MyPass123\n\n"
        "Perintah:\n"
        "  /start  - Mulai reinstall\n"
        "  /status - Cek VPS online/offline\n"
        "  /cancel - Batalkan\n"
        "  /help   - Bantuan\n\n"
        "OS tersedia:\n"
        "  Windows: 10, 11, Server 2012-2022\n"
        "  Linux: Debian, Ubuntu, CentOS, dll\n\n"
        "Login default:\n"
        "  Windows: Administrator / Bolehtuh1\n"
        "  Linux: root / Bolehtuh1"
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
            VPS_DETAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_vps_detail)],
            SELECT_OS: [CallbackQueryHandler(select_os, pattern="^os_"),
                        CallbackQueryHandler(select_os_category, pattern="^(cat_|back_)")],
            SELECT_LANG: [CallbackQueryHandler(select_lang, pattern="^lang_")],
            CONFIRM: [CallbackQueryHandler(confirm_install, pattern="^confirm_")],
        },
        fallbacks=[CommandHandler("cancel", cancel), CommandHandler("start", start)],
        allow_reentry=True,
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("help", help_command))

    print("Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
